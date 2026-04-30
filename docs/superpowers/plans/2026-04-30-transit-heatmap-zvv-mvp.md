# Transit Heatmap ZVV MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local Leaflet/FastAPI transit reachability heatmap for ZVV/Zurich with progressive approximate-then-refined results.

**Architecture:** The backend is a small FastAPI service that loads a filtered GTFS feed, returns approximate heatmap points immediately, and stores in-memory refinement jobs for schedule-quality routing. The frontend is a vanilla JavaScript Leaflet app using OpenStreetMap tiles and a heatmap layer. Data setup is a local command that downloads Swiss GTFS and writes a Zurich-area subset.

**Tech Stack:** Python 3.11, FastAPI, Uvicorn, pandas, numpy, scipy cKDTree, pytest, vanilla HTML/CSS/JavaScript, Leaflet, leaflet.heat.

---

## File Structure

- `requirements.txt`: runtime and test dependencies.
- `pyproject.toml`: pytest configuration and package metadata.
- `README.md`: local setup, data setup, test, and run instructions.
- `backend/__init__.py`: backend package marker.
- `backend/models.py`: dataclasses shared by loader, router, heatmap builder, and API.
- `backend/time_utils.py`: GTFS time parsing and service-calendar logic.
- `backend/gtfs_loader.py`: parse filtered GTFS files into in-memory indexes and spatial lookup helpers.
- `backend/setup_data.py`: download Swiss GTFS, extract it, filter to Zurich/ZVV scope, and write local files.
- `backend/router.py`: approximate reachability and refined time-dependent GTFS routing.
- `backend/heatmap_builder.py`: convert reachability into weighted heatmap points with walking halos.
- `backend/main.py`: app factory, routes, job store, background refinement, and static frontend serving.
- `frontend/index.html`: map app shell and external Leaflet assets.
- `frontend/app.js`: stop search, origin selection, heatmap requests, polling, and layer replacement.
- `frontend/style.css`: compact control panel and responsive map layout.
- `tests/__init__.py`: test package marker.
- `tests/helpers.py`: shared file-writing helper for synthetic GTFS fixtures.
- `tests/conftest.py`: shared tiny GTFS fixture.
- `tests/test_models.py`: dataclass sanity tests.
- `tests/test_time_utils.py`: GTFS time and calendar tests.
- `tests/test_gtfs_loader.py`: loader/index/spatial lookup tests.
- `tests/test_setup_data.py`: filter consistency tests with tiny GTFS input.
- `tests/test_router.py`: routing tests over synthetic GTFS.
- `tests/test_heatmap_builder.py`: heatmap weighting and cap tests.
- `tests/test_api.py`: API and background job state tests.
- `tests/test_frontend_assets.py`: static frontend contract checks.

---

### Task 1: Project Scaffold And Shared Models

**Files:**
- Create: `requirements.txt`
- Create: `pyproject.toml`
- Create: `backend/__init__.py`
- Create: `backend/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write the failing model test**

Create `tests/test_models.py`:

```python
from backend.models import HeatmapPoint, JobRecord, Stop, StopTime, Transfer, TripStop


def test_stop_time_and_trip_stop_fields_are_numeric():
    stop_time = StopTime(
        trip_id="trip-1",
        stop_id="stop-a",
        arrival_sec=8 * 3600 + 60,
        departure_sec=8 * 3600 + 120,
        stop_sequence=2,
    )
    trip_stop = TripStop(
        trip_id="trip-1",
        stop_id="stop-b",
        arrival_sec=8 * 3600 + 600,
        departure_sec=8 * 3600 + 660,
        stop_sequence=3,
    )

    assert stop_time.departure_sec == 28920
    assert trip_stop.arrival_sec == 29400


def test_shared_models_hold_api_shapes():
    stop = Stop(id="8503000", name="Zurich HB", lat=47.378, lon=8.54)
    transfer = Transfer(to_stop_id="8503001", transfer_time_sec=120)
    point = HeatmapPoint(lat=47.378, lng=8.54, weight=0.8)
    job = JobRecord(id="hm_test", status="running")

    assert stop.name == "Zurich HB"
    assert transfer.transfer_time_sec == 120
    assert point.weight == 0.8
    assert job.status == "running"
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
pytest tests/test_models.py -v
```

Expected: fail with `ModuleNotFoundError: No module named 'backend.models'`.

- [ ] **Step 3: Add dependencies, pytest config, package marker, and models**

Create `requirements.txt`:

```text
fastapi>=0.110.0
uvicorn[standard]>=0.29.0
pandas>=2.2.0
numpy>=1.26.0
scipy>=1.12.0
python-dateutil>=2.9.0
pytest>=8.0.0
httpx>=0.27.0
```

Create `pyproject.toml`:

```toml
[project]
name = "transit-heat-map"
version = "0.1.0"
requires-python = ">=3.11"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

Create `backend/__init__.py`:

```python
"""Transit heatmap backend package."""
```

Create `backend/models.py`:

```python
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
```

- [ ] **Step 4: Run the model test to verify it passes**

Run:

```powershell
pytest tests/test_models.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

Run:

```powershell
git add requirements.txt pyproject.toml backend/__init__.py backend/models.py tests/test_models.py
git commit -m "feat: add project scaffold and shared models"
```

Expected: commit succeeds.

---

### Task 2: GTFS Time And Calendar Utilities

**Files:**
- Create: `backend/time_utils.py`
- Create: `tests/test_time_utils.py`

- [ ] **Step 1: Write failing tests for time parsing and service activation**

Create `tests/test_time_utils.py`:

```python
from datetime import date, datetime

from backend.models import ServiceCalendar
from backend.time_utils import active_service_ids, parse_gtfs_date, parse_gtfs_time, seconds_since_midnight


def test_parse_gtfs_time_handles_overnight_values():
    assert parse_gtfs_time("08:30:15") == 30615
    assert parse_gtfs_time("25:30:00") == 91800


def test_seconds_since_midnight_uses_local_clock_time():
    assert seconds_since_midnight(datetime(2026, 4, 30, 8, 5, 7)) == 29107


