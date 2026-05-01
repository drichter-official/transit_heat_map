from pathlib import Path
from datetime import datetime

from fastapi.testclient import TestClient

from backend.gtfs_loader import load_gtfs
from backend.main import (
    _typical_window_start_datetime,
    create_app,
)


def test_search_stops_returns_matches(tiny_gtfs_dir: Path):
    app = create_app(gtfs_data=load_gtfs(tiny_gtfs_dir))
    client = TestClient(app)

    response = client.get("/api/stops/search", params={"q": "alpha"})

    assert response.status_code == 200
    assert response.json()[0]["name"] == "Zurich Alpha"


def test_search_stops_collapses_platform_duplicates(tiny_gtfs_dir: Path):
    gtfs = load_gtfs(tiny_gtfs_dir)
    gtfs.stops["A:1"] = type(gtfs.stops["A"])(
        id="A:1",
        name=gtfs.stops["A"].name,
        lat=gtfs.stops["A"].lat,
        lon=gtfs.stops["A"].lon,
    )
    gtfs.stops["A:2"] = type(gtfs.stops["A"])(
        id="A:2",
        name=gtfs.stops["A"].name,
        lat=gtfs.stops["A"].lat,
        lon=gtfs.stops["A"].lon,
    )
    app = create_app(gtfs_data=gtfs)
    client = TestClient(app)

    response = client.get("/api/stops/search", params={"q": "alpha"})

    matches = [item for item in response.json() if item["name"] == "Zurich Alpha"]
    assert response.status_code == 200
    assert len(matches) == 1
    assert matches[0]["id"] == "A"


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


def test_heatmap_does_not_require_departure_for_typical_day(tiny_gtfs_dir: Path):
    app = create_app(gtfs_data=load_gtfs(tiny_gtfs_dir))
    client = TestClient(app)

    response = client.get(
        "/api/heatmap",
        params={
            "lat": 47.3760,
            "lon": 8.5410,
            "minutes": 30,
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["quality"] == "approximate"
    assert body["job_id"].startswith("hm_")


def test_typical_window_start_uses_representative_midday(tiny_gtfs_dir: Path):
    gtfs = load_gtfs(tiny_gtfs_dir)

    start = _typical_window_start_datetime(gtfs)

    assert start == datetime(2026, 4, 1, 12, 0)
