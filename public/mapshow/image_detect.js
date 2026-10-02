// let buildLayer;
// function normalize_name(name) {
//   return name.replace(/Thành\s*phố\s*/i, 'tp')
//              .replace(/Tỉnh\s*/i, 'tinh')
//              .normalize("NFD").replace(/[\u0300-\u036f]/g, "")
//              .replace(/đ/g, "d").replace(/Đ/g, "D")
//              .replace(/\s+/g, '');
// }

// async function loadBuild() {
//   const province = normalize_name(document.getElementById("provinceSelect").value);
//   const districts = document.getElementById("districtSelect").value;
//   const end = document.getElementById("endDate").value;

//   if (!province) {
//     alert("Vui lòng chọn tỉnh/thành phố!");
//     return;
//   }

//   if (!end) {
//     alert("Vui lòng chọn thời điểm giám sát!");
//     return;
//   }

//   const endDateObj = new Date(end);
//   const startDateObj = new Date(endDateObj);
//   startDateObj.setDate(endDateObj.getDate() - 35);
//   const start = startDateObj.toISOString().split("T")[0];
//   const month = endDateObj.getMonth() + 1;
//   const year = endDateObj.getFullYear();

//   // === Hiển thị popup tiến trình ===
//   const popup = document.createElement("div");
//   popup.id = "loading-popup";
//   popup.innerHTML = `
//     <div class="popup-box">
//       <h3>Đang phát hiện biến động xây dựng</h3>
//       <div class="progress-bar"><div class="progress-fill"></div></div>
//       <p class="progress-text">0%</p>
//     </div>
//   `;
//   document.body.appendChild(popup);

//   const progressFill = popup.querySelector(".progress-fill");
//   const progressText = popup.querySelector(".progress-text");

//   let progress = 0;
//   const progressTimer = setInterval(() => {
//     progress += 5;
//     if (progress >= 90) progress = 90;
//     progressFill.style.width = `${progress}%`;
//     progressText.textContent = `${progress}%`;
//   }, 500);

//   try {
//     const resp = await fetch(`/build_detect?start=${start}&end=${end}&provinceSelect=${encodeURIComponent(province)}&districtSelect=${encodeURIComponent(districts)}`);
    
//     if (!resp.ok) throw new Error(`Server trả về lỗi ${resp.status}`);

//     const data = await resp.json();
//     if (!data.tile_url) throw new Error("Không có tile URL trả về từ server");

//     clearInterval(progressTimer);
//     progressFill.style.width = "100%";
//     progressText.textContent = "Hoàn tất!";

//     setTimeout(() => popup.remove(), 700);

//     // Xóa layer cũ
//     if (buildLayer) {
//         map.removeLayer(buildLayer);
//         layerControl.removeLayer(buildLayer);
//         delete overlayMaps["Biến động xây dựng"];
//     }

//     // Tạo layer mới
//     buildLayer = L.tileLayer(data.tile_url).addTo(map);

//     // Thêm vào Layer Control
//     const label = `Biến động xây dựng (${month}/${year})`;
//     overlayMaps[label] = buildLayer;
//     layerControl.addOverlay(buildLayer, label);

//   } catch (err) {
//     clearInterval(progressTimer);
//     popup.remove();
//     console.error(err);
//     alert("Lỗi tải Sentinel-1: " + err.message);
//   }
// }
let buildLayer;
let buildLegend; // giữ legend để xóa khi thêm mới
let buildCommuneTable;

function normalize_name(name) {
  return name.replace(/Thành\s*phố\s*/i, 'tp')
             .replace(/Tỉnh\s*/i, 'tinh')
             .normalize("NFD").replace(/[\u0300-\u036f]/g, "")
             .replace(/đ/g, "d").replace(/Đ/g, "D")
             .replace(/\s+/g, '');
}

