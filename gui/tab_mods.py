"""
TabMods — Tab dọn dẹp & sắp xếp mod Sims 4.

Luồng hoạt động:
    Quét (scan) → lưu kết quả vào :class:`ScanResult` → Xếp / Xóa trùng.

Logic nặng chạy trên daemon thread; kết quả được đẩy về main thread
thông qua ``widget.after(0, callback)``.
"""
from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional
import json

from core.file_utils import safe_delete
import customtkinter as ctk

from ._constants import (
    ARCHIVE_EXTENSIONS,
    Color,
    ConfigKey,
    MOD_EXTENSIONS,
    Status,
    TRAY_EXTENSIONS,
)
from .widgets import StatsCard
from core.config_manager import ConfigManager
from core.sorter import ModSorter
from core.thumbnail_extractor import ThumbnailExtractor
from PIL import Image


logger = logging.getLogger("ModManager.TabMods")


# ─── Dữ liệu kết quả quét ────────────────────────────────────────────────────

@dataclass
class ModInfo:
    """Thông tin chi tiết về một file mod."""
    path: str
    name: str
    size: int
    mtime: float
    category: str
    is_active: bool = True  # True nếu không có suffix .disabled
    is_merged: bool = False # True nếu file này đã tồn tại trong file đã gộp (trong backup)
    merged_in: str = ""    # Tên folder đã gộp chứa file này

    @property
    def size_str(self) -> str:
        if self.size < 1024 ** 2:
            return f"{self.size / 1024:.1f} KB"
        return f"{self.size / 1024 ** 2:.1f} MB"

@dataclass
class ScanResult:
    """Kết quả của một lần quét thư mục mod."""
    total_mods: int = 0
    total_size: int = 0
    all_files: list[ModInfo] = field(default_factory=list)
    unsorted_files: list[str] = field(default_factory=list)
    duplicates: dict[str, list[str]] = field(default_factory=dict)
    merged_files: dict[str, str] = field(default_factory=dict) # key (name_size) -> folder_name

    # ── computed ──────────────────────────────────────────────────────────────
    @property
    def duplicate_count(self) -> int:
        """Tổng số bản sao thừa + file đã gộp."""
        normal_dups = sum(len(v) - 1 for v in self.duplicates.values())
        return normal_dups

    @property
    def size_str(self) -> str:
        """Dung lượng dạng chuỗi có đơn vị."""
        if self.total_size < 1024 ** 2:
            return f"{self.total_size / 1024:.1f} KB"
        if self.total_size < 1024 ** 3:
            return f"{self.total_size / 1024 ** 2:.1f} MB"
        return f"{self.total_size / 1024 ** 3:.2f} GB"


# ─── Tab ─────────────────────────────────────────────────────────────────────

