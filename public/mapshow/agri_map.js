let agriLayers;
let agriLegend; // giữ legend để xóa khi thêm mới
let agriCommuneTable;

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
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function buildCommuneAreaHtmlGeneric(data) {
  const layerNames = Object.keys(data);
  const communeSet = new Set();
  const layerMap = {};
  for (const name of layerNames) {
    const rows = Array.isArray(data[name]?.area_ha_by_commune) ? data[name].area_ha_by_commune : [];
    layerMap[name] = {};
    for (const r of rows) {
      if (!r || !r.tenxa) continue;
      layerMap[name][r.tenxa] = Number(r.area_ha || 0);
      communeSet.add(r.tenxa);
    }
  }

  const communes = Array.from(communeSet);
  if (communes.length === 0) return `<div style="font-size:12px; color:#666; font-style:italic;">Không có dữ liệu diện tích theo xã.</div>`;
  communes.sort();

  // Header
  let header = `<th style="padding:6px 8px; border-bottom:1px solid #ddd; text-align:left;">Tên xã</th>`;
  for (const name of layerNames) header += `<th style="padding:6px 8px; border-bottom:1px solid #ddd; text-align:right;">${escapeHtml(name)}</th>`;

  let body = '';
  for (const c of communes) {
    body += '<tr>';
    body += `<td style="padding:6px 8px; border-bottom:1px solid #f0f0f0;">${escapeHtml(c)}</td>`;
    for (const name of layerNames) {
      const v = layerMap[name][c] || 0;
      body += `<td style="padding:6px 8px; border-bottom:1px solid #f0f0f0; text-align:right; white-space:nowrap;">${v.toFixed(2)}</td>`;
    }
    body += '</tr>';
  }

  return `
    <div style="font-weight:600; text-align:center; margin-bottom:8px; font-size:14px;">Diện tích theo xã</div>
    <div style="max-height:320px; overflow:auto; padding-right:4px; background:#fff;">
      <table style="width:100%; border-collapse:collapse; font-size:13px;">
        <thead><tr style="background:#f7f7f7;">${header}</tr></thead>
        <tbody>${body}</tbody>
      </table>
    </div>
  `;
}

async function model_agri_classify() {
  const province = normalize_name(document.getElementById("provinceSelect").value);
  const districts = Array.from(document.getElementById("districtSelect").selectedOptions)
    .map(option => option.value)
    .filter(Boolean).join(',');
  const end = document.getElementById("endDate").value;
  let endDateObj = new Date(end);

  const monthnow = endDateObj.getMonth() + 1;
  const yearnow = endDateObj.getFullYear();

  
  if (!end) {
    alert("Vui lòng chọn thời điểm giám sát!");
    return;
  }

  // === Hiển thị popup tiến trình ===
  const popup = document.createElement("div");
  popup.id = "loading-popup";
  popup.innerHTML = `
    <div class="popup-box">
      <h3>AI phân loại đối tượng</h3>
      <div class="progress-bar"><div class="progress-fill"></div></div>
      <p class="progress-text">0%</p>
    </div>
  `;
  document.body.appendChild(popup);
  const progressFill = popup.querySelector(".progress-fill");
  const progressText = popup.querySelector(".progress-text");

  let progress = 0;
  const progressTimer = setInterval(() => {
    progress += 1;
    if (progress >= 99) progress = 99;
    progressFill.style.width = `${progress}%`;
    progressText.textContent = `${progress}%`;
  }, 500);

  try {
    const resp = await fetch(`/agrir_layer?end=${end}&provinceSelect=${encodeURIComponent(province)}&districtSelect=${encodeURIComponent(districts)}`);
    if (!resp.ok) throw new Error(`Server trả về lỗi ${resp.status}`);
    const data = await resp.json();

    clearInterval(progressTimer);
    progressFill.style.width = "100%";
    progressText.textContent = "Hoàn tất!";
    setTimeout(() => popup.remove(), 700);

    // Xóa layer và legend cũ nếu có
    if (agriLayers) {
      for (let name in agriLayers) {
        map.removeLayer(agriLayers[name]);
        layerControl.removeLayer(agriLayers[name]);
      }
    }
    if (agriLegend) {
      map.removeControl(agriLegend);
    }

    agriLayers = {};

    // === Thêm từng lớp LULC ===
    for (let name in data) {
      const tile_url = data[name].tile_url;
      if (!tile_url) continue;

      const layer = L.tileLayer(tile_url).addTo(map);
      const label = `${name}`;
      overlayMaps[label] = layer;
      layerControl.addOverlay(layer, label);
      agriLayers[name] = layer;
    }

    // === 🟡 Tạo Legend chung cho tất cả lớp ===
    agriLegend = L.control({ position: 'bottomright' });
    agriLegend.onAdd = function () {
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

      let html = `<div style="font-weight:600; text-align:center; margin-bottom:8px; font-size:14px;">Bản đồ cây trồng mùa vụ (${monthnow}/${yearnow})</div>`;
      for (let name in data) {
        html += `
          <div style="display:flex; align-items:center; margin-bottom:4px;">
            <div style="width:14px; height:14px; background:${data[name].palette};
                        border:1px solid #999; margin-right:8px; border-radius:2px;"></div>
            <span>${name} (${data[name].area_ha.toFixed(2)} ha)</span>
          </div>
        `;
      }
      div.innerHTML = html;
      return div;
    };
    agriLegend.addTo(map);

    // Thêm bảng commune nếu backend trả về area_ha_by_commune
    try {
      const hasCommuneTable = Object.values(data).some(item => Array.isArray(item?.area_ha_by_commune) && item.area_ha_by_commune.length > 0);
      if (hasCommuneTable) {
        if (agriCommuneTable) { map.removeControl(agriCommuneTable); }
        agriCommuneTable = L.control({ position: 'bottomleft' });
        agriCommuneTable.onAdd = function () {
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
          div.style.width = '360px';
          div.style.maxWidth = 'calc(100vw - 24px)';
          div.innerHTML = buildCommuneAreaHtmlGeneric(data);
          return div;
        };
        agriCommuneTable.addTo(map);
      }
    } catch (e) {
      console.warn('Không thể hiển thị bảng xã:', e);
    }

  } catch (err) {
    clearInterval(progressTimer);
    popup.remove();
    console.error(err);
    alert("Lỗi tải dữ liệu LULC: " + err.message);
  }
}