def test_parse_gtfs_date_reads_compact_date():
    assert parse_gtfs_date("20260430") == date(2026, 4, 30)


def test_active_service_ids_applies_weekday_and_exceptions():
    weekday = ServiceCalendar(
        service_id="weekday",
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 30),
        monday=True,
        tuesday=True,
        wednesday=True,
        thursday=True,
        friday=True,
        saturday=False,
        sunday=False,
    )
    weekend = ServiceCalendar(
        service_id="weekend",
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 30),
        monday=False,
        tuesday=False,
        wednesday=False,
        thursday=False,
        friday=False,
        saturday=True,
        sunday=True,
    )

    active = active_service_ids(
        {"weekday": weekday, "weekend": weekend},
        {date(2026, 4, 30): {"weekday": 2, "weekend": 1}},
        date(2026, 4, 30),
    )

    assert active == {"weekend"}
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
pytest tests/test_time_utils.py -v
```

Expected: fail with `ModuleNotFoundError: No module named 'backend.time_utils'`.

- [ ] **Step 3: Implement the utility module**

Create `backend/time_utils.py`:

```python
from __future__ import annotations

from datetime import date, datetime

from backend.models import ServiceCalendar


def parse_gtfs_time(value: str) -> int:
    parts = value.strip().split(":")
    if len(parts) != 3:
        raise ValueError(f"Invalid GTFS time: {value!r}")
    hours, minutes, seconds = (int(part) for part in parts)
    if minutes < 0 or minutes > 59 or seconds < 0 or seconds > 59:
        raise ValueError(f"Invalid GTFS time: {value!r}")
    return hours * 3600 + minutes * 60 + seconds


def seconds_since_midnight(value: datetime) -> int:
    return value.hour * 3600 + value.minute * 60 + value.second


def parse_gtfs_date(value: str) -> date:
    return datetime.strptime(value.strip(), "%Y%m%d").date()


def _calendar_matches_day(calendar: ServiceCalendar, service_date: date) -> bool:
    if service_date < calendar.start_date or service_date > calendar.end_date:
        return False
    weekday = service_date.weekday()
    return (
        (weekday == 0 and calendar.monday)
        or (weekday == 1 and calendar.tuesday)
        or (weekday == 2 and calendar.wednesday)
        or (weekday == 3 and calendar.thursday)
        or (weekday == 4 and calendar.friday)
        or (weekday == 5 and calendar.saturday)
        or (weekday == 6 and calendar.sunday)
    )


def active_service_ids(
    calendars: dict[str, ServiceCalendar],
    calendar_dates: dict[date, dict[str, int]],
    service_date: date,
) -> set[str]:
    active = {
        service_id
        for service_id, calendar in calendars.items()
        if _calendar_matches_day(calendar, service_date)
    }
    for service_id, exception_type in calendar_dates.get(service_date, {}).items():
        if exception_type == 1:
            active.add(service_id)
        elif exception_type == 2:
            active.discard(service_id)
    return active
```

- [ ] **Step 4: Run the time utility tests**

Run:

```powershell
pytest tests/test_time_utils.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

Run:

```powershell
git add backend/time_utils.py tests/test_time_utils.py
git commit -m "feat: add GTFS time and calendar utilities"
```

Expected: commit succeeds.

---

### Task 3: GTFS Loader And Spatial Lookups

**Files:**
- Create: `tests/conftest.py`
- Create: `tests/__init__.py`
- Create: `tests/helpers.py`
- Create: `backend/gtfs_loader.py`
- Create: `tests/test_gtfs_loader.py`

- [ ] **Step 1: Add tiny GTFS fixture helpers**

Create `tests/__init__.py`:

```python
"""Test package for transit heatmap."""
```

Create `tests/helpers.py`:

```python
from __future__ import annotations

from pathlib import Path


def write_table(path: Path, name: str, header: list[str], rows: list[list[object]]) -> None:
    lines = [",".join(header)]
    for row in rows:
        lines.append(",".join(str(value) for value in row))
    path.joinpath(name).write_text("\n".join(lines) + "\n", encoding="utf-8")
```

Create `tests/conftest.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers import write_table


@pytest.fixture
def tiny_gtfs_dir(tmp_path: Path) -> Path:
    write_table(
        tmp_path,
        "stops.txt",
        ["stop_id", "stop_name", "stop_lat", "stop_lon"],
        [
            ["A", "Zurich Alpha", 47.3760, 8.5410],
            ["B", "Zurich Beta", 47.3770, 8.5450],
            ["C", "Zurich Gamma", 47.3800, 8.5500],
        ],
    )
    write_table(
        tmp_path,
        "trips.txt",
        ["route_id", "service_id", "trip_id"],
        [["R1", "WKD", "T1"]],
    )
    write_table(
        tmp_path,
        "stop_times.txt",
        ["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"],
        [
            ["T1", "08:00:00", "08:00:00", "A", 1],
            ["T1", "08:10:00", "08:10:00", "B", 2],
            ["T1", "08:20:00", "08:20:00", "C", 3],
        ],
    )
    write_table(
        tmp_path,
        "calendar.txt",
        [
            "service_id",
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
            "start_date",
            "end_date",
        ],
        [["WKD", 1, 1, 1, 1, 1, 0, 0, "20260401", "20260430"]],
    )
    write_table(
        tmp_path,
        "calendar_dates.txt",
        ["service_id", "date", "exception_type"],
        [["WKD", "20260430", 1]],
    )
    write_table(
        tmp_path,
        "transfers.txt",
        ["from_stop_id", "to_stop_id", "transfer_type", "min_transfer_time"],
        [["A", "B", 2, 180]],
    )
    return tmp_path
```

- [ ] **Step 2: Write failing loader tests**

Create `tests/test_gtfs_loader.py`:

