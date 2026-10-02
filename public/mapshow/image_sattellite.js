let sentinel1Layer;
function normalize_name(name) {
  return name.replace(/Thành\s*phố\s*/i, 'tp')
             .replace(/Tỉnh\s*/i, 'tinh')
             .normalize("NFD").replace(/[\u0300-\u036f]/g, "")
             .replace(/đ/g, "d").replace(/Đ/g, "D")
             .replace(/\s+/g, '');
}

async function loadSentinel1() {
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
  startDateObj.setDate(endDateObj.getDate() - 35);
  const start = startDateObj.toISOString().split("T")[0];
  const month = endDateObj.getMonth() + 1;
  const year = endDateObj.getFullYear();

  // === Hiển thị popup tiến trình ===
  const popup = document.createElement("div");
  popup.id = "loading-popup";
  popup.innerHTML = `
    <div class="popup-box">
      <h3>Đang xử lý dữ liệu Sentinel-1</h3>
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
    let resp
    if (districts.length === 0) {
      resp = await fetch(`/sentinel1?start=${start}&end=${end}&provinceSelect=${encodeURIComponent(province)}`);
    } else {
      resp = await fetch(`/sentinel1?start=${start}&end=${end}&provinceSelect=${encodeURIComponent(province)}&districtSelect=${encodeURIComponent(districts)}`);
    }
    if (!resp.ok) throw new Error(`Server trả về lỗi ${resp.status}`);

    const data = await resp.json();
    if (!data.tile_url) throw new Error("Không có tile URL trả về từ server");

    clearInterval(progressTimer);
    progressFill.style.width = "100%";
    progressText.textContent = "Hoàn tất!";

    setTimeout(() => popup.remove(), 700);

    if (sideBySideControl) {
      try { map.removeControl(sideBySideControl); } catch {}
      sideBySideControl = null;
    }

    // Xóa layer cũ
    if (sentinel1Layer) {
      map.removeLayer(sentinel1Layer);
      layerControl.removeLayer(sentinel1Layer);
      delete overlayMaps["Sentinel-1"];
    }

    // Tạo layer mới
    sentinel1Layer = L.tileLayer(data.tile_url).addTo(map);

    // Thêm vào Layer Control
    const label = `Sentinel-1 (${month}/${year})`;
    overlayMaps[label] = sentinel1Layer;
    layerControl.addOverlay(sentinel1Layer, label);

  } catch (err) {
    clearInterval(progressTimer);
    popup.remove();
    console.error(err);
    alert("Lỗi tải Sentinel-1: " + err.message);
  }
}


let sentinel2Layer;
async function loadSentinel2() {
  const province = normalize_name(document.getElementById("provinceSelect").value);
  const districts = Array.from(document.getElementById("districtSelect").selectedOptions)
    .map(o => o.value).filter(Boolean).join(',');
  const end = document.getElementById("endDate").value;
  const endDateObj = new Date(end);
  const startDateObj = new Date(endDateObj);
  startDateObj.setDate(endDateObj.getDate() - 35);
  const start = startDateObj.toISOString().split('T')[0];
  const month = new Date(end).getMonth() + 1;
  const year  = new Date(end).getFullYear(); 

  // === Hiển thị popup tiến trình ===
  const popup = document.createElement("div");
  popup.id = "loading-popup";
  popup.innerHTML = `
    <div class="popup-box">
      <h3>Đang xử lý dữ liệu Sentinel-2</h3>
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
    let resp
    if (districts.length === 0) {
      resp = await fetch(`/sentinel2?start=${start}&end=${end}&provinceSelect=${encodeURIComponent(province)}`);
    } else {
      resp = await fetch(`/sentinel2?start=${start}&end=${end}&provinceSelect=${encodeURIComponent(province)}&districtSelect=${encodeURIComponent(districts)}`);
    }
        
    const data = await resp.json();

    if (!data.tile_url) {
      alert('Không có tile URL trả về từ server');
      return;
    }
    clearInterval(progressTimer);
    progressFill.style.width = "100%";
    progressText.textContent = "Hoàn tất!";

    setTimeout(() => popup.remove(), 700);

    if (sentinel2Layer) {
      map.removeLayer(sentinel2Layer);
      layerControl.removeLayer(sentinel2Layer);
      delete overlayMaps["Sentinel-2"];
    }

    sentinel2Layer = L.tileLayer(data.tile_url);

    // Thêm layer vào map
    sentinel2Layer.addTo(map);

    // Thêm vào Overlay Control
    const label = `Sentinel-2 (${month}/${year})`;
    overlayMaps[label] = sentinel2Layer;
    layerControl.addOverlay(sentinel2Layer, label);

  } catch (err) {
    clearInterval(progressTimer);
    popup.remove();
    console.error(err);
    alert('Lỗi tải Sentinel-2: ' + err.message);
  }
}

