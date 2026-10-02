let forestAgbLayer;
let forestAgbLegend;
let forestAgbStatsControl;
let forestAgbDrawControl;
let forestAgbPolygonControl;
let forestAgbMapBound = false;
const forestAgbDraw = {
	active: false,
	points: [],
	preview: null,
	polygon: null,
	vertices: [],
	query: null,
};

function forestAgbNormalizeName(name) {
	return String(name || '')
		.replace(/Thành\s*phố\s*/i, 'tp')
		.replace(/Tỉnh\s*/i, 'tinh')
		.normalize('NFD').replace(/[\u0300-\u036f]/g, '')
		.replace(/đ/g, 'd').replace(/Đ/g, 'D')
		.replace(/\s+/g, '');
}

function forestAgbEscapeHtml(value) {
	return String(value ?? '')
		.replace(/&/g, '&amp;')
		.replace(/</g, '&lt;')
		.replace(/>/g, '&gt;')
		.replace(/"/g, '&quot;')
		.replace(/'/g, '&#39;');
}

function forestAgbNumber(value, digits = 2) {
	const number = Number(value);
	return Number.isFinite(number) ? number.toFixed(digits) : 'N/A';
}

function forestAgbStockUnitHtml() {
	return '10<sup>3</sup> tấn';
}

function forestAgbToThousandTons(sumMgHa) {
	const densitySum = Number(sumMgHa);
	if (!Number.isFinite(densitySum)) return NaN;
	const pixelAreaHa = 0.09;
	return densitySum * pixelAreaHa / 1000;
}

async function forestAgbReadJson(response) {
	const text = await response.text();
	const trimmed = (text || '').trim();
	if (!trimmed) {
		throw new Error(`Server không trả dữ liệu (HTTP ${response.status})`);
	}
	try {
		return JSON.parse(trimmed);
	} catch (err) {
		const snippet = trimmed.startsWith('<')
			? 'phản hồi HTML. Hãy khởi động lại server-product.py'
			: trimmed.replace(/\s+/g, ' ').slice(0, 160);
		throw new Error(`Server không trả JSON (HTTP ${response.status}): ${snippet}`);
	}
}

function forestAgbRenderCommuneTable(rows, { stockConverted = false } = {}) {
	if (!Array.isArray(rows) || rows.length === 0) {
		return '<div style="font-size:12px;color:#666;font-style:italic;">Không có dữ liệu theo xã.</div>';
	}

	const body = rows.map((item, index) => {
		const totalAgb = stockConverted
			? Number(item?.total_agb)
			: forestAgbToThousandTons(item?.total_agb);
		const totalCarbon = Number.isFinite(Number(item?.total_carbon)) && stockConverted
			? Number(item.total_carbon)
			: totalAgb * 0.47;
		return `
		<tr>
			<td style="padding:4px 6px;border-bottom:1px solid #eee;text-align:center;">${index + 1}</td>
			<td style="padding:4px 6px;border-bottom:1px solid #eee;">${forestAgbEscapeHtml(item?.tenxa || 'Không rõ')}</td>
			<td style="padding:4px 6px;border-bottom:1px solid #eee;text-align:right;white-space:nowrap;">${forestAgbNumber(item?.mean_agb, 4)}</td>
			<td style="padding:4px 6px;border-bottom:1px solid #eee;text-align:right;white-space:nowrap;">${forestAgbNumber(totalAgb, 4)}</td>
			<td style="padding:4px 6px;border-bottom:1px solid #eee;text-align:right;white-space:nowrap;">${forestAgbNumber(totalCarbon, 4)}</td>
		</tr>
	`;
	}).join('');

	return `
		<div style="max-height:220px;overflow:auto;border:1px solid #e6e6e6;border-radius:6px;">
			<table style="width:100%;border-collapse:collapse;font-size:12px;">
				<thead>
					<tr style="background:#f7f7f7;position:sticky;top:0;z-index:1;">
						<th style="padding:4px 6px;border-bottom:1px solid #ddd;width:28px;">#</th>
						<th style="padding:4px 6px;border-bottom:1px solid #ddd;text-align:left;">Tên xã</th>
						<th style="padding:4px 6px;border-bottom:1px solid #ddd;text-align:right;">AGB TB<br><span style="font-weight:400;color:#666;">Mg/ha</span></th>
						<th style="padding:4px 6px;border-bottom:1px solid #ddd;text-align:right;">Tổng AGB<br><span style="font-weight:400;color:#666;">${forestAgbStockUnitHtml()}</span></th>
						<th style="padding:4px 6px;border-bottom:1px solid #ddd;text-align:right;">Carbon<br><span style="font-weight:400;color:#666;">${forestAgbStockUnitHtml()}</span></th>
					</tr>
				</thead>
				<tbody>${body}</tbody>
			</table>
		</div>
	`;
}

function forestAgbRemoveControls() {
	forestAgbClearPolygon();
	forestAgbUnbindMap();
	if (forestAgbLayer) {
		map.removeLayer(forestAgbLayer);
		layerControl.removeLayer(forestAgbLayer);
		Object.keys(overlayMaps).forEach(key => {
			if (key.startsWith('Sinh khối rừng')) delete overlayMaps[key];
		});
		forestAgbLayer = null;
	}
	if (forestAgbLegend) {
		map.removeControl(forestAgbLegend);
		forestAgbLegend = null;
	}
	if (forestAgbStatsControl) {
		map.removeControl(forestAgbStatsControl);
		forestAgbStatsControl = null;
	}
	if (forestAgbDrawControl) {
		map.removeControl(forestAgbDrawControl);
		forestAgbDrawControl = null;
	}
	if (forestAgbPolygonControl) {
		map.removeControl(forestAgbPolygonControl);
		forestAgbPolygonControl = null;
	}
}

function forestAgbDrawEls() {
	return {
		draw: document.getElementById('forest-agb-draw-btn'),
		finish: document.getElementById('forest-agb-finish-btn'),
		clear: document.getElementById('forest-agb-clear-btn'),
		stats: document.getElementById('forest-agb-polygon-stats'),
	};
}

function forestAgbUpdateDrawButtons() {
	const { draw, finish, clear } = forestAgbDrawEls();
	if (!draw) return;
	const drawing = forestAgbDraw.active;
	const hasShape = Boolean(forestAgbDraw.polygon) || forestAgbDraw.points.length > 0;
	draw.classList.toggle('active', drawing);
	draw.textContent = drawing ? 'Đang vẽ…' : 'Vẽ vùng';
	if (finish) finish.disabled = !drawing || forestAgbDraw.points.length < 3;
	if (clear) clear.disabled = !hasShape && !drawing;
}

function forestAgbLockMap() {
	if (forestAgbDraw.active) map.doubleClickZoom.disable();
	else map.doubleClickZoom.enable();
	map.getContainer().classList.toggle('forest-agb-drawing', forestAgbDraw.active);
}

function forestAgbClearPreview() {
	if (forestAgbDraw.preview) {
		map.removeLayer(forestAgbDraw.preview);
		forestAgbDraw.preview = null;
	}
	forestAgbDraw.vertices.forEach(marker => map.removeLayer(marker));
	forestAgbDraw.vertices = [];
}

function forestAgbClearPolygon() {
	forestAgbDraw.active = false;
	forestAgbDraw.points = [];
	forestAgbClearPreview();
	if (forestAgbDraw.polygon) {
		map.removeLayer(forestAgbDraw.polygon);
		forestAgbDraw.polygon = null;
	}
	forestAgbLockMap();
	const { stats } = forestAgbDrawEls();
	if (stats) {
		stats.hidden = true;
		stats.innerHTML = '';
	}
	forestAgbUpdateDrawButtons();
}

function forestAgbStartDraw() {
	if (!forestAgbLayer) return;
	if (forestAgbDraw.active) {
		forestAgbClearPolygon();
		return;
	}
	forestAgbClearPolygon();
	forestAgbDraw.active = true;
	forestAgbLockMap();
	forestAgbUpdateDrawButtons();
}

function forestAgbAddVertex(latlng) {
	forestAgbDraw.points.push(latlng);
	const marker = L.circleMarker(latlng, {
		radius: 4,
		color: '#c62828',
		weight: 2,
		fillColor: '#ffcdd2',
		fillOpacity: 1,
		interactive: false,
	}).addTo(map);
	forestAgbDraw.vertices.push(marker);
	if (forestAgbDraw.preview) {
		forestAgbDraw.preview.setLatLngs(forestAgbDraw.points);
	} else {
		forestAgbDraw.preview = L.polyline(forestAgbDraw.points, {
			color: '#c62828',
			weight: 2,
			interactive: false,
		}).addTo(map);
	}
	forestAgbUpdateDrawButtons();
}

function forestAgbNearFirst(latlng) {
	if (forestAgbDraw.points.length < 3) return false;
	const first = forestAgbDraw.points[0];
	return map.latLngToLayerPoint(first).distanceTo(map.latLngToLayerPoint(latlng)) < 14;
}

function forestAgbRenderPolygonStats(res) {
	const { stats } = forestAgbDrawEls();
	if (!stats) return;
	stats.hidden = false;
	if (res.error) {
		stats.innerHTML = `<div style="font-weight:700;margin-bottom:4px;">Vùng đã vẽ</div><div>${forestAgbEscapeHtml(res.error)}</div>`;
		return;
	}
	const fraction = Number(res.ipcc_carbon_fraction);
	const fractionLabel = Number.isFinite(fraction) ? fraction.toFixed(2) : '0.47';
	stats.innerHTML = `
		<div style="font-weight:700;margin-bottom:6px;">Thống kê vùng đã vẽ</div>
		<div>AGB TB: <b>${forestAgbNumber(res.mean_agb, 2)} Mg/ha</b></div>
		<div>Tổng AGB: <b>${forestAgbNumber(res.total_agb, 2)} ${forestAgbStockUnitHtml()}</b></div>
		<div>Tổng Carbon: <b>${forestAgbNumber(res.total_carbon, 2)} ${forestAgbStockUnitHtml()}</b></div>
		<div style="color:#666;margin-top:4px;">Diện tích ${forestAgbNumber(res.area_ha, 2)} ha · IPCC ${fractionLabel}</div>
	`;
}

async function forestAgbFinishPolygon() {
	if (!forestAgbDraw.active || forestAgbDraw.points.length < 3) return;
	const points = forestAgbDraw.points.slice();
	forestAgbDraw.active = false;
	forestAgbClearPreview();
	forestAgbLockMap();
	if (forestAgbDraw.polygon) map.removeLayer(forestAgbDraw.polygon);
	forestAgbDraw.polygon = L.polygon(points, {
		color: '#c62828',
		weight: 2,
		fillColor: '#e53935',
		fillOpacity: 0.18,
	}).addTo(map);
	forestAgbUpdateDrawButtons();
	const coordinates = points.map(p => [p.lng, p.lat]);
	const query = forestAgbDraw.query || {};
	const { stats } = forestAgbDrawEls();
	if (stats) {
		stats.hidden = false;
		stats.innerHTML = '<div>Đang thống kê AGB theo vùng…</div>';
	}
	try {
		const response = await fetch('/forerest_agb_polygon', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
			body: JSON.stringify({
				coordinates,
				provinceSelect: query.province,
				districtSelect: query.districts,
				end: query.end,
			}),
		});
		const res = await forestAgbReadJson(response);
		if (!response.ok || res.error) {
			throw new Error(res.error || res.message || `HTTP ${response.status}`);
		}
		forestAgbRenderPolygonStats(res);
	} catch (err) {
		forestAgbRenderPolygonStats({ error: err.message });
	}
}

function forestAgbOnMapClick(event) {
	if (!forestAgbDraw.active) return;
	L.DomEvent.stop(event);
	if (forestAgbNearFirst(event.latlng)) {
		forestAgbFinishPolygon();
		return;
	}
	forestAgbAddVertex(event.latlng);
}

function forestAgbOnMapDblClick(event) {
	if (!forestAgbDraw.active) return;
	L.DomEvent.stop(event);
	if (forestAgbDraw.points.length >= 3) forestAgbFinishPolygon();
}

function forestAgbOnMapMouseMove(event) {
	if (!forestAgbDraw.active || !forestAgbDraw.points.length) return;
	const latlngs = forestAgbDraw.points.concat([event.latlng]);
	if (forestAgbDraw.preview) {
		forestAgbDraw.preview.setLatLngs(latlngs);
	} else {
		forestAgbDraw.preview = L.polyline(latlngs, {
			color: '#c62828',
			weight: 2,
			dashArray: '6 5',
			interactive: false,
		}).addTo(map);
	}
}

function forestAgbOnKeyDown(event) {
	if (event.key !== 'Escape' || !forestAgbDraw.active) return;
	forestAgbClearPolygon();
}

function forestAgbBindMap() {
	if (forestAgbMapBound) return;
	map.on('click', forestAgbOnMapClick);
	map.on('dblclick', forestAgbOnMapDblClick);
	map.on('mousemove', forestAgbOnMapMouseMove);
	document.addEventListener('keydown', forestAgbOnKeyDown);
	forestAgbMapBound = true;
}

function forestAgbUnbindMap() {
	if (!forestAgbMapBound) return;
	map.off('click', forestAgbOnMapClick);
	map.off('dblclick', forestAgbOnMapDblClick);
	map.off('mousemove', forestAgbOnMapMouseMove);
	document.removeEventListener('keydown', forestAgbOnKeyDown);
	forestAgbLockMap();
	forestAgbMapBound = false;
}

function forestAgbMountDrawUi(query) {
	forestAgbDraw.query = query;
	forestAgbBindMap();
	if (forestAgbDrawControl) map.removeControl(forestAgbDrawControl);
	if (forestAgbPolygonControl) {
		map.removeControl(forestAgbPolygonControl);
		forestAgbPolygonControl = null;
	}

	forestAgbDrawControl = L.control({ position: 'topleft' });
	forestAgbDrawControl.onAdd = function () {
		const wrap = L.DomUtil.create('div', 'forest-agb-draw-wrap');
		wrap.innerHTML = `
			<div class="forest-agb-draw-menu">
				<button id="forest-agb-draw-btn" type="button">Vẽ vùng</button>
				<button id="forest-agb-finish-btn" type="button" disabled>Hoàn thành</button>
				<button id="forest-agb-clear-btn" type="button" disabled>Xóa vùng</button>
			</div>
			<div id="forest-agb-polygon-stats" class="forest-agb-polygon-box" hidden></div>
		`;
		L.DomEvent.disableClickPropagation(wrap);
		L.DomEvent.disableScrollPropagation(wrap);
		return wrap;
	};
	forestAgbDrawControl.addTo(map);

	const { draw, finish, clear } = forestAgbDrawEls();
	if (draw) draw.addEventListener('click', forestAgbStartDraw);
	if (finish) finish.addEventListener('click', forestAgbFinishPolygon);
	if (clear) clear.addEventListener('click', () => forestAgbClearPolygon());
	forestAgbUpdateDrawButtons();
}

async function loadForestAgb() {
	const provinceElement = document.getElementById('provinceSelect');
	const districtElement = document.getElementById('districtSelect');
	const endElement = document.getElementById('endDate');
	const province = forestAgbNormalizeName(provinceElement?.value);
	const districts = Array.from(districtElement?.selectedOptions || [])
		.map(option => option.value).filter(Boolean).join(',');
	const end = endElement?.value || '';

	if (!province) {
		alert('Vui lòng chọn tỉnh/thành phố!');
		return;
	}
	if (!end) {
		alert('Vui lòng chọn thời điểm giám sát!');
		return;
	}

	const popup = document.createElement('div');
	popup.id = 'loading-popup';
	popup.innerHTML = `
		<div class="popup-box">
			<h3>AI ước tính sinh khối rừng</h3>
			<div class="progress-bar"><div class="progress-fill"></div></div>
			<p class="progress-text">0%</p>
		</div>
	`;
	document.body.appendChild(popup);
	const progressFill = popup.querySelector('.progress-fill');
	const progressText = popup.querySelector('.progress-text');
	let progress = 0;
	const progressTimer = setInterval(() => {
		progress = Math.min(progress + 5, 90);
		progressFill.style.width = `${progress}%`;
		progressText.textContent = `${progress}%`;
	}, 500);

	try {
		const params = new URLSearchParams({
			end,
			provinceSelect: province,
			districtSelect: districts,
		});
		const response = await fetch(`/forerest_agb?${params.toString()}`, {
			headers: { 'Accept': 'application/json' },
		});
		const data = await forestAgbReadJson(response);
		if (!response.ok) {
			const details = data.error || data.message || data.details;
			throw new Error(details ? `${details} (HTTP ${response.status})` : `Server trả về lỗi ${response.status}`);
		}
		if (data.error) throw new Error(data.error);
		if (!data.tile_url) throw new Error('Không có tile URL sinh khối trả về từ server');

		clearInterval(progressTimer);
		progressFill.style.width = '100%';
		progressText.textContent = 'Hoàn tất!';
		setTimeout(() => popup.remove(), 700);

		forestAgbRemoveControls();
		forestAgbLayer = L.tileLayer(data.tile_url).addTo(map);
		const endDate = new Date(`${end}T00:00:00`);
		const periodLabel = `${String(endDate.getMonth() + 1).padStart(2, '0')}/${endDate.getFullYear()}`;
		const layerLabel = `Sinh khối rừng (${periodLabel})`;
		overlayMaps[layerLabel] = forestAgbLayer;
		layerControl.addOverlay(forestAgbLayer, layerLabel);

		forestAgbStatsControl = L.control({ position: 'bottomleft' });
		forestAgbStatsControl.onAdd = function () {
			const div = L.DomUtil.create('div', 'info legend');
			div.style.marginBottom = '45px';
			div.style.marginLeft = '8px';
			div.style.background = 'rgba(255,255,255,0.94)';
			div.style.padding = '8px 10px';
			div.style.borderRadius = '8px';
			div.style.boxShadow = '0 2px 8px rgba(0,0,0,0.22)';
			div.style.fontFamily = 'Segoe UI, sans-serif';
			div.style.color = '#222';
			div.style.fontSize = '12px';
			div.style.lineHeight = '1.35';
			div.style.maxWidth = '380px';
			const carbonFraction = Number(data.ipcc_carbon_fraction);
			const fraction = Number.isFinite(carbonFraction) ? carbonFraction : 0.47;
			const fractionLabel = fraction.toFixed(2);
			const stockConverted = data.stock_unit === '10^3 tấn';
			const totalAgb = stockConverted
				? Number(data.total_agb)
				: forestAgbToThousandTons(data.total_agb);
			const totalCarbon = stockConverted && Number.isFinite(Number(data.total_carbon))
				? Number(data.total_carbon)
				: totalAgb * fraction;
			div.innerHTML = `
				<div style="font-weight:700;margin-bottom:6px;font-size:13px;">Thống kê sinh khối rừng</div>
				<div style="margin-bottom:3px;">Khoảng thời gian: <b>${forestAgbEscapeHtml(data.period?.start || '')} - ${forestAgbEscapeHtml(data.period?.end || end)}</b></div>
				<div>Giá trị nhỏ nhất: <b>${forestAgbNumber(data.min, 2)} Mg/ha</b></div>
				<div>Giá trị lớn nhất: <b>${forestAgbNumber(data.max, 2)} Mg/ha</b></div>
				<div>Tổng AGB: <b>${forestAgbNumber(totalAgb, 2)} ${forestAgbStockUnitHtml()}</b></div>
				<div>Tổng Carbon (IPCC ${fractionLabel}): <b>${forestAgbNumber(totalCarbon, 2)} ${forestAgbStockUnitHtml()}</b></div>
				<div style="font-size:11px;color:#666;margin-top:2px;">C = ${fractionLabel} × AGB (IPCC AFOLU)</div>
				<div style="font-weight:600;margin:8px 0 6px;">AGB theo ranh giới xã</div>
				${forestAgbRenderCommuneTable(data.mean_agb_by_commune, { stockConverted })}
			`;
			L.DomEvent.disableClickPropagation(div);
			return div;
		};
		forestAgbStatsControl.addTo(map);

		forestAgbLegend = L.control({ position: 'bottomright' });
		forestAgbLegend.onAdd = function () {
			const div = L.DomUtil.create('div', 'info legend');
			div.style.marginBottom = '45px';
			div.style.marginRight = '8px';
			div.style.background = 'rgba(255,255,255,0.92)';
			div.style.padding = '8px 10px';
			div.style.borderRadius = '8px';
			div.style.boxShadow = '0 2px 8px rgba(0,0,0,0.25)';
			div.style.font = '12px Segoe UI, sans-serif';
			const palette = Array.isArray(data.palette) ? data.palette : [];
			const swatches = palette.map(color => `
				<span style="display:inline-block;width:18px;height:12px;background:${forestAgbEscapeHtml(color)};border:1px solid #999;"></span>
			`).join('');
			div.innerHTML = `
				<div style="font-weight:700;text-align:center;margin-bottom:6px;font-size:13px;">Sinh khối rừng (${periodLabel})</div>
				<div style="text-align:center;margin-bottom:6px;font-size:11px;color:#555;">Đơn vị: Mg/ha</div>
				<div style="display:flex;gap:2px;margin-bottom:3px;">${swatches}</div>
				<div style="display:flex;justify-content:space-between;font-size:11px;color:#555;"><span>${forestAgbNumber(data.min)}</span><span>${forestAgbNumber(data.max)}</span></div>
				<hr style="border:none;border-top:1px solid #ccc;margin:8px 0;">
				<button id="btn-download-agb" style="width:100%;padding:7px 8px;background:#2e7d32;color:white;border:none;border-radius:5px;cursor:pointer;font-size:12px;font-weight:600;">⬇ Tải kết quả</button>
			`;
			const downloadButton = div.querySelector('#btn-download-agb');
			if (!data.download_url) {
				downloadButton.style.display = 'none';
			} else {
				downloadButton.addEventListener('click', () => {
					const link = document.createElement('a');
					link.href = data.download_url;
					link.download = `forest_agb_${end}.tif`;
					link.rel = 'noopener';
					document.body.appendChild(link);
					link.click();
					link.remove();
				});
			}
			L.DomEvent.disableClickPropagation(div);
			return div;
		};
		forestAgbLegend.addTo(map);
		forestAgbMountDrawUi({ province, districts, end });
	} catch (error) {
		clearInterval(progressTimer);
		popup.remove();
		console.error(error);
		alert(`Lỗi tải dữ liệu sinh khối rừng: ${error.message}`);
	}
}
