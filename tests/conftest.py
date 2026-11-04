from __future__ import annotations

from pathlib import Path

import pytest

from parkrun_agent.data import cache

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def db(tmp_path):
    """A fresh, isolated SQLite database for one test."""
    url = f"sqlite:///{tmp_path / 'test.db'}"
    cache.init_db(url)
    yield url
    cache._engine = None
    cache._Session = None


@pytest.fixture
def athlete_html() -> str:
    return (FIXTURES / "athlete_sample.html").read_text(encoding="utf-8")
