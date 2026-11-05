# Contributing to ParkrunAgent

Thanks for your interest! This is a personal-use parkrun tool — contributions
that keep it polite, useful, and respectful of parkrun's infrastructure are very
welcome.

## Development setup

```bash
git clone <your-fork> parkrun-agent && cd parkrun-agent
python -m venv .venv && source .venv/bin/activate
pip install -e ".[agent,dev]"     # core + agent + dev tools
```

## Before you open a PR

```bash
pytest -q          # all tests are offline (no network, no LLM) and must pass
ruff check .       # lint must be clean
```

- Keep tests **offline** — use the injectable fetchers (pass `fetcher=...` /
  `profile_fetcher=...`) and the fixtures in `tests/`. Tests must never hit
  parkrun or an LLM.
- Keep the **core deterministic and LLM-free**. The challenge logic, scoring,
  and stats live in `parkrun_agent/core/` and `parkrun_agent/*.py` and should
  have no LangChain imports. The agent is a thin optional layer.
- New challenges: subclass `Challenge` (or reuse `TokenCollectionChallenge`) in
  `parkrun_agent/core/challenges/`, and add it to the config builder. See
  [DESIGN.md](DESIGN.md) §5.

## Respecting parkrun

parkrun has no public API and discourages automated scraping. Please keep every
change **personal-use and polite**:

- One request at a time, with delays; cache aggressively.
- **Never** add header-spoofing, retry storms, or anything designed to evade
  rate-limiting / bot detection. If parkrun returns 405/429, we back off — we do
  not work around it.
- Don't add features that scrape many athletes from one machine/server.

The public `events.json` catalogue is fine to use.

## Architecture

See [DESIGN.md](DESIGN.md). The short version: deterministic Python core →
optional LangChain agent; the database doubles as a read-through cache.
