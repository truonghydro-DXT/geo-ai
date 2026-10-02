// Base map
const osm = L.tileLayer('https://{s}.tile.openstreetmap.de/{z}/{x}/{y}.png');
const googleSat = L.tileLayer('https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}')
const SIRDXTBase =  L.maplibreGL({
        style: "http://54.252.221.55:3000/styles/basic-preview/style.json?key=sirdxt9385Truong",
        attribution: "@ DXTBase / OpenStreetMap",
        maxZoom: 22
      });
// Map khởi tạo
const map = L.map('map', {
  center: [21.03, 105.85],
  zoom: 10,
  layers: [osm] // mặc định chỉ OSM
});

// Quản lý layer
const baseMaps = {
  "OpenStreetMap": osm,
  "Google Satellite": googleSat,
  "SIRDXTBaseMap": SIRDXTBase,
};

const overlayMaps = {};  // Sentinel-1 sẽ add động vào đây

// Control
let layerControl = L.control.layers(baseMaps, overlayMaps).addTo(map);
let districtBoundaryLayer = null;
const BOUNDARY_LAYER_LABEL = 'Lớp ranh giới';

function updateDistrictBoundaryLayer(geojson) {
  if (!geojson || !geojson.features || !geojson.features.length) {
    if (districtBoundaryLayer && map.hasLayer(districtBoundaryLayer)) {
      map.removeLayer(districtBoundaryLayer);
    }
    delete overlayMaps[BOUNDARY_LAYER_LABEL];
    districtBoundaryLayer = null;
    return;
  }

  if (districtBoundaryLayer && map.hasLayer(districtBoundaryLayer)) {
    map.removeLayer(districtBoundaryLayer);
  }
  delete overlayMaps[BOUNDARY_LAYER_LABEL];

  districtBoundaryLayer = L.geoJSON(geojson, {
    style: {
      color: '#d7191c',
      weight: 3,
      opacity: 1,
      fillColor: '#d7191c',
      fillOpacity: 0.08
    }
  }).addTo(map);

  overlayMaps[BOUNDARY_LAYER_LABEL] = districtBoundaryLayer;
  layerControl.addOverlay(districtBoundaryLayer, BOUNDARY_LAYER_LABEL);
}

function isProtectedMapLayer(layer) {
  return layer === osm
    || layer === SIRDXTBase
    || layer === googleSat
    || layer === districtBoundaryLayer;
}

function clearOverlayMapsPreservingBoundary() {
  for (const key of Object.keys(overlayMaps)) {
    if (key !== BOUNDARY_LAYER_LABEL) {
      delete overlayMaps[key];
    }
  }
  if (districtBoundaryLayer) {
    overlayMaps[BOUNDARY_LAYER_LABEL] = districtBoundaryLayer;
  }
}

function clearMapLayersPreservingBoundary() {
  map.eachLayer(function (layer) {
    if (!isProtectedMapLayer(layer)) {
      map.removeLayer(layer);
    }
  });
  if (districtBoundaryLayer && !map.hasLayer(districtBoundaryLayer)) {
    districtBoundaryLayer.addTo(map);
  }
}

function rebuildLayerControlPreservingBoundary() {
  clearOverlayMapsPreservingBoundary();
  if (layerControl && typeof layerControl.remove === 'function') {
    layerControl.remove();
  }
  layerControl = L.control.layers(baseMaps, overlayMaps).addTo(map);
}

