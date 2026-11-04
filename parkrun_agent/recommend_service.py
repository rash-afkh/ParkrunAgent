"""Recommendation service — orchestrates the catalogue + the pure scorer.

Separated from core/recommend.py so the scoring stays pure/testable while this
layer handles the DB-backed candidate generation (near query + global
destination scan) and policy (adult-only events, travel vs home behaviour).
"""

from __future__ import annotations

from parkrun_agent.core.challenges.base import Challenge
from parkrun_agent.core.geo import GeoPoint, haversine_km
from parkrun_agent.core.models import Athlete, Event, Recommendation
from parkrun_agent.core.recommend import (
    ScoringParams,
    build_slot_counts,
    score_event,
)
from parkrun_agent.data.events_catalogue import EventsCatalogue

# series 1 = 5k parkrun, 2 = junior 2k. Recommend adult events only by default.
DEFAULT_SERIES = frozenset({1})


class RecommendationService:
    def __init__(self, catalogue: EventsCatalogue | None = None, series_ids=DEFAULT_SERIES):
        self.catalogue = catalogue or EventsCatalogue()
        self.series_ids = frozenset(series_ids)

    def recommend(
        self,
        athlete: Athlete,
        challenges: list[Challenge],
        origin: GeoPoint,
        params: ScoringParams,
        *,
        travel: bool = False,
        max_local: int = 5,
        max_stretch: int = 5,
        max_destination: int = 3,
    ) -> list[Recommendation]:
        visited = athlete.visited_slugs
        near = [
            (ev, dist)
            for ev, dist in self.catalogue.near(origin, params.stretch_radius_km)
            if ev.series_id in self.series_ids
        ]

        if travel:
            # You're already in the region: no distance penalty. Surface events
            # that advance a challenge OR are simply new to you, nearest first.
            counts = build_slot_counts([ev for ev, _ in near], athlete, challenges)
            recs = [
                score_event(ev, dist, athlete, challenges, params, visited, counts, ignore_distance=True)
                for ev, dist in near
            ]
            picks = [r for r in recs if r.challenge_contributions or r.event.slug not in visited]
            picks.sort(key=lambda r: (-r.score, r.distance_km))
            return picks[: max_local + max_stretch]

        # Home mode: distance matters, and the global destination scan applies.
        slot_counts = build_slot_counts([ev for ev, _ in near], athlete, challenges)
        near_recs = [
            score_event(ev, dist, athlete, challenges, params, visited, slot_counts)
            for ev, dist in near
        ]
        local = _top(
            [r for r in near_recs if r.tier == "local" and (r.challenge_contributions or r.score > 0)],
            max_local,
        )
        stretch = _top(
            [r for r in near_recs if r.tier == "stretch" and r.challenge_contributions],
            max_stretch,
        )
        destination = self._destinations(
            athlete, challenges, origin, params, set(slot_counts), visited, max_destination
        )
        return local + stretch + destination

    def _destinations(
        self,
        athlete: Athlete,
        challenges: list[Challenge],
        origin: GeoPoint,
        params: ScoringParams,
        near_slots: set[str],
        visited: set[str],
        limit: int,
    ) -> list[Recommendation]:
        """High-value events beyond the stretch radius that fill slots you
        simply can't reach locally (e.g. the Wilson blocker, a missing letter
        with no nearby event). Distance is ignored in scoring."""
        far: list[tuple[Event, float, set[str]]] = []
        for ev in self.catalogue.all_events():
            if ev.series_id not in self.series_ids:
                continue
            dist = haversine_km(origin, ev.point)
            if dist <= params.stretch_radius_km:
                continue
            fills: set[str] = set()
            for ch in challenges:
                fills |= ch.slots(ev, athlete)
            unique = fills - near_slots  # not obtainable near home
            if unique:
                far.append((ev, dist, unique))

        allowed = {s for _ev, _d, u in far for s in u}
        far_counts = build_slot_counts([ev for ev, _d, _u in far], athlete, challenges)
        recs = [
            score_event(
                ev, dist, athlete, challenges, params, visited, far_counts,
                ignore_distance=True, allowed_slots=allowed,
            )
            for ev, dist, _u in far
        ]
        return _top([r for r in recs if r.challenge_contributions], limit)


def _top(recs: list[Recommendation], n: int) -> list[Recommendation]:
    return sorted(recs, key=lambda r: r.score, reverse=True)[:n]
