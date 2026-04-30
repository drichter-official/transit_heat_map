from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
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
    return [
        {
            "lat": p["lat"],
            "lng": p["lng"],
            "weight": p["weight"],
            "radius_m": p["radius_m"],
        }
        for p in points
    ]


def create_app(gtfs_data: GTFSData | None = None, data_dir: Path = DEFAULT_DATA_DIR) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if app.state.gtfs_data is None and data_dir.exists():
            app.state.gtfs_data = load_gtfs(data_dir)
        yield

    app = FastAPI(title="Transit Heatmap API", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.gtfs_data = gtfs_data
    app.state.jobs = JobStore()

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
        points = build_heatmap_points(
            best,
            gtfs.stops,
            departure_sec,
            minutes * 60,
        )
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
