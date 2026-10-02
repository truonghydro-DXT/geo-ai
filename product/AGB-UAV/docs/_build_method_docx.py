"""Generate the methodology Word document for AGB-UAV."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "Mo_ta_thuat_toan_phuong_phap_AGB_UAV.docx"


def set_run_font(run, *, size=12, bold=False, italic=False, color=None, name="Times New Roman"):
    run.font.name = name
    run._element.rPr.rFonts.set(qn("w:eastAsia"), name)
    run.font.size = Pt(size)
    run.bold = bold
    run.italic = italic
    if color is not None:
        run.font.color.rgb = color


def add_paragraph(doc, text, *, size=12, bold=False, italic=False, align=None, space_after=8, first_line=True):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_after = Pt(space_after)
    pf.space_before = Pt(0)
    pf.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
    if first_line:
        pf.first_line_indent = Cm(1.0)
    if align is not None:
        p.alignment = align
    run = p.add_run(text)
    set_run_font(run, size=size, bold=bold, italic=italic)
    return p


def add_heading_custom(doc, text, level=1):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_before = Pt(16 if level == 1 else 12)
    pf.space_after = Pt(8)
    pf.first_line_indent = Cm(0)
    pf.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
    run = p.add_run(text)
    size = 14 if level == 1 else 13
    set_run_font(run, size=size, bold=True, color=RGBColor(0x1B, 0x3D, 0x2F))
    return p


def add_formula(doc, text):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_before = Pt(6)
    pf.space_after = Pt(6)
    pf.first_line_indent = Cm(0)
    pf.left_indent = Cm(1.25)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(text)
    set_run_font(run, size=12, italic=True)
    return p


def set_cell_text(cell, text, *, bold=False, center=False):
    cell.text = ""
    p = cell.paragraphs[0]
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.first_line_indent = Cm(0)
    if center:
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(text)
    set_run_font(run, size=11, bold=bold)


def shade_header(row):
    for cell in row.cells:
        tc = cell._tc
        tcPr = tc.get_or_add_tcPr()
        shd = tcPr.makeelement(qn("w:shd"), {qn("w:fill"): "1F6B3A", qn("w:val"): "clear"})
        tcPr.append(shd)
        for p in cell.paragraphs:
            for run in p.runs:
                run.font.color.rgb = RGBColor(255, 255, 255)
                run.bold = True


def add_table(doc, headers, rows):
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, h in enumerate(headers):
        set_cell_text(table.rows[0].cells[i], h, bold=True, center=True)
    shade_header(table.rows[0])
    for r, row in enumerate(rows, start=1):
        for c, val in enumerate(row):
            set_cell_text(table.rows[r].cells[c], val)
    doc.add_paragraph()
    return table


def build():
    doc = Document()
    section = doc.sections[0]
    section.top_margin = Cm(2.2)
    section.bottom_margin = Cm(2.2)
    section.left_margin = Cm(2.5)
    section.right_margin = Cm(2.2)
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)

    style = doc.styles["Normal"]
    style.font.name = "Times New Roman"
    style.font.size = Pt(12)
    style._element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")

    # Title page
    for _ in range(2):
        doc.add_paragraph()
    t = doc.add_paragraph()
    t.alignment = WD_ALIGN_PARAGRAPH.CENTER
    t.paragraph_format.space_after = Pt(8)
    r = t.add_run("BÁO CÁO KỸ THUẬT")
    set_run_font(r, size=16, bold=True, color=RGBColor(0x1B, 0x3D, 0x2F))

    t2 = doc.add_paragraph()
    t2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    t2.paragraph_format.space_after = Pt(18)
    r = t2.add_run("THUẬT TOÁN, PHƯƠNG PHÁP, KỸ THUẬT VÀ DỮ LIỆU")
    set_run_font(r, size=14, bold=True)

    t3 = doc.add_paragraph()
    t3.alignment = WD_ALIGN_PARAGRAPH.CENTER
    t3.paragraph_format.space_after = Pt(6)
    r = t3.add_run("Ứng dụng ước lượng sinh khối trên mặt đất (AGB)")
    set_run_font(r, size=14, italic=True)

    t4 = doc.add_paragraph()
    t4.alignment = WD_ALIGN_PARAGRAPH.CENTER
    t4.paragraph_format.space_after = Pt(28)
    r = t4.add_run("từ ảnh orthomosaic UAV RGB — AGB-UAV")
    set_run_font(r, size=14, italic=True)

    meta = [
        "Phần mềm: AGB-UAV (DeepLiDARPlanet / GeoTIFF Viewer)",
        "Mô-đun tính toán: Modelling/Biomass_analysis.py",
        "Mô-đun hiển thị: viewer/server.py, viewer/raster.py",
        f"Ngày biên soạn: {date.today().strftime('%d/%m/%Y')}",
        "Khu vực minh họa: khoảng 21,12°N – 105,68°E (WGS 84)",
    ]
    for line in meta:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.first_line_indent = Cm(0)
        r = p.add_run(line)
        set_run_font(r, size=12)

    doc.add_page_break()

    add_heading_custom(doc, "1. Giới thiệu", 1)
    add_paragraph(
        doc,
        "Ứng dụng AGB-UAV ước lượng sinh khối trên mặt đất (Aboveground Biomass, AGB) "
        "của rừng từ một tấm ảnh orthomosaic UAV kênh Đỏ–Lục–Lam kèm kênh Alpha, "
        "không sử dụng LiDAR, mô hình số độ cao tán (CHM) hay ảnh đa phổ có kênh cận hồng ngoại. "
        "Đây là lựa chọn thay thế khi thiếu dữ liệu độ cao tán: tán được nhận dạng bằng chỉ số "
        "thực vật RGB, độ che phủ phân đoạn (fractional canopy cover, FCC) được tổng hợp "
        "trên lưới 2 m × 2 m, rồi chuyển sang AGB theo mô hình hàm mũ dựa trên độ che phủ.",
    )
    add_paragraph(
        doc,
        "Hệ thống gồm hai khối. Khối tính toán (Biomass_analysis.py) đọc orthomosaic, "
        "phân loại tán, ước lượng AGB và ghi các lớp GeoTIFF cùng bảng thống kê. "
        "Khối hiển thị là máy chủ web nội bộ (cổng 8765) cho phép xem chồng lớp bản đồ, "
        "đọc giá trị pixel, vẽ polygon để thống kê tổng AGB theo vùng, đo chiều dài, "
        "và chạy lại mô hình từ giao diện.",
    )

    add_heading_custom(doc, "2. Mục tiêu và phạm vi", 1)
    add_paragraph(
        doc,
        "Mục tiêu là lập bản đồ mật độ AGB (Mg/ha) và tổng trữ lượng (tấn) trên phạm vi bay chụp, "
        "kèm các lớp phụ trợ: độ che phủ tán, chỉ số Excess Green (ExG), VARI, "
        "và tỷ lệ diện tích tán lớn trên ô 1 ha. Phạm vi địa lý minh họa khoảng "
        "927 m × 832 m (khoảng 77 ha khung ảnh; 54,75 ha pixel hợp lệ), tọa độ gốc "
        "105,677041°E, 21,126801°N, hệ quy chiếu EPSG:4326 (WGS 84).",
    )
    add_paragraph(
        doc,
        "Phạm vi kỹ thuật: xử lý ảnh UAV RGB+Alpha độ phân giải centimet, tổng hợp đa tỷ lệ "
        "(0,5 m cho tán lớn; 2 m cho AGB; 100 m cho lưới 1 ha), thống kê không gian theo polygon "
        "trên lớp AGB. Ứng dụng không thay thế kiểm kê rừng bằng ô mẫu hiện trường; "
        "các hệ số mô hình cần hiệu chỉnh nếu có số liệu ô tiêu chuẩn địa phương.",
    )

    add_heading_custom(doc, "3. Dữ liệu sử dụng", 1)
    add_heading_custom(doc, "3.1. Dữ liệu đầu vào", 2)
    add_paragraph(
        doc,
        "Dữ liệu chính là file data/orthomosaic.tif: GeoTIFF UAV RGB cộng kênh Alpha, "
        "nén theo tile 256 × 256 pixel. Kênh Alpha phân biệt vùng có ảnh (alpha > 0) "
        "và nền trong suốt ngoài hành lang bay. Kích thước pixel gốc khoảng 3,42 cm. "
        "Siêu dữ liệu địa lý được đọc từ thẻ GeoTIFF (ModelPixelScaleTag, ModelTiepointTag, GeoKeys) "
        "và giữ nguyên hệ WGS 84 khi ghi sản phẩm.",
    )
    add_table(
        doc,
        ["Thông số", "Giá trị"],
        [
            ["Định dạng", "GeoTIFF, RGB + Alpha"],
            ["Hệ tọa độ", "EPSG:4326 (WGS 84)"],
            ["Kích thước pixel gốc", "≈ 3,42 cm"],
            ["Phạm vi Đông–Tây", "927,04 m"],
            ["Phạm vi Bắc–Nam", "832,40 m"],
            ["Tọa độ gốc (lon, lat)", "105,677041°E; 21,126801°N"],
            ["Số tile đã xử lý (lần chạy minh họa)", "7.316"],
        ],
    )
    add_paragraph(
        doc,
        "Ứng dụng không dùng ảnh Planet BGR+NIR, mô hình U-Net chiều cao tán, hay CHM LiDAR "
        "(các đầu vào của pipeline DeepLiDARPlanet gốc). Nền bản đồ trên giao diện lấy từ "
        "các máy chủ OpenStreetMap công cộng (OSM.de, OSM France, OpenTopoMap), lưu cache cục bộ.",
        first_line=True,
    )

    add_heading_custom(doc, "3.2. Dữ liệu đầu ra", 2)
    add_paragraph(
        doc,
        "Kết quả ghi vào thư mục output/, gồm lớp raster, bảng CSV và ảnh xem trước.",
    )
    add_table(
        doc,
        ["Tệp", "Nội dung", "Đơn vị / ghi chú"],
        [
            ["agb_Mg_ha_2m.tif", "Mật độ AGB lưới 2 m", "Mg/ha (float32)"],
            ["canopy_cover_2m.tif", "Độ che phủ tán FCC", "%"],
            ["exg_2m.tif", "ExG trung bình ô 2 m", "không thứ nguyên"],
            ["vari_2m.tif", "VARI trung bình ô 2 m", "không thứ nguyên"],
            ["agb_Mg_ha_1ha.tif", "AGB gộp ô 1 ha", "Mg/ha"],
            ["canopy_cover_1ha.tif", "Che phủ gộp ô 1 ha", "%"],
            ["large_crown_area_pct_1ha.tif", "Tỷ lệ tán lớn (≥ 100 m²)", "%"],
            ["biomass_summary.csv", "Chỉ số toàn cảnh", "ha, Mg/ha, tấn"],
            ["biomass_1ha.csv", "Bảng từng ô 1 ha", "hàng, cột, lon, lat, AGB"],
        ],
    )

    add_heading_custom(doc, "4. Phương pháp", 1)
    add_heading_custom(doc, "4.1. Định hướng phương pháp", 2)
    add_paragraph(
        doc,
        "Khi không có chiều cao tán, AGB được ước từ cấu trúc quang phổ RGB và tỷ lệ che phủ. "
        "Luồng xử lý: (1) chuẩn hóa RGB về [0, 1]; (2) tính ExG và VARI trên pixel centimet; "
        "(3) tạo mặt nạ tán; (4) tổng hợp FCC, ExG, VARI lên lưới 2 m; "
        "(5) áp mô hình AGB = f(FCC, VARI); (6) gộp lên 1 ha và tính chỉ số tán lớn; "
        "(7) quy đổi trữ lượng theo từng pixel 2 m rồi tổng hợp.",
    )

    add_heading_custom(doc, "4.2. Chỉ số thực vật RGB", 2)
    add_paragraph(
        doc,
        "Excess Green (Woebbecke và cộng sự) nhấn mạnh kênh lục so với đỏ và lam, "
        "thường dùng tách thực vật trên ảnh RGB:",
    )
    add_formula(doc, "ExG = 2G − R − B")
    add_paragraph(
        doc,
        "Visible Atmospherically Resistant Index (Gitelson và cộng sự) giảm ảnh hưởng "
        "bầu khí quyển trong dải nhìn thấy:",
    )
    add_formula(doc, "VARI = (G − R) / (G + R − B)")
    add_paragraph(
        doc,
        "Mẫu số gần 0 được gán VARI = 0 để tránh chia cho không. Hai chỉ số được tính "
        "trên pixel gốc, chỉ với vị trí alpha > 0.",
        first_line=True,
    )

    add_heading_custom(doc, "4.3. Phân loại tán", 2)
    add_paragraph(
        doc,
        "Pixel được xem là tán khi đồng thời thỏa: nằm trong vùng ảnh hợp lệ, "
        "ExG > 0,16 và VARI > 0,08. Ngưỡng được tinh chỉnh trên các tile của orthomosaic hiện tại. "
        "FCC của ô 2 m là tỷ lệ pixel tán trên tổng pixel hợp lệ trong ô đó.",
    )
    add_formula(doc, "FCC = N_tán / N_hợp_lệ    (0 ≤ FCC ≤ 1)")

    add_heading_custom(doc, "4.4. Mô hình AGB theo độ che phủ", 2)
    add_paragraph(
        doc,
        "Rừng thường xanh/hỗn giao miền Bắc Việt Nam thường có AGB tán kín khoảng 150–300 Mg/ha "
        "(tham chiếu dải kiểm kê VNFOREST / UN-REDD). Khi không có CHM, ứng dụng dùng dạng hàm mũ "
        "theo FCC, nhân thêm hệ số vigor từ VARI:",
    )
    add_formula(doc, "AGB (Mg/ha) = 240 × FCC^1,48 × vigor(VARI)")
    add_paragraph(
        doc,
        "Hệ số 240 Mg/ha là AGB quy ước khi tán kín (FCC = 1) và vigor trung bình–cao. "
        "Số mũ 1,48 làm AGB tăng chậm hơn tuyến tính khi FCC thấp (đất trống, tán thưa). "
        "Vigor ánh xạ VARI từ khoảng [0,05; 0,40] sang [0,80; 1,20]: tán khỏe (VARI cao) "
        "tăng nhẹ AGB, tán yếu giảm nhẹ. Cần hiệu chỉnh 240 và 1,48 khi có ô mẫu hiện trường.",
    )
    add_formula(doc, "vigor = 0,80 + 0,40 × clip((VARI − 0,05) / 0,35, 0, 1)")

    add_heading_custom(doc, "4.5. Carbon", 2)
    add_paragraph(
        doc,
        "Carbon sinh khối trên mặt đất lấy theo IPCC: C = 0,47 × AGB. "
        "Đây là hệ số chuyển đổi khối lượng khô, không phải carbon dioxide tương đương.",
    )

    add_heading_custom(doc, "5. Thuật toán chi tiết", 1)
    add_heading_custom(doc, "5.1. Đọc ảnh theo tile", 2)
    add_paragraph(
        doc,
        "Orthomosaic lớn được đọc từng tile 256 × 256 bằng tifffile (giải nén imagecodecs), "
        "tránh nạp cả ảnh vào bộ nhớ. Mỗi tile cắt đúng biên ảnh, bỏ tile toàn alpha = 0.",
    )

    add_heading_custom(doc, "5.2. Tổng hợp đa tỷ lệ", 2)
    add_paragraph(
        doc,
        "Tọa độ pixel centimet được đổi sang mét (gần đúng WGS 84 tại vĩ độ cảnh), "
        "rồi gán vào ô lưới. Lưới 2 m nhận tổng tán, tổng pixel hợp lệ, tổng ExG và VARI "
        "có trọng số hợp lệ (np.add.at). Lưới 0,5 m nhận mặt nạ tán/hợp lệ bằng np.maximum.at "
        "phục vụ phân tích tán lớn. Sau khi quét hết tile:",
    )
    add_formula(doc, "ExG_2m = Σ(ExG × valid) / Σ valid")
    add_formula(doc, "VARI_2m = Σ(VARI × valid) / Σ valid")
    add_paragraph(
        doc,
        "Ô không có pixel hợp lệ nhận NaN và không tham gia AGB.",
        first_line=True,
    )

    add_heading_custom(doc, "5.3. Trữ lượng theo pixel rồi quy đổi hecta", 2)
    add_paragraph(
        doc,
        "Raster agb_Mg_ha_2m.tif lưu mật độ (Mg/ha), không phải tấn trên từng ô. "
        "Mỗi pixel sản phẩm có kích thước 2 m × 2 m = 4 m² = 0,0004 ha. "
        "Thống kê tổng và trung bình được tính theo pixel trước:",
    )
    add_formula(doc, "kg/pixel = (Mg/ha) × 0,4")
    add_paragraph(
        doc,
        "vì 0,0004 ha × 1000 kg/Mg = 0,4 kg trên mỗi Mg/ha. Sau đó:",
        first_line=True,
    )
    add_formula(doc, "Tổng AGB (tấn) = (Σ kg/pixel) / 1000")
    add_formula(doc, "AGB TB (Mg/ha) = (kg/pixel trung bình) / 0,4")
    add_formula(doc, "Diện tích (ha) = N_pixel × 0,0004")
    add_paragraph(
        doc,
        "Ví dụ: 240 Mg/ha tương ứng 96 kg trên một ô 2 × 2 m. "
        "Toàn cảnh minh họa: 136.881 pixel hợp lệ, 54,752 ha, AGB trung bình 124,77 Mg/ha, "
        "tổng 6.831,59 tấn, carbon 3.210,85 tấn C.",
        first_line=True,
    )

    add_heading_custom(doc, "5.4. Gộp ô 1 ha", 2)
    add_paragraph(
        doc,
        "Lưới 100 m × 100 m (1 ha danh nghĩa) lấy trung bình có trọng số số pixel hợp lệ "
        "của FCC và của trữ lượng từng ô 2 m, rồi quy đổi lại Mg/ha. "
        "Bảng biomass_1ha.csv lưu hàng, cột, kinh độ, vĩ độ tâm ô, che phủ, AGB và tỷ lệ tán lớn.",
    )

    add_heading_custom(doc, "5.5. Diện tích tán lớn", 2)
    add_paragraph(
        doc,
        "Trên lưới 0,5 m, các pixel tán được dán nhãn liên thông 8 hướng (scipy.ndimage.label). "
        "Đám có diện tích ≥ 100 m² được coi là tán lớn. Tỷ lệ diện tích tán lớn trên mỗi ô 1 ha "
        "là số ô 0,5 m thuộc đám lớn chia cho số ô hợp lệ trong khối 1 ha. "
        "Đây là chỉ thị cấu trúc tán khi không có chiều cao cây.",
    )

    add_heading_custom(doc, "5.6. Thống kê AGB theo polygon", 2)
    add_paragraph(
        doc,
        "Trên tab AGB – Sinh khối, người dùng vẽ một đa giác (WGS 84). Máy chủ "
        "chuyển polygon sang không gian raster, tạo mặt nạ pixel (tâm pixel nằm trong đa giác), "
        "đổi từng giá trị Mg/ha sang kg/pixel, rồi tính tổng, trung bình và quy đổi Mg/ha "
        "như mục 5.3. Công cụ đo chiều dài dùng công thức haversine trên mặt cầu 6.371 km.",
    )

    add_heading_custom(doc, "6. Kỹ thuật hiện thực", 1)
    add_heading_custom(doc, "6.1. Địa lý và mét trên một độ", 2)
    add_paragraph(
        doc,
        "Vì ảnh ở WGS 84, kích thước mét của pixel gốc được xấp xỉ tại vĩ độ cảnh:",
    )
    add_formula(doc, "m/°lat ≈ 111132,92 − 559,82 cos(2φ) + 1,175 cos(4φ)")
    add_formula(doc, "m/°lon ≈ 111412,84 cos(φ) − 93,5 cos(3φ)")
    add_paragraph(
        doc,
        "Lưới 2 m và 1 ha được ghi GeoTIFF bằng bước lưới đổi ngược ra độ, kèm world file (.tfw). "
        "Thống kê trữ lượng dùng đúng 4 m²/pixel (lưới thiết kế), không lấy lại diện tích từ xấp xỉ độ.",
        first_line=True,
    )

    add_heading_custom(doc, "6.2. Máy chủ bản đồ", 2)
    add_paragraph(
        doc,
        "viewer/server.py chạy ThreadingHTTPServer, lắng nghe 0.0.0.0:8765. "
        "Lớp overlay PNG do rasterio cắt cửa sổ theo khung nhìn Leaflet, tô màu YlGn hoặc RdYlGn. "
        "Orthomosaic được lấy theo cửa sổ để tránh tải cả file. "
        "Một instance chiếm cổng; nếu đã chạy, launcher chỉ mở trình duyệt.",
    )

    add_heading_custom(doc, "6.3. Giao diện", 2)
    add_paragraph(
        doc,
        "Giao diện (HTML/CSS/JavaScript, Leaflet) chồng OpenStreetMap với GeoTIFF. "
        "Tab lớp: Orthomosaic, AGB, độ che phủ, VARI, ExG. "
        "Chỉ tab AGB có vẽ vùng (polygon đỏ) và đo chiều dài (đường xanh). "
        "Lưới 1 ha và bảng CSV cho phép chọn ô và nhảy bản đồ. "
        "Nút Tính sinh khối gọi lại Biomass_analysis.py trong tiến trình nền.",
    )

    add_heading_custom(doc, "6.4. Phần mềm", 2)
    add_table(
        doc,
        ["Thành phần", "Vai trò"],
        [
            ["Python 3.13", "Ngôn ngữ chạy mô hình và máy chủ"],
            ["NumPy / SciPy", "Lưới, tổng hợp, dán nhãn liên thông"],
            ["tifffile, imagecodecs", "Đọc/ghi GeoTIFF tiled"],
            ["rasterio, Pillow", "Cửa sổ raster, PNG overlay, mặt nạ polygon"],
            ["matplotlib", "Ảnh preview tĩnh"],
            ["Leaflet", "Bản đồ web, vẽ và đo"],
        ],
    )

    add_heading_custom(doc, "7. Kết quả minh họa (lần chạy hiện tại)", 1)
    add_table(
        doc,
        ["Chỉ số", "Giá trị"],
        [
            ["Diện tích hợp lệ", "54,752 ha"],
            ["Diện tích có tán", "29,951 ha"],
            ["Che phủ tán trung bình", "54,7 %"],
            ["AGB trung bình", "124,77 Mg/ha"],
            ["AGB nhỏ nhất / lớn nhất", "0,0 / 288,0 Mg/ha"],
            ["Tổng AGB", "6.831,59 tấn"],
            ["Carbon (IPCC 0,47)", "3.210,85 tấn C"],
            ["Thời gian xử lý (minh họa)", "144,7 giây"],
        ],
    )
    add_paragraph(
        doc,
        "AGB lớn nhất 288 Mg/ha xuất hiện khi FCC gần 1 và vigor > 1 (VARI cao): "
        "240 × 1^1,48 × 1,20 = 288. Giá trị 0 ứng với ô không có tán.",
        first_line=True,
    )

    add_heading_custom(doc, "8. Hạn chế và khuyến nghị", 1)
    add_paragraph(
        doc,
        "Mô hình không quan sát chiều cao, đường kính hay loài cây; AGB suy từ che phủ và độ xanh RGB, "
        "dễ lệch ở rừng thưa, rừng trồng đồng đều, bóng đổ mạnh, hay thời điểm phenology khác. "
        "Ngưỡng ExG/VARI phụ thuộc điều kiện chiếu sáng của orthomosaic. "
        "Hệ số 240 Mg/ha và số mũ 1,48 mang tính khu vực, chưa phải hồi quy từ ô mẫu của cảnh bay này. "
        "Diện tích 1 ha là ô 100 m trên mặt đất xấp xỉ, không phải ranh giới tiểu khu hành chính.",
    )
    add_paragraph(
        doc,
        "Khuyến nghị: thu thập ô mẫu AGB hiện trường trong cùng khu, hiệu chỉnh AGB_CLOSED_MG_HA "
        "và COVER_EXPONENT; nếu có CHM quang trắc hoặc LiDAR thì thay FCC bằng mô hình "
        "dựa trên chiều cao/thể tích tán; kiểm tra ngưỡng ExG/VARI khi đổi cảm biến hoặc mùa bay.",
    )

    add_heading_custom(doc, "9. Kết luận", 1)
    add_paragraph(
        doc,
        "AGB-UAV là quy trình khép kín từ orthomosaic UAV RGB đến bản đồ AGB 2 m, "
        "bảng 1 ha và công cụ thống kê theo vùng trên web. "
        "Thuật toán cốt lõi là mặt nạ tán ExG–VARI, FCC trên lưới 2 m, "
        "mô hình AGB = 240 × FCC^1,48 × vigor(VARI), và quy đổi trữ lượng theo từng pixel 4 m². "
        "Kết quả phục vụ trực quan hóa và ước lượng sơ bộ; độ tin cậy tăng khi được hiệu chỉnh bằng số liệu ô tiêu chuẩn.",
    )

    add_heading_custom(doc, "Tài liệu tham chiếu (cơ sở phương pháp)", 1)
    refs = [
        "Gitelson, A.A. et al. (2002). Vegetation and soil lines in visible spectral space: "
        "a concept and formula for differential vegetation index. International Journal of Remote Sensing.",
        "Woebbecke, D.M. et al. (1995). Color indices for weed identification under various soil, residue, and lighting conditions. Transactions of the ASAE.",
        "IPCC (2006/2019). Guidelines for National Greenhouse Gas Inventories, Volume 4: Agriculture, Forestry and Other Land Use — hệ số carbon 0,47.",
        "VNFOREST / UN-REDD: dải AGB rừng thường xanh, hỗn giao miền Bắc Việt Nam (tham chiếu khoảng 150–300 Mg/ha khi tán kín).",
        "Mã nguồn nội bộ: Modelling/Biomass_analysis.py; viewer/raster.py; viewer/server.py.",
    ]
    for i, ref in enumerate(refs, start=1):
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Cm(0.75)
        p.paragraph_format.first_line_indent = Cm(-0.75)
        p.paragraph_format.space_after = Pt(6)
        p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
        run = p.add_run(f"[{i}] {ref}")
        set_run_font(run, size=11)

    footer = section.footer
    fp = footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = fp.add_run("AGB-UAV — Báo cáo kỹ thuật thuật toán và dữ liệu — Tài liệu nội bộ")
    set_run_font(run, size=9, italic=True, color=RGBColor(0x66, 0x66, 0x66))

    doc.save(OUT)
    print(OUT)


if __name__ == "__main__":
    build()
