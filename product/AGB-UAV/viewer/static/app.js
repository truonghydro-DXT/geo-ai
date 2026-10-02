const state = {
  summary: {},
  layers: [],
  cells: [],
  activeLayer: "agb_2m",
  metric: "agb_Mg_ha",
  selectedKey: null,
  sortKey: "agb_Mg_ha",
  sortDir: "desc",
  filter: "",
  map: null,
  geotiffLayer: null,
  rasterCache: {},
  overlayNonce: Date.now(),
  biomassPoll: null,
  overlayReq: 0,
  overlayTimer: null,
  overlayObjectUrl: null,
  ignoreMove: false,
  gridObserver: null,
  draw: {
    active: false,
    points: [],
    preview: null,
    polygon: null,
    vertices: [],
    lastClickAt: 0,
  },
  measure: {
    active: false,
    points: [],
    preview: null,
    line: null,
    vertices: [],
    lastClickAt: 0,
  },
};

const POLY_STYLE = {
  color: "#e23d3d",
  weight: 2,
  fillColor: "#e23d3d",
  fillOpacity: 0.22,
  interactive: false,
};

const MEASURE_STYLE = {
  color: "#5ec8ff",
  weight: 3,
  interactive: false,
};

const kpiDefs = [
  ["mapped_area_ha", "Diện tích hợp lệ", "ha", 2],
  ["vegetated_area_ha", "Diện tích có tán", "ha", 2],
  ["mean_canopy_cover_pct", "Che phủ tán TB", "%", 1],
  ["mean_agb_Mg_ha", "AGB trung bình", "Mg/ha", 1],
  ["total_agb_Mg", "Tổng AGB", "tấn", 1],
  ["total_carbon_Mg", "Carbon (IPCC 0.47)", "tấn C", 1],
];

function $(id) {
  return document.getElementById(id);
}

function fmt(value, digits = 1) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return n.toLocaleString("vi-VN", { maximumFractionDigits: digits, minimumFractionDigits: 0 });
}

function haversineMeters(a, b) {
  const toRad = (deg) => (deg * Math.PI) / 180;
  const dLat = toRad(b.lat - a.lat);
  const dLng = toRad(b.lng - a.lng);
  const lat1 = toRad(a.lat);
  const lat2 = toRad(b.lat);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2;
  return 2 * 6371000 * Math.asin(Math.min(1, Math.sqrt(h)));
}

function pathLengthMeters(latlngs) {
  let total = 0;
  for (let i = 1; i < latlngs.length; i += 1) {
    total += haversineMeters(latlngs[i - 1], latlngs[i]);
  }
  return total;
}

function fmtLength(meters) {
  if (!Number.isFinite(meters)) return "—";
  if (meters < 1000) return `${fmt(meters, 1)} m`;
  return `${fmt(meters / 1000, 3)} km`;
}

function cellKey(cell) {
  return `${cell.row}-${cell.col}`;
}

const layerLegends = {
  ortho: {
    kind: "rgb",
    title: "Orthomosaic RGB",
    unit: "ảnh UAV",
    caption: "Màu thật từ orthomosaic UAV (kênh Đỏ–Lục–Lam). Vùng trong suốt nằm ngoài phạm vi bay chụp.",
    swatches: [
      ["#c4473a", "Đỏ (R)"],
      ["#4ea35a", "Lục (G)"],
      ["#3a6fb0", "Lam (B)"],
    ],
  },
  agb_2m: {
    kind: "ramp",
    cmap: "ylgn",
    title: "Sinh khối trên mặt đất",
    unit: "Mg/ha",
    digits: 0,
    low: "Thấp",
    high: "Cao",
    fallbackMin: 0,
    fallbackMax: 240,
    caption: "Tính theo pixel 2×2 m (kg), rồi quy đổi Mg/ha = (kg/pixel) / 0,4.",
  },
  cover_2m: {
    kind: "ramp",
    cmap: "ylgn",
    title: "Che phủ tán",
    unit: "%",
    digits: 0,
    low: "Hở / đất trống",
    high: "Tán kín",
    fallbackMin: 0,
    fallbackMax: 100,
    caption: "Tỷ lệ pixel tán lá trong ô 2 m, từ mặt nạ ExG/VARI.",
  },
  vari_2m: {
    kind: "ramp",
    cmap: "rdylgn",
    title: "VARI",
    unit: "chỉ số",
    digits: 2,
    low: "Ít xanh / đất",
    high: "Tán khỏe",
    fallbackMin: -0.1,
    fallbackMax: 0.4,
    caption: "Visible Atmospherically Resistant Index. Ngưỡng tán: VARI ≥ 0,08.",
  },
  exg_2m: {
    kind: "ramp",
    cmap: "rdylgn",
    title: "Excess Green (ExG)",
    unit: "chỉ số",
    digits: 2,
    low: "Phi thực vật",
    high: "Thực vật xanh",
    fallbackMin: -0.05,
    fallbackMax: 0.45,
    caption: "ExG = 2G − R − B. Ngưỡng tán: ExG ≥ 0,16.",
  },
};

