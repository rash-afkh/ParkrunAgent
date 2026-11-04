"""Plain-text rendering of recommendations / progress, shared by the CLI and
the LangChain tools (so the agent and the CLI say the same thing)."""

from __future__ import annotations

from parkrun_agent.core.models import ChallengeProgress, Recommendation


def format_recommendations(recs: list[Recommendation], *, travel: bool) -> str:
    if not recs:
        return "No suggestions found in range."
    lines: list[str] = []

    def section(title: str, group: list[Recommendation]) -> None:
        if not group:
            return
        lines.append(title)
        for r in group:
            where = r.event.location or r.event.country_url or ""
            lines.append(f"  - {r.event.name} ({r.distance_km:g} km, {where}) [score {r.score:+.2f}]")
            for reason in r.reasons[:3]:
                lines.append(f"      * {reason}")

    if travel:
        section("Nearby:", recs)
    else:
        section("Local (nearby):", [r for r in recs if r.tier == "local"])
        section("Stretch (a bit further):", [r for r in recs if r.tier == "stretch"])
        section("Destination (worth travelling for):", [r for r in recs if r.tier == "destination"])
    return "\n".join(lines)


def format_progress(progress: list[ChallengeProgress]) -> str:
    lines: list[str] = []
    for p in progress:
        if p.summary is not None:
            lines.append(f"- {p.name}: {p.summary}")
            continue
        done = len(p.completed)
        total = done + len(p.remaining)
        flag = " (complete)" if p.is_complete else ""
        lines.append(f"- {p.name}: {done}/{total} ({p.percent:g}%){flag}")
        if p.remaining and not p.is_complete:
            shown = p.remaining[:15]
            more = "" if len(shown) == len(p.remaining) else f" (+{len(p.remaining) - len(shown)} more)"
            lines.append(f"    still needed: {' '.join(shown)}{more}")
    return "\n".join(lines)
