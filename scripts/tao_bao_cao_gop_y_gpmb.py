from datetime import date
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor


OUTPUT = Path(__file__).resolve().parents[1] / "Bao_cao_gop_y_ung_dung_GPMB.docx"


def set_cell_shading(cell, fill):
    properties = cell._tc.get_or_add_tcPr()
    shading = properties.find(qn("w:shd"))
    if shading is None:
        shading = OxmlElement("w:shd")
        properties.append(shading)
    shading.set(qn("w:fill"), fill)


def set_cell_text(cell, text, bold=False, color=None, size=9):
    cell.text = ""
    paragraph = cell.paragraphs[0]
    paragraph.paragraph_format.space_after = Pt(0)
    run = paragraph.add_run(text)
    run.bold = bold
    run.font.size = Pt(size)
    if color:
        run.font.color.rgb = RGBColor(*color)
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER


def set_cell_margins(cell, top=90, start=100, bottom=90, end=100):
    properties = cell._tc.get_or_add_tcPr()
    margins = properties.first_child_found_in("w:tcMar")
    if margins is None:
        margins = OxmlElement("w:tcMar")
        properties.append(margins)
    for margin, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = margins.find(qn(f"w:{margin}"))
        if node is None:
            node = OxmlElement(f"w:{margin}")
            margins.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def add_heading(document, text, level=1):
    paragraph = document.add_paragraph()
    paragraph.paragraph_format.space_before = Pt(12 if level == 1 else 8)
    paragraph.paragraph_format.space_after = Pt(5)
    run = paragraph.add_run(text)
    run.bold = True
    run.font.name = "Aptos Display"
    run.font.size = Pt(15 if level == 1 else 11.5)
    run.font.color.rgb = RGBColor(31, 78, 121) if level == 1 else RGBColor(55, 55, 55)
    return paragraph


def add_bullet(document, text, level=0):
    paragraph = document.add_paragraph(style="List Bullet" if level == 0 else "List Bullet 2")
    paragraph.paragraph_format.space_after = Pt(3)
    paragraph.paragraph_format.left_indent = Cm(0.65 + level * 0.4)
    paragraph.add_run(text)
    return paragraph


def add_callout(document, title, text, fill="EAF2F8"):
    table = document.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    cell = table.cell(0, 0)
    cell.width = Cm(16.3)
    set_cell_shading(cell, fill)
    set_cell_margins(cell, top=130, start=160, bottom=130, end=160)
    paragraph = cell.paragraphs[0]
    paragraph.paragraph_format.space_after = Pt(2)
    title_run = paragraph.add_run(title)
    title_run.bold = True
    title_run.font.color.rgb = RGBColor(31, 78, 121)
    body = cell.add_paragraph(text)
    body.paragraph_format.space_after = Pt(0)
    document.add_paragraph().paragraph_format.space_after = Pt(0)