// let planetLayer;
// async function loadPlanet() {
//   const province = normalize_name(document.getElementById("provinceSelect").value);
//   const districts = document.getElementById("districtSelect").value;
//   const end = document.getElementById("endDate").value;
//   const endDateObj = new Date(end);
//   const startDateObj = new Date(endDateObj);
//   startDateObj.setDate(endDateObj.getDate() - 35);
//   const month = new Date(end).getMonth() + 1;
//   const year  = new Date(end).getFullYear(); 
  
//   // === Hiển thị popup tiến trình ===
//   const popup = document.createElement("div");
//   popup.id = "loading-popup";
//   popup.innerHTML = `
//     <div class="popup-box">
//       <h3>Đang xử lý dữ liệu Planet</h3>
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
//     let resp
//     if (districts === "") {
//       resp = await fetch(`/planet?end=${end}&provinceSelect=${encodeURIComponent(province)}`);
//     } else {
//       resp = await fetch(`/planet?end=${end}&provinceSelect=${encodeURIComponent(province)}&districtSelect=${encodeURIComponent(districts)}`);
//     }
        
//     const data = await resp.json();
//     console.log(data)

//     if (!data.tile_url) {
//       alert('Không có tile URL trả về từ server');
//       return;
//     }
//     clearInterval(progressTimer);
//     progressFill.style.width = "100%";
//     progressText.textContent = "Hoàn tất!";

//     setTimeout(() => popup.remove(), 700);

//     if (planetLayer) {
//       map.removeLayer(planetLayer);
//       layerControl.removeLayer(planetLayer);
//       delete overlayMaps["Planet"];
//     }

//     planetLayer = L.tileLayer(data.tile_url);

//     // Thêm layer vào map
//     planetLayer.addTo(map);

//     // Thêm vào Overlay Control
//     const label = `Planet (${month}/${year})`;
//     overlayMaps[label] = planetLayer;
//     layerControl.addOverlay(planetLayer, label);

//   } catch (err) {
//     clearInterval(progressTimer);
//     popup.remove();
//     console.error(err);
//     alert('Lỗi tải Planet: ' + err.message);
//   }
// }

let planetLayerCurrent, planetLayerPrevious, sideBySideControl;

