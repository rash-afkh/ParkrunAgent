import json
from datetime import date

from parkrun_agent.core.challenges.builtins import alphabeteer
from parkrun_agent.core.challenges.wilson import wilson_from_events
from parkrun_agent.core.geo import GeoPoint
from parkrun_agent.core.models import Athlete, Event, Run
from parkrun_agent.core.recommend import (
    ScoringParams,
    build_slot_counts,
    distance_penalty,
    score_event,
    tier_for,
)
from parkrun_agent.data.events_catalogue import EventsCatalogue
from parkrun_agent.recommend_service import RecommendationService
from tests.conftest import FIXTURES

PARAMS = ScoringParams(local_radius_km=50, stretch_radius_km=200)


def _event(slug, name, lat=0.0, lon=0.0, eid=1):
    return Event(id=eid, slug=slug, name=name, short_name=name, country_code=97, lat=lat, lon=lon)


def _athlete(event_names):
    runs = [
        Run(event_name=n, event_slug=n.lower(), run_date=date(2025, 1, 1 + i), run_number=1, time_seconds=1500)
        for i, n in enumerate(event_names)
    ]
    return Athlete(id=3244769, runs=runs)


def test_distance_penalty_and_tier():
    assert distance_penalty(10, PARAMS) == 0.0
    assert distance_penalty(250, PARAMS) == 1.0
    assert abs(distance_penalty(125, PARAMS) - 0.5) < 1e-9
    assert tier_for(10, PARAMS) == "local"
    assert tier_for(120, PARAMS) == "stretch"
    assert tier_for(500, PARAMS) == "destination"


def test_scarcity_rewards_rare_slot():
    challenge = alphabeteer()
    athlete = _athlete(["Bushy"])  # has B; A and Z still needed
    ascot = _event("ascot", "Ascot")
    avon = _event("avon", "Avon")      # also fills A -> A is not scarce
    zed = _event("zedtown", "Zedtown")  # only Z filler -> scarce

    candidates = [ascot, avon, zed]
    counts = build_slot_counts(candidates, athlete, [challenge])
    assert counts["alphabeteer:A"] == 2
    assert counts["alphabeteer:Z"] == 1

    s_ascot = score_event(ascot, 5, athlete, [challenge], PARAMS, athlete.visited_slugs, counts)
    s_zed = score_event(zed, 5, athlete, [challenge], PARAMS, athlete.visited_slugs, counts)
    assert s_zed.score > s_ascot.score  # the unique Z filler wins
    assert "fills Z (the only option in range)" in " ".join(s_zed.reasons)


def test_distance_reduces_score():
    challenge = alphabeteer()
    athlete = _athlete(["Bushy"])
    zed = _event("zedtown", "Zedtown")
    counts = build_slot_counts([zed], athlete, [challenge])
    near = score_event(zed, 5, athlete, [challenge], PARAMS, athlete.visited_slugs, counts)
    far = score_event(zed, 180, athlete, [challenge], PARAMS, athlete.visited_slugs, counts)
    assert near.score > far.score


def test_service_tiers_and_destination(db):
    data = json.loads((FIXTURES / "events_sample.json").read_text())
    catalogue = EventsCatalogue(fetcher=lambda _etag: (data, "e", False))
    catalogue.refresh(force=True)

    athlete = Athlete(id=3244769, runs=[])  # done nothing
    challenges = [alphabeteer(), wilson_from_events(catalogue.all_events())]
    vilnius = GeoPoint(54.6872, 25.2797)

    recs = RecommendationService(catalogue).recommend(athlete, challenges, vilnius, PARAMS)
    by_slug = {r.event.slug: r for r in recs}

    # Vingis is ~2 km away -> local, fills alphabeteer:V.
    assert "vingis" in by_slug
    assert by_slug["vingis"].tier == "local"
    assert "alphabeteer" in by_slug["vingis"].challenge_contributions

    # Bushy is ~1800 km away but is the Wilson blocker (#1) -> destination.
    assert "bushy" in by_slug
    assert by_slug["bushy"].tier == "destination"
    assert "wilson" in by_slug["bushy"].challenge_contributions


def _catalogue_with(db_url, features):
    data = {
        "countries": {"54": {"url": "www.parkrun.lt"}, "97": {"url": "www.parkrun.org.uk"}},
        "events": {"type": "FeatureCollection", "features": features},
    }
    cat = EventsCatalogue(fetcher=lambda _etag: (data, "e", False))
    cat.refresh(force=True)
    return cat


def _feature(eid, slug, name, lat, lon, series=1):
    return {
        "id": eid, "type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {"eventname": slug, "EventLongName": name, "EventShortName": name,
                       "countrycode": 54, "seriesid": series},
    }


def test_junior_events_excluded(db):
    cat = _catalogue_with(db, [
        _feature(1, "vingis", "parkrun Vingis", 54.68, 25.24, series=1),
        _feature(2, "vingisjuniors", "Vingis junior parkrun", 54.68, 25.25, series=2),
    ])
    athlete = Athlete(id=3244769, runs=[])
    recs = RecommendationService(cat).recommend(
        athlete, [alphabeteer()], GeoPoint(54.6872, 25.2797), PARAMS, travel=True
    )
    slugs = {r.event.slug for r in recs}
    assert "vingis" in slugs
    assert "vingisjuniors" not in slugs  # junior (series 2) filtered out


def test_travel_surfaces_new_event_without_challenge_value(db):
    cat = _catalogue_with(db, [_feature(1, "vingis", "parkrun Vingis", 54.68, 25.24)])
    # Athlete already has a 'V' event, so Vingis advances no challenge — but it's
    # unvisited, so travel mode should still surface it.
    athlete = _athlete(["Victoria"])
    recs = RecommendationService(cat).recommend(
        athlete, [alphabeteer()], GeoPoint(54.6872, 25.2797), PARAMS, travel=True
    )
    assert [r.event.slug for r in recs] == ["vingis"]
    assert recs[0].challenge_contributions == {}  # pure novelty pick
