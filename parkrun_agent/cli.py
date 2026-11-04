"""Command-line entry point for Milestone 1.

    parkrun-agent init-db
    parkrun-agent events refresh [--force]
    parkrun-agent events near --lat 54.6872 --lon 25.2797 --radius 50
    parkrun-agent athlete show --id 123456 [--force]
"""

from __future__ import annotations

import argparse
import sys

from parkrun_agent.config import (
    DEFAULT_CONFIG_PATH,
    build_challenges,
    load_config,
    resolve_home,
)
from parkrun_agent.core.geo import GeoPoint
from parkrun_agent.data.athlete_repo import AthleteRepository
from parkrun_agent.data.cache import init_db
from parkrun_agent.data.events_catalogue import EventsCatalogue


def cmd_init_db(_args: argparse.Namespace) -> int:
    init_db()
    print("Database initialised.")
    return 0


def cmd_events_refresh(args: argparse.Namespace) -> int:
    init_db()
    count = EventsCatalogue().refresh(force=args.force)
    print(f"Events catalogue: {count} events cached.")
    return 0


def cmd_events_near(args: argparse.Namespace) -> int:
    init_db()
    catalogue = EventsCatalogue()
    if not catalogue.all_events():
        print("Catalogue empty — run 'parkrun-agent events refresh' first.", file=sys.stderr)
        return 1
    results = catalogue.near(GeoPoint(lat=args.lat, lon=args.lon), args.radius)
    print(f"{len(results)} events within {args.radius:g} km:")
    for ev, dist in results[: args.limit]:
        print(f"  {dist:6.1f} km  {ev.name}  ({ev.location or ev.country_url or ''})")
    return 0


def cmd_athlete_show(args: argparse.Namespace) -> int:
    init_db()
    athlete = AthleteRepository().get(args.id, force=args.force)
    print(f"Athlete:   {athlete.name or '(name not parsed)'}  (A{athlete.id})")
    print(f"Home:      {athlete.home_event or '(unknown)'}")
    print(f"Total runs:     {athlete.total_runs}")
    print(f"Distinct events: {len(athlete.distinct_event_names)}")

    letters = sorted({name[0].upper() for name in athlete.distinct_event_names if name})
    print(f"Initial letters covered ({len(letters)}): {' '.join(letters)}")

    recent = sorted(athlete.runs, key=lambda r: r.run_date, reverse=True)[:5]
    if recent:
        print("Most recent runs:")
        for r in recent:
            mins, secs = divmod(r.time_seconds, 60)
            print(f"  {r.run_date}  {r.event_name:<32}  {mins:>2}:{secs:02d}")
    return 0


def cmd_config_show(args: argparse.Namespace) -> int:
    init_db()
    config = load_config(args.config)
    print(f"Config:    {args.config}")
    print(f"Athlete:   {config.athlete_id}")
    try:
        point, label = resolve_home(config.home)
        print(f"Home:      {label}  ({point.lat:.4f}, {point.lon:.4f})")
    except Exception as exc:  # HomeResolutionError or empty catalogue
        print(f"Home:      UNRESOLVED — {exc}", file=sys.stderr)
    print(f"Radii:     local {config.preferences.local_radius_km:g} km, "
          f"stretch {config.preferences.stretch_radius_km:g} km")
    challenges = build_challenges(config)
    print(f"Challenges: {', '.join(c.key for c in challenges)}")
    return 0


def cmd_challenges_show(args: argparse.Namespace) -> int:
    init_db()
    config = load_config(args.config)
    athlete_id = args.id or config.athlete_id
    if athlete_id is None:
        print("No athlete id (pass --id or set athlete_id in config).", file=sys.stderr)
        return 1

    athlete = AthleteRepository().get(athlete_id)
    challenges = build_challenges(config)
    print(f"Challenge progress for {athlete.name or athlete_id} "
          f"({athlete.total_runs} runs, {len(athlete.distinct_event_names)} events):\n")
    for ch in challenges:
        p = ch.progress(athlete)
        if p.summary is not None:  # unbounded challenge (e.g. Wilson)
            print(f"  {p.name:<22} {p.summary}")
            continue
        done = len(p.completed)
        total = done + len(p.remaining)
        flag = "  ✓ COMPLETE" if p.is_complete else ""
        print(f"  {p.name:<22} {done}/{total}  ({p.percent:g}%){flag}")
        if p.remaining and not p.is_complete:
            shown = p.remaining[:15]
            more = "" if len(p.remaining) == len(shown) else f"  (+{len(p.remaining) - len(shown)} more)"
            print(f"      still needed: {' '.join(shown)}{more}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="parkrun-agent", description="Find your next parkrun.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="Create the local database.").set_defaults(func=cmd_init_db)

    events = sub.add_parser("events", help="Events catalogue commands.")
    events_sub = events.add_subparsers(dest="events_command", required=True)

    refresh = events_sub.add_parser("refresh", help="Fetch/refresh the events catalogue.")
    refresh.add_argument("--force", action="store_true", help="Ignore the 7-day cache TTL.")
    refresh.set_defaults(func=cmd_events_refresh)

    near = events_sub.add_parser("near", help="List events near a point.")
    near.add_argument("--lat", type=float, required=True)
    near.add_argument("--lon", type=float, required=True)
    near.add_argument("--radius", type=float, default=50.0, help="Radius in km (default 50).")
    near.add_argument("--limit", type=int, default=25)
    near.set_defaults(func=cmd_events_near)

    athlete = sub.add_parser("athlete", help="Athlete commands.")
    athlete_sub = athlete.add_subparsers(dest="athlete_command", required=True)

    show = athlete_sub.add_parser("show", help="Fetch + cache + summarise an athlete.")
    show.add_argument("--id", type=int, required=True, help="Your parkrun athlete number.")
    show.add_argument("--force", action="store_true", help="Ignore the cache and re-fetch.")
    show.set_defaults(func=cmd_athlete_show)

    config_cmd = sub.add_parser("config", help="Configuration commands.")
    config_sub = config_cmd.add_subparsers(dest="config_command", required=True)
    config_show = config_sub.add_parser("show", help="Show resolved config + home.")
    config_show.add_argument("--config", default=DEFAULT_CONFIG_PATH)
    config_show.set_defaults(func=cmd_config_show)

    challenges = sub.add_parser("challenges", help="Challenge commands.")
    challenges_sub = challenges.add_subparsers(dest="challenges_command", required=True)
    ch_show = challenges_sub.add_parser("show", help="Show an athlete's challenge progress.")
    ch_show.add_argument("--id", type=int, default=None, help="Athlete number (default: from config).")
    ch_show.add_argument("--config", default=DEFAULT_CONFIG_PATH)
    ch_show.set_defaults(func=cmd_challenges_show)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
