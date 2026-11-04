# ParkrunAgent — Design Document

An agent that reads your public parkrun profile, tracks your progress against a
set of challenges, and recommends where to run next — as a weekly email and as
an on-demand assistant ("I'm travelling to Vilnius next week, where should I
run?"). Built with LangChain, designed to become an API, and extensible toward
group/friends recommendations.

---

## 1. Guiding principles

1. **Deterministic core, LLM at the edges.** All math (distance, challenge
   progress, scoring) lives in plain Python that is unit-testable and
   framework-agnostic. The LLM is used only for (a) parsing free-text requests
   into a structured query, and (b) turning ranked results into friendly prose.
   Never let the model compute distances or decide challenge logic — it will
   hallucinate. LangChain *orchestrates* the core; it does not *contain* it.

2. **The core has no knowledge of LangChain, email, or HTTP.** Those are three
   separate delivery adapters (scheduler, SMTP, FastAPI) that all call the same
   `recommend()` function. This is what makes the "convert to an API later" step
   trivial.

3. **Challenges are plugins.** A `Challenge` is an object with a known
   interface. Built-ins ship in the repo; user-defined ones are registered via
   config. Adding the "Pirates" challenge should be ~15 lines, not a refactor.

4. **Everything is cached.** parkrun has no public API and rate-limits/guards
   its pages (see §3). Fetch rarely, cache aggressively, degrade gracefully.

---

## 2. High-level architecture

```
                         ┌─────────────────────────────────────────┐
                         │             DELIVERY ADAPTERS             │
                         │                                           │
  weekly cron ──────────▶│  scheduler  │  FastAPI  │  CLI / chat     │
                         └───────┬───────────┬──────────┬────────────┘
                                 │           │          │
                                 ▼           ▼          ▼
                         ┌─────────────────────────────────────────┐
                         │          LANGCHAIN ORCHESTRATION          │
                         │                                           │
                         │  • Weekly digest pipeline (LangGraph)     │
                         │  • Interactive ReAct agent (tools)        │
                         │  • Structured-output query parser         │
                         │  • Narrative generator (prose from data)  │
                         └───────────────────┬───────────────────────┘
                                             │ calls tools, which wrap…
                                             ▼
                         ┌─────────────────────────────────────────┐
                         │            DETERMINISTIC CORE             │
                         │                                           │
                         │  domain models   challenge engine         │
                         │  recommendation engine (scoring)          │
                         │  geo utilities   candidate generation      │
                         └───────────────────┬───────────────────────┘
                                             │
                                             ▼
                         ┌─────────────────────────────────────────┐
                         │          DATA ACCESS + CACHE              │
                         │                                           │
                         │  profile fetcher   events catalogue       │
                         │  geocoder          SQLite/Postgres cache   │
                         └─────────────────────────────────────────┘
```

Two orchestration entry points share one core:

- **Weekly digest** — a fixed pipeline (best modelled as a LangGraph): fetch →
  compute progress → generate candidates → score → draft email. Deterministic;
  LLM only writes the final narrative.
- **Interactive agent** — a tool-using ReAct agent for free-text questions. The
  LLM decides *which* tools to call and in what order, but the tools do the work.

---

## 3. Data acquisition (the hard part — read this first)

parkrun has **no official public API**, and its Terms of Use discourage
automated scraping; result pages sit behind bot protection (Cloudflare). Design
accordingly:

| Data | Source | Notes |
|------|--------|-------|
| **All events** (name, country, lat/lon, status) | `https://images.parkrun.com/events.json` | Public, single JSON file, ~2500 events worldwide incl. Vilnius. Refresh weekly. This is your geo catalogue. |
| **Athlete run history** | `https://www.parkrun.<tld>/parkrunner/<id>/all/` | HTML; parse the "All Results" table (event, date, run #, pos, time, age grade). Works from any country domain. ⚠️ The older `/results/athleteresultshistory/?athleteNumber=<id>` endpoint now returns only a 10-row summary — don't use it. Needs realistic headers + polite rate limiting. |
| **Geocoding** a place name ("Vilnius") | Nominatim/OpenStreetMap or a geocoding API | Only needed for the free-text travel query; events.json already has coordinates. |

Design rules for the data layer:
- **Cache athlete history** (e.g. 24h TTL) and **events.json** (7d TTL) in the
  DB. The scraper is the *only* code allowed to touch the network for parkrun.
- One realistic `User-Agent`, exponential backoff, max 1 request / few seconds,
  for **personal use only**. Keep this behind an interface
  (`AthleteRepository`) so it can be swapped for a manual CSV import or a
  community dataset if scraping becomes unreliable.
- Make the fetcher *fail soft*: if a fetch fails, serve the last cached profile
  and flag staleness in the output.

> ⚠️ Flagging honestly: automated access may breach parkrun's ToS. Keep usage
> personal, low-volume, and cached. If this ever goes multi-user/public, you'd
> want to switch to user-provided exports or seek permission.

---

## 3.5 Data storage & caching (Postgres)

### Philosophy: the database *is* the cache

For a single-user, weekly-cadence app you do **not** need Redis or a separate
cache server. Every table that holds fetched data carries a `fetched_at`
timestamp, and each repository does **read-through with TTL**:

```
get(key):
    row = db.lookup(key)
    if row and fresh(row.fetched_at, ttl):   return row          # cache hit
    try:    data = fetch_from_network();  db.upsert(data);  return data
    except: if row: return row (flag stale)  else raise          # fail-soft
```

So "caching" is not a separate component — it's the tables below + TTL logic in
the repositories. Redis only becomes worthwhile if you go multi-user with hot,
concurrent reads; design leaves room for it but doesn't require it.

Use **SQLAlchemy** models so dev can run **SQLite** and prod can run
**Postgres** with only a connection-string change. Add **PostGIS** in prod *if*
you want native radius queries; otherwise a bounding-box prefilter + haversine
in SQL handles 2,500 events trivially.

### Tables

```
events                     -- geo catalogue, from events.json (TTL 7d, global)
  id            PK          -- parkrun event id
  name, short_name, country_code
  lat, lon                 -- (+ geom geography(Point) if PostGIS)
  status                   -- active | closed
  url
  founding_rank            -- nullable; for Wilson Index
  raw            jsonb      -- original record, for re-parsing
  fetched_at     timestamptz

catalogue_meta             -- one row: refresh bookkeeping for events.json
  last_refreshed_at, source_etag   -- ETag → If-None-Match, skip re-download

athletes                   -- one row per athlete number (TTL ~ next Saturday)
  id            PK          -- athlete number
  name, home_event
  fetched_at     timestamptz
  raw_html       text       -- optional, for re-parse/debug

runs                       -- append-only history; parsed from profile
  id            PK serial
  athlete_id    FK -> athletes
  event_name, event_id (FK -> events, nullable; resolved by name match)
  run_date, run_number, time_seconds, age_grade
  UNIQUE(athlete_id, event_name, run_date)   -- idempotent re-scrape

geocode_cache              -- place name -> coords (TTL ~ forever)
  query         PK          -- normalised lowercased place string
  lat, lon, display_name, source, fetched_at

users                      -- subscriptions / prefs (future multi-user)
  id            PK
  athlete_id    FK -> athletes
  email
  prefs          jsonb      -- radii, per-challenge weights, focus challenges
  active         bool

custom_challenges          -- user-defined challenges (mirrors challenges.yaml)
  id            PK
  user_id       FK nullable -- null = global built-in override
  key, name, type
  config         jsonb      -- targets, token rule, etc.

recommendations_log        -- closes the feedback loop for learned ranking
  id            PK serial
  athlete_id    FK
  event_id      FK
  generated_at   timestamptz
  score          float
  reasons        jsonb
  context        jsonb      -- origin, radius, intent (weekly/travel/friends)
  sent_in_digest bool
  outcome        text       -- null | 'ran' | 'ignored'
```

### Why `recommendations_log.outcome` is clever
You never have to ask the user whether they took a suggestion. When you
re-scrape their run history, any new `run` whose event matches a prior
recommendation flips that row's `outcome` to `'ran'`. That labelled data is
exactly what trains the `LearnedScorer` in §6 — the feedback loop is automatic.

### TTLs / invalidation

| Data | TTL | Notes |
|------|-----|-------|
| `events` catalogue | 7 days | Use ETag `If-None-Match`; a 304 just bumps `fetched_at`, no re-parse. |
| `athletes` + `runs` | **until next Saturday** | Results only change after Saturday's run. Smarter than a flat 24h — avoids needless scrapes mid-week and guarantees a fresh pull before the weekly email. |
| `geocode_cache` | ~forever (30d+) | Place coordinates don't move. |
| LLM calls | optional | Back LangChain's built-in LLM cache with SQLite/Postgres to skip paying for identical prompts (e.g. repeated narrative generation in dev). |

### Write pattern
All fetchers use **upserts** (`INSERT … ON CONFLICT DO UPDATE` for events/
athletes; `DO NOTHING` for append-only runs). This makes every fetch idempotent
and safe to retry — important given the flaky-scrape reality of §3.

### How this changes §10 layout
`data/cache.py` becomes the SQLAlchemy engine/session + TTL helpers; add
`data/schema.py` (models) and `data/migrations/` (Alembic). The repositories
(`athlete_repo.py`, `events_catalogue.py`, `geocoder.py`) own the read-through
logic above.

---

## 4. Domain model

Plain Pydantic models (Pydantic v2) — these double as API schemas and
LangChain structured-output targets.

```python
class Event(BaseModel):
    id: int
    name: str                 # "Bushy parkrun"
    short_name: str           # "Bushy"
    country: str
    lat: float
    lon: float
    url: str

class Run(BaseModel):
    event_name: str
    event_id: int | None
    date: date
    run_number: int           # the event's nth running when you ran it
    time_seconds: int
    age_grade: float | None

class Athlete(BaseModel):
    id: int
    name: str | None
    home_event: str | None
    runs: list[Run]
    # derived
    distinct_events: set[str]

class ChallengeProgress(BaseModel):
    challenge: str
    completed: list[str]       # e.g. letters/events already satisfied
    remaining: list[str]       # what's still needed
    percent: float
    is_complete: bool

class Recommendation(BaseModel):
    event: Event
    distance_km: float
    score: float
    reasons: list[str]         # human-readable "why" lines
    challenge_contributions: dict[str, float]
    tier: Literal["local", "stretch", "destination"]
```

---

## 5. Challenge engine

The heart of the extensibility story. A challenge is an object implementing:

```python
class Challenge(Protocol):
    key: str
    name: str
    description: str

    def progress(self, athlete: Athlete) -> ChallengeProgress: ...

    # marginal value in [0, 1]: how much does running `event` advance the
    # challenge *given what the athlete has already done*?
    def contribution(self, event: Event, athlete: Athlete) -> float: ...
```

Most parkrun challenges are variations of **"collect a set of tokens"**, so a
single parameterised base class covers many of them:

```python
class TokenCollectionChallenge(Challenge):
    """Collect a target set of tokens, each derived from an event name."""
    def __init__(self, key, name, targets: set[str],
                 token_fn: Callable[[str], set[str]]):
        ...
    # progress = targets already covered by athlete's distinct events
    # contribution(event) = (# new targets this event's tokens would fill) / |targets|,
    #                       boosted if the token is rare (see scarcity in §6)
```

### Built-in challenges

| Challenge | token_fn / rule |
|-----------|-----------------|
| **Alphabeteer (A–Z)** | first letter of event name; targets = A–Z (minus X by convention) |
| **Pirates** | letters present in name; targets = {P,I,R,A,T,E,S} |
| **Compass Club** | targets = {North, South, East, West} appearing in name |
| **Stopwatch Bingo** | token = seconds digits of finish time (00–59); targets = 00..59 — *time-based, not event-based* → overrides `contribution` to always return 0 (you can't pick an event to guarantee a second) but still reports progress |
| **Wilson Index** | run at the events that were the 1st, 2nd … nth founded; index = largest n fully covered. `contribution(event)` high if event's founding rank == current_index + 1 |
| **NENDY** (Nearest Event Not Done Yet) | not a collection; `contribution` = 1 for the single nearest unvisited event |
| **Tourist / Cowell (distinct events)** | every new distinct event contributes; `contribution` = 1 if unvisited |
| **Regionnaire** | all events in a chosen region/country |

Stopwatch Bingo and Wilson show why `Challenge` is an interface, not just a
config row: some challenges need custom logic. The common case stays config.

### User-defined challenges

A `challenges.yaml` registers new token-collection challenges without code:

```yaml
challenges:
  - key: double_letter
    name: "Double Letter Club"
    type: token_collection
    targets: [AA, BB, CC, DD]          # silly example
    token: first_two_letters
  - key: my_counties
    name: "Home Counties Tour"
    type: token_collection
    targets: [Surrey, Kent, Essex]
    token: region
```

The loader maps `type` + `token` to a builder. Anything not expressible this way
is added as a Python subclass and registered in a `CHALLENGE_REGISTRY` dict.

---

## 6. Recommendation engine

Pure function, no LLM:

```python
def recommend(
    athlete: Athlete,
    events: list[Event],
    challenges: list[Challenge],
    origin: GeoPoint,              # home event, or a travel destination
    prefs: Preferences,
) -> list[Recommendation]
```

### Step 1 — candidate generation
Filter `events` to those within `prefs.stretch_radius_km` of `origin` (e.g.
200 km), tagging each with distance. Also keep a small set of *destination*
candidates if a travel origin was supplied (all events near that place).

### Step 2 — feature extraction per candidate
For each candidate event compute:

- `contrib[c]` = `challenge.contribution(event, athlete)` for each active `c`.
- `scarcity[c]` = `1 / (1 + N)` where `N` = number of *other nearby* candidates
  that could fill the **same** slot. → The only Q-event in 100 km is worth far
  more than one of ten A-events. This is what makes recommendations smart.
- `novelty` = 1 if unvisited, small positive if visited long ago, else 0.
- `distance_km`.

### Step 3 — scoring

```
challenge_value = Σ_c  w_c · contrib[c] · (0.5 + scarcity[c])
raw_score       = challenge_value + w_novelty · novelty
distance_penalty = f(distance_km)          # 0 within home radius, then rising
score            = raw_score − w_distance · distance_penalty
```

`w_c` are per-challenge weights from `Preferences` (lets the user say "I care
most about the alphabet challenge"). `f` is piecewise: free inside
`prefs.local_radius_km` (~50 km), linear beyond.

### Step 4 — tiering & selection
- **local**: distance ≤ `local_radius_km`. Rank by score. Take top K.
- **stretch**: beyond local but `score` still high *because* of rare challenge
  fills (scarcity carried the day). Top K.
- **destination**: only when a travel origin was given; rank purely by challenge
  value, ignoring distance.

Return a merged, de-duplicated, ranked list with `reasons` populated, e.g.
`"Fills 'Q' for your Alphabet challenge — the only Q-event within 180 km"`.

### Why this is a "recommendation engine" and where it grows
- Today: **content-based** scoring (features of events × athlete state).
- Later: log whether the user actually went (feedback), and learn the weights
  `w_c` / distance sensitivity per user (**learning-to-rank**).
- Later: **group/collaborative** objective for the friends feature (§9).

Keep the scorer behind a `Scorer` interface (`RuleScorer` now, `LearnedScorer`
later) so the engine doesn't change when the model does.

---

## 7. LangChain orchestration

### 7a. Tools (wrap the core — this is the LangChain you'll write most)

```python
@tool
def get_profile(athlete_id: int) -> Athlete: ...
@tool
def get_challenge_progress(athlete_id: int) -> list[ChallengeProgress]: ...
@tool
def find_events_near(place: str | None, lat: float | None,
                     lon: float | None, radius_km: float) -> list[Event]: ...
@tool
def recommend_events(athlete_id: int, origin: str | None,
                     radius_km: float = 50) -> list[Recommendation]: ...
@tool
def geocode(place: str) -> GeoPoint: ...
```

Each tool is a thin wrapper around a core function. Tools return Pydantic
models; the agent passes them around.

### 7b. Interactive agent (the "Vilnius" use case)

A **ReAct / tool-calling agent** (`create_react_agent` in LangGraph, or
`AgentExecutor` in classic LangChain). Flow it learns to perform:

> "I'm travelling to Vilnius next week — where should I run?"
> → `geocode("Vilnius")` → `recommend_events(athlete_id, origin="Vilnius",
> radius_km=30)` → narrate the top picks with challenge reasons.

The system prompt pins the athlete id and tells the model: *use tools for all
facts; never invent events or distances.*

### 7c. Query parsing with structured output

For both entry points, parse free text into a typed request so the deterministic
core gets clean input:

```python
class QuerySpec(BaseModel):
    intent: Literal["weekly_digest", "travel", "nearby", "friends"]
    place: str | None
    radius_km: float | None
    focus_challenges: list[str] | None
    athlete_ids: list[int] | None

parser = llm.with_structured_output(QuerySpec)
```

### 7d. Weekly digest pipeline (LangGraph)

A small state graph — deterministic nodes, one LLM node at the end:

```
[fetch_profile] → [compute_progress] → [generate_candidates]
      → [score_and_rank] → [draft_email (LLM)] → [send]
```

Only `draft_email` touches the LLM: it receives the structured
`list[Recommendation]` + progress and produces the friendly email body
(Jinja2 handles layout; the LLM writes the "why you'll like this" sentences).
Modelling it as a graph gives you retries, checkpointing, and a clean place to
add nodes (e.g. a "weather check" node) later.

### LCEL / chains note (since you're learning)
- Use **LCEL** (`prompt | llm | parser`) for the simple, linear bits (query
  parsing, narrative generation).
- Use **LangGraph** for the multi-step weekly flow and the agent (it's the
  modern successor to `AgentExecutor` and handles loops/state better).
- Use **tools + `with_structured_output`** everywhere the LLM touches data.

---

## 8. Delivery adapters

- **Scheduler** — APScheduler (in-process) or a system cron / cloud scheduler
  that runs the weekly LangGraph pipeline per subscribed athlete.
- **Email** — Jinja2 template + SMTP or a provider (SendGrid/SES/Resend). The
  email renderer takes `list[Recommendation]` + narrative text; it is dumb.
- **FastAPI (future)** — same core, new transport:
  ```
  GET  /athletes/{id}/progress            → list[ChallengeProgress]
  GET  /athletes/{id}/recommendations     ?lat&lon&radius → list[Recommendation]
  POST /query            {text, athlete_id}  → agent answer (free text)
  POST /athletes/{id}/subscribe           → enable weekly digest
  ```
  Because the core and tools are already pure, the API is a day's work: wire
  endpoints to the same functions the tools call.

---

## 9. Future add-ons (designed-for, not built yet)

- **Friends / group recommendations.** `recommend_group(athlete_ids, origin)`:
  compute each person's challenge state, then score events by a *group
  objective* — e.g. maximise total challenge progress across the group, or find
  events *nobody* has done (shared tourism). The scoring loop already iterates
  athletes; extend it to aggregate. New tool `recommend_for_friends`, new intent
  in `QuerySpec`.
- **Learned ranking.** Log recommendations + whether the user ran there; train
  `LearnedScorer` to personalise weights.
- **Cancellations / weather / travel feasibility** as extra LangGraph nodes and
  score features.
- **Vector search** over events ("scenic trail parkruns near lakes") using
  event descriptions + an embedding store.
- **Multi-user SaaS** — move cache to Postgres, add auth, per-user prefs &
  challenge sets.

---

## 10. Suggested project layout

```
parkrun_agent/
  core/
    models.py            # Pydantic domain + API schemas
    geo.py               # haversine, GeoPoint
    challenges/
      base.py            # Challenge protocol, TokenCollectionChallenge
      builtins.py        # alphabet, pirates, compass, wilson, bingo, ...
      registry.py        # CHALLENGE_REGISTRY + yaml loader
    recommend.py         # recommend(), Scorer interface, RuleScorer
  data/
    events_catalogue.py  # events.json fetch + cache
    athlete_repo.py      # AthleteRepository (scraper impl + cache)
    geocoder.py
    schema.py            # SQLAlchemy models (§3.5 tables)
    cache.py             # engine/session + TTL read-through helpers
    migrations/          # Alembic (SQLite dev → Postgres prod)
  agent/
    tools.py             # @tool wrappers over core
    interactive.py       # ReAct agent (travel/nearby questions)
    digest_graph.py      # LangGraph weekly pipeline
    query_parser.py      # QuerySpec structured output
    narrative.py         # LCEL chain: recommendations → prose
  delivery/
    email_renderer.py    # Jinja2 templates
    scheduler.py         # APScheduler jobs
    api.py               # FastAPI (future)
  config/
    challenges.yaml      # user-defined challenges
    preferences.yaml     # radii, weights, athlete id, email
  tests/                 # core is pure → easy unit tests
```

---

## 11. Build order (milestones)

1. **Core data + models**: fetch events.json, scrape one athlete, parse to
   `Athlete`/`Run`. Cache. (No LangChain yet.)
2. **Challenge engine**: `TokenCollectionChallenge` + alphabet/pirates/compass,
   `progress()` for your real profile. Unit tests.
3. **Recommendation engine**: `recommend()` with scoring + tiers, printed to
   console. This is the actual brain — get it right before adding the LLM.
4. **LangChain tools + interactive agent**: the Vilnius query end-to-end.
5. **Weekly digest**: LangGraph pipeline + email template + scheduler.
6. **Wrap in FastAPI.**
7. **Friends / learned ranking** add-ons.

Start at 1–3 (no LLM) so the recommendations are correct and testable; add
LangChain (4–5) once the core is trustworthy.
```
