# Switzerland Static Network Design

## Goal

Extend the static GitHub Pages app from a Zurich-area network to a Switzerland-wide network, while moving the saved data format toward larger regions without requiring a server.

## Approach

The app will use a versioned static data layout:

- `static-data/manifest.json` describes the region, constants, bounds, stop count, and graph shard files.
- `static-data/search-index.json` stores stop names, quantized coordinates, and the spatial lookup grid needed for search and first-stop lookup.
- `static-data/tiles/*.json` stores graph adjacency rows in fixed stop-index ranges.
- `static-data/transit-network.json` remains as an optional legacy v1 fallback during transition.

The frontend loads the manifest and search index at startup, then loads graph shards on demand while running the browser-side Dijkstra. This keeps the first payload smaller than loading the full graph and lets future larger regions grow by adding more shards.

## Data Encoding

Coordinates are quantized to integer microdegrees using a manifest precision value. This avoids repeated decimal strings while keeping sub-meter precision. Stops are stored as compact arrays:

```json
["stop_id", "Stop Name", 47378177, 8540212, "stop name"]
```

Each graph shard stores rows for a contiguous stop-index range. Each row contains ride edges and walk edges for one stop:

```json
[ [[nextIndex, seconds]], [[nextIndex, meters]] ]
```

Rows with no edges are `[[], []]`. The frontend can load a shard for any stop index by integer division over `shard_size`.

## Switzerland Scope

The existing `backend.setup_data` command already defaults to Swiss GTFS and Swiss geographic bounds. The new exporter consumes `backend/data/filtered` and writes static artifacts from the filtered feed. It does not fetch data itself.

For the committed GitHub Pages artifact, the export command should be:

```powershell
python -m backend.setup_data --region switzerland
python -m backend.export_static_network --region switzerland
```

## Larger Regions

The v2 layout is intended to scale by adding more graph shards and, later, splitting the search index by country or map tile. Europe-wide static routing remains harder than Switzerland because feeds are fragmented and cross-border schedule semantics vary. The v2 layout keeps that option open without adding binary parsing or a build system now.

## Testing

Tests should cover:

- Exporter output shape from a tiny GTFS fixture.
- Quantized coordinates and manifest metadata.
- Shard edge placement for ride and walk edges.
- Frontend contract for manifest/search-index/tile loading.
- Existing v1 frontend helper compatibility where useful.
