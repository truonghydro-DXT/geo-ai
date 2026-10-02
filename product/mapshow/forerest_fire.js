let forest_fireLayers;
let forest_fireLegend; // giữ legend để xóa khi thêm mới
let forest_fireCommuneTable;

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

function buildCommuneAreaHtml(data) {
  const riskOrder = [
    'Nguy cơ thấp',
    'Nguy cơ trung bình',
    'Nguy cơ cao',
    'Nguy cơ rất cao'
  ];

  // Build map risk -> (commune -> area)
  const riskMaps = {};
  const palettes = {};
  const communeSet = new Set();
  for (const riskName of riskOrder) {
    const riskData = data[riskName];
    const rows = Array.isArray(riskData?.area_ha_by_commune) ? riskData.area_ha_by_commune : [];
    palettes[riskName] = Array.isArray(riskData?.palette) ? riskData.palette[0] : (riskData?.palette || '#999');
    const m = {};
    for (const it of rows) {
      if (!it || !it.tenxa) continue;
      m[it.tenxa] = Number(it.area_ha || 0);
      communeSet.add(it.tenxa);
    }
    riskMaps[riskName] = m;
  }

  const communes = Array.from(communeSet);
  if (communes.length === 0) {
    return `
      <div style="font-size:12px; color:#666; font-style:italic;">Không có dữ liệu diện tích theo xã.</div>
    `;
  }

  communes.sort();

  // Header
  let headerHtml = `<th style="padding:6px 8px; border-bottom:1px solid #ddd; text-align:left;">Tên xã</th>`;
  for (const riskName of riskOrder) {
    headerHtml += `<th style="padding:6px 8px; border-bottom:1px solid #ddd; text-align:right;">${escapeHtml(riskName)}</th>`;
  }

  // Rows
  let bodyHtml = '';
  communes.forEach((commune) => {
    bodyHtml += `<tr>`;
    bodyHtml += `<td style="padding:6px 8px; border-bottom:1px solid #f0f0f0;">${escapeHtml(commune)}</td>`;
    for (const riskName of riskOrder) {
      const val = riskMaps[riskName][commune] || 0;
      bodyHtml += `<td style="padding:6px 8px; border-bottom:1px solid #f0f0f0; text-align:right; white-space:nowrap;">${val.toFixed(2)}</td>`;
    }
    bodyHtml += `</tr>`;
  });

  // Legend/palette row
  let paletteRow = '';
  for (const riskName of riskOrder) {
    const p = palettes[riskName] || '#999';
    paletteRow += `<td style="padding:6px 8px; text-align:center;"> <span style="display:inline-block;width:12px;height:12px;background:${p};border:1px solid #999;border-radius:2px;"></span></td>`;
  }

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

async function loadForestFire() {
  const province = normalize_name(document.getElementById("provinceSelect").value);
  const districtSelect = document.getElementById("districtSelect");
  const selectedDistricts = Array.from(districtSelect?.selectedOptions || [])
    .map(option => option.value)
    .filter(Boolean);
  const districts = selectedDistricts.join(',');
  const end = document.getElementById("endDate").value;
  let endDateObj = new Date(end);

  const monthnow = endDateObj.getMonth() + 1;
  const yearnow = endDateObj.getFullYear();

  if (!province) {
    alert("Vui lòng chọn tỉnh/thành phố!");
    return;
  }

  if (!end) {
    alert("Vui lòng chọn thời điểm giám sát!");
    return;
  }

  // === Hiển thị popup tiến trình ===
  const popup = document.createElement("div");
  popup.id = "loading-popup";
  popup.innerHTML = `
    <div class="popup-box">
      <h3>AI cảnh báo cháy rừng</h3>
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
    const queryParams = new URLSearchParams({
      end,
      provinceSelect: province,
      districtSelect: districts
    });
    const resp = await fetch(`/forerest_fire?${queryParams.toString()}`);
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      const detail = data.error || data.message || data.details || "";
      throw new Error(detail ? `Server trả về lỗi ${resp.status}: ${detail}` : `Server trả về lỗi ${resp.status}`);
    }
    // support new response shape: { tiles: {...}, all_vectors: { vector_download_url, geojson } }
    const tiles = data.tiles || data;
    const all_vectors = data.all_vectors || null;

    clearInterval(progressTimer);
    progressFill.style.width = "100%";
    progressText.textContent = "Hoàn tất!";
    setTimeout(() => popup.remove(), 700);

    // Xóa layer và legend cũ nếu có
    if (forest_fireLayers) {
      for (let name in forest_fireLayers) {
        map.removeLayer(forest_fireLayers[name]);
        layerControl.removeLayer(forest_fireLayers[name]);
      }
    }
    if (forest_fireLegend) {
      map.removeControl(forest_fireLegend);
    }
    if (forest_fireCommuneTable) {
      map.removeControl(forest_fireCommuneTable);
    }

    forest_fireLayers = {};

    // === Thêm từng lớp LULC ===
    for (let name in tiles) {
      const tile_url = tiles[name].tile_url;
      if (!tile_url) continue;

      const layer = L.tileLayer(tile_url).addTo(map);
      const label = `${name}`;
      overlayMaps[label] = layer;
      layerControl.addOverlay(layer, label);
      forest_fireLayers[name] = layer;
    }

    // Thêm bảng commune matrix khi backend có dữ liệu theo xã
    const hasCommuneTable = Object.values(tiles).some(item => Array.isArray(item?.area_ha_by_commune) && item.area_ha_by_commune.length > 0);
    if (hasCommuneTable) {
      forest_fireCommuneTable = L.control({ position: 'bottomleft' });
      forest_fireCommuneTable.onAdd = function () {
        const div = L.DomUtil.create('div', 'info legend');
        div.style.marginBottom = '30px';
        div.style.marginLeft = '8px';
        div.style.background = 'rgba(255, 255, 255, 0.95)';
        div.style.padding = '10px 12px';
        div.style.borderRadius = '10px';
        div.style.boxShadow = '0 2px 8px rgba(0,0,0,0.25)';
        div.style.lineHeight = '18px';
        div.style.fontSize = '12px';
        div.style.fontFamily = 'Segoe UI, sans-serif';
        div.style.color = '#222';
        div.style.width = '320px';
        div.style.maxWidth = 'calc(100vw - 24px)';
        div.innerHTML = buildCommuneAreaHtml(data);
        return div;
      };
      forest_fireCommuneTable.addTo(map);
    }

    // === 🟡 Tạo Legend chung cho tất cả lớp ===
    forest_fireLegend = L.control({ position: 'bottomright' });
    forest_fireLegend.onAdd = function () {
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

      let html = `<div style="font-weight:600; text-align:center; margin-bottom:8px; font-size:14px;">Cảnh báo cháy rừng tháng (${monthnow}/${yearnow})</div>`;
      for (let name in tiles) {
        const palette = Array.isArray(tiles[name].palette) ? tiles[name].palette[0] : tiles[name].palette;
        const areaVal = Number(tiles[name].area_ha || 0).toFixed(2);
        html += `
          <div style="display:flex; align-items:center; margin-bottom:4px;">
            <div style="width:14px; height:14px; background:${palette};
                        border:1px solid #999; margin-right:8px; border-radius:2px;"></div>
            <span>${name} (${areaVal} ha)</span>
          </div>
        `;
      }
      // Ngăn click legend làm kéo map
      L.DomEvent.disableClickPropagation(div);

      
      div.innerHTML = html;
      // Chèn separator và nút tải bên dưới toàn bộ nội dung legend
      div.insertAdjacentHTML('beforeend', `
        <hr style="border:none; border-top:1px solid #ccc; margin:8px 0;">
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
      `);

      // Kiểm tra xem có download_url nào trong data không; nếu không, ẩn nút
      const downloadBtn = div.querySelector('#btn-download-result');
      let firstDownloadUrl = null;
      for (const k in tiles) {
        if (tiles[k] && tiles[k].download_url) {
          firstDownloadUrl = tiles[k].download_url;
          break;
        }
      }
      const combinedVectorUrl = all_vectors?.vector_download_url || null;
      const combinedGeoJson = all_vectors?.geojson || null;
      if (!firstDownloadUrl && !combinedVectorUrl && !combinedGeoJson) {
        if (downloadBtn) {
          downloadBtn.style.display = 'none';
          downloadBtn.title = 'Không có đường dẫn tải kết quả.';
        }
      } else {
        downloadBtn.addEventListener('click', async () => {
          // Prefer inline GeoJSON content, then combined vector URL, then raster fallback
          if (combinedGeoJson) {
            const blob = new Blob([JSON.stringify(combinedGeoJson)], { type: 'application/geo+json' });
            const fname = `forestfire_result_${monthnow}_${yearnow}.geojson`;
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url; a.download = fname; document.body.appendChild(a); a.click(); a.remove();
            URL.revokeObjectURL(url);
            return;
          }

          if (combinedVectorUrl) {
            const fname = `forestfire_result_${monthnow}_${yearnow}.geojson`;
            const a = document.createElement('a');
            a.href = combinedVectorUrl; a.download = fname; a.rel = 'noopener'; document.body.appendChild(a); a.click(); a.remove();
            return;
          }

          // fallback to first raster download
          const fileName = `forestfire_result_${monthnow}_${yearnow}.tif`;
          const link = document.createElement('a');
          link.href = firstDownloadUrl;
          link.download = fileName;
          link.rel = 'noopener';
          document.body.appendChild(link);
          link.click();
          link.remove();
        });
      }

      return div;
    };
    forest_fireLegend.addTo(map);

  } catch (err) {
    clearInterval(progressTimer);
    popup.remove();
    console.error(err);
    alert("Lỗi tải dữ liệu cháy rừng: " + err.message);
  }
}