```python
from datetime import date

from backend.gtfs_loader import get_active_trips, load_gtfs, stops_within_radius, stops_within_radius_cached


def test_load_gtfs_builds_stop_and_trip_indexes(tiny_gtfs_dir):
    gtfs = load_gtfs(tiny_gtfs_dir)

    assert gtfs.stops["A"].name == "Zurich Alpha"
    assert [entry.stop_id for entry in gtfs.trip_stops["T1"]] == ["A", "B", "C"]
    assert [entry.trip_id for entry in gtfs.stop_times_by_stop["A"]] == ["T1"]


def test_get_active_trips_uses_active_services(tiny_gtfs_dir):
    gtfs = load_gtfs(tiny_gtfs_dir)

    assert get_active_trips(gtfs, date(2026, 4, 30)) == {"T1"}
    assert get_active_trips(gtfs, date(2026, 5, 1)) == set()


def test_spatial_lookup_finds_nearby_stops(tiny_gtfs_dir):
    gtfs = load_gtfs(tiny_gtfs_dir)

    nearby = stops_within_radius(gtfs, 47.3760, 8.5410, 100)
    assert nearby[0][0] == "A"
    assert nearby[0][1] < 1


def test_cached_stop_lookup_uses_stop_id(tiny_gtfs_dir):
    gtfs = load_gtfs(tiny_gtfs_dir)

    first = stops_within_radius_cached(gtfs, "A", 600)
    second = stops_within_radius_cached(gtfs, "A", 600)

    assert first == second
    assert any(stop_id == "B" for stop_id, _ in first)
```

- [ ] **Step 3: Run the loader tests to verify they fail**

Run:

```powershell
pytest tests/test_gtfs_loader.py -v
```

Expected: fail with `ModuleNotFoundError: No module named 'backend.gtfs_loader'`.

- [ ] **Step 4: Implement the loader**

Create `backend/gtfs_loader.py`:

```python
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

    trip_service_ids = {
        row.trip_id: row.service_id for row in trips_df.itertuples(index=False)
    }

    stop_times_by_stop: dict[str, list[StopTime]] = defaultdict(list)
    trip_stops: dict[str, list[TripStop]] = defaultdict(list)
    for row in stop_times_df.itertuples(index=False):
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
        stop_id_order=stop_id_order,
        stop_coordinates=coordinates,
        stop_kdtree=stop_kdtree,
    )


def get_active_trips(gtfs: GTFSData, service_date: date) -> set[str]:
    services = active_service_ids(gtfs.calendars, gtfs.calendar_dates, service_date)
    return {trip_id for trip_id, service_id in gtfs.trip_service_ids.items() if service_id in services}


def stops_within_radius(
    gtfs: GTFSData,
    lat: float,
    lon: float,
    radius_m: float,
) -> list[tuple[str, float]]:
    if gtfs.stop_kdtree is None:
        return []
    radius_degrees = radius_m / 111_000
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
            item for item in stops_within_radius(gtfs, stop.lat, stop.lon, radius_m)
            if item[0] != stop_id
        ]
    return gtfs.walk_cache[key]
```

- [ ] **Step 5: Run loader tests**

Run:

```powershell
pytest tests/test_gtfs_loader.py tests/test_time_utils.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

Run:

```powershell
git add backend/gtfs_loader.py tests/__init__.py tests/helpers.py tests/conftest.py tests/test_gtfs_loader.py
git commit -m "feat: load filtered GTFS indexes"
```

Expected: commit succeeds.

---

### Task 4: Automated GTFS Download And Zurich Filter

**Files:**
- Create: `backend/setup_data.py`
- Create: `tests/test_setup_data.py`

- [ ] **Step 1: Write failing filter consistency tests**

Create `tests/test_setup_data.py`:

```python
from pathlib import Path

import pandas as pd

from backend.setup_data import Bounds, filter_gtfs
from tests.helpers import write_table


def test_filter_gtfs_keeps_consistent_zurich_subset(tmp_path: Path):
    raw = tmp_path / "raw"
    out = tmp_path / "filtered"
    raw.mkdir()

    write_table(
        raw,
        "agency.txt",
        ["agency_id", "agency_name", "agency_url", "agency_timezone"],
        [["AG1", "Agency 1", "https://example.test", "Europe/Zurich"]],
    )
    write_table(
        raw,
        "stops.txt",
        ["stop_id", "stop_name", "stop_lat", "stop_lon"],
        [
            ["A", "Inside A", 47.37, 8.54],
            ["B", "Inside B", 47.38, 8.55],
            ["X", "Outside X", 46.00, 7.00],
        ],
    )
    write_table(
        raw,
        "routes.txt",
        ["route_id", "agency_id", "route_short_name", "route_long_name", "route_type"],
        [["R1", "AG1", "1", "Route 1", 3], ["RX", "AG1", "X", "Route X", 3]],
    )
    write_table(
        raw,
        "trips.txt",
        ["route_id", "service_id", "trip_id"],
        [["R1", "WKD", "T1"], ["RX", "WKD", "TX"]],
    )
    write_table(
        raw,
        "stop_times.txt",
        ["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"],
        [
            ["T1", "08:00:00", "08:00:00", "A", 1],
            ["T1", "08:05:00", "08:05:00", "B", 2],
            ["TX", "08:00:00", "08:00:00", "X", 1],
        ],
    )
    write_table(
        raw,
        "calendar.txt",
        [
            "service_id",
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
            "start_date",
            "end_date",
        ],
        [["WKD", 1, 1, 1, 1, 1, 0, 0, "20260401", "20260430"]],
    )
    write_table(raw, "calendar_dates.txt", ["service_id", "date", "exception_type"], [["WKD", "20260430", 1]])
    write_table(raw, "transfers.txt", ["from_stop_id", "to_stop_id", "transfer_type", "min_transfer_time"], [["A", "B", 2, 120], ["A", "X", 2, 120]])

    filter_gtfs(raw, out, Bounds(min_lat=47.0, max_lat=48.0, min_lon=8.0, max_lon=9.0))

    stops = pd.read_csv(out / "stops.txt")
    trips = pd.read_csv(out / "trips.txt")
    stop_times = pd.read_csv(out / "stop_times.txt")
    transfers = pd.read_csv(out / "transfers.txt")

    assert set(stops.stop_id) == {"A", "B"}
    assert set(trips.trip_id) == {"T1"}
    assert set(stop_times.stop_id) == {"A", "B"}
    assert set(transfers.to_stop_id) == {"B"}
