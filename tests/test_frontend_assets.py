from pathlib import Path


def test_frontend_uses_leaflet_and_not_google_maps():
    html = Path("frontend/index.html").read_text(encoding="utf-8")

    assert "leaflet" in html.lower()
    assert "leaflet-heat" not in html.lower()
    assert "maps.googleapis.com" not in html
    assert "app.js?v=walking-radius-2" in html


def test_frontend_polling_and_status_contracts_exist():
    js = Path("frontend/app.js").read_text(encoding="utf-8")

    assert "fetchHeatmap" in js
    assert "pollJob" in js
    assert "Approximate result" in js
    assert "Schedule result" in js


def test_frontend_invalidates_leaflet_size_before_heat_render():
    js = Path("frontend/app.js").read_text(encoding="utf-8")

    assert "map.invalidateSize()" in js
    assert "requestAnimationFrame(() => map.invalidateSize())" in js
    assert js.index("map.invalidateSize()") < js.index("L.circle")


def test_frontend_map_has_stable_responsive_height():
    css = Path("frontend/style.css").read_text(encoding="utf-8")

    assert "height: 100vh;" in css
    assert "height: 58vh;" in css


def test_frontend_uses_tighter_station_dot_heat_kernel():
    js = Path("frontend/app.js").read_text(encoding="utf-8")

    assert "L.circle" in js
    assert "L.featureGroup" in js
    assert "radius: point.radius_m" in js
    assert "colorForWeight(point.weight)" in js
    assert "L.heatLayer" not in js