async function loadProvinces() {
  const provinces = [
    "Thành phố Hà Nội", "Thành phố Hải Phòng", "Tỉnh Hưng Yên", "Tỉnh Ninh Bình",
    "Tỉnh Cao Bằng", "Tỉnh Lào Cai", "Tỉnh Lạng Sơn", "Tỉnh Tuyên Quang",
    "Tỉnh Thái Nguyên", "Tỉnh Phú Thọ", "Tỉnh Bắc Ninh", "Tỉnh Quảng Ninh",
    "Tỉnh Điện Biên", "Tỉnh Lai Châu", "Tỉnh Sơn La", "Tỉnh Thanh Hóa",
    "Tỉnh Nghệ An", "Tỉnh Hà Tĩnh", "Tỉnh Quảng Trị", "Thành phố Huế",
    "Thành phố Đà Nẵng", "Tỉnh Quảng Ngãi", "Tỉnh Khánh Hòa",
    "Tỉnh Gia Lai", "Tỉnh Đắk Lắk", "Thành phố Hồ Chí Minh", "Tỉnh Lâm Đồng",
    "Tỉnh Tây Ninh", "Tỉnh Đồng Nai", "Tỉnh Đồng Tháp", "Tỉnh An Giang",
    "Tỉnh Vĩnh Long", "Thành phố Cần Thơ", "Tỉnh Cà Mau"
  ];

  const provinceSelect = document.getElementById('provinceSelect');
  provinces.sort().forEach(t => {
      const o = document.createElement('option');
      o.value = t;
      o.textContent = t;
      provinceSelect.appendChild(o);
  });
}

function normalize_name(name) {
  return name.replace(/Thành\s*phố\s*/i, 'tp')
             .replace(/Tỉnh\s*/i, 'tinh')
             .normalize("NFD").replace(/[\u0300-\u036f]/g, "")
             .replace(/đ/g, "d").replace(/Đ/g, "D")
             .replace(/\s+/g, '');
}

function getSelectedDistrictValues() {
  const districtSelect = document.getElementById('districtSelect');
  if (!districtSelect) return [];
  return Array.from(districtSelect.selectedOptions)
    .map(option => option.value)
    .filter(Boolean);
}

function clearDistrictSelection(select) {
  if (!select) return;
  Array.from(select.options).forEach(option => {
    option.selected = false;
  });
  select.selectedIndex = -1;
}

async function loadDistrictsByProvince(tentinh) {
  const url = `/load-districts?provinceSelect=${encodeURIComponent(tentinh)}`;

  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();

  currentDistrictGeoJSON = data;

  const districtSelect = document.getElementById('districtSelect');
  districtSelect.multiple = true;
  districtSelect.innerHTML = '<option value="">-- Chọn xã/phường --</option>';
  clearDistrictSelection(districtSelect);
  data.features.forEach(f => {
    if (f.properties?.tenxa) {
      const o = document.createElement('option');
      o.value = f.properties.tenxa;
      o.textContent = f.properties.tenxa;
      districtSelect.appendChild(o);
    }
  });
  makeSearchableSelect('districtSelect');

  // Zoom tỉnh vừa khít
  if (data.features.length > 0) {
      const geoLayer = L.geoJSON(data);
      map.fitBounds(geoLayer.getBounds(), { padding: [20, 20] });
  }
}