async function loadPlanet() {
  const end = document.getElementById("endDate").value;
  let endDateObj = new Date(end);

  const monthnow = endDateObj.getMonth() + 1;
  const yearnow = endDateObj.getFullYear();

  // === Nếu end cùng tháng và năm với thời gian hiện tại thì tự lùi lại 1 tháng ===
  const now = new Date();
  if (
    endDateObj.getFullYear() === now.getFullYear() &&
    endDateObj.getMonth() === now.getMonth()
  ) {
    // Lùi lại 1 tháng an toàn
    endDateObj.setMonth(endDateObj.getMonth() - 1);
  }

  // === Lấy lại giá trị năm và tháng sau khi hiệu chỉnh ===
  const month = endDateObj.getMonth() + 1;
  const year = endDateObj.getFullYear();

  // === Xác định tháng trước ===
  let prevMonth = month - 1;
  let prevYear = year;  
  if (prevMonth <= 0) {
    prevMonth = 12;
    prevYear -= 1;
  }

  // === Popup tiến trình ===
  const popup = document.createElement("div");
  popup.id = "loading-popup";
  popup.innerHTML = `
    <div class="popup-box">
      <h3>Đang tải dữ liệu Planet...</h3>
      <div class="progress-bar"><div class="progress-fill"></div></div>
      <p class="progress-text">0%</p>
    </div>
  `;
  document.body.appendChild(popup);

  const progressFill = popup.querySelector(".progress-fill");
  const progressText = popup.querySelector(".progress-text");

  let progress = 0;
  const timer = setInterval(() => {
    progress += 5;
    if (progress >= 90) progress = 90;
    progressFill.style.width = `${progress}%`;
    progressText.textContent = `${progress}%`;
  }, 500);

  try {
    
    const [respPrev, respCurr] = await Promise.all([
      fetch(`/planet?end=${prevYear}-${String(prevMonth).padStart(2, "0")}-01`),
      fetch(`/planet?end=${year}-${String(month).padStart(2, "0")}-01`)
    ]);

    const dataPrev = await respPrev.json();
    const dataCurr = await respCurr.json();

    clearInterval(timer);
    progressFill.style.width = "100%";
    progressText.textContent = "Hoàn tất!";
    setTimeout(() => popup.remove(), 700);

    if (!dataCurr.tile_url || !dataPrev.tile_url) {
      alert("Không có dữ liệu Planet cho 1 trong 2 tháng.");
      return;
    }

    // === Gỡ bỏ control & layer cũ ===
    if (sideBySideControl) {
      try { map.removeControl(sideBySideControl); } catch {}
      sideBySideControl = null;
    }
    if (planetLayerCurrent && map.hasLayer(planetLayerCurrent)) {
      map.removeLayer(planetLayerCurrent);
    }
    if (planetLayerPrevious && map.hasLayer(planetLayerPrevious)) {
      map.removeLayer(planetLayerPrevious);
    }

    planetLayerCurrent = null;
    planetLayerPrevious = null;

    // === Tạo 2 tile layer mới ===
    planetLayerPrevious = L.tileLayer(dataPrev.tile_url, { opacity: 1 });
    planetLayerCurrent = L.tileLayer(dataCurr.tile_url, { opacity: 1 });
    map.addLayer(planetLayerPrevious);
    map.addLayer(planetLayerCurrent);


    // === Hiển thị hiệu ứng trượt (SideBySide) ===
    sideBySideControl = L.control.sideBySide(planetLayerPrevious, planetLayerCurrent).addTo(map);

    // === Xóa nhãn cũ (nếu có) ===
    document.querySelectorAll('.side-label').forEach(el => el.remove());


    const monthlable = monthnow-1
    const yearlable = yearnow

    if (monthlable <= 0) {
      monthlable = 12;
      yearlable -= 1;
    }
    // === Thêm nhãn tên lớp 2 bên ===
    const leftLabel = document.createElement('div');
    leftLabel.className = 'side-label side-label-left';
    leftLabel.textContent = `Planet ${monthlable}/${yearlable}`;

    const rightLabel = document.createElement('div');
    rightLabel.className = 'side-label side-label-right';
    rightLabel.textContent = `Planet ${monthnow}/${yearnow}`;

    document.body.appendChild(leftLabel);
    document.body.appendChild(rightLabel);

    // === Chỉ tắt dragging khi đang kéo thanh trượt & xử lý ẩn nhãn ===
    setTimeout(() => {
      const handle = document.querySelector('.leaflet-sbs-range');
      if (handle) {
        handle.addEventListener('mousedown', () => map.dragging.disable());
        handle.addEventListener('touchstart', () => map.dragging.disable());
        handle.addEventListener('mouseup', () => map.dragging.enable());
        handle.addEventListener('touchend', () => map.dragging.enable());

        // === Ẩn/hiện nhãn khi kéo ===
        handle.addEventListener('input', () => {
          const val = parseFloat(handle.value);
          // console.log(val); // kiểm tra vị trí slider: từ 0 đến 1
          if (val <= 0.1) {
            leftLabel.style.opacity = "0";   // ẩn nhãn trái
            rightLabel.style.opacity = "1";
          } else if (val >= 0.9) {
            rightLabel.style.opacity = "0";  // ẩn nhãn phải
            leftLabel.style.opacity = "1";
          } else {
            leftLabel.style.opacity = "1";
            rightLabel.style.opacity = "1";
          }
        });
      }
    }, 500);


    // === Cập nhật layer control ===
    if (layerControl) {
      // Xóa layer cũ khỏi overlayMaps
      Object.keys(overlayMaps).forEach(k => {
        if (k.startsWith("Planet")) delete overlayMaps[k];
      });
      layerControl.remove(); // remove old control
      layerControl = L.control.layers(baseMaps, overlayMaps).addTo(map);
    }

    overlayMaps[`Planet ${monthlable}/${yearlable}`] = planetLayerPrevious;
    overlayMaps[`Planet ${monthnow}/${yearnow}`] = planetLayerCurrent;
    layerControl.addOverlay(planetLayerPrevious, `Planet ${monthlable}/${yearlable}`);
    layerControl.addOverlay(planetLayerCurrent, `Planet ${monthnow}/${yearnow}`);

  } catch (err) {
    clearInterval(timer);
    popup.remove();
    console.error(err);
    alert("Lỗi tải Planet: " + err.message);
  }
}

