const API_BASE = "";

let map;
let heatLayer;
let marker;
let selectedOrigin = null;
let activePollTimer = null;

const searchInput = document.getElementById("stop-search");
const suggestions = document.getElementById("stop-suggestions");
const timeSlider = document.getElementById("time-slider");
const timeLabel = document.getElementById("time-label");
const goButton = document.getElementById("go-btn");
const statusEl = document.getElementById("status");

const OVERLAY_OPACITY = "0.48";
const RENDER_SCALE = 0.45;
const MIN_RENDER_RADIUS_PX = 7;
const HEAT_STOPS = [
  { weight: 0, color: "#2563eb" },
  { weight: 0.25, color: "#16a34a" },
  { weight: 0.5, color: "#facc15" },
  { weight: 0.75, color: "#f97316" },
  { weight: 1, color: "#ef4444" },
];

function initMap() {
  map = L.map("map").setView([47.376, 8.541], 12);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(map);

  map.on("click", (event) => {
    setOrigin(event.latlng.lat, event.latlng.lng, "Custom location");
  });

}

function setStatus(message, mode = "neutral") {
  statusEl.textContent = message;
  statusEl.dataset.mode = mode;
}

function setOrigin(lat, lon, name) {
  selectedOrigin = { lat, lon, name };
  if (marker) {
    marker.remove();
  }
  marker = L.marker([lat, lon]).addTo(map).bindPopup(name);
  map.panTo([lat, lon]);
}

function hexToRgb(hex) {
  return {
    r: Number.parseInt(hex.slice(1, 3), 16),
    g: Number.parseInt(hex.slice(3, 5), 16),
    b: Number.parseInt(hex.slice(5, 7), 16),
  };
}

function interpolateColor(startColor, endColor, fraction) {
  const start = hexToRgb(startColor);
  const end = hexToRgb(endColor);
  const mix = Math.max(0, Math.min(1, fraction));
  return {
    r: Math.round(start.r + (end.r - start.r) * mix),
    g: Math.round(start.g + (end.g - start.g) * mix),
    b: Math.round(start.b + (end.b - start.b) * mix),
  };
}

function rgbForWeight(weight) {
  const clamped = Math.max(0, Math.min(1, weight));
  for (let index = 1; index < HEAT_STOPS.length; index += 1) {
    const previous = HEAT_STOPS[index - 1];
    const next = HEAT_STOPS[index];
    if (clamped <= next.weight) {
      const span = next.weight - previous.weight;
      return interpolateColor(previous.color, next.color, (clamped - previous.weight) / span);
    }
  }
  return hexToRgb(HEAT_STOPS[HEAT_STOPS.length - 1].color);
}

function colorForWeight(weight) {
  const rgb = rgbForWeight(weight);
  return `rgb(${rgb.r}, ${rgb.g}, ${rgb.b})`;
}

function metersPerPixel(lat, zoom) {
  return (40075016.686 * Math.cos((lat * Math.PI) / 180)) / (256 * 2 ** zoom);
}

function extendBoundsByRadius(bounds, point) {
  const latOffset = point.radius_m / 111320;
  const lngScale = 111320 * Math.max(0.2, Math.cos((point.lat * Math.PI) / 180));
  const lngOffset = point.radius_m / lngScale;
  bounds.extend([point.lat - latOffset, point.lng - lngOffset]);
  bounds.extend([point.lat + latOffset, point.lng + lngOffset]);
}

function boundsForPoints(points) {
  const bounds = L.latLngBounds();
  points.forEach((point) => extendBoundsByRadius(bounds, point));
  return bounds;
}