function clearPlanetElements() {
  if (sideBySideControl) {
    try { map.removeControl(sideBySideControl); } catch {}
    sideBySideControl = null;
  }

  if (planetLayerCurrent && map.hasLayer(planetLayerCurrent)) {
    map.removeLayer(planetLayerCurrent);
    planetLayerCurrent = null;
  }

  if (planetLayerPrevious && map.hasLayer(planetLayerPrevious)) {
    map.removeLayer(planetLayerPrevious);
    planetLayerPrevious = null;
  }

  if (planningLayer && map.hasLayer(planningLayer)) {
    map.removeLayer(planningLayer);
    planningLayer = null;
  }
 

  if (buildLegend) {
    try { map.removeControl(buildLegend); } catch {}
    buildLegend = null;
  }

  if (legendControl) {
    try { map.removeControl(legendControl); } catch {}
    legendControl = null;
  }

  if (legend_quyhoach) {
    try { map.removeControl(legend_quyhoach); } catch {}
    legend_quyhoach = null;
  }

  if (landuseLayers) {
    try { map.removeControl(landuseLayers); } catch {}
    landuseLayers = null;
  }
  if (landuseLegend) {
    try { map.removeControl(landuseLegend); } catch {}
    landuseLegend = null;
  }

  if (agriLayers) {
    try { map.removeControl(agriLayers); } catch {}
    agriLayers = null;
  }
  if (agriLegend) {
    try { map.removeControl(agriLegend); } catch {}
    agriLegend = null;
  }

  if (floodLayers) {
    try { map.removeControl(floodLayers); } catch {}
    floodLayers = null;
  }

  if (floodLegend) {
    try { map.removeControl(floodLegend); } catch {}
    floodLegend = null;
  }

  if (droughtLayers) {
    try {
      for (const name in droughtLayers) {
        const layer = droughtLayers[name];
        if (layer && map.hasLayer(layer)) map.removeLayer(layer);
        try { layerControl.removeLayer(layer); } catch {}
        delete overlayMaps[name];
      }
    } catch {}
    droughtLayers = null;
  }

  if (droughtLegend) {
    try { map.removeControl(droughtLegend); } catch {}
    droughtLegend = null;
  }

  if (typeof droughtCommune !== 'undefined' && droughtCommune) {
    try { map.removeControl(droughtCommune); } catch {}
    droughtCommune = null;
  }
 
  if (forerestLayer) {
    try { map.removeControl(forerestLayer); } catch {}
    forerestLayer = null;
  }

  if (forerestLegend) {
    try { map.removeControl(forerestLegend); } catch {}
    forerestLegend = null;
  }

  if (forest_fireLayers) {
    try { map.removeControl(forest_fireLayers); } catch {}
    forest_fireLayers = null;
  }

  if (forest_fireLegend) {
    try { map.removeControl(forest_fireLegend); } catch {}
    forest_fireLegend = null;
  }


  if (forest_fireCommuneTable) {
    try { map.removeControl(forest_fireCommuneTable); } catch {}
    forest_fireCommuneTable = null;
  }

  if (typeof forestAgbRemoveControls === 'function') {
    try { forestAgbRemoveControls(); } catch {}
  } else {
    if (typeof forestAgbLayer !== 'undefined' && forestAgbLayer) {
      try { map.removeLayer(forestAgbLayer); } catch {}
      try { layerControl.removeLayer(forestAgbLayer); } catch {}
      forestAgbLayer = null;
    }
    if (typeof forestAgbLegend !== 'undefined' && forestAgbLegend) {
      try { map.removeControl(forestAgbLegend); } catch {}
      forestAgbLegend = null;
    }
    if (typeof forestAgbStatsControl !== 'undefined' && forestAgbStatsControl) {
      try { map.removeControl(forestAgbStatsControl); } catch {}
      forestAgbStatsControl = null;
    }
    if (typeof forestAgbDrawControl !== 'undefined' && forestAgbDrawControl) {
      try { map.removeControl(forestAgbDrawControl); } catch {}
      forestAgbDrawControl = null;
    }
  }
  
  if (agriCommuneTable) {
    try { map.removeControl(agriCommuneTable); } catch {}
    agriCommuneTable = null;
  }
 
  if (landuseCommuneTable) {
    try { map.removeControl(landuseCommuneTable); } catch {}
    landuseCommuneTable = null;
  }

  document.querySelectorAll('.side-label').forEach(el => el.remove());
}

// === Khi chuyển tác vụ ===
function handleTaskChange(taskName) {
  // Nếu KHÔNG phải Planet thì xóa tất cả các thành phần Planet
  if (taskName.toLowerCase() !== 'planet') {
    clearPlanetElements();
  }
}

function setUavMode(enabled) {
  if (enabled) {
    // Ẩn công cụ thống kê vùng của AGB S2 khi vào tab UAV
    if (typeof forestAgbRemoveControls === 'function') {
      try { forestAgbRemoveControls(); } catch {}
    }
    if (typeof window.showUavAgbWorkspace === 'function') {
      window.showUavAgbWorkspace();
    }
    return;
  }
  if (typeof window.hideUavAgbWorkspace === 'function') {
    window.hideUavAgbWorkspace();
  }
}

