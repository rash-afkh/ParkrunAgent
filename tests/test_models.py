from datetime import date

from parkrun_agent.core.models import Athlete, Event, Run


def test_event_url_and_point():
    ev = Event(
        id=1, slug="bushy", name="Bushy parkrun", short_name="Bushy",
        country_code=97, country_url="www.parkrun.org.uk", lat=51.41, lon=-0.33,
    )
    assert ev.url == "https://www.parkrun.org.uk/bushy"
    assert ev.point.lat == 51.41


def test_event_url_none_without_country():
    ev = Event(id=1, slug="x", name="X", short_name="X", country_code=0, lat=0, lon=0)
    assert ev.url is None


def test_athlete_derived_fields():
    runs = [
        Run(event_name="Bushy parkrun", run_date=date(2025, 1, 4), run_number=1, time_seconds=1400),
        Run(event_name="Bushy parkrun", run_date=date(2025, 1, 11), run_number=2, time_seconds=1390),
        Run(event_name="parkrun Vingis", run_date=date(2025, 2, 1), run_number=3, time_seconds=1500),
    ]
    a = Athlete(id=42, runs=runs)
    assert a.total_runs == 3
    assert a.distinct_event_names == {"Bushy parkrun", "parkrun Vingis"}
