from datetime import UTC, datetime, timedelta

from parkrun_agent.data.cache import (
    EVENTS_TTL,
    is_athlete_fresh,
    is_fresh,
    most_recent_results_cutoff,
)


def test_is_fresh_within_ttl():
    now = datetime(2025, 11, 4, 12, 0, tzinfo=UTC)
    assert is_fresh(now - timedelta(days=3), EVENTS_TTL, now)
    assert not is_fresh(now - timedelta(days=8), EVENTS_TTL, now)
    assert not is_fresh(None, EVENTS_TTL, now)


def test_most_recent_results_cutoff_is_a_saturday():
    # Tuesday 2025-11-04 -> previous Saturday is 2025-11-01.
    now = datetime(2025, 11, 4, 9, 0, tzinfo=UTC)
    cutoff = most_recent_results_cutoff(now)
    assert cutoff.weekday() == 5  # Saturday
    assert cutoff.date() == datetime(2025, 11, 1, tzinfo=UTC).date()


def test_athlete_freshness_flips_after_saturday():
    now = datetime(2025, 11, 4, 9, 0, tzinfo=UTC)  # Tuesday
    # Fetched last Sunday -> still fresh (no Saturday since).
    assert is_athlete_fresh(datetime(2025, 11, 2, 10, 0, tzinfo=UTC), now)
    # Fetched the Friday before last Saturday -> stale.
    assert not is_athlete_fresh(datetime(2025, 10, 31, 10, 0, tzinfo=UTC), now)
