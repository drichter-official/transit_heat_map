from datetime import date, datetime

from backend.models import ServiceCalendar
from backend.time_utils import active_service_ids, parse_gtfs_date, parse_gtfs_time, seconds_since_midnight


def test_parse_gtfs_time_handles_overnight_values():
    assert parse_gtfs_time("08:30:15") == 30615
    assert parse_gtfs_time("25:30:00") == 91800


def test_seconds_since_midnight_uses_local_clock_time():
    assert seconds_since_midnight(datetime(2026, 4, 30, 8, 5, 7)) == 29107


def test_parse_gtfs_date_reads_compact_date():
    assert parse_gtfs_date("20260430") == date(2026, 4, 30)


def test_active_service_ids_applies_weekday_and_exceptions():
    weekday = ServiceCalendar(
        service_id="weekday",
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 30),
        monday=True,
        tuesday=True,
        wednesday=True,
        thursday=True,
        friday=True,
        saturday=False,
        sunday=False,
    )
    weekend = ServiceCalendar(
        service_id="weekend",
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 30),
        monday=False,
        tuesday=False,
        wednesday=False,
        thursday=False,
        friday=False,
        saturday=True,
        sunday=True,
    )

    active = active_service_ids(
        {"weekday": weekday, "weekend": weekend},
        {date(2026, 4, 30): {"weekday": 2, "weekend": 1}},
        date(2026, 4, 30),
    )

    assert active == {"weekend"}
