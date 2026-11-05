from datetime import UTC, date, datetime

from parkrun_agent.core.models import Athlete, Run
from parkrun_agent.crowds import format_summary, refresh
from parkrun_agent.data.cache import get_session
from parkrun_agent.data.event_occurrences import EventOccurrencesRepo, parse_event_history
from parkrun_agent.data.events_catalogue import EventsCatalogue
from parkrun_agent.data.schema import AthleteRow

HISTORY_HTML = """
<table><tbody>
  <tr><td>3</td><td>2025-01-18 Someone (M) 18:00</td>
      <td>120 120 finishers</td><td>8 8 volunteers</td></tr>
  <tr><td>2</td><td>2025-01-11 Someone (M) 17:30</td>
      <td>95 95 finishers</td><td>7 7 volunteers</td></tr>
  <tr><td>1</td><td>2025-01-04 Someone (M) 19:00</td>
      <td>210 210 finishers</td><td>9 9 volunteers</td></tr>
</tbody></table>
"""

CATALOGUE = {
    "countries": {"3": {"url": "www.parkrun.com.au"}},
    "events": {"features": [{
        "id": 1, "type": "Feature", "geometry": {"type": "Point", "coordinates": [115.8, -32.0]},
        "properties": {"eventname": "myevent", "EventLongName": "My Event parkrun",
                       "EventShortName": "My Event", "countrycode": 3,
                       "EventLocation": "My Park, Perth", "seriesid": 1},
    }]},
}


def _catalogue(db):
    cat = EventsCatalogue(fetcher=lambda _etag: (CATALOGUE, "e", False))
    cat.refresh(force=True)
    return cat


def _athlete(db):
    # The athlete row must exist in the DB so set_crowd_summary can persist.
    runs = [
        Run(event_name="My Event", event_slug="myevent", run_date=date(2025, 1, 4),
            run_number=1, time_seconds=1500),   # 210 finishers
        Run(event_name="My Event", event_slug="myevent", run_date=date(2025, 1, 18),
            run_number=3, time_seconds=1500),   # 120 finishers
    ]
    with get_session() as s:
        s.add(AthleteRow(id=3244769, name="Me", fetched_at=datetime.now(UTC)))
        s.commit()
    return Athlete(id=3244769, name="Me", runs=runs)


def test_parse_event_history():
    assert parse_event_history(HISTORY_HTML) == [(3, 120, 8), (2, 95, 7), (1, 210, 9)]


def test_refresh_fetches_once_and_builds_summary(db):
    cat = _catalogue(db)
    fetches = {"n": 0}

    def fetch(_slug, _domain=None):
        fetches["n"] += 1
        return HISTORY_HTML

    repo = EventOccurrencesRepo(fetcher=fetch)
    athlete = _athlete(db)

    summary = refresh(athlete, repo, cat, delay=0)
    assert fetches["n"] == 1
    assert summary["covered"] == 2
    assert summary["most"]["finishers"] == 210
    assert summary["least"]["finishers"] == 120
    assert summary["least"]["location"] == "My Park, Perth"

    # Second refresh: event already cached -> no new fetch.
    refresh(athlete, repo, cat, delay=0)
    assert fetches["n"] == 1


def _http_error(code: int):
    import requests

    resp = requests.Response()
    resp.status_code = code
    return requests.exceptions.HTTPError(f"{code} error", response=resp)


def test_genuine_404_is_marked_and_not_retried(db):
    cat = _catalogue(db)
    fetches = {"n": 0}

    def boom(_slug, _domain=None):
        fetches["n"] += 1
        raise _http_error(404)

    repo = EventOccurrencesRepo(fetcher=boom)
    athlete = _athlete(db)

    assert refresh(athlete, repo, cat, delay=0) is None
    assert fetches["n"] == 1
    refresh(athlete, repo, cat, delay=0)  # 404 -> marked unavailable -> not retried
    assert fetches["n"] == 1


def test_transient_error_is_not_marked_and_retried(db):
    cat = _catalogue(db)
    fetches = {"n": 0}

    def boom(_slug, _domain=None):
        fetches["n"] += 1
        raise _http_error(405)  # rate-limited, not gone

    repo = EventOccurrencesRepo(fetcher=boom)
    athlete = _athlete(db)

    refresh(athlete, repo, cat, delay=0)
    assert fetches["n"] == 1
    refresh(athlete, repo, cat, delay=0)  # transient -> NOT marked -> retried
    assert fetches["n"] == 2


def test_retry_unavailable_clears_false_markers(db):
    cat = _catalogue(db)
    athlete = _athlete(db)

    def fail_404(_slug, _domain=None):
        raise _http_error(404)

    # A 404 marks myevent unavailable...
    refresh(athlete, EventOccurrencesRepo(fetcher=fail_404), cat, delay=0)
    # ...but now it's actually fetchable; --retry-unavailable clears the marker.
    good = EventOccurrencesRepo(fetcher=lambda s, d=None: HISTORY_HTML)
    summary = refresh(athlete, good, cat, delay=0, retry_unavailable=True)
    assert summary["covered"] == 2


def test_no_fetch_builds_from_cache_only(db):
    cat = _catalogue(db)
    repo = EventOccurrencesRepo(fetcher=lambda s, d=None: HISTORY_HTML)
    athlete = _athlete(db)
    repo.backfill_event("myevent", "www.parkrun.com.au")  # pre-cache

    called = {"n": 0}
    repo._fetch = lambda *a, **k: (called.__setitem__("n", called["n"] + 1) or HISTORY_HTML)
    summary = refresh(athlete, repo, cat, max_new=0, delay=0)  # no-fetch mode
    assert called["n"] == 0
    assert summary["covered"] == 2


def test_format_summary():
    summary = {
        "covered": 2, "total_runs": 5, "avg": 165,
        "most": {"finishers": 210, "event": "Busy", "location": "X", "date": "2025-01-04"},
        "least": {"finishers": 40, "event": "Quiet", "location": None, "date": "2025-02-01"},
    }
    out = format_summary(summary)
    assert "Most crowded: 210 finishers — Busy" in out
    assert "Least crowded: 40 finishers — Quiet" in out
    assert "2/5 runs" in out
    assert "No crowd data" in format_summary(None)
