from pathlib import Path
import zipfile

import pandas as pd
import pytest

import backend.setup_data as setup_data
from backend.setup_data import Bounds, discover_download_url, download_gtfs, extract_gtfs, filter_gtfs
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
    assert set(calendar.service_id) == {"WKD"}
    assert set(calendar_dates.service_id) == {"WKD"}
    assert set(transfers.to_stop_id) == {"B"}


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
