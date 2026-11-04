"""Pydantic domain models.

These are the single source of truth for the shape of the data. They double as
(a) the objects the recommendation engine works on and (b) API response schemas
once FastAPI is added. Deliberately free of any DB / LangChain concerns.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, computed_field

from parkrun_agent.core.geo import GeoPoint


class Event(BaseModel):
    """A parkrun venue, sourced from the public events.json catalogue."""

    id: int
    slug: str = Field(description="URL slug, e.g. 'bushy'")
    name: str = Field(description="Long name, e.g. 'Bushy parkrun'")
    short_name: str
    country_code: int
    country_url: str | None = Field(default=None, description="e.g. 'www.parkrun.org.uk'")
    series_id: int = Field(default=1, description="1 = 5k parkrun, 2 = junior 2k")
    location: str | None = None
    lat: float
    lon: float
    status: str = "active"
    founding_rank: int | None = Field(default=None, description="For the Wilson Index challenge")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def point(self) -> GeoPoint:
        return GeoPoint(lat=self.lat, lon=self.lon)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def url(self) -> str | None:
        if not self.country_url:
            return None
        return f"https://{self.country_url}/{self.slug}"


class Run(BaseModel):
    """A single result from an athlete's history."""

    event_name: str
    event_slug: str | None = Field(default=None, description="Resolved from the result link")
    run_date: date
    run_number: int = Field(description="The event's nth staging when the athlete ran it")
    time_seconds: int
    position: int | None = None
    age_grade: float | None = Field(default=None, description="Percentage, 0-100")


class Athlete(BaseModel):
    """An athlete and their full run history."""

    id: int
    name: str | None = None
    home_event: str | None = None
    runs: list[Run] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_runs(self) -> int:
        return len(self.runs)

    @property
    def distinct_event_names(self) -> set[str]:
        return {r.event_name for r in self.runs}
