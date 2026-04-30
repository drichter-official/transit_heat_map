# Transit Heatmap

Local-first public transport reachability heatmap for Switzerland.

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
