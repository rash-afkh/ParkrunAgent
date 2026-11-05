"""Geocoder: free-text place -> coordinates, with a permanent cache.

Turns "Vilnius" into a GeoPoint so the agent can answer travel questions.
Read-through against the geocode_cache table; place coordinates don't move, so
a cached hit is served forever.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from parkrun_agent.core.geo import GeoPoint
from parkrun_agent.data import fetchers
from parkrun_agent.data.cache import get_session
from parkrun_agent.data.schema import GeocodeCacheRow

GeocodeFetcher = Callable[[str], dict | None]


class Geocoder:
    def __init__(self, fetcher: GeocodeFetcher | None = None):
        self._fetch = fetcher or fetchers.fetch_geocode

    def geocode(self, place: str) -> tuple[GeoPoint, str] | None:
        """Return (coordinates, display_name) or None if the place is unknown."""
        key = place.strip().lower()
        if not key:
            return None
        with get_session() as s:
            row = s.get(GeocodeCacheRow, key)
            if row is not None:
                return GeoPoint(row.lat, row.lon), row.display_name or place

        result = self._fetch(place)
        if result is None:
            return None
        with get_session() as s:
            s.merge(
                GeocodeCacheRow(
                    query=key,
                    lat=result["lat"],
                    lon=result["lon"],
                    display_name=result.get("display_name"),
                    source="nominatim",
                    fetched_at=datetime.now(UTC),
                )
            )
            s.commit()
        return GeoPoint(result["lat"], result["lon"]), result.get("display_name") or place
