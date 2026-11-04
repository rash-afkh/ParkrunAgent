"""The LangChain tools, exercised without any LLM (we invoke them directly)."""

import json

from parkrun_agent.agent.context import AgentContext
from parkrun_agent.agent.tools import build_tools
from parkrun_agent.config import AppConfig
from parkrun_agent.core.challenges.builtins import alphabeteer
from parkrun_agent.core.challenges.wilson import wilson_from_events
from parkrun_agent.core.geo import GeoPoint
from parkrun_agent.core.models import Athlete
from parkrun_agent.core.recommend import ScoringParams
from parkrun_agent.data.events_catalogue import EventsCatalogue
from parkrun_agent.data.geocoder import Geocoder
from parkrun_agent.recommend_service import RecommendationService
from tests.conftest import FIXTURES


def _context(db) -> AgentContext:
    data = json.loads((FIXTURES / "events_sample.json").read_text())
    catalogue = EventsCatalogue(fetcher=lambda _etag: (data, "e", False))
    catalogue.refresh(force=True)

    athlete = Athlete(id=3244769, name="Rashid AFKHAMI", runs=[])
    challenges = [alphabeteer(), wilson_from_events(catalogue.all_events())]
    geocoder = Geocoder(
        fetcher=lambda q: {"lat": 54.6872, "lon": 25.2797, "display_name": "Vilnius"}
    )
    return AgentContext(
        config=AppConfig(),
        athlete=athlete,
        challenges=challenges,
        catalogue=catalogue,
        geocoder=geocoder,
        service=RecommendationService(catalogue),
        params=ScoringParams(local_radius_km=50, stretch_radius_km=200),
        home=GeoPoint(54.6872, 25.2797),  # home near Vingis for this test
        home_label="parkrun Vingis",
    )


def _tool(tools, name):
    return next(t for t in tools if t.name == name)


def test_tools_built(db):
    names = {t.name for t in build_tools(_context(db))}
    assert names == {"profile_summary", "challenge_progress", "recommend_from_home", "recommend_near"}


def test_profile_summary_tool(db):
    out = _tool(build_tools(_context(db)), "profile_summary").invoke({})
    assert "Rashid AFKHAMI" in out
    assert "A3244769" in out


def test_challenge_progress_tool(db):
    out = _tool(build_tools(_context(db)), "challenge_progress").invoke({})
    assert "Alphabeteer" in out
    assert "Wilson" in out


def test_recommend_near_tool_geocodes_and_ranks(db):
    out = _tool(build_tools(_context(db)), "recommend_near").invoke({"place": "Vilnius"})
    assert "Vilnius" in out
    assert "Vingis" in out  # the nearby Lithuanian event


def test_recommend_from_home_tool(db):
    out = _tool(build_tools(_context(db)), "recommend_from_home").invoke({})
    # Home is at Vingis: it's visited-free here, so it should surface locally,
    # and Bushy (Wilson #1) should appear as a destination.
    assert "Vingis" in out
    assert "Bushy" in out
