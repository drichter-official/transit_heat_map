# Switzerland Static Network Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate and serve a Switzerland-wide static transit network for GitHub Pages with a compact sharded data layout.

**Architecture:** Add a Python exporter that consumes the filtered GTFS runtime data and writes v2 static artifacts. Update the vanilla JavaScript frontend to load `manifest.json`, `search-index.json`, and graph tile shards lazily, with legacy v1 fallback retained for existing artifacts.

**Tech Stack:** Python 3.12, pytest, pandas/numpy/scipy via the existing backend loader, vanilla JavaScript, Leaflet, GitHub Pages static hosting.

---

## File Structure

- `backend/export_static_network.py`: build static v2 manifest, search index, spatial grid, and graph shards from a filtered GTFS directory.
- `tests/test_static_export.py`: exporter behavior over the tiny GTFS fixture.
- `tests/test_frontend_assets.py`: static v2 frontend contract checks.
- `app.js`: GitHub Pages frontend entry point.
- `frontend/app.js`: local FastAPI-served frontend copy.
- `README.md`: commands for generating and publishing static Switzerland artifacts.
- `static-data/manifest.json`, `static-data/search-index.json`, `static-data/tiles/*.json`: generated Switzerland artifacts.

## Tasks

- [ ] Add failing exporter tests for v2 manifest/search-index/tile output.
- [ ] Implement `backend.export_static_network` with deterministic compact JSON output.
- [ ] Add failing frontend asset tests for v2 static loading symbols.
- [ ] Update both frontend copies to load v2 static artifacts lazily and keep v1 fallback.
- [ ] Generate Switzerland static data from the official Swiss GTFS feed.
- [ ] Verify Python tests and rendered static app behavior.
- [ ] Commit and push `gh-pages`.
