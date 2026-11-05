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

# Rich athlete summary (countries, years active, PBs, farthest-apart, volunteering, clubs)
parkrun-agent athlete describe

# Most / least crowded parkruns you've run (one fetch per event, cached forever)
parkrun-agent athlete crowds                 # full backfill (~1 req/event, ~2 min first time)
parkrun-agent athlete crowds --max-events 15 # fetch a sample first
parkrun-agent athlete crowds --no-fetch      # cached data only

# Configure home + challenges, then see where you stand
cp config/preferences.example.yaml config/preferences.yaml   # then edit
parkrun-agent config show            # resolved home + enabled challenges
parkrun-agent challenges show        # your progress per challenge

# Where should I run next? (local / stretch / destination tiers from home)
parkrun-agent recommend
parkrun-agent recommend --local-only   # hide the global "destination" tier

# "I'm travelling to <place> — which parkrun there?" (manual coords)
parkrun-agent recommend --lat 54.6872 --lon 25.2797 --stretch 150

# Natural-language agent (needs an Anthropic API key — see below)
export ANTHROPIC_API_KEY=sk-ant-...
parkrun-agent ask "I'm travelling to Vilnius next week — where should I run?"
parkrun-agent ask "How am I doing on my challenges?"
```

## The agent (LangChain / LangGraph)

Milestone 4 (DESIGN.md §7) wraps the deterministic core in LangChain **tools**
(`profile_summary`, `challenge_progress`, `recommend_from_home`,
`recommend_near`) and a **LangGraph ReAct agent** that calls them. A **geocoder**
(OpenStreetMap Nominatim, cached) turns free-text places like "Vilnius" into
coordinates, so travel questions work from plain English. The LLM only picks
tools and writes prose — all facts come from the deterministic core.

Requires Anthropic credentials (`ANTHROPIC_API_KEY`). The model defaults to
`claude-opus-5-5`; override with `PARKRUN_LLM_MODEL` (e.g.
`claude-haiku-5-5` is far cheaper for experimenting) or `--model`.

## Recommendation engine

Milestone 3 (DESIGN.md §6): scores each candidate event by scarcity-weighted
challenge contribution, novelty and distance, then splits results into **local**
(≤50 km), **stretch** (further but fills a rare slot) and **destination**
(globally high-value, e.g. the Wilson blocker) tiers. Adult (5k) events only;
junior parkruns are excluded. Still no LLM — this is pure, testable Python.

## Configuration

`config/preferences.yaml` (gitignored; copy from `preferences.example.yaml`)
holds your athlete number, home location (either a parkrun **event name/slug**
or explicit **lat/lon**), search radii, and which challenges are enabled —
including custom ones defined entirely in YAML. See the example file.

## Challenges

Built-in: `alphabeteer`, `pirates`, `compass` (token-collection); `wilson`
(prefix from event #1) and `floating_wilson` (longest consecutive run anywhere —
far more achievable); and region-completion challenges `australia` + per-state
`au_wa`/`au_nsw`/`au_vic`/`au_qld`/`au_sa`/`au_tas`/`au_act`/`au_nt` (run every
event in that region). Enable the ones you want in `preferences.yaml`, or define
your own in YAML. See [DESIGN.md](DESIGN.md) §5.

> Note: Australian state assignment uses approximate straight-line borders; the
> WA (129°E) and SA/NT (26°S) borders are exact, but events near the irregular
> NSW/VIC and QLD/NSW borders may be misclassified.

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
