"""Geo utilities: great-circle distance and a bounding-box prefilter.

Kept deliberately dependency-free so the recommendation engine and the DB layer
can both use it. For 3,000-odd events a bounding-box prefilter followed by an
exact haversine is plenty; PostGIS is only needed if this ever goes multi-user.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import asin, cos, degrees, radians, sin, sqrt

EARTH_RADIUS_KM = 6371.0088


@dataclass(frozen=True)
class GeoPoint:
    lat: float
    lon: float


def haversine_km(a: GeoPoint, b: GeoPoint) -> float:
    """Great-circle distance between two points in kilometres."""
    lat1, lon1, lat2, lon2 = map(radians, (a.lat, a.lon, b.lat, b.lon))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(h))


def bounding_box(center: GeoPoint, radius_km: float) -> tuple[float, float, float, float]:
    """A lat/lon box that is guaranteed to contain every point within radius_km.

    Returns (min_lat, max_lat, min_lon, max_lon). Used as a cheap SQL prefilter
    before computing exact haversine distances in Python. The longitude span is
    widened by latitude to stay valid away from the equator.
    """
    lat_delta = degrees(radius_km / EARTH_RADIUS_KM)
    # Guard against division by ~0 near the poles.
    cos_lat = max(cos(radians(center.lat)), 1e-6)
    lon_delta = degrees(radius_km / (EARTH_RADIUS_KM * cos_lat))
    return (
        center.lat - lat_delta,
        center.lat + lat_delta,
        center.lon - lon_delta,
        center.lon + lon_delta,
    )
