// Base map — OSM.org is often blocked in-browser; reuse the local tile proxy.
const osm = L.tileLayer('/uav/basemap/{z}/{x}/{y}.png', {
  attribution: '&copy; OpenStreetMap contributors',
  maxZoom: 22,
  maxNativeZoom: 19,
  errorTileUrl: '/uav/static/vendor/empty-tile.png',
});
const googleSat = L.tileLayer('https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}')

// Map khởi tạo
const map = L.map('map', {
  center: [21.03, 105.85],
  zoom: 10,
  layers: [osm] // mặc định chỉ OSM
});

// Quản lý layer
const baseMaps = {
  "OpenStreetMap": osm,
  "Google Satellite": googleSat
};

const overlayMaps = {};  // Sentinel-1 sẽ add động vào đây
const QUY_HOACH_LAYER_LABEL_FALLBACK = "Bản đồ quy hoạch 2030";

function getQuyHoachLayerLabel() {
  return window.QUY_HOACH_LAYER_LABEL || QUY_HOACH_LAYER_LABEL_FALLBACK;
}

function clearOverlayMapsPreservingQuyHoach() {
  const quyHoachLabel = getQuyHoachLayerLabel();

  for (let key in overlayMaps) {
    if (key !== quyHoachLabel) {
      delete overlayMaps[key];
    }
  }
}

function rebuildLayerControl() {
  if (layerControl && typeof layerControl.remove === 'function') {
    layerControl.remove();
  }

  layerControl = L.control.layers(baseMaps, overlayMaps).addTo(map);
}

// Control
let layerControl = L.control.layers(baseMaps, overlayMaps).addTo(map);
let districtBoundaryLayer = null;

function loadScriptOnce(src) {
  if (document.querySelector(`script[src="${src}"]`)) {
    return Promise.resolve();
  }

  return new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = src;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error(`Không tải được script: ${src}`));
    document.head.appendChild(script);
  });
}

loadScriptOnce('mapshow/map-quyhoach.js').catch(error => {
  console.error('Lỗi nạp lớp quy hoạch 2030:', error);
});

async function loadProvinces() {
  const provinces = ["Tỉnh Nghệ An"];

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
             .replace(/\s+/g, '')
             .toLowerCase();
}

function updateDistrictBoundaryLayer(geojson) {
  if (districtBoundaryLayer && map.hasLayer(districtBoundaryLayer)) {
    map.removeLayer(districtBoundaryLayer);
  }
  delete overlayMaps['Lớp ranh giới'];

  districtBoundaryLayer = L.geoJSON(geojson, {
    style: {
      color: '#d7191c',
      weight: 3,
      opacity: 1,
      fillColor: '#d7191c',
      fillOpacity: 0.08
    }
  }).addTo(map);

  overlayMaps['Lớp ranh giới'] = districtBoundaryLayer;
  layerControl.addOverlay(districtBoundaryLayer, 'Lớp ranh giới');
}

