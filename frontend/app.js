const PAGE_PARAMS = new URLSearchParams(window.location.search);
const EXPLICIT_API_BASE = PAGE_PARAMS.get("api") || "";
const STORED_API_BASE = window.localStorage.getItem("transitHeatMapApiBase") || "";
const FORCE_STATIC = PAGE_PARAMS.get("static") === "1";
const IS_LOCAL_HTTP_HOST = ["localhost", "127.0.0.1", "::1"].includes(window.location.hostname);
const USE_STATIC_DATA = !EXPLICIT_API_BASE && window.location.protocol !== "file:" && (
  FORCE_STATIC
  || !IS_LOCAL_HTTP_HOST
);
const API_BASE_RAW = EXPLICIT_API_BASE || (USE_STATIC_DATA ? "" : STORED_API_BASE);
const API_BASE = API_BASE_RAW.replace(/\/$/, "");
const STATIC_DATA_BASE = "static-data/";
const STATIC_MANIFEST_URL = `${STATIC_DATA_BASE}manifest.json`;
const STATIC_LEGACY_DATA_URL = `${STATIC_DATA_BASE}transit-network.json`;
const ZURICH_CENTER = [47.376, 8.541];
const CARTO_ATTRIBUTION = "&copy; OpenStreetMap contributors &copy; CARTO";
const ESRI_ATTRIBUTION = "Tiles &copy; Esri";
const BASE_LAYERS = {
  standard: [
    {
      url: "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
      options: { maxZoom: 19, attribution: CARTO_ATTRIBUTION },
    },
  ],
  hybrid: [
    {
      url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      options: { maxZoom: 19, attribution: ESRI_ATTRIBUTION },
    },
    {
      url: "https://{s}.basemaps.cartocdn.com/light_only_labels/{z}/{x}/{y}{r}.png",
      options: { maxZoom: 19, attribution: CARTO_ATTRIBUTION, pane: "tilePane" },
    },
  ],
  satellite: [
    {
      url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      options: { maxZoom: 19, attribution: ESRI_ATTRIBUTION },
    },
  ],
};
const TRANSIT_LINE_COLORS = ["#0ea5e9", "#22c55e", "#f59e0b", "#ef4444", "#8b5cf6", "#111827"];

let map;
let heatLayer;
let marker;
let tileLayers = [];
let transitLineLayer;
let selectedOrigin = null;
let activePollTimer = null;
let staticNetworkPromise = null;
let activeNetwork = null;
let activeBaseLayer = "standard";
let transitLinesVisible = true;

const searchInput = document.getElementById("stop-search");
const suggestions = document.getElementById("stop-suggestions");
const timeSlider = document.getElementById("time-slider");
const timeLabel = document.getElementById("time-label");
const goButton = document.getElementById("go-btn");
const statusEl = document.getElementById("status");
const statusCard = document.querySelector(".status-card");
const layerToggle = document.getElementById("layer-toggle");
const layerMenu = document.getElementById("layer-menu");
const layerOptions = document.querySelectorAll(".layer-option");
const transitLinesToggle = document.getElementById("transit-lines-toggle");

const OVERLAY_OPACITY = "0.48";
const RENDER_SCALE = 0.45;
const MIN_RENDER_RADIUS_PX = 7;
const STATIC_HEATMAP_POINT_LIMIT = 30000;
const HEAT_STOPS = [
  { weight: 0, color: "#2563eb" },
  { weight: 0.25, color: "#16a34a" },
  { weight: 0.5, color: "#facc15" },
  { weight: 0.75, color: "#f97316" },
  { weight: 1, color: "#ef4444" },
];

function setBaseLayer(layerName = activeBaseLayer) {
  activeBaseLayer = BASE_LAYERS[layerName] ? layerName : "standard";
  tileLayers.forEach((layer) => layer.remove());
  tileLayers = BASE_LAYERS[activeBaseLayer].map((definition) => (
    L.tileLayer(definition.url, definition.options).addTo(map)
  ));
  layerOptions.forEach((option) => {
    option.setAttribute("aria-pressed", String(option.dataset.layer === activeBaseLayer));
  });
}

