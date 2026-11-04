from datetime import date

from parkrun_agent.core.challenges.base import compass_words, initial_letter
from parkrun_agent.core.challenges.builtins import alphabeteer, compass, pirates
from parkrun_agent.core.challenges.registry import build_challenge_from_config
from parkrun_agent.core.models import Athlete, Event, Run


def _athlete(event_names: list[str]) -> Athlete:
    runs = [
        Run(event_name=n, run_date=date(2025, 1, 1 + i), run_number=i + 1, time_seconds=1500)
        for i, n in enumerate(event_names)
    ]
    return Athlete(id=3244769, runs=runs)


def _event(name: str, short: str | None = None) -> Event:
    return Event(
        id=1, slug="x", name=name, short_name=short or name,
        country_code=97, lat=0, lon=0,
    )


def test_initial_letter_strips_parkrun_word():
    assert initial_letter("Bushy parkrun") == {"B"}
    assert initial_letter("parkrun Vingis") == {"V"}
    assert initial_letter("junior parkrun Foo") == {"F"}


def test_compass_words():
    assert compass_words("Southsea parkrun") == set()  # 'Southsea' is one word
    assert compass_words("North Beach parkrun") == {"NORTH"}
    assert compass_words("East End") == {"EAST"}


def test_alphabeteer_progress_and_contribution():
    challenge = alphabeteer()
    athlete = _athlete(["Ascot parkrun", "Bushy parkrun", "Shelley parkrun"])

    p = challenge.progress(athlete)
    assert set(p.completed) == {"A", "B", "S"}
    assert "X" not in p.remaining  # X is excluded from the Alphabeteer
    assert len(p.completed) + len(p.remaining) == 25
    assert not p.is_complete

    # An event starting with a new letter contributes; a repeat letter does not.
    assert challenge.contribution(_event("Carlisle parkrun", "Carlisle"), athlete) > 0
    assert challenge.contribution(_event("Another Ascot", "Ascot"), athlete) == 0


def test_pirates_targets():
    p = pirates().progress(_athlete(["Perry Lakes", "Ibsley"]))
    assert set(p.completed) == {"P", "I"}
    assert set(p.remaining) == {"R", "A", "T", "E", "S"}


def test_compass_complete():
    athlete = _athlete(["North Park", "South Bank", "East Hill", "West Beach"])
    p = compass().progress(athlete)
    assert p.is_complete
    assert p.percent == 100.0


def test_custom_challenge_from_config():
    cfg = {
        "key": "vowels",
        "name": "Vowel Hunter",
        "type": "token_collection",
        "token": "first_letter",
        "targets": ["A", "E", "I", "O", "U"],
    }
    challenge = build_challenge_from_config(cfg)
    p = challenge.progress(_athlete(["Ascot", "Epsom"]))
    assert set(p.completed) == {"A", "E"}
    assert set(p.remaining) == {"I", "O", "U"}
