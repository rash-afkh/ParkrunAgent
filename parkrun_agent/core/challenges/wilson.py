"""Wilson Index challenges (DESIGN.md §5), both event-id / founding-order based.

events.json assigns ids in establishment order (Bushy = 1, Wimbledon Common = 2,
...), so an event's id is its founding rank.

- WilsonIndexChallenge: the unbroken prefix from #1 (missing #3 caps you at 2).
- FloatingWilsonIndexChallenge: the longest run of consecutive ids anywhere in
  the sequence — no need to start at #1, so far more achievable.

Neither is a token-collection challenge; both take the id-ordered event list as
plain data (EventRef), keeping this module free of DB/network concerns. Only
active events are in the catalogue, so closed events drop out of the sequence.
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


def _build_id_maps(event_index: list[EventRef]) -> tuple[dict[str, int], dict[str, int]]:
    return (
        {e.slug.lower(): e.id for e in event_index},
        {e.name.lower(): e.id for e in event_index},
    )


def _completed_ids(athlete: Athlete, slug2id: dict[str, int], name2id: dict[str, int]) -> set[int]:
    ids: set[int] = set()
    for run in athlete.runs:
        if run.event_slug and run.event_slug.lower() in slug2id:
            ids.add(slug2id[run.event_slug.lower()])
        elif run.event_name and run.event_name.lower() in name2id:
            ids.add(name2id[run.event_name.lower()])
    return ids


def wilson_from_events(events: list[Event], next_preview: int = 5) -> "WilsonIndexChallenge":
    refs = [EventRef(id=e.id, slug=e.slug, name=e.name) for e in events]
    return WilsonIndexChallenge(refs, next_preview=next_preview)


def floating_wilson_from_events(events: list[Event]) -> "FloatingWilsonIndexChallenge":
    refs = [EventRef(id=e.id, slug=e.slug, name=e.name) for e in events]
    return FloatingWilsonIndexChallenge(refs)


class WilsonIndexChallenge(Challenge):
    key = "wilson"
    name = "Wilson Index"
    description = (
        "Run the parkrun events in their founding order (#1, #2, #3, ...). "
        "Your index is how far up the unbroken sequence from #1 you have reached."
    )

    def __init__(self, event_index: list[EventRef], next_preview: int = 5):
        self._seq = sorted(event_index, key=lambda e: e.id)
        self._slug2id, self._name2id = _build_id_maps(event_index)
        self._next_preview = next_preview

    def _index_blocker_upcoming(self, athlete: Athlete):
        cache = getattr(self, "_cache", None)
        if cache is not None and cache[0] == id(athlete):
            return cache[1]
        done = _completed_ids(athlete, self._slug2id, self._name2id)
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
        _index, blocker, _upcoming = self._index_blocker_upcoming(athlete)
        return 1.0 if blocker is not None and event.id == blocker.id else 0.0

    def slots(self, event: Event, athlete: Athlete) -> set[str]:
        _index, blocker, _upcoming = self._index_blocker_upcoming(athlete)
        if blocker is not None and event.id == blocker.id:
            return {f"wilson:#{blocker.id}"}
        return set()


class FloatingWilsonIndexChallenge(Challenge):
    key = "floating_wilson"
    name = "Floating Wilson Index"
    description = (
        "The longest run of consecutively-numbered events (by founding order) you "
        "have completed anywhere in the sequence — you don't have to start at #1, "
        "so it's far more achievable than the standard Wilson Index."
    )

    def __init__(self, event_index: list[EventRef], gain_cap: int = 3, next_preview: int = 3):
        self._by_id = {e.id: e for e in event_index}
        self._slug2id, self._name2id = _build_id_maps(event_index)
        self._gain_cap = gain_cap
        self._next_preview = next_preview

    def _done(self, athlete: Athlete) -> set[int]:
        cache = getattr(self, "_cache", None)
        if cache is not None and cache[0] == id(athlete):
            return cache[1]
        done = _completed_ids(athlete, self._slug2id, self._name2id)
        self._cache = (id(athlete), done)
        return done

    @staticmethod
    def _best_run(done: set[int]) -> tuple[int, tuple[int, int]]:
        best_len, best = 0, (0, 0)
        for x in done:
            if x - 1 not in done:  # start of a consecutive run
                y = x
                while y + 1 in done:
                    y += 1
                if y - x + 1 > best_len:
                    best_len, best = y - x + 1, (x, y)
        return best_len, best

    def _run_len_if_added(self, k: int, done: set[int]) -> int:
        if k in done:
            return 0
        down = 0
        j = k - 1
        while j in done:
            down += 1
            j -= 1
        up = 0
        j = k + 1
        while j in done:
            up += 1
            j += 1
        return down + up + 1

    def _gain(self, k: int, done: set[int], current_max: int) -> int:
        """How much running event #k would grow the longest consecutive run."""
        return max(0, self._run_len_if_added(k, done) - current_max)

    def progress(self, athlete: Athlete) -> ChallengeProgress:
        done = self._done(athlete)
        current_max, (lo, hi) = self._best_run(done)
        if not done:
            return ChallengeProgress(
                challenge=self.key, name=self.name, completed=[], remaining=[],
                percent=0.0, is_complete=False,
                summary="Index 0 — run any event to start a streak.",
            )
        targets = sorted(
            ((self._gain(k, done, current_max), k) for k in self._by_id if k not in done),
            key=lambda t: (-t[0], t[1]),
        )
        remaining = [
            f"#{k} {self._by_id[k].name} (+{g})" for g, k in targets[: self._next_preview] if g > 0
        ]
        tip = ("extend it with " + ", ".join(remaining)) if remaining else "no active neighbour found"
        return ChallengeProgress(
            challenge=self.key, name=self.name, completed=[], remaining=remaining,
            percent=0.0, is_complete=False,
            summary=f"Index {current_max} (events #{lo}-#{hi}); {tip}",
        )

    def contribution(self, event: Event, athlete: Athlete) -> float:
        done = self._done(athlete)
        current_max, _ = self._best_run(done)
        return 1.0 if self._gain(event.id, done, current_max) > 0 else 0.0

    def slots(self, event: Event, athlete: Athlete) -> set[str]:
        done = self._done(athlete)
        current_max, _ = self._best_run(done)
        gain = self._gain(event.id, done, current_max)
        if gain <= 0:
            return set()
        # More slots for a bigger jump (e.g. a gap-fill bridging two runs),
        # capped so one event can't dominate scoring.
        return {f"floating_wilson:{event.id}#{i}" for i in range(min(gain, self._gain_cap))}
