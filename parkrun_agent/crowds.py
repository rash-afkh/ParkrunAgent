"""Crowd / field-size stats: match each of an athlete's runs to the finisher
count of that specific event staging, and report the most/least crowded.

The finisher data needs one event-history fetch per distinct event (cached
permanently), so backfilling is opt-in and rate-limited.
"""

from __future__ import annotations

import time
from typing import Callable

from parkrun_agent.core.models import Athlete, Run
from parkrun_agent.data.event_occurrences import EventOccurrencesRepo
from parkrun_agent.data.events_catalogue import EventsCatalogue


def backfill_crowds(
    athlete: Athlete,
    repo: EventOccurrencesRepo,
    catalogue: EventsCatalogue | None = None,
    *,
    max_events: int | None = None,
    delay: float = 1.0,
    log: Callable[[str], None] = print,
) -> int:
    """Fetch event histories for the athlete's distinct events not yet cached.
    Each event page lives on its home-country domain, resolved from the catalogue.
    Returns the number of events fetched. Polite: one request per `delay` seconds."""
    domains = {e.slug: e.country_url for e in catalogue.all_events()} if catalogue else {}
    slugs = sorted({r.event_slug for r in athlete.runs if r.event_slug})
    todo = [s for s in slugs if not repo.has_event(s)]
    if max_events is not None:
        todo = todo[:max_events]
    for i, slug in enumerate(todo, 1):
        log(f"  [{i}/{len(todo)}] fetching event history: {slug}")
        try:
            repo.backfill_event(slug, domains.get(slug))
        except Exception as exc:  # noqa: BLE001 - one bad event shouldn't stop the rest
            log(f"      skipped {slug}: {exc}")
        if delay and i < len(todo):
            time.sleep(delay)
    return len(todo)


def runs_with_finishers(athlete: Athlete, repo: EventOccurrencesRepo) -> list[tuple[Run, int]]:
    out: list[tuple[Run, int]] = []
    for r in athlete.runs:
        if not r.event_slug:
            continue
        fin = repo.finishers_for(r.event_slug, r.run_number)
        if fin:
            out.append((r, fin))
    return out


def format_crowds(pairs: list[tuple[Run, int]], *, distinct_events: int, total_runs: int) -> str:
    if not pairs:
        return ("No field-size data cached yet — run 'parkrun-agent athlete crowds' "
                "to fetch it (one request per distinct event).")
    pairs_sorted = sorted(pairs, key=lambda p: p[1])
    least_run, least = pairs_sorted[0]
    most_run, most = pairs_sorted[-1]
    avg = sum(f for _, f in pairs) / len(pairs)
    coverage = f"{len(pairs)}/{total_runs} runs"
    return "\n".join([
        f"Crowd stats ({coverage} with field-size data):",
        f"- Average field size on your runs: {avg:.0f}",
        f"- Most crowded: {most} finishers — {most_run.event_name} ({most_run.run_date})",
        f"- Least crowded: {least} finishers — {least_run.event_name} ({least_run.run_date})",
    ])