function colorRamp(t) {
  const stops = [
    [247, 241, 200],
    [157, 206, 107],
    [31, 107, 58],
  ];
  const x = Math.min(1, Math.max(0, t));
  const idx = x < 0.5 ? 0 : 1;
  const local = x < 0.5 ? x * 2 : (x - 0.5) * 2;
  const a = stops[idx];
  const b = stops[idx + 1];
  return `rgb(${Math.round(a[0] + (b[0] - a[0]) * local)}, ${Math.round(a[1] + (b[1] - a[1]) * local)}, ${Math.round(a[2] + (b[2] - a[2]) * local)})`;
}

function layerById(id) {
  return state.layers.find((item) => item.id === id);
}

function leafletBounds(bounds) {
  const [south, west, north, east] = bounds;
  return [
    [south, west],
    [north, east],
  ];
}

function initMap() {
  if (state.map) {
    state.map.invalidateSize();
    return;
  }
  if (typeof L === "undefined") {
    throw new Error("Leaflet chua tai. Hay Ctrl+F5.");
  }
  state.map = L.map("map", {
    zoomControl: true,
    minZoom: 12,
    maxZoom: 22,
    zoomAnimation: false,
    fadeAnimation: false,
    markerZoomAnimation: false,
    center: [21.1232, 105.6815],
    zoom: 16,
  });
  L.tileLayer("/basemap/{z}/{x}/{y}.png", {
    attribution: "&copy; OpenStreetMap contributors &copy; OSM.de / OSM France",
    maxZoom: 22,
    maxNativeZoom: 19,
    errorTileUrl: "/static/vendor/empty-tile.png",
  }).addTo(state.map);
  state.map.on("click", onMapClick);
  state.map.on("dblclick", onMapDblClick);
  state.map.on("mousemove", onMapMouseMove);
  state.map.on("moveend", scheduleOverlayRefresh);
  setTimeout(() => state.map.invalidateSize(), 50);
}

function fitScene() {
  const layer = layerById(state.activeLayer) || state.layers[0];
  if (!layer || !layer.bounds) return;
  state.map.fitBounds(leafletBounds(layer.bounds), { padding: [12, 12] });
}

function viewWindow(layer) {
  if (!state.map || layer.west == null) return null;
  const padded = state.map.getBounds().pad(0.12);
  const west = Math.max(padded.getWest(), layer.west);
  const south = Math.max(padded.getSouth(), layer.south);
  const east = Math.min(padded.getEast(), layer.east);
  const north = Math.min(padded.getNorth(), layer.north);
  if (!(east > west) || !(north > south)) return null;
  return { west, south, east, north };
}

function overlayPixelSize() {
  const size = state.map.getSize();
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  return Math.round(Math.max(512, Math.min(3072, Math.max(size.x, size.y) * dpr)));
}

function overlayRequestUrl(layer, view) {
  const params = new URLSearchParams({
    t: String(state.overlayNonce),
    size: String(overlayPixelSize()),
  });
  if (view) {
    params.set("west", String(view.west));
    params.set("south", String(view.south));
    params.set("east", String(view.east));
    params.set("north", String(view.north));
  }
  if (Number.isFinite(layer.vmin) && Number.isFinite(layer.vmax)) {
    params.set("vmin", String(layer.vmin));
    params.set("vmax", String(layer.vmax));
  }
  return `${layer.overlayUrl}?${params.toString()}`;
}

function isPhotoLayer(layer) {
  return layer.id === "ortho" || layer.cmap === "rgb";
}

function scheduleOverlayRefresh() {
  if (state.ignoreMove) return;
  const layer = layerById(state.activeLayer);
  if (!layer) return;
  clearTimeout(state.overlayTimer);
  state.overlayTimer = setTimeout(() => {
    loadGeoTiffLayer(layer).catch((err) => {
      $("layer-note").textContent = `Loi GeoTIFF: ${err.message}`;
    });
  }, 180);
}

function colorForValue(layer, value) {
  if (value == null || Number.isNaN(value)) return null;
  if (layer.nodata != null && value === layer.nodata) return null;
  const min = layer.vmin ?? 0;
  const max = layer.vmax ?? 1;
  const t = max === min ? 0.5 : (value - min) / (max - min);
  return colorRamp(t);
}

async function loadGeoTiffLayer(layer) {
  const req = ++state.overlayReq;
  const view = viewWindow(layer);
  if (!view) {
    $("layer-note").textContent = `${layer.file} · ngoài phạm vi hiển thị`;
    return;
  }
  $("layer-note").textContent = `Đang đọc ${layer.file} · cửa sổ theo mức zoom`;
  const url = overlayRequestUrl(layer, view);
  const res = await fetch(url);
  if (req !== state.overlayReq) return;
  if (!res.ok) throw new Error(`Khong ve duoc lop GeoTIFF (${res.status})`);
  const blob = await res.blob();
  if (req !== state.overlayReq) return;
  const objUrl = URL.createObjectURL(blob);
  const bounds = [
    [view.south, view.west],
    [view.north, view.east],
  ];
  const next = L.imageOverlay(objUrl, bounds, {
    opacity: Number($("opacity").value) / 100,
    interactive: false,
    zIndex: 400,
    className: isPhotoLayer(layer) ? "overlay-photo" : "overlay-raster",
  });
  await new Promise((resolve, reject) => {
    next.once("load", resolve);
    next.once("error", () => reject(new Error("Khong ve duoc lop GeoTIFF")));
    next.addTo(state.map);
  });
  if (req !== state.overlayReq) {
    state.map.removeLayer(next);
    URL.revokeObjectURL(objUrl);
    return;
  }
  if (state.geotiffLayer) {
    state.map.removeLayer(state.geotiffLayer);
  }
  if (state.overlayObjectUrl) {
    URL.revokeObjectURL(state.overlayObjectUrl);
  }
  state.overlayObjectUrl = objUrl;
  state.geotiffLayer = next;
  $("layer-note").textContent = `${layer.file} · ${layer.driver || "GTiff"} · ${layer.crs || ""}`;
}

