"""Wilson Index challenge (DESIGN.md §5).

The Wilson Index is the length of the unbroken run of events, in founding order
(#1, #2, #3, ...), that an athlete has completed. Missing event #3 caps the
index at 2 even if later events are done. events.json assigns ids in
establishment order (Bushy = 1, Wimbledon Common = 2, ...), so the id doubles as
founding rank.

This is NOT a token-collection challenge — it needs the id-ordered event list,
which is injected as plain data (`EventRef`s) so this module stays free of DB /
network concerns. Only *active* events appear in the catalogue, so a closed
event simply drops out of the sequence; we never recommend an event that no
longer exists.
"""

from __future__ import annotations

from dataclasses import dataclass

from parkrun_agent.core.challenges.base import Challenge
from parkrun_agent.core.models import Athlete, ChallengeProgress, Event


@dataclass(frozen=True)
class EventRef:
    id: int
    slug: str
    name: str


def wilson_from_events(events: list[Event], next_preview: int = 5) -> "WilsonIndexChallenge":
    refs = [EventRef(id=e.id, slug=e.slug, name=e.name) for e in events]
    return WilsonIndexChallenge(refs, next_preview=next_preview)


class WilsonIndexChallenge(Challenge):
    key = "wilson"
    name = "Wilson Index"
    description = (
        "Run at the parkrun events in their founding order (#1, #2, #3, ...). "
        "Your index is how far up the unbroken sequence you have reached."
    )

    def __init__(self, event_index: list[EventRef], next_preview: int = 5):
        self._seq = sorted(event_index, key=lambda e: e.id)
        self._slug2id = {e.slug.lower(): e.id for e in event_index}
        self._name2id = {e.name.lower(): e.id for e in event_index}
        self._next_preview = next_preview

    def _completed_ids(self, athlete: Athlete) -> set[int]:
        ids: set[int] = set()
        for run in athlete.runs:
            if run.event_slug and run.event_slug.lower() in self._slug2id:
                ids.add(self._slug2id[run.event_slug.lower()])
            elif run.event_name and run.event_name.lower() in self._name2id:
                ids.add(self._name2id[run.event_name.lower()])
        return ids

    def _index_blocker_upcoming(self, athlete: Athlete):
        """Return (index, blocker_or_None, [upcoming needed refs]).

        index = count of leading consecutive completed events in founding order;
        blocker = the first not-yet-done event (the single highest-value target).
        """
        cache = getattr(self, "_cache", None)
        if cache is not None and cache[0] == id(athlete):
            return cache[1]
        done = self._completed_ids(athlete)
        index = 0
        blocker: EventRef | None = None
        upcoming: list[EventRef] = []
        for ref in self._seq:
            if blocker is None:
                if ref.id in done:
                    index += 1
                else:
                    blocker = ref
            elif ref.id not in done:
                upcoming.append(ref)
                if len(upcoming) >= self._next_preview:
                    break
        result = (index, blocker, upcoming)
        self._cache = (id(athlete), result)
        return result

    def progress(self, athlete: Athlete) -> ChallengeProgress:
        index, blocker, upcoming = self._index_blocker_upcoming(athlete)
        if blocker is None:
            return ChallengeProgress(
                challenge=self.key, name=self.name, completed=[], remaining=[],
                percent=100.0, is_complete=True,
                summary=f"Index {index} — every active event completed in sequence!",
            )
        remaining = [f"#{blocker.id} {blocker.name}"] + [f"#{u.id} {u.name}" for u in upcoming]
        return ChallengeProgress(
            challenge=self.key, name=self.name, completed=[], remaining=remaining,
            percent=0.0, is_complete=False,
            summary=f"Index {index} — next needed: #{blocker.id} {blocker.name}",
        )

    def contribution(self, event: Event, athlete: Athlete) -> float:
        """Only the single blocker advances the index, so only it scores."""
        _index, blocker, _upcoming = self._index_blocker_upcoming(athlete)
        return 1.0 if blocker is not None and event.id == blocker.id else 0.0

    def slots(self, event: Event, athlete: Athlete) -> set[str]:
        _index, blocker, _upcoming = self._index_blocker_upcoming(athlete)
        if blocker is not None and event.id == blocker.id:
            return {f"wilson:#{blocker.id}"}
        return set()