function createReachabilityLayer(points) {
  const ReachabilityCanvasLayer = L.Layer.extend({
    onAdd(layerMap) {
      this._map = layerMap;
      this._canvas = L.DomUtil.create("canvas", "reachability-canvas");
      this._canvas.style.opacity = OVERLAY_OPACITY;
      this._canvas.style.pointerEvents = "none";
      this._ctx = this._canvas.getContext("2d");
      layerMap.getPanes().overlayPane.appendChild(this._canvas);
      layerMap.on("moveend zoomend resize", this._reset, this);
      this._reset();
    },
    onRemove(layerMap) {
      layerMap.off("moveend zoomend resize", this._reset, this);
      L.DomUtil.remove(this._canvas);
    },
    getBounds() {
      return boundsForPoints(points);
    },
    _reset() {
      const size = this._map.getSize();
      const topLeft = this._map.containerPointToLayerPoint([0, 0]);
      this._topLeft = topLeft;
      L.DomUtil.setPosition(this._canvas, topLeft);
      this._canvas.width = Math.max(1, Math.ceil(size.x * RENDER_SCALE));
      this._canvas.height = Math.max(1, Math.ceil(size.y * RENDER_SCALE));
      this._canvas.style.width = `${size.x}px`;
      this._canvas.style.height = `${size.y}px`;
      this._draw();
    },
    _draw() {
      if (!this._ctx) {
        return;
      }
      const ctx = this._ctx;
      const width = this._canvas.width;
      const height = this._canvas.height;
      const weights = new Float32Array(width * height);
      const sortedPoints = [...points].sort((a, b) => a.weight - b.weight);
      sortedPoints.forEach((point) => {
        const center = this._map.latLngToLayerPoint([point.lat, point.lng]).subtract(this._topLeft);
        const cx = center.x * RENDER_SCALE;
        const cy = center.y * RENDER_SCALE;
        const geographicRadiusPx = Math.max(1, (point.radius_m / metersPerPixel(point.lat, this._map.getZoom())) * RENDER_SCALE);
        const radiusPx = Math.max(geographicRadiusPx, MIN_RENDER_RADIUS_PX * RENDER_SCALE);
        const minX = Math.max(0, Math.floor(cx - radiusPx));
        const maxX = Math.min(width - 1, Math.ceil(cx + radiusPx));
        const minY = Math.max(0, Math.floor(cy - radiusPx));
        const maxY = Math.min(height - 1, Math.ceil(cy + radiusPx));
        if (
          maxX < 0 ||
          maxY < 0 ||
          minX >= width ||
          minY >= height
        ) {
          return;
        }
        for (let y = minY; y <= maxY; y += 1) {
          const dy = y - cy;
          for (let x = minX; x <= maxX; x += 1) {
            const dx = x - cx;
            const distance = Math.sqrt(dx * dx + dy * dy);
            if (distance > radiusPx) {
              continue;
            }
            const candidate = point.weight * (1 - distance / radiusPx);
            const index = y * width + x;
            if (candidate > weights[index]) {
              weights[index] = candidate;
            }
          }
        }
      });
      const image = ctx.createImageData(width, height);
      for (let index = 0; index < weights.length; index += 1) {
        const weight = weights[index];
        if (weight <= 0) {
          continue;
        }
        const rgb = rgbForWeight(weight);
        const offset = index * 4;
        image.data[offset] = rgb.r;
        image.data[offset + 1] = rgb.g;
        image.data[offset + 2] = rgb.b;
        image.data[offset + 3] = 255;
      }
      ctx.putImageData(image, 0, 0);
    },
  });

  return new ReachabilityCanvasLayer();
}

function renderHeatmap(points) {
  if (heatLayer) {
    heatLayer.remove();
  }
  map.invalidateSize();
  heatLayer = createReachabilityLayer(points).addTo(map);

  if (points.length > 0) {
    map.fitBounds(heatLayer.getBounds(), { padding: [30, 30], maxZoom: 13 });
  }
  requestAnimationFrame(() => map.invalidateSize());
}

async function searchStops(query) {
  const response = await fetch(`${API_BASE}/api/stops/search?q=${encodeURIComponent(query)}`);
  if (!response.ok) {
    throw new Error("Stop search failed");
  }
  return response.json();
}

async function fetchHeatmap() {
  if (!selectedOrigin) {
    setStatus("Select a stop or click the map first.", "warning");
    return;
  }
  if (activePollTimer) {
    clearTimeout(activePollTimer);
  }

  setStatus("Computing quick network estimate...", "loading");
  const params = new URLSearchParams({
    lat: selectedOrigin.lat,
    lon: selectedOrigin.lon,
    minutes: timeSlider.value,
  });
  const response = await fetch(`${API_BASE}/api/heatmap?${params.toString()}`);
  if (!response.ok) {
    throw new Error(`Heatmap request failed: ${response.status}`);
  }
  const data = await response.json();
  renderHeatmap(data.points);
  setStatus(`Quick estimate: ${data.stop_count} stops. Checking typical 2-hour connection window...`, "loading");
  pollJob(data.job_id);
}

async function pollJob(jobId) {
  const response = await fetch(`${API_BASE}/api/jobs/${encodeURIComponent(jobId)}`);
  if (!response.ok) {
    setStatus("Refinement status unavailable; keeping approximate result.", "warning");
    return;
  }
  const data = await response.json();
  if (data.status === "running") {
    activePollTimer = setTimeout(() => pollJob(jobId), 1200);
    return;
  }
  if (data.status === "failed") {
    setStatus("Refinement failed; keeping approximate result.", "warning");
    return;
  }
  renderHeatmap(data.points);
  setStatus(`Typical connection-window result: ${data.stop_count} stops in ${data.computation_ms} ms.`, "success");
}

let debounceTimer;
searchInput.addEventListener("input", () => {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(async () => {
    const query = searchInput.value.trim();
    if (query.length < 2) {
      suggestions.innerHTML = "";
      return;
    }
    try {
      const stops = await searchStops(query);
      const items = stops.map((stop) => {
        const item = document.createElement("li");
        item.dataset.lat = stop.lat;
        item.dataset.lon = stop.lon;
        item.dataset.name = stop.name;
        item.textContent = stop.name;
        return item;
      });
      suggestions.replaceChildren(...items);
    } catch (error) {
      setStatus(error.message, "error");
    }
  }, 250);
});

suggestions.addEventListener("click", (event) => {
  const item = event.target.closest("li");
  if (!item) {
    return;
  }
  searchInput.value = item.dataset.name;
  suggestions.innerHTML = "";
  setOrigin(Number(item.dataset.lat), Number(item.dataset.lon), item.dataset.name);
});

timeSlider.addEventListener("input", () => {
  timeLabel.textContent = timeSlider.value;
});

goButton.addEventListener("click", async () => {
  try {
    await fetchHeatmap();
  } catch (error) {
    setStatus(error.message, "error");
  }
});

initMap();
