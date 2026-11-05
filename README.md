# ParkrunAgent 🏃

Find your next parkrun. ParkrunAgent reads your **public parkrun profile**,
tracks your progress against a set of **challenges** (Alphabeteer, Wilson Index,
state/country completion, …), and recommends **where to run next** — nearby,
a bit further for a rare challenge fill, or worth-the-trip destinations. It also
answers travel questions in plain English ("I'm in Vilnius next week — where
should I run?") and digs up stats parkrun doesn't show you, like your **most and
least crowded** parkruns.

Everything runs **locally on your machine** against your own profile. The useful
parts need **no account, no API key, and no cost**.

## What it can do

- **Challenge tracking** — Alphabeteer (A–Z), Pirates, Compass Club, Wilson Index
  and the more achievable **Floating Wilson Index**, plus **region-completion**
  challenges (all of Australia, or per-state). Add your own in YAML.
- **Recommendations** — scored by how much an event advances your challenges
  (rare fills rank higher), split into **local / stretch / destination** tiers.
- **Travel queries** — "which parkrun near \<place\>?" via a natural-language agent.
- **Athlete summary** — runs, distinct events, countries, years active, PBs,
  volunteering, farthest-apart events, and **field-size (crowd) stats**.

## Install

Requires Python 3.11+.

```bash
git clone <your-fork-url> parkrun-agent && cd parkrun-agent
python -m venv .venv && source .venv/bin/activate

pip install -e .            # core features (no LLM) — recommendations, challenges, stats
pip install -e ".[agent]"   # + the natural-language `ask` agent (optional)
```

## Quickstart

```bash
parkrun-agent init-db                 # create the local cache
parkrun-agent events refresh          # fetch the global events catalogue (cached 7 days)

cp config/preferences.example.yaml config/preferences.yaml
# edit it: set athlete_id to your parkrun number and your home event/coords

parkrun-agent challenges show         # how you're doing on each challenge
parkrun-agent recommend               # where to run next
parkrun-agent athlete describe        # your parkrun summary
```

Your athlete number is on your results page URL:
`parkrun.com.au/parkrunner/<NUMBER>/` (any country domain works).

📖 **Full command reference and LLM setup: [docs/USAGE.md](docs/USAGE.md).**

## Commands

```bash
# Profile & stats
parkrun-agent athlete show --id <N>        # fetch + cache + summarise
parkrun-agent athlete describe             # rich summary (stats, farthest-apart, clubs, volunteering)
parkrun-agent athlete crowds               # most/least crowded parkruns you've run
parkrun-agent athlete crowds --backfill    #   one-time: fetch field sizes for ALL your events

# Challenges & recommendations
parkrun-agent challenges show
parkrun-agent recommend                    # from home: local / stretch / destination tiers
parkrun-agent recommend --local-only       # hide the global destination tier
parkrun-agent recommend --lat 54.69 --lon 25.28   # near a travel location (manual coords)

# Natural language (needs an LLM backend — see below)
parkrun-agent ask "I'm travelling to Vilnius next week, where should I run?"
parkrun-agent ask "how am I doing on my challenges?"
```

## The `ask` agent (optional) — free local **or** paid

The agent only *chooses tools and writes prose*; every fact comes from the
deterministic core. Pick a backend:

**Free & local — Ollama (no key, no cost, nothing leaves your machine):**
```bash
# install Ollama from ollama.com, then:
ollama pull llama3.1
export PARKRUN_LLM_PROVIDER=ollama
parkrun-agent ask "which parkrun near Edinburgh helps my challenges?"
```
Use a model that supports tool-calling (llama3.1 / llama3.2 / qwen2.5 are good).

**Anthropic Claude (paid, bring your own key):**
```bash
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env     # auto-loaded; .env is gitignored
export PARKRUN_LLM_MODEL=claude-haiku-5-5       # ~$0.0007/query; cheap and plenty
parkrun-agent ask "..."
```

Configure with `PARKRUN_LLM_PROVIDER` (`ollama`/`anthropic`), `PARKRUN_LLM_MODEL`,
or `--provider` / `--model`.

## Configuration

`config/preferences.yaml` (copy from the example; it's gitignored so your details
stay private):

```yaml
athlete_id: 1234567
home:
  event: "Bushy parkrun"     # a name/slug, OR explicit lat/lon
preferences:
  local_radius_km: 50
  stretch_radius_km: 200
challenges:
  enabled: [alphabeteer, pirates, compass, wilson, floating_wilson, australia, au_wa]
```

Challenge keys: `alphabeteer`, `pirates`, `compass`, `wilson`, `floating_wilson`,
and region keys `australia` + `au_wa`/`au_nsw`/`au_vic`/`au_qld`/`au_sa`/`au_tas`/
`au_act`/`au_nt`. Define your own token-collection challenges in YAML too — see the
example file. (Australian state assignment uses approximate straight-line borders.)

## How it works

A deterministic Python core (challenge logic, geo scoring, stats) with an optional
LangChain/LangGraph agent layered on top. The database doubles as a cache
(read-through with TTLs). See **[DESIGN.md](DESIGN.md)** for the full architecture.

## Please use it responsibly

parkrun has no public API, and its terms discourage automated scraping. This tool
is for **personal use**: it reads **your own** profile from **your own** machine,
caches aggressively (events weekly, your history until the next Saturday, event
field-sizes forever), and makes at most one polite request at a time. Please don't
turn it into a service that scrapes many athletes from one server — that's what
gets tools blocked. The public `events.json` catalogue is fine to use.

## Development

```bash
pip install -e ".[agent,dev]"
pytest -q        # offline tests (no network, no LLM)
ruff check .
```

## License

MIT — see [LICENSE](LICENSE).