document.addEventListener('DOMContentLoaded', async () => {

  await loadProvinces()
  // Lấy các select
  const province = document.getElementById('provinceSelect')
  const districts = document.getElementById('districtSelect');
  const satelliteSelect = document.getElementById('satelliteSelect');
  const indexSelect = document.getElementById('indexSelect');
  const end = document.getElementById('endDate');
  const satelliteDetect = document.getElementById('satelliteDetect');
  const satelliteFile = document.getElementById('satelliteFile');



  // Đặt về mặc định
  satelliteSelect.value = "";
  indexSelect.value = "";
  // mặc định chọn "Thành phố Hà Nội" nếu có, nếu không thì chọn tỉnh đầu tiên
  if (!province.value) {
    const hanoiiOption = Array.from(province.options).find(o => o.value === 'Thành phố Hà Nội');
    const firstProv = Array.from(province.options).find(o => o.value);
    const toSelect = hanoiiOption || firstProv;
    if (toSelect) {
      province.value = toSelect.value;
      try {
        await loadDistrictsByProvince(normalize_name(province.value));
        if (typeof currentDistrictGeoJSON !== 'undefined' && currentDistrictGeoJSON) {
          updateDistrictBoundaryLayer(currentDistrictGeoJSON);
        }
      } catch (err) {
        console.error('Không thể tự động tải danh sách xã/phường:', err);
      }
    }
  }
  satelliteDetect.value = "";
  clearDistrictSelection(districts);
  if (satelliteFile) {
    satelliteFile.value = "";
  }
  const today = new Date();
  const yyyy = today.getFullYear();
  const mm = String(today.getMonth() + 1).padStart(2, '0');
  const dd = String(today.getDate()).padStart(2, '0');
  end.value = `${yyyy}-${mm}-${dd}`;

  province.addEventListener('change', async function() {
    satelliteSelect.value = "";
    indexSelect.value = "";
    satelliteDetect.value = "";
    setUavMode(false);

    const provinceName = normalize_name(this.value);
    if (!provinceName) return;

    try {
      await loadDistrictsByProvince(provinceName);

      // Xóa các layer ngoài bản đồ mặc định
      map.eachLayer(function (layer) {
        if (layer !== osm && layer !== SIRDXTBase && layer !== googleSat) {
          map.removeLayer(layer);
        }
      });
      districtBoundaryLayer = null;

      // Reset lại overlayMaps và layerControl
      for (let key in overlayMaps) {
        delete overlayMaps[key];
      }

      // Thêm lại layerControl
      layerControl.remove();
      layerControl = L.control.layers(baseMaps, overlayMaps).addTo(map);

      if (typeof currentDistrictGeoJSON !== 'undefined' && currentDistrictGeoJSON) {
        updateDistrictBoundaryLayer(currentDistrictGeoJSON);
      }

      // Fetch dữ liệu bbox và zoom tới tỉnh
      const response = await fetch(`/province?provinceSelect=${encodeURIComponent(provinceName)}`);
      const text = await response.text();
      let data;
      try {
        data = JSON.parse(text);
      } catch (e) {
        console.error("Không thể parse JSON:", e);
        alert("Phản hồi từ server không phải JSON.");
        return;
      }

      if (data.error) {
        console.error(data.error);
        alert("Không tìm thấy dữ liệu cho " + provinceName);
        return;
      }

      const bbox = data.bbox;
      const bounds = [
        [bbox.miny, bbox.minx],
        [bbox.maxy, bbox.maxx]
      ];
      map.fitBounds(bounds);

    } catch (err) {
      console.error("Lỗi tải ranh giới tỉnh:", err);
    }
});

  districts.addEventListener('change', async function() {
    satelliteSelect.value = "";
    indexSelect.value = "";
    satelliteDetect.value = "";
    setUavMode(false);
    const districtNames = getSelectedDistrictValues();
    const districtName = districtNames[0] || "";
    const province = normalize_name(document.getElementById('provinceSelect').value);
    handleTaskChange(districtName || 'district');
    try {
      map.eachLayer(function (layer) {
        if (layer !== osm && layer !== SIRDXTBase && layer !== googleSat) {
          map.removeLayer(layer);
        }
      });
      districtBoundaryLayer = null;

      for (let key in overlayMaps) {
        delete overlayMaps[key];
      }

      layerControl.remove();
      layerControl = L.control.layers(baseMaps, overlayMaps).addTo(map);

      if (!districtNames.length) {
        if (typeof currentDistrictGeoJSON !== 'undefined' && currentDistrictGeoJSON) {
          updateDistrictBoundaryLayer(currentDistrictGeoJSON);
        }
        const response = await fetch(`/province?provinceSelect=${encodeURIComponent(province)}`);
        const text = await response.text();

        let data;
        try {
          data = JSON.parse(text);
        } catch (e) {
          console.error("Không thể parse JSON:", e);
          alert("Phản hồi từ server không phải JSON. Kiểm tra console để xem chi tiết.");
          return;
        }

        if (data.error) {
          console.error(data.error);
          alert("Không tìm thấy dữ liệu cho " + province);
          return;
        }

        const bbox = data.bbox;
        const bounds = [
          [bbox.miny, bbox.minx],
          [bbox.maxy, bbox.maxx]
        ];
        map.fitBounds(bounds);
        return;
      }

      const response = await fetch(
        `/load-district-geometry?provinceSelect=${encodeURIComponent(province)}&districtSelect=${encodeURIComponent(districtNames.join(','))}`
      );
      const text = await response.text();

      let data;
      try {
        data = JSON.parse(text);
      } catch (e) {
        console.error("Không thể parse JSON:", e);
        alert("Phản hồi từ server không phải JSON. Kiểm tra console để xem chi tiết.");
        return;
      }

      if (data.error) {
        console.error(data.error);
        alert("Không tìm thấy dữ liệu cho " + districtNames.join(', '));
        return;
      }

      updateDistrictBoundaryLayer(data);

      const bbox = data.bbox;
      const bounds = [
        [bbox.miny, bbox.minx],
        [bbox.maxy, bbox.maxx]
      ];
      map.fitBounds(bounds);

    } catch (err) {
      console.error("Lỗi tải ranh giới tỉnh:", err);
    }
  })   


  end.addEventListener('change', async function() {
    satelliteSelect.value = "";
    indexSelect.value = "";
    satelliteDetect.value = "";
  });
 

  // Thêm sự kiện change cho satellite
  satelliteSelect.addEventListener('change', async function() {
    const choice = this.value;
    setUavMode(false);
    handleTaskChange(choice);
    if (choice === 's1') {
      loadSentinel1();
    } else if (choice === 's2') {
      loadSentinel2();
    } else if (choice === 'planet') {
      loadPlanet();
    } else {
      return
    }
  });

  satelliteDetect.addEventListener('change', async function() {
    const choice = this.value;
    const districts = getSelectedDistrictValues();
    const province = document.getElementById('provinceSelect').value;
    indexSelect.value = "";

    // Công cụ thống kê theo vùng chỉ dùng cho AGB UAV / AGB S2
    const isAgbRegionStats = choice === "forerest_agb_uav" || choice === "forerest_agb";
    if (!isAgbRegionStats && typeof forestAgbRemoveControls === 'function') {
      try { forestAgbRemoveControls(); } catch {}
    }

    if (choice === "forerest_agb_uav") {
      handleTaskChange(choice);
      setUavMode(true);
      return;
    }
    setUavMode(false);
    if (province === "") {
      alert("Vui lòng chọn khu vực tỉnh/thành phố!");
      return;
    }
    handleTaskChange(choice);
    clearMapLayersPreservingBoundary();
    rebuildLayerControlPreservingBoundary();

    if (choice === "build") {
      if (districts.length === 0) {
        alert("Vui lòng chọn khu vực xã/phường!");
        return;
      }

      showPeriodPopup(period => {
        if (!period) return; // Người dùng hủy

        // Gọi hàm xử lý với giá trị chọn
        loadPlanetBuild();
        loadBuild(period);
      });
    
    } else if (choice === "flood") {
      
      loadFloodLayer()
    } else if (choice === "drought") {
      if (districts.length === 0) {
        alert("Vui lòng chọn khu vực tỉnh/thành phố!");
        return;
      }
      loadDroughtLayer()
    } else if (choice === "fire") {
      showPeriodPopup(period => {
        if (!period) return; // Người dùng hủy

        // Gọi hàm xử lý với giá trị chọn
        loadPlanetBuild();
        loadForerest(period);
      });
    } else if (choice === "forerest_fire") {
      loadForestFire()  
    } else if (choice === "forerest_agb") {
      loadForestAgb();
    } else if (choice === "landslide") {
      showPeriodPopup(period => {
        if (!period) return;

        loadPlanetBuild();
        loadLandslide(period);
      });
    } else {
      return;
    }
  });


  // Thêm sự kiện change cho index (nếu cần xử lý)
  indexSelect.addEventListener('change', function() {
    const selectedIndex = this.value;
    satelliteDetect.value = "";
    setUavMode(false);
    handleTaskChange(selectedIndex);
    clearMapLayersPreservingBoundary();
    rebuildLayerControlPreservingBoundary();

    if (selectedIndex === "") return
    loadIndex(selectedIndex);
    bindIndexPopup(map, 'indexSelect', `/${selectedIndex}_value`);
  });
});