def add_findings_table(document):
    rows = [
        ("Cao", "Định dạng và quy đổi số liệu", "Dashboard hiển thị “1.235.793.135tỷ”; chi tiết dự án hiển thị “1.235.777.990 tỷ đồng”. Đơn vị và quy mô số liệu cần được chuẩn hóa, đồng thời kiểm tra khả năng nhập nhầm đơn vị.", "Chuẩn hóa quy ước nhập/lưu/hiển thị: số tiền có dấu phân cách, đơn vị tách riêng; diện tích thống nhất m² hoặc ha; thêm tooltip quy đổi và kiểm tra tổng.", "P0"),
        ("Cao", "Kiểm soát tài khoản demo và mật khẩu", "Trang đăng nhập công khai thông tin tài khoản demo và mật khẩu. Đây là rủi ro nếu môi trường này có dữ liệu thật hoặc dùng chung với môi trường vận hành.", "Tách hoàn toàn dữ liệu demo khỏi production; đổi hoặc vô hiệu hóa mật khẩu demo khi triển khai; yêu cầu đổi mật khẩu lần đầu và bổ sung MFA cho nhóm quản trị.", "P0"),
        ("Cao", "Kiểm tra tính nhất quán dữ liệu", "Chi tiết dự án “abc” có dữ liệu thử nghiệm như mô tả “test”, số quyết định “1234/NNN”, ngày hiển thị 2/9/2026 và các giá trị vốn rất lớn. Cần phân biệt dữ liệu mẫu với dữ liệu nghiệp vụ.", "Có cờ dữ liệu mẫu, quy trình làm sạch trước nghiệm thu; ràng buộc định dạng số quyết định, ngày, tiền và kiểm tra miền giá trị.", "P0"),
        ("Trung bình", "Thông báo lỗi và trạng thái tải", "Khi mở chi tiết dự án, giao diện hiển thị “Đang tải thông tin dự án...” trước khi hoàn tất; kiểm tra trình duyệt ghi nhận một tài nguyên trả về 404.", "Bổ sung trạng thái loading có giới hạn thời gian, thông báo lỗi thân thiện, nút thử lại và giám sát các tài nguyên 4xx/5xx trước khi phát hành.", "P1"),
        ("Trung bình", "Khả năng quét và lọc dữ liệu", "Dashboard nhiều chỉ số, biểu đồ và bảng trên cùng một màn hình. Bảng có nhiều cột, tên dự án dài, dễ bị cắt trên màn hình nhỏ.", "Cho phép chọn cột, ghim cột dự án, xem chi tiết bằng drawer, lọc theo khoảng tiến độ/thời gian/đơn vị; bảo đảm cuộn ngang có chỉ báo rõ ràng.", "P1"),
        ("Trung bình", "Bản đồ và chú giải", "Trang chi tiết có bản đồ Leaflet, các lớp dữ liệu và nút biểu tượng; một số nút chỉ nhận diện được khi rê chuột, chưa thể hiện rõ trạng thái lớp đang bật.", "Bổ sung chú giải, tên/tooltip thống nhất, trạng thái bật/tắt rõ bằng màu và khả năng tắt từng lớp; cung cấp nút đưa bản đồ về phạm vi dự án.", "P1"),
        ("Trung bình", "Trải nghiệm biểu mẫu", "Nên kiểm tra thống nhất cách nhập ngày, tiền, diện tích, số hộ và tệp bản đồ; các trường dữ liệu nghiệp vụ cần thông báo lỗi ngay tại trường.", "Dùng input theo kiểu dữ liệu, định dạng mẫu, kiểm tra trước khi lưu, hiển thị lỗi cạnh trường và cảnh báo khi rời biểu mẫu chưa lưu.", "P1"),
        ("Thấp", "Thuật ngữ và viết hoa", "Menu dùng cả “Vướng Mắc”, “Upload dữ liệu bản đồ”, “Quản lý upload ảnh”; cách viết chưa đồng nhất giữa tiếng Việt và tiếng Anh.", "Chuẩn hóa bảng thuật ngữ và nhãn giao diện, ưu tiên tiếng Việt: “Tải ảnh lên”, “Tải dữ liệu bản đồ lên”, “Vướng mắc”.", "P2"),
        ("Thấp", "Khả năng tiếp cận", "Nên kiểm tra tương phản, kích thước vùng bấm, thứ tự bàn phím, nhãn cho nút biểu tượng và thông báo lỗi cho người dùng dùng trình đọc màn hình.", "Thực hiện checklist WCAG 2.1 AA tối thiểu cho đăng nhập, sidebar, bảng, biểu mẫu và bản đồ.", "P2"),
    ]
    table = document.add_table(rows=1, cols=5)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    widths = [Cm(1.8), Cm(3.0), Cm(5.0), Cm(5.2), Cm(1.3)]
    headers = ["Mức độ", "Hạng mục", "Góp ý/hiện trạng", "Đề xuất xử lý", "Ưu tiên"]
    for index, header in enumerate(headers):
        cell = table.rows[0].cells[index]
        cell.width = widths[index]
        set_cell_text(cell, header, bold=True, color=(255, 255, 255), size=8.5)
        set_cell_shading(cell, "1F4E79")
        set_cell_margins(cell)
    for row_index, row in enumerate(rows, start=1):
        cells = table.add_row().cells
        for index, value in enumerate(row):
            cells[index].width = widths[index]
            set_cell_text(cells[index], value, bold=index in (0, 4), size=8.2)
            set_cell_margins(cells[index])
            set_cell_shading(cells[index], "F4F7FA" if row_index % 2 == 0 else "FFFFFF")
            if index == 4:
                color = {"P0": "C00000", "P1": "BF9000", "P2": "548235"}[value]
                cells[index].paragraphs[0].runs[0].font.color.rgb = RGBColor.from_string(color)
    document.add_paragraph().paragraph_format.space_after = Pt(0)


