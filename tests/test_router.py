from datetime import datetime

import numpy as np
from scipy.spatial import cKDTree

from backend.gtfs_loader import get_active_trips, load_gtfs
from backend.models import GTFSData, Stop
from backend.router import compute_approximate_reachability, compute_schedule_reachability


def test_schedule_reachability_finds_direct_trip(tiny_gtfs_dir):
    gtfs = load_gtfs(tiny_gtfs_dir)
    active_trips = get_active_trips(gtfs, datetime(2026, 4, 30, 8, 0).date())

    best = compute_schedule_reachability(
        origin_lat=47.3760,
        origin_lon=8.5410,
        departure_datetime=datetime(2026, 4, 30, 8, 0),
        max_travel_seconds=30 * 60,
        gtfs=gtfs,
        active_trips=active_trips,
    )

    assert best["A"] == 8 * 3600
    assert "B" in best
    assert best["C"] == 8 * 3600 + 20 * 60


def test_schedule_reachability_respects_deadline(tiny_gtfs_dir):
    gtfs = load_gtfs(tiny_gtfs_dir)
    active_trips = get_active_trips(gtfs, datetime(2026, 4, 30, 8, 0).date())

    best = compute_schedule_reachability(
        origin_lat=47.3760,
        origin_lon=8.5410,
        departure_datetime=datetime(2026, 4, 30, 8, 0),
        max_travel_seconds=12 * 60,
        gtfs=gtfs,
        active_trips=active_trips,
    )

    assert "B" in best
    assert "C" not in best


def test_approximate_reachability_returns_fast_route_estimate(tiny_gtfs_dir):
    gtfs = load_gtfs(tiny_gtfs_dir)

    best = compute_approximate_reachability(
        origin_lat=47.3760,
        origin_lon=8.5410,
        departure_sec=8 * 3600,
        max_travel_seconds=30 * 60,
        gtfs=gtfs,
    )

    assert {"A", "B", "C"}.issubset(best)


def test_approximate_reachability_uses_fast_trip_edges():
    stops = {
        "A": Stop(id="A", name="Alpha", lat=47.3760, lon=8.5410),
        "B": Stop(id="B", name="Beta", lat=47.5000, lon=8.8000),
    }
    stop_id_order = ["A", "B"]
    coordinates = np.array([(stops[stop_id].lat, stops[stop_id].lon) for stop_id in stop_id_order])
    gtfs = GTFSData(
        stops=stops,
        stop_times_by_stop={},
        trip_stops={},
        trip_service_ids={},
        calendars={},
        calendar_dates={},
        transfers={},
        approx_edges_by_stop={"A": [("B", 300)]},
        stop_id_order=stop_id_order,
        stop_coordinates=coordinates,
        stop_kdtree=cKDTree(coordinates),
    )

    best = compute_approximate_reachability(
        origin_lat=47.3760,
        origin_lon=8.5410,
        departure_sec=8 * 3600,
        max_travel_seconds=10 * 60,
        gtfs=gtfs,
    )

    assert best["B"] == 8 * 3600 + 300
