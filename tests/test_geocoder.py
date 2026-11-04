from parkrun_agent.data.geocoder import Geocoder


def test_geocode_and_cache(db):
    calls = {"n": 0}

    def fetch(query):
        calls["n"] += 1
        return {"lat": 54.6872, "lon": 25.2797, "display_name": "Vilnius, Lithuania"}

    geo = Geocoder(fetcher=fetch)
    point, label = geo.geocode("Vilnius")
    assert abs(point.lat - 54.6872) < 1e-6
    assert label == "Vilnius, Lithuania"
    assert calls["n"] == 1

    # Second lookup is served from the cache — no second fetch.
    geo.geocode("vilnius")  # different case -> same normalised key
    assert calls["n"] == 1


def test_geocode_unknown_place(db):
    geo = Geocoder(fetcher=lambda q: None)
    assert geo.geocode("Nowhereville") is None
    assert geo.geocode("   ") is None