def add_checklist(document):
    table = document.add_table(rows=1, cols=3)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    headers = ["Nhóm kiểm tra", "Tiêu chí nghiệm thu đề xuất", "Kết quả"]
    widths = [Cm(3.3), Cm(10.8), Cm(2.2)]
    for index, header in enumerate(headers):
        cell = table.rows[0].cells[index]
        cell.width = widths[index]
        set_cell_text(cell, header, bold=True, color=(255, 255, 255), size=8.5)
        set_cell_shading(cell, "5B9BD5")
    items = [
        ("Dữ liệu", "Các tổng số trên dashboard khớp với tổng ở danh sách và chi tiết; đơn vị tiền/diện tích được hiển thị nhất quán.", "Đạt một phần: trang chi tiết dự án mã 2 đọc được, nhưng các màn hình đã kiểm tra trước đó còn lỗi quy ước đơn vị và dữ liệu mẫu."),
        ("Phân quyền", "Mỗi vai trò chỉ nhìn thấy và thao tác đúng phạm vi; thao tác duyệt, sửa, xóa đều có kiểm tra quyền phía máy chủ.", "Chưa đủ bằng chứng: mới kiểm tra vai trò Quản trị đơn vị, chưa có bộ ca kiểm thử đối chiếu các vai trò."),
        ("Tệp bản đồ", "Tải lên đúng định dạng, giới hạn dung lượng, hệ tọa độ; có thông báo lỗi và khả năng xem lại lớp đã tải.", "Chưa kiểm tra: cần tệp mẫu hợp lệ/không hợp lệ và quyền truy cập chức năng upload."),
        ("Hiệu năng", "Dashboard và chi tiết dự án hiển thị trong ngưỡng thống nhất khi có dữ liệu lớn; không có request 404/5xx trong luồng chính.", "Đạt sơ bộ: tải lại trang chi tiết mã 2 không ghi nhận 4xx/5xx hoặc lỗi console; chưa kiểm thử tải dữ liệu lớn."),
        ("Bảo mật", "Không để lộ mật khẩu mẫu; phiên đăng nhập, đăng xuất, hết hạn phiên và nhật ký thao tác được kiểm tra.", "Không đạt: trang đăng nhập đang hiển thị tài khoản và mật khẩu demo; các nội dung phiên, hết hạn và nhật ký chưa kiểm tra đầy đủ."),
        ("Responsive", "Đăng nhập, dashboard, bảng và bản đồ sử dụng được ở màn hình laptop và điện thoại; không che khuất nút thao tác.", "Đạt sơ bộ: viewport 390px không phát hiện tràn ngang; chưa thay thế cho kiểm thử thao tác trực quan trên thiết bị thật."),
    ]
    for row_index, row in enumerate(items, start=1):
        cells = table.add_row().cells
        for index, value in enumerate(row):
            cells[index].width = widths[index]
            set_cell_text(cells[index], value, bold=index == 0, size=8.5)
            set_cell_shading(cells[index], "F4F7FA" if row_index % 2 == 0 else "FFFFFF")
            set_cell_margins(cells[index])
    document.add_paragraph().paragraph_format.space_after = Pt(0)


