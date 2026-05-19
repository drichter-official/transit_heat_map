from pathlib import Path
import zipfile

import pandas as pd
import pytest

import backend.setup_data as setup_data
from backend.setup_data import (
    Bounds,
    REGION_BOUNDS,
    _replace_dir,
    discover_download_url,
    download_gtfs,
    extract_gtfs,
    filter_gtfs,
    resolve_source_url,
)
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
            ["T1", "", "", "B", 3],
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
    routes = pd.read_csv(out / "routes.txt")
    agency = pd.read_csv(out / "agency.txt")
    trips = pd.read_csv(out / "trips.txt")
    stop_times = pd.read_csv(out / "stop_times.txt")
    calendar = pd.read_csv(out / "calendar.txt")
    calendar_dates = pd.read_csv(out / "calendar_dates.txt")
    transfers = pd.read_csv(out / "transfers.txt")

    assert set(stops.stop_id) == {"A", "B"}
    assert set(routes.route_id) == {"R1"}
    assert set(agency.agency_id) == {"AG1"}
    assert set(trips.trip_id) == {"T1"}
    assert set(stop_times.stop_id) == {"A", "B"}
    assert not stop_times.arrival_time.isna().any()
    assert not stop_times.departure_time.isna().any()
    assert set(calendar.service_id) == {"WKD"}
    assert set(calendar_dates.service_id) == {"WKD"}
    assert set(transfers.to_stop_id) == {"B"}


def test_filter_gtfs_defaults_to_switzerland_scope(tmp_path: Path):
    raw = tmp_path / "raw"
    out = tmp_path / "filtered"
    raw.mkdir()

    write_table(
        raw,
        "stops.txt",
        ["stop_id", "stop_name", "stop_lat", "stop_lon"],
        [
            ["ZRH", "Zurich HB", 47.378, 8.540],
            ["GVA", "Geneve", 46.210, 6.142],
            ["MIL", "Milano Centrale", 45.487, 9.204],
        ],
    )
    write_table(
        raw,
        "trips.txt",
        ["route_id", "service_id", "trip_id"],
        [["R1", "WKD", "T1"]],
    )
    write_table(
        raw,
        "stop_times.txt",
        ["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"],
        [
            ["T1", "08:00:00", "08:00:00", "ZRH", 1],
            ["T1", "10:50:00", "10:52:00", "GVA", 2],
            ["T1", "14:00:00", "14:00:00", "MIL", 3],
        ],
    )

    filter_gtfs(raw, out)

    stops = pd.read_csv(out / "stops.txt")
    stop_times = pd.read_csv(out / "stop_times.txt")

    assert set(stops.stop_id) == {"ZRH", "GVA"}
    assert set(stop_times.stop_id) == {"ZRH", "GVA"}


def test_filter_gtfs_can_prepare_london_scope(tmp_path: Path):
    raw = tmp_path / "raw"
    out = tmp_path / "filtered"
    raw.mkdir()

    write_table(
        raw,
        "stops.txt",
        ["stop_id", "stop_name", "stop_lat", "stop_lon"],
        [
            ["VIC", "London Victoria", 51.4952, -0.1439],
            ["WAT", "Waterloo", 51.5031, -0.1132],
            ["BHM", "Birmingham New Street", 52.4778, -1.8990],
        ],
    )
    write_table(
        raw,
        "trips.txt",
        ["route_id", "service_id", "trip_id"],
        [["R1", "WKD", "T1"], ["R2", "WKD", "T2"]],
    )
    write_table(
        raw,
        "stop_times.txt",
        ["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"],
        [
            ["T1", "08:00:00", "08:00:00", "VIC", 1],
            ["T1", "08:08:00", "08:08:00", "WAT", 2],
            ["T2", "08:00:00", "08:00:00", "BHM", 1],
        ],
    )

    filter_gtfs(raw, out, REGION_BOUNDS["london"])

    stops = pd.read_csv(out / "stops.txt")
    trips = pd.read_csv(out / "trips.txt")
    stop_times = pd.read_csv(out / "stop_times.txt")

    assert set(stops.stop_id) == {"VIC", "WAT"}
    assert set(trips.trip_id) == {"T1"}
    assert set(stop_times.stop_id) == {"VIC", "WAT"}


