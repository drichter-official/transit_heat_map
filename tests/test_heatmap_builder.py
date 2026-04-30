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


def test_build_heatmap_points_caps_output(tiny_gtfs_dir):
    gtfs = load_gtfs(tiny_gtfs_dir)

    points = build_heatmap_points(
        best_arrival={"A": 8 * 3600, "B": 8 * 3600, "C": 8 * 3600},
        stops=gtfs.stops,
        departure_sec=8 * 3600,
        max_travel_sec=60 * 60,
        max_points=5,
    )

    assert len(points) == 5
