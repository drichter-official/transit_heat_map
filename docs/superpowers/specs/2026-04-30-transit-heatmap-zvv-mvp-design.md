# Transit Heatmap ZVV MVP Design

## Summary

Build a local-first web app that lets a user choose a public transport stop or map location in the ZVV/Zurich area, choose a travel-time budget, and view a heatmap of reachable places. The first MVP optimizes for fast interaction: it shows an approximate heatmap immediately, then replaces it with a more correct GTFS schedule-based result when the background refinement job completes.

The MVP uses OpenStreetMap tiles through Leaflet, so no Google Maps API key is required.

## Goals

- Automate setup of a small Zurich-area GTFS dataset from an official Swiss GTFS source.
- Provide a usable Leaflet/OpenStreetMap frontend with stop search, map-click origin selection, travel-time controls, and progress status.
- Return a fast approximate heatmap first.
- Run time-dependent GTFS routing in the background and update the heatmap when refined results are ready.
- Keep the code split into small, testable backend modules.
- Include focused tests for GTFS parsing, filtering, routing, API job state, and frontend update behavior.

## Non-Goals

- Full Switzerland performance tuning.
- Real-time GTFS-RT delay integration.
- OSM pedestrian-network isochrones.
- Arrival-by reverse routing.
- Multi-origin meeting-point mode.
- Redis, database-backed caching, or distributed background workers.
- Google Maps integration.

## Data Source And Setup

The setup command downloads Swiss GTFS data from the official OpenTransportData 2026 GTFS dataset, with geOps as a practical mirror or fallback. The setup process filters the feed to a Zurich-area subset suitable for local development.

Filtering should preserve GTFS consistency:

- Keep stops within a configured Zurich-area bounding box or canton/ZVV scope.
- Keep trips that serve at least one retained stop.
- Keep the related `routes.txt`, `agency.txt`, `calendar.txt`, `calendar_dates.txt`, `transfers.txt`, and `stop_times.txt` rows needed by those trips and stops.
- Write the filtered feed to a local data directory that the app can load on startup.

The exact filter can start with a conservative Zurich bounding box and later tighten toward a formal ZVV/canton boundary if needed.

## Architecture

The application has a FastAPI backend and a vanilla JavaScript frontend.

Backend modules:

- `backend/setup_data.py`: download the GTFS zip, extract it, filter it to the Zurich/ZVV MVP scope, and write the local subset.
- `backend/gtfs_loader.py`: parse filtered GTFS files into in-memory indexes.
- `backend/router.py`: compute reachability. It owns both the fast approximation and the refined time-dependent GTFS routing.
- `backend/heatmap_builder.py`: convert reachable stops into weighted heatmap points with walking halos.
- `backend/main.py`: define API routes, load GTFS data on startup, manage in-memory background jobs, and serve the frontend.

Frontend files:

- `frontend/index.html`: app shell and asset includes.
- `frontend/app.js`: Leaflet map, stop search, controls, API calls, polling, and heatmap replacement.
- `frontend/style.css`: responsive app layout and status states.

## Progressive Results Flow

1. The user selects an origin, travel-time budget, and departure time.
2. The frontend calls `GET /api/heatmap`.
3. The backend computes an approximate heatmap quickly and starts a background refinement job.
4. The immediate response includes approximate points, `quality: "approximate"`, and a `job_id`.
5. The frontend renders the approximate heatmap and shows a status such as `Approximate result - refining...`.
6. The frontend polls `GET /api/jobs/{job_id}`.
7. When the job completes, the response includes refined schedule-quality points and `quality: "schedule"`.
8. The frontend replaces the heatmap layer and updates status with the refined stop count and computation time.

The app should always preserve the best available result. If refinement fails, the approximate heatmap remains visible.

## API Design

### `GET /api/stops/search`

Query parameters:

- `q`: stop-name search text, minimum length 2.

Response:

```json
[
  { "id": "stop-id", "name": "Zurich HB", "lat": 47.378, "lon": 8.54 }
]
```

### `GET /api/heatmap`

Query parameters:

- `lat`: origin latitude.
- `lon`: origin longitude.
- `minutes`: travel-time budget, initially 5 to 120.
- `departure`: ISO datetime string. If omitted, default to server local time.

Immediate response:

