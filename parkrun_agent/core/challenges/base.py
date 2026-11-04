"""Challenge engine — the pluggable core (DESIGN.md §5).

A `Challenge` knows two things about an athlete:
  - progress(athlete)      -> where they stand (completed / remaining / %)
  - contribution(event, a) -> marginal value in [0, 1] of running `event` next

Most parkrun challenges are "collect a set of tokens derived from event names",
so `TokenCollectionChallenge` covers alphabet / pirates / compass and anything
a user defines in YAML. Challenges that need extra data or non-collection logic
(Wilson Index, Stopwatch Bingo) subclass `Challenge` directly in a later
milestone.

Pure module: no DB, no network, no LangChain.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Callable

from parkrun_agent.core.models import Athlete, ChallengeProgress, Event

TokenFn = Callable[[str], set[str]]

_COMPASS = {"NORTH", "SOUTH", "EAST", "WEST"}


def event_display_name(name: str) -> str:
    """Strip the 'parkrun' / 'junior parkrun' words so the distinguishing part
    of the name drives letter tokens (e.g. 'parkrun Vingis' -> 'Vingis')."""
    return re.sub(r"\b(junior\s+)?parkrun\b", " ", name, flags=re.IGNORECASE).strip()


def initial_letter(name: str) -> set[str]:
    """The first alphabetic character of the (cleaned) event name, uppercased."""
    for ch in event_display_name(name):
        if ch.isalpha():
            return {ch.upper()}
    return set()


def compass_words(name: str) -> set[str]:
    """Which of NORTH/SOUTH/EAST/WEST appear as words in the name."""
    words = {w.upper() for w in re.findall(r"[a-zA-Z]+", name)}
    return words & _COMPASS


class Challenge(ABC):
    key: str
    name: str
    description: str

    @abstractmethod
    def progress(self, athlete: Athlete) -> ChallengeProgress: ...

    @abstractmethod
    def contribution(self, event: Event, athlete: Athlete) -> float: ...


class TokenCollectionChallenge(Challenge):
    """Collect a target set of tokens, each derived from an event name."""

    def __init__(
        self,
        key: str,
        name: str,
        description: str,
        targets: list[str],
        token_fn: TokenFn,
    ):
        self.key = key
        self.name = name
        self.description = description
        # Preserve order for display; dedupe while keeping order.
        self.targets = list(dict.fromkeys(t.upper() for t in targets))
        self._target_set = set(self.targets)
        self.token_fn = token_fn

    def _covered(self, athlete: Athlete) -> set[str]:
        covered: set[str] = set()
        for event_name in athlete.distinct_event_names:
            covered |= self.token_fn(event_name) & self._target_set
        return covered

    def progress(self, athlete: Athlete) -> ChallengeProgress:
        covered = self._covered(athlete)
        completed = [t for t in self.targets if t in covered]
        remaining = [t for t in self.targets if t not in covered]
        total = len(self.targets)
        percent = round(100 * len(completed) / total, 1) if total else 100.0
        return ChallengeProgress(
            challenge=self.key,
            name=self.name,
            completed=completed,
            remaining=remaining,
            percent=percent,
            is_complete=not remaining,
        )

    def contribution(self, event: Event, athlete: Athlete) -> float:
        covered = self._covered(athlete)
        name = event.short_name or event.name
        new = (self.token_fn(name) & self._target_set) - covered
        return len(new) / len(self._target_set) if self._target_set else 0.0
