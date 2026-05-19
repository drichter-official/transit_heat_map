from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.gtfs_loader import load_gtfs, stops_within_radius_cached
from backend.models import GTFSData
from backend.router import MAX_WALK_TO_FIRST_STOP_M, MAX_WALK_TRANSFER_M, WALK_SPEED_M_PER_SEC

STATIC_SCHEMA_VERSION = 1
GRID_DEGREES = 0.01
DEFAULT_DATA_DIR = Path("backend/data/filtered")
DEFAULT_OUTPUT_PATH = Path("frontend/static-data/transit-network.json")


def _grid_key(lat: float, lon: float) -> str:
    return f"{int(lat // GRID_DEGREES)}:{int(lon // GRID_DEGREES)}"


def _stop_tuple(stop_id: str, gtfs: GTFSData) -> list[object]:
    stop = gtfs.stops[stop_id]
    return [
        stop.id,
        stop.name,
        round(stop.lat, 7),
        round(stop.lon, 7),
        stop.name.casefold(),
    ]


def _default_center(gtfs: GTFSData) -> list[float]:
    if not gtfs.stops:
        return [0, 0]
    lat = sum(stop.lat for stop in gtfs.stops.values()) / len(gtfs.stops)
    lon = sum(stop.lon for stop in gtfs.stops.values()) / len(gtfs.stops)
    return [round(lat, 4), round(lon, 4)]


def _build_grid(stop_ids: list[str], gtfs: GTFSData) -> dict[str, list[int]]:
    grid: dict[str, list[int]] = {}
    for index, stop_id in enumerate(stop_ids):
        stop = gtfs.stops[stop_id]
        grid.setdefault(_grid_key(stop.lat, stop.lon), []).append(index)
    return dict(sorted(grid.items()))


def _build_ride_edges(stop_ids: list[str], gtfs: GTFSData) -> list[list[list[int]]]:
    index_by_stop_id = {stop_id: index for index, stop_id in enumerate(stop_ids)}
    edges: list[list[list[int]]] = []
    for stop_id in stop_ids:
        edges.append(
            [
                [index_by_stop_id[to_stop_id], int(travel_sec)]
                for to_stop_id, travel_sec in gtfs.approx_edges_by_stop.get(stop_id, [])
                if to_stop_id in index_by_stop_id
            ]
        )
    return edges


def _build_walk_edges(stop_ids: list[str], gtfs: GTFSData) -> list[list[list[float]]]:
    index_by_stop_id = {stop_id: index for index, stop_id in enumerate(stop_ids)}
    edges: list[list[list[float]]] = []
    for stop_id in stop_ids:
        edges.append(
            [
                [index_by_stop_id[to_stop_id], round(dist_m, 1)]
                for to_stop_id, dist_m in stops_within_radius_cached(gtfs, stop_id, MAX_WALK_TRANSFER_M)
                if to_stop_id in index_by_stop_id
            ]
        )
    return edges


def build_static_network(gtfs: GTFSData) -> dict[str, object]:
    stop_ids = list(gtfs.stop_id_order or gtfs.stops)
    return {
        "v": STATIC_SCHEMA_VERSION,
        "constants": {
            "walk_mps": WALK_SPEED_M_PER_SEC,
            "first_walk_m": MAX_WALK_TO_FIRST_STOP_M,
            "transfer_walk_m": MAX_WALK_TRANSFER_M,
            "grid_degrees": GRID_DEGREES,
        },
        "default_center": _default_center(gtfs),
        "stops": [_stop_tuple(stop_id, gtfs) for stop_id in stop_ids],
        "grid": _build_grid(stop_ids, gtfs),
        "ride_edges": _build_ride_edges(stop_ids, gtfs),
        "walk_edges": _build_walk_edges(stop_ids, gtfs),
    }


def write_static_network(gtfs: GTFSData, output_path: Path = DEFAULT_OUTPUT_PATH) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_static_network(gtfs)
    output_path.write_text(
        json.dumps(payload, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Export a compact static transit network for GitHub Pages.")
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH))
    args = parser.parse_args()

    output = write_static_network(load_gtfs(Path(args.data_dir)), Path(args.output))
    print(f"Wrote static transit network to {output}")


if __name__ == "__main__":
    main()
