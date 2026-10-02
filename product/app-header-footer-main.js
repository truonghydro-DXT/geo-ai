document.addEventListener("DOMContentLoaded", function () {
  document.body.insertAdjacentHTML(
    "afterbegin",
    `
    <header class="main-header">
      <div class="header-left">
        <h1 class="header-title">PHÂN TÍCH RỪNG TỪ ẢNH VIỄN THÁM</h1>
      </div>
      <div class="header-right">
        <img src="images/icon.png" alt="Logo" class="header-logo" />
      </div>
    </header>
    `
  );

  if (location.hash === "#uav" && typeof window.showUavAgbWorkspace === "function") {
    const detect = document.getElementById("satelliteDetect");
    if (detect) detect.value = "forerest_agb_uav";
    window.showUavAgbWorkspace();
  }

  const footer = document.getElementById("footer");
  if (footer) {
    footer.innerHTML = `
      <div class="footer-container">
        <div class="footer-left">
          © 2025 <strong>Đinh Xuân Trường</strong>. All rights reserved.
        </div>
        <div class="footer-right">
          <a href="mailto:truonghydro@gmail.com" class="footer-email">✉️ truonghydro@gmail.com</a>
        </div>
      </div>
    `;
  }
});
