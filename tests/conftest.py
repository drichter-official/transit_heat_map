from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers import write_table


@pytest.fixture
def tiny_gtfs_dir(tmp_path: Path) -> Path:
    write_table(
        tmp_path,
        "stops.txt",
        ["stop_id", "stop_name", "stop_lat", "stop_lon"],
        [
            ["A", "Zurich Alpha", 47.3760, 8.5410],
            ["B", "Zurich Beta", 47.3770, 8.5450],
            ["C", "Zurich Gamma", 47.3800, 8.5500],
            ["D", "Zurich Delta", 47.3760, 8.5485],
        ],
    )
    write_table(
        tmp_path,
        "trips.txt",
        ["route_id", "service_id", "trip_id"],
        [["R1", "WKD", "T1"]],
    )
    write_table(
        tmp_path,
        "stop_times.txt",
        ["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"],
        [
            ["T1", "08:00:00", "08:00:00", "A", 1],
            ["T1", "08:10:00", "08:10:00", "B", 2],
            ["T1", "08:20:00", "08:20:00", "C", 3],
        ],
    )
    write_table(
        tmp_path,
        "calendar.txt",
        [
            "service_id",
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
            "start_date",
            "end_date",
        ],
        [["WKD", 1, 1, 1, 1, 1, 0, 0, "20260401", "20260430"]],
    )
    write_table(
        tmp_path,
        "calendar_dates.txt",
        ["service_id", "date", "exception_type"],
        [["WKD", "20260430", 1]],
    )
    write_table(
        tmp_path,
        "transfers.txt",
        ["from_stop_id", "to_stop_id", "transfer_type", "min_transfer_time"],
        [["A", "B", 2, 180]],
    )
    return tmp_path