async function loadDistrictsByProvince(tentinh) {
  const url = `/load-districts?provinceSelect=${encodeURIComponent(tentinh)}`;

  const res = await fetch(url);
  if (!res.ok) {
    const message = await res.text().catch(() => '');
    throw new Error(`HTTP ${res.status}${message ? `: ${message}` : ''}`);
  }
  const data = await res.json();

  currentDistrictGeoJSON = data;

  const districtSelect = document.getElementById('districtSelect');
  districtSelect.innerHTML = '<option value="">-- Chọn xã/phường --</option>';
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
  
  if (legendControl) {
    try { map.removeControl(legendControl); } catch {}
    legendControl = null;
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

  if (forerestStatsControl) {
    try { map.removeControl(forerestStatsControl); } catch {}
    forerestStatsControl = null;
  };

if (typeof forestAgbRemoveControls === 'function') {
    try { forestAgbRemoveControls(); } catch {}
  } else {
    if (forestAgbLayer) {
      try { map.removeControl(forestAgbLayer); } catch {}
      forestAgbLayer = null;
    };
    if (forestAgbLegend) {
      try { map.removeControl(forestAgbLegend); } catch {}
      forestAgbLegend = null;
    };
    if (forestAgbStatsControl) {
      try { map.removeControl(forestAgbStatsControl); } catch {}
      forestAgbStatsControl = null;
    };
    if (typeof forestAgbDrawControl !== 'undefined' && forestAgbDrawControl) {
      try { map.removeControl(forestAgbDrawControl); } catch {}
      forestAgbDrawControl = null;
    }
  }
  document.querySelectorAll('.side-label').forEach(el => el.remove());
}

function setUavMode(enabled) {
  if (enabled) {
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

// === Khi chuyển tác vụ ===
function handleTaskChange(taskName) {
  // Nếu KHÔNG phải Planet thì xóa tất cả các thành phần Planet
  if (taskName.toLowerCase() !== 'planet') {
    clearPlanetElements();
  }
}

document.addEventListener('DOMContentLoaded', () => {

  loadProvinces()
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
  province.value = "";
  satelliteDetect.value = "";
  districts.value = "";
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
    try {
      await loadDistrictsByProvince(provinceName);
    } catch (err) {
      console.error('Lỗi tải danh sách xã/phường:', err);
      alert('Không tải được danh sách xã/phường. Kiểm tra console để xem chi tiết.');
    }
    if (!provinceName) return;

    try {
        // Xóa các layer ngoài bản đồ mặc định
        map.eachLayer(function (layer) {
            if (layer !== osm && layer !== googleSat) {
                map.removeLayer(layer);
            }
        });

        // Reset lại overlayMaps và layerControl
        clearOverlayMapsPreservingQuyHoach();

        // Thêm lại layerControl
        rebuildLayerControl();

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
    const districtNames = Array.from(this.selectedOptions || [])
      .map(option => option.value)
      .filter(Boolean);
    const districtName = districtNames.join(',');
    const province = normalize_name(document.getElementById('provinceSelect').value);
    handleTaskChange(districtName);
    if (!districtName) {
      try {
        map.eachLayer(function (layer) {
          if (layer !== osm && layer !== googleSat) {
                map.removeLayer(layer);
            }
        });

        clearOverlayMapsPreservingQuyHoach();

        rebuildLayerControl();

        // 🚀 Lấy dữ liệu bbox từ server
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
    } else {
      try {
        map.eachLayer(function (layer) {
          if (layer !== osm && layer !== googleSat) {
                map.removeLayer(layer);
          }
        });

        if (districtBoundaryLayer) {
          districtBoundaryLayer = null;
        }

        clearOverlayMapsPreservingQuyHoach();

        rebuildLayerControl();

        // 🚀 Lấy dữ liệu bbox từ server
        const query = new URLSearchParams();
        query.set('provinceSelect', province);
        districtNames.forEach(name => query.append('districtSelect', name));
        const response = await fetch(`/load-district-geometry?${query.toString()}`);
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
          alert("Không tìm thấy dữ liệu cho " + districtName);
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
    }
  })   


  end.addEventListener('change', async function() {
    satelliteSelect.value = "";
    indexSelect.value = "";
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
  const districts = Array.from(document.getElementById("districtSelect").selectedOptions || [])
    .map(option => option.value)
    .filter(Boolean)
    .join(',');
  const province = document.getElementById('provinceSelect').value;
    indexSelect.value = "";

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
    map.eachLayer(function (layer) {
    if (layer !== osm && layer !== googleSat) {
        map.removeLayer(layer);
      }
    });

    clearOverlayMapsPreservingQuyHoach();

    rebuildLayerControl();

    if (choice === "forerest_agb") {
      loadForestAgb();
    } else if (choice === "fire") {
      showPeriodPopup(period => {
        if (!period) return; // Người dùng hủy

        // Gọi hàm xử lý với giá trị chọn
        loadPlanetBuild();
        loadSentinel2();
        // loadForerest(period);
        loadForestLoss(period);
      });
    } else if (choice === "forerest_fire") {
      loadSentinel2();
      loadForestFire()  
    } else {
      return;
    }
  });


  // Thêm sự kiện change cho index (nếu cần xử lý)
  indexSelect.addEventListener('change', function() {
    const selectedIndex = this.value;
    setUavMode(false);
    handleTaskChange(selectedIndex);
    map.eachLayer(function (layer) {
    if (layer !== osm) {
        map.removeLayer(layer);
      }
    });

    clearOverlayMapsPreservingQuyHoach();

    rebuildLayerControl();

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

const runfire = document.getElementById("runfire");

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
// runfire.onclick = async () => {
//     const districts = document.getElementById("districtSelect").value;
//     const province = document.getElementById('provinceSelect')
//     clearPlanetElements();
//     map.eachLayer(function (layer) {
//     if (layer !== osm) {
//         map.removeLayer(layer);
//       }
//     });

//     for (let key in overlayMaps) {
//       delete overlayMaps[key];
//     }

//     layerControl.remove();
//     layerControl = L.control.layers(baseMaps, overlayMaps).addTo(map);
//     if (districts === "") {
//         alert("Vui lòng chọn khu vực tỉnh/thành phố!");
//         return;
//       }
//       showPeriodPopup(period => {
//         if (!period) return; // Người dùng hủy

//         // Gọi hàm xử lý với giá trị chọn
//         loadPlanetBuild();
//         loadForerest(period);
//       });
// }