async function setLayer(id) {
  const layer = layerById(id) || state.layers[0];
  if (!layer) return;
  state.activeLayer = layer.id;
  renderTabs();
  renderMapLegend(layer);
  syncAgbDrawUi();
  $("map-value").textContent = "Click bản đồ để đọc giá trị pixel GeoTIFF";
  try {
    await loadGeoTiffLayer(layer);
  } catch (err) {
    $("layer-note").textContent = `Loi GeoTIFF: ${err.message}`;
  }
}

async function onMapClick(event) {
  if (state.measure.active && isAgbLayer()) {
    L.DomEvent.stop(event);
    const now = Date.now();
    if (now - state.measure.lastClickAt < 280) return;
    state.measure.lastClickAt = now;
    addMeasureVertex(event.latlng);
    return;
  }
  if (state.draw.active && isAgbLayer()) {
    L.DomEvent.stop(event);
    const now = Date.now();
    if (now - state.draw.lastClickAt < 280) return;
    state.draw.lastClickAt = now;
    if (nearFirstVertex(event.latlng)) {
      finishPolygon();
      return;
    }
    addDrawVertex(event.latlng);
    return;
  }
  const { lat, lng } = event.latlng;
  const layer = layerById(state.activeLayer);
  if (!layer) {
    $("map-value").textContent = `${lat.toFixed(6)}, ${lng.toFixed(6)}`;
    return;
  }
  const res = await fetch(`/api/value?layer=${encodeURIComponent(layer.id)}&lat=${lat}&lon=${lng}`).then((r) => r.json());
  if (res.value == null) {
    $("map-value").textContent = `${lat.toFixed(6)}, ${lng.toFixed(6)} · ngoài vùng dữ liệu`;
    return;
  }
  if (layer.id === "agb_2m" && res.pixel_kg != null) {
    $("map-value").textContent =
      `${lat.toFixed(6)}, ${lng.toFixed(6)} · ${fmt(res.pixel_kg, 1)} kg / pixel 2×2 m · quy đổi ${fmt(res.value, 1)} Mg/ha`;
    return;
  }
  $("map-value").textContent = `${lat.toFixed(6)}, ${lng.toFixed(6)} · ${layer.file} = ${fmt(res.value, 2)} ${res.unit}`;
}

function onMapDblClick(event) {
  if (!isAgbLayer()) return;
  if (state.measure.active) {
    L.DomEvent.stop(event);
    finishMeasure();
    return;
  }
  if (!state.draw.active) return;
  L.DomEvent.stop(event);
  finishPolygon();
}

function onMapMouseMove(event) {
  if (!isAgbLayer()) return;
  if (state.measure.active && state.measure.points.length) {
    const latlngs = state.measure.points.concat([event.latlng]);
    if (state.measure.preview) {
      state.measure.preview.setLatLngs(latlngs);
    } else {
      state.measure.preview = L.polyline(latlngs, {
        ...MEASURE_STYLE,
        dashArray: "6 5",
      }).addTo(state.map);
    }
    const meters = pathLengthMeters(latlngs);
    setDrawHint(`${fmtLength(meters)} · click thêm điểm · double-click để xong`);
    renderMeasureStats(meters, latlngs.length, true);
    return;
  }
  if (!state.draw.active || !state.draw.points.length) return;
  const latlngs = state.draw.points.concat([event.latlng]);
  if (state.draw.preview) {
    state.draw.preview.setLatLngs(latlngs);
  } else {
    state.draw.preview = L.polyline(latlngs, {
      color: "#e23d3d",
      weight: 2,
      dashArray: "6 5",
      interactive: false,
    }).addTo(state.map);
  }
}

function nearFirstVertex(latlng) {
  if (state.draw.points.length < 3 || !state.map) return false;
  const first = state.draw.points[0];
  return state.map.latLngToLayerPoint(first).distanceTo(state.map.latLngToLayerPoint(latlng)) < 14;
}

function isAgbLayer() {
  return state.activeLayer === "agb_2m";
}

function syncAgbDrawUi() {
  const onAgb = isAgbLayer();
  $("draw-tools").hidden = !onAgb;
  if (!onAgb && state.draw.active) {
    cancelPolygonDraw();
  }
  if (!onAgb && state.measure.active) {
    cancelMeasure();
  }
  if (state.draw.polygon && state.map) {
    const shown = state.map.hasLayer(state.draw.polygon);
    if (onAgb && !shown) state.draw.polygon.addTo(state.map);
    if (!onAgb && shown) state.map.removeLayer(state.draw.polygon);
  }
  if (state.measure.line && state.map) {
    const shown = state.map.hasLayer(state.measure.line);
    if (onAgb && !shown) state.measure.line.addTo(state.map);
    if (!onAgb && shown) state.map.removeLayer(state.measure.line);
  }
  const polyBox = $("polygon-stats");
  const measureBox = $("measure-stats");
  if (!onAgb) {
    polyBox.hidden = true;
    measureBox.hidden = true;
  } else {
    if (polyBox.innerHTML.trim()) polyBox.hidden = false;
    if (measureBox.innerHTML.trim()) measureBox.hidden = false;
  }
  updateDrawButtons();
  updateMeasureButtons();
}

