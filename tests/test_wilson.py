from datetime import date

from parkrun_agent.core.challenges.wilson import EventRef, WilsonIndexChallenge
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
