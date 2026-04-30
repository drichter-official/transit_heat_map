from __future__ import annotations

from collections import defaultdict
from datetime import date
from math import asin, cos, radians, sin, sqrt
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from backend.models import GTFSData, ServiceCalendar, Stop, StopTime, Transfer, TripStop
from backend.time_utils import active_service_ids, parse_gtfs_date, parse_gtfs_time

EARTH_RADIUS_M = 6_371_000


def _read_csv(data_dir: Path, name: str, required: bool = True) -> pd.DataFrame:
    path = data_dir / name
    if not path.exists():
        if required:
            raise FileNotFoundError(f"Missing GTFS file: {path}")
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str).fillna("")


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * asin(sqrt(a))


def load_gtfs(data_dir: str | Path) -> GTFSData:
    data_path = Path(data_dir)
    stops_df = _read_csv(data_path, "stops.txt")
    trips_df = _read_csv(data_path, "trips.txt")
    stop_times_df = _read_csv(data_path, "stop_times.txt")
    calendar_df = _read_csv(data_path, "calendar.txt", required=False)
    calendar_dates_df = _read_csv(data_path, "calendar_dates.txt", required=False)
    transfers_df = _read_csv(data_path, "transfers.txt", required=False)

    stops = {
        row.stop_id: Stop(
            id=row.stop_id,
            name=row.stop_name,
            lat=float(row.stop_lat),
            lon=float(row.stop_lon),
        )
        for row in stops_df.itertuples(index=False)
    }

    trip_service_ids = {row.trip_id: row.service_id for row in trips_df.itertuples(index=False)}

    stop_times_by_stop: dict[str, list[StopTime]] = defaultdict(list)
    trip_stops: dict[str, list[TripStop]] = defaultdict(list)
    for row in stop_times_df.itertuples(index=False):
        if not row.arrival_time.strip() or not row.departure_time.strip():
            continue
        arrival_sec = parse_gtfs_time(row.arrival_time)
        departure_sec = parse_gtfs_time(row.departure_time)
        stop_sequence = int(row.stop_sequence)
        stop_time = StopTime(
            trip_id=row.trip_id,
            stop_id=row.stop_id,
            arrival_sec=arrival_sec,
            departure_sec=departure_sec,
            stop_sequence=stop_sequence,
        )
        trip_stop = TripStop(
            trip_id=row.trip_id,
            stop_id=row.stop_id,
            arrival_sec=arrival_sec,
            departure_sec=departure_sec,
            stop_sequence=stop_sequence,
        )
        stop_times_by_stop[row.stop_id].append(stop_time)
        trip_stops[row.trip_id].append(trip_stop)

    for entries in stop_times_by_stop.values():
        entries.sort(key=lambda entry: (entry.departure_sec, entry.trip_id, entry.stop_sequence))
    for entries in trip_stops.values():
        entries.sort(key=lambda entry: entry.stop_sequence)

    approx_edge_best: dict[str, dict[str, int]] = defaultdict(dict)
    for entries in trip_stops.values():
        previous: TripStop | None = None
        for entry in entries:
            if previous is not None:
                travel_sec = entry.arrival_sec - previous.departure_sec
                if travel_sec >= 0:
                    travel_sec = max(60, travel_sec)
                    by_destination = approx_edge_best[previous.stop_id]
                    if travel_sec < by_destination.get(entry.stop_id, travel_sec + 1):
                        by_destination[entry.stop_id] = travel_sec
            previous = entry
    approx_edges_by_stop = {
        stop_id: sorted(edges.items(), key=lambda item: (item[1], item[0]))
        for stop_id, edges in approx_edge_best.items()
    }

    calendars: dict[str, ServiceCalendar] = {}
    if not calendar_df.empty:
        for row in calendar_df.itertuples(index=False):
            calendars[row.service_id] = ServiceCalendar(
                service_id=row.service_id,
                start_date=parse_gtfs_date(row.start_date),
                end_date=parse_gtfs_date(row.end_date),
                monday=row.monday == "1",
                tuesday=row.tuesday == "1",
                wednesday=row.wednesday == "1",
                thursday=row.thursday == "1",
                friday=row.friday == "1",
                saturday=row.saturday == "1",
                sunday=row.sunday == "1",
            )

    calendar_dates: dict[date, dict[str, int]] = defaultdict(dict)
    if not calendar_dates_df.empty:
        for row in calendar_dates_df.itertuples(index=False):
            calendar_dates[parse_gtfs_date(row.date)][row.service_id] = int(row.exception_type)

    transfers: dict[str, list[Transfer]] = defaultdict(list)
    if not transfers_df.empty:
        for row in transfers_df.itertuples(index=False):
            if row.transfer_type == "3":
                continue
            if row.from_stop_id in stops and row.to_stop_id in stops:
                transfer_time = int(row.min_transfer_time or "120")
                transfers[row.from_stop_id].append(
                    Transfer(to_stop_id=row.to_stop_id, transfer_time_sec=transfer_time)
                )

    stop_id_order = list(stops)
    coordinates = np.array([(stops[stop_id].lat, stops[stop_id].lon) for stop_id in stop_id_order])
    stop_kdtree = cKDTree(coordinates) if len(coordinates) else None

    return GTFSData(
        stops=stops,
        stop_times_by_stop=dict(stop_times_by_stop),
        trip_stops=dict(trip_stops),
        trip_service_ids=trip_service_ids,
        calendars=calendars,
        calendar_dates=dict(calendar_dates),
        transfers=dict(transfers),
        approx_edges_by_stop=approx_edges_by_stop,
        stop_id_order=stop_id_order,
        stop_coordinates=coordinates,
        stop_kdtree=stop_kdtree,
    )


def get_active_trips(gtfs: GTFSData, service_date: date) -> set[str]:
    services = active_service_ids(gtfs.calendars, gtfs.calendar_dates, service_date)
    return {
        trip_id
        for trip_id, service_id in gtfs.trip_service_ids.items()
        if service_id in services
    }


def stops_within_radius(
    gtfs: GTFSData,
    lat: float,
    lon: float,
    radius_m: float,
) -> list[tuple[str, float]]:
    if gtfs.stop_kdtree is None:
        return []
    radius_degrees = radius_m / 70_000
    indexes = gtfs.stop_kdtree.query_ball_point([lat, lon], radius_degrees)
    results = []
    for index in indexes:
        stop_id = gtfs.stop_id_order[index]
        stop = gtfs.stops[stop_id]
        dist_m = _distance_m(lat, lon, stop.lat, stop.lon)
        if dist_m <= radius_m:
            results.append((stop_id, dist_m))
    return sorted(results, key=lambda item: item[1])


def stops_within_radius_cached(gtfs: GTFSData, stop_id: str, radius_m: int) -> list[tuple[str, float]]:
    key = (stop_id, radius_m)
    if key not in gtfs.walk_cache:
        stop = gtfs.stops[stop_id]
        gtfs.walk_cache[key] = [
            item
            for item in stops_within_radius(gtfs, stop.lat, stop.lon, radius_m)
            if item[0] != stop_id
        ]
    return gtfs.walk_cache[key]
