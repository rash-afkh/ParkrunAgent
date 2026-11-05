"""Rich athlete summary: runs, distinct events, countries, clubs, date range,
most-visited event, PBs, and the two farthest-apart events the athlete has run.

Needs the catalogue to resolve event coordinates/countries from run slugs.
"""

from __future__ import annotations

from collections import Counter

from parkrun_agent.core.geo import haversine_km
from parkrun_agent.core.models import Athlete
from parkrun_agent.data.events_catalogue import EventsCatalogue


def _fmt_time(seconds: int) -> str:
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def athlete_summary(athlete: Athlete, catalogue: EventsCatalogue) -> str:
    a = athlete
    if not a.runs:
        return f"{a.name or 'Athlete'} (A{a.id}) has no recorded runs."

    by_slug = {e.slug: e for e in catalogue.all_events()}
    ran_events = [by_slug[r.event_slug] for r in a.runs if r.event_slug in by_slug]

    lines = [f"{a.name or 'Athlete'} (A{a.id})"]
    lines.append(f"- Total parkruns: {a.total_runs}  (~{a.total_runs * 5} km of 5k runs)")
    lines.append(f"- Distinct events: {len(a.distinct_event_names)}")

    if ran_events:
        countries = {e.country_code for e in ran_events}
        lines.append(f"- Countries: {len(countries)}")

    dates = sorted(r.run_date for r in a.runs)
    years = (dates[-1] - dates[0]).days / 365.25
    lines.append(f"- Active: {dates[0]} to {dates[-1]}  ({years:.1f} years)")

    most_event, most_n = Counter(r.event_name for r in a.runs).most_common(1)[0]
    lines.append(f"- Most-visited event: {most_event} ({most_n} runs)")

    timed = [r for r in a.runs if r.time_seconds]
    if timed:
        pb = min(timed, key=lambda r: r.time_seconds)
        lines.append(f"- Fastest run: {_fmt_time(pb.time_seconds)} at {pb.event_name} ({pb.run_date})")
    graded = [r for r in a.runs if r.age_grade]
    if graded:
        best = max(graded, key=lambda r: r.age_grade)
        lines.append(f"- Best age grade: {best.age_grade:g}% at {best.event_name}")

    if len(ran_events) >= 2:
        far_km, pair = 0.0, (ran_events[0], ran_events[0])
        for i in range(len(ran_events)):
            for j in range(i + 1, len(ran_events)):
                d = haversine_km(ran_events[i].point, ran_events[j].point)
                if d > far_km:
                    far_km, pair = d, (ran_events[i], ran_events[j])
        lines.append(f"- Farthest-apart events: {far_km:.0f} km — {pair[0].name} <-> {pair[1].name}")

    # Stored crowd summary only — never triggers fetches from describe.
    cs = a.crowd_summary
    if cs:
        m, l = cs["most"], cs["least"]
        lines.append(
            f"- Field sizes (from {cs['covered']}/{cs['total_runs']} runs): avg {cs['avg']}, "
            f"busiest {m['finishers']} ({m['event']}), quietest {l['finishers']} ({l['event']})"
        )

    if a.volunteer_count is not None:
        top = sorted(a.volunteer_roles.items(), key=lambda kv: kv[1], reverse=True)[:3]
        roles = f" (top: {', '.join(f'{r} ×{n}' for r, n in top)})" if top else ""
        lines.append(f"- Volunteering: {a.volunteer_count} occasions{roles}")

    if a.clubs:
        lines.append(f"- Clubs: {', '.join(a.clubs)}")

    return "\n".join(lines)
