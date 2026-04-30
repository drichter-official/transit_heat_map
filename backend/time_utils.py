from __future__ import annotations

from datetime import date, datetime

from backend.models import ServiceCalendar


def parse_gtfs_time(value: str) -> int:
    parts = value.strip().split(":")
    if len(parts) != 3:
        raise ValueError(f"Invalid GTFS time: {value!r}")
    hours, minutes, seconds = (int(part) for part in parts)
    if hours < 0 or minutes < 0 or minutes > 59 or seconds < 0 or seconds > 59:
        raise ValueError(f"Invalid GTFS time: {value!r}")
    return hours * 3600 + minutes * 60 + seconds


def seconds_since_midnight(value: datetime) -> int:
    return value.hour * 3600 + value.minute * 60 + value.second


def parse_gtfs_date(value: str) -> date:
    return datetime.strptime(value.strip(), "%Y%m%d").date()


def _calendar_matches_day(calendar: ServiceCalendar, service_date: date) -> bool:
    if service_date < calendar.start_date or service_date > calendar.end_date:
        return False
    weekday = service_date.weekday()
    return (
        (weekday == 0 and calendar.monday)
        or (weekday == 1 and calendar.tuesday)
        or (weekday == 2 and calendar.wednesday)
        or (weekday == 3 and calendar.thursday)
        or (weekday == 4 and calendar.friday)
        or (weekday == 5 and calendar.saturday)
        or (weekday == 6 and calendar.sunday)
    )


def active_service_ids(
    calendars: dict[str, ServiceCalendar],
    calendar_dates: dict[date, dict[str, int]],
    service_date: date,
) -> set[str]:
    active = {
        service_id
        for service_id, calendar in calendars.items()
        if _calendar_matches_day(calendar, service_date)
    }
    for service_id, exception_type in calendar_dates.get(service_date, {}).items():
        if exception_type == 1:
            active.add(service_id)
        elif exception_type == 2:
            active.discard(service_id)
    return active
