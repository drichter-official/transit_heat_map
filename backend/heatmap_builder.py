from __future__ import annotations

from backend.models import Stop
from backend.router import WALK_SPEED_M_PER_SEC


def build_heatmap_points(
    best_arrival: dict[str, int],
    stops: dict[str, Stop],
    departure_sec: int,
    max_travel_sec: int,
    max_points: int | None = 5_000,
    connection_counts: dict[str, int] | None = None,
) -> list[dict[str, float]]:
    points: list[dict[str, float]] = []
    best_by_coordinate: dict[tuple[float, float], int] = {}

    for stop_id, arrival_sec in sorted(best_arrival.items(), key=lambda item: item[1]):
        if stop_id not in stops:
            continue
        stop = stops[stop_id]
        coordinate_key = (round(stop.lat, 7), round(stop.lon, 7))
        if coordinate_key in best_by_coordinate:
            continue
        best_by_coordinate[coordinate_key] = arrival_sec
        elapsed_sec = max(0, arrival_sec - departure_sec)
        remaining_sec = max(0, max_travel_sec - elapsed_sec)
        weight = 0 if max_travel_sec <= 0 else remaining_sec / max_travel_sec
        points.append(
            {
                "lat": stop.lat,
                "lng": stop.lon,
                "weight": round(weight, 4),
                "radius_m": round(remaining_sec * WALK_SPEED_M_PER_SEC, 1),
            }
        )
        if max_points is not None and len(points) >= max_points:
            return points

    return points if max_points is None else points[:max_points]
