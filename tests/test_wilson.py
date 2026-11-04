from datetime import date

from parkrun_agent.core.challenges.wilson import (
    EventRef,
    FloatingWilsonIndexChallenge,
    WilsonIndexChallenge,
)
from parkrun_agent.core.models import Athlete, Event, Run

# Founding order: Bushy(1), Wimbledon(2), Banstead(3), Richmond(4).
INDEX = [
    EventRef(1, "bushy", "Bushy parkrun"),
    EventRef(2, "wimbledoncommon", "Wimbledon Common parkrun"),
    EventRef(3, "banstead", "Banstead Woods parkrun"),
    EventRef(4, "richmond", "Richmond parkrun"),
]


def _athlete(slugs: list[str]) -> Athlete:
    runs = [
        Run(event_name=s, event_slug=s, run_date=date(2025, 1, 1 + i), run_number=1, time_seconds=1500)
        for i, s in enumerate(slugs)
    ]
    return Athlete(id=3244769, runs=runs)


def _event(eid: int, slug: str) -> Event:
    return Event(id=eid, slug=slug, name=slug, short_name=slug, country_code=97, lat=0, lon=0)


def test_consecutive_prefix_index():
    ch = WilsonIndexChallenge(INDEX)
    # Done #1 and #2 -> index 2, blocker is #3.
    p = ch.progress(_athlete(["bushy", "wimbledoncommon"]))
    assert p.summary.startswith("Index 2")
    assert p.remaining[0] == "#3 Banstead Woods parkrun"
    assert not p.is_complete


def test_gap_caps_index():
    ch = WilsonIndexChallenge(INDEX)
    # Done #1, #3, #4 but NOT #2 -> index 1, blocker #2 (gap caps it).
    p = ch.progress(_athlete(["bushy", "banstead", "richmond"]))
    assert p.summary.startswith("Index 1")
    assert p.remaining[0] == "#2 Wimbledon Common parkrun"


def test_zero_when_first_not_done():
    ch = WilsonIndexChallenge(INDEX)
    p = ch.progress(_athlete(["richmond"]))  # high-id only
    assert p.summary.startswith("Index 0")
    assert p.remaining[0] == "#1 Bushy parkrun"


def test_contribution_only_blocker_scores():
    ch = WilsonIndexChallenge(INDEX)
    athlete = _athlete(["bushy", "wimbledoncommon"])  # blocker = #3
    assert ch.contribution(_event(3, "banstead"), athlete) == 1.0
    assert ch.contribution(_event(4, "richmond"), athlete) == 0.0  # doesn't move index yet
    assert ch.contribution(_event(1, "bushy"), athlete) == 0.0  # already done


def test_complete_when_all_done():
    ch = WilsonIndexChallenge(INDEX)
    p = ch.progress(_athlete(["bushy", "wimbledoncommon", "banstead", "richmond"]))
    assert p.is_complete
    assert p.percent == 100.0


# --- Floating Wilson Index ---

FLOAT_INDEX = [
    EventRef(10, "a", "A parkrun"),
    EventRef(11, "b", "B parkrun"),
    EventRef(12, "c", "C parkrun"),
    EventRef(13, "d", "D parkrun"),
    EventRef(14, "e", "E parkrun"),
]


def test_floating_longest_run_not_anchored_at_one():
    ch = FloatingWilsonIndexChallenge(FLOAT_INDEX)
    # Done #11, #12, #13 -> a run of 3 (doesn't need #1 / #10).
    p = ch.progress(_athlete(["b", "c", "d"]))
    assert p.summary.startswith("Index 3")


def test_floating_contribution_extends_or_bridges():
    ch = FloatingWilsonIndexChallenge(FLOAT_INDEX)
    athlete = _athlete(["b", "c", "d"])  # run #11-#13, current max 3
    # Extending the ends grows the run.
    assert ch.contribution(_event(10, "a"), athlete) == 1.0  # extend down
    assert ch.contribution(_event(14, "e"), athlete) == 1.0  # extend up


def test_floating_bridge_scores_more_than_extension():
    # Two runs #10-#12 and #14-#16, missing #13: filling #13 bridges to length 7.
    idx = [EventRef(i, f"e{i}", f"E{i}") for i in range(10, 17)]
    ch = FloatingWilsonIndexChallenge(idx)
    athlete = _athlete(["e10", "e11", "e12", "e14", "e15", "e16"])  # max run 3
    bridge = ch.slots(_event(13, "e13"), athlete)       # gain 4 (3->7), capped at 3
    extend = ch.slots(_event(9, "e9"), athlete)         # gain 1 (extends e10..12)
    assert len(bridge) > len(extend)  # bigger jump -> more slots -> higher score


def test_floating_zero_when_no_runs():
    ch = FloatingWilsonIndexChallenge(FLOAT_INDEX)
    assert ch.progress(_athlete([])).summary.startswith("Index 0")
