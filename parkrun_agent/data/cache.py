"""Engine/session management and TTL ("freshness") helpers.

The DB is the cache. These helpers encode *when* a cached row is considered
stale, which is all the "caching policy" this app needs:

- events catalogue: fresh for 7 days.
- athlete history: fresh until the next Saturday's results are published —
  results only change after Saturday, so there is no point re-scraping mid-week.
- geocode: effectively permanent (handled in a later milestone).
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from parkrun_agent.data.schema import Base, CatalogueMetaRow

EVENTS_TTL = timedelta(days=7)
# The hour (UTC) after which a given Saturday's results are assumed published.
SATURDAY_RESULTS_HOUR_UTC = 12

_engine: Engine | None = None
_Session: sessionmaker[Session] | None = None


def default_db_url() -> str:
    """Local SQLite file under ./local_data unless PARKRUN_DB_URL overrides it."""
    url = os.environ.get("PARKRUN_DB_URL")
    if url:
        return url
    data_dir = Path(os.environ.get("PARKRUN_DATA_DIR", "local_data"))
    data_dir.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{(data_dir / 'parkrun_agent.db').resolve()}"


def get_engine(url: str | None = None) -> Engine:
    global _engine, _Session
    if _engine is None or url is not None:
        _engine = create_engine(url or default_db_url(), future=True)
        _Session = sessionmaker(bind=_engine, future=True, expire_on_commit=False)
    return _engine


def get_session() -> Session:
    if _Session is None:
        get_engine()
    assert _Session is not None
    return _Session()


# Columns added after the initial release; applied to existing SQLite DBs so the
# cache doesn't need rebuilding. create_all() handles brand-new tables already.
_ADDITIVE_COLUMNS = {
    "athletes": {"volunteer_count": "INTEGER", "volunteer_roles": "JSON"},
}


def _apply_additive_migrations(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return  # Postgres uses Alembic (future); SQLite gets lightweight ALTERs.
    insp = inspect(engine)
    with engine.begin() as conn:
        for table, columns in _ADDITIVE_COLUMNS.items():
            existing = {c["name"] for c in insp.get_columns(table)}
            for col, ddl in columns.items():
                if col not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"))


def init_db(url: str | None = None) -> Engine:
    """Create all tables and seed the single catalogue_meta row."""
    engine = get_engine(url)
    Base.metadata.create_all(engine)
    _apply_additive_migrations(engine)
    with get_session() as s:
        if s.scalar(select(CatalogueMetaRow).where(CatalogueMetaRow.id == 1)) is None:
            s.add(CatalogueMetaRow(id=1))
            s.commit()
    return engine


def _now(now: datetime | None = None) -> datetime:
    return now or datetime.now(timezone.utc)


def _as_aware(dt: datetime) -> datetime:
    """SQLite drops tzinfo on round-trip; treat naive timestamps as UTC."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def is_fresh(fetched_at: datetime | None, ttl: timedelta, now: datetime | None = None) -> bool:
    if fetched_at is None:
        return False
    return _now(now) - _as_aware(fetched_at) < ttl


def most_recent_results_cutoff(now: datetime | None = None) -> datetime:
    """The most recent Saturday at SATURDAY_RESULTS_HOUR_UTC, at or before `now`.

    Athlete data fetched after this instant already reflects the latest results.
    """
    n = _now(now)
    # Monday=0 ... Saturday=5, Sunday=6
    days_since_saturday = (n.weekday() - 5) % 7
    candidate = (n - timedelta(days=days_since_saturday)).replace(
        hour=SATURDAY_RESULTS_HOUR_UTC, minute=0, second=0, microsecond=0
    )
    if candidate > n:
        candidate -= timedelta(days=7)
    return candidate


def is_athlete_fresh(fetched_at: datetime | None, now: datetime | None = None) -> bool:
    """Fresh iff fetched after the most recent Saturday results publication."""
    if fetched_at is None:
        return False
    return _as_aware(fetched_at) >= most_recent_results_cutoff(now)
