"""Recommendation scoring — the pure brain (DESIGN.md §6).

No DB, no network, no LLM. Given an athlete, candidate events (with distances),
active challenges and scoring params, produce ranked `Recommendation`s with
human-readable reasons.

Scoring per candidate event:

    challenge_value = Σ_challenges w_c · Σ_slots (BASE_FILL + scarcity(slot))
    score           = challenge_value + w_novelty·novelty − w_distance·penalty(distance)

`scarcity(slot) = 1 / (candidates in scope that fill the same slot)`, so the
only event filling a rare slot in range scores far higher than one of many
filling a common one. Distance penalty is 0 within the local radius, then ramps
linearly to the stretch radius.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from parkrun_agent.core.challenges.base import Challenge
from parkrun_agent.core.models import Athlete, Event, Recommendation

BASE_FILL_VALUE = 0.5  # value of any fill before the scarcity bonus


@dataclass
class ScoringParams:
    local_radius_km: float = 50.0
    stretch_radius_km: float = 200.0
    challenge_weights: dict[str, float] = field(default_factory=dict)
    novelty_weight: float = 0.3
    distance_weight: float = 1.0


def distance_penalty(dist_km: float, params: ScoringParams) -> float:
    if dist_km <= params.local_radius_km:
        return 0.0
    if dist_km >= params.stretch_radius_km:
        return 1.0
    span = params.stretch_radius_km - params.local_radius_km
    return (dist_km - params.local_radius_km) / span if span > 0 else 1.0


def tier_for(dist_km: float, params: ScoringParams) -> str:
    if dist_km <= params.local_radius_km:
        return "local"
    if dist_km <= params.stretch_radius_km:
        return "stretch"
    return "destination"


def build_slot_counts(
    events: list[Event], athlete: Athlete, challenges: list[Challenge]
) -> dict[str, int]:
    """How many of `events` fill each slot — the scarcity denominator."""
    counts: dict[str, int] = {}
    for ev in events:
        for ch in challenges:
            for slot in ch.slots(ev, athlete):
                counts[slot] = counts.get(slot, 0) + 1
    return counts


def _slot_label(slot: str) -> str:
    return slot.split(":", 1)[1] if ":" in slot else slot


def score_event(
    event: Event,
    dist_km: float,
    athlete: Athlete,
    challenges: list[Challenge],
    params: ScoringParams,
    visited: set[str],
    slot_counts: dict[str, int],
    *,
    ignore_distance: bool = False,
    allowed_slots: set[str] | None = None,
) -> Recommendation:
    challenge_value = 0.0
    contributions: dict[str, float] = {}
    reasons: list[str] = []

    for ch in challenges:
        slots = ch.slots(event, athlete)
        if allowed_slots is not None:
            slots = {s for s in slots if s in allowed_slots}
        if not slots:
            continue
        weight = params.challenge_weights.get(ch.key, 1.0)
        value = 0.0
        for slot in slots:
            n = slot_counts.get(slot, 1)
            value += BASE_FILL_VALUE + 1.0 / n
            rarity = "the only option in range" if n <= 1 else f"1 of {n} in range"
            reasons.append(f"{ch.name}: fills {_slot_label(slot)} ({rarity})")
        challenge_value += weight * value
        contributions[ch.key] = round(weight * value, 3)

    novelty = 1.0 if event.slug not in visited else 0.0
    if novelty and not contributions:
        reasons.append("A new event you haven't run yet")

    penalty = 0.0 if ignore_distance else distance_penalty(dist_km, params)
    score = challenge_value + params.novelty_weight * novelty - params.distance_weight * penalty

    return Recommendation(
        event=event,
        distance_km=round(dist_km, 1),
        score=round(score, 3),
        tier=tier_for(dist_km, params),
        reasons=reasons,
        challenge_contributions=contributions,
    )