function showPeriodPopup(callback) {
  // Tạo nền mờ
  const overlay = document.createElement("div");
  overlay.style = `
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.4);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 9999;
  `;

  // Tạo hộp popup
  const popup = document.createElement("div");
  popup.style = `
    background: #fff;
    padding: 20px 28px;
    border-radius: 12px;
    box-shadow: 0 6px 20px rgba(0,0,0,0.25);
    width: 300px;
    font-family: 'Segoe UI', sans-serif;
    text-align: center;
    animation: fadeIn 0.2s ease-out;
  `;

  popup.innerHTML = `
    <h3 style="margin-top: 0; color: #333;">🕓 Chọn khoảng thời gian</h3>
    <p style="margin-bottom: 18px; color: #555; font-size: 14px;">
      Vui lòng chọn khoảng thời gian giám sát:
    </p>
    <div style="display: flex; flex-direction: column; gap: 10px;">
      <button data-value="halfmonth" style="padding: 8px; border:none; background:#0078d7; color:#fff; border-radius:6px; cursor:pointer;">Nửa tháng</button>
      <button data-value="month" style="padding: 8px; border:none; background:#2ecc71; color:#fff; border-radius:6px; cursor:pointer;">Tháng</button>
      <button data-value="quarter" style="padding: 8px; border:none; background:#e67e22; color:#fff; border-radius:6px; cursor:pointer;">Quý</button>
      <button id="cancel-btn" style="padding: 8px; border:none; background:#f28b82; color:#fff; border-radius:6px; cursor:pointer;">Hủy</button>
      </div>
  `;

  overlay.appendChild(popup);
  document.body.appendChild(overlay);

  // Gán sự kiện chọn
  popup.querySelectorAll("button[data-value]").forEach(btn => {
    btn.addEventListener("click", () => {
      const value = btn.getAttribute("data-value");
      document.body.removeChild(overlay);
      callback(value);
    });
  });

  // Nút Hủy
  popup.querySelector("#cancel-btn").addEventListener("click", () => {
    document.body.removeChild(overlay);
    callback(null);
  });
}

