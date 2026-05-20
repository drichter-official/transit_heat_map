from __future__ import annotations

import argparse
import json
import math
import shutil
from pathlib import Path
from typing import Any

from backend.gtfs_loader import load_gtfs, stops_within_radius_cached
from backend.models import GTFSData, Stop
from backend.router import MAX_WALK_TO_FIRST_STOP_M, MAX_WALK_TRANSFER_M, WALK_SPEED_M_PER_SEC

DEFAULT_DATA_DIR = Path("backend/data/filtered")
DEFAULT_OUTPUT_DIR = Path("static-data")
COORDINATE_PRECISION = 1_000_000
DEFAULT_GRID_DEGREES = 0.01
DEFAULT_SHARD_SIZE = 1024


def _dump_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def _quantize_coordinate(value: float) -> int:
    return round(value * COORDINATE_PRECISION)


def _dequantize_coordinate(value: int) -> float:
    return value / COORDINATE_PRECISION


def _grid_key(lat: float, lon: float, grid_degrees: float) -> str:
    return f"{math.floor(lat / grid_degrees)}:{math.floor(lon / grid_degrees)}"


def _bounds(stops: list[Stop]) -> dict[str, float]:
    lats = [stop.lat for stop in stops]
    lons = [stop.lon for stop in stops]
    return {
        "min_lat": round(min(lats), 6),
        "max_lat": round(max(lats), 6),
        "min_lon": round(min(lons), 6),
        "max_lon": round(max(lons), 6),
    }


def _default_center(bounds: dict[str, float]) -> list[float]:
    return [
        round((bounds["min_lat"] + bounds["max_lat"]) / 2, 6),
        round((bounds["min_lon"] + bounds["max_lon"]) / 2, 6),
    ]


def _build_search_index(
    stops: list[Stop],
    grid_degrees: float,
) -> dict[str, Any]:
    grid: dict[str, list[int]] = {}
    compact_stops = []

    for index, stop in enumerate(stops):
        compact_stops.append(
            [
                stop.id,
                stop.name,
                _quantize_coordinate(stop.lat),
                _quantize_coordinate(stop.lon),
                stop.name.casefold(),
            ]
        )
        grid.setdefault(_grid_key(stop.lat, stop.lon, grid_degrees), []).append(index)

    return {
        "v": 2,
        "coordinate_precision": COORDINATE_PRECISION,
        "grid_degrees": grid_degrees,
        "stops": compact_stops,
        "grid": dict(sorted(grid.items())),
    }


def _compact_ride_edges(gtfs: GTFSData, stop_id: str, stop_indexes: dict[str, int]) -> list[list[int]]:
    edges = []
    for next_stop_id, travel_sec in gtfs.approx_edges_by_stop.get(stop_id, []):
        if next_stop_id in stop_indexes:
            edges.append([stop_indexes[next_stop_id], int(travel_sec)])
    return edges


def _compact_walk_edges(gtfs: GTFSData, stop_id: str, stop_indexes: dict[str, int]) -> list[list[float]]:
    edges = []
    for next_stop_id, dist_m in stops_within_radius_cached(gtfs, stop_id, MAX_WALK_TRANSFER_M):
        if next_stop_id in stop_indexes:
            edges.append([stop_indexes[next_stop_id], round(float(dist_m), 1)])
    return edges


def _write_tiles(
    gtfs: GTFSData,
    stops: list[Stop],
    stop_indexes: dict[str, int],
    output_dir: Path,
    shard_size: int,
) -> list[dict[str, Any]]:
    tiles_dir = output_dir / "tiles"
    if tiles_dir.exists():
        shutil.rmtree(tiles_dir)
    tiles_dir.mkdir(parents=True, exist_ok=True)

    tiles = []
    for tile_id, start in enumerate(range(0, len(stops), shard_size)):
        tile_name = f"{tile_id:04d}.json"
        tile_path = tiles_dir / tile_name
        tile_stops = stops[start:start + shard_size]
        rows = [
            [
                _compact_ride_edges(gtfs, stop.id, stop_indexes),
                _compact_walk_edges(gtfs, stop.id, stop_indexes),
            ]
            for stop in tile_stops
        ]
        _dump_json(
            tile_path,
            {
                "v": 2,
                "start": start,
                "rows": rows,
            },
        )
        tiles.append(
            {
                "id": tile_id,
                "path": f"tiles/{tile_name}",
                "start": start,
                "end": start + len(tile_stops),
            }
        )
    return tiles


def export_static_network(
    data_dir: str | Path = DEFAULT_DATA_DIR,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    region: str = "switzerland",
    shard_size: int = DEFAULT_SHARD_SIZE,
    grid_degrees: float = DEFAULT_GRID_DEGREES,
) -> dict[str, Any]:
    if shard_size <= 0:
        raise ValueError("shard_size must be positive")

    gtfs = load_gtfs(data_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    stop_ids = gtfs.stop_id_order or list(gtfs.stops)
    stops = [gtfs.stops[stop_id] for stop_id in stop_ids]
    stop_indexes = {stop.id: index for index, stop in enumerate(stops)}
    network_bounds = _bounds(stops)
    search_index = _build_search_index(stops, grid_degrees)
    tiles = _write_tiles(gtfs, stops, stop_indexes, output_path, shard_size)

    manifest = {
        "v": 2,
        "region": region,
        "stop_count": len(stops),
        "shard_size": shard_size,
        "coordinate_precision": COORDINATE_PRECISION,
        "bounds": network_bounds,
        "default_center": _default_center(network_bounds),
        "constants": {
            "walk_mps": WALK_SPEED_M_PER_SEC,
            "first_walk_m": MAX_WALK_TO_FIRST_STOP_M,
            "transfer_walk_m": MAX_WALK_TRANSFER_M,
            "grid_degrees": grid_degrees,
        },
        "search_index": "search-index.json",
        "tiles": tiles,
    }
    _dump_json(output_path / "manifest.json", manifest)
    _dump_json(output_path / "search-index.json", search_index)

    return {
        "region": region,
        "stop_count": len(stops),
        "tile_count": len(tiles),
        "output_dir": str(output_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Export a compact static transit network.")
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--region", default="switzerland")
    parser.add_argument("--shard-size", type=int, default=DEFAULT_SHARD_SIZE)
    parser.add_argument("--grid-degrees", type=float, default=DEFAULT_GRID_DEGREES)
    args = parser.parse_args()

    summary = export_static_network(
        data_dir=Path(args.data_dir),
        output_dir=Path(args.output_dir),
        region=args.region,
        shard_size=args.shard_size,
        grid_degrees=args.grid_degrees,
    )
    print(
        f"Wrote {summary['stop_count']} stops in {summary['tile_count']} tiles "
        f"to {summary['output_dir']}"
    )


if __name__ == "__main__":
    main()