function setDrawHint(text) {
  $("map-value").textContent = text;
}

function updateDrawButtons() {
  const drawing = state.draw.active;
  const hasShape = Boolean(state.draw.polygon) || state.draw.points.length > 0;
  $("draw-polygon-btn").classList.toggle("active", drawing);
  $("draw-polygon-btn").textContent = drawing ? "Đang vẽ…" : "Vẽ vùng AGB";
  $("finish-polygon-btn").disabled = !drawing || state.draw.points.length < 3;
  $("clear-polygon-btn").disabled = !hasShape && !drawing;
}

function updateMeasureButtons() {
  const measuring = state.measure.active;
  const hasLine = Boolean(state.measure.line) || state.measure.points.length > 0;
  $("measure-btn").classList.toggle("active", measuring);
  $("measure-btn").textContent = measuring ? "Đang đo…" : "Đo chiều dài";
  $("finish-measure-btn").disabled = !measuring || state.measure.points.length < 2;
  $("clear-measure-btn").disabled = !hasLine && !measuring;
}

function lockMapTools() {
  if (!state.map) return;
  const busy = state.draw.active || state.measure.active;
  if (busy) state.map.doubleClickZoom.disable();
  else state.map.doubleClickZoom.enable();
  state.map.getContainer().classList.toggle("drawing-polygon", state.draw.active);
  state.map.getContainer().classList.toggle("measuring-line", state.measure.active);
}

function clearDrawPreview() {
  if (state.draw.preview) {
    state.map.removeLayer(state.draw.preview);
    state.draw.preview = null;
  }
  state.draw.vertices.forEach((marker) => state.map.removeLayer(marker));
  state.draw.vertices = [];
}

function startPolygonDraw() {
  if (!state.map || !isAgbLayer()) return;
  if (state.measure.active) cancelMeasure();
  clearPolygon({ keepHint: true });
  state.draw.active = true;
  state.draw.points = [];
  lockMapTools();
  setDrawHint("Click để thêm đỉnh · click điểm đầu hoặc Hoàn thành để đóng vùng");
  updateDrawButtons();
}

function addDrawVertex(latlng) {
  state.draw.points.push(latlng);
  const marker = L.circleMarker(latlng, {
    radius: 4,
    color: "#e23d3d",
    weight: 2,
    fillColor: "#ffb3b3",
    fillOpacity: 1,
    interactive: false,
  }).addTo(state.map);
  state.draw.vertices.push(marker);
  if (state.draw.preview) {
    state.draw.preview.setLatLngs(state.draw.points);
  } else {
    state.draw.preview = L.polyline(state.draw.points, {
      color: "#e23d3d",
      weight: 2,
      interactive: false,
    }).addTo(state.map);
  }
  setDrawHint(`Đã ${state.draw.points.length} đỉnh · cần ≥ 3 rồi Hoàn thành`);
  updateDrawButtons();
}

function cancelPolygonDraw() {
  if (!state.draw.active) return;
  state.draw.active = false;
  state.draw.points = [];
  clearDrawPreview();
  lockMapTools();
  setDrawHint("Đã hủy vẽ vùng. Click bản đồ để đọc giá trị pixel GeoTIFF");
  updateDrawButtons();
}

function clearPolygon({ keepHint = false } = {}) {
  state.draw.active = false;
  state.draw.points = [];
  clearDrawPreview();
  if (state.draw.polygon) {
    state.map.removeLayer(state.draw.polygon);
    state.draw.polygon = null;
  }
  lockMapTools();
  const box = $("polygon-stats");
  box.hidden = true;
  box.innerHTML = "";
  if (!keepHint) {
    setDrawHint("Click bản đồ để đọc giá trị pixel GeoTIFF");
  }
  updateDrawButtons();
}

async function finishPolygon() {
  if (!isAgbLayer() || !state.draw.active || state.draw.points.length < 3) {
    setDrawHint("Cần ít nhất 3 đỉnh để đóng vùng");
    return;
  }
  const points = state.draw.points.slice();
  state.draw.active = false;
  clearDrawPreview();
  lockMapTools();
  if (state.draw.polygon) {
    state.map.removeLayer(state.draw.polygon);
  }
  state.draw.polygon = L.polygon(points, POLY_STYLE).addTo(state.map);
  updateDrawButtons();
  const coordinates = points.map((p) => [p.lng, p.lat]);
  setDrawHint("Đang thống kê AGB theo vùng…");
  $("polygon-stats").hidden = false;
  $("polygon-stats").innerHTML = `<h3>Vùng AGB</h3><p>Đang tính tổng sinh khối…</p>`;
  try {
    const res = await fetch("/api/polygon-stats", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ coordinates }),
    }).then((r) => r.json());
    renderPolygonStats(res);
  } catch (err) {
    $("polygon-stats").innerHTML = `<h3>Vùng AGB</h3><p>Không thống kê được: ${err.message}</p>`;
    setDrawHint(`Không thống kê được: ${err.message}`);
  }
}