let planningLayer;
let legend_quyhoach;
async function loadPlanetBuild() {
  function normalize_name(name) {
    return name.replace(/Thành\s*phố\s*/i, 'tp')
              .replace(/Tỉnh\s*/i, 'tinh')
              .normalize("NFD").replace(/[\u0300-\u036f]/g, "")
              .replace(/đ/g, "d").replace(/Đ/g, "D")
              .replace(/\s+/g, '');
  }
  const GEOSERVER = 'https://geoserver.lifetex.vn/geoserver';

  const province = normalize_name(document.getElementById("provinceSelect").value);
  const end = document.getElementById("endDate").value;
  let endDateObj = new Date(end);

  const monthnow = endDateObj.getMonth() + 1;
  const yearnow = endDateObj.getFullYear();

  // === Nếu end cùng tháng và năm với thời gian hiện tại thì tự lùi lại 1 tháng ===
  const now = new Date();
  if (
    endDateObj.getFullYear() === now.getFullYear() &&
    endDateObj.getMonth() === now.getMonth()
  ) {
    // Lùi lại 1 tháng an toàn
    endDateObj.setMonth(endDateObj.getMonth() - 1);
  }

  // === Lấy lại giá trị năm và tháng sau khi hiệu chỉnh ===
  const month = endDateObj.getMonth() + 1;
  const year = endDateObj.getFullYear();

  // === Xác định tháng trước ===
  let prevMonth = month - 1;
  let prevYear = year;  
  if (prevMonth <= 0) {
    prevMonth = 12;
    prevYear -= 1;
  }

  // === Popup tiến trình ===
  const popup = document.createElement("div");
  popup.id = "loading-popup";
  popup.innerHTML = `
    <div class="popup-box">
      <h3>Đang tải dữ liệu Planet...</h3>
      <div class="progress-bar"><div class="progress-fill"></div></div>
      <p class="progress-text">0%</p>
    </div>
  `;
  document.body.appendChild(popup);

  const progressFill = popup.querySelector(".progress-fill");
  const progressText = popup.querySelector(".progress-text");

  let progress = 0;
  const timer = setInterval(() => {
    progress += 5;
    if (progress >= 90) progress = 90;
    progressFill.style.width = `${progress}%`;
    progressText.textContent = `${progress}%`;
  }, 500);

  try {
    
    const [respPrev, respCurr] = await Promise.all([
      fetch(`/planet?end=${prevYear}-${String(prevMonth).padStart(2, "0")}-01`),
      fetch(`/planet?end=${year}-${String(month).padStart(2, "0")}-01`)
    ]);

    const dataPrev = await respPrev.json();
    const dataCurr = await respCurr.json();

    clearInterval(timer);
    progressFill.style.width = "100%";
    progressText.textContent = "Hoàn tất!";
    setTimeout(() => popup.remove(), 700);

    if (!dataCurr.tile_url || !dataPrev.tile_url) {
      alert("Không có dữ liệu Planet cho 1 trong 2 tháng.");
      return;
    }

    // === Gỡ bỏ control & layer cũ ===
    if (sideBySideControl) {
      try { map.removeControl(sideBySideControl); } catch {}
      sideBySideControl = null;
    }
    if (planetLayerCurrent && map.hasLayer(planetLayerCurrent)) {
      map.removeLayer(planetLayerCurrent);
    }
    if (planetLayerPrevious && map.hasLayer(planetLayerPrevious)) {
      map.removeLayer(planetLayerPrevious);
    }

    if (planningLayer && map.hasLayer(planningLayer)) {
      map.removeLayer(planningLayer);
    }

    planetLayerCurrent = null;
    planetLayerPrevious = null;
    planningLayer = null;


    // === Tạo 2 tile layer mới ===
    planetLayerPrevious = L.tileLayer(dataPrev.tile_url, { opacity: 1 });
    planetLayerCurrent = L.tileLayer(dataCurr.tile_url, { opacity: 1 });

    const tablenameQH = `QH_${province}`;
    planningLayer = L.tileLayer.wms(`${GEOSERVER}/wms`, {
      layers: 'lifetexQH:' + tablenameQH,
      format: 'image/png',
      transparent: true,
      tiled: true
    });
  

    // === Hiển thị hiệu ứng trượt (SideBySide) ===
    sideBySideControl = L.control.sideBySide(planetLayerPrevious, planetLayerCurrent).addTo(map);

    // === Xóa nhãn cũ (nếu có) ===
    document.querySelectorAll('.side-label').forEach(el => el.remove());


    const monthlable = monthnow-1
    const yearlable = yearnow

    if (monthlable <= 0) {
      monthlable = 12;
      yearlable -= 1;
    }
    // === Thêm nhãn tên lớp 2 bên ===
    const leftLabel = document.createElement('div');
    leftLabel.className = 'side-label side-label-left';
    leftLabel.textContent = `Planet ${monthlable}/${yearlable}`;

    const rightLabel = document.createElement('div');
    rightLabel.className = 'side-label side-label-right';
    rightLabel.textContent = `Planet ${monthnow}/${yearnow}`;

    document.body.appendChild(leftLabel);
    document.body.appendChild(rightLabel);

    // === Chỉ tắt dragging khi đang kéo thanh trượt & xử lý ẩn nhãn ===
    setTimeout(() => {
      const handle = document.querySelector('.leaflet-sbs-range');
      if (handle) {
        handle.addEventListener('mousedown', () => map.dragging.disable());
        handle.addEventListener('touchstart', () => map.dragging.disable());
        handle.addEventListener('mouseup', () => map.dragging.enable());
        handle.addEventListener('touchend', () => map.dragging.enable());

        // === Ẩn/hiện nhãn khi kéo ===
        handle.addEventListener('input', () => {
          const val = parseFloat(handle.value);
          // console.log(val); // kiểm tra vị trí slider: từ 0 đến 1
          if (val <= 0.1) {
            leftLabel.style.opacity = "0";   // ẩn nhãn trái
            rightLabel.style.opacity = "1";
          } else if (val >= 0.9) {
            rightLabel.style.opacity = "0";  // ẩn nhãn phải
            leftLabel.style.opacity = "1";
          } else {
            leftLabel.style.opacity = "1";
            rightLabel.style.opacity = "1";
          }
        });
      }
    }, 500);


    // === Cập nhật layer control ===
    if (layerControl) {
      // Xóa layer cũ khỏi overlayMaps
      Object.keys(overlayMaps).forEach(k => {
        if (k.startsWith("Planet")) delete overlayMaps[k];
      });
      layerControl.remove(); // remove old control
      layerControl = L.control.layers(baseMaps, overlayMaps).addTo(map);
    }

    overlayMaps[`Planet ${monthlable}/${yearlable}`] = planetLayerPrevious;
    overlayMaps[`Planet ${monthnow}/${yearnow}`] = planetLayerCurrent;
    // overlayMaps[`Bản đồ quy hoạch 2030`] = planningLayer;
     
    layerControl.addOverlay(planetLayerPrevious, `Planet ${monthlable}/${yearlable}`);
    layerControl.addOverlay(planetLayerCurrent, `Planet ${monthnow}/${yearnow}`);
    // layerControl.addOverlay(planningLayer, `Bản đồ quy hoạch 2030`);

    createQHLegend(map)

  } catch (err) {
    clearInterval(timer);
    popup.remove();
    console.error(err);
    alert("Lỗi tải Planet: " + err.message);
  }
}

