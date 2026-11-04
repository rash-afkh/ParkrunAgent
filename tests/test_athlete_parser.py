from datetime import date

from parkrun_agent.data.athlete_repo import (
    parse_age_grade,
    parse_athlete_html,
    parse_date,
    parse_time_to_seconds,
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