function renderPolygonStats(res) {
  if (res.error) {
    $("polygon-stats").innerHTML = `<h3>Vùng AGB</h3><p>${res.error}</p>`;
    setDrawHint(res.error);
    return;
  }
  $("polygon-stats").innerHTML = `
    <h3>Tổng AGB theo vùng</h3>
    <p>Pixel: <strong>2 × 2 m</strong> · ${res.pixel_count} ô</p>
    <p>AGB TB / pixel: <strong>${fmt(res.mean_pixel_kg, 2)} kg</strong></p>
    <p>Tổng AGB: <strong>${fmt(res.total_agb_Mg, 1)} tấn</strong></p>
    <p>Quy đổi TB: <strong>${fmt(res.mean_agb_Mg_ha, 1)} Mg/ha</strong></p>
    <p>Diện tích: <strong>${fmt(res.valid_area_ha, 3)} ha</strong> (n × 0,0004)</p>
    <p>Carbon (IPCC 0.47): <strong>${fmt(res.total_carbon_Mg, 1)} tấn C</strong></p>
  `;
  setDrawHint(`Tổng AGB vùng = ${fmt(res.total_agb_Mg, 1)} tấn`);
}

function clearMeasurePreview() {
  if (state.measure.preview && state.map) {
    state.map.removeLayer(state.measure.preview);
    state.measure.preview = null;
  }
  state.measure.vertices.forEach((marker) => state.map.removeLayer(marker));
  state.measure.vertices = [];
}

function renderMeasureStats(meters, pointCount, live = false) {
  const box = $("measure-stats");
  box.hidden = false;
  box.innerHTML = `
    <h3>Đo chiều dài</h3>
    <p>Tổng dài: <strong>${fmtLength(meters)}</strong></p>
    <p>${pointCount} điểm${live ? " · đang đo" : ""}</p>
    <p class="hint">${live ? "Click thêm điểm · double-click hoặc Xong đo" : "Xóa đo để vẽ đường mới"}</p>
  `;
}

function startMeasure() {
  if (!state.map || !isAgbLayer()) return;
  if (state.draw.active) cancelPolygonDraw();
  clearMeasure({ keepHint: true });
  state.measure.active = true;
  state.measure.points = [];
  lockMapTools();
  setDrawHint("Click các điểm trên bản đồ để đo chiều dài");
  updateMeasureButtons();
}

function addMeasureVertex(latlng) {
  state.measure.points.push(latlng);
  const marker = L.circleMarker(latlng, {
    radius: 4,
    color: "#5ec8ff",
    weight: 2,
    fillColor: "#d7f4ff",
    fillOpacity: 1,
    interactive: false,
  }).addTo(state.map);
  state.measure.vertices.push(marker);
  if (state.measure.preview) {
    state.measure.preview.setLatLngs(state.measure.points);
  } else {
    state.measure.preview = L.polyline(state.measure.points, MEASURE_STYLE).addTo(state.map);
  }
  const meters = pathLengthMeters(state.measure.points);
  const hint =
    state.measure.points.length < 2
      ? "Đã 1 điểm · click điểm tiếp theo"
      : `${fmtLength(meters)} · click thêm hoặc Xong đo`;
  setDrawHint(hint);
  renderMeasureStats(meters, state.measure.points.length, true);
  updateMeasureButtons();
}

function cancelMeasure() {
  if (!state.measure.active) return;
  state.measure.active = false;
  state.measure.points = [];
  clearMeasurePreview();
  lockMapTools();
  $("measure-stats").hidden = true;
  $("measure-stats").innerHTML = "";
  setDrawHint("Đã hủy đo. Click bản đồ để đọc giá trị pixel GeoTIFF");
  updateMeasureButtons();
}

function clearMeasure({ keepHint = false } = {}) {
  state.measure.active = false;
  state.measure.points = [];
  clearMeasurePreview();
  if (state.measure.line) {
    state.map.removeLayer(state.measure.line);
    state.measure.line = null;
  }
  lockMapTools();
  $("measure-stats").hidden = true;
  $("measure-stats").innerHTML = "";
  if (!keepHint) {
    setDrawHint("Click bản đồ để đọc giá trị pixel GeoTIFF");
  }
  updateMeasureButtons();
}

function finishMeasure() {
  if (!isAgbLayer() || !state.measure.active || state.measure.points.length < 2) {
    setDrawHint("Cần ít nhất 2 điểm để đo chiều dài");
    return;
  }
  const points = state.measure.points.slice();
  state.measure.active = false;
  clearMeasurePreview();
  lockMapTools();
  if (state.measure.line) {
    state.map.removeLayer(state.measure.line);
  }
  state.measure.line = L.polyline(points, MEASURE_STYLE).addTo(state.map);
  const meters = pathLengthMeters(points);
  renderMeasureStats(meters, points.length, false);
  setDrawHint(`Chiều dài = ${fmtLength(meters)}`);
  updateMeasureButtons();
}

async function loadAll() {
  try {
    initMap();
  } catch (err) {
    $("layer-note").textContent = `Loi ban do: ${err.message}`;
    return;
  }
  const [summaryRes, cellsRes] = await Promise.all([
    fetch("/api/summary").then((r) => r.json()),
    fetch("/api/cells").then((r) => r.json()),
  ]);
  state.summary = summaryRes.summary || {};
  state.layers = summaryRes.layers || [];
  state.cells = cellsRes.cells || [];
  setPathFields(summaryRes);
  renderKpis();
  state.ignoreMove = true;
  const first = layerById(state.activeLayer) || state.layers[0];
  if (first && first.bounds) {
    state.map.fitBounds(leafletBounds(first.bounds), { padding: [16, 16], maxZoom: 17 });
  }
  state.map.invalidateSize();
  await setLayer(state.activeLayer);
  renderGrid();
  renderTable();
  observeHaGrid();
  setTimeout(() => {
    state.ignoreMove = false;
  }, 400);
}