class TabMods(ctk.CTkFrame):
    """Tab dọn dẹp & sắp xếp mod.

    Parameters
    ----------
    master:
        Widget cha.
    config:
        Instance :class:`core.config_manager.ConfigManager`.
    """

    def __init__(self, master: ctk.CTkBaseClass, config: Optional[ConfigManager] = None, **kwargs) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)
        self.config = config or ConfigManager()
        self._sorter = ModSorter(self.config)
        self._scan_result: Optional[ScanResult] = None
        self._filter_vars = {
            "search": ctk.StringVar(),
            "category": ctk.StringVar(value="Tất cả"),
            "min_size": ctk.StringVar(),
            "max_size": ctk.StringVar(),
            "sort_by": ctk.StringVar(value="Tên (A-Z)")
        }
        self._build_ui()

    # ─────────────────────────────────────────────────────────────────────────
    # Build UI
    # ─────────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self._build_stats_row()
        self._build_filter_row()
        self._build_action_row()
        self._build_results_area()
        self._build_log_area()

    def _build_stats_row(self) -> None:
        """Hàng thẻ thống kê."""
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid(row=0, column=0, padx=15, pady=(15, 10), sticky="ew")
        frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self._stat_total = StatsCard(frame, "Tổng Mod", "—", "📦", Color.ACCENT)
        self._stat_total.grid(row=0, column=0, padx=5, sticky="ew")

        self._stat_unsorted = StatsCard(frame, "Chưa xếp", "—", "📂", Color.WARNING)
        self._stat_unsorted.grid(row=0, column=1, padx=5, sticky="ew")

        self._stat_duplicates = StatsCard(frame, "Trùng lặp", "—", "♻️", Color.ERROR)
        self._stat_duplicates.grid(row=0, column=2, padx=5, sticky="ew")

        self._stat_size = StatsCard(frame, "Dung lượng", "—", "💾", Color.SUCCESS)
        self._stat_size.grid(row=0, column=3, padx=5, sticky="ew")

    def _build_action_row(self) -> None:
        """Hàng nút hành động."""
        frame = ctk.CTkFrame(self, fg_color=Color.BG_CARD, corner_radius=12)
        frame.grid(row=1, column=0, padx=15, pady=5, sticky="ew")
        frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        actions = [
            ("🔍 Quét thư mục",    Color.ACCENT,   Color.ACCENT_HOVER,  self._on_scan,    "_scan_btn"),
            ("📂 Tự xếp mod",      Color.PURPLE,   Color.PURPLE_HOVER,  self._on_sort,    "_sort_btn"),
            ("♻️ Xóa trùng lặp",  Color.ERROR,    Color.ERROR_HOVER,   self._on_dedup,   "_dedup_btn"),
            ("📥 Cài đặt thủ công", Color.SUCCESS, Color.SUCCESS_HOVER, self._on_install, "_install_btn"),
        ]

        for col, (text, fg, hover, cmd, attr) in enumerate(actions):
            btn = ctk.CTkButton(
                frame, text=text, height=45,
                font=ctk.CTkFont(size=13, weight="bold"),
                fg_color=fg, hover_color=hover,
                command=cmd,
            )
            btn.grid(row=0, column=col, padx=10, pady=12, sticky="ew")
            btn.grid(row=0, column=col, padx=10, pady=12, sticky="ew")
            setattr(self, attr, btn)

    def _build_filter_row(self) -> None:
        """Hàng lọc nâng cao."""
        frame = ctk.CTkFrame(self, fg_color=Color.BG_CARD, corner_radius=12)
        frame.grid(row=2, column=0, padx=15, pady=5, sticky="ew")
        frame.grid_columnconfigure(0, weight=1)

        # Search
        search_f = ctk.CTkFrame(frame, fg_color="transparent")
        search_f.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        ctk.CTkLabel(search_f, text="🔍 Tìm:", font=ctk.CTkFont(size=12)).pack(side="left", padx=5)
        self._search_entry = ctk.CTkEntry(
            search_f, placeholder_text="Tên file mod...", height=32,
            textvariable=self._filter_vars["search"],
            fg_color=Color.BG_INPUT, border_color=Color.BG_DIVIDER
        )
        self._search_entry.pack(side="left", fill="x", expand=True, padx=5)
        self._filter_vars["search"].trace_add("write", lambda *args: self._on_filter_changed())

        # Category
        cat_f = ctk.CTkFrame(frame, fg_color="transparent")
        cat_f.grid(row=0, column=1, padx=10, pady=10)
        ctk.CTkLabel(cat_f, text="📂 Loại:", font=ctk.CTkFont(size=12)).pack(side="left", padx=5)
        self._cat_combo = ctk.CTkComboBox(
            cat_f, values=["Tất cả"], height=32, width=140,
            variable=self._filter_vars["category"],
            fg_color=Color.BG_INPUT, border_color=Color.BG_DIVIDER,
            command=lambda _: self._on_filter_changed()
        )
        self._cat_combo.pack(side="left", padx=5)

        # Size
        size_f = ctk.CTkFrame(frame, fg_color="transparent")
        size_f.grid(row=0, column=2, padx=10, pady=10)
        ctk.CTkLabel(size_f, text="💾 Size (MB):", font=ctk.CTkFont(size=12)).pack(side="left", padx=5)
        self._min_size_ent = ctk.CTkEntry(size_f, width=50, height=32, placeholder_text="Min", textvariable=self._filter_vars["min_size"])
        self._min_size_ent.pack(side="left", padx=2)
        ctk.CTkLabel(size_f, text="-").pack(side="left")
        self._max_size_ent = ctk.CTkEntry(size_f, width=50, height=32, placeholder_text="Max", textvariable=self._filter_vars["max_size"])
        self._max_size_ent.pack(side="left", padx=2)
        self._filter_vars["min_size"].trace_add("write", lambda *args: self._on_filter_changed())
        self._filter_vars["max_size"].trace_add("write", lambda *args: self._on_filter_changed())

        # Sort
        sort_f = ctk.CTkFrame(frame, fg_color="transparent")
        sort_f.grid(row=0, column=3, padx=10, pady=10)
        self._sort_combo = ctk.CTkComboBox(
            sort_f, values=["Tên (A-Z)", "Size (Lớn nhất)", "Mới nhất", "Cũ nhất"], height=32, width=130,
            variable=self._filter_vars["sort_by"],
            command=lambda _: self._on_filter_changed()
        )
        self._sort_combo.pack(side="left", padx=5)

    def _build_results_area(self) -> None:
        """Khu vực hiển thị danh sách kết quả lọc & Thumbnail Preview."""
        # Chia layout thành 2 cột: Danh sách trái, Ảnh preview phải
        results_container = ctk.CTkFrame(self, fg_color="transparent")
        results_container.grid(row=3, column=0, padx=15, pady=5, sticky="nsew")
        results_container.grid_columnconfigure(0, weight=3) # Danh sách
        results_container.grid_columnconfigure(1, weight=1) # Thumb
        results_container.grid_rowconfigure(0, weight=1)

        self._results_frame = ctk.CTkScrollableFrame(
            results_container, height=180, fg_color=Color.BG_BASE,
            scrollbar_button_color=Color.BG_DIVIDER
        )
        self._results_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        self._results_frame.grid_columnconfigure(0, weight=1)
        
        # Performance: Widget pool for mod list
        self._active_widgets: list[ctk.CTkFrame] = []
        self._widget_pool: list[ctk.CTkFrame] = []
        
        # Vùng xem trước ảnh Thumbnail
        self._thumb_panel = ctk.CTkFrame(results_container, fg_color=Color.BG_CARD, corner_radius=8)
        self._thumb_panel.grid(row=0, column=1, sticky="nsew")
        self._thumb_panel.grid_rowconfigure(1, weight=1)
        self._thumb_panel.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(
            self._thumb_panel, text="🖼️ Xem trước",
            font=ctk.CTkFont(size=13, weight="bold")
        ).grid(row=0, column=0, pady=10)
        
        self._thumb_label = ctk.CTkLabel(
            self._thumb_panel, text="(Nhấn vào mod\nđể xem)",
            text_color=Color.TEXT_DISABLED,
            font=ctk.CTkFont(size=11, slant="italic")
        )
        self._thumb_label.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        self._current_ctk_image = None


    def _build_log_area(self) -> None:
        """Khu vực nhật ký hoạt động (di chuyển xuống row 4)."""
        self.grid_rowconfigure(5, weight=1)
        ctk.CTkLabel(
            self, text="📋 Nhật ký hoạt động",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=Color.TEXT_PRIMARY, anchor="w",
        ).grid(row=4, column=0, padx=20, pady=(10, 0), sticky="nw")

        self._log_box = ctk.CTkTextbox(
            self, fg_color=Color.BG_CARD,
            text_color=Color.TEXT_SECONDARY,
            font=ctk.CTkFont(size=12, family="Consolas"),
            corner_radius=10,
            scrollbar_button_color=Color.BG_DIVIDER,
        )
        self._log_box.grid(row=5, column=0, padx=15, pady=(5, 15), sticky="nsew")
        self._log(
            "📂 Nhấn 'Quét thư mục' để bắt đầu...\n"
            "💡 Bạn có thể dùng bộ lọc phía trên để tìm mod nhanh hơn."
        )
        self._log_box.configure(state="disabled")

    # ─────────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _log(self, msg: str) -> None:
        """Ghi một dòng vào nhật ký (thread-safe)."""
        def _insert() -> None:
            self._log_box.configure(state="normal")
            self._log_box.insert("end", msg + "\n")
            self._log_box.see("end")
            self._log_box.configure(state="disabled")

        self.after(0, _insert)

    def _set_buttons_state(self, state: str) -> None:
        """Bật / tắt tất cả nút hành động (thread-safe)."""
        for attr in ("_scan_btn", "_sort_btn", "_dedup_btn", "_install_btn"):
            self.after(0, lambda b=getattr(self, attr): b.configure(state=state))

    def _run_in_thread(self, target, *args) -> None:
        """Khởi chạy ``target`` trong daemon thread, khóa nút trước và mở sau."""
        self._set_buttons_state("disabled")
        threading.Thread(target=target, args=args, daemon=True).start()

    # ─────────────────────────────────────────────────────────────────────────
    # Event handlers
    # ─────────────────────────────────────────────────────────────────────────

    def _on_scan(self) -> None:
        self._log("─" * 40)
        self._log("🔍 Đang quét thư mục Mods...")
        self._run_in_thread(self._scan_worker)

    def _on_sort(self) -> None:
        if not self._scan_result or not self._scan_result.unsorted_files:
            self._log("⚠️ Chưa quét hoặc không có file cần xếp. Hãy nhấn 'Quét thư mục' trước.")
            return
        self._log("")
        self._log("─" * 40)
        self._log(f"📂 Bắt đầu tự xếp {len(self._scan_result.unsorted_files)} file...")
        self._run_in_thread(self._sort_worker)

    def _on_dedup(self) -> None:
        if not self._scan_result or not self._scan_result.duplicates:
            self._log("⚠️ Chưa quét hoặc không có file trùng. Hãy nhấn 'Quét thư mục' trước.")
            return
        self._log("")
        self._log("─" * 40)
        self._log(f"♻️ Xóa {self._scan_result.duplicate_count} file trùng lặp...")
        self._run_in_thread(self._dedup_worker)

    def _on_install(self) -> None:
        paths = ctk.filedialog.askopenfilenames(
            title="Chọn file Mod (File nén hoặc .package)",
            filetypes=[
                ("Tất cả Mod/File nén", "*.zip;*.rar;*.7z;*.package;*.ts4script"),
                ("File nén", "*.zip;*.rar;*.7z"),
                ("Sims 4 Mods", "*.package;*.ts4script"),
                ("Tất cả", "*.*"),
            ],
        )
        if paths:
            self.process_manual_mods(list(paths))

    # ─────────────────────────────────────────────────────────────────────────
    # Worker threads
    # ─────────────────────────────────────────────────────────────────────────

    def _scan_worker(self) -> None:
        """Thread: quét toàn bộ thư mục mod và cập nhật :attr:`_scan_result`."""
        mod_dir = self.config.mod_directory
        backup_dir = self.config.backup_directory
        staging_dir = os.path.abspath(self.config.staging_directory or "")
        result = ScanResult()

        # 1. Tải danh sách file đã gộp từ backup
        if os.path.exists(backup_dir):
            for safe_folder in os.listdir(backup_dir):
                m_path = os.path.join(backup_dir, safe_folder, "_manifest.json")
                if os.path.exists(m_path):
                    try:
                        with open(m_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            folder_name = data.get("folder", safe_folder)
                            for finfo in data.get("files", []):
                                key = f"{finfo['name'].lower()}_{finfo['size']}"
                                result.merged_files[key] = folder_name
                    except Exception:
                        pass

        sorted_folders: set[str] = set(self.config.sort_rules.keys())
        sorted_folders.add(ModSorter.SCRIPT_FOLDER)
        sorted_folders.add(ModSorter.OTHER_FOLDER)
        
        hash_map: dict[str, list[str]] = {}

        dirs_to_scan = [
            (mod_dir, MOD_EXTENSIONS, False), # (path, valid_exts, is_tray)
            (self.config.tray_directory, TRAY_EXTENSIONS, True)
        ]

        for base_path, allowed_exts, is_tray in dirs_to_scan:
            if not base_path or not os.path.exists(base_path):
                continue
                
            for root, _dirs, files in os.walk(base_path):
                # Bỏ qua thư mục staging trong mod_dir
                if not is_tray and staging_dir and os.path.abspath(root).startswith(staging_dir):
                    continue

                rel = os.path.relpath(root, base_path)
                top_folder = rel.split(os.sep)[0] if rel != "." else ""

                for fname in files:
                    _, ext = os.path.splitext(fname)
                    if ext.lower() not in allowed_exts:
                        continue

                    fpath = os.path.join(root, fname)
                    try:
                        stats = os.stat(fpath)
                        fsize = stats.st_size
                        mtime = stats.st_mtime
                        result.total_size += fsize
                    except OSError:
                        fsize = 0
                        mtime = 0

                    if is_tray:
                        category = "Tray Item"
                    else:
                        is_sorted_folder = top_folder in sorted_folders
                        is_protected = self._sorter.is_protected(fname)

                        # Category: Giữ tên folder nếu đã sorted hoặc được bảo vệ
                        if is_sorted_folder or (top_folder and is_protected):
                            category = top_folder
                        else:
                            category = ModSorter.OTHER_FOLDER

                        # Unsorted: Chỉ flag nếu (không được bảo vệ) VÀ (ở root HOẶC ở subfolder lạ)
                        if not is_protected and (not top_folder or not is_sorted_folder):
                            result.unsorted_files.append(fpath)

                    # Thu thập thông tin đầy đủ
                    key = f"{fname.lower()}_{fsize}"
                    is_merged = key in result.merged_files
                    
                    result.all_files.append(ModInfo(
                        path=fpath,
                        name=fname,
                        size=fsize,
                        mtime=mtime,
                        category=category,
                        is_active=not fname.endswith(".disabled"),
                        is_merged=is_merged,
                        merged_in=result.merged_files.get(key, "")
                    ))

                    result.total_mods += 1

                    hash_map.setdefault(key, []).append(fpath)

        result.duplicates = {k: v for k, v in hash_map.items() if len(v) > 1}
        merged_dup_count = sum(1 for m in result.all_files if m.is_merged)
        self._scan_result = result

        # Cập nhật UI
        self.after(0, self._update_stats_from_scan)

        # Log chi tiết
        self._log(f"✅ Quét xong!")
        self._log(f"   📦 Tổng: {result.total_mods} mod")
        self._log(f"   📂 Chưa xếp: {len(result.unsorted_files)} file")
        self._log(f"   ♻️ Trùng lặp: {result.duplicate_count} file")
        if merged_dup_count:
            self._log(f"   📎 Đã gộp: {merged_dup_count} file (đang nằm trong merged package)")
        self._log(f"   💾 Dung lượng: {result.size_str}")

        if result.duplicates or merged_dup_count:
            self._log("")
            self._log("── File trùng lặp ──")
            # Normal duplicates
            for paths in list(result.duplicates.values())[:5]:
                self._log(f"   🔴 {os.path.basename(paths[0])} ({len(paths)} bản)")
            
            # Merged duplicates
            if merged_dup_count:
                merged_list = [m for m in result.all_files if m.is_merged]
                for m in merged_list[:5]:
                    self._log(f"   🟡 {m.name} (Đã có trong: {m.merged_in})")
            
            total_shown = len(result.duplicates) + merged_dup_count
            if total_shown > 10:
                self._log(f"   ... và {total_shown - 10} nhóm trùng nữa")


        self._set_buttons_state("normal")

    def _sort_worker(self) -> None:
        """Thread: di chuyển các file chưa xếp vào đúng thư mục."""
        assert self._scan_result is not None
        count = 0
        remaining: list[str] = []

        for fpath in self._scan_result.unsorted_files:
            if not os.path.isfile(fpath):
                continue
            try:
                new_path = self._sorter.sort_file(fpath)
                dest = os.path.basename(os.path.dirname(new_path))
                self._log(f"   ✅ {os.path.basename(fpath)} → {dest}")
                count += 1
            except Exception as exc:
                self._log(f"   ❌ Lỗi xếp {os.path.basename(fpath)}: {exc}")
                remaining.append(fpath)

        self._scan_result.unsorted_files = remaining
        self._log(f"✅ Xếp xong {count} file!")
        self.after(0, lambda: self._stat_unsorted.update_value(str(len(remaining))))
        self._set_buttons_state("normal")

    def _dedup_worker(self) -> None:
        """Thread: xóa các bản sao thừa, giữ lại bản đầu tiên trong mỗi nhóm."""
        assert self._scan_result is not None
        removed = 0

        for paths in self._scan_result.duplicates.values():
            for dup_path in paths[1:]:
                if safe_delete(dup_path):
                    self._log(f"   🗑️ Đưa vào Thùng rác: {os.path.relpath(dup_path, self.config.mod_directory)}")
                    removed += 1
                else:
                    self._log(f"   ❌ Lỗi khi dọn dẹp {os.path.basename(dup_path)}")

        self._scan_result.duplicates.clear()
        self._log(f"✅ Đã xóa {removed} file trùng!")
        self.after(0, lambda: self._stat_duplicates.update_value("0"))
        self._set_buttons_state("normal")

    def _manual_install_worker(self, file_paths: list[str]) -> None:
        """Thread: giải nén / copy và sắp xếp các file được chọn thủ công."""
        from core.unpacker import unpack, is_archive
        import shutil

        staging_dir = self.config.staging_directory
        os.makedirs(staging_dir, exist_ok=True)
        count = 0

        for path in file_paths:
            try:
                if not os.path.exists(path):
                    continue

                fname = os.path.basename(path)
                _, ext = os.path.splitext(fname)
                self._log(f"⚙️ Đang xử lý: {fname}")

                if is_archive(path):
                    for extracted in unpack(path, extract_to=staging_dir, delete_after=False):
                        new_path = self._sorter.sort_file(extracted)
                        dest = os.path.basename(os.path.dirname(new_path))
                        self._log(f"   ✅ {os.path.basename(extracted)} → {dest}")
                        count += 1
                elif ext.lower() in MOD_EXTENSIONS:
                    temp_path = os.path.join(staging_dir, fname)
                    shutil.copy2(path, temp_path)
                    new_path = self._sorter.sort_file(temp_path)
                    dest = os.path.basename(os.path.dirname(new_path))
                    self._log(f"   ✅ {fname} → {dest}")
                    count += 1
                else:
                    self._log(f"   ⚠️ Bỏ qua định dạng không hỗ trợ: {ext}")
            except Exception as exc:
                self._log(f"   ❌ Lỗi cài đặt {os.path.basename(path)}: {exc}")
                logger.error(f"Manual install error for {path}: {exc}")

        self._log(f"🎉 Cài đặt thành công {count} mod mới!")
        self._set_buttons_state("normal")

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    def process_manual_mods(self, file_paths: list[str]) -> None:
        """Cài đặt mod thủ công (kéo thả hoặc chọn qua dialog).

        Parameters
        ----------
        file_paths:
            Danh sách đường dẫn tuyệt đối đến file cần cài.
        """
        self._log("")
        self._log("─" * 40)
        self._log(f"📥 Bắt đầu cài đặt {len(file_paths)} file...")
        self._run_in_thread(self._manual_install_worker, file_paths)

    # ─────────────────────────────────────────────────────────────────────────
    # UI update helpers (main thread only)
    # ─────────────────────────────────────────────────────────────────────────

    def _update_stats_from_scan(self) -> None:
        """Cập nhật thẻ thống kê từ :attr:`_scan_result` (main thread)."""
        r = self._scan_result
        if r is None:
            return
        self._stat_total.update_value(str(r.total_mods))
        self._stat_unsorted.update_value(str(len(r.unsorted_files)))
        self._stat_duplicates.update_value(str(r.duplicate_count))
        self._stat_size.update_value(r.size_str)

        # Cập nhật danh mục vào combo
        cats = sorted(list(set(m.category for m in r.all_files)))
        self._cat_combo.configure(values=["Tất cả"] + cats)
        self._on_filter_changed()

    def _on_filter_changed(self) -> None:
        """Kích hoạt khi bất kỳ filter nào thay đổi (có debounce nhẹ hoặc chạy nhanh)."""
        if not self._scan_result:
            return
        
        # Debounce logic đơn giản bằng after
        if hasattr(self, "_filter_job"):
            self.after_cancel(self._filter_job)
        self._filter_job = self.after(300, self._apply_filters)

    def _apply_filters(self) -> None:
        """Thực hiện lọc và hiển thị kết quả."""
        if not self._scan_result:
            return

        query = self._filter_vars["search"].get().lower()
        cat = self._filter_vars["category"].get()
        min_mb = float(self._filter_vars["min_size"].get() or 0)
        max_mb = float(self._filter_vars["max_size"].get() or 999999)
        sort_by = self._filter_vars["sort_by"].get()

        filtered = []
        for mod in self._scan_result.all_files:
            # Search
            if query and query not in mod.name.lower():
                continue
            # Category
            if cat != "Tất cả" and mod.category != cat:
                continue
            # Size
            size_mb = mod.size / (1024 * 1024)
            if size_mb < min_mb or size_mb > max_mb:
                continue
            
            filtered.append(mod)

        # Sort
        if sort_by == "Tên (A-Z)":
            filtered.sort(key=lambda m: m.name)
        elif sort_by == "Mới nhất":
            filtered.sort(key=lambda m: m.mtime, reverse=True)
        elif sort_by == "Cũ nhất":
            filtered.sort(key=lambda m: m.mtime, reverse=False)

        self._render_filtered_results(filtered)
        self.update_idletasks() # Flush drawing

    def _render_filtered_results(self, mods: list[ModInfo]) -> None:
        """Vẽ danh sách các mod đã lọc (sử dụng widget pool để tối ưu)."""
        # 1. Thu hồi các widget đang hiển thị vào pool
        for widget in self._active_widgets:
            widget.pack_forget()
            self._widget_pool.append(widget)
        self._active_widgets.clear()
        
        # Ẩn label "Không tìm thấy" nếu có
        if hasattr(self, "_empty_results_label"):
            self._empty_results_label.pack_forget()
        if hasattr(self, "_more_items_label"):
            self._more_items_label.pack_forget()

        # 2. Hiển thị tối đa 100 mod
        for i, mod in enumerate(mods[:100]):
            widget = self._get_or_create_mod_widget()
            self._update_mod_widget(widget, mod)
            widget.pack(fill="x", pady=1)
            self._active_widgets.append(widget)
            # Cập nhật GUI ngay lập tức để người dùng thấy mượt hơn
            if (i + 1) % 5 == 0: # Update every 5 items
                self.update_idletasks()

        # 3. Xử lý trạng thái đặc biệt
        if len(mods) > 100:
            if not hasattr(self, "_more_items_label"):
                self._more_items_label = ctk.CTkLabel(self._results_frame, text="", font=ctk.CTkFont(size=10, slant="italic"))
            self._more_items_label.configure(text=f"... và {len(mods)-100} mod khác")
            self._more_items_label.pack(pady=5)

        if not mods:
            if not hasattr(self, "_empty_results_label"):
                self._empty_results_label = ctk.CTkLabel(self._results_frame, text="Empty (Không tìm thấy mod nào khớp)", text_color=Color.TEXT_MUTED)
            self._empty_results_label.pack(pady=20)
        
        # Đảm bảo layout được cập nhật mượt mà
        self.update_idletasks()

    def _get_or_create_mod_widget(self) -> ctk.CTkFrame:
        """Lấy một widget từ pool hoặc tạo mới nếu pool trống."""
        if self._widget_pool:
            return self._widget_pool.pop()

        # Tạo mới cấu trúc widget (chạy 1 lần duy nhất cho mỗi widget trong pool)
        f = ctk.CTkFrame(self._results_frame, fg_color=Color.BG_CARD, height=35, cursor="hand2")
        
        # Lưu các label vào thuộc tính của frame để dễ truy cập khi update
        f.lbl_name = ctk.CTkLabel(f, text="", font=ctk.CTkFont(size=12))
        f.lbl_name.pack(side="left", padx=10)
        
        f.lbl_cat = ctk.CTkLabel(f, text="", font=ctk.CTkFont(size=10), text_color=Color.TEXT_MUTED)
        f.lbl_cat.pack(side="left", padx=5)
        
        f.lbl_sz = ctk.CTkLabel(f, text="", font=ctk.CTkFont(size=11), text_color=Color.ACCENT_LIGHT)
        f.lbl_sz.pack(side="right", padx=10)
        
        f.badge = ctk.CTkLabel(
            f, text=" ĐÃ GỘP ", font=ctk.CTkFont(size=9, weight="bold"),
            fg_color=Color.WARNING, text_color="white", corner_radius=4
        )
        # Sẽ pack/unpack tùy theo mod
        
        return f

    def _update_mod_widget(self, widget: ctk.CTkFrame, mod: ModInfo) -> None:
        """Cập nhật dữ liệu cho một widget cũ."""
        widget.lbl_name.configure(text=mod.name)
        widget.lbl_cat.configure(text=mod.category)
        widget.lbl_sz.configure(text=mod.size_str)
        
        if mod.is_merged:
            widget.badge.pack(side="right", padx=5)
        else:
            widget.badge.pack_forget()
            
        # Cập nhật sự kiện click
        click_cmd = lambda e, m=mod: self._on_mod_item_clicked(m)
        widget.bind("<Button-1>", click_cmd)
        widget.lbl_name.bind("<Button-1>", click_cmd)
        widget.lbl_cat.bind("<Button-1>", click_cmd)
        widget.lbl_sz.bind("<Button-1>", click_cmd)

    def _on_mod_item_clicked(self, mod: ModInfo) -> None:
        """Khi click vào 1 mod list item -> Hiện Thumbnail lên side panel."""
        self._thumb_label.configure(text="⏳ Đang tải ảnh...", image="")
        self.update_idletasks()
        
        def _fetch_preview():
            try:
                img = ThumbnailExtractor.extract_thumbnail(mod.path)
                if img:
                    # Resize max 200x200 giữ tỉ lệ
                    img.thumbnail((200, 200), Image.Resampling.LANCZOS)
                    ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
                    self.after(0, lambda: self._show_thumbnail(ctk_img))
                else:
                    self.after(0, lambda: self._thumb_label.configure(text="🚫\nKhông có ảnh gốc", image=""))
            except Exception as e:
                logger.error(f"Thumbnail error: {e}")
                self.after(0, lambda: self._thumb_label.configure(text="❌ Lỗi đọc ảnh", image=""))
                
        threading.Thread(target=_fetch_preview, daemon=True).start()

    def _show_thumbnail(self, ctk_img: ctk.CTkImage) -> None:
        self._current_ctk_image = ctk_img # Giữ tham chiếu để không bị GC thu hồi
        self._thumb_label.configure(text="", image=self._current_ctk_image)
