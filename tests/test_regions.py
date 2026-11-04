from datetime import date

from parkrun_agent.core.challenges.regions import (
    RegionCompletionChallenge,
    au_state,
    build_region_challenges,
)
from parkrun_agent.core.models import Athlete, Event, Run


def _event(slug, lat, lon, cc=3):
    return Event(id=1, slug=slug, name=slug, short_name=slug, country_code=cc, lat=lat, lon=lon)


def _athlete(slugs):
    runs = [
        Run(event_name=s, event_slug=s, run_date=date(2025, 1, 1 + i), run_number=1, time_seconds=1500)
        for i, s in enumerate(slugs)
    ]
    return Athlete(id=3244769, runs=runs)


def test_au_state_key_borders():
    assert au_state(-32.0, 115.8) == "WA"      # Perth
    assert au_state(-33.87, 151.2) == "NSW"    # Sydney
    assert au_state(-37.81, 144.96) == "VIC"   # Melbourne
    assert au_state(-27.47, 153.0) == "QLD"    # Brisbane
    assert au_state(-34.93, 138.6) == "SA"     # Adelaide
    assert au_state(-42.88, 147.33) == "TAS"   # Hobart
    assert au_state(-35.28, 149.13) == "ACT"   # Canberra
    assert au_state(-12.46, 130.84) == "NT"    # Darwin


def test_region_completion_progress_and_contribution():
    ch = RegionCompletionChallenge("au_wa", "WA (Australia)", {"perth", "shelley", "applecross"})
    athlete = _athlete(["perth", "shelley"])  # 2 of 3 done
    p = ch.progress(athlete)
    assert not p.is_complete
    assert p.remaining == ["applecross"]
    assert "2/3" in p.summary
    # An unvisited WA event advances it; a visited or out-of-region one does not.
    assert ch.contribution(_event("applecross", -32.0, 115.84), athlete) == 1.0
    assert ch.contribution(_event("perth", -31.95, 115.86), athlete) == 0.0
    assert ch.contribution(_event("bushy", 51.4, -0.33, cc=97), athlete) == 0.0


def test_build_region_challenges_splits_australia():
    events = [
        _event("perth", -32.0, 115.8),      # WA
        _event("sydney", -33.87, 151.2),    # NSW
        _event("bushy", 51.4, -0.33, cc=97),  # not AU -> excluded
    ]
    challenges = build_region_challenges(events)
    assert challenges["australia"].targets == {"perth", "sydney"}
    assert challenges["au_wa"].targets == {"perth"}
    assert challenges["au_nsw"].targets == {"sydney"}
