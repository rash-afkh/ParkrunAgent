import pytest

from parkrun_agent.data.athlete_repo import AthleteRepository


def test_get_fetches_stores_and_serves_from_cache(db, athlete_html):
    calls = {"n": 0}

    def fetch(_id):
        calls["n"] += 1
        return athlete_html

    repo = AthleteRepository(fetcher=fetch)
    a1 = repo.get(1234567, force=True)
    assert a1.total_runs == 3
    assert calls["n"] == 1

    # Freshly fetched -> second non-forced get serves from DB, no new fetch.
    a2 = repo.get(1234567, force=False)
    assert a2.total_runs == 3
    assert calls["n"] == 1

    # Re-scrape replaces runs wholesale (no duplication).
    repo.get(1234567, force=True)
    assert repo.get(1234567).total_runs == 3


def test_fail_soft_serves_stale_cache_on_fetch_error(db, athlete_html):
    good = AthleteRepository(fetcher=lambda _id: athlete_html)
    good.get(1234567, force=True)

    def boom(_id):
        raise RuntimeError("network down")

    broken = AthleteRepository(fetcher=boom)
    athlete = broken.get(1234567, force=True)  # must fall back to cache
    assert athlete.total_runs == 3


def test_fail_soft_reraises_without_cache(db):
    def boom(_id):
        raise RuntimeError("network down")

    with pytest.raises(RuntimeError):
        AthleteRepository(fetcher=boom).get(999, force=True)