def build_document():
    document = Document()
    section = document.sections[0]
    section.top_margin = Cm(1.7)
    section.bottom_margin = Cm(1.6)
    section.left_margin = Cm(1.7)
    section.right_margin = Cm(1.7)

    normal = document.styles["Normal"]
    normal.font.name = "Aptos"
    normal.font.size = Pt(10)
    normal.paragraph_format.space_after = Pt(5)
    normal.paragraph_format.line_spacing = 1.08

    header = section.header.paragraphs[0]
    header.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    header_run = header.add_run("BÁO CÁO GÓP Ý  |  08/09/2026")
    header_run.font.size = Pt(8)
    header_run.font.color.rgb = RGBColor(100, 100, 100)

    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer_run = footer.add_run("Tài liệu góp ý phục vụ hoàn thiện ứng dụng quản lý GPMB")
    footer_run.font.size = Pt(8)
    footer_run.font.color.rgb = RGBColor(100, 100, 100)

    title = document.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.paragraph_format.space_before = Pt(22)
    title.paragraph_format.space_after = Pt(4)
    run = title.add_run("BÁO CÁO GÓP Ý VỀ ỨNG DỤNG")
    run.bold = True
    run.font.name = "Aptos Display"
    run.font.size = Pt(21)
    run.font.color.rgb = RGBColor(31, 78, 121)

    subtitle = document.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle.paragraph_format.space_after = Pt(18)
    run = subtitle.add_run("Hệ thống quản trị Giải phóng mặt bằng")
    run.bold = True
    run.font.size = Pt(14)
    run.font.color.rgb = RGBColor(89, 89, 89)

    info = document.add_table(rows=4, cols=2)
    info.alignment = WD_TABLE_ALIGNMENT.CENTER
    info.autofit = False
    info_data = [
        ("Ứng dụng", "Quản lý các dự án Giải phóng mặt bằng"),
        ("Địa chỉ kiểm tra", "https://gpmb.vdcdninhbinh.vn/login"),
        ("Phạm vi", "Đăng nhập demo, dashboard, danh sách dự án, chi tiết dự án và bản đồ"),
        ("Vai trò sử dụng", "Quản trị đơn vị (tài khoản demo hiển thị trên trang đăng nhập)"),
    ]
    for row, (key, value) in zip(info.rows, info_data):
        row.cells[0].width = Cm(4.0)
        row.cells[1].width = Cm(12.3)
        set_cell_text(row.cells[0], key, bold=True, color=(31, 78, 121), size=9)
        set_cell_text(row.cells[1], value, size=9)
        set_cell_shading(row.cells[0], "EAF2F8")
        set_cell_shading(row.cells[1], "F8FBFD")
        set_cell_margins(row.cells[0])
        set_cell_margins(row.cells[1])
    document.add_paragraph()

    add_callout(
        document,
        "Tóm tắt đánh giá",
        "Ứng dụng đã hình thành được luồng nghiệp vụ chính gồm tổng quan dự án, quản lý hồ sơ, phê duyệt, quản lý hộ dân và dữ liệu bản đồ. Ưu tiên trước khi nghiệm thu/vận hành chính thức là chuẩn hóa dữ liệu hiển thị, khóa tài khoản demo, hoàn thiện thông báo lỗi và rà soát phân quyền.",
    )

    add_heading(document, "1. Nhận xét tổng quan")
    add_bullet(document, "Điểm tích cực: giao diện có cấu trúc điều hướng rõ, dashboard tập trung các chỉ số chính và có chức năng lọc/xuất báo cáo.")
    add_bullet(document, "Điểm tích cực: trang chi tiết dự án kết hợp thông tin hồ sơ, tiến độ, số hộ bị ảnh hưởng và bản đồ trong cùng một luồng làm việc.")
    add_bullet(document, "Cần cải thiện: dữ liệu mẫu và định dạng đơn vị đang làm giảm độ tin cậy của báo cáo; người dùng khó biết số liệu nào là số liệu nghiệp vụ chính thức.")
    add_bullet(document, "Cần cải thiện: một số thao tác bản đồ và nút biểu tượng chưa có chú giải trực quan; khả năng sử dụng trên màn hình hẹp cần được kiểm tra riêng.")

    add_heading(document, "2. Góp ý chi tiết và mức độ ưu tiên")
    add_findings_table(document)

    add_heading(document, "3. Đề xuất thứ tự xử lý")
    add_bullet(document, "P0 - Trước khi đưa vào vận hành: chuẩn hóa đơn vị và số liệu; loại bỏ hoặc khóa tài khoản demo; làm sạch dữ liệu thử nghiệm; rà soát quyền sửa/xóa/duyệt.")
    add_bullet(document, "P1 - Trong đợt hoàn thiện kế tiếp: sửa tài nguyên 404; cải thiện loading/error; tối ưu bảng, bộ lọc và chú giải bản đồ; tăng kiểm tra dữ liệu đầu vào.")
    add_bullet(document, "P2 - Trong đợt chuẩn hóa trải nghiệm: thống nhất thuật ngữ, bổ sung khả năng tiếp cận và kiểm thử responsive trên các thiết bị phổ biến.")

    add_heading(document, "4. Checklist nghiệm thu đề xuất")
    add_checklist(document)
    add_callout(
        document,
        "Kết quả kiểm tra nhanh ngày 08/09/2026",
        "Đã kiểm tra trực tiếp trang chi tiết dự án mã 2 bằng tài khoản demo Quản trị đơn vị. Kết quả: không ghi nhận phản hồi HTTP 4xx/5xx hoặc lỗi console khi tải lại; viewport rộng 390px không bị tràn ngang. Chưa thể kết luận đạt về phân quyền, upload dữ liệu bản đồ, hết hạn phiên và kiểm thử tải vì chưa có bộ ca kiểm thử và dữ liệu tương ứng.",
        fill="FFF2CC",
    )

    add_heading(document, "5. Kết luận")
    paragraph = document.add_paragraph()
    paragraph.add_run("Kiến nghị: ").bold = True
    paragraph.add_run("tiếp tục hoàn thiện ứng dụng theo các mục P0 trước khi sử dụng với dữ liệu chính thức. Sau khi xử lý P0, nên thực hiện một vòng kiểm thử nghiệp vụ có dữ liệu thật đã ẩn danh, kiểm thử phân quyền theo từng vai trò và kiểm thử tải với số lượng dự án/hộ dân lớn hơn dữ liệu demo.")

    note = document.add_paragraph()
    note.paragraph_format.space_before = Pt(10)
    note_run = note.add_run("Lưu ý về phạm vi: Báo cáo này là góp ý nhanh dựa trên việc kiểm tra giao diện và các luồng có thể truy cập bằng tài khoản demo; chưa thay thế cho kiểm thử bảo mật, kiểm thử tải, kiểm thử dữ liệu chuyên sâu hoặc nghiệm thu nghiệp vụ chính thức.")
    note_run.italic = True
    note_run.font.size = Pt(8.5)
    note_run.font.color.rgb = RGBColor(100, 100, 100)

    document.core_properties.title = "Báo cáo góp ý về ứng dụng quản lý GPMB"
    document.core_properties.subject = "Góp ý giao diện, dữ liệu và trải nghiệm sử dụng"
    document.core_properties.author = ""
    document.save(OUTPUT)


if __name__ == "__main__":
    build_document()
    print(OUTPUT)