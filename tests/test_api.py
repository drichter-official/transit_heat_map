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
