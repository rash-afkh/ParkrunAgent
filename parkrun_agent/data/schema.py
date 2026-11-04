"""SQLAlchemy 2.0 ORM models — the tables described in DESIGN.md §3.5.

The database doubles as the cache: every table that holds fetched data carries a
`fetched_at` timestamp, and repositories do read-through with a TTL (see
cache.py). Written to run on SQLite in dev and Postgres in prod with only a
connection-string change.

Milestone 1 actively uses: events, catalogue_meta, athletes, runs. The
remaining tables (geocode_cache, users, custom_challenges, recommendations_log)
are defined here so later milestones can fill them without a migration churn.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class EventRow(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(128), index=True)
    name: Mapped[str] = mapped_column(String(256))
    short_name: Mapped[str] = mapped_column(String(256))
    country_code: Mapped[int] = mapped_column(Integer, index=True)
    country_url: Mapped[str | None] = mapped_column(String(128), nullable=True)
    series_id: Mapped[int] = mapped_column(Integer, default=1)
    location: Mapped[str | None] = mapped_column(String(256), nullable=True)
    lat: Mapped[float] = mapped_column(Float, index=True)
    lon: Mapped[float] = mapped_column(Float, index=True)
    status: Mapped[str] = mapped_column(String(32), default="active")
    founding_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CatalogueMetaRow(Base):
    """Single-row bookkeeping for the events.json refresh."""

    __tablename__ = "catalogue_meta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    last_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_etag: Mapped[str | None] = mapped_column(String(256), nullable=True)


class AthleteRow(Base):
    __tablename__ = "athletes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    home_event: Mapped[str | None] = mapped_column(String(256), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    raw_html: Mapped[str | None] = mapped_column(Text, nullable=True)

    runs: Mapped[list[RunRow]] = relationship(
        back_populates="athlete", cascade="all, delete-orphan"
    )


class RunRow(Base):
    __tablename__ = "runs"
    __table_args__ = (
        UniqueConstraint("athlete_id", "event_name", "run_date", name="uq_run"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"), index=True)
    event_name: Mapped[str] = mapped_column(String(256))
    event_slug: Mapped[str | None] = mapped_column(String(128), nullable=True)
    run_date: Mapped[date] = mapped_column(Date)
    run_number: Mapped[int] = mapped_column(Integer)
    time_seconds: Mapped[int] = mapped_column(Integer)
    position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    age_grade: Mapped[float | None] = mapped_column(Float, nullable=True)

    athlete: Mapped[AthleteRow] = relationship(back_populates="runs")


# --- Tables reserved for later milestones (defined now to avoid churn) ---


class GeocodeCacheRow(Base):
    __tablename__ = "geocode_cache"

    query: Mapped[str] = mapped_column(String(256), primary_key=True)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    display_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class UserRow(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"))
    email: Mapped[str | None] = mapped_column(String(256), nullable=True)
    prefs: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class CustomChallengeRow(Base):
    __tablename__ = "custom_challenges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    key: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(256))
    type: Mapped[str] = mapped_column(String(64))
    config: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class RecommendationLogRow(Base):
    __tablename__ = "recommendations_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"), index=True)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("events.id"), nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    reasons: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    context: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    sent_in_digest: Mapped[bool] = mapped_column(Boolean, default=False)
    outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