function createQHLegend(map) {
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

    legend_quyhoach = L.control({ position: "topright" });

    legend_quyhoach.onAdd = function () {
        const container = L.DomUtil.create("div", "qh-legend-container");
        container.innerHTML = `
            <div class="qh-legend-toggle">&#x25C0;</div>
            <div class="qh-legend-panel">
                <h6 style="margin-bottom:6px;font-weight:bold;">Chú giải quy hoạch</h6>
                <div class="qh-legend-content"></div>
            </div>
        `;

        const content = container.querySelector(".qh-legend-content");
        quyhoachColors.forEach(item => {
            content.innerHTML += `
                <div style="display:flex;align-items:center;margin-bottom:3px;">
                    <span style="display:inline-block;width:20px;height:20px;background:${item.color};
                        border:1px solid #666;margin-right:6px;"></span>
                    <span>${item.name}</span>
                </div>
            `;
        });

        // xử lý toggle
        const toggleBtn = container.querySelector(".qh-legend-toggle");
        let isOpen = false; // mặc định đóng

        function updatePanel() {
            if (isOpen) {
                container.style.transform = "translateX(0)";
                toggleBtn.innerHTML = "&#x25B6;"; // mũi tên sang phải
            } else {
                container.style.transform = "translateX(300px)"; // ẩn ra ngoài
                toggleBtn.innerHTML = "&#x25C0;"; // mũi tên sang trái
            }
        }

        toggleBtn.addEventListener("click", () => {
            isOpen = !isOpen;
            updatePanel();
        });

        updatePanel(); // khởi tạo ở trạng thái đóng

        return container;
    };

    // legend_quyhoach.addTo(map);
}