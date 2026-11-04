"""App configuration loaded from preferences.yaml.

Bridges the pure core (challenges, geo) and the data layer (catalogue lookup for
home resolution). Home can be given as explicit lat/lon or as a parkrun event
name/slug, which is resolved to coordinates via the events catalogue.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from parkrun_agent.core.challenges.base import Challenge
from parkrun_agent.core.challenges.builtins import BUILTIN_BUILDERS
from parkrun_agent.core.challenges.registry import build_challenge_from_config
from parkrun_agent.core.geo import GeoPoint
from parkrun_agent.data.events_catalogue import EventsCatalogue

DEFAULT_CONFIG_PATH = "config/preferences.yaml"


class HomeConfig(BaseModel):
    event: str | None = None
    lat: float | None = None
    lon: float | None = None


class Preferences(BaseModel):
    local_radius_km: float = 50.0
    stretch_radius_km: float = 200.0
    challenge_weights: dict[str, float] = Field(default_factory=dict)


class AppConfig(BaseModel):
    athlete_id: int | None = None
    home: HomeConfig = Field(default_factory=HomeConfig)
    preferences: Preferences = Field(default_factory=Preferences)
    enabled_challenges: list[str] = Field(default_factory=list)
    custom_challenges: list[dict] = Field(default_factory=list)


class HomeResolutionError(Exception):
    pass


def load_config(path: str | Path = DEFAULT_CONFIG_PATH) -> AppConfig:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    challenges = data.get("challenges") or {}
    return AppConfig(
        athlete_id=data.get("athlete_id"),
        home=HomeConfig(**(data.get("home") or {})),
        preferences=Preferences(**(data.get("preferences") or {})),
        enabled_challenges=challenges.get("enabled", []),
        custom_challenges=challenges.get("custom", []),
    )


def resolve_home(home: HomeConfig, catalogue: EventsCatalogue | None = None) -> tuple[GeoPoint, str]:
    """Return (coordinates, human label). Prefers explicit lat/lon over event."""
    if home.lat is not None and home.lon is not None:
        return GeoPoint(home.lat, home.lon), f"{home.lat:.4f}, {home.lon:.4f}"
    if home.event:
        catalogue = catalogue or EventsCatalogue()
        ev = catalogue.find_by_name(home.event)
        if ev is None:
            raise HomeResolutionError(
                f"Home event {home.event!r} not found. Run 'parkrun-agent events refresh' first, "
                "or check the spelling."
            )
        return ev.point, ev.name
    raise HomeResolutionError(
        "No home configured: set home.lat/lon or home.event in preferences.yaml."
    )


def build_challenges(config: AppConfig) -> list[Challenge]:
    """Instantiate enabled built-ins (default: all) plus any custom challenges."""
    enabled = config.enabled_challenges or list(BUILTIN_BUILDERS)
    challenges: list[Challenge] = []
    for key in enabled:
        builder = BUILTIN_BUILDERS.get(key)
        if builder is None:
            raise ValueError(f"Unknown built-in challenge {key!r} (have {list(BUILTIN_BUILDERS)}).")
        challenges.append(builder())
    for cfg in config.custom_challenges:
        challenges.append(build_challenge_from_config(cfg))
    return challenges
