from datetime import datetime

import numpy as np
from scipy.spatial import cKDTree

from backend.gtfs_loader import get_active_trips, load_gtfs
from backend.models import GTFSData, Stop, StopTime, TripStop
from backend.router import (
    compute_approximate_reachability,
    compute_schedule_reachability,
    compute_window_normalized_reachability,
)


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


def test_window_normalized_reachability_subtracts_initial_wait_for_first_connection():
    stops = {
        "A": Stop(id="A", name="Alpha", lat=47.3760, lon=8.5410),
        "B": Stop(id="B", name="Beta", lat=47.5000, lon=8.8000),
    }
    coordinates = np.array([(stops["A"].lat, stops["A"].lon), (stops["B"].lat, stops["B"].lon)])
    gtfs = GTFSData(
        stops=stops,
        stop_times_by_stop={
            "A": [StopTime("T1", "A", 12 * 3600 + 30 * 60, 12 * 3600 + 30 * 60, 1)]
        },
        trip_stops={
            "T1": [
                TripStop("T1", "A", 12 * 3600 + 30 * 60, 12 * 3600 + 30 * 60, 1),
                TripStop("T1", "B", 13 * 3600, 13 * 3600, 2),
            ]
        },
        trip_service_ids={"T1": "WKD"},
        calendars={},
        calendar_dates={},
        transfers={},
        stop_id_order=["A", "B"],
        stop_coordinates=coordinates,
        stop_kdtree=cKDTree(coordinates),
    )

    best = compute_window_normalized_reachability(
        origin_lat=47.3760,
        origin_lon=8.5410,
        window_start_sec=12 * 3600,
        first_departure_window_sec=2 * 3600,
        max_travel_seconds=40 * 60,
        gtfs=gtfs,
        active_trips={"T1"},
    )

    assert best["B"] == 12 * 3600 + 30 * 60


def test_window_normalized_reachability_rejects_trips_longer_than_travel_limit():
    stops = {
        "A": Stop(id="A", name="Alpha", lat=47.3760, lon=8.5410),
        "B": Stop(id="B", name="Beta", lat=47.5000, lon=8.8000),
    }
    coordinates = np.array([(stops["A"].lat, stops["A"].lon), (stops["B"].lat, stops["B"].lon)])
    gtfs = GTFSData(
        stops=stops,
        stop_times_by_stop={
            "A": [StopTime("T1", "A", 12 * 3600 + 30 * 60, 12 * 3600 + 30 * 60, 1)]
        },
        trip_stops={
            "T1": [
                TripStop("T1", "A", 12 * 3600 + 30 * 60, 12 * 3600 + 30 * 60, 1),
                TripStop("T1", "B", 13 * 3600, 13 * 3600, 2),
            ]
        },
        trip_service_ids={"T1": "WKD"},
        calendars={},
        calendar_dates={},
        transfers={},
        stop_id_order=["A", "B"],
        stop_coordinates=coordinates,
        stop_kdtree=cKDTree(coordinates),
    )

    best = compute_window_normalized_reachability(
        origin_lat=47.3760,
        origin_lon=8.5410,
        window_start_sec=12 * 3600,
        first_departure_window_sec=2 * 3600,
        max_travel_seconds=20 * 60,
        gtfs=gtfs,
        active_trips={"T1"},
    )

    assert "B" not in best
