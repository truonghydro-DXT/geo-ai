let droughtLayers;
let droughtLegend;
let droughtCommune;

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function buildCommuneAreaHtml(data) {
  const classColumns = [
    { key: 'class_1_ha', label: 'Nguy cơ rất cao' },
    { key: 'class_2_ha', label: 'Nguy cơ cao' },
    { key: 'class_3_ha', label: 'Nguy cơ trung bình' },
    { key: 'class_4_ha', label: 'Nguy cơ thấp' }
  ];

  const communeMap = new Map();
  const paletteByClass = [null, null, null, null];

  for (const [riskName, item] of Object.entries(data || {})) {
    if (!item || !Array.isArray(item.area_ha_by_commune)) continue;
    const classIndex = {
      'Nguy cơ rất cao': 0,
      'Nguy cơ cao': 1,
      'Nguy cơ trung bình': 2,
      'Nguy cơ thấp': 3,
    }[riskName];
    if (classIndex !== undefined) {
      const palette = Array.isArray(item.palette) ? item.palette[0] : item.palette;
      paletteByClass[classIndex] = palette || paletteByClass[classIndex] || '#999';
      for (const row of item.area_ha_by_commune) {
        if (!row || !row.tenxa) continue;
        const current = communeMap.get(row.tenxa) || {
          tenxa: row.tenxa,
          class_1_ha: 0,
          class_2_ha: 0,
          class_3_ha: 0,
          class_4_ha: 0,
        };
        current[classColumns[classIndex].key] = Number(row.area_ha || 0);
        communeMap.set(row.tenxa, current);
      }
    }
  }

  const rows = Array.from(communeMap.values());
  if (rows.length === 0) {
    return `
      <div style="font-size:12px; color:#666; font-style:italic;">Không có dữ liệu diện tích theo xã.</div>
    `;
  }

  rows.sort((a, b) => String(a.tenxa).localeCompare(String(b.tenxa), 'vi'));

  let headerHtml = `<th style="padding:6px 8px; border-bottom:1px solid #ddd; text-align:left;">Tên xã</th>`;
  for (const col of classColumns) {
    headerHtml += `<th style="padding:6px 8px; border-bottom:1px solid #ddd; text-align:right;">${escapeHtml(col.label)}</th>`;
  }

  let bodyHtml = '';
  rows.forEach((row) => {
    bodyHtml += `<tr>`;
    bodyHtml += `<td style="padding:6px 8px; border-bottom:1px solid #f0f0f0;">${escapeHtml(row.tenxa)}</td>`;
    for (const col of classColumns) {
      const val = Number(row[col.key] || 0);
      bodyHtml += `<td style="padding:6px 8px; border-bottom:1px solid #f0f0f0; text-align:right; white-space:nowrap;">${val.toFixed(2)}</td>`;
    }
    bodyHtml += `</tr>`;
  });

  const paletteRow = classColumns.map((col, index) => {
    const p = paletteByClass[index] || '#999';
    return `<td style="padding:6px 8px; text-align:center;"><span style="display:inline-block;width:12px;height:12px;background:${p};border:1px solid #999;border-radius:2px;"></span></td>`;
  }).join('');

  return `
    <div style="font-weight:600; text-align:center; margin-bottom:8px; font-size:14px;">Diện tích theo mức nguy cơ và theo xã</div>
    <div style="max-height:320px; overflow:auto; padding-right:4px; background:#fff;">
      <table style="width:100%; border-collapse:collapse; font-size:13px;">
        <thead>
          <tr style="background:#f7f7f7;">
            ${headerHtml}
          </tr>
        </thead>
        <tbody>
          ${bodyHtml}
          <tr style="background:#fafafa; font-size:12px; color:#444;">
            <td style="padding:6px 8px; border-top:1px solid #e6e6e6; font-weight:600;">Màu</td>
            ${paletteRow}
          </tr>
        </tbody>
      </table>
    </div>
  `;
}