function renderKpis() {
  $("kpi-row").innerHTML = kpiDefs
    .map(([key, label, unit, digits]) => {
      return `<article class="kpi"><span>${label}</span><strong>${fmt(state.summary[key], digits)} <small>${unit}</small></strong></article>`;
    })
    .join("");
}

function renderTabs() {
  $("layer-tabs").innerHTML = state.layers
    .map((layer) => {
      const active = layer.id === state.activeLayer ? "active" : "";
      return `<button type="button" class="${active}" data-layer="${layer.id}">${layer.title}</button>`;
    })
    .join("");
}

function legendExtent(layer, spec) {
  const min = Number.isFinite(layer.vmin) ? layer.vmin : spec.fallbackMin;
  const max = Number.isFinite(layer.vmax) ? layer.vmax : spec.fallbackMax;
  const mid = (min + max) / 2;
  return { min, max, mid };
}

function renderMapLegend(layer) {
  const box = $("map-legend");
  const spec = layerLegends[layer.id];
  if (!spec) {
    box.hidden = true;
    box.innerHTML = "";
    return;
  }
  box.hidden = false;
  if (spec.kind === "rgb") {
    box.innerHTML = `
      <h3>${spec.title}</h3>
      <p class="legend-unit">${spec.unit}</p>
      <div class="legend-swatches">
        ${spec.swatches
          .map(([color, label]) => `<div class="legend-swatch"><i style="background:${color}"></i>${label}</div>`)
          .join("")}
      </div>
      <p class="legend-caption">${spec.caption}</p>
    `;
    return;
  }
  const { min, max, mid } = legendExtent(layer, spec);
  box.innerHTML = `
    <h3>${spec.title}</h3>
    <p class="legend-unit">${spec.unit}</p>
    <div class="map-legend-body">
      <div class="legend-ramp ${spec.cmap}"></div>
      <div class="legend-ticks">
        <div><strong>${fmt(max, spec.digits)}</strong>${spec.high}</div>
        <div>${fmt(mid, spec.digits)}</div>
        <div><strong>${fmt(min, spec.digits)}</strong>${spec.low}</div>
      </div>
    </div>
    <p class="legend-caption">${spec.caption}</p>
  `;
}

function metricExtent() {
  const values = state.cells.map((c) => Number(c[state.metric])).filter(Number.isFinite);
  return {
    min: values.length ? Math.min(...values) : 0,
    max: values.length ? Math.max(...values) : 1,
  };
}

function renderGrid() {
  const canvas = $("ha-grid");
  if (!canvas) return;
  const rows = state.cells.map((c) => c.row);
  const cols = state.cells.map((c) => c.col);
  if (!rows.length) return;
  const minR = Math.min(...rows);
  const maxR = Math.max(...rows);
  const minC = Math.min(...cols);
  const maxC = Math.max(...cols);
  const nR = maxR - minR + 1;
  const nC = maxC - minC + 1;
  const box = canvas.parentElement;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const pad = 8;
  const availW = Math.max(64, box?.clientWidth || 240);
  const availH = Math.max(64, box?.clientHeight || availW);
  const cell = Math.max(3, Math.min((availW - pad * 2) / nC, (availH - pad * 2) / nR));
  const cssW = pad * 2 + cell * nC;
  const cssH = pad * 2 + cell * nR;
  canvas.style.width = `${cssW}px`;
  canvas.style.height = `${cssH}px`;
  const bufW = Math.max(1, Math.round(cssW * dpr));
  const bufH = Math.max(1, Math.round(cssH * dpr));
  if (canvas.width !== bufW) canvas.width = bufW;
  if (canvas.height !== bufH) canvas.height = bufH;
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const { min, max } = metricExtent();
  ctx.clearRect(0, 0, cssW, cssH);
  ctx.fillStyle = "#0d1812";
  ctx.fillRect(0, 0, cssW, cssH);

  state.cells.forEach((cellData) => {
    const x = pad + (cellData.col - minC) * cell;
    const y = pad + (cellData.row - minR) * cell;
    const t = max === min ? 0.5 : (Number(cellData[state.metric]) - min) / (max - min);
    ctx.fillStyle = colorRamp(t);
    const gap = cell > 8 ? 1 : 0.5;
    ctx.fillRect(x + gap, y + gap, Math.max(1, cell - gap * 2), Math.max(1, cell - gap * 2));
    if (state.selectedKey === cellKey(cellData)) {
      ctx.strokeStyle = "#f3e3b0";
      ctx.lineWidth = Math.max(1, Math.min(2, cell / 10));
      ctx.strokeRect(x + gap, y + gap, Math.max(1, cell - gap * 2), Math.max(1, cell - gap * 2));
    }
  });

  canvas.onclick = (event) => {
    const rect = canvas.getBoundingClientRect();
    const px = event.clientX - rect.left;
    const py = event.clientY - rect.top;
    const col = minC + Math.floor((px - pad) / cell);
    const row = minR + Math.floor((py - pad) / cell);
    const hit = state.cells.find((c) => c.row === row && c.col === col);
    if (hit) selectCell(hit);
  };

  $("grid-legend").innerHTML = `
    <span>${fmt(min, 1)}</span>
    <div class="legend-bar"></div>
    <span>${fmt(max, 1)}</span>
  `;
  const card = $("cell-card");
  if (card) {
    const shownH = canvas.getBoundingClientRect().height || cssH;
    card.style.height = `${Math.round(shownH)}px`;
  }
}