```

- [ ] **Step 2: Run the setup-data test to verify it fails**

Run:

```powershell
pytest tests/test_setup_data.py -v
```

Expected: fail with `ModuleNotFoundError: No module named 'backend.setup_data'`.

- [ ] **Step 3: Implement data setup and filtering**

Create `backend/setup_data.py`:

```python
from __future__ import annotations

import argparse
import json
import shutil
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

DEFAULT_CKAN_PACKAGE_URL = "https://data.opentransportdata.swiss/api/3/action/package_show?id=timetable-2026-gtfs2020"
GEOPS_FALLBACK_URL = "https://gtfs.geops.ch/dl/gtfs_complete.zip"


@dataclass(frozen=True)
class Bounds:
    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float


ZURICH_BOUNDS = Bounds(min_lat=47.05, max_lat=47.75, min_lon=8.25, max_lon=8.95)


def _read(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str).fillna("")


def _write(df: pd.DataFrame, output_dir: Path, name: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_dir / name, index=False)


def discover_download_url(package_url: str = DEFAULT_CKAN_PACKAGE_URL) -> str:
    try:
        with urllib.request.urlopen(package_url, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
        resources = payload.get("result", {}).get("resources", [])
        zip_resources = [
            resource for resource in resources
            if str(resource.get("url", "")).lower().endswith(".zip")
        ]
        if zip_resources:
            return str(zip_resources[0]["url"])
    except Exception:
        return GEOPS_FALLBACK_URL
    return GEOPS_FALLBACK_URL


def download_gtfs(destination: Path, source_url: str | None = None) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    url = source_url or discover_download_url()
    urllib.request.urlretrieve(url, destination)
    return destination


def extract_gtfs(zip_path: Path, output_dir: Path) -> Path:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(output_dir)
    return output_dir


def filter_gtfs(raw_dir: Path, output_dir: Path, bounds: Bounds = ZURICH_BOUNDS) -> Path:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    stops = _read(raw_dir / "stops.txt")
    stops["stop_lat_float"] = stops.stop_lat.astype(float)
    stops["stop_lon_float"] = stops.stop_lon.astype(float)
    kept_stops = stops[
        stops.stop_lat_float.between(bounds.min_lat, bounds.max_lat)
        & stops.stop_lon_float.between(bounds.min_lon, bounds.max_lon)
    ].drop(columns=["stop_lat_float", "stop_lon_float"])
    kept_stop_ids = set(kept_stops.stop_id)

    stop_times = _read(raw_dir / "stop_times.txt")
    kept_stop_times = stop_times[stop_times.stop_id.isin(kept_stop_ids)]
    kept_trip_ids = set(kept_stop_times.trip_id)

    trips = _read(raw_dir / "trips.txt")
    kept_trips = trips[trips.trip_id.isin(kept_trip_ids)]
    kept_route_ids = set(kept_trips.route_id)
    kept_service_ids = set(kept_trips.service_id)

    routes = _read(raw_dir / "routes.txt") if (raw_dir / "routes.txt").exists() else pd.DataFrame()
    kept_routes = routes[routes.route_id.isin(kept_route_ids)] if not routes.empty else routes
    kept_agency_ids = set(kept_routes.agency_id) if "agency_id" in kept_routes.columns else set()

    agency = _read(raw_dir / "agency.txt") if (raw_dir / "agency.txt").exists() else pd.DataFrame()
    if not agency.empty and kept_agency_ids and "agency_id" in agency.columns:
        agency = agency[agency.agency_id.isin(kept_agency_ids)]

    calendar = _read(raw_dir / "calendar.txt") if (raw_dir / "calendar.txt").exists() else pd.DataFrame()
    if not calendar.empty:
        calendar = calendar[calendar.service_id.isin(kept_service_ids)]

    calendar_dates = _read(raw_dir / "calendar_dates.txt") if (raw_dir / "calendar_dates.txt").exists() else pd.DataFrame()
    if not calendar_dates.empty:
        calendar_dates = calendar_dates[calendar_dates.service_id.isin(kept_service_ids)]

    transfers = _read(raw_dir / "transfers.txt") if (raw_dir / "transfers.txt").exists() else pd.DataFrame()
    if not transfers.empty:
        transfers = transfers[
            transfers.from_stop_id.isin(kept_stop_ids)
            & transfers.to_stop_id.isin(kept_stop_ids)
        ]

    _write(kept_stops, output_dir, "stops.txt")
    _write(kept_stop_times, output_dir, "stop_times.txt")
    _write(kept_trips, output_dir, "trips.txt")
    if not kept_routes.empty:
        _write(kept_routes, output_dir, "routes.txt")
    if not agency.empty:
        _write(agency, output_dir, "agency.txt")
    if not calendar.empty:
        _write(calendar, output_dir, "calendar.txt")
    if not calendar_dates.empty:
        _write(calendar_dates, output_dir, "calendar_dates.txt")
    if not transfers.empty:
        _write(transfers, output_dir, "transfers.txt")
    return output_dir


def prepare_data(raw_zip: Path, raw_dir: Path, output_dir: Path, source_url: str | None = None) -> Path:
    download_gtfs(raw_zip, source_url=source_url)
    extract_gtfs(raw_zip, raw_dir)
    return filter_gtfs(raw_dir, output_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare a Zurich-area GTFS subset.")
    parser.add_argument("--zip-path", default="backend/data/raw/gtfs.zip")
    parser.add_argument("--raw-dir", default="backend/data/raw/extracted")
    parser.add_argument("--output-dir", default="backend/data/filtered")
    parser.add_argument("--source-url", default=None)
    args = parser.parse_args()
    output = prepare_data(
        raw_zip=Path(args.zip_path),
        raw_dir=Path(args.raw_dir),
        output_dir=Path(args.output_dir),
        source_url=args.source_url,
    )
    print(f"Wrote filtered GTFS to {output}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run setup-data tests**

Run:

```powershell
pytest tests/test_setup_data.py tests/test_gtfs_loader.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add backend/setup_data.py tests/test_setup_data.py
git commit -m "feat: prepare Zurich GTFS subset"
```

Expected: commit succeeds.

---

### Task 5: Approximate And Schedule Routing

**Files:**
- Create: `backend/router.py`
- Create: `tests/test_router.py`

- [ ] **Step 1: Write failing routing tests**

Create `tests/test_router.py`:

```python
from datetime import datetime

from backend.gtfs_loader import get_active_trips, load_gtfs
from backend.router import compute_approximate_reachability, compute_schedule_reachability


def test_schedule_reachability_finds_direct_trip(tiny_gtfs_dir):
    gtfs = load_gtfs(tiny_gtfs_dir)
    active_trips = get_active_trips(gtfs, datetime(2026, 4, 30, 8, 0).date())

    best = compute_schedule_reachability(
        origin_lat=47.3760,
        origin_lon=8.5410,
        departure_datetime=datetime(2026, 4, 30, 8, 0),
        max_travel_seconds=30 * 60,
        gtfs=gtfs,
        active_trips=active_trips,
    )

    assert best["A"] == 8 * 3600
    assert best["B"] == 8 * 3600 + 10 * 60
    assert best["C"] == 8 * 3600 + 20 * 60


def test_schedule_reachability_respects_deadline(tiny_gtfs_dir):
    gtfs = load_gtfs(tiny_gtfs_dir)
    active_trips = get_active_trips(gtfs, datetime(2026, 4, 30, 8, 0).date())

    best = compute_schedule_reachability(
        origin_lat=47.3760,
        origin_lon=8.5410,
        departure_datetime=datetime(2026, 4, 30, 8, 0),
        max_travel_seconds=12 * 60,
        gtfs=gtfs,
        active_trips=active_trips,
    )

    assert "B" in best
    assert "C" not in best


def test_approximate_reachability_returns_fast_route_estimate(tiny_gtfs_dir):
    gtfs = load_gtfs(tiny_gtfs_dir)

    best = compute_approximate_reachability(
        origin_lat=47.3760,
        origin_lon=8.5410,
        departure_sec=8 * 3600,
        max_travel_seconds=30 * 60,
        gtfs=gtfs,
    )

    assert {"A", "B", "C"}.issubset(best)
```

- [ ] **Step 2: Run routing tests to verify they fail**

Run:

```powershell
pytest tests/test_router.py -v
```

Expected: fail with `ModuleNotFoundError: No module named 'backend.router'`.

- [ ] **Step 3: Implement routing**

Create `backend/router.py`:

```python
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
    for stop_id, dist_m in stops_within_radius(gtfs, origin_lat, origin_lon, MAX_WALK_TO_FIRST_STOP_M):
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
```

- [ ] **Step 4: Run routing tests**

Run:

```powershell
pytest tests/test_router.py tests/test_gtfs_loader.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add backend/router.py tests/test_router.py
git commit -m "feat: compute transit reachability"
```

Expected: commit succeeds.

---

### Task 6: Heatmap Point Builder

**Files:**
- Create: `backend/heatmap_builder.py`
- Create: `tests/test_heatmap_builder.py`

- [ ] **Step 1: Write failing heatmap tests**

Create `tests/test_heatmap_builder.py`:

```python
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
```

- [ ] **Step 2: Run heatmap tests to verify they fail**

Run:

```powershell
pytest tests/test_heatmap_builder.py -v
```

Expected: fail with `ModuleNotFoundError: No module named 'backend.heatmap_builder'`.

- [ ] **Step 3: Implement heatmap builder**

Create `backend/heatmap_builder.py`:

```python
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
```

- [ ] **Step 4: Run heatmap tests**

Run:

```powershell
pytest tests/test_heatmap_builder.py tests/test_router.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add backend/heatmap_builder.py tests/test_heatmap_builder.py
git commit -m "feat: build weighted heatmap points"
```

Expected: commit succeeds.

---

### Task 7: FastAPI App And Progressive Job API

**Files:**
- Create: `backend/main.py`
- Create: `tests/test_api.py`

- [ ] **Step 1: Write failing API tests**

Create `tests/test_api.py`:

```python
from pathlib import Path

from fastapi.testclient import TestClient

from backend.gtfs_loader import load_gtfs
from backend.main import create_app


def test_search_stops_returns_matches(tiny_gtfs_dir: Path):
    app = create_app(gtfs_data=load_gtfs(tiny_gtfs_dir))
    client = TestClient(app)

    response = client.get("/api/stops/search", params={"q": "alpha"})

    assert response.status_code == 200
    assert response.json()[0]["name"] == "Zurich Alpha"


def test_heatmap_returns_approximate_points_and_job(tiny_gtfs_dir: Path):
    app = create_app(gtfs_data=load_gtfs(tiny_gtfs_dir))
    client = TestClient(app)

    response = client.get(
        "/api/heatmap",
        params={
            "lat": 47.3760,
            "lon": 8.5410,
            "minutes": 30,
            "departure": "2026-04-30T08:00:00",
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["quality"] == "approximate"
    assert body["job_id"].startswith("hm_")
    assert body["points"]


def test_job_endpoint_returns_completed_schedule_result(tiny_gtfs_dir: Path):
    app = create_app(gtfs_data=load_gtfs(tiny_gtfs_dir))
    client = TestClient(app)

    first = client.get(
        "/api/heatmap",
        params={
            "lat": 47.3760,
            "lon": 8.5410,
            "minutes": 30,
            "departure": "2026-04-30T08:00:00",
        },
    ).json()

    job = client.get(f"/api/jobs/{first['job_id']}")

    assert job.status_code == 200
    assert job.json()["status"] == "complete"
    assert job.json()["quality"] == "schedule"


def test_unknown_job_returns_404(tiny_gtfs_dir: Path):
    app = create_app(gtfs_data=load_gtfs(tiny_gtfs_dir))
    client = TestClient(app)

    response = client.get("/api/jobs/hm_missing")

    assert response.status_code == 404
```

- [ ] **Step 2: Run API tests to verify they fail**

Run:

```powershell
pytest tests/test_api.py -v
```

Expected: fail with `ModuleNotFoundError: No module named 'backend.main'`.

- [ ] **Step 3: Implement FastAPI app and in-memory jobs**

Create `backend/main.py`:

```python
from __future__ import annotations

import time
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.gtfs_loader import get_active_trips, load_gtfs
from backend.heatmap_builder import build_heatmap_points
from backend.models import GTFSData, JobRecord
from backend.router import compute_approximate_reachability, compute_schedule_reachability
from backend.time_utils import seconds_since_midnight

DEFAULT_DATA_DIR = Path("backend/data/filtered")


class JobStore:
    def __init__(self) -> None:
        self.jobs: dict[str, JobRecord] = {}

    def create(self) -> JobRecord:
        job = JobRecord(id=f"hm_{uuid.uuid4().hex[:12]}", status="running")
        self.jobs[job.id] = job
        return job

    def get(self, job_id: str) -> JobRecord | None:
        return self.jobs.get(job_id)


def _serialize_points(points: list[dict[str, float]]) -> list[dict[str, float]]:
    return [{"lat": p["lat"], "lng": p["lng"], "weight": p["weight"]} for p in points]


def create_app(gtfs_data: GTFSData | None = None, data_dir: Path = DEFAULT_DATA_DIR) -> FastAPI:
    app = FastAPI(title="Transit Heatmap API")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.gtfs_data = gtfs_data
    app.state.jobs = JobStore()

    @app.on_event("startup")
    async def startup() -> None:
        if app.state.gtfs_data is None and data_dir.exists():
            app.state.gtfs_data = load_gtfs(data_dir)

    def require_gtfs() -> GTFSData:
        if app.state.gtfs_data is None:
            raise HTTPException(
                status_code=503,
                detail="GTFS data is missing. Run: python -m backend.setup_data",
            )
        return app.state.gtfs_data

    def refine_job(
        job_id: str,
        lat: float,
        lon: float,
        minutes: int,
        departure_dt: datetime,
    ) -> None:
        gtfs = require_gtfs()
        job = app.state.jobs.get(job_id)
        if job is None:
            return
        started = time.perf_counter()
        try:
            active_trips = get_active_trips(gtfs, departure_dt.date())
            best = compute_schedule_reachability(
                origin_lat=lat,
                origin_lon=lon,
                departure_datetime=departure_dt,
                max_travel_seconds=minutes * 60,
                gtfs=gtfs,
                active_trips=active_trips,
            )
            points = build_heatmap_points(
                best,
                gtfs.stops,
                seconds_since_midnight(departure_dt),
                minutes * 60,
            )
            job.status = "complete"
            job.quality = "schedule"
            job.points = []
            job.stop_count = len(best)
            job.computation_ms = int((time.perf_counter() - started) * 1000)
            job.warnings = []
            job._serialized_points = points
        except Exception as exc:
            job.status = "failed"
            job.error = str(exc)
            job.warnings = ["Approximate result is still available"]

    @app.get("/api/stops/search")
    async def search_stops(q: str = Query(..., min_length=2)) -> list[dict[str, object]]:
        gtfs = require_gtfs()
        needle = q.casefold()
        results = [
            {"id": stop.id, "name": stop.name, "lat": stop.lat, "lon": stop.lon}
            for stop in gtfs.stops.values()
            if needle in stop.name.casefold()
        ]
        return sorted(results, key=lambda item: str(item["name"]))[:10]

    @app.get("/api/heatmap")
    async def get_heatmap(
        background_tasks: BackgroundTasks,
        lat: float,
        lon: float,
        minutes: int = Query(30, ge=1, le=120),
        departure: str | None = None,
    ) -> dict[str, object]:
        gtfs = require_gtfs()
        departure_dt = datetime.fromisoformat(departure) if departure else datetime.now()
        departure_sec = seconds_since_midnight(departure_dt)
        best = compute_approximate_reachability(
            origin_lat=lat,
            origin_lon=lon,
            departure_sec=departure_sec,
            max_travel_seconds=minutes * 60,
            gtfs=gtfs,
        )
        points = build_heatmap_points(best, gtfs.stops, departure_sec, minutes * 60)
        job = app.state.jobs.create()
        background_tasks.add_task(refine_job, job.id, lat, lon, minutes, departure_dt)
        warnings = [] if best else ["No reachable transit stops found"]
        return {
            "quality": "approximate",
            "job_id": job.id,
            "points": _serialize_points(points),
            "stop_count": len(best),
            "warnings": warnings,
        }

    @app.get("/api/jobs/{job_id}")
    async def get_job(job_id: str) -> dict[str, object]:
        job = app.state.jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Unknown job id")
        if job.status == "running":
            return {"status": "running", "quality": None}
        if job.status == "failed":
            return {"status": "failed", "error": job.error, "warnings": job.warnings}
        points = getattr(job, "_serialized_points", [])
        return {
            "status": "complete",
            "quality": job.quality,
            "points": _serialize_points(points),
            "stop_count": job.stop_count,
            "computation_ms": job.computation_ms,
            "warnings": job.warnings,
        }

    frontend_dir = Path("frontend")
    if frontend_dir.exists():
        app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="static")

    return app


app = create_app()
```

- [ ] **Step 4: Run API tests**

Run:

```powershell
pytest tests/test_api.py tests/test_heatmap_builder.py tests/test_router.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add backend/main.py tests/test_api.py
git commit -m "feat: expose progressive heatmap API"
```

Expected: commit succeeds.

---

### Task 8: Leaflet/OpenStreetMap Frontend

**Files:**
- Create: `frontend/index.html`
- Create: `frontend/app.js`
- Create: `frontend/style.css`
- Create: `tests/test_frontend_assets.py`

- [ ] **Step 1: Write failing frontend asset contract tests**

Create `tests/test_frontend_assets.py`:

```python
from pathlib import Path


def test_frontend_uses_leaflet_and_not_google_maps():
    html = Path("frontend/index.html").read_text(encoding="utf-8")

    assert "leaflet" in html.lower()
    assert "leaflet-heat" in html.lower()
    assert "maps.googleapis.com" not in html


def test_frontend_polling_and_status_contracts_exist():
    js = Path("frontend/app.js").read_text(encoding="utf-8")

    assert "fetchHeatmap" in js
    assert "pollJob" in js
    assert "Approximate result" in js
    assert "Schedule result" in js
```

- [ ] **Step 2: Run frontend tests to verify they fail**

Run:

```powershell
pytest tests/test_frontend_assets.py -v
```

Expected: fail because `frontend/index.html` does not exist.

- [ ] **Step 3: Create frontend files**

Create `frontend/index.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Transit Heatmap</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <aside id="controls" aria-label="Transit heatmap controls">
    <h1>Transit Reach</h1>
    <label for="stop-search">Station or stop</label>
    <input id="stop-search" type="text" aria-label="Station or stop" autocomplete="off">
    <ul id="stop-suggestions"></ul>

    <label for="time-slider">Travel time: <span id="time-label">30</span> min</label>
    <input id="time-slider" type="range" min="5" max="120" step="5" value="30">

    <label for="departure-time">Departure</label>
    <input id="departure-time" type="datetime-local">

    <button id="go-btn" type="button">Show Heatmap</button>
    <div id="status" role="status"></div>
  </aside>
  <main id="map" aria-label="Reachability map"></main>

  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script src="https://unpkg.com/leaflet.heat@0.2.0/dist/leaflet-heat.js"></script>
  <script src="app.js"></script>
</body>
</html>
```

Create `frontend/app.js`:

```javascript
const API_BASE = "";

let map;
let heatLayer;
let marker;
let selectedOrigin = null;
let activePollTimer = null;

const searchInput = document.getElementById("stop-search");
const suggestions = document.getElementById("stop-suggestions");
const timeSlider = document.getElementById("time-slider");
const timeLabel = document.getElementById("time-label");
const departureInput = document.getElementById("departure-time");
const goButton = document.getElementById("go-btn");
const statusEl = document.getElementById("status");

function initMap() {
  map = L.map("map").setView([47.376, 8.541], 12);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(map);

  map.on("click", (event) => {
    setOrigin(event.latlng.lat, event.latlng.lng, "Custom location");
  });

  const now = new Date();
  now.setSeconds(0, 0);
  departureInput.value = new Date(now.getTime() - now.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16);
}

function setStatus(message, mode = "neutral") {
  statusEl.textContent = message;
  statusEl.dataset.mode = mode;
}

function setOrigin(lat, lon, name) {
  selectedOrigin = { lat, lon, name };
  if (marker) {
    marker.remove();
  }
  marker = L.marker([lat, lon]).addTo(map).bindPopup(name);
  map.panTo([lat, lon]);
}

function renderHeatmap(points) {
  if (heatLayer) {
    heatLayer.remove();
  }
  const heatPoints = points.map((point) => [point.lat, point.lng, point.weight]);
  heatLayer = L.heatLayer(heatPoints, {
    radius: 24,
    blur: 18,
    maxZoom: 13,
    minOpacity: 0.25,
    gradient: {
      0.15: "#2563eb",
      0.4: "#16a34a",
      0.65: "#facc15",
      0.9: "#f97316",
      1.0: "#ef4444",
    },
  }).addTo(map);

  if (points.length > 0) {
    const bounds = L.latLngBounds(points.map((point) => [point.lat, point.lng]));
    map.fitBounds(bounds, { padding: [30, 30], maxZoom: 13 });
  }
}

async function searchStops(query) {
  const response = await fetch(`${API_BASE}/api/stops/search?q=${encodeURIComponent(query)}`);
  if (!response.ok) {
    throw new Error("Stop search failed");
  }
  return response.json();
}

async function fetchHeatmap() {
  if (!selectedOrigin) {
    setStatus("Select a stop or click the map first.", "warning");
    return;
  }
  if (activePollTimer) {
    clearTimeout(activePollTimer);
  }

  setStatus("Computing approximate result...", "loading");
  const params = new URLSearchParams({
    lat: selectedOrigin.lat,
    lon: selectedOrigin.lon,
    minutes: timeSlider.value,
    departure: departureInput.value,
  });
  const response = await fetch(`${API_BASE}/api/heatmap?${params.toString()}`);
  if (!response.ok) {
    throw new Error(`Heatmap request failed: ${response.status}`);
  }
  const data = await response.json();
  renderHeatmap(data.points);
  setStatus(`Approximate result: ${data.stop_count} stops. Refining...`, "loading");
  pollJob(data.job_id);
}

async function pollJob(jobId) {
  const response = await fetch(`${API_BASE}/api/jobs/${encodeURIComponent(jobId)}`);
  if (!response.ok) {
    setStatus("Refinement status unavailable; keeping approximate result.", "warning");
    return;
  }
  const data = await response.json();
  if (data.status === "running") {
    activePollTimer = setTimeout(() => pollJob(jobId), 1200);
    return;
  }
  if (data.status === "failed") {
    setStatus("Refinement failed; keeping approximate result.", "warning");
    return;
  }
  renderHeatmap(data.points);
  setStatus(`Schedule result: ${data.stop_count} stops in ${data.computation_ms} ms.`, "success");
}

let debounceTimer;
searchInput.addEventListener("input", () => {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(async () => {
    const query = searchInput.value.trim();
    if (query.length < 2) {
      suggestions.innerHTML = "";
      return;
    }
    try {
      const stops = await searchStops(query);
      suggestions.innerHTML = stops
        .map(
          (stop) =>
            `<li data-lat="${stop.lat}" data-lon="${stop.lon}" data-name="${stop.name}">${stop.name}</li>`
        )
        .join("");
    } catch (error) {
      setStatus(error.message, "error");
    }
  }, 250);
});

suggestions.addEventListener("click", (event) => {
  const item = event.target.closest("li");
  if (!item) {
    return;
  }
  searchInput.value = item.dataset.name;
  suggestions.innerHTML = "";
  setOrigin(Number(item.dataset.lat), Number(item.dataset.lon), item.dataset.name);
});

timeSlider.addEventListener("input", () => {
  timeLabel.textContent = timeSlider.value;
});

goButton.addEventListener("click", async () => {
  try {
    await fetchHeatmap();
  } catch (error) {
    setStatus(error.message, "error");
  }
});

initMap();
```

Create `frontend/style.css`:

```css
* {
  box-sizing: border-box;
}

html,
body {
  height: 100%;
  margin: 0;
  font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

body {
  display: flex;
  background: #f8fafc;
  color: #0f172a;
}

#controls {
  width: 300px;
  min-width: 260px;
  padding: 18px;
  background: #111827;
  color: #f8fafc;
  display: flex;
  flex-direction: column;
  gap: 11px;
  z-index: 500;
  box-shadow: 4px 0 18px rgba(15, 23, 42, 0.28);
}

h1 {
  margin: 0 0 4px;
  font-size: 1.35rem;
  font-weight: 700;
}

label {
  font-size: 0.82rem;
  color: #cbd5e1;
}

input {
  width: 100%;
  border: 1px solid #334155;
  border-radius: 6px;
  padding: 9px 10px;
  background: #1f2937;
  color: #f8fafc;
}

input[type="range"] {
  padding: 0;
  accent-color: #20c997;
}

button {
  border: 0;
  border-radius: 6px;
  padding: 10px 12px;
  background: #20c997;
  color: #06281f;
  font-weight: 700;
  cursor: pointer;
}

button:hover {
  background: #34d399;
}

#stop-suggestions {
  margin: -5px 0 0;
  padding: 0;
  list-style: none;
  max-height: 180px;
  overflow-y: auto;
  background: #1f2937;
  border-radius: 6px;
}

#stop-suggestions li {
  padding: 9px 10px;
  border-bottom: 1px solid #334155;
  cursor: pointer;
}

#stop-suggestions li:hover {
  background: #334155;
}

#status {
  min-height: 44px;
  padding: 10px;
  border-radius: 6px;
  background: #1f2937;
  color: #cbd5e1;
  font-size: 0.86rem;
  line-height: 1.3;
}

#status[data-mode="success"] {
  color: #bbf7d0;
}

#status[data-mode="warning"] {
  color: #fde68a;
}

#status[data-mode="error"] {
  color: #fecaca;
}

#map {
  flex: 1;
  min-width: 0;
}

@media (max-width: 720px) {
  body {
    flex-direction: column;
  }

  #controls {
    width: 100%;
    min-width: 0;
    max-height: 42vh;
    overflow-y: auto;
  }

  #map {
    min-height: 58vh;
  }
}
```

- [ ] **Step 4: Run frontend asset tests**

Run:

```powershell
pytest tests/test_frontend_assets.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

Run:

```powershell
git add frontend/index.html frontend/app.js frontend/style.css tests/test_frontend_assets.py
git commit -m "feat: add Leaflet heatmap frontend"
```

Expected: commit succeeds.

---

### Task 9: Documentation And Full Verification

**Files:**
- Create: `README.md`
- Modify: `.gitignore`

- [ ] **Step 1: Update `.gitignore` for filtered GTFS data**

Modify `.gitignore` so it contains:

```text
.superpowers/
__pycache__/
.pytest_cache/
.venv/
venv/
backend/data/raw/
backend/data/cache/
backend/data/filtered/
*.pyc
```

- [ ] **Step 2: Create README**

Create `README.md`:

```markdown
# Transit Heatmap

Local-first public transport reachability heatmap for the ZVV/Zurich area.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Prepare Data

```powershell
python -m backend.setup_data
```

This downloads Swiss GTFS data, extracts it under `backend/data/raw/`, filters it to the Zurich-area MVP scope, and writes the app feed to `backend/data/filtered/`.

## Run Tests

```powershell
pytest -v
```

## Start The App

```powershell
uvicorn backend.main:app --reload --port 8000
```

Open `http://localhost:8000`.

## Behavior

The first heatmap is approximate and should appear quickly. The backend then computes a schedule-based refinement in the background; the frontend polls the job endpoint and replaces the heatmap when the refined result is ready.
```

- [ ] **Step 3: Run all tests**

Run:

```powershell
pytest -v
```

Expected: all tests pass.

- [ ] **Step 4: Start the server for a local smoke test**

If `backend/data/filtered/stops.txt` exists, run:

```powershell
uvicorn backend.main:app --reload --port 8000
```

Expected: server starts and serves `http://localhost:8000`.

If the data directory does not exist, run this API check instead:

```powershell
python -c "from backend.main import create_app; app=create_app(); print(app.title)"
```

Expected output:

```text
Transit Heatmap API
```

- [ ] **Step 5: Commit**

Run:

```powershell
git add README.md .gitignore
git commit -m "docs: add local setup instructions"
```

Expected: commit succeeds.

---

### Task 10: Final Quality Pass

**Files:**
- Modify only files needed to fix verification failures found in this task.

- [ ] **Step 1: Run repository status**

Run:

```powershell
git status --short
```

Expected: no uncommitted files before final checks.

- [ ] **Step 2: Run the complete test suite**

Run:

```powershell
pytest -v
```

Expected: all tests pass.

- [ ] **Step 3: Inspect frontend for accidental Google Maps dependencies**

Run:

```powershell
rg -n "google|maps.googleapis|YOUR_API_KEY" .
```

Expected: no matches in implementation files. A match in the original design/spec text is acceptable.

- [ ] **Step 4: Inspect code for unfinished-work markers**

Run:

```powershell
$pattern = 'T' + 'BD|TO' + 'DO|FIX' + 'ME|place' + 'holder'
rg -n $pattern backend frontend tests README.md
```

Expected: no matches.

- [ ] **Step 5: Commit any verification fixes**

If any files changed during this task, run:

```powershell
git add backend frontend tests README.md .gitignore pyproject.toml requirements.txt
git commit -m "chore: finish MVP verification"
```

Expected: commit succeeds if changes were needed. If no files changed, skip the commit.

---

## Spec Coverage Checklist

- Automated Zurich/ZVV data setup: Task 4 and Task 9.
- Leaflet/OpenStreetMap frontend without API key: Task 8.
- Stop search and map-click origins: Task 7 and Task 8.
- Fast approximate heatmap: Task 5, Task 6, Task 7, Task 8.
- Background refined schedule heatmap: Task 5, Task 7, Task 8.
- Walking halos: Task 6.
- Missing data and unknown job errors: Task 7 and Task 9.
- GTFS time, calendar, filtering, routing, API, and frontend tests: Tasks 2 through 8.
- Local setup docs and verification: Task 9 and Task 10.
