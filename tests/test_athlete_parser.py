from datetime import date
from pathlib import Path

import pytest

from parkrun_agent.data.athlete_repo import (
    parse_age_grade,
    parse_athlete_html,
    parse_date,
    parse_time_to_seconds,
)

# The user's real saved profile lives in the gitignored local_files/ dir, so this
# regression runs locally but is skipped in a clean checkout (no personal data
# committed).
REAL_PROFILE = (
    Path(__file__).parents[1] / "local_files" / "sample_parkrun_page_a3244769.html"
)


def test_parse_time_to_seconds():
    assert parse_time_to_seconds("23:45") == 23 * 60 + 45
    assert parse_time_to_seconds("1:02:33") == 3753
    assert parse_time_to_seconds("--") is None


def test_parse_date_and_age_grade():
    assert parse_date("01/11/2025") == date(2025, 11, 1)
    assert parse_date("nonsense") is None
    assert parse_age_grade("58.21%") == 58.21
    assert parse_age_grade("") is None


def test_parse_athlete_html(athlete_html):
    athlete = parse_athlete_html(athlete_html, athlete_id=1234567)

    assert athlete.id == 1234567
    assert athlete.name == "Jane SMITH"
    assert athlete.home_event == "Bushy parkrun"
    assert athlete.total_runs == 3

    by_name = {r.event_name: r for r in athlete.runs}
    assert set(by_name) == {"Bushy parkrun", "Alexandra Palace parkrun", "parkrun Vingis"}

    bushy = by_name["Bushy parkrun"]
    assert bushy.event_slug == "bushy"
    assert bushy.run_date == date(2025, 11, 1)
    assert bushy.run_number == 845
    assert bushy.position == 120
    assert bushy.time_seconds == 23 * 60 + 45
    assert bushy.age_grade == 58.21

    assert by_name["parkrun Vingis"].event_slug == "vingis"
    assert by_name["parkrun Vingis"].time_seconds == 3753


def test_parse_handles_empty_page():
    athlete = parse_athlete_html("<html><body>No results here</body></html>", athlete_id=9)
    assert athlete.total_runs == 0


def test_picks_largest_results_table():
    # A 'Most Recent' table (1 run) must not win over 'All Results' (2 runs).
    html = """
    <h2>Test RUNNER (A1)</h2>
    <table id="results"><thead><tr>
      <th>Event</th><th>Run Date</th><th>Pos</th><th>Time</th><th>Age Grade</th>
    </tr></thead><tbody>
      <tr><td><a href="https://www.parkrun.org.uk/bushy/results">Bushy parkrun</a></td>
          <td>01/11/2025</td><td>10</td><td>20:00</td><td>60.00%</td></tr>
    </tbody></table>
    <table id="results"><thead><tr>
      <th>Event</th><th>Run Date</th><th>Run Number</th><th>Pos</th><th>Time</th><th>Age Grade</th>
    </tr></thead><tbody>
      <tr><td><a href="https://www.parkrun.org.uk/bushy/results">Bushy parkrun</a></td>
          <td>01/11/2025</td><td>845</td><td>10</td><td>20:00</td><td>60.00%</td></tr>
      <tr><td><a href="https://www.parkrun.org.uk/ally/results">Ally parkrun</a></td>
          <td>25/10/2025</td><td>512</td><td>12</td><td>21:00</td><td>58.00%</td></tr>
    </tbody></table>
    """
    athlete = parse_athlete_html(html, athlete_id=1)
    assert athlete.total_runs == 2
    assert {r.event_name for r in athlete.runs} == {"Bushy parkrun", "Ally parkrun"}


def test_parse_real_saved_profile():
    """Regression test against the real 298-run profile (local only)."""
    if not REAL_PROFILE.exists():
        pytest.skip("real profile not present (local_files is gitignored)")
    athlete = parse_athlete_html(REAL_PROFILE.read_text(encoding="utf-8", errors="replace"), 3244769)
    assert athlete.name == "Rashid AFKHAMI"
    assert athlete.total_runs == 298
    assert len(athlete.distinct_event_names) > 100
