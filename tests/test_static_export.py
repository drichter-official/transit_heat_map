import json
from pathlib import Path

from backend.export_static_network import export_static_network


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_export_static_network_writes_manifest_search_index_and_tiles(tiny_gtfs_dir: Path, tmp_path: Path):
    output_dir = tmp_path / "static-data"

    summary = export_static_network(
        data_dir=tiny_gtfs_dir,
        output_dir=output_dir,
        region="testland",
        shard_size=2,
    )

    manifest = _read_json(output_dir / "manifest.json")
    search_index = _read_json(output_dir / "search-index.json")
    first_tile = _read_json(output_dir / "tiles" / "0000.json")
    second_tile = _read_json(output_dir / "tiles" / "0001.json")

    assert summary["stop_count"] == 4
    assert manifest["v"] == 2
    assert manifest["region"] == "testland"
    assert manifest["stop_count"] == 4
    assert manifest["shard_size"] == 2
    assert manifest["coordinate_precision"] == 1_000_000
    assert manifest["search_index"] == "search-index.json"
    assert [tile["path"] for tile in manifest["tiles"]] == ["tiles/0000.json", "tiles/0001.json"]

    assert search_index["v"] == 2
    assert search_index["coordinate_precision"] == 1_000_000
    assert search_index["stops"][0][:2] == ["A", "Zurich Alpha"]
    assert isinstance(search_index["stops"][0][2], int)
    assert isinstance(search_index["stops"][0][3], int)
    assert "zurich alpha" in search_index["stops"][0][4]
    assert search_index["grid"]

    assert first_tile["v"] == 2
    assert first_tile["start"] == 0
    assert len(first_tile["rows"]) == 2
    assert first_tile["rows"][0][0] == [[1, 600]]
    assert first_tile["rows"][1][0] == [[2, 600]]

    assert second_tile["start"] == 2
    assert len(second_tile["rows"]) == 2


def test_export_static_network_removes_stale_tile_files(tiny_gtfs_dir: Path, tmp_path: Path):
    output_dir = tmp_path / "static-data"
    stale_tile = output_dir / "tiles" / "9999.json"
    stale_tile.parent.mkdir(parents=True)
    stale_tile.write_text("{}", encoding="utf-8")

    export_static_network(
        data_dir=tiny_gtfs_dir,
        output_dir=output_dir,
        region="testland",
        shard_size=3,
    )

    manifest = _read_json(output_dir / "manifest.json")

    assert not stale_tile.exists()
    assert [tile["path"] for tile in manifest["tiles"]] == ["tiles/0000.json", "tiles/0001.json"]
