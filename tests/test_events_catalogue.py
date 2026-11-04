import json

from parkrun_agent.core.geo import GeoPoint
from parkrun_agent.data.events_catalogue import EventsCatalogue, parse_events_json
from tests.conftest import FIXTURES


def _sample_data() -> dict:
    return json.loads((FIXTURES / "events_sample.json").read_text())


def test_parse_events_json():
    events = parse_events_json(_sample_data())
    assert len(events) == 2
    bushy = next(e for e in events if e.slug == "bushy")
    assert bushy.name == "Bushy parkrun"
    assert bushy.country_url == "www.parkrun.org.uk"
    assert bushy.url == "https://www.parkrun.org.uk/bushy"
    assert bushy.lat == 51.410992


def _fetcher_factory(data, etag="etag-1"):
    calls = {"n": 0}

    def fetch(sent_etag):
        calls["n"] += 1
        if sent_etag == etag:
            return None, etag, True  # not modified
        return data, etag, False

    return fetch, calls


def test_refresh_caches_and_respects_etag(db):
    data = _sample_data()
    fetch, calls = _fetcher_factory(data)
    catalogue = EventsCatalogue(fetcher=fetch)

    assert catalogue.refresh(force=True) == 2
    assert calls["n"] == 1
    assert len(catalogue.all_events()) == 2

    # Forcing again sends the stored ETag -> 304 -> no re-parse, same count.
    assert catalogue.refresh(force=True) == 2
    assert calls["n"] == 2


def test_refresh_skips_fetch_when_fresh(db):
    data = _sample_data()
    fetch, calls = _fetcher_factory(data)
    catalogue = EventsCatalogue(fetcher=fetch)

    catalogue.refresh(force=True)
    # Within TTL and not forced -> must not fetch again.
    catalogue.refresh(force=False)
    assert calls["n"] == 1


def test_near_filters_and_sorts(db):
    fetch, _ = _fetcher_factory(_sample_data())
    catalogue = EventsCatalogue(fetcher=fetch)
    catalogue.refresh(force=True)

    vilnius = GeoPoint(54.6872, 25.2797)
    results = catalogue.near(vilnius, radius_km=50)
    assert [e.slug for e, _ in results] == ["vingis"]  # Bushy is ~1800 km away
    _, dist = results[0]
    assert dist < 10
