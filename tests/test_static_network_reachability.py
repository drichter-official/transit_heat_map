import heapq
import json
import math
import re
from pathlib import Path


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth_radius_m = 6_371_000
    to_rad = math.pi / 180
    dlat = (lat2 - lat1) * to_rad
    dlon = (lon2 - lon1) * to_rad
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1 * to_rad) * math.cos(lat2 * to_rad) * math.sin(dlon / 2) ** 2
    return 2 * earth_radius_m * math.asin(math.sqrt(a))


def _frontend_static_point_limit() -> int:
    js = Path("frontend/app.js").read_text(encoding="utf-8")
    constant = re.search(r"STATIC_HEATMAP_POINT_LIMIT\s*=\s*(\d+)", js)
    if constant:
        return int(constant.group(1))
    legacy_slice = re.search(r"points\.slice\(0,\s*(\d+)\)", js)
    if legacy_slice:
        return int(legacy_slice.group(1))
    raise AssertionError("Could not find frontend static heatmap point limit")


def test_static_switzerland_render_limit_includes_landquart_from_zurich_hb():
    base = Path("static-data")
    manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
    search = json.loads((base / "search-index.json").read_text(encoding="utf-8"))
    precision = manifest["coordinate_precision"]
    stops = [
        {
            "index": index,
            "id": stop[0],
            "name": stop[1],
            "lat": stop[2] / precision,
            "lon": stop[3] / precision,
        }
        for index, stop in enumerate(search["stops"])
    ]
    stop_by_id = {stop["id"]: stop for stop in stops}
    origin = stop_by_id["8503000"]
    target = stop_by_id["8509002"]
    max_travel_sec = 90 * 60
    tile_cache = {}

    def edges_for_stop(stop_index: int):
        tile_index = stop_index // manifest["shard_size"]
        if tile_index not in tile_cache:
            tile = manifest["tiles"][tile_index]
            tile_cache[tile_index] = json.loads((base / tile["path"]).read_text(encoding="utf-8"))
        tile = tile_cache[tile_index]
        return tile["rows"][stop_index - tile["start"]]

    best = [math.inf] * len(stops)
    heap = []
    for stop in stops:
        distance_m = _distance_m(origin["lat"], origin["lon"], stop["lat"], stop["lon"])
        if distance_m <= manifest["constants"]["first_walk_m"]:
            elapsed_sec = distance_m / manifest["constants"]["walk_mps"]
            best[stop["index"]] = elapsed_sec
            heapq.heappush(heap, (elapsed_sec, stop["index"]))

    while heap:
        elapsed_sec, stop_index = heapq.heappop(heap)
        if elapsed_sec > best[stop_index]:
            continue
        ride_edges, walk_edges = edges_for_stop(stop_index)
        for next_stop_index, distance_m in walk_edges:
            next_elapsed_sec = elapsed_sec + distance_m / manifest["constants"]["walk_mps"]
            if next_elapsed_sec <= max_travel_sec and next_elapsed_sec < best[next_stop_index]:
                best[next_stop_index] = next_elapsed_sec
                heapq.heappush(heap, (next_elapsed_sec, next_stop_index))
        for next_stop_index, travel_sec in ride_edges:
            next_elapsed_sec = elapsed_sec + travel_sec
            if next_elapsed_sec <= max_travel_sec and next_elapsed_sec < best[next_stop_index]:
                best[next_stop_index] = next_elapsed_sec
                heapq.heappush(heap, (next_elapsed_sec, next_stop_index))

    rendered_rank = None
    seen_coordinates = set()
    rank = 0
    for elapsed_sec, stop_index in sorted((elapsed, index) for index, elapsed in enumerate(best) if math.isfinite(elapsed)):
        stop = stops[stop_index]
        coordinate_key = (round(stop["lat"], 7), round(stop["lon"], 7))
        if coordinate_key in seen_coordinates:
            continue
        seen_coordinates.add(coordinate_key)
        rank += 1
        if stop["id"] == target["id"]:
            rendered_rank = rank
            break

    assert best[target["index"]] <= max_travel_sec
    assert rendered_rank is not None
    assert rendered_rank <= _frontend_static_point_limit()
