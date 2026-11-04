"""AgentContext — everything the tools need, assembled once from config.

This is the seam for the future API: a web request would build one of these per
athlete and hand it to the same tools the CLI agent uses.
"""

from __future__ import annotations

from dataclasses import dataclass

from parkrun_agent.config import AppConfig, build_challenges, load_config, resolve_home
from parkrun_agent.core.challenges.base import Challenge
from parkrun_agent.core.geo import GeoPoint
from parkrun_agent.core.models import Athlete
from parkrun_agent.core.recommend import ScoringParams
from parkrun_agent.data.athlete_repo import AthleteRepository
from parkrun_agent.data.events_catalogue import EventsCatalogue
from parkrun_agent.data.geocoder import Geocoder
from parkrun_agent.recommend_service import RecommendationService


@dataclass
class AgentContext:
    config: AppConfig
    athlete: Athlete
    challenges: list[Challenge]
    catalogue: EventsCatalogue
    geocoder: Geocoder
    service: RecommendationService
    params: ScoringParams
    home: GeoPoint
    home_label: str


def build_context(config_path: str) -> AgentContext:
    config = load_config(config_path)
    if config.athlete_id is None:
        raise ValueError("preferences.yaml must set athlete_id for the agent.")

    catalogue = EventsCatalogue()
    if not catalogue.all_events():
        raise ValueError("Events catalogue is empty — run 'parkrun-agent events refresh' first.")

    athlete = AthleteRepository().get(config.athlete_id)
    challenges = build_challenges(config, catalogue)
    home, home_label = resolve_home(config.home, catalogue)
    params = ScoringParams(
        local_radius_km=config.preferences.local_radius_km,
        stretch_radius_km=config.preferences.stretch_radius_km,
        challenge_weights=config.preferences.challenge_weights,
    )
    return AgentContext(
        config=config,
        athlete=athlete,
        challenges=challenges,
        catalogue=catalogue,
        geocoder=Geocoder(),
        service=RecommendationService(catalogue),
        params=params,
        home=home,
        home_label=home_label,
    )
