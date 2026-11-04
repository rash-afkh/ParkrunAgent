"""Region-completion challenges: run *every* event in a region (DESIGN.md §5).

Unlike token/id challenges, a region challenge's targets are a fixed set of
event slugs (all the events in a state or country). You complete it by visiting
each one. The target set is injected as plain data, so this stays pure.

State assignment for Australia uses APPROXIMATE straight-line boundaries. The
WA border (129 degrees E) and the SA/NT border (26 degrees S) are exact, but the
NSW/VIC (Murray River) and QLD/NSW borders are irregular, so events near those
borders may be misclassified. `au_state` is isolated so it can later be replaced
with proper point-in-polygon lookup.
"""

from __future__ import annotations

from parkrun_agent.core.challenges.base import Challenge
from parkrun_agent.core.models import Athlete, ChallengeProgress, Event

AUSTRALIA_COUNTRY_CODE = 3
AU_STATES = ["WA", "NT", "SA", "QLD", "NSW", "ACT", "VIC", "TAS"]

# Region challenge keys recognised by config (whole country + each state).
REGION_KEYS = {"australia", *(f"au_{s.lower()}" for s in AU_STATES)}


def au_state(lat: float, lon: float) -> str:
    """Approximate Australian state/territory from coordinates (see module docstring)."""
    if lon < 129.0:
        return "WA"
    if lat >= -26.0:  # north of the SA/NT top border
        return "NT" if lon < 138.0 else "QLD"
    if lon < 141.0:  # south of 26 S, west of the eastern-states border
        return "SA"
    # Eastern states (east of 141 E, south of 26 S)
    if lat <= -40.0:
        return "TAS"
    if -35.92 <= lat <= -35.11 and 148.76 <= lon <= 149.40:
        return "ACT"
    if lat >= -29.0:
        return "QLD"
    if lat <= -36.0:
        return "VIC"
    return "NSW"


class RegionCompletionChallenge(Challenge):
    def __init__(self, key: str, name: str, target_slugs: set[str]):
        self.key = key
        self.name = name
        self.description = f"Run every parkrun in {name}."
        self.targets = set(target_slugs)

    def progress(self, athlete: Athlete) -> ChallengeProgress:
        done = self.targets & athlete.visited_slugs
        remaining = sorted(self.targets - athlete.visited_slugs)
        total = len(self.targets)
        percent = round(100 * len(done) / total, 1) if total else 100.0
        return ChallengeProgress(
            challenge=self.key, name=self.name,
            completed=sorted(done), remaining=remaining,
            percent=percent, is_complete=not remaining,
            summary=f"{len(done)}/{total} {self.name} events done ({len(remaining)} to go, {percent:g}%)",
        )

    def contribution(self, event: Event, athlete: Athlete) -> float:
        return 1.0 if event.slug in self.targets and event.slug not in athlete.visited_slugs else 0.0

    def slots(self, event: Event, athlete: Athlete) -> set[str]:
        if event.slug in self.targets and event.slug not in athlete.visited_slugs:
            return {f"{self.key}:{event.slug}"}
        return set()


def build_region_challenges(events: list[Event]) -> dict[str, RegionCompletionChallenge]:
    """Build the whole-Australia and per-state completion challenges from the catalogue."""
    au = [e for e in events if e.country_code == AUSTRALIA_COUNTRY_CODE]
    by_state: dict[str, set[str]] = {s: set() for s in AU_STATES}
    for e in au:
        by_state[au_state(e.lat, e.lon)].add(e.slug)

    challenges: dict[str, RegionCompletionChallenge] = {
        "australia": RegionCompletionChallenge("australia", "Australia", {e.slug for e in au})
    }
    for state in AU_STATES:
        key = f"au_{state.lower()}"
        challenges[key] = RegionCompletionChallenge(key, f"{state} (Australia)", by_state[state])
    return challenges
