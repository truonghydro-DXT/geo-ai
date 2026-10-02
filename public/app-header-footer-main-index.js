document.addEventListener("DOMContentLoaded", function () {
  // Header
  document.body.insertAdjacentHTML(
    "afterbegin",
    `
    <header class="main-header">
      <div class="header-left">
        <h1 class="header-title">ỨNG DỤNG GIẢI ĐOÁN ẢNH VIỄN THÁM</h1>
      </div>
      <div class="header-right">
        <img src="images/icon.png" alt="Logo" class="header-logo" />
      </div>
    </header>
    `
  );

  // Footer
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
