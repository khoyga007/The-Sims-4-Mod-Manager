# Sims 4 Mod Manager - Mega Features Plan

## Goal
Tích hợp 4 tính năng siêu cấp vào Sims 4 Mod Manager: Thumbnail Viewer, Tray Explorer, Orphan Mesh Scanner, và Mod Profiles.

## Tasks

### Phase 1: Mod Profiles (Quản lý hồ sơ Mod)
- [ ] Task 1: Tạo class `ProfileManager` trong `core/profile_manager.py` quản lý các profile (bản chất là thư mục con chứa các file `.package` hoặc file danh sách symlink/move file). → Verify: Unit test / Chạy CLI tạo profile.
- [ ] Task 2: Cập nhật GUI: Thêm Tab "Hồ Sơ (Profiles)" với danh sách các Profile, nút "Tạo mới", "Áp dụng", "Xóa". → Verify: UI hiển thị đúng, áp dụng profile thành công thì đổi layout mod.

### Phase 2: Thumbnail Viewer (Xem trước Mod)
- [ ] Task 3: Cập nhật `_DBPFReader` lấy resource Thumbnail (Type ID `0x3C1AF1F2` `THUM` hoặc `0x00B2D882` `Object Catalog`) giải mã ảnh PNG từ binary. → Verify: Trích xuất được bytes mảng PNG từ `.package`.
- [ ] Task 4: Làm GUI hiển thị danh sách Mod có kèm khung hiển thị hình ảnh (`ctk.CTkImage`) khi click vào một `.package`. → Verify: Giao diện hiển thị được ảnh load lên từ RAM.

### Phase 3: Tray Explorer (Quét CC theo Nhân vật/Nhà trong thư mục Tray)
- [ ] Task 5: Parse file `trayitem` (đọc chuẩn DBPF của file Tray), bóc tách danh sách CC required.
- [ ] Task 6: Đối chiếu danh sách CC từ Tray với Mod database đã scan → Giao diện hiển thị những Mod file nào đang được dùng cho nhân vật đó.

### Phase 4: Orphan Mesh Scanner (Máy quét Đồ tàng hình)
- [ ] Task 7: Đọc binary payload của resource `CAS Part` (0x025ED6F4) tóm lược các Key Index chỉ đến Mesh. 
- [ ] Task 8: Tích hợp vào Conflict Detector UI (đổi tên thành "Công cụ chuyên sâu" hay Tab "Chẩn đoán") -> Nút quét Missing Mesh.

## Done When
- [ ] Quản lý profile hoạt động trơn tru (đáp ứng chuyển ngữ cảnh mod nhanh).
- [ ] Giao diện có thể soi xem trước ảnh (Thumbnail) của file CC.
- [ ] Quét được nhân vật Tray đang mặc những file mod gì.
- [ ] Tìm đúng file thiếu mesh.
