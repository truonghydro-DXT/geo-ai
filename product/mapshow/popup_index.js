function bindIndexPopup(map, selectId, apiEndpoint) {
  const indexSelect = document.getElementById(selectId);
  if (!indexSelect) return;

  map.on("click", async function(e) {
    const { lat, lng } = e.latlng;
    const end = document.getElementById("endDate").value;
    const endDateObj = new Date(end);
    const startDateObj = new Date(endDateObj);
    startDateObj.setDate(endDateObj.getDate() - 35);
    const start = startDateObj.toISOString().split('T')[0];
    const indexName = indexSelect.value;
    if (!indexName) return;

    try {
      const resp = await fetch(`${apiEndpoint}?lat=${lat}&lon=${lng}&start=${start}&end=${end}`);
      const data = await resp.json();
      let value = data[indexName] ?? "No data";

      L.popup()
        .setLatLng(e.latlng)
        .setContent(`<b>Chỉ số ${indexName.toUpperCase()}</b><br>Lat: ${lat.toFixed(4)}, Lon: ${lng.toFixed(4)}<br>Value: ${typeof value === "number" ? value.toFixed(4) : value}`)
        .openOn(map);
    } catch (err) {
      console.error(err);
      alert("Error fetching value: " + err.message);
    }
  });
}
