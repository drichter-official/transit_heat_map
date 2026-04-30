from __future__ import annotations

import math

from backend.models import Stop
from backend.router import WALK_SPEED_M_PER_SEC

EARTH_RADIUS_M = 6_371_000
SAMPLE_POINTS_PER_STOP = 12


def build_heatmap_points(
    best_arrival: dict[str, int],
    stops: dict[str, Stop],
    departure_sec: int,
    max_travel_sec: int,
    max_points: int = 5_000,
) -> list[dict[str, float]]:
    points: list[dict[str, float]] = []

    for stop_id, arrival_sec in sorted(best_arrival.items(), key=lambda item: item[1]):
        if stop_id not in stops:
            continue
        stop = stops[stop_id]
        elapsed_sec = max(0, arrival_sec - departure_sec)
        remaining_sec = max(0, max_travel_sec - elapsed_sec)
        weight = 0 if max_travel_sec <= 0 else remaining_sec / max_travel_sec
        points.append({"lat": stop.lat, "lng": stop.lon, "weight": round(weight, 4)})

        walk_radius_m = remaining_sec * WALK_SPEED_M_PER_SEC
        if walk_radius_m < 50:
            continue

        dlat = (walk_radius_m / EARTH_RADIUS_M) * (180 / math.pi)
        dlon = dlat / max(0.2, math.cos(math.radians(stop.lat)))
        for r_frac in (0.5, 0.85, 1.0):
            n_samples = max(6, int(SAMPLE_POINTS_PER_STOP * r_frac))
            for index in range(n_samples):
                angle = 2 * math.pi * index / n_samples
                pt_lat = stop.lat + dlat * r_frac * math.sin(angle)
                pt_lon = stop.lon + dlon * r_frac * math.cos(angle)
                pt_weight = max(0, weight * (1 - 0.4 * r_frac))
                points.append({"lat": pt_lat, "lng": pt_lon, "weight": round(pt_weight, 4)})

    return points[:max_points]
