"""Crowd / field-size stats, stored as a compact per-athlete summary.

Rather than caching every event's full history, we keep one small summary per
athlete (most/least crowded run + location/date, average, coverage) and update
it incrementally: each refresh fetches field sizes only for the athlete's events
we haven't seen yet (capped unless `backfill=True`), tolerating cancelled events
whose pages 404. Historical runs are immutable, so the summary only ever gains
coverage.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Callable

from parkrun_agent.core.models import Athlete
from parkrun_agent.data.athlete_repo import set_crowd_summary
from parkrun_agent.data.event_occurrences import EventOccurrencesRepo
from parkrun_agent.data.events_catalogue import EventsCatalogue


def build_summary(athlete: Athlete, repo: EventOccurrencesRepo, catalogue: EventsCatalogue) -> dict | None:
    """Compute the summary from whatever field-size data is already cached."""
    by_slug = {e.slug: e for e in catalogue.all_events()}
    pairs = []
    for r in athlete.runs:
        if not r.event_slug:
            continue
        fin = repo.finishers_for(r.event_slug, r.run_number)
        if fin:
            pairs.append((r, fin))
    if not pairs:
        return None
    pairs.sort(key=lambda p: p[1])

    def entry(run, finishers):
        ev = by_slug.get(run.event_slug)
        return {
            "finishers": finishers,
            "event": run.event_name,
            "location": ev.location if ev else None,
            "date": run.run_date.isoformat(),
        }

    least_r, least = pairs[0]
    most_r, most = pairs[-1]
    return {
        "covered": len(pairs),
        "total_runs": athlete.total_runs,
        "avg": round(sum(f for _, f in pairs) / len(pairs)),
        "most": entry(most_r, most),
        "least": entry(least_r, least),
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def refresh(
    athlete: Athlete,
    repo: EventOccurrencesRepo,
    catalogue: EventsCatalogue,
    *,
    backfill: bool = False,
    max_new: int = 5,
    delay: float = 1.0,
    log: Callable[[str], None] = print,
) -> dict | None:
    """Fetch field sizes for not-yet-seen events (all if backfill, else up to
    max_new), rebuild the summary, persist it, and return it."""
    domains = {e.slug: e.country_url for e in catalogue.all_events()}
    needed = [
        slug for slug in sorted({r.event_slug for r in athlete.runs if r.event_slug})
        if not repo.has_event(slug)
    ]
    if not backfill:
        needed = needed[:max_new]

    for i, slug in enumerate(needed, 1):
        log(f"  [{i}/{len(needed)}] fetching field sizes: {slug}")
        try:
            repo.backfill_event(slug, domains.get(slug))
        except Exception as exc:  # noqa: BLE001 - cancelled/404 events are expected
            log(f"      unavailable ({exc}); won't retry")
            repo.mark_unavailable(slug)
        if delay and i < len(needed):
            time.sleep(delay)

    summary = build_summary(athlete, repo, catalogue)
    if summary is not None:
        set_crowd_summary(athlete.id, summary)
    return summary


def format_summary(summary: dict | None) -> str:
    if not summary:
        return ("No crowd data yet — run 'parkrun-agent athlete crowds --backfill' "
                "to fetch field sizes for your events.")

    def line(label: str, e: dict) -> str:
        loc = f", {e['location']}" if e.get("location") else ""
        return f"- {label}: {e['finishers']} finishers — {e['event']} ({e['date']}{loc})"

    return "\n".join([
        f"Crowd stats ({summary['covered']}/{summary['total_runs']} runs with data, "
        f"avg field {summary['avg']}):",
        line("Most crowded", summary["most"]),
        line("Least crowded", summary["least"]),
    ])
