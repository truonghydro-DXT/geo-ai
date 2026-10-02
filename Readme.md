# GeoAI Satellite

Hệ thống phân tích dữ liệu viễn thám và GIS dựa trên Python, Flask và Google Earth Engine, phục vụ giám sát môi trường, rừng, đất nông nghiệp, lũ lụt, hạn hán và các chỉ số thực vật.

## 1. Tổng quan

Dự án này xây dựng một nền tảng web GIS cho phép:
- Truy xuất ảnh vệ tinh từ Sentinel-1, Sentinel-2 và Planet
- Tính toán chỉ số thực vật và cảnh quan như NDVI, NDRE, MSAVI, NDWI, EVI, SAVI, GNDVI
- Phát hiện cháy rừng, sạt lở, lũ, hạn hán và thay đổi sử dụng đất
- Hiển thị và phân tích dữ liệu theo cấp tỉnh/huyện/xã
- Hỗ trợ tích hợp với giao diện web và mô-đun sản phẩm

Ứng dụng chính chạy qua Flask (`server.py`) và phục vụ giao diện nằm trong thư mục `public/` và `product/`.

## 2. Cấu trúc thư mục chính

- `server.py` – ứng dụng chính chạy nền web GIS
- `server-product.py` – phiên bản sản phẩm, dùng cho giao diện `product/`
- `server-demo.py` – phiên bản demo (cần có thư mục `demo/` tương ứng nếu muốn chạy)
- `public/` – giao diện web mặc định
- `product/` – phiên bản sản phẩm / UI dành cho môi trường triển khai
- `public/algorithm/` – các thuật toán xử lý ảnh vệ tinh và GIS
- `scripts/` – script phụ trợ
- `requirements.txt` – danh sách dependency
- `setup.py` – build Cython cho các module thuật toán
- `gee-service-account.json` – khóa dịch vụ Google Earth Engine (bắt buộc)
- `run_geoai.bat`, `run_geoai-product.bat`, `run_geoai-demo.bat` – script chạy nhanh trên Windows

## 3. Yêu cầu môi trường

- Python 3.10+
- Windows 10/11 hoặc Linux/macOS
- Microsoft Build Tools / C++ build tools nếu cần compile một số dependency
- Google Earth Engine service account JSON hợp lệ
- PostgreSQL nếu bạn chạy các API liên quan đến đăng nhập / quản lý người dùng

## 4. Cài đặt

### Tạo môi trường ảo

PowerShell:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

CMD:

```cmd
python -m venv venv
venv\Scripts\activate.bat
```

### Cài đặt dependency

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Nếu cần build lại module thuật toán:

```powershell
python setup.py build_ext --inplace
```

## 5. Cấu hình bắt buộc

### Google Earth Engine

Dự án yêu cầu file `gee-service-account.json` ở thư mục gốc. File này chứa thông tin tài khoản service account của Google Earth Engine.

Nếu tài liệu không tồn tại, ứng dụng sẽ báo lỗi tương tự:

```text
FileNotFoundError: Missing service account file: ...\gee-service-account.json
```

Lưu ý: file này phải được giữ bí mật và không commit vào kho lưu trữ nếu không được phép.

### Cơ sở dữ liệu PostgreSQL

Một số API trong ứng dụng (đăng nhập, quản lý người dùng, tải dữ liệu người dùng theo dự án) kết nối tới PostgreSQL ở localhost với cấu hình được định nghĩa trực tiếp trong `server.py`. Nếu bạn chạy môi trường không có DB tương ứng, hãy cập nhật thông tin kết nối trước khi sử dụng các endpoint liên quan.

## 6. Chạy ứng dụng

### Chạy ứng dụng chính

```powershell
python server.py
```

Sau đó mở trình duyệt tại:

```text
http://localhost:5000
```

### Chạy phiên bản sản phẩm

```powershell
python server-product.py
```

### Chạy script Windows sẵn có

```powershell
.\run_geoai.bat
```

```powershell
.\run_geoai-product.bat
```

## 7. Tính năng chính

### Theo dõi và phân tích viễn thám
- Sentinel-1, Sentinel-2, Planet
- Chỉ số thực vật: NDVI, NDRE, MSAVI, NDWI, EVI, SAVI, GNDVI
- Phân tích rừng và đất nông nghiệp
- Phát hiện cháy rừng, sạt lở, lũ lụt, hạn hán

### GIS / bản đồ
- Xử lý dữ liệu hình học và shapefile
- Hiển thị dữ liệu theo tỉnh / huyện / xã
- Tích hợp với giao diện bản đồ web

### Mô-đun sản phẩm
- Dự án có cả phiên bản `public/` và `product/` để dễ triển khai theo nhu cầu khác nhau
- Phần `product` phù hợp để chuẩn bị cho môi trường dùng thực tế/ứng dụng thương mại

## 8. Xử lý sự cố thường gặp

### 1) Lỗi `gee-service-account.json` không tìm thấy
- Kiểm tra file có ở thư mục gốc hay chưa
- Đảm bảo tên file đúng chính xác
- Nếu đang dùng mode Windows, kiểm tra không có ký tự thừa hoặc tên khác

### 2) Lỗi thư viện GDAL / rasterio
- Tạo lại môi trường ảo
- Reinstall dependency theo `requirements.txt`
- Trên Windows, có thể cần cài `rasterio` phù hợp với phiên bản Python đang dùng

### 3) Lỗi Earth Engine
- Kiểm tra đồng bộ thời gian máy
- Xác nhận service account JSON còn hợp lệ
- Kiểm tra quyền truy cập Google Earth Engine

## 9. Ghi chú triển khai

- Khi chạy trong môi trường thực tế, nên tách riêng file cấu hình nhạy cảm (service account, thông tin DB) khỏi repository chính
- Nên lưu trữ file `gee-service-account.json` trong biến môi trường hoặc bộ quản lý bí mật nếu triển khai production
- Nếu muốn xây dựng exe standalone, có thể dùng PyInstaller với lệnh tương tự:

```powershell
python -m pip install pyinstaller
pyinstaller --onefile server.py
```

## 10. Lời khuyên

Để khởi động nhanh nhất, hãy dùng `server.py` và `public/` vì đây là phiên bản đang được cấu trúc rõ ràng nhất trong repo hiện tại. Nếu cần triển khai sản phẩm, hãy dùng `server-product.py` và cấu hình thêm dữ liệu địa lý/khóa service phù hợp với môi trường chạy của bạn.

---

Nếu cần, có thể tiếp tục cập nhật README này theo hướng:
- thêm sơ đồ kiến trúc hệ thống
- thêm danh sách API endpoint
- thêm hướng dẫn phát triển và triển khai trên server production
- bổ sung mô tả nghiệp vụ theo từng chức năng (rừng, nông nghiệp, lũ lụt, chống cháy)
