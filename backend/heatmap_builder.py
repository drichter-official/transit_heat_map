from __future__ import annotations

from backend.models import Stop
from backend.router import WALK_SPEED_M_PER_SEC


def build_heatmap_points(
    best_arrival: dict[str, int],
    stops: dict[str, Stop],
    departure_sec: int,
    max_travel_sec: int,
    max_points: int = 5_000,
    connection_counts: dict[str, int] | None = None,
) -> list[dict[str, float]]:
    points: list[dict[str, float]] = []

    for stop_id, arrival_sec in sorted(best_arrival.items(), key=lambda item: item[1]):
        if stop_id not in stops:
            continue
        stop = stops[stop_id]
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
        if len(points) >= max_points:
            return points

    return points[:max_points]
