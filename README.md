# Transit Heatmap

Local-first public transport reachability heatmap for Switzerland and London.

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

This downloads Swiss GTFS data, extracts it under `backend/data/raw/`, filters it to the Switzerland scope, and writes the app feed to `backend/data/filtered/`.

To prepare the smaller Zurich development feed instead, run:

```powershell
python -m backend.setup_data --region zurich
```

To prepare a London feed, provide a GTFS schedule ZIP URL:

```powershell
python -m backend.setup_data --region london --source-url "https://example.test/london-gtfs.zip"
```

You can also set `TRANSIT_HEATMAP_LONDON_GTFS_URL` and omit `--source-url`.
TfL's live timetable feeds require portal access, and the public Journey Planner example ZIP is TransXChange XML rather than GTFS, so this backend expects a GTFS-converted London schedule feed.

## Run Tests

```powershell
pytest -v
```

## Start The App

```powershell
uvicorn backend.main:app --reload --port 8000
```

Open `http://localhost:8000`.

## Static GitHub Pages

The frontend can also run without FastAPI by loading `frontend/static-data/transit-network.json` and computing approximate reachability in the browser. Regenerate that file from a prepared GTFS feed with:

```powershell
python -m backend.static_export --data-dir backend/data/filtered --output frontend/static-data/transit-network.json
```

When served from GitHub Pages or another non-local static host, the app uses the static data automatically. To point the same frontend at a hosted API instead, open it with `?api=https://your-api.example.com`.

## Behavior

The first heatmap is an approximate general network reach estimate and should appear quickly. The backend then checks first connections in a representative two-hour window starting at midday, subtracts the initial wait until the first connection starts, keeps the best journey duration per stop, and replaces the heatmap when the refined result is ready.