async function loadModules() {
    try {
        const resp = await fetch("/modules");
        if (!resp.ok) throw new Error(`Server trả về lỗi ${resp.status}`);
        const modules = await resp.json();

        const moduleSelect = document.getElementById("moduleSelect");

        // Xóa option cũ (trừ placeholder)
        moduleSelect.querySelectorAll("option:not([value=''])").forEach(opt => opt.remove());

        // Thêm module mới
        modules.forEach(mod => {
            const option = document.createElement("option");
            option.value = mod.value;   // gửi về server
            option.textContent = mod.label; // hiển thị
            moduleSelect.appendChild(option);
        });
    } catch (err) {
        console.error("Không tải được danh sách module:", err);
        alert("Lỗi tải danh sách module từ server!");
    }
}

// Gọi khi load trang
loadModules();

const aiType = document.getElementById("aiType");
const geoaiControls = document.getElementById("geoaiControls");
const torchgeoControls = document.getElementById("torchgeoControls");
const runBtn = document.getElementById("runModule");

aiType.onchange = () => {
    if (aiType.value === "GeoAI") {
        geoaiControls.style.display = "block";
        torchgeoControls.style.display = "none";
        runBtn.textContent = "Chạy GeoAI";
    } else {
        geoaiControls.style.display = "none";
        torchgeoControls.style.display = "block";
        runBtn.textContent = "Chạy TorchGeo";
    }
};
let originalOverlay = null;

