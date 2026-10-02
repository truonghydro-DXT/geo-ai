let landslideLayer;
let landslideLegend;
let landslideCommuneTable;

function normalize_name(name) {
	return name.replace(/Thành\s*phố\s*/i, 'tp')
						 .replace(/Tỉnh\s*/i, 'tinh')
						 .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
						 .replace(/đ/g, 'd').replace(/Đ/g, 'D')
						 .replace(/\s+/g, '');
}

function escapeHtml(value) {
	return String(value ?? '')
		.replace(/&/g, '&amp;')
		.replace(/</g, '&lt;')
		.replace(/>/g, '&gt;')
		.replace(/"/g, '&quot;')
		.replace(/'/g, '&#39;');
}

function renderCommuneTable(rows) {
	if (!Array.isArray(rows) || rows.length === 0) {
		return '<div style="font-size:12px; color:#666; font-style:italic;">Không có dữ liệu diện tích theo xã.</div>';
	}

	const htmlRows = rows.map((item, index) => `
		<tr>
			<td style="padding:4px 6px; border-bottom:1px solid #eee; text-align:center;">${index + 1}</td>
			<td style="padding:4px 6px; border-bottom:1px solid #eee;">${escapeHtml(item.tenxa)}</td>
			<td style="padding:4px 6px; border-bottom:1px solid #eee; text-align:right; white-space:nowrap;">${Number(item.area_ha || 0).toFixed(2)}</td>
		</tr>
	`).join('');

	return `
		<div style="max-height:220px; overflow:auto; border:1px solid #e6e6e6; border-radius:6px; background:#fff;">
			<table style="width:100%; border-collapse:collapse; font-size:12px;">
				<thead>
					<tr style="background:#f7f7f7; position:sticky; top:0; z-index:1;">
						<th style="padding:4px 6px; border-bottom:1px solid #ddd; width:28px;">#</th>
						<th style="padding:4px 6px; border-bottom:1px solid #ddd; text-align:left;">Tên xã</th>
						<th style="padding:4px 6px; border-bottom:1px solid #ddd; text-align:right; width:72px;">ha</th>
					</tr>
				</thead>
				<tbody>
					${htmlRows}
				</tbody>
			</table>
		</div>
	`;
}

async function loadLandslide(period) {
	const province = normalize_name(document.getElementById('provinceSelect').value);
	const districts = Array.from(document.getElementById('districtSelect').selectedOptions)
		.map(option => option.value)
		.filter(Boolean)
		.join(',');
	const end = document.getElementById('endDate').value;

	if (!province) {
		alert('Vui lòng chọn tỉnh/thành phố!');
		return;
	}

	if (!end) {
		alert('Vui lòng chọn thời điểm giám sát!');
		return;
	}

	const endDateObj = new Date(end);
	const startDateObj = new Date(endDateObj);
	let daysRange = 15;
	if (period === 'month') daysRange = 30;
	else if (period === 'quarter') daysRange = 90;

	startDateObj.setDate(endDateObj.getDate() - daysRange);
	const start = startDateObj.toISOString().split('T')[0];
	const month = endDateObj.getMonth() + 1;
	const year = endDateObj.getFullYear();

	const popup = document.createElement('div');
	popup.id = 'loading-popup';
	popup.innerHTML = `
		<div class="popup-box">
			<h3>Đang xác định sạt lở đất</h3>
			<div class="progress-bar"><div class="progress-fill"></div></div>
			<p class="progress-text">0%</p>
		</div>
	`;
	document.body.appendChild(popup);

	const progressFill = popup.querySelector('.progress-fill');
	const progressText = popup.querySelector('.progress-text');
	let progress = 0;
	const progressTimer = setInterval(() => {
		progress += 5;
		if (progress >= 90) progress = 90;
		progressFill.style.width = `${progress}%`;
		progressText.textContent = `${progress}%`;
	}, 500);

	try {
		const resp = await fetch(`/landslide_area?start=${start}&end=${end}&provinceSelect=${encodeURIComponent(province)}&districtSelect=${encodeURIComponent(districts)}`);
		if (!resp.ok) throw new Error(`Server trả về lỗi ${resp.status}`);

		const data = await resp.json();
		const landslideData = data.ALDI || data.aldi || data;
		if (!landslideData?.tile_url) throw new Error('Không có tile URL trả về từ server');

		clearInterval(progressTimer);
		progressFill.style.width = '100%';
		progressText.textContent = 'Hoàn tất!';
		setTimeout(() => popup.remove(), 700);

		if (landslideLayer) {
			map.removeLayer(landslideLayer);
			layerControl.removeLayer(landslideLayer);
			delete overlayMaps['Sạt lở đất'];
		}
		if (landslideLegend) {
			map.removeControl(landslideLegend);
		}
		if (landslideCommuneTable) {
			map.removeControl(landslideCommuneTable);
		}

		landslideLayer = L.tileLayer(landslideData.tile_url).addTo(map);
		overlayMaps['Sạt lở đất'] = landslideLayer;
		layerControl.addOverlay(landslideLayer, `Sạt lở đất (${month}/${year})`);

		landslideLegend = L.control({ position: 'bottomright' });
		landslideLegend.onAdd = function () {
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
			div.innerHTML = `
				<div style="font-weight:600; text-align:center; margin-bottom:8px; font-size:14px;">Sạt lở đất (${month}/${year})</div>
				<div style="display:flex; align-items:center; margin-bottom:4px;">
					<div style="width:14px; height:14px; background:${landslideData.palette?.[0] || landslideData.palette || '#FF0000'}; border:1px solid #999; margin-right:8px; border-radius:2px;"></div>
					<span>Khu vực có nguy cơ</span>
				</div>
				<div style="margin-top:8px; line-height:1.4;">
					<div style="font-weight:600; margin-bottom:4px;">Thống kê</div>
					<div>Diện tích: <span style="color:#d00; font-weight:700;">${Number(landslideData.area_ha || 0).toFixed(2)}</span> ha</div>
				</div>
			`;
			return div;
		};
		landslideLegend.addTo(map);

		if (Array.isArray(landslideData.area_ha_by_commune) && landslideData.area_ha_by_commune.length > 0) {
			landslideCommuneTable = L.control({ position: 'bottomleft' });
			landslideCommuneTable.onAdd = function () {
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
				div.innerHTML = `<div style="font-weight:600; text-align:center; margin-bottom:8px; font-size:13px;">Diện tích theo xã</div>${renderCommuneTable(landslideData.area_ha_by_commune)}`;
				return div;
			};
			landslideCommuneTable.addTo(map);
		}
	} catch (err) {
		clearInterval(progressTimer);
		popup.remove();
		console.error(err);
		alert('Lỗi tải dữ liệu sạt lở đất: ' + err.message);
	}
}
