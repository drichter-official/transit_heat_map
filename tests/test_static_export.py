from __future__ import annotations

import json
from pathlib import Path

from backend.gtfs_loader import load_gtfs
from backend.static_export import build_static_network, write_static_network


def test_build_static_network_exports_indexed_browser_graph(tiny_gtfs_dir: Path):
    gtfs = load_gtfs(tiny_gtfs_dir)

    payload = build_static_network(gtfs)

    assert payload["v"] == 1
    assert payload["constants"]["walk_mps"] == 1.39
    assert payload["constants"]["first_walk_m"] == 800
    assert payload["constants"]["transfer_walk_m"] == 400
    assert payload["stops"][0] == ["A", "Zurich Alpha", 47.376, 8.541, "zurich alpha"]
    assert payload["ride_edges"][0] == [[1, 600]]
    assert payload["ride_edges"][1] == [[2, 600]]
    assert any(edge[0] == 1 for edge in payload["walk_edges"][0])
    assert all(edge[0] != 2 for edge in payload["walk_edges"][0])
    assert payload["grid"]
    assert payload["default_center"] == [47.3773, 8.5461]


def test_write_static_network_writes_json_for_pages(tiny_gtfs_dir: Path, tmp_path: Path):
    output_path = tmp_path / "static-data" / "transit-network.json"

    write_static_network(load_gtfs(tiny_gtfs_dir), output_path)

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["stops"][0][1] == "Zurich Alpha"
    assert output_path.is_file()
