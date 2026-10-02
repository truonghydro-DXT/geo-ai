
let legendControl;

function normalize_name(name) {
  return name.replace(/Thành\s*phố\s*/i, 'tp')
             .replace(/Tỉnh\s*/i, 'tinh')
             .normalize("NFD").replace(/[\u0300-\u036f]/g, "")
             .replace(/đ/g, "d").replace(/Đ/g, "D")
             .replace(/\s+/g, '');
}

async function loadIndex(index) {
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
      <h3>Đang tính toán chỉ số ${index.toUpperCase()}</h3>
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
      resp = await fetch(`/${index}?start=${start}&end=${end}&provinceSelect=${encodeURIComponent(province)}`);
    } else {
      resp = await fetch(`/${index}?start=${start}&end=${end}&provinceSelect=${encodeURIComponent(province)}&districtSelect=${encodeURIComponent(districts)}`);
    }

    const data = await resp.json();

    if (!data.tile_url) {
      console.error('No tile URL from server', data);
      alert('No tile URL returned - check server console');
      return;
    }

    clearInterval(progressTimer);
    progressFill.style.width = "100%";
    progressText.textContent = "Hoàn tất!";

    setTimeout(() => popup.remove(), 700);

    // Xóa tile cũ nếu có
    if (window.eeTile) map.removeLayer(window.eeTile);
    window.eeTile = L.tileLayer(data.tile_url).addTo(map);

    // Xóa legend cũ nếu có
    if (legendControl) {
      map.removeControl(legendControl);
    }

    // Tạo legend mới
    const label = `(${month}/${year})`;
    legendControl = L.control({ position: 'bottomright' });
    legendControl.onAdd = function () {
      const div = L.DomUtil.create('div', 'info legend');
      div.style.marginBottom = '30px';
      div.style.marginRight = '8px';
      div.style.background = 'white';
      div.style.padding = '10px';
      div.style.border = '1px solid #ccc';
      div.style.fontSize = '12px';
      div.innerHTML = `<b>${index.toUpperCase()} Legend ${label}</b><br>`; 
      
      data.legend.forEach(item => {
        div.innerHTML += `
          <div style="display:flex;align-items:center;margin-bottom:2px;">
            <span style="background:${item.color};width:18px;height:18px;display:inline-block;margin-right:5px;border:1px solid #555"></span>
            ${item.label}
          </div>
        `;
      });
      return div;
    };
    legendControl.addTo(map);

  } catch (err) {
    clearInterval(progressTimer);
    popup.remove();
    console.error(err);
    alert(`Error loading ${index.toUpperCase()}: ` + err.message);
  }
}
indexSelect.addEventListener('change', function() {
  if (legendControl) {
      map.removeControl(legendControl);
  }
});
