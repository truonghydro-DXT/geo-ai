let floodLayers;
let floodLegend;
let floodCommuneTable;

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function buildFloodCommuneHtml(data) {
  const rows = Array.isArray(data?.["Flooded Area"]?.area_ha_by_commune)
    ? data["Flooded Area"].area_ha_by_commune
    : [];

  if (rows.length === 0) {
    return `<div style="font-size:12px; color:#666; font-style:italic;">Không có dữ liệu diện tích theo xã.</div>`;
  }

  let bodyHtml = "";
  for (const row of rows) {
    bodyHtml += `
      <tr>
        <td style="padding:6px 8px; border-bottom:1px solid #f0f0f0;">${escapeHtml(row.tenxa)}</td>
        <td style="padding:6px 8px; border-bottom:1px solid #f0f0f0; text-align:right; white-space:nowrap;">${Number(row.area_ha || 0).toFixed(2)}</td>
      </tr>
    `;
  }

  return `
    <div style="font-weight:600; text-align:center; margin-bottom:8px; font-size:14px;">Diện tích ngập lụt theo xã</div>
    <div style="max-height:320px; overflow:auto; padding-right:4px; background:#fff;">
      <table style="width:100%; border-collapse:collapse; font-size:13px;">
        <thead>
          <tr style="background:#f7f7f7;">
            <th style="padding:6px 8px; border-bottom:1px solid #ddd; text-align:left;">Tên xã</th>
            <th style="padding:6px 8px; border-bottom:1px solid #ddd; text-align:right;">Diện tích (ha)</th>
          </tr>
        </thead>
        <tbody>
          ${bodyHtml}
        </tbody>
      </table>
    </div>
  `;
}

async function loadFloodLayer() {
  const province = normalize_name(document.getElementById("provinceSelect").value);
  const districts = Array.from(document.getElementById("districtSelect").selectedOptions)
    .map(option => option.value)
    .filter(Boolean).join(',');
  const end = document.getElementById("endDate").value;
   let endDateObj = new Date(end);

  const monthnow = endDateObj.getMonth() + 1;
  const yearnow = endDateObj.getFullYear();

  // === Hiển thị popup tiến trình ===
  const popup = document.createElement("div");
  popup.id = "loading-popup";
  popup.innerHTML = `
    <div class="popup-box">
      <h3>AI giám sát ngập lụt</h3>
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
    const resp = await fetch(`/flood_area?end=${end}&provinceSelect=${encodeURIComponent(province)}&districtSelect=${encodeURIComponent(districts)}`);
    if (!resp.ok) throw new Error(`Server trả về lỗi ${resp.status}`);
    const data = await resp.json();

    clearInterval(progressTimer);
    progressFill.style.width = "100%";
    progressText.textContent = "Hoàn tất!";
    setTimeout(() => popup.remove(), 700);

    // Xóa layer và legend cũ nếu có
    if (floodLayers) {
        for (let name in floodLayers) {
        map.removeLayer(floodLayers[name]);
        layerControl.removeLayer(floodLayers[name]);
        }
    }
    if (floodLegend) map.removeControl(floodLegend);
    if (floodCommuneTable) map.removeControl(floodCommuneTable);

    if (data.active === 0) {
      alert("Không xảy ra ngập lụt tại thời điểm giám sát!");
      return;
    }
    floodLayers = {}
    // ======================
    // 🟦 1️⃣ LỚP: NƯỚC VĨNH CỬU
    // ======================
    if (data["Permanent Water"]) {
        const waterLayer = L.tileLayer(data["Permanent Water"].tile_url, {
        opacity: 0.85,
        maxZoom: 22,
        maxNativeZoom: 14,
        updateWhenZooming: false,
        updateWhenIdle: true,
        keepBuffer: 4,
        }).addTo(map);

        layerControl.addOverlay(waterLayer, "Vùng nước vĩnh cửu");
        floodLayers["Permanent Water"] = waterLayer;
    }

    // ======================
    // 🟢 2️⃣ LỚP: VÙNG NGẬP LỤT
    // ======================
    if (data["Flooded Area"]) {
        const floodLayer = L.tileLayer(data["Flooded Area"].tile_url, {
        opacity: 0.85,
        maxZoom: 22,
        maxNativeZoom: 14,
        updateWhenZooming: false,
        updateWhenIdle: true,
        keepBuffer: 4,
        }).addTo(map);

        layerControl.addOverlay(floodLayer, "Vùng ngập lụt");
        floodLayers["Flooded Area"] = floodLayer;
    }

      // ======================
      // 📋 BẢNG DIỆN TÍCH THEO XÃ
      // ======================
      if (Array.isArray(data?.["Flooded Area"]?.area_ha_by_commune) && data["Flooded Area"].area_ha_by_commune.length > 0) {
        floodCommuneTable = L.control({ position: "bottomleft" });
        floodCommuneTable.onAdd = function () {
          const div = L.DomUtil.create("div", "info legend");
          div.style.marginBottom = "30px";
          div.style.marginLeft = "8px";
          div.style.background = "rgba(255, 255, 255, 0.95)";
          div.style.padding = "10px 12px";
          div.style.borderRadius = "10px";
          div.style.boxShadow = "0 2px 8px rgba(0,0,0,0.25)";
          div.style.lineHeight = "18px";
          div.style.fontSize = "12px";
          div.style.fontFamily = "Segoe UI, sans-serif";
          div.style.color = "#222";
          div.style.width = "320px";
          div.style.maxWidth = "calc(100vw - 24px)";
          div.innerHTML = buildFloodCommuneHtml(data);
          return div;
        };
        floodCommuneTable.addTo(map);
      }

    // ======================
    // 🧭 TẠO LEGEND CHUNG
    // ======================
    floodLegend = L.control({ position: "bottomright" });
    floodLegend.onAdd = function () {
        const div = L.DomUtil.create("div", "info legend");
        div.style.marginBottom = "30px";
        div.style.marginRight = "8px";
        div.style.background = "rgba(255, 255, 255, 0.9)";
        div.style.padding = "10px 14px";
        div.style.borderRadius = "10px";
        div.style.boxShadow = "0 2px 8px rgba(0,0,0,0.25)";
        div.style.lineHeight = "20px";
        div.style.fontSize = "13px";
        div.style.fontFamily = "Segoe UI, sans-serif";
        div.style.color = "#222";

        let html = `
        <div style="font-weight:600; text-align:center; margin-bottom:8px; font-size:14px;">
            Phát hiện vùng ngập lụt (${monthnow}/${yearnow})
        </div>
        `;

        if (data["Permanent Water"]) {
        const d = data["Permanent Water"];
        html += `
            <div style="display:flex; align-items:center; margin-bottom:4px;">
            <div style="width:14px; height:14px; background:${d.palette};
                        border:1px solid #999; margin-right:8px; border-radius:2px;"></div>
            <span>Vùng nước vĩnh cửu</span>
            </div>`;
        }

        if (data["Flooded Area"]) {
        const d = data["Flooded Area"];
        html += `
            <div style="display:flex; align-items:center; margin-bottom:4px;">
            <div style="width:14px; height:14px; background:${d.palette};
                        border:1px solid #999; margin-right:8px; border-radius:2px;"></div>
            <span>Vùng ngập lụt (${d.area_ha.toFixed(2)} ha)</span>
            </div>`;
        }

        div.innerHTML = html;
        return div;
    };
    floodLegend.addTo(map);

    } catch (err) {
    clearInterval(progressTimer);
    popup.remove();
    console.error(err);
    alert("Lỗi tải dữ liệu: " + err.message);
    }

}
