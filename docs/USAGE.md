# ParkrunAgent — User Guide

Everything ParkrunAgent can do, and how to set it up. All commands start with
`parkrun-agent` (after installing — see below).

## Contents
- [Install](#install)
- [First-time setup](#first-time-setup)
- [Command reference](#command-reference)
- [Setting up the `ask` agent (Ollama or Anthropic)](#setting-up-the-ask-agent)
- [Configuration file](#configuration-file)
- [Challenges](#challenges)
- [Troubleshooting](#troubleshooting)

---

## Install

Requires Python 3.11+.

```bash
git clone <repo-url> parkrun-agent && cd parkrun-agent
python -m venv .venv && source .venv/bin/activate

pip install -e .            # core features (no LLM) — this is all most people need
pip install -e ".[agent]"   # also install the natural-language `ask` agent
```

---

## First-time setup

```bash
parkrun-agent init-db            # create the local SQLite cache
parkrun-agent events refresh     # download the global events catalogue (cached 7 days)

cp config/preferences.example.yaml config/preferences.yaml
#  edit config/preferences.yaml:
#   - athlete_id: your parkrun number (from your results URL: /parkrunner/<NUMBER>/)
#   - home: a parkrun event name/slug, OR explicit lat/lon
```

The database lives in `./local_data/` by default. Override with
`PARKRUN_DB_URL` (any SQLAlchemy URL, e.g. a Postgres DSN).

---

## Command reference

### Profile & stats

| Command | What it does |
|---|---|
| `athlete show --id <N>` | Fetch + cache + summarise a profile (runs, distinct events, letters). |
| `athlete describe` | Rich summary: runs, countries, years active, PBs, farthest-apart events, volunteering, clubs, field sizes. |
| `athlete crowds` | Most/least crowded parkruns you've run. Incremental: fetches up to `--max-new` new events. |
| `athlete crowds --backfill` | One-time: fetch field sizes for **all** your events (slower; use `--delay 3` to be gentle). |
| `athlete crowds --no-fetch` | Rebuild the summary from cache only. |
| `athlete crowds --retry-unavailable` | Retry events previously marked unavailable (e.g. after rate-limiting). |

### Challenges & recommendations

| Command | What it does |
|---|---|
| `challenges show` | Your progress on every enabled challenge. |
| `recommend` | Where to run next from home: **local / stretch / destination** tiers. |
| `recommend --local-only` | Only nearby picks; hide the global destination tier. |
| `recommend --lat <LAT> --lon <LON>` | Recommend near a travel location (manual coordinates). |
| `recommend --local <KM> --stretch <KM>` | Override the tier radii. |

### Events & config

| Command | What it does |
|---|---|
| `events refresh [--force]` | Refresh the events catalogue (cached 7 days; `--force` ignores the TTL). |
| `events near --lat <LAT> --lon <LON> --radius <KM>` | List events near a point. |
| `config show` | Show the resolved config (home, radii, enabled challenges). |

### Natural language

| Command | What it does |
|---|---|
| `ask "<question>"` | Ask the agent anything, e.g. travel or challenge questions. Needs an LLM backend (below). |
| `ask "..." --provider ollama` | Force the free local backend for this call. |
| `ask "..." --model <id>` | Override the model id. |

Most commands accept `--id <N>` (defaults to `athlete_id` in your config) and
`--config <path>` (defaults to `config/preferences.yaml`).

---

## Setting up the `ask` agent

The agent turns plain-English questions into tool calls over the deterministic
core. **You don't need it** for recommendations/challenges/stats — those work
without any LLM. If you want it, pick one backend:

### Option A — Free & local with Ollama (no key, no cost, private)

1. Install Ollama from <https://ollama.com>.
2. Pull a tool-calling model:
   ```bash
   ollama pull llama3.1        # or llama3.2 / qwen2.5 — all support tool-calling
   ```
3. Tell ParkrunAgent to use it:
   ```bash
   export PARKRUN_LLM_PROVIDER=ollama
   export PARKRUN_LLM_MODEL=llama3.1          # optional; this is the default
   parkrun-agent ask "which parkrun near Edinburgh helps my challenges?"
   ```
   If your Ollama runs elsewhere, set `OLLAMA_HOST=http://host:11434`.

> Use a model that supports **tool calling** (llama3.1/3.2, qwen2.5). Very small
> models can be unreliable at picking tools.

### Option B — Anthropic Claude (paid, bring your own key)

1. Get an API key from <https://console.anthropic.com>.
2. Put it in a `.env` file in the project root (auto-loaded; `.env` is gitignored):
   ```
   ANTHROPIC_API_KEY=sk-ant-...
   PARKRUN_LLM_MODEL=claude-haiku-5-5
   ```
3. Ask away:
   ```bash
   parkrun-agent ask "I'm travelling to Vilnius next week, where should I run?"
   ```

**Cost:** `claude-haiku-5-5` is ~$0.0007 per question (a fraction of a cent) and
plenty for this task. `claude-opus-5-5` is ~40× more — not needed here.

### Switching / precedence

`--provider` / `--model` (per command) override `PARKRUN_LLM_PROVIDER` /
`PARKRUN_LLM_MODEL` (env), which override the defaults (`anthropic`,
`claude-opus-5-5`).

---

## Configuration file

`config/preferences.yaml` (copy from `config/preferences.example.yaml`):

```yaml
athlete_id: 1234567

home:
  event: "Bushy parkrun"     # a parkrun name or slug...
  # lat: 51.410992           # ...or explicit coordinates (take precedence)
  # lon: -0.335791

preferences:
  local_radius_km: 50        # "nearby" tier
  stretch_radius_km: 200     # how far to look for high-value stretch picks
  challenge_weights:         # optional: emphasise challenges you care about
    alphabeteer: 1.5

challenges:
  enabled: [alphabeteer, pirates, compass, wilson, floating_wilson, au_wa]
  custom:                    # define your own without touching code
    - key: my_counties
      name: "Home Counties Tour"
      type: token_collection
      token: first_letter    # or 'compass'
      targets: [S, K, E]
```

---

## Challenges

| Key | Description |
|---|---|
| `alphabeteer` | Events whose names start with each letter A–Z (excluding X). |
| `pirates` | Events starting with each of P, I, R, A, T, E, S. |
| `compass` | Events whose names contain North, South, East, West. |
| `wilson` | Wilson Index: unbroken run of events in founding order from #1. |
| `floating_wilson` | Longest run of consecutive event numbers anywhere (more achievable). |
| `australia` | Run every parkrun in Australia. |
| `au_wa`, `au_nsw`, `au_vic`, `au_qld`, `au_sa`, `au_tas`, `au_act`, `au_nt` | Run every event in that state/territory. |

Add your own `token_collection` challenges in `preferences.yaml` (see above).

---

## Troubleshooting

- **"Catalogue empty"** → run `parkrun-agent events refresh`.
- **`athlete crowds` shows a lot of "temporarily unavailable (HTTP 405)"** →
  you're being rate-limited. Stop, wait, and retry later with a larger delay:
  `parkrun-agent athlete crowds --backfill --delay 3`. Events hit by this are
  **not** lost — they're retried next time. (A genuine `404` means the event was
  cancelled/removed and is skipped permanently; `--retry-unavailable` re-checks.)
- **`ask` says "Agent needs extra dependencies"** → `pip install ".[agent]"`.
- **`ask` can't reach an LLM** → set up Ollama or an Anthropic key (above).
- **Volunteer count missing from `describe`** → refresh the profile once:
  `parkrun-agent athlete show --id <N> --force`.

See [DESIGN.md](../DESIGN.md) for how it all works.
