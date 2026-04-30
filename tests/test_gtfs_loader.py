from datetime import date

from backend.gtfs_loader import get_active_trips, load_gtfs, stops_within_radius, stops_within_radius_cached


def test_load_gtfs_builds_stop_and_trip_indexes(tiny_gtfs_dir):
    gtfs = load_gtfs(tiny_gtfs_dir)

    assert gtfs.stops["A"].name == "Zurich Alpha"
    assert [entry.stop_id for entry in gtfs.trip_stops["T1"]] == ["A", "B", "C"]
    assert [entry.trip_id for entry in gtfs.stop_times_by_stop["A"]] == ["T2", "T1"]
    assert [entry.departure_sec for entry in gtfs.stop_times_by_stop["A"]] == [28200, 28800]


def test_get_active_trips_uses_active_services(tiny_gtfs_dir):
    gtfs = load_gtfs(tiny_gtfs_dir)

    assert get_active_trips(gtfs, date(2026, 4, 30)) == {"T1", "T2"}
    assert get_active_trips(gtfs, date(2026, 5, 1)) == set()


def test_load_gtfs_skips_forbidden_transfers(tiny_gtfs_dir):
    gtfs = load_gtfs(tiny_gtfs_dir)

    assert [(transfer.to_stop_id, transfer.transfer_time_sec) for transfer in gtfs.transfers["A"]] == [
        ("B", 180)
    ]


def test_spatial_lookup_finds_nearby_stops(tiny_gtfs_dir):
    gtfs = load_gtfs(tiny_gtfs_dir)

    nearby = stops_within_radius(gtfs, 47.3760, 8.5410, 100)
    assert nearby[0][0] == "A"
    assert nearby[0][1] < 1


def test_spatial_lookup_prefilter_includes_longitude_nearby_stops(tiny_gtfs_dir):
    gtfs = load_gtfs(tiny_gtfs_dir)

    nearby = stops_within_radius(gtfs, 47.3760, 8.5410, 600)

    assert any(stop_id == "D" for stop_id, _ in nearby)


def test_cached_stop_lookup_uses_stop_id(tiny_gtfs_dir):
    gtfs = load_gtfs(tiny_gtfs_dir)

    first = stops_within_radius_cached(gtfs, "A", 600)
    second = stops_within_radius_cached(gtfs, "A", 600)

    assert first == second
    assert any(stop_id == "B" for stop_id, _ in first)
