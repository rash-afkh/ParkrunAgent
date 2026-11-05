import json
from datetime import date

from parkrun_agent.data.athlete_repo import parse_clubs, parse_volunteer_summary
from parkrun_agent.data.events_catalogue import EventsCatalogue
from parkrun_agent.core.models import Athlete, Run
from parkrun_agent.describe import athlete_summary
from tests.conftest import FIXTURES


def test_parse_clubs():
    html = (
        "<h2>Jane</h2><p>Member of the Volunteer 25 Club Member of the 250 Club "
        "doing great</p>"
    )
    assert parse_clubs(html) == ["Volunteer 25 Club", "250 Club"]
    assert parse_clubs("<p>no clubs here</p>") == []


def test_parse_volunteer_summary():
    html = """
    <h3>Volunteer Summary</h3>
    <table><thead><tr><th>Role</th><th>Occasions</th></tr></thead><tbody>
      <tr><td>Marshal</td><td>20 20 Marshal</td></tr>
      <tr><td>Timekeeper</td><td>6 6 Timekeeper</td></tr>
    </tbody></table>
    """
    total, roles = parse_volunteer_summary(html)
    assert total == 26
    assert roles == {"Marshal": 20, "Timekeeper": 6}
    assert parse_volunteer_summary("<p>nothing</p>") == (0, {})


def test_athlete_summary_stats(db):
    data = json.loads((FIXTURES / "events_sample.json").read_text())  # Bushy, Vingis
    catalogue = EventsCatalogue(fetcher=lambda _etag: (data, "e", False))
    catalogue.refresh(force=True)

    runs = [
        Run(event_name="Bushy parkrun", event_slug="bushy", run_date=date(2020, 1, 4),
            run_number=1, time_seconds=1400, age_grade=60.0),
        Run(event_name="Bushy parkrun", event_slug="bushy", run_date=date(2021, 1, 2),
            run_number=2, time_seconds=1380, age_grade=61.0),
        Run(event_name="parkrun Vingis", event_slug="vingis", run_date=date(2025, 6, 7),
            run_number=3, time_seconds=1500, age_grade=55.0),
    ]
    athlete = Athlete(id=3244769, name="Rashid AFKHAMI", runs=runs, clubs=["250 Club"])
    out = athlete_summary(athlete, catalogue)

    assert "Total parkruns: 3" in out
    assert "Distinct events: 2" in out
    assert "Most-visited event: Bushy parkrun (2 runs)" in out
    assert "Fastest run: 23:00" in out          # 1380s
    assert "Countries: 2" in out                 # UK + Lithuania
    assert "Farthest-apart events" in out        # Bushy <-> Vingis
    assert "250 Club" in out