function observeHaGrid() {
  const box = $("ha-grid")?.parentElement;
  if (!box || state.gridObserver || typeof ResizeObserver === "undefined") return;
  let frame = 0;
  state.gridObserver = new ResizeObserver(() => {
    if (frame) cancelAnimationFrame(frame);
    frame = requestAnimationFrame(() => {
      frame = 0;
      renderGrid();
    });
  });
  state.gridObserver.observe(box);
}

function selectCell(cell) {
  state.selectedKey = cellKey(cell);
  renderGrid();
  renderCellCard(cell);
  renderTable();
  if (state.map) {
    state.map.setView([cell.lat, cell.lon], Math.max(state.map.getZoom(), 18));
  }
}

function renderCellCard(cell) {
  $("cell-card").innerHTML = `
    <p><strong>Ô ${cell.row}, ${cell.col}</strong></p>
    <p>Kinh độ: ${cell.lon.toFixed(6)}</p>
    <p>Vĩ độ: ${cell.lat.toFixed(6)}</p>
    <p>Che phủ tán: <strong>${fmt(cell.canopy_cover_pct, 1)}%</strong></p>
    <p>AGB: <strong>${fmt(cell.agb_Mg_ha, 1)} Mg/ha</strong></p>
    <p>Tán lớn: <strong>${fmt(cell.large_crown_area_pct, 1)}%</strong></p>
  `;
}

function filteredCells() {
  const q = state.filter.trim().toLowerCase();
  const rows = state.cells.filter((cell) => {
    if (!q) return true;
    return (
      String(cell.row).includes(q) ||
      String(cell.col).includes(q) ||
      String(cell.agb_Mg_ha).includes(q) ||
      String(cell.canopy_cover_pct).includes(q)
    );
  });
  rows.sort((a, b) => {
    const av = a[state.sortKey];
    const bv = b[state.sortKey];
    if (av === bv) return 0;
    const cmp = av > bv ? 1 : -1;
    return state.sortDir === "asc" ? cmp : -cmp;
  });
  return rows;
}

function renderTable() {
  const body = $("ha-table").querySelector("tbody");
  body.innerHTML = filteredCells()
    .map((cell) => {
      const selected = state.selectedKey === cellKey(cell) ? "selected" : "";
      return `<tr class="${selected}" data-key="${cellKey(cell)}">
        <td>${cell.row}</td>
        <td>${cell.col}</td>
        <td>${cell.lon.toFixed(6)}</td>
        <td>${cell.lat.toFixed(6)}</td>
        <td>${fmt(cell.canopy_cover_pct, 2)}</td>
        <td>${fmt(cell.agb_Mg_ha, 2)}</td>
        <td>${fmt(cell.large_crown_area_pct, 2)}</td>
      </tr>`;
    })
    .join("");
}

function setRunStatus(text) {
  $("run-status").textContent = text || "";
}

function pathPayload() {
  return {
    input: $("input-path").value.trim(),
    output: $("output-path").value.trim(),
  };
}

function setPathFields(payload) {
  if (!payload) return;
  if (payload.input) $("input-path").value = payload.input;
  if (payload.output) $("output-path").value = payload.output;
}

async function applyOutputAndReload({ quiet = false } = {}) {
  try {
    const res = await fetch("/api/paths", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(pathPayload()),
    }).then((r) => r.json());
    if (res.error) {
      setRunStatus(res.error);
      return false;
    }
    setPathFields(res);
    state.overlayNonce = Date.now();
    await loadAll();
    if (!quiet) setRunStatus("Đã tải kết quả từ thư mục output");
    return true;
  } catch (err) {
    setRunStatus(`Không tải được kết quả: ${err.message}`);
    return false;
  }
}

async function browsePath(kind, inputId) {
  setRunStatus(kind === "dir" ? "Chọn thư mục output…" : "Chọn file input…");
  try {
    const res = await fetch("/api/browse", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind, initial: $(inputId).value.trim() }),
    }).then((r) => r.json());
    if (res.error) {
      setRunStatus(res.error);
      return;
    }
    if (res.cancelled || !res.path) {
      setRunStatus("");
      return;
    }
    $(inputId).value = res.path;
    if (kind === "dir") {
      await applyOutputAndReload();
    } else {
      setRunStatus("");
    }
  } catch (err) {
    setRunStatus(`Không chọn được đường dẫn: ${err.message}`);
  }
}

function stopBiomassPoll() {
  if (state.biomassPoll) {
    clearTimeout(state.biomassPoll);
    state.biomassPoll = null;
  }
}