async function loadDroughtLayer() {
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
      <h3>Đang xác định nguy cơ hạn hán</h3>
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
    const resp = await fetch(`/drought_area?end=${end}&provinceSelect=${encodeURIComponent(province)}&districtSelect=${encodeURIComponent(districts)}`);
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      const detail = data.error || data.message || data.details || "";
      throw new Error(detail ? `Server trả về lỗi ${resp.status}: ${detail}` : `Server trả về lỗi ${resp.status}`);
    }

    clearInterval(progressTimer);
    progressFill.style.width = "100%";
    progressText.textContent = "Hoàn tất!";
    setTimeout(() => popup.remove(), 700);

    // Xóa layer, legend và control commune cũ nếu có
    if (droughtLayers) {
      for (const name in droughtLayers) {
        const layer = droughtLayers[name];
        if (layer && map.hasLayer(layer)) map.removeLayer(layer);
        try { layerControl.removeLayer(layer); } catch (e) { /* ignore */ }
        delete overlayMaps[name];
      }
    }

    if (droughtLegend) {
      map.removeControl(droughtLegend);
      droughtLegend = null;
    }

    if (droughtCommune) {
      try { map.removeControl(droughtCommune); } catch (e) { /* ignore */ }
      droughtCommune = null;
    }

    const mapEntries = Object.entries(data || {}).filter(([, value]) => value && value.tile_url);

    if (data.active === 0 || mapEntries.length === 0) {
      alert("Không xảy ra nguy cơ hạn hán giám sát!");
      return;
    }

    droughtLayers = {};
    for (const [name, item] of mapEntries) {
      const layer = L.tileLayer(item.tile_url, {
        opacity: 0.85,
        // EE (Landsat 30m) thường chỉ ổn định tới ~z14; zoom sâu hơn thì phóng to tile sẵn có
        maxZoom: 22,
        maxNativeZoom: 14,
        updateWhenZooming: false,
        updateWhenIdle: true,
        keepBuffer: 4,
        crossOrigin: true,
      }).addTo(map);
      droughtLayers[name] = layer;
      overlayMaps[name] = layer;
      layerControl.addOverlay(layer, name);
    }

    // Ép tải lại tile sau khi zoom/pan để tránh lớp bị trống
    if (!map._droughtTileRefreshBound) {
      map._droughtTileRefreshBound = true;
      const refreshDroughtTiles = () => {
        if (!droughtLayers) return;
        Object.values(droughtLayers).forEach((layer) => {
          if (layer && map.hasLayer(layer) && typeof layer.redraw === 'function') {
            layer.redraw();
          }
        });
      };
      map.on('zoomend', refreshDroughtTiles);
      map.on('moveend', refreshDroughtTiles);
    }

    // ======================
    // 🧭 TẠO LEGEND CHUNG
    // ======================
    droughtLegend = L.control({ position: "bottomright" });

    droughtLegend.onAdd = function () {
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
            Cảnh báo hạn hán (${monthnow}/${yearnow})
        </div>
        `;

        // Lặp qua từng lớp
        for (const [name, item] of mapEntries) {
            html += `
                <div style="display:flex; align-items:center; margin-bottom:4px;">
              <div style="width:14px; height:14px; background:${Array.isArray(item.palette) ? item.palette[0] : item.palette};
                                border:1px solid #999; margin-right:8px; border-radius:2px;"></div>
              <span>${name} (${Number(item.area_ha || 0).toFixed(2)} ha)</span>
                </div>`;
        }
        div.innerHTML = html;
        return div;
    };

    droughtLegend.addTo(map);

    // Hiển thị bảng xã x nguy cơ hạn hán nếu backend có dữ liệu
    try {
      const communeData = data || {};
      const communeList = Object.values(communeData).flatMap(item => Array.isArray(item?.area_ha_by_commune) ? item.area_ha_by_commune : []);
      if (Array.isArray(communeList) && communeList.length > 0) {
        droughtCommune = L.control({ position: 'bottomleft' });
        droughtCommune.onAdd = function () {
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
          div.style.width = '320px';
          div.style.maxWidth = 'calc(100vw - 24px)';
          if (L.DomEvent && L.DomEvent.disableClickPropagation) L.DomEvent.disableClickPropagation(div);
          if (L.DomEvent && L.DomEvent.disableScrollPropagation) L.DomEvent.disableScrollPropagation(div);
          div.innerHTML = buildCommuneAreaHtml(communeData);
          return div;
        };
        try { droughtCommune.addTo(map); } catch (e) { console.warn('Failed to add droughtCommune to map', e); }
      }
    } catch (e) { console.warn('Không thể hiển thị bảng xã hạn:', e); }

  } catch (err) {
    clearInterval(progressTimer);
    popup.remove();
    console.error(err);
    alert("Lỗi tải dữ liệu: " + err.message);
  }
}
