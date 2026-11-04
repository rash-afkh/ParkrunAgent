# ParkrunAgent

An agent that reads your public parkrun profile, tracks your progress against a
set of challenges, and recommends where to run next.

See [DESIGN.md](DESIGN.md) for the full architecture. This repository currently
implements **Milestone 1 — core data + models + cache** (no LangChain yet):

- Fetch and cache the global parkrun events catalogue (`events.json`).
- Scrape and parse a single athlete's run history into typed models.
- Store everything in a local DB that doubles as the cache (read-through + TTL).
- Geo utilities (haversine + bounding box) and an "events near a point" query.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Usage

```bash
# Create the local SQLite database (the cache)
parkrun-agent init-db

# Refresh the events catalogue (cached for 7 days)
parkrun-agent events refresh

# List events within 50 km of a point (e.g. Vilnius)
parkrun-agent events near --lat 54.6872 --lon 25.2797 --radius 50

# Fetch + parse + cache your athlete profile, then print a summary
parkrun-agent athlete show --id <YOUR_ATHLETE_NUMBER>

# Configure home + challenges, then see where you stand
cp config/preferences.example.yaml config/preferences.yaml   # then edit
parkrun-agent config show            # resolved home + enabled challenges
parkrun-agent challenges show        # your progress per challenge
```

## Configuration

`config/preferences.yaml` (gitignored; copy from `preferences.example.yaml`)
holds your athlete number, home location (either a parkrun **event name/slug**
or explicit **lat/lon**), search radii, and which challenges are enabled —
including custom ones defined entirely in YAML. See the example file.

## Challenges

Milestone 2 ships `alphabeteer`, `pirates`, and `compass`, built on a
`TokenCollectionChallenge` base so new ones are just config. See
[DESIGN.md](DESIGN.md) §5.

The database location defaults to `./local_data/parkrun_agent.db` and can be
overridden with the `PARKRUN_DB_URL` environment variable (any SQLAlchemy URL,
e.g. a Postgres DSN).

## Running tests

```bash
pytest
```

Tests use offline fixtures — they never hit the network.

## A note on data sources

parkrun has no public API and its terms discourage automated scraping; result
pages sit behind bot protection. This tool is for **personal use**: it caches
aggressively (events weekly, athlete history until the next Saturday) and makes
at most one polite request at a time. See [DESIGN.md](DESIGN.md) §3.
