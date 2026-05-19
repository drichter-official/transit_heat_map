from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
import urllib.request
import warnings
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


@dataclass(frozen=True)
class RegionConfig:
    bounds: Bounds
    source_env_var: str | None = None


SWITZERLAND_BOUNDS = Bounds(min_lat=45.75, max_lat=47.95, min_lon=5.75, max_lon=10.70)
ZURICH_BOUNDS = Bounds(min_lat=47.05, max_lat=47.75, min_lon=8.25, max_lon=8.95)
LONDON_BOUNDS = Bounds(min_lat=51.25, max_lat=51.75, min_lon=-0.55, max_lon=0.35)
LONDON_GTFS_SOURCE_ENV_VAR = "TRANSIT_HEATMAP_LONDON_GTFS_URL"
REGION_CONFIGS = {
    "switzerland": RegionConfig(bounds=SWITZERLAND_BOUNDS),
    "zurich": RegionConfig(bounds=ZURICH_BOUNDS),
    "london": RegionConfig(bounds=LONDON_BOUNDS, source_env_var=LONDON_GTFS_SOURCE_ENV_VAR),
}
REGION_BOUNDS = {name: config.bounds for name, config in REGION_CONFIGS.items()}
STOP_COLUMNS = ["stop_id", "stop_name", "stop_lat", "stop_lon"]
TRIP_COLUMNS = ["route_id", "service_id", "trip_id"]
STOP_TIME_COLUMNS = ["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"]


def _read(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str).fillna("")


def _write(df: pd.DataFrame, output_dir: Path, name: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_dir / name, index=False)


def _keep_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    return df[[column for column in columns if column in df.columns]]


def _make_staging_dir(target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=f".{target.name}.tmp-", dir=target.parent))


def _replace_dir(staging_dir: Path, output_dir: Path) -> None:
    if not output_dir.exists():
        staging_dir.replace(output_dir)
        return

    backup_dir = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.backup-", dir=output_dir.parent))
    backup_dir.rmdir()
    backup_created = False
    try:
        output_dir.replace(backup_dir)
        backup_created = True
        staging_dir.replace(output_dir)
    except Exception:
        if backup_created and output_dir.exists():
            shutil.rmtree(output_dir, ignore_errors=True)
        if backup_created and backup_dir.exists() and not output_dir.exists():
            backup_dir.replace(output_dir)
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)
        if backup_dir.exists() and output_dir.exists():
            shutil.rmtree(backup_dir, ignore_errors=True)
        raise
    shutil.rmtree(backup_dir, ignore_errors=True)


def _validate_required_files(raw_dir: Path) -> None:
    for name in ("stops.txt", "trips.txt", "stop_times.txt"):
        path = raw_dir / name
        if not path.is_file():
            raise FileNotFoundError(path)


def _reject_overlapping_dirs(raw_dir: Path, output_dir: Path) -> None:
    raw_path = raw_dir.resolve()
    output_path = output_dir.resolve()
    if raw_path == output_path or raw_path in output_path.parents or output_path in raw_path.parents:
        raise ValueError("raw_dir and output_dir must be separate, non-overlapping directories")


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
    except Exception as error:
        warnings.warn(
            f"CKAN GTFS discovery failed; falling back to {GEOPS_FALLBACK_URL}: {error}",
            RuntimeWarning,
            stacklevel=2,
        )
        return GEOPS_FALLBACK_URL
    warnings.warn(
        f"CKAN GTFS discovery found no zip resource; falling back to {GEOPS_FALLBACK_URL}",
        RuntimeWarning,
        stacklevel=2,
    )
    return GEOPS_FALLBACK_URL


def download_gtfs(destination: Path, source_url: str | None = None) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    url = source_url or discover_download_url()
    with tempfile.NamedTemporaryFile(
        delete=False,
        dir=destination.parent,
        prefix=f".{destination.name}.tmp-",
        suffix=".zip",
    ) as temp_file:
        temp_path = Path(temp_file.name)
    try:
        urllib.request.urlretrieve(url, temp_path)
        if not zipfile.is_zipfile(temp_path):
            raise zipfile.BadZipFile(f"Downloaded file is not a zip archive: {url}")
        temp_path.replace(destination)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
    return destination


