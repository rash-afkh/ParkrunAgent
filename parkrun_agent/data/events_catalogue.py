"""Events catalogue repository: fetch events.json, cache it, query by location.

Read-through with a 7-day TTL. `refresh()` is the only thing that fetches; all
reads come from the DB.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import select

from parkrun_agent.core.geo import GeoPoint, bounding_box, haversine_km
from parkrun_agent.core.models import Event
from parkrun_agent.data import fetchers
from parkrun_agent.data.cache import EVENTS_TTL, get_session, is_fresh
from parkrun_agent.data.schema import CatalogueMetaRow, EventRow

EventsFetcher = Callable[[str | None], tuple[dict | None, str | None, bool]]


def parse_events_json(data: dict) -> list[Event]:
    """Convert the raw events.json structure into Event models (pure)."""
    countries: dict[str, dict] = data.get("countries", {})
    features = data.get("events", {}).get("features", [])
    events: list[Event] = []
    for feat in features:
        props = feat.get("properties", {})
        lon, lat = feat["geometry"]["coordinates"]
        code = props.get("countrycode")
        country = countries.get(str(code), {}) if code is not None else {}
        events.append(
            Event(
                id=feat["id"],
                slug=props["eventname"],
                name=props.get("EventLongName") or props["eventname"],
                short_name=props.get("EventShortName") or props.get("EventLongName") or "",
                country_code=code if code is not None else 0,
                country_url=country.get("url"),
                series_id=props.get("seriesid", 1),
                location=props.get("EventLocation"),
                lat=float(lat),
                lon=float(lon),
            )
        )
    return events


def _row_to_event(row: EventRow) -> Event:
    return Event(
        id=row.id,
        slug=row.slug,
        name=row.name,
        short_name=row.short_name,
        country_code=row.country_code,
        country_url=row.country_url,
        series_id=row.series_id,
        location=row.location,
        lat=row.lat,
        lon=row.lon,
        status=row.status,
        founding_rank=row.founding_rank,
    )


class EventsCatalogue:
    def __init__(self, fetcher: EventsFetcher | None = None):
        self._fetch = fetcher or fetchers.fetch_events_json

    def refresh(self, *, force: bool = False, now: datetime | None = None) -> int:
        """Refresh the catalogue if stale. Returns the number of events stored."""
        now = now or datetime.now(timezone.utc)
        with get_session() as s:
            meta = s.get(CatalogueMetaRow, 1) or CatalogueMetaRow(id=1)
            if not force and is_fresh(meta.last_refreshed_at, EVENTS_TTL, now):
                return s.query(EventRow).count()

            data, etag, not_modified = self._fetch(meta.source_etag)
            if not_modified:
                meta.last_refreshed_at = now
                s.merge(meta)
                s.commit()
                return s.query(EventRow).count()

            assert data is not None
            events = parse_events_json(data)
            for ev in events:
                s.merge(
                    EventRow(
                        id=ev.id,
                        slug=ev.slug,
                        name=ev.name,
                        short_name=ev.short_name,
                        country_code=ev.country_code,
                        country_url=ev.country_url,
                        series_id=ev.series_id,
                        location=ev.location,
                        lat=ev.lat,
                        lon=ev.lon,
                        status=ev.status,
                        fetched_at=now,
                    )
                )
            meta.last_refreshed_at = now
            meta.source_etag = etag
            s.merge(meta)
            s.commit()
            return len(events)

    def all_events(self) -> list[Event]:
        with get_session() as s:
            return [_row_to_event(r) for r in s.scalars(select(EventRow)).all()]

    def get(self, slug: str) -> Event | None:
        with get_session() as s:
            row = s.scalar(select(EventRow).where(EventRow.slug == slug))
            return _row_to_event(row) if row else None

    def near(self, point: GeoPoint, radius_km: float) -> list[tuple[Event, float]]:
        """Events within radius_km, as (event, distance_km), nearest first."""
        min_lat, max_lat, min_lon, max_lon = bounding_box(point, radius_km)
        with get_session() as s:
            rows = s.scalars(
                select(EventRow).where(
                    EventRow.status == "active",
                    EventRow.lat >= min_lat,
                    EventRow.lat <= max_lat,
                    EventRow.lon >= min_lon,
                    EventRow.lon <= max_lon,
                )
            ).all()
        out: list[tuple[Event, float]] = []
        for row in rows:
            ev = _row_to_event(row)
            dist = haversine_km(point, ev.point)
            if dist <= radius_km:
                out.append((ev, dist))
        out.sort(key=lambda t: t[1])
        return out
