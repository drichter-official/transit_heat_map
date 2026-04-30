from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass(frozen=True)
class Stop:
    id: str
    name: str
    lat: float
    lon: float


@dataclass(frozen=True)
class StopTime:
    trip_id: str
    stop_id: str
    arrival_sec: int
    departure_sec: int
    stop_sequence: int


@dataclass(frozen=True)
class TripStop:
    trip_id: str
    stop_id: str
    arrival_sec: int
    departure_sec: int
    stop_sequence: int


@dataclass(frozen=True)
class Transfer:
    to_stop_id: str
    transfer_time_sec: int


@dataclass(frozen=True)
class ServiceCalendar:
    service_id: str
    start_date: date
    end_date: date
    monday: bool
    tuesday: bool
    wednesday: bool
    thursday: bool
    friday: bool
    saturday: bool
    sunday: bool


@dataclass
class GTFSData:
    stops: dict[str, Stop]
    stop_times_by_stop: dict[str, list[StopTime]]
    trip_stops: dict[str, list[TripStop]]
    trip_service_ids: dict[str, str]
    calendars: dict[str, ServiceCalendar]
    calendar_dates: dict[date, dict[str, int]]
    transfers: dict[str, list[Transfer]]
    approx_edges_by_stop: dict[str, list[tuple[str, int]]] = field(default_factory=dict)
    stop_id_order: list[str] = field(default_factory=list)
    stop_coordinates: Any = None
    stop_kdtree: Any = None
    walk_cache: dict[tuple[str, int], list[tuple[str, float]]] = field(default_factory=dict)


@dataclass(frozen=True)
class HeatmapPoint:
    lat: float
    lng: float
    weight: float


@dataclass
class JobRecord:
    id: str
    status: str
    quality: str | None = None
    points: list[HeatmapPoint] = field(default_factory=list)
    stop_count: int = 0
    computation_ms: int | None = None
    error: str | None = None
    warnings: list[str] = field(default_factory=list)