const satelliteFileInput = document.getElementById("satelliteFile");

if (satelliteFileInput) {
  satelliteFileInput.addEventListener("change", function (event) {
    const files = event.target.files;
    if (!files.length) return;

  Array.from(files).forEach((file, index) => {
    const reader = new FileReader();

    reader.onload = function (e) {
      const arrayBuffer = e.target.result;

      // Dùng parseGeoraster để đọc GeoTIFF từ ArrayBuffer
      parseGeoraster(arrayBuffer).then(georaster => {
        originalOverlay = new GeoRasterLayer({
          georaster,
          opacity: 1,
          resolution: 256,
          pixelValuesToColorFn: values => {
            if (!values) return null;
            if (values.length >= 3) {
              // ảnh RGB (3 band)
              return `rgb(${values[0]}, ${values[1]}, ${values[2]})`;
            } else {
              // ảnh đơn band: tô màu theo giá trị
              const val = values[0];
              if (isNaN(val)) return null;
              return val > 200 ? "#f00" : val > 100 ? "#ff0" : "#0f0";
            }
          }
        });

        // Thêm lên bản đồ và control
        originalOverlay.addTo(map);
        overlayMaps[file.name] = originalOverlay;
        layerControl.addOverlay(originalOverlay, file.name);

        // Zoom tới vùng ảnh đầu tiên
        if (index === 0) map.fitBounds(originalOverlay.getBounds());
      }).catch(err => {
        console.error("Lỗi đọc GeoTIFF:", err);
        alert("Không thể đọc file: " + file.name);
      });
    };

      reader.readAsArrayBuffer(file); // Đọc file dưới dạng binary buffer
    });
  });
}

