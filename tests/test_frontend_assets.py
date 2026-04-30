from pathlib import Path


def test_frontend_uses_leaflet_and_not_google_maps():
    html = Path("frontend/index.html").read_text(encoding="utf-8")

    assert "leaflet" in html.lower()
    assert "leaflet-heat" not in html.lower()
    assert "maps.googleapis.com" not in html
    assert "app.js?v=smooth-canvas-heat" in html


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
    assert js.index("map.invalidateSize()") < js.index("heatLayer = createReachabilityLayer")


def test_frontend_map_has_stable_responsive_height():
    css = Path("frontend/style.css").read_text(encoding="utf-8")

    assert "height: 100vh;" in css
    assert "height: 58vh;" in css


def test_frontend_renders_single_opacity_canvas_overlay():
    js = Path("frontend/app.js").read_text(encoding="utf-8")

    assert "createReachabilityLayer" in js
    assert "canvas.style.opacity" in js
    assert "Float32Array" in js
    assert "putImageData" in js
    assert "fillOpacity" not in js
    assert "L.circle" not in js
    assert "L.heatLayer" not in js


def test_frontend_interpolates_heat_colors_smoothly():
    js = Path("frontend/app.js").read_text(encoding="utf-8")

    assert "function interpolateColor" in js
    assert "HEAT_STOPS" in js
    assert "rgbForWeight(weight)" in js
    assert "if (weight >= 0.8)" not in js