function applyBiomassStatus(job, { justFinished = false } = {}) {
  const btn = $("run-biomass-btn");
  const loadBtn = $("load-output-btn");
  btn.disabled = Boolean(job.running);
  if (loadBtn) loadBtn.disabled = Boolean(job.running);
  $("browse-input-btn").disabled = Boolean(job.running);
  $("browse-output-btn").disabled = Boolean(job.running);
  $("input-path").disabled = Boolean(job.running);
  $("output-path").disabled = Boolean(job.running);
  btn.textContent = job.running ? "Đang tính…" : "Tính sinh khối";
  setPathFields(job);
  const detail = job.message || job.log || "";
  if (job.running) {
    setRunStatus(detail || "Đang chạy Biomass_analysis.py…");
    return;
  }
  if (job.returncode === 0) {
    setRunStatus(justFinished ? "Hoàn thành — đã tải lại bản đồ" : "");
  } else if (job.returncode != null && job.returncode !== 0) {
    setRunStatus(detail || `Lỗi (mã ${job.returncode})`);
  } else {
    setRunStatus("");
  }
}

async function pollBiomassStatus() {
  try {
    const job = await fetch("/api/run-biomass").then((r) => r.json());
    const wasRunning = $("run-biomass-btn").disabled;
    applyBiomassStatus(job, { justFinished: wasRunning && !job.running && job.returncode === 0 });
    if (job.running) {
      state.biomassPoll = setTimeout(pollBiomassStatus, 2000);
      return;
    }
    stopBiomassPoll();
    if (wasRunning && job.returncode === 0) {
      state.overlayNonce = Date.now();
      await loadAll();
    }
  } catch (err) {
    setRunStatus(`Không đọc được trạng thái: ${err.message}`);
    state.biomassPoll = setTimeout(pollBiomassStatus, 4000);
  }
}

async function startBiomassJob() {
  const btn = $("run-biomass-btn");
  btn.disabled = true;
  btn.textContent = "Đang tính…";
  setRunStatus("Đang chạy Biomass_analysis.py…");
  stopBiomassPoll();
  try {
    const job = await fetch("/api/run-biomass", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(pathPayload()),
    }).then((r) => r.json());
    setPathFields(job);
    applyBiomassStatus(job);
    if (job.running) {
      state.biomassPoll = setTimeout(pollBiomassStatus, 2000);
    } else if (job.returncode === 0) {
      state.overlayNonce = Date.now();
      await loadAll();
    }
  } catch (err) {
    btn.disabled = false;
    btn.textContent = "Tính sinh khối";
    setRunStatus(`Không chạy được: ${err.message}`);
  }
}

function bindEvents() {
  $("layer-tabs").addEventListener("click", (event) => {
    const btn = event.target.closest("button[data-layer]");
    if (btn) setLayer(btn.dataset.layer);
  });
  $("opacity").addEventListener("input", (event) => {
    if (state.geotiffLayer) state.geotiffLayer.setOpacity(Number(event.target.value) / 100);
  });
  $("grid-metric").addEventListener("change", (event) => {
    state.metric = event.target.value;
    renderGrid();
  });
  $("table-filter").addEventListener("input", (event) => {
    state.filter = event.target.value;
    renderTable();
  });
  $("ha-table").querySelectorAll("th").forEach((th) => {
    th.addEventListener("click", () => {
      const key = th.dataset.sort;
      if (state.sortKey === key) {
        state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
      } else {
        state.sortKey = key;
        state.sortDir = "desc";
      }
      renderTable();
    });
  });
  $("ha-table").addEventListener("click", (event) => {
    const row = event.target.closest("tr[data-key]");
    if (!row) return;
    const cell = state.cells.find((c) => cellKey(c) === row.dataset.key);
    if (cell) selectCell(cell);
  });
  window.addEventListener("resize", () => {
    if (state.map) state.map.invalidateSize();
    renderGrid();
  });
  $("run-form").addEventListener("submit", (event) => {
    event.preventDefault();
    applyOutputAndReload();
  });
  $("load-output-btn").addEventListener("click", () => applyOutputAndReload());
  $("browse-input-btn").addEventListener("click", () => browsePath("file", "input-path"));
  $("browse-output-btn").addEventListener("click", () => browsePath("dir", "output-path"));
  $("output-path").addEventListener("change", () => applyOutputAndReload());
  $("run-biomass-btn").addEventListener("click", startBiomassJob);
  $("draw-polygon-btn").addEventListener("click", () => {
    if (!isAgbLayer()) return;
    if (state.draw.active) {
      cancelPolygonDraw();
    } else {
      startPolygonDraw();
    }
  });
  $("finish-polygon-btn").addEventListener("click", () => {
    if (isAgbLayer()) finishPolygon();
  });
  $("clear-polygon-btn").addEventListener("click", () => {
    if (isAgbLayer()) clearPolygon();
  });
  $("measure-btn").addEventListener("click", () => {
    if (!isAgbLayer()) return;
    if (state.measure.active) {
      cancelMeasure();
    } else {
      startMeasure();
    }
  });
  $("finish-measure-btn").addEventListener("click", () => {
    if (isAgbLayer()) finishMeasure();
  });
  $("clear-measure-btn").addEventListener("click", () => {
    if (isAgbLayer()) clearMeasure();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || !isAgbLayer()) return;
    if (state.measure.active) {
      cancelMeasure();
      return;
    }
    if (state.draw.active) {
      cancelPolygonDraw();
    }
  });
}

bindEvents();
pollBiomassStatus();
loadAll().catch((err) => {
  $("layer-note").textContent = `Không tải được dữ liệu: ${err.message}`;
});