runBtn.onclick = async () => {
    const moduleSelect = document.getElementById("moduleSelect").value;
    const districts = getSelectedDistrictValues();
    const province = document.getElementById('provinceSelect').value
    handleTaskChange(moduleSelect)
    if (moduleSelect === "change_detection") {
      if (districts.length === 0) {
        alert("Vui lòng chọn khu vực xã/phường!");
        return;
      }
      loadLanduse()
    } else if (moduleSelect === "classify") {
      if (province === "") {
        alert("Vui lòng chọn khu vực xã/phường!");
        return;
      }
      model_agri_classify()
    } else {
      return;
    }
    
    // const fileInput = document.getElementById("satelliteFile");
    // if (!fileInput.files.length) {
    //     alert("Vui lòng chọn ảnh.");
    //     return;
    // }

    // let formData = new FormData();
    // formData.append("aiType", aiType.value);
    // formData.append("image", fileInput.files[0]);

    // if (aiType.value === "GeoAI") {
    //     const moduleSelect = document.getElementById("moduleSelect");
    //     if (!moduleSelect.value) { alert("Chọn module GeoAI."); return; }
    //     formData.append("module", moduleSelect.value);
    // } else {
    //     const modelSelect = document.getElementById("torchModel");
    //     const numClasses = document.getElementById("numClasses");
    //     formData.append("torchModel", modelSelect.value);
    //     formData.append("numClasses", numClasses.value);
    // }

    // let resp = await fetch("/process", { method:"POST", body:formData });
    // let data = await resp.json();

    // if(data.success){
    //     // Fetch GeoTIFF từ URL và hiển thị bằng GeoRasterLayer
    //     const geotiffUrl = data.result;
    //     fetch(geotiffUrl)
    //         .then(response => response.arrayBuffer())
    //         .then(arrayBuffer => {
    //             parseGeoraster(arrayBuffer).then(georaster => {
    //                 const layerName = aiType.value + (aiType.value==="GeoAI"? "_"+document.getElementById("moduleSelect").value:"_"+document.getElementById("torchModel").value);
    //                 const overlay = new GeoRasterLayer({
    //                     georaster: georaster,
    //                     opacity: 1,
    //                     resolution: 256,
    //                     pixelValuesToColorFn: values => {
    //                         if (!values) return null;
    //                         const val = values[0];
    //                         if (isNaN(val)) return null;
    //                         // Tô màu theo giá trị (có thể tùy chỉnh)
    //                         return val > 200 ? "#f00" : val > 100 ? "#ff0" : "#0f0";
    //                     }
    //                 });
    //                 overlay.addTo(map);
    //                 overlayMaps[layerName] = overlay;
    //                 layerControl.remove();
    //                 layerControl = L.control.layers({"OpenStreetMap": osm}, overlayMaps).addTo(map);
    //                 map.fitBounds(overlay.getBounds());
    //                 alert("✅ Xử lý xong!");
    //             }).catch(err => {
    //                 console.error("Lỗi parse GeoTIFF:", err);
    //                 alert("⚠️ Lỗi hiển thị GeoTIFF: " + err.message);
    //             });
    //         })
    //         .catch(err => {
    //             console.error("Lỗi fetch GeoTIFF:", err);
    //             alert("⚠️ Lỗi tải GeoTIFF: " + err.message);
    //         });
    // } else {
    //     alert("⚠️ " + data.message);
    // }
};


// runBtn.onclick = async () => {
//     const fileInput = document.getElementById("satelliteFile");
//     if (!fileInput.files.length) {
//         alert("Vui lòng chọn ảnh.");
//         return;
//     }

//     let formData = new FormData();
//     formData.append("aiType", aiType.value);
//     formData.append("image", fileInput.files[0]);

//     if (aiType.value === "GeoAI") {
//         const moduleSelect = document.getElementById("moduleSelect");
//         if (!moduleSelect.value) { alert("Chọn module GeoAI."); return; }
//         formData.append("module", moduleSelect.value);
//     } else {
//         const modelSelect = document.getElementById("torchModel");
//         const numClasses = document.getElementById("numClasses");
//         formData.append("torchModel", modelSelect.value);
//         formData.append("numClasses", numClasses.value);
//     }

//     let resp = await fetch("/process", { method:"POST", body:formData });
//     let data = await resp.json();

//     if(data.success){
//         let bounds = map.getBounds();
//         if (data.bbox) {
//             bounds = L.latLngBounds(
//                 [data.bbox[0], data.bbox[1]],
//                 [data.bbox[2], data.bbox[3]]
//             );
//             map.fitBounds(bounds);
//         }

//         let overlay = L.imageOverlay(data.result, bounds).addTo(map);
//         overlayMaps[aiType.value + "_" + (aiType.value==="GeoAI" ? document.getElementById("moduleSelect").value : document.getElementById("torchModel").value)] = overlay;

//         if (layerControl) map.removeControl(layerControl);
//         layerControl = L.control.layers(baseMaps, overlayMaps).addTo(map);

//         alert("✅ Xử lý xong! Có thể bật/tắt layer bằng Layer Control.");
//     } else {
//         alert("⚠️ " + data.message);
//     }
// };

// document.getElementById('s1Btn').onclick = loadSentinel1;
// document.getElementById('s2Btn').onclick = loadSentinel2;
// document.getElementById('ndviBtn').onclick = loadNDVI;