function setLayerMenuOpen(isOpen) {
  layerMenu.hidden = !isOpen;
  layerToggle.setAttribute("aria-expanded", String(isOpen));
}

function originIcon() {
  return L.divIcon({
    className: "origin-marker",
    html: '<span class="origin-pin"></span>',
    iconSize: [28, 28],
    iconAnchor: [14, 14],
  });
}

function initMap() {
  map = L.map("map", { zoomControl: false }).setView([47.376, 8.541], 12);
  L.control.zoom({ position: "topright" }).addTo(map);
  setBaseLayer();

  map.on("click", (event) => {
    setOrigin(event.latlng.lat, event.latlng.lng, "Custom location");
  });
}

function setStatus(message, mode = "neutral") {
  statusEl.textContent = message;
  statusEl.dataset.mode = mode;
  if (statusCard) {
    statusCard.dataset.mode = mode;
  }
}

function setOrigin(lat, lon, name) {
  selectedOrigin = { lat, lon, name };
  if (marker) {
    marker.remove();
  }
  marker = L.marker([lat, lon], { icon: originIcon() }).addTo(map).bindPopup(name);
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

function distanceMeters(lat1, lon1, lat2, lon2) {
  const earthRadiusM = 6371000;
  const toRad = Math.PI / 180;
  const dlat = (lat2 - lat1) * toRad;
  const dlon = (lon2 - lon1) * toRad;
  const a = Math.sin(dlat / 2) ** 2
    + Math.cos(lat1 * toRad) * Math.cos(lat2 * toRad) * Math.sin(dlon / 2) ** 2;
  return 2 * earthRadiusM * Math.asin(Math.sqrt(a));
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

function colorForTransitSegment(fromStop, toStop, fromIndex, toIndex) {
  const angle = Math.atan2(toStop.lat - fromStop.lat, toStop.lon - fromStop.lon);
  const normalized = (angle + Math.PI) / (Math.PI * 2);
  const colorIndex = Math.floor(normalized * TRANSIT_LINE_COLORS.length + Math.abs(fromIndex - toIndex)) % TRANSIT_LINE_COLORS.length;
  return TRANSIT_LINE_COLORS[colorIndex];
}

function transitLineStyleForZoom(zoom) {
  if (zoom < 12) {
    return null;
  }
  if (zoom < 13) {
    return { alpha: 0.28, maxDistanceM: 1800, width: 0.85 };
  }
  if (zoom < 14) {
    return { alpha: 0.46, maxDistanceM: 3200, width: 1.15 };
  }
  return { alpha: 0.64, maxDistanceM: 5200, width: 1.5 };
}

function buildTransitLineSegments(stops, rideEdges) {
  const seen = new Set();
  const segments = [];
  rideEdges.forEach((edges, fromIndex) => {
    const fromStop = stops[fromIndex];
    if (!fromStop || !edges) {
      return;
    }
    edges.forEach(([toIndex]) => {
      const toStop = stops[toIndex];
      if (!toStop) {
        return;
      }
      const key = fromIndex < toIndex ? `${fromIndex}:${toIndex}` : `${toIndex}:${fromIndex}`;
      if (seen.has(key)) {
        return;
      }
      seen.add(key);
      segments.push({
        fromLat: fromStop.lat,
        fromLng: fromStop.lon,
        toLat: toStop.lat,
        toLng: toStop.lon,
        distanceM: distanceMeters(fromStop.lat, fromStop.lon, toStop.lat, toStop.lon),
        color: colorForTransitSegment(fromStop, toStop, fromIndex, toIndex),
      });
    });
  });
  return segments;
}

function createTransitLineLayer(segments) {
  const TransitLineCanvasLayer = L.Layer.extend({
    onAdd(layerMap) {
      this._map = layerMap;
      this._canvas = L.DomUtil.create("canvas", "transit-line-canvas");
      this._canvas.style.opacity = "0.88";
      this._canvas.style.zIndex = "430";
      this._ctx = this._canvas.getContext("2d");
      layerMap.getPanes().overlayPane.appendChild(this._canvas);
      layerMap.on("moveend zoomend resize", this._reset, this);
      this._reset();
    },
    onRemove(layerMap) {
      layerMap.off("moveend zoomend resize", this._reset, this);
      L.DomUtil.remove(this._canvas);
    },
    _reset() {
      const size = this._map.getSize();
      const topLeft = this._map.containerPointToLayerPoint([0, 0]);
      this._topLeft = topLeft;
      L.DomUtil.setPosition(this._canvas, topLeft);
      this._canvas.width = Math.max(1, Math.ceil(size.x));
      this._canvas.height = Math.max(1, Math.ceil(size.y));
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
      const style = transitLineStyleForZoom(this._map.getZoom());
      ctx.clearRect(0, 0, width, height);
      if (!style) {
        return;
      }
      ctx.globalAlpha = style.alpha;
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      ctx.lineWidth = style.width;
      segments.forEach((segment) => {
        if (segment.distanceM > style.maxDistanceM) {
          return;
        }
        const from = this._map.latLngToLayerPoint([segment.fromLat, segment.fromLng]).subtract(this._topLeft);
        const to = this._map.latLngToLayerPoint([segment.toLat, segment.toLng]).subtract(this._topLeft);
        const margin = 80;
        if (
          (from.x < -margin && to.x < -margin) ||
          (from.y < -margin && to.y < -margin) ||
          (from.x > width + margin && to.x > width + margin) ||
          (from.y > height + margin && to.y > height + margin)
        ) {
          return;
        }
        ctx.strokeStyle = segment.color;
        ctx.beginPath();
        ctx.moveTo(from.x, from.y);
        ctx.lineTo(to.x, to.y);
        ctx.stroke();
      });
    },
  });

  return new TransitLineCanvasLayer();
}

function setTransitLineLayer() {
  if (transitLineLayer) {
    transitLineLayer.remove();
    transitLineLayer = null;
  }
  if (activeNetwork?.lineSegments?.length && transitLinesVisible) {
    transitLineLayer = createTransitLineLayer(activeNetwork.lineSegments).addTo(map);
  }
  transitLinesToggle.setAttribute("aria-pressed", String(transitLinesVisible));
}

function createReachabilityLayer(points) {
  const ReachabilityCanvasLayer = L.Layer.extend({
    onAdd(layerMap) {
      this._map = layerMap;
      this._canvas = L.DomUtil.create("canvas", "reachability-canvas");
      this._canvas.style.opacity = OVERLAY_OPACITY;
      this._canvas.style.pointerEvents = "none";
      this._canvas.style.zIndex = "420";
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
    const isCompact = window.matchMedia("(max-width: 720px)").matches;
    map.fitBounds(heatLayer.getBounds(), isCompact
      ? { padding: [28, 28], maxZoom: 13 }
      : { paddingTopLeft: [410, 120], paddingBottomRight: [88, 120], maxZoom: 13 });
  }
  requestAnimationFrame(() => map.invalidateSize());
}

function prepareStaticNetwork(payload) {
  const constants = {
    walk_mps: 1.39,
    first_walk_m: 800,
    transfer_walk_m: 400,
    grid_degrees: 0.01,
    ...payload.constants,
  };
  const stops = payload.stops.map((entry, index) => ({
    index,
    id: entry[0],
    name: entry[1],
    lat: Number(entry[2]),
    lon: Number(entry[3]),
    search: entry[4] || String(entry[1]).toLowerCase(),
  }));
  return {
    version: 1,
    constants,
    defaultCenter: payload.default_center || [47.376, 8.541],
    stops,
    grid: payload.grid || {},
    rideEdges: payload.ride_edges || [],
    walkEdges: payload.walk_edges || [],
    lineSegments: buildTransitLineSegments(stops, payload.ride_edges || []),
  };
}

function decodeCoordinate(value, precision) {
  return Number(value) / precision;
}

function staticDataUrl(path) {
  return `${STATIC_DATA_BASE}${path}`;
}

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Static network data unavailable: ${response.status}`);
  }
  return response.json();
}

function prepareStaticV2Network(manifest, searchIndex) {
  const precision = manifest.coordinate_precision || searchIndex.coordinate_precision || 1000000;
  const constants = {
    walk_mps: 1.39,
    first_walk_m: 800,
    transfer_walk_m: 400,
    grid_degrees: searchIndex.grid_degrees || 0.01,
    ...manifest.constants,
  };
  const stops = searchIndex.stops.map((entry, index) => ({
    index,
    id: entry[0],
    name: entry[1],
    lat: decodeCoordinate(entry[2], precision),
    lon: decodeCoordinate(entry[3], precision),
    search: entry[4] || String(entry[1]).toLowerCase(),
  }));
  return {
    version: 2,
    constants,
    defaultCenter: manifest.default_center || [47.376, 8.541],
    stops,
    grid: searchIndex.grid || {},
    tiles: manifest.tiles || [],
    shardSize: manifest.shard_size || stops.length || 1,
    tilePromises: new Map(),
    lineSegments: [],
    lineSegmentsPromise: null,
  };
}

async function loadStaticManifest() {
  const response = await fetch(STATIC_MANIFEST_URL);
  if (!response.ok) {
    return null;
  }
  return response.json();
}

async function loadStaticNetwork() {
  if (!USE_STATIC_DATA) {
    return null;
  }
  const manifest = await loadStaticManifest();
  if (manifest && manifest.v === 2) {
    const searchIndex = await fetchJson(staticDataUrl(manifest.search_index || "search-index.json"));
    const network = prepareStaticV2Network(manifest, searchIndex);
    activeNetwork = network;
    map.setView(ZURICH_CENTER, 13);
    setStatus(`Static ${manifest.region || "network"} ready: ${network.stops.length} stops.`, "success");
    loadTransitLineSegments(network);
    return network;
  }

  const network = prepareStaticNetwork(await fetchJson(STATIC_LEGACY_DATA_URL));
  activeNetwork = network;
  map.setView(ZURICH_CENTER, 13);
  setTransitLineLayer();
  setStatus(`Static network ready: ${network.stops.length} stops.`, "success");
  return network;
}

function staticNetwork() {
  if (!staticNetworkPromise) {
    staticNetworkPromise = loadStaticNetwork().catch((error) => {
      setStatus(error.message, "error");
      return null;
    });
  }
  return staticNetworkPromise;
}

function stopSearchSortKey(stop) {
  return [stop.name, stop.id.includes(":") ? 1 : 0, stop.id];
}

function compareStopSearch(a, b) {
  const left = stopSearchSortKey(a);
  const right = stopSearchSortKey(b);
  for (let index = 0; index < left.length; index += 1) {
    if (left[index] < right[index]) {
      return -1;
    }
    if (left[index] > right[index]) {
      return 1;
    }
  }
  return 0;
}

function searchStaticStops(network, query) {
  const needle = query.toLowerCase();
  const results = network.stops
    .filter((stop) => stop.search.includes(needle))
    .sort(compareStopSearch);
  const byStationKey = new Map();
  results.forEach((stop) => {
    const key = `${stop.name.toLowerCase()}|${stop.lat.toFixed(6)}|${stop.lon.toFixed(6)}`;
    if (!byStationKey.has(key)) {
      byStationKey.set(key, stop);
    }
  });
  return [...byStationKey.values()].sort(compareStopSearch).slice(0, 10);
}

function gridKey(latIndex, lonIndex) {
  return `${latIndex}:${lonIndex}`;
}

function staticStopsWithinRadius(network, lat, lon, radiusM) {
  const gridDegrees = network.constants.grid_degrees;
  const latCell = Math.floor(lat / gridDegrees);
  const lonCell = Math.floor(lon / gridDegrees);
  const latCells = Math.ceil((radiusM / 111320) / gridDegrees) + 1;
  const lonScale = 111320 * Math.max(0.2, Math.cos((lat * Math.PI) / 180));
  const lonCells = Math.ceil((radiusM / lonScale) / gridDegrees) + 1;
  const candidateIndexes = new Set();

  for (let latOffset = -latCells; latOffset <= latCells; latOffset += 1) {
    for (let lonOffset = -lonCells; lonOffset <= lonCells; lonOffset += 1) {
      const indexes = network.grid[gridKey(latCell + latOffset, lonCell + lonOffset)] || [];
      indexes.forEach((index) => candidateIndexes.add(index));
    }
  }

  const candidates = candidateIndexes.size ? [...candidateIndexes] : network.stops.map((stop) => stop.index);
  return candidates
    .map((index) => {
      const stop = network.stops[index];
      return [index, distanceMeters(lat, lon, stop.lat, stop.lon)];
    })
    .filter((item) => item[1] <= radiusM)
    .sort((a, b) => a[1] - b[1]);
}

function heapPush(heap, item) {
  heap.push(item);
  let index = heap.length - 1;
  while (index > 0) {
    const parent = Math.floor((index - 1) / 2);
    if (heap[parent][0] <= item[0]) {
      break;
    }
    heap[index] = heap[parent];
    index = parent;
  }
  heap[index] = item;
}

function heapPop(heap) {
  if (heap.length === 1) {
    return heap.pop();
  }
  const first = heap[0];
  const item = heap.pop();
  let index = 0;
  while (true) {
    const left = index * 2 + 1;
    const right = left + 1;
    if (left >= heap.length) {
      break;
    }
    let child = left;
    if (right < heap.length && heap[right][0] < heap[left][0]) {
      child = right;
    }
    if (heap[child][0] >= item[0]) {
      break;
    }
    heap[index] = heap[child];
    index = child;
  }
  heap[index] = item;
  return first;
}

function pushStaticBest(heap, best, stopIndex, elapsedSec, maxTravelSec) {
  if (elapsedSec <= maxTravelSec && elapsedSec < best[stopIndex]) {
    best[stopIndex] = elapsedSec;
    heapPush(heap, [elapsedSec, stopIndex]);
  }
}

async function loadStaticTile(network, stopIndex) {
  if (network.version !== 2) {
    return null;
  }
  const tileIndex = Math.floor(stopIndex / network.shardSize);
  const tile = network.tiles[tileIndex];
  if (!tile) {
    throw new Error(`Static network tile missing for stop ${stopIndex}`);
  }
  if (!network.tilePromises.has(tileIndex)) {
    network.tilePromises.set(tileIndex, fetchJson(staticDataUrl(tile.path)));
  }
  return network.tilePromises.get(tileIndex);
}

async function buildV2TransitLineSegments(network) {
  const rideEdges = Array.from({ length: network.stops.length }, () => []);
  const tiles = await Promise.all(
    network.tiles.map((tile) => loadStaticTile(network, tile.start)),
  );
  tiles.forEach((tile) => {
    (tile.rows || []).forEach((row, offset) => {
      rideEdges[tile.start + offset] = row[0] || [];
    });
  });
  return buildTransitLineSegments(network.stops, rideEdges);
}

async function loadTransitLineSegments(network) {
  if (network.lineSegments?.length) {
    setTransitLineLayer();
    return;
  }
  if (!network.lineSegmentsPromise) {
    network.lineSegmentsPromise = buildV2TransitLineSegments(network)
      .then((segments) => {
        network.lineSegments = segments;
        return segments;
      })
      .catch(() => []);
  }
  await network.lineSegmentsPromise;
  setTransitLineLayer();
}

async function staticEdgesForStop(network, stopIndex) {
  if (network.version !== 2) {
    return {
      rideEdges: network.rideEdges[stopIndex] || [],
      walkEdges: network.walkEdges[stopIndex] || [],
    };
  }
  const tile = await loadStaticTile(network, stopIndex);
  const row = (tile.rows || [])[stopIndex - tile.start] || [[], []];
  return {
    rideEdges: row[0] || [],
    walkEdges: row[1] || [],
  };
}

async function computeStaticReachability(network, originLat, originLon, minutes) {
  const maxTravelSec = minutes * 60;
  const best = new Array(network.stops.length).fill(Number.POSITIVE_INFINITY);
  const heap = [];

  staticStopsWithinRadius(network, originLat, originLon, network.constants.first_walk_m)
    .forEach(([stopIndex, distM]) => {
      pushStaticBest(heap, best, stopIndex, distM / network.constants.walk_mps, maxTravelSec);
    });

  while (heap.length > 0) {
    const [elapsedSec, stopIndex] = heapPop(heap);
    if (elapsedSec > best[stopIndex]) {
      continue;
    }
    const edges = await staticEdgesForStop(network, stopIndex);
    edges.walkEdges.forEach(([nextStopIndex, distM]) => {
      pushStaticBest(heap, best, nextStopIndex, elapsedSec + distM / network.constants.walk_mps, maxTravelSec);
    });
    edges.rideEdges.forEach(([nextStopIndex, travelSec]) => {
      pushStaticBest(heap, best, nextStopIndex, elapsedSec + travelSec, maxTravelSec);
    });
  }

  return best;
}

function buildStaticHeatmapPoints(network, best, minutes) {
  const maxTravelSec = minutes * 60;
  const bestByCoordinate = new Set();
  const points = [];

  best
    .map((elapsedSec, stopIndex) => [elapsedSec, stopIndex])
    .filter(([elapsedSec]) => Number.isFinite(elapsedSec))
    .sort((a, b) => a[0] - b[0])
    .forEach(([elapsedSec, stopIndex]) => {
      const stop = network.stops[stopIndex];
      const coordinateKey = `${stop.lat.toFixed(7)}|${stop.lon.toFixed(7)}`;
      if (bestByCoordinate.has(coordinateKey)) {
        return;
      }
      bestByCoordinate.add(coordinateKey);
      const remainingSec = Math.max(0, maxTravelSec - elapsedSec);
      points.push({
        lat: stop.lat,
        lng: stop.lon,
        weight: maxTravelSec <= 0 ? 0 : Number((remainingSec / maxTravelSec).toFixed(4)),
        radius_m: Number((remainingSec * network.constants.walk_mps).toFixed(1)),
      });
    });

  return points.slice(0, STATIC_HEATMAP_POINT_LIMIT);
}

async function searchStops(query) {
  const network = await staticNetwork();
  if (network) {
    return searchStaticStops(network, query);
  }
  if (USE_STATIC_DATA) {
    throw new Error("Static network data is unavailable.");
  }

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

  const network = await staticNetwork();
  if (network) {
    setStatus("Computing static network reach...", "loading");
    const best = await computeStaticReachability(
      network,
      selectedOrigin.lat,
      selectedOrigin.lon,
      Number(timeSlider.value),
    );
    const stopCount = best.filter((elapsedSec) => Number.isFinite(elapsedSec)).length;
    const points = buildStaticHeatmapPoints(network, best, Number(timeSlider.value));
    renderHeatmap(points);
    setStatus(`Static network result: ${stopCount} stops.`, "success");
    return;
  }
  if (USE_STATIC_DATA) {
    throw new Error("Static network data is unavailable.");
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

layerToggle.addEventListener("click", () => {
  setLayerMenuOpen(layerMenu.hidden);
});

layerOptions.forEach((option) => {
  option.addEventListener("click", () => {
    setBaseLayer(option.dataset.layer);
    setLayerMenuOpen(false);
  });
});

transitLinesToggle.addEventListener("click", () => {
  transitLinesVisible = !transitLinesVisible;
  setTransitLineLayer();
});

document.addEventListener("click", (event) => {
  if (!layerMenu.hidden && !event.target.closest(".map-tools")) {
    setLayerMenuOpen(false);
  }
});

window.__transitHeatMapInternals = {
  API_BASE,
  USE_STATIC_DATA,
  prepareStaticNetwork,
  prepareStaticV2Network,
  loadStaticManifest,
  loadStaticTile,
  searchStaticStops,
  computeStaticReachability,
  buildStaticHeatmapPoints,
};

initMap();
staticNetwork();
