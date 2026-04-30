from __future__ import annotations

import heapq
from datetime import datetime

from backend.gtfs_loader import stops_within_radius, stops_within_radius_cached
from backend.models import GTFSData
from backend.time_utils import seconds_since_midnight

WALK_SPEED_M_PER_SEC = 1.39
MAX_WALK_TO_FIRST_STOP_M = 800
MAX_WALK_TRANSFER_M = 400


def _push_best(
    pq: list[tuple[float, str]],
    best: dict[str, float],
    stop_id: str,
    arrival_sec: float,
    deadline_sec: float,
) -> None:
    if arrival_sec <= deadline_sec and arrival_sec < best.get(stop_id, float("inf")):
        best[stop_id] = arrival_sec
        heapq.heappush(pq, (arrival_sec, stop_id))


def _seed_origin(
    origin_lat: float,
    origin_lon: float,
    departure_sec: int,
    deadline_sec: int,
    gtfs: GTFSData,
) -> tuple[list[tuple[float, str]], dict[str, float]]:
    pq: list[tuple[float, str]] = []
    best: dict[str, float] = {}
    for stop_id, dist_m in stops_within_radius(
        gtfs,
        origin_lat,
        origin_lon,
        MAX_WALK_TO_FIRST_STOP_M,
    ):
        _push_best(pq, best, stop_id, departure_sec + dist_m / WALK_SPEED_M_PER_SEC, deadline_sec)
    return pq, best


def compute_schedule_reachability(
    origin_lat: float,
    origin_lon: float,
    departure_datetime: datetime,
    max_travel_seconds: int,
    gtfs: GTFSData,
    active_trips: set[str],
) -> dict[str, int]:
    departure_sec = seconds_since_midnight(departure_datetime)
    deadline_sec = departure_sec + max_travel_seconds
    pq, best = _seed_origin(origin_lat, origin_lon, departure_sec, deadline_sec, gtfs)

    while pq:
        current_arrival, stop_id = heapq.heappop(pq)
        if current_arrival > best.get(stop_id, float("inf")):
            continue

        for transfer_stop_id, dist_m in stops_within_radius_cached(gtfs, stop_id, MAX_WALK_TRANSFER_M):
            _push_best(
                pq,
                best,
                transfer_stop_id,
                current_arrival + dist_m / WALK_SPEED_M_PER_SEC,
                deadline_sec,
            )

        for transfer in gtfs.transfers.get(stop_id, []):
            _push_best(
                pq,
                best,
                transfer.to_stop_id,
                current_arrival + transfer.transfer_time_sec,
                deadline_sec,
            )

        for board in gtfs.stop_times_by_stop.get(stop_id, []):
            if board.trip_id not in active_trips or board.departure_sec < current_arrival:
                continue
            for stop_entry in gtfs.trip_stops.get(board.trip_id, []):
                if stop_entry.stop_sequence <= board.stop_sequence:
                    continue
                if stop_entry.arrival_sec > deadline_sec:
                    break
                _push_best(pq, best, stop_entry.stop_id, stop_entry.arrival_sec, deadline_sec)

    return {stop_id: int(arrival) for stop_id, arrival in best.items()}


def compute_approximate_reachability(
    origin_lat: float,
    origin_lon: float,
    departure_sec: int,
    max_travel_seconds: int,
    gtfs: GTFSData,
) -> dict[str, int]:
    deadline_sec = departure_sec + max_travel_seconds
    pq, best = _seed_origin(origin_lat, origin_lon, departure_sec, deadline_sec, gtfs)

    while pq:
        current_arrival, stop_id = heapq.heappop(pq)
        if current_arrival > best.get(stop_id, float("inf")):
            continue

        for transfer_stop_id, dist_m in stops_within_radius_cached(gtfs, stop_id, MAX_WALK_TRANSFER_M):
            _push_best(
                pq,
                best,
                transfer_stop_id,
                current_arrival + dist_m / WALK_SPEED_M_PER_SEC,
                deadline_sec,
            )

        for board in gtfs.stop_times_by_stop.get(stop_id, []):
            for stop_entry in gtfs.trip_stops.get(board.trip_id, []):
                if stop_entry.stop_sequence <= board.stop_sequence:
                    continue
                travel_sec = max(60, stop_entry.arrival_sec - board.departure_sec)
                _push_best(pq, best, stop_entry.stop_id, current_arrival + travel_sec, deadline_sec)

    return {stop_id: int(arrival) for stop_id, arrival in best.items()}
