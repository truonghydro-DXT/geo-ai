
let forerestLayer;
let forerestLegend; // giữ legend để xóa khi thêm mới
let forerestStatsControl;
let locationInfoMode = false;
let forerestDownloadUrl = null;
let forerestVectorDownloadUrl = null;

function normalize_name(name) {
  return name.replace(/Thành\s*phố\s*/i, 'tp')
             .replace(/Tỉnh\s*/i, 'tinh')
             .normalize("NFD").replace(/[\u0300-\u036f]/g, "")
             .replace(/đ/g, "d").replace(/Đ/g, "D")
             .replace(/\s+/g, '');
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function renderCommuneAreaTable(areaByCommune) {
  if (!Array.isArray(areaByCommune) || areaByCommune.length === 0) {
    return `
      <div style="font-size:12px; color:#666; font-style:italic;">
        Không có dữ liệu diện tích theo xã.
      </div>
    `;
  }

  const rows = areaByCommune.map((item, index) => `
    <tr>
      <td style="padding:4px 6px; border-bottom:1px solid #eee; text-align:center;">${index + 1}</td>
      <td style="padding:4px 6px; border-bottom:1px solid #eee;">${escapeHtml(item.tenxa)}</td>
      <td style="padding:4px 6px; border-bottom:1px solid #eee; text-align:right; white-space:nowrap;">${Number(item.area_ha || 0).toFixed(2)}</td>
    </tr>
  `).join("");

  return `
    <div style="max-height:180px; overflow:auto; border:1px solid #e6e6e6; border-radius:6px;">
      <table style="width:100%; border-collapse:collapse; font-size:12px;">
        <thead>
          <tr style="background:#f7f7f7; position:sticky; top:0; z-index:1;">
            <th style="padding:4px 6px; border-bottom:1px solid #ddd; width:28px;">#</th>
            <th style="padding:4px 6px; border-bottom:1px solid #ddd; text-align:left;">Tên xã</th>
            <th style="padding:4px 6px; border-bottom:1px solid #ddd; text-align:right; width:72px;">ha</th>
          </tr>
        </thead>
        <tbody>
          ${rows}
        </tbody>
      </table>
    </div>
  `;
}

function getVn2000Zone(lon) {
  return lon >= 108 ? 49 : 48;
}

function convertWgs84ToVn2000(lat, lon) {
  if (typeof proj4 === "undefined") {
    return null;
  }

  const zone = getVn2000Zone(lon);
  const vn2000Crs = `+proj=utm +zone=${zone} +ellps=GRS80 +units=m +no_defs`;
  const [x, y] = proj4("EPSG:4326", vn2000Crs, [lon, lat]);

  return {
    x,
    y,
    zone
  };
}

async function loadForerest(period) {
  const province = normalize_name(document.getElementById("provinceSelect").value);
  const districts = Array.from(document.getElementById("districtSelect").selectedOptions)
    .map(o => o.value).filter(Boolean).join(',');
  const end = document.getElementById("endDate").value;

  if (!province) {
    alert("Vui lòng chọn tỉnh/thành phố!");
    return;
  }

  if (!end) {
    alert("Vui lòng chọn thời điểm giám sát!");
    return;
  }

  const endDateObj = new Date(end);
  const startDateObj = new Date(endDateObj);
  let daysRange = 15; // mặc định nửa tháng
  if (period === "month") daysRange = 30;
  else if (period === "quarter") daysRange = 90;

  startDateObj.setDate(endDateObj.getDate() - daysRange);
  const start = startDateObj.toISOString().split("T")[0];
  const month = endDateObj.getMonth() + 1;
  const year = endDateObj.getFullYear();

  // === Hiển thị popup tiến trình ===
  const popup = document.createElement("div");
  popup.id = "loading-popup";
  popup.innerHTML = `
    <div class="popup-box">
      <h3>Đang xác định mất rừng</h3>
      <div class="progress-bar"><div class="progress-fill"></div></div>
      <p class="progress-text">0%</p>
    </div>
  `;
  document.body.appendChild(popup);

  const progressFill = popup.querySelector(".progress-fill");
  const progressText = popup.querySelector(".progress-text");

  let progress = 0;
  const progressTimer = setInterval(() => {
    progress += 5;
    if (progress >= 90) progress = 90;
    progressFill.style.width = `${progress}%`;
    progressText.textContent = `${progress}%`;
  }, 500);

  try {
    const resp = await fetch(`/forerest_detect?start=${start}&end=${end}&provinceSelect=${encodeURIComponent(province)}&districtSelect=${encodeURIComponent(districts)}`);
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      const detail = data.error || data.message || data.details || "";
      throw new Error(detail ? `Server trả về lỗi ${resp.status}: ${detail}` : `Server trả về lỗi ${resp.status}`);
    }
    console.log("Forest response:", data);
    if (!data.tile_url) throw new Error("Không có tile URL trả về từ server");
    forerestDownloadUrl = data.download_url || null;
    forerestVectorDownloadUrl = data.vector_download_url || null;

    clearInterval(progressTimer);
    progressFill.style.width = "100%";
    progressText.textContent = "Hoàn tất!";
    setTimeout(() => popup.remove(), 700);

    // Xóa layer và legend cũ nếu có
    if (forerestLayer) {
      map.removeLayer(forerestLayer);
      layerControl.removeLayer(forerestLayer);
      Object.keys(overlayMaps).forEach(key => {
        if (key.startsWith("Biến động rừng")) {
            delete overlayMaps[key];
        }
      });
    }
    if (forerestLegend) {
      map.removeControl(forerestLegend);
    }
    if (forerestStatsControl) {
      map.removeControl(forerestStatsControl);
    }

    // Tạo layer mới
    forerestLayer = L.tileLayer(data.tile_url).addTo(map);
    if (data.largest_patch?.center) {

        const lon = data.largest_patch.center[0];
        const lat = data.largest_patch.center[1];

        console.log("Forest center:", lat, lon);

        map.flyTo(
            [lat, lon],
            14,
            {
                animate: true,
                duration: 2
            }
        );
    }

    
    const label = `Biến động rừng (${month}/${year})`;
    overlayMaps[label] = forerestLayer;
    layerControl.addOverlay(forerestLayer, label);

    // === 🟡 TẠO LEGEND ===
    const vis_params = {
      min: 0,
      max: 1,
      palette: ['black', 'red']
    };
    const showCommuneTable = !districts;
    const communeStatsHtml = showCommuneTable
      ? renderCommuneAreaTable(data.area_ha_by_commune)
      : "";

    forerestLegend = L.control({ position: 'bottomright'});

    forerestStatsControl = L.control({ position: 'bottomleft' });

    forerestStatsControl.onAdd = function () {
      const div = L.DomUtil.create('div', 'info legend');
      div.style.marginBottom = '18px';
      div.style.marginLeft = '8px';
      div.style.background = 'rgba(255, 255, 255, 0.92)';
      div.style.padding = '8px 10px';
      div.style.borderRadius = '8px';
      div.style.boxShadow = '0 2px 8px rgba(0,0,0,0.22)';
      div.style.fontFamily = 'Segoe UI, sans-serif';
      div.style.color = '#222';
      div.style.fontSize = '12px';
      div.style.lineHeight = '1.35';
      div.style.maxWidth = '260px';
      div.style.maxHeight = '220px';
      div.style.overflow = 'auto';

      div.innerHTML = `
        <div style="font-weight:700; margin-bottom:6px; font-size:13px; text-align:left;">
          Thống kê biến động
        </div>

        <div style="margin-bottom:8px;">
          <div style="font-size:11px; color:#666; margin-bottom:2px;">Diện tích mất rừng</div>
          <div style="font-weight:700; color:#d00; font-size:14px;">
            ${data.area_ha ? data.area_ha.toFixed(2) : "0.00"} ha
          </div>
        </div>

        ${showCommuneTable ? `
          <div style="font-weight:600; margin:8px 0 6px; font-size:12px;">Diện tích theo xã</div>
          ${communeStatsHtml}
        ` : ""}
      `;

      L.DomEvent.disableClickPropagation(div);
      return div;
    };

    forerestLegend.onAdd = function () {
      const div = L.DomUtil.create('div', 'info legend');
      div.style.marginBottom = '18px';
      div.style.marginRight = '8px';
      div.style.background = 'rgba(255, 255, 255, 0.9)';
      div.style.padding = '8px 10px';
      div.style.borderRadius = '8px';
      div.style.boxShadow = '0 2px 8px rgba(0,0,0,0.25)';
      div.style.lineHeight = '18px';
      div.style.fontSize = '12px';
      div.style.fontFamily = 'Segoe UI, sans-serif';
      div.style.color = '#222';
      div.style.maxWidth = '240px';

      // Nội dung legend được căn hàng bằng flex
      div.innerHTML = `
        <div style="font-weight:700; text-align:center; margin-bottom:6px; font-size:13px;">
          Biến động rừng (${month}/${year})
        </div>

        <div style="display:flex; align-items:center; margin-bottom:4px; gap:6px;">
          <div style="width:12px; height:12px; background:${vis_params.palette[0]};
                      border:1px solid #999; border-radius:2px; flex:0 0 auto;"></div>
          <span>Rừng trồng mới</span>
        </div>

        <div style="display:flex; align-items:center; margin-bottom:6px; gap:6px;">
          <div style="width:12px; height:12px; background:${vis_params.palette[1]};
                      border:1px solid #999; border-radius:2px; flex:0 0 auto;"></div>
          <span>Rừng bị mất</span>
        </div>

        <hr style="border:none; border-top:1px solid #ccc; margin:8px 0;">

        <button id="btn-location-info"
          style="
            width:100%;
            padding:7px 8px;
            background:#1976d2;
            color:white;
            border:none;
            border-radius:5px;
            cursor:pointer;
            font-size:12px;
            font-weight:600;">
          📍 Thông tin vị trí
      </button>

          <button id="btn-download-result"
            style="
            width:100%;
            margin-top:6px;
            padding:7px 8px;
            background:#2e7d32;
            color:white;
            border:none;
            border-radius:5px;
            cursor:pointer;
            font-size:12px;
            font-weight:600;">
            ⬇ Tải kết quả
          </button>
      `;
      // Ngăn click legend làm kéo map
      L.DomEvent.disableClickPropagation(div);

      // Gắn sự kiện sau khi button được tạo
      setTimeout(() => {
          const btn = div.querySelector("#btn-location-info");
            const downloadBtn = div.querySelector("#btn-download-result");
          if (btn) {
              btn.onclick = function () {
                  locationInfoMode = true;
                  btn.innerHTML = "✔ Chọn vị trí trên bản đồ";
                  btn.style.background = "#f57c00";
              };
          }

            if (downloadBtn) {
              downloadBtn.onclick = function () {
                // Prefer vector GeoJSON if available
                if (forerestVectorDownloadUrl) {
                  const fname = `forerest_result_${month}_${year}.geojson`;
                  const a = document.createElement('a');
                  a.href = forerestVectorDownloadUrl;
                  a.download = fname;
                  a.rel = 'noopener';
                  document.body.appendChild(a);
                  a.click();
                  a.remove();
                  return;
                }

                if (!forerestDownloadUrl) {
                  alert("Chưa có đường dẫn tải kết quả.");
                  return;
                }

                const fileName = `forerest_result_${month}_${year}.tif`;
                const link = document.createElement("a");
                link.href = forerestDownloadUrl;
                link.download = fileName;
                link.rel = "noopener";
                document.body.appendChild(link);
                link.click();
                link.remove();
              };
            }

      }, 100);

      return div;
    };
    forerestStatsControl.addTo(map);
    forerestLegend.addTo(map);

  } catch (err) {
    clearInterval(progressTimer);
    popup.remove();
    console.error(err);
    alert("Lỗi tải Sentinel-1: " + err.message);
  }
  map.on("click", async function(e) {

    if (!locationInfoMode)
        return;

    locationInfoMode = false;

    const lat = e.latlng.lat;
    const lon = e.latlng.lng;
    const vn2000 = convertWgs84ToVn2000(lat, lon);

    try {

        const response = await fetch(
            `https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=${lat}&lon=${lon}`
        );

        const geo = await response.json();

        const address =
            geo.display_name || "Không xác định";

        const vn2000Html = vn2000
          ? `
              <b>VN2000 (UTM zone ${vn2000.zone}N):</b><br>
              X: ${vn2000.x.toFixed(3)}<br>
              Y: ${vn2000.y.toFixed(3)}<br><br>
            `
          : `
              <b>VN2000:</b><br>
              Không thể chuyển đổi do thiếu thư viện proj4.<br><br>
            `;

        L.popup()
            .setLatLng([lat, lon])
            .setContent(`
                <div style="font-size:13px;">
                    <b>Thông tin vị trí</b><br><br>

              <b>WGS84:</b><br>
              Vĩ độ: ${lat.toFixed(6)}<br>
              Kinh độ: ${lon.toFixed(6)}<br><br>

              ${vn2000Html}

                    <b>Địa chỉ:</b><br>
                    ${address}
                </div>
            `)
            .openOn(map);
    }
    catch(err){
        console.error(err);
    }
  });

}