def test_resolve_source_url_requires_london_gtfs_source(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("TRANSIT_HEATMAP_LONDON_GTFS_URL", raising=False)

    with pytest.raises(ValueError, match="London setup requires a GTFS schedule ZIP URL"):
        resolve_source_url("london", None)


def test_resolve_source_url_uses_london_gtfs_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TRANSIT_HEATMAP_LONDON_GTFS_URL", "https://example.test/london.zip")

    assert resolve_source_url("london", None) == "https://example.test/london.zip"


def test_main_reports_london_source_requirement(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.delenv("TRANSIT_HEATMAP_LONDON_GTFS_URL", raising=False)
    monkeypatch.setattr(setup_data, "prepare_data", lambda **kwargs: Path("unused"))
    monkeypatch.setattr(
        "sys.argv",
        ["setup_data", "--region", "london"],
    )

    with pytest.raises(SystemExit) as exc_info:
        setup_data.main()

    assert exc_info.value.code == 2
    assert "London setup requires a GTFS schedule ZIP URL" in capsys.readouterr().err


def test_filter_gtfs_writes_minimal_runtime_columns(tmp_path: Path):
    raw = tmp_path / "raw"
    out = tmp_path / "filtered"
    raw.mkdir()

    write_table(
        raw,
        "stops.txt",
        ["stop_id", "stop_name", "stop_lat", "stop_lon", "unused_stop_column"],
        [["ZRH", "Zurich HB", 47.378, 8.540, "drop-me"]],
    )
    write_table(
        raw,
        "trips.txt",
        ["route_id", "service_id", "trip_id", "unused_trip_column"],
        [["R1", "WKD", "T1", "drop-me"]],
    )
    write_table(
        raw,
        "stop_times.txt",
        ["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence", "unused_time_column"],
        [["T1", "08:00:00", "08:00:00", "ZRH", 1, "drop-me"]],
    )

    filter_gtfs(raw, out)

    stops = pd.read_csv(out / "stops.txt")
    trips = pd.read_csv(out / "trips.txt")
    stop_times = pd.read_csv(out / "stop_times.txt")

    assert list(stops.columns) == ["stop_id", "stop_name", "stop_lat", "stop_lon"]
    assert list(trips.columns) == ["route_id", "service_id", "trip_id"]
    assert list(stop_times.columns) == ["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"]


def test_filter_gtfs_preserves_existing_output_when_raw_data_is_malformed(tmp_path: Path):
    raw = tmp_path / "raw"
    out = tmp_path / "filtered"
    raw.mkdir()
    out.mkdir()
    existing = out / "stops.txt"
    existing.write_text("existing,data\n1,2\n", encoding="utf-8")

    write_table(
        raw,
        "stops.txt",
        ["stop_id", "stop_name", "stop_lat", "stop_lon"],
        [["A", "Inside A", 47.37, 8.54]],
    )

    with pytest.raises(FileNotFoundError):
        filter_gtfs(raw, out, Bounds(min_lat=47.0, max_lat=48.0, min_lon=8.0, max_lon=9.0))

    assert existing.read_text(encoding="utf-8") == "existing,data\n1,2\n"


def test_filter_gtfs_cleans_staging_when_raw_data_parse_fails(tmp_path: Path):
    raw = tmp_path / "raw"
    out = tmp_path / "filtered"
    raw.mkdir()
    out.mkdir()
    existing = out / "stops.txt"
    existing.write_text("existing,data\n1,2\n", encoding="utf-8")

    write_table(
        raw,
        "stops.txt",
        ["stop_id", "stop_name", "stop_lat", "stop_lon"],
        [["A", "Inside A", "not-a-latitude", 8.54]],
    )
    write_table(
        raw,
        "trips.txt",
        ["route_id", "service_id", "trip_id"],
        [["R1", "WKD", "T1"]],
    )
    write_table(
        raw,
        "stop_times.txt",
        ["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"],
        [["T1", "08:00:00", "08:00:00", "A", 1]],
    )

    with pytest.raises(ValueError):
        filter_gtfs(raw, out, Bounds(min_lat=47.0, max_lat=48.0, min_lon=8.0, max_lon=9.0))

    assert existing.read_text(encoding="utf-8") == "existing,data\n1,2\n"
    assert not list(tmp_path.glob(".filtered.tmp-*"))


def test_filter_gtfs_rejects_raw_output_collision(tmp_path: Path):
    raw = tmp_path / "raw"
    raw.mkdir()

    with pytest.raises(ValueError):
        filter_gtfs(raw, raw, Bounds(min_lat=47.0, max_lat=48.0, min_lon=8.0, max_lon=9.0))


def test_extract_gtfs_preserves_existing_output_when_zip_is_invalid(tmp_path: Path):
    zip_path = tmp_path / "bad.zip"
    output = tmp_path / "extracted"
    output.mkdir()
    existing = output / "kept.txt"
    existing.write_text("keep me\n", encoding="utf-8")
    zip_path.write_text("not a zip", encoding="utf-8")

    with pytest.raises(zipfile.BadZipFile):
        extract_gtfs(zip_path, output)

    assert existing.read_text(encoding="utf-8") == "keep me\n"


def test_replace_dir_restores_existing_output_when_staging_move_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    staging = tmp_path / ".filtered.tmp-test"
    output = tmp_path / "filtered"
    staging.mkdir()
    output.mkdir()
    (staging / "stops.txt").write_text("new,data\n", encoding="utf-8")
    existing = output / "stops.txt"
    existing.write_text("old,data\n", encoding="utf-8")
    original_replace = Path.replace

    def fail_staging_move(self: Path, target: Path):
        if self == staging and target == output:
            raise OSError("simulated final move failure")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", fail_staging_move)

    with pytest.raises(OSError, match="simulated final move failure"):
        _replace_dir(staging, output)

    assert existing.read_text(encoding="utf-8") == "old,data\n"
    assert not staging.exists()
    assert not list(tmp_path.glob(".filtered.backup-*"))


def test_replace_dir_cleans_staging_when_backup_move_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    staging = tmp_path / ".filtered.tmp-test"
    output = tmp_path / "filtered"
    staging.mkdir()
    output.mkdir()
    (staging / "stops.txt").write_text("new,data\n", encoding="utf-8")
    existing = output / "stops.txt"
    existing.write_text("old,data\n", encoding="utf-8")
    original_replace = Path.replace

    def fail_backup_move(self: Path, target: Path):
        if self == output:
            raise OSError("simulated backup move failure")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", fail_backup_move)

    with pytest.raises(OSError, match="simulated backup move failure"):
        _replace_dir(staging, output)

    assert existing.read_text(encoding="utf-8") == "old,data\n"
    assert not staging.exists()
    assert not list(tmp_path.glob(".filtered.backup-*"))


def test_download_gtfs_uses_temp_zip_and_replaces_destination_after_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    destination = tmp_path / "gtfs.zip"
    seen_temp_paths = []

    def fake_urlretrieve(url: str, filename: Path):
        seen_temp_paths.append(Path(filename))
        with zipfile.ZipFile(filename, "w") as archive:
            archive.writestr("stops.txt", "stop_id\nA\n")
        return filename, None

    monkeypatch.setattr(setup_data.urllib.request, "urlretrieve", fake_urlretrieve)

    result = download_gtfs(destination, source_url="https://example.test/gtfs.zip")

    assert result == destination
    assert seen_temp_paths
    assert seen_temp_paths[0] != destination
    assert zipfile.is_zipfile(destination)
    assert not seen_temp_paths[0].exists()


def test_discover_download_url_warns_when_ckan_discovery_falls_back(monkeypatch: pytest.MonkeyPatch):
    def failing_urlopen(url: str, timeout: int):
        raise OSError("ckan unavailable")

    monkeypatch.setattr(setup_data.urllib.request, "urlopen", failing_urlopen)

    with pytest.warns(RuntimeWarning):
        assert discover_download_url() == setup_data.GEOPS_FALLBACK_URL