def resolve_source_url(region: str, source_url: str | None) -> str | None:
    if source_url:
        return source_url
    config = REGION_CONFIGS[region]
    if config.source_env_var:
        env_url = os.environ.get(config.source_env_var)
        if env_url:
            return env_url
        raise ValueError(
            f"London setup requires a GTFS schedule ZIP URL via --source-url or {config.source_env_var}. "
            "TfL live timetable feeds require portal registration and are not unauthenticated GTFS downloads."
        )
    return None


def extract_gtfs(zip_path: Path, output_dir: Path) -> Path:
    staging_dir = _make_staging_dir(output_dir)
    try:
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(staging_dir)
        _replace_dir(staging_dir, output_dir)
    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise
    return output_dir


def filter_gtfs(raw_dir: Path, output_dir: Path, bounds: Bounds = SWITZERLAND_BOUNDS) -> Path:
    _reject_overlapping_dirs(raw_dir, output_dir)
    _validate_required_files(raw_dir)
    staging_dir = _make_staging_dir(output_dir)

    try:
        stops = _read(raw_dir / "stops.txt")
        stops["stop_lat_float"] = stops.stop_lat.astype(float)
        stops["stop_lon_float"] = stops.stop_lon.astype(float)
        kept_stops = stops[
            stops.stop_lat_float.between(bounds.min_lat, bounds.max_lat)
            & stops.stop_lon_float.between(bounds.min_lon, bounds.max_lon)
        ].drop(columns=["stop_lat_float", "stop_lon_float"])
        kept_stops = _keep_columns(kept_stops, STOP_COLUMNS)
        kept_stop_ids = set(kept_stops.stop_id)

        stop_times = _read(raw_dir / "stop_times.txt")
        has_arrival = stop_times.arrival_time.str.strip().ne("")
        has_departure = stop_times.departure_time.str.strip().ne("")
        stop_times = stop_times[has_arrival & has_departure]
        kept_stop_times = stop_times[stop_times.stop_id.isin(kept_stop_ids)]
        kept_stop_times = _keep_columns(kept_stop_times, STOP_TIME_COLUMNS)
        kept_trip_ids = set(kept_stop_times.trip_id)

        trips = _read(raw_dir / "trips.txt")
        kept_trips = trips[trips.trip_id.isin(kept_trip_ids)]
        kept_trips = _keep_columns(kept_trips, TRIP_COLUMNS)
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

        _write(kept_stops, staging_dir, "stops.txt")
        _write(kept_stop_times, staging_dir, "stop_times.txt")
        _write(kept_trips, staging_dir, "trips.txt")
        if not kept_routes.empty:
            _write(kept_routes, staging_dir, "routes.txt")
        if not agency.empty:
            _write(agency, staging_dir, "agency.txt")
        if not calendar.empty:
            _write(calendar, staging_dir, "calendar.txt")
        if not calendar_dates.empty:
            _write(calendar_dates, staging_dir, "calendar_dates.txt")
        if not transfers.empty:
            _write(transfers, staging_dir, "transfers.txt")
        _validate_required_files(staging_dir)
        _replace_dir(staging_dir, output_dir)
    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise
    return output_dir


def prepare_data(
    raw_zip: Path,
    raw_dir: Path,
    output_dir: Path,
    source_url: str | None = None,
    bounds: Bounds = SWITZERLAND_BOUNDS,
) -> Path:
    download_gtfs(raw_zip, source_url=source_url)
    extract_gtfs(raw_zip, raw_dir)
    return filter_gtfs(raw_dir, output_dir, bounds=bounds)


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare a GTFS subset.")
    parser.add_argument("--zip-path", default="backend/data/raw/gtfs.zip")
    parser.add_argument("--raw-dir", default="backend/data/raw/extracted")
    parser.add_argument("--output-dir", default="backend/data/filtered")
    parser.add_argument("--source-url", default=None)
    parser.add_argument(
        "--region",
        choices=sorted(REGION_BOUNDS),
        default="switzerland",
        help="Geographic scope to keep from the source GTFS feed.",
    )
    args = parser.parse_args()
    try:
        source_url = resolve_source_url(args.region, args.source_url)
    except ValueError as error:
        parser.error(str(error))
    output = prepare_data(
        raw_zip=Path(args.zip_path),
        raw_dir=Path(args.raw_dir),
        output_dir=Path(args.output_dir),
        source_url=source_url,
        bounds=REGION_BOUNDS[args.region],
    )
    print(f"Wrote {args.region} GTFS to {output}")


if __name__ == "__main__":
    main()
