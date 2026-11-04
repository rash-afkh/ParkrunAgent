import json

import pytest

from parkrun_agent.config import (
    HomeConfig,
    HomeResolutionError,
    build_challenges,
    load_config,
    resolve_home,
)
from parkrun_agent.data.events_catalogue import EventsCatalogue
from tests.conftest import FIXTURES

CONFIG_YAML = """
athlete_id: 3244769
home:
  event: "Vingis"
preferences:
  local_radius_km: 40
challenges:
  enabled: [alphabeteer, pirates]
  custom:
    - key: vowels
      name: Vowel Hunter
      type: token_collection
      token: first_letter
      targets: [A, E, I, O, U]
"""


def _write_config(tmp_path):
    path = tmp_path / "prefs.yaml"
    path.write_text(CONFIG_YAML)
    return path


def test_load_config(tmp_path):
    config = load_config(_write_config(tmp_path))
    assert config.athlete_id == 3244769
    assert config.home.event == "Vingis"
    assert config.preferences.local_radius_km == 40
    assert config.enabled_challenges == ["alphabeteer", "pirates"]
    assert config.custom_challenges[0]["key"] == "vowels"


def test_build_challenges_enabled_plus_custom(tmp_path):
    config = load_config(_write_config(tmp_path))
    challenges = build_challenges(config)
    keys = [c.key for c in challenges]
    assert keys == ["alphabeteer", "pirates", "vowels"]


def test_resolve_home_latlon():
    point, label = resolve_home(HomeConfig(lat=54.68, lon=25.28))
    assert point.lat == 54.68 and point.lon == 25.28


def test_resolve_home_by_event_name(db):
    data = json.loads((FIXTURES / "events_sample.json").read_text())
    catalogue = EventsCatalogue(fetcher=lambda _etag: (data, "e", False))
    catalogue.refresh(force=True)

    point, label = resolve_home(HomeConfig(event="Vingis"), catalogue)
    assert label == "parkrun Vingis"
    assert abs(point.lat - 54.682498) < 1e-6


def test_resolve_home_errors(db):
    with pytest.raises(HomeResolutionError):
        resolve_home(HomeConfig())  # nothing set
    catalogue = EventsCatalogue(fetcher=lambda _etag: ({"countries": {}, "events": {"features": []}}, "e", False))
    catalogue.refresh(force=True)
    with pytest.raises(HomeResolutionError):
        resolve_home(HomeConfig(event="Nonexistent"), catalogue)
