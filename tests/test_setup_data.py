from pathlib import Path

import pandas as pd

from backend.setup_data import Bounds, filter_gtfs
from tests.helpers import write_table


def test_filter_gtfs_keeps_consistent_zurich_subset(tmp_path: Path):
    raw = tmp_path / "raw"
    out = tmp_path / "filtered"
    raw.mkdir()

    write_table(
        raw,
        "agency.txt",
        ["agency_id", "agency_name", "agency_url", "agency_timezone"],
        [["AG1", "Agency 1", "https://example.test", "Europe/Zurich"]],
    )
    write_table(
        raw,
        "stops.txt",
        ["stop_id", "stop_name", "stop_lat", "stop_lon"],
        [
            ["A", "Inside A", 47.37, 8.54],
            ["B", "Inside B", 47.38, 8.55],
            ["X", "Outside X", 46.00, 7.00],
        ],
    )
    write_table(
        raw,
        "routes.txt",
        ["route_id", "agency_id", "route_short_name", "route_long_name", "route_type"],
        [["R1", "AG1", "1", "Route 1", 3], ["RX", "AG1", "X", "Route X", 3]],
    )
    write_table(
        raw,
        "trips.txt",
        ["route_id", "service_id", "trip_id"],
        [["R1", "WKD", "T1"], ["RX", "WKD", "TX"]],
    )
    write_table(
        raw,
        "stop_times.txt",
        ["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"],
        [
            ["T1", "08:00:00", "08:00:00", "A", 1],
            ["T1", "08:05:00", "08:05:00", "B", 2],
            ["TX", "08:00:00", "08:00:00", "X", 1],
        ],
    )
    write_table(
        raw,
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
    write_table(raw, "calendar_dates.txt", ["service_id", "date", "exception_type"], [["WKD", "20260430", 1]])
    write_table(raw, "transfers.txt", ["from_stop_id", "to_stop_id", "transfer_type", "min_transfer_time"], [["A", "B", 2, 120], ["A", "X", 2, 120]])

    filter_gtfs(raw, out, Bounds(min_lat=47.0, max_lat=48.0, min_lon=8.0, max_lon=9.0))

    stops = pd.read_csv(out / "stops.txt")
    trips = pd.read_csv(out / "trips.txt")
    stop_times = pd.read_csv(out / "stop_times.txt")
    transfers = pd.read_csv(out / "transfers.txt")

    assert set(stops.stop_id) == {"A", "B"}
    assert set(trips.trip_id) == {"T1"}
    assert set(stop_times.stop_id) == {"A", "B"}
    assert set(transfers.to_stop_id) == {"B"}
