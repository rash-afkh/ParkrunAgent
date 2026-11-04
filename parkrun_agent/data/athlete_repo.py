"""Athlete repository: scrape a profile, parse it, cache it, serve it.

Read-through with a "fresh until next Saturday" TTL. The HTML parser is a pure
function (`parse_athlete_html`) so it is unit-tested against a saved fixture and
never needs the network.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Callable

from bs4 import BeautifulSoup
from sqlalchemy import delete, select

from parkrun_agent.core.models import Athlete, Run
from parkrun_agent.data import fetchers
from parkrun_agent.data.cache import get_session, is_athlete_fresh
from parkrun_agent.data.schema import AthleteRow, RunRow

HtmlFetcher = Callable[[int], str]


# --- Pure parsing helpers ------------------------------------------------


def parse_time_to_seconds(text: str) -> int | None:
    """'19:34' -> 1174, '1:02:33' -> 3753."""
    text = text.strip()
    if not re.match(r"^\d{1,2}(:\d{2}){1,2}$", text):
        return None
    parts = [int(p) for p in text.split(":")]
    seconds = 0
    for part in parts:
        seconds = seconds * 60 + part
    return seconds


def parse_date(text: str) -> date | None:
    """parkrun prints dd/mm/yyyy."""
    text = text.strip()
    try:
        d, m, y = (int(x) for x in text.split("/"))
        return date(y, m, d)
    except (ValueError, TypeError):
        return None


def parse_age_grade(text: str) -> float | None:
    text = text.strip().rstrip("%").strip()
    try:
        return float(text) if text else None
    except ValueError:
        return None


def _slug_from_href(href: str | None) -> str | None:
    if not href:
        return None
    # e.g. https://www.parkrun.org.uk/bushy/results/  -> 'bushy'
    m = re.search(r"https?://[^/]+/([^/]+)/", href + "/")
    return m.group(1) if m else None


def _find_results_table(soup: BeautifulSoup):
    """Pick the results table.

    A profile page can contain several tables whose headers mention 'Run Date'
    (e.g. a 10-row 'Most Recent parkruns' table alongside the full 'All Results'
    table). We want the full one, so among all candidates we take the table with
    the most data rows.
    """
    best = None
    best_headers: list[str] = []
    best_rows = -1
    for table in soup.find_all("table"):
        headers = [th.get_text(" ", strip=True).lower() for th in table.find_all("th")]
        if not any("run date" in h for h in headers):
            continue
        body = table.find("tbody") or table
        n_rows = len(body.find_all("tr"))
        if n_rows > best_rows:
            best, best_headers, best_rows = table, headers, n_rows
    return best, best_headers


def _column_index(headers: list[str], *needles: str) -> int | None:
    for i, h in enumerate(headers):
        if any(n in h for n in needles):
            return i
    return None


def parse_athlete_html(html: str, athlete_id: int) -> Athlete:
    """Parse an athleteresultshistory page into an Athlete (pure, offline)."""
    soup = BeautifulSoup(html, "lxml")

    name = None
    heading = soup.find(["h2", "h1"])
    if heading:
        name = re.sub(r"\s*\(A\d+\)\s*$", "", heading.get_text(strip=True)).strip() or None

    home_event = None
    m = re.search(r"home parkrun is\s+(.+?)[.<\n]", soup.get_text(" ", strip=True), re.I)
    if m:
        home_event = m.group(1).strip()

    table, headers = _find_results_table(soup)
    runs: list[Run] = []
    if table is not None:
        i_event = _column_index(headers, "event") or 0
        i_date = _column_index(headers, "run date", "date")
        i_num = _column_index(headers, "run number", "number")
        i_pos = _column_index(headers, "pos")
        i_time = _column_index(headers, "time")
        i_ag = _column_index(headers, "age grade", "grade")

        body = table.find("tbody") or table
        for tr in body.find_all("tr"):
            cells = tr.find_all("td")
            if not cells or len(cells) <= i_event:
                continue

            event_cell = cells[i_event]
            link = event_cell.find("a")
            event_name = (link or event_cell).get_text(strip=True)
            if not event_name:
                continue
            event_slug = _slug_from_href(link.get("href")) if link else None

            def cell(idx: int | None) -> str:
                return cells[idx].get_text(strip=True) if idx is not None and idx < len(cells) else ""

            run_date = parse_date(cell(i_date))
            time_seconds = parse_time_to_seconds(cell(i_time))
            if run_date is None or time_seconds is None:
                continue  # skip malformed / summary rows

            num_text = cell(i_num)
            pos_text = cell(i_pos)
            runs.append(
                Run(
                    event_name=event_name,
                    event_slug=event_slug,
                    run_date=run_date,
                    run_number=int(num_text) if num_text.isdigit() else 0,
                    time_seconds=time_seconds,
                    position=int(pos_text) if pos_text.isdigit() else None,
                    age_grade=parse_age_grade(cell(i_ag)),
                )
            )

    return Athlete(id=athlete_id, name=name, home_event=home_event, runs=runs)


# --- Repository ----------------------------------------------------------


def _row_to_athlete(row: AthleteRow) -> Athlete:
    runs = [
        Run(
            event_name=r.event_name,
            event_slug=r.event_slug,
            run_date=r.run_date,
            run_number=r.run_number,
            time_seconds=r.time_seconds,
            position=r.position,
            age_grade=r.age_grade,
        )
        for r in sorted(row.runs, key=lambda r: r.run_date)
    ]
    return Athlete(id=row.id, name=row.name, home_event=row.home_event, runs=runs)


class AthleteRepository:
    def __init__(self, fetcher: HtmlFetcher | None = None):
        self._fetch = fetcher or fetchers.fetch_athlete_history_html

    def get(self, athlete_id: int, *, force: bool = False, now: datetime | None = None) -> Athlete:
        now = now or datetime.now(timezone.utc)
        with get_session() as s:
            row = s.get(AthleteRow, athlete_id)
            if row is not None and not force and is_athlete_fresh(row.fetched_at, now):
                return _row_to_athlete(row)

        try:
            html = self._fetch(athlete_id)
            athlete = parse_athlete_html(html, athlete_id)
            self._store(athlete, html, now)
            return athlete
        except Exception:
            # Fail-soft: serve stale cache if we have it, else re-raise.
            with get_session() as s:
                row = s.get(AthleteRow, athlete_id)
                if row is not None:
                    return _row_to_athlete(row)
            raise

    def _store(self, athlete: Athlete, html: str, now: datetime) -> None:
        with get_session() as s:
            s.merge(
                AthleteRow(
                    id=athlete.id,
                    name=athlete.name,
                    home_event=athlete.home_event,
                    fetched_at=now,
                    raw_html=html,
                )
            )
            # Full-history scrape: replace this athlete's runs wholesale.
            s.execute(delete(RunRow).where(RunRow.athlete_id == athlete.id))
            for r in athlete.runs:
                s.add(
                    RunRow(
                        athlete_id=athlete.id,
                        event_name=r.event_name,
                        event_slug=r.event_slug,
                        run_date=r.run_date,
                        run_number=r.run_number,
                        time_seconds=r.time_seconds,
                        position=r.position,
                        age_grade=r.age_grade,
                    )
                )
            s.commit()

    def cached(self, athlete_id: int) -> Athlete | None:
        with get_session() as s:
            row = s.get(AthleteRow, athlete_id)
            return _row_to_athlete(row) if row else None