async function loadBuild(period) {
  const province = normalize_name(document.getElementById("provinceSelect").value);
  const districts = Array.from(document.getElementById("districtSelect").selectedOptions)
    .map(option => option.value)
    .filter(Boolean).join(',');
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
      <h3>Đang xác định biến động</h3>
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
    const resp = await fetch(`/build_detect?start=${start}&end=${end}&provinceSelect=${encodeURIComponent(province)}&districtSelect=${encodeURIComponent(districts)}`);
    
    if (!resp.ok) throw new Error(`Server trả về lỗi ${resp.status}`);

    const data = await resp.json();
    if (!data.tile_url) throw new Error("Không có tile URL trả về từ server");

    clearInterval(progressTimer);
    progressFill.style.width = "100%";
    progressText.textContent = "Hoàn tất!";
    setTimeout(() => popup.remove(), 700);

    // Xóa layer và legend cũ nếu có
    if (buildLayer) {
      map.removeLayer(buildLayer);
      layerControl.removeLayer(buildLayer);
      delete overlayMaps["Biến động xây dựng"];
    }
    if (buildLegend) {
      map.removeControl(buildLegend);
    }

    // Tạo layer mới
    buildLayer = L.tileLayer(data.tile_url).addTo(map);
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
    const label = `Biến động xây dựng (${month}/${year})`;
    overlayMaps[label] = buildLayer;
    layerControl.addOverlay(buildLayer, label);

    // === 🟡 TẠO LEGEND ===
    const vis_params = {
      min: 0,
      max: 1,
      palette: ['black', 'red']
    };

    buildLegend = L.control({ position: 'bottomright'});
    buildLegend.onAdd = function () {
      const div = L.DomUtil.create('div', 'info legend');
      div.style.marginBottom = '30px';
      div.style.marginRight = '8px';
      div.style.background = 'rgba(255, 255, 255, 0.9)';
      div.style.padding = '10px 14px';
      div.style.borderRadius = '10px';
      div.style.boxShadow = '0 2px 8px rgba(0,0,0,0.25)';
      div.style.lineHeight = '20px';
      div.style.fontSize = '13px';
      div.style.fontFamily = 'Segoe UI, sans-serif';
      div.style.color = '#222';

      // Nội dung legend được căn hàng bằng flex
      div.innerHTML = `
        <div style="font-weight:600; text-align:center; margin-bottom:8px; font-size:14px;">
          Biến động xây dựng
        </div>

        <div style="display:flex; align-items:center; margin-bottom:4px;">
          <div style="width:14px; height:14px; background:${vis_params.palette[0]};
                      border:1px solid #999; margin-right:8px; border-radius:2px;"></div>
          <span>Không biến động</span>
        </div>

        <div style="display:flex; align-items:center; margin-bottom:8px;">
          <div style="width:14px; height:14px; background:${vis_params.palette[1]};
                      border:1px solid #999; margin-right:8px; border-radius:2px;"></div>
          <span>Có biến động</span>
        </div>

        <hr style="border:none; border-top:1px solid #ccc; margin:6px 0;">

        <div style="text-align:left; line-height:1.4;">
          <div style="font-weight:600; margin-bottom:4px;">Thống kê biến động</div>
          <div>
            Diện tích: 
            <span style="color:#d00; font-weight:700;">${data.area_ha ? data.area_ha.toFixed(2) : "0.00"}</span>
            ha
          </div>
        </div>
        <hr style="border:none; border-top:1px solid #ccc; margin:8px 0;">
        <button id="btn-location-info"
          style="
            width:100%;
            padding:8px;
            background:#1976d2;
            color:white;
            border:none;
            border-radius:5px;
            cursor:pointer;
            font-size:13px;
            font-weight:600;">
          📍 Thông tin vị trí
      </button>
      `;
      // Ngăn click legend làm kéo map
      L.DomEvent.disableClickPropagation(div);

      // Gắn sự kiện sau khi button được tạo
      setTimeout(() => {
          const btn = div.querySelector("#btn-location-info");
          if (btn) {
              btn.onclick = function () {
                  locationInfoMode = true;
                  btn.innerHTML = "✔ Chọn vị trí trên bản đồ";
                  btn.style.background = "#f57c00";
              };
          }

      }, 100);
      return div;
    };
    buildLegend.addTo(map);

    // Thêm bảng commune (bottom-left) nếu có
    try {
      if (Array.isArray(data.area_ha_by_commune) && data.area_ha_by_commune.length > 0) {
        if (buildCommuneTable) { map.removeControl(buildCommuneTable); }
        buildCommuneTable = L.control({ position: 'bottomleft' });
        buildCommuneTable.onAdd = function () {
          const div = L.DomUtil.create('div', 'info legend');
          div.style.marginBottom = '30px';
          div.style.marginLeft = '8px';
          div.style.background = 'rgba(255,255,255,0.95)';
          div.style.padding = '10px 12px';
          div.style.borderRadius = '10px';
          div.style.boxShadow = '0 2px 8px rgba(0,0,0,0.25)';
          div.style.lineHeight = '18px';
          div.style.fontSize = '12px';
          div.style.fontFamily = 'Segoe UI, sans-serif';
          div.style.color = '#222';
          div.style.width = '260px';
          div.style.maxWidth = 'calc(100vw - 24px)';
          let html = `<div style="font-weight:600; text-align:center; margin-bottom:8px; font-size:14px;">Diện tích theo xã</div>`;
          html += `<div style="max-height:300px; overflow:auto; background:#fff;"><table style="width:100%; border-collapse:collapse; font-size:13px;">`;
          html += `<thead><tr style="background:#f7f7f7;"><th style="padding:6px 8px; text-align:left;">Tên xã</th><th style="padding:6px 8px; text-align:right;">Diện tích (ha)</th></tr></thead><tbody>`;
          data.area_ha_by_commune.forEach(it => {
            html += `<tr><td style="padding:6px 8px; border-bottom:1px solid #f0f0f0;">${(it.tenxa||'')}</td><td style="padding:6px 8px; border-bottom:1px solid #f0f0f0; text-align:right;">${Number(it.area_ha||0).toFixed(2)}</td></tr>`;
          });
          html += `</tbody></table></div>`;
          div.innerHTML = html;
          return div;
        };
        buildCommuneTable.addTo(map);
      }
    } catch (e) { console.warn('Không thể hiển thị bảng xã', e); }

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

    try {

        const response = await fetch(
            `https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=${lat}&lon=${lon}`
        );

        const geo = await response.json();

        const address =
            geo.display_name || "Không xác định";

        L.popup()
            .setLatLng([lat, lon])
            .setContent(`
                <div style="font-size:13px;">
                    <b>Thông tin vị trí</b><br><br>

                    <b>Vĩ độ:</b>
                    ${lat.toFixed(6)}<br>

                    <b>Kinh độ:</b>
                    ${lon.toFixed(6)}<br><br>

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
