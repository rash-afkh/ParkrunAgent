from datetime import date

from parkrun_agent.core.models import Athlete, Run
from parkrun_agent.crowds import backfill_crowds, format_crowds, runs_with_finishers
from parkrun_agent.data.event_occurrences import EventOccurrencesRepo, parse_event_history

# Minimal event-history markup mirroring parkrun's duplicated responsive cells.
HISTORY_HTML = """
<table><tbody>
  <tr><td>3</td><td>2025-01-18 Someone (M) 18:00</td>
      <td>120 120 finishers</td><td>8 8 volunteers</td></tr>
  <tr><td>2</td><td>2025-01-11 Someone (M) 17:30</td>
      <td>95 95 finishers</td><td>7 7 volunteers</td></tr>
  <tr><td>1</td><td>2025-01-04 Someone (M) 19:00</td>
      <td>210 210 finishers</td><td>9 9 volunteers</td></tr>
</tbody></table>
"""


def test_parse_event_history():
    occ = parse_event_history(HISTORY_HTML)
    assert occ == [(3, 120, 8), (2, 95, 7), (1, 210, 9)]


def _athlete(runs):
    return Athlete(id=3244769, runs=runs)


def _run(slug, run_number, d):
    return Run(event_name=slug.title(), event_slug=slug, run_date=d, run_number=run_number, time_seconds=1500)


def test_backfill_and_match_finishers(db):
    fetches = {"n": 0}

    def fetch(_slug, _domain=None):
        fetches["n"] += 1
        return HISTORY_HTML

    repo = EventOccurrencesRepo(fetcher=fetch)
    athlete = _athlete([
        _run("myevent", 1, date(2025, 1, 4)),   # 210 finishers
        _run("myevent", 3, date(2025, 1, 18)),  # 120 finishers
    ])

    assert backfill_crowds(athlete, repo, delay=0) == 1  # one distinct event
    assert fetches["n"] == 1

    pairs = runs_with_finishers(athlete, repo)
    assert sorted(f for _, f in pairs) == [120, 210]

    # Second backfill does nothing — already cached.
    assert backfill_crowds(athlete, repo, delay=0) == 0
    assert fetches["n"] == 1


def test_format_crowds():
    runs = [
        (_run("busy", 1, date(2025, 1, 4)), 210),
        (_run("quiet", 1, date(2025, 2, 1)), 40),
    ]
    out = format_crowds(runs, distinct_events=2, total_runs=5)
    assert "Most crowded: 210" in out
    assert "Least crowded: 40" in out
    assert "2/5 runs" in out


def test_format_crowds_empty():
    assert "No field-size data" in format_crowds([], distinct_events=0, total_runs=0)
