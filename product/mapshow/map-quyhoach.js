const QUY_HOACH_LAYER_LABEL = "Bản đồ quy hoạch 2030";
const QUY_HOACH_TILE_URL = "/quyhoach-tiles/{z}/{x}/{y}.png";
const QUY_HOACH_LAYER_DEFAULT_VISIBLE = false;

window.QUY_HOACH_LAYER_LABEL = QUY_HOACH_LAYER_LABEL;

let quyHoachLayer = null;
let quyHoachLegend = null;
let quyHoachLoadPromise = null;

function createQuyHoachLegend() {
	const quyhoachColors = [
		{ name: "Đất ở (OTC, ONT, ODT)", color: "#FFB4FF" },
		{ name: "Đất chuyên dùng (CDG, TSC, DSN, DSK…)", color: "#FFA0AA" },
		{ name: "Đất quốc phòng (CQP)", color: "#FF6450" },
		{ name: "Đất an ninh (CAN)", color: "#FF5046" },
		{ name: "Đất giao thông (DGT)", color: "#FFAA32" },
		{ name: "Đất nông nghiệp (NNP)", color: "#FFFF64" },
		{ name: "Đất sản xuất nông nghiệp (SXN)", color: "#FFFC6E" },
		{ name: "Đất trồng cây hàng năm (CHN)", color: "#FFFC78" },
		{ name: "Đất trồng lúa (LUA)", color: "#FFFC82" },
		{ name: "Đất chuyên trồng lúa nước (LUC)", color: "#FFFC8C" },
		{ name: "Đất trồng lúa nước còn lại (LUK)", color: "#FFFC96" },
		{ name: "Đất trồng lúa nương (LUN)", color: "#FFFCB4" },
		{ name: "Đất trồng cây hàng năm khác (HNK, BHK, NHK)", color: "#FFF0B4" },
		{ name: "Đất trồng cây lâu năm (CLN)", color: "#FFD2A0" },
		{ name: "Đất lâm nghiệp (LNP)", color: "#AAFF32" },
		{ name: "Đất rừng sản xuất (RSX, RSN, RST, RSM)", color: "#B4FFB4" },
		{ name: "Đất rừng phòng hộ (RPH, RPN, RPT, RPM)", color: "#BEFF1E" },
		{ name: "Đất rừng đặc dụng (RDD, RDN, RDT, RDM)", color: "#6EFF64" },
		{ name: "Đất nuôi trồng thủy sản (NTS)", color: "#AAFFFF" },
		{ name: "Đất làm muối (LMU)", color: "#FFFFFE" },
		{ name: "Đất nông nghiệp khác (NKH)", color: "#F5FFB4" },
		{ name: "Đất phi nông nghiệp (PNN)", color: "#FFFF64" },
		{ name: "Đất thủy lợi (DTL)", color: "#AAFFFF" },
		{ name: "Đất bãi thải, xử lý chất thải (DRA)", color: "#CDAACD" },
		{ name: "Đất nghĩa trang, nghĩa địa (NTD)", color: "#D2D2D2" },
		{ name: "Đất sông, ngòi, kênh, rạch, suối (SON)", color: "#A0FFFF" },
		{ name: "Đất có mặt nước chuyên dùng (MNC)", color: "#B4FFFF" },
		{ name: "Đất chưa sử dụng (CSD, BCS, DCS)", color: "#FFFFFE" },
		{ name: "Núi đá không có rừng cây (NCS)", color: "#E6E6C8" },
		{ name: "Đất mặt nước ven biển (MVB, MVT, MVR, MVK)", color: "#B4FFFF" }
	];

	const legend = L.control({ position: "topright" });
	legend.onAdd = function () {
		const container = L.DomUtil.create("div", "qh-legend-container");
		container.innerHTML = `
            <div class="qh-legend-toggle">&#x25C0;</div>
            <div class="qh-legend-panel">
				<h6 style="margin:0 0 10px 0;font-weight:bold;font-size:18px;text-align:center;line-height:1.2;">Chú giải quy hoạch</h6>
                <div class="qh-legend-content"></div>
            </div>
        `;

		const content = container.querySelector(".qh-legend-content");
		quyhoachColors.forEach((item) => {
			content.innerHTML += `
				<div style="display:flex;align-items:center;margin-bottom:3px;">
					<span style="display:inline-block;width:20px;height:20px;background:${item.color};border:1px solid #666;margin-right:6px;"></span>
					<span>${item.name}</span>
				</div>
			`;
		});

		const toggleBtn = container.querySelector(".qh-legend-toggle");
		let isOpen = false;

		function updatePanel() {
			if (isOpen) {
				container.style.transform = "translateX(0)";
				toggleBtn.innerHTML = "&#x25B6;";
			} else {
				container.style.transform = "translateX(300px)";
				toggleBtn.innerHTML = "&#x25C0;";
			}
		}

		toggleBtn.addEventListener("click", () => {
			isOpen = !isOpen;
			updatePanel();
		});

		updatePanel();
		return container;
	};

	return legend;
}

