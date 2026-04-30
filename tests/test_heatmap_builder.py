from backend.gtfs_loader import load_gtfs
from backend.heatmap_builder import build_heatmap_points


def test_build_heatmap_points_weights_remaining_time(tiny_gtfs_dir):
    gtfs = load_gtfs(tiny_gtfs_dir)

    points = build_heatmap_points(
        best_arrival={"A": 8 * 3600, "B": 8 * 3600 + 15 * 60},
        stops=gtfs.stops,
        departure_sec=8 * 3600,
        max_travel_sec=30 * 60,
        max_points=200,
    )

    origin = points[0]
    assert origin["lat"] == gtfs.stops["A"].lat
    assert origin["lng"] == gtfs.stops["A"].lon
    assert origin["weight"] == 1.0
    assert any(point["weight"] < 1.0 for point in points)
    later = next(point for point in points if point["lat"] == gtfs.stops["B"].lat)
    assert later["radius_m"] == 1251.0


def test_build_heatmap_points_caps_output(tiny_gtfs_dir):
    gtfs = load_gtfs(tiny_gtfs_dir)

    points = build_heatmap_points(
        best_arrival={"A": 8 * 3600, "B": 8 * 3600, "C": 8 * 3600},
        stops=gtfs.stops,
        departure_sec=8 * 3600,
        max_travel_sec=60 * 60,
        max_points=5,
    )

    assert len(points) == 3


def test_build_heatmap_points_does_not_emit_ring_samples(tiny_gtfs_dir):
    gtfs = load_gtfs(tiny_gtfs_dir)
    stop_positions = {
        (round(stop.lat, 7), round(stop.lon, 7))
        for stop in gtfs.stops.values()
    }

    points = build_heatmap_points(
        best_arrival={"A": 8 * 3600, "B": 8 * 3600 + 15 * 60},
        stops=gtfs.stops,
        departure_sec=8 * 3600,
        max_travel_sec=30 * 60,
        max_points=200,
    )

    assert {
        (round(point["lat"], 7), round(point["lng"], 7))
        for point in points
    }.issubset(stop_positions)


def test_build_heatmap_points_ignores_connection_counts(tiny_gtfs_dir):
    gtfs = load_gtfs(tiny_gtfs_dir)

    points = build_heatmap_points(
        best_arrival={"A": 8 * 3600, "B": 8 * 3600},
        stops=gtfs.stops,
        departure_sec=8 * 3600,
        max_travel_sec=30 * 60,
        max_points=200,
        connection_counts={"A": 30, "B": 1},
    )

    assert len(points) == 2
