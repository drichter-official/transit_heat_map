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
const departureInput = document.getElementById("departure-time");
const goButton = document.getElementById("go-btn");
const statusEl = document.getElementById("status");

function initMap() {
  map = L.map("map").setView([47.376, 8.541], 12);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(map);

  map.on("click", (event) => {
    setOrigin(event.latlng.lat, event.latlng.lng, "Custom location");
  });

  const now = new Date();
  now.setSeconds(0, 0);
  departureInput.value = new Date(now.getTime() - now.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16);
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

function colorForWeight(weight) {
  if (weight >= 0.8) {
    return "#ef4444";
  }
  if (weight >= 0.6) {
    return "#f97316";
  }
  if (weight >= 0.4) {
    return "#facc15";
  }
  if (weight >= 0.2) {
    return "#16a34a";
  }
  return "#2563eb";
}

function renderHeatmap(points) {
  if (heatLayer) {
    heatLayer.remove();
  }
  map.invalidateSize();
  const circles = points.map((point) => {
    const color = colorForWeight(point.weight);
    return L.circle([point.lat, point.lng], {
      radius: point.radius_m,
      stroke: false,
      color,
      fillColor: color,
      fillOpacity: 0.28,
    });
  });
  heatLayer = L.featureGroup(circles).addTo(map);

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

  setStatus("Computing approximate result...", "loading");
  const params = new URLSearchParams({
    lat: selectedOrigin.lat,
    lon: selectedOrigin.lon,
    minutes: timeSlider.value,
    departure: departureInput.value,
  });
  const response = await fetch(`${API_BASE}/api/heatmap?${params.toString()}`);
  if (!response.ok) {
    throw new Error(`Heatmap request failed: ${response.status}`);
  }
  const data = await response.json();
  renderHeatmap(data.points);
  setStatus(`Approximate result: ${data.stop_count} stops. Refining...`, "loading");
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
  setStatus(`Schedule result: ${data.stop_count} stops in ${data.computation_ms} ms.`, "success");
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