function removeQuyHoachLayer() {
	if (quyHoachLayer && typeof map !== "undefined" && map.hasLayer(quyHoachLayer)) {
		map.removeLayer(quyHoachLayer);
	}

	if (typeof layerControl !== "undefined" && layerControl && typeof layerControl.removeLayer === "function" && quyHoachLayer) {
		try {
			layerControl.removeLayer(quyHoachLayer);
		} catch (error) {
			console.warn("Không thể xóa lớp quy hoạch khỏi layer control:", error);
		}
	}

	if (typeof overlayMaps !== "undefined" && overlayMaps) {
		delete overlayMaps[QUY_HOACH_LAYER_LABEL];
	}

	quyHoachLayer = null;

	if (quyHoachLegend && typeof map !== "undefined") {
		try {
			map.removeControl(quyHoachLegend);
		} catch (error) {
			console.warn("Không thể xóa legend quy hoạch:", error);
		}
	}

	quyHoachLegend = null;
}

function syncQuyHoachLegend(visible) {
	if (!quyHoachLegend || typeof map === "undefined") {
		return;
	}

	if (visible) {
		if (!map.hasControl || !map.hasControl(quyHoachLegend)) {
			quyHoachLegend.addTo(map);
		}
	} else {
		try {
			map.removeControl(quyHoachLegend);
		} catch (error) {
			console.warn("Không thể ẩn legend quy hoạch:", error);
		}
	}
}

async function loadQuyHoachRaster() {
	if (typeof map === "undefined" || typeof L === "undefined") {
		throw new Error("Chưa khởi tạo bản đồ Leaflet.");
	}

	if (quyHoachLoadPromise) {
		return quyHoachLoadPromise;
	}

	quyHoachLoadPromise = (async () => {
		removeQuyHoachLayer();

		quyHoachLayer = L.tileLayer(QUY_HOACH_TILE_URL, {
			opacity: 1,
			tileSize: 256,
			maxZoom: 22,
			maxNativeZoom: 22,
			noWrap: true,
			updateWhenZooming: true,
			updateWhenIdle: true,
			errorTileUrl: "",
		});

		if (QUY_HOACH_LAYER_DEFAULT_VISIBLE) {
			quyHoachLayer.addTo(map);
		}

		if (typeof overlayMaps !== "undefined" && overlayMaps) {
			overlayMaps[QUY_HOACH_LAYER_LABEL] = quyHoachLayer;
		}

		if (typeof layerControl !== "undefined" && layerControl && typeof layerControl.addOverlay === "function") {
			layerControl.addOverlay(quyHoachLayer, QUY_HOACH_LAYER_LABEL);
		}

		quyHoachLegend = createQuyHoachLegend();
		syncQuyHoachLegend(QUY_HOACH_LAYER_DEFAULT_VISIBLE);

		if (typeof map !== "undefined" && typeof map.on === "function") {
			map.on("overlayadd overlayremove", (event) => {
				if (event.layer === quyHoachLayer) {
					syncQuyHoachLegend(event.type === "overlayadd");
				}
			});
		}

		return quyHoachLayer;
	})()
		.catch((error) => {
			console.error("Không tải được lớp quy hoạch 2030:", error);
			throw error;
		})
		.finally(() => {
			quyHoachLoadPromise = null;
		});

	return quyHoachLoadPromise;
}

window.loadQuyHoachRaster = loadQuyHoachRaster;
window.removeQuyHoachRaster = removeQuyHoachLayer;

if (document.readyState === "loading") {
	document.addEventListener("DOMContentLoaded", () => {
		loadQuyHoachRaster().catch(() => {});
	});
} else {
	loadQuyHoachRaster().catch(() => {});
}