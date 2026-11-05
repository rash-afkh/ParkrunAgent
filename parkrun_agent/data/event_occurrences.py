"""Event-occurrence (field size) repository.

Each event's history page lists every staging with its finisher count. Historical
rows never change, so we fetch an event's history once and cache every occurrence
permanently. One fetch per distinct event the athlete has run — not per run.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Callable

from bs4 import BeautifulSoup
from sqlalchemy import select

from parkrun_agent.data import fetchers
from parkrun_agent.data.cache import get_session
from parkrun_agent.data.schema import EventOccurrenceRow

HistoryFetcher = Callable[[str, str], str]


def parse_event_history(html: str) -> list[tuple[int, int, int | None]]:
    """Return [(run_number, finishers, volunteers)] from an event-history page.

    Columns are identified by their in-cell label text ('... finishers' /
    '... volunteers') rather than header position, because parkrun's responsive
    table duplicates values and shifts columns."""
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table")
    if table is None:
        return []
    out: list[tuple[int, int, int | None]] = []
    for tr in (table.find("tbody") or table).find_all("tr"):
        tds = tr.find_all("td")
        if not tds:
            continue
        head = re.match(r"\s*(\d+)\s*$", tds[0].get_text(" ", strip=True))
        if not head:  # first cell is the event number
            continue
        run_number = int(head.group(1))
        finishers = volunteers = None
        for td in tds:
            text = td.get_text(" ", strip=True).lower()
            lead = re.match(r"\s*(\d+)", text)
            if not lead:
                continue
            if "finisher" in text and "first" not in text:
                finishers = int(lead.group(1))
            elif "volunteer" in text:
                volunteers = int(lead.group(1))
        if finishers is not None:
            out.append((run_number, finishers, volunteers))
    return out


class EventOccurrencesRepo:
    def __init__(self, fetcher: HistoryFetcher | None = None):
        self._fetch = fetcher or fetchers.fetch_event_history_html

    def has_event(self, slug: str) -> bool:
        with get_session() as s:
            return s.scalar(
                select(EventOccurrenceRow).where(EventOccurrenceRow.event_slug == slug).limit(1)
            ) is not None

    def finishers_for(self, slug: str, run_number: int) -> int | None:
        with get_session() as s:
            row = s.get(EventOccurrenceRow, (slug, run_number))
            return row.finishers if row else None

    def backfill_event(self, slug: str, domain: str | None = None, now: datetime | None = None) -> int:
        """Fetch one event's history (from its home-country domain) and cache all
        its occurrences. Event pages are domain-specific, unlike athlete pages."""
        now = now or datetime.now(timezone.utc)
        domain = domain or fetchers.PARKRUN_DEFAULT_DOMAIN
        occurrences = parse_event_history(self._fetch(slug, domain))
        with get_session() as s:
            for run_number, finishers, volunteers in occurrences:
                s.merge(
                    EventOccurrenceRow(
                        event_slug=slug, run_number=run_number,
                        finishers=finishers, volunteers=volunteers, fetched_at=now,
                    )
                )
            if not occurrences:
                self._mark(s, slug, now)
            s.commit()
        return len(occurrences)

    def mark_unavailable(self, slug: str, now: datetime | None = None) -> None:
        """Record that an event's history couldn't be fetched (e.g. cancelled /
        404), so it isn't retried on every weekly update."""
        with get_session() as s:
            self._mark(s, slug, now or datetime.now(timezone.utc))
            s.commit()

    @staticmethod
    def _mark(session, slug: str, now: datetime) -> None:
        # Sentinel row (run_number 0 never occurs) marking "fetched, no data".
        session.merge(
            EventOccurrenceRow(event_slug=slug, run_number=0, finishers=None, volunteers=None, fetched_at=now)
        )
