# 🎮 The Sims 4 Mod Manager (TS4MM)

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![GUI](https://img.shields.io/badge/GUI-CustomTkinter-orange.svg)](https://github.com/TomSchimansky/CustomTkinter)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Một công cụ quản lý Mod mạnh mẽ, mượt mà và thông minh dành cho người chơi The Sims 4. Dự án tập trung vào trải nghiệm người dùng tối ưu và khả năng xử lý hàng nghìn mod mà không gây lag máy.

---

## ✨ Tính năng nổi bật

### 🚀 Hiệu suất cực cao
- **Throttling & Debouncing**: Giao diện được tối ưu hóa để không bao giờ bị treo, kể cả khi bạn đang tải 300+ file cùng lúc.
- **Widget Pooling**: Cuộn danh sách hàng nghìn mod mượt mà nhờ công nghệ tái sử dụng widget.
- **Tab Switching Instant**: Chuyển đổi giữa các tính năng tức thì.

### ⬇️ Quản lý tải xuống thông minh
- **Hỗ trợ đa nguồn**: Tải trực tiếp từ **TSR (The Sims Resource)**, **SFS (SimsFileShare)**.
- **SFS LinkGrabber**: Tự động quét và liệt kê toàn bộ file trong folder SFS để bạn chọn lọc.
- **IP Rotation Resiliency**: Hỗ trợ đổi IP qua Warp mà không làm gián đoạn hay lỗi file đang tải.

### 🛡️ Chẩn đoán & Sửa lỗi
- **Conflict Detector**: Quét sâu vào file `.package` để tìm xung đột Resource ID (Object Catalog, CAS, Tuning).
- **Smart Surgery (Phẫu thuật thông minh)**: Tự động loại bỏ các tài nguyên trùng lặp trong file đã Merged mà không làm mất mod.
- **Exception Parser**: Dịch file `LastException.txt` sang tiếng Việt để bạn biết mod nào gây crash game.
- **50/50 Diagnostic**: Công cụ hỗ trợ tìm mod lỗi bằng phương pháp loại trừ 50/50 tự động.

### 📂 Tổ chức Mod khoa học
- **Auto-Sorter**: Tự động phân loại Mod vào các thư mục (Clothing, Shoes, Hair, Script...) dựa trên từ khóa.
- **Duplicate Check**: Tự động phát hiện và xóa các bản mod trùng lặp dựa trên mã hash MD5.
- **WinError 32 Resiliency**: Cơ chế tự động thử lại khi file bị khóa bởi trình diệt virus.

---

## 🛠️ Cài đặt & Sử dụng

### Yêu cầu hệ thống
- Windows 10/11.
- Python 3.10 trở lên.
- (Khuyên dùng) [7-Zip](https://www.7-zip.org/) để giải nén file tốc độ cao.

### Các bước cài đặt
1. **Clone repository**:
   ```bash
   git clone https://github.com/khoyga007/The-Sims-4-Mod-Manager.git
   cd The-Sims-4-Mod-Manager
   ```
2. **Cài đặt thư viện**:
   ```bash
   pip install -r requirements.txt
   ```
3. **Chạy ứng dụng**:
   ```bash
   python main.py
   ```

---

## 📸 Ảnh chụp màn hình
*(Đang cập nhật...)*

## 🤝 Đóng góp
Nếu bạn thấy lỗi hoặc có ý tưởng tính năng mới, hãy mở một Issue hoặc tạo Pull Request. Rất hoan nghênh sự đóng góp của cộng đồng!

## 📜 Giấy phép
Phân phối theo giấy phép MIT. Xem `LICENSE` để biết thêm thông tin.

---
**Sims 4 Mod Manager** — Làm cho việc chơi Sims trở nên dễ dàng hơn bao giờ hết! ✨