```json
{
  "quality": "approximate",
  "job_id": "hm_abc123",
  "points": [{ "lat": 47.37, "lng": 8.54, "weight": 0.9 }],
  "stop_count": 142,
  "warnings": []
}
```

### `GET /api/jobs/{job_id}`

Response while running:

```json
{
  "status": "running",
  "quality": null
}
```

Response when complete:

```json
{
  "status": "complete",
  "quality": "schedule",
  "points": [{ "lat": 47.37, "lng": 8.54, "weight": 0.9 }],
  "stop_count": 156,
  "computation_ms": 1840,
  "warnings": []
}
```

Response when failed:

```json
{
  "status": "failed",
  "error": "Refinement failed",
  "warnings": ["Approximate result is still available"]
}
```

## Routing Design

The fast approximation should favor speed and stability over perfect transit correctness. For the first implementation, it can use the local stop graph, nearby transfers, route-level reachability, or bounded schedule shortcuts as long as it returns quickly and is clearly labeled as approximate.

The refined router uses time-dependent Dijkstra over the filtered GTFS schedule:

- State is earliest known arrival time per stop.
- Seed the queue with walkable stops near the origin.
- Board departures at or after arrival time.
- Traverse subsequent stops on each active trip until the time budget is exhausted.
- Include walking transfers and scheduled transfers.
- Use sorted stop-time indexes and binary search to avoid linear scans where practical.
- Respect active service dates from `calendar.txt` and `calendar_dates.txt`.
- Parse GTFS times as seconds since service-day midnight, including values above `24:00:00`.

For the MVP, the background jobs can live in memory. A server restart may lose in-progress jobs.

## Heatmap Design

The heatmap builder receives earliest arrival times and emits weighted latitude/longitude points:

- The stop itself gets a point weighted by remaining travel-time budget.
- Walking halo points are scattered around each reachable stop.
- Weight decreases with elapsed time and with distance from the stop.
- Point count should be capped or sampled to avoid browser slowdown.

The MVP uses circular walking halos. Real pedestrian-network isochrones are deferred.

## Frontend Design

The frontend is a compact tool interface, not a landing page.

Core UI:

- Left control panel with stop search, travel-time slider/input, departure datetime, and submit button.
- Full-height Leaflet map with OpenStreetMap tiles.
- Origin marker for selected stop or clicked location.
- Heatmap layer for returned weighted points.
- Status area that distinguishes approximate, refining, complete, no-results, and failed-refinement states.

Expected behavior:

- Selecting a stop recenters the map and places the origin marker.
- Clicking the map sets a custom origin.
- Submitting renders approximate points as soon as they arrive.
- Polling stops when the refined job completes, fails, or expires.
- A refined result replaces the existing heatmap without clearing the map first.

## Error Handling

- If GTFS data is missing, startup or API responses should explain how to run the setup command.
- If no reachable transit stops are found, return a walking-only result or an empty transit result with a clear warning.
- If approximate routing fails, return an API error and show a visible frontend error.
- If refined routing fails, keep the approximate heatmap visible and show a non-blocking status message.
- If a job id is unknown or expired, return `404` with a clear message.
- If the frontend cannot reach the API, show a network error without hiding the current map.

## Testing Strategy

Backend tests:

- GTFS time parsing, especially values above `24:00:00`.
- Calendar and calendar-date active-service logic.
- Zurich-area filter consistency across stops, trips, routes, stop times, calendars, and transfers.
- KD-tree nearest-stop and within-radius lookups.
- Synthetic routing fixtures for direct trips, waiting, transfers, walking transfers, unreachable stops, and overnight times.
- Heatmap weight normalization and point caps.
- API tests for approximate response, job creation, running/completed/failed job states, and missing data.

Frontend tests:

- Stop search renders suggestions and selects a stop.
- Submitting renders approximate points.
- Polling replaces approximate heatmap with refined heatmap.
- Failed refinement leaves approximate heatmap in place.
- Controls and status text fit on desktop and mobile widths.

## Implementation Notes

- Use `requirements.txt` and `pyproject.toml`.
- Use Python 3.11, FastAPI, Uvicorn, pandas, numpy, scipy, and pytest.
- Use Leaflet plus a Leaflet heatmap plugin for rendering.
- Keep the local data directory out of git.
- Document setup with a single command for data preparation and a single command for starting the server.
