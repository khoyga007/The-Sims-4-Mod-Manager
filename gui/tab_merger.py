"""
Tab Merger — Giao diện gộp file .package để giảm thời gian load game.

Hiển thị danh sách folder, cho phép chọn và gộp/khôi phục.
"""
import logging
import os
import threading
from typing import TYPE_CHECKING

from core.package_merger import PackageMerger, format_size
import customtkinter as ctk

from gui._constants import Color
from gui.base_tab import BaseTab
from gui.ui_utils import _card, _label, _btn

if TYPE_CHECKING:
    from core.config_manager import ConfigManager

logger = logging.getLogger("ModManager.TabMerger")


# ─── Tab ─────────────────────────────────────────────────────────────────────

class TabMerger(BaseTab):
    """Tab gộp mod để giảm load game."""

    def __init__(self, parent, config: "ConfigManager", **kwargs):
        super().__init__(parent, **kwargs)
        self._config = config
        self._folder_vars: list[tuple[ctk.BooleanVar, dict]] = []
        
        self._build_ui()
        self.after(500, self._on_scan)

    # ─────────────────────────────────────────────────────────────────────────
    # UI
    # ─────────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Header
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 0))
        hdr.grid_columnconfigure(1, weight=1)

        _label(hdr, "🔗 Gộp Mod (Package Merger)", size=18, weight="bold").grid(
            row=0, column=0, sticky="w")
        _label(hdr, "Gộp file .package để giảm thời gian load game",
               size=12, color=Color.TEXT_SECONDARY).grid(row=1, column=0, sticky="w")

        # Stats bar
        self._stats_frame = ctk.CTkFrame(hdr, fg_color="transparent")
        self._stats_frame.grid(row=0, column=1, rowspan=2, sticky="e")

        self._stat_folders = _label(self._stats_frame, "—", size=20, weight="bold",
                                    color=Color.ACCENT_LIGHT)
        self._stat_folders.pack(side="left", padx=(0, 4))
        _label(self._stats_frame, "folders", size=11, color=Color.TEXT_MUTED).pack(
            side="left", padx=(0, 16))

        self._stat_files = _label(self._stats_frame, "—", size=20, weight="bold",
                                  color=Color.WARNING)
        self._stat_files.pack(side="left", padx=(0, 4))
        _label(self._stats_frame, "files", size=11, color=Color.TEXT_MUTED).pack(
            side="left", padx=(0, 16))

        self._stat_size = _label(self._stats_frame, "—", size=20, weight="bold",
                                 color=Color.SUCCESS)
        self._stat_size.pack(side="left", padx=(0, 4))
        _label(self._stats_frame, "total", size=11, color=Color.TEXT_MUTED).pack(side="left")

        # Main area: folder list + log
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=1, column=0, sticky="nsew", padx=20, pady=12)
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(0, weight=1)
        main.grid_rowconfigure(1, weight=0)

        # Folder scroll
        self._folder_scroll = ctk.CTkScrollableFrame(
            main, fg_color=Color.BG_CARD, corner_radius=10,
            label_text="📁 Chọn folder cần gộp",
            label_font=ctk.CTkFont(size=13, weight="bold"),
            label_text_color=Color.TEXT_PRIMARY,
        )
        self._folder_scroll.grid(row=0, column=0, sticky="nsew", pady=(0, 8))
        self._folder_scroll.grid_columnconfigure(0, weight=1)

        # Progress + log area
        bottom = _card(main)
        bottom.grid(row=1, column=0, sticky="ew")
        bottom.grid_columnconfigure(0, weight=1)

        self._progress = ctk.CTkProgressBar(
            bottom, fg_color=Color.BG_INPUT, progress_color=Color.ACCENT, height=6)
        self._progress.set(0)
        self._progress.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 4))

        self._log_label = _label(bottom, "Sẵn sàng.", size=12, color=Color.TEXT_SECONDARY)
        self._log_label.grid(row=1, column=0, sticky="w", padx=16, pady=(0, 12))

        # Buttons
        btn_row = ctk.CTkFrame(bottom, fg_color="transparent")
        btn_row.grid(row=2, column=0, pady=(0, 14))

        self._btn_scan = _btn(btn_row, "🔄 Quét lại", command=self._on_scan,
                              color=Color.BG_DIVIDER, hover=Color.BG_INPUT, width=100)
        self._btn_scan.pack(side="left", padx=6)

        self._btn_select_all = _btn(btn_row, "☑ Chọn tất cả",
                                    command=self._on_select_all,
                                    color=Color.BG_DIVIDER, hover=Color.BG_INPUT, width=120)
        self._btn_select_all.pack(side="left", padx=6)

        self._btn_deselect_all = _btn(btn_row, "☐ Bỏ chọn",
                                      command=self._on_deselect_all,
                                      color=Color.BG_DIVIDER, hover=Color.BG_INPUT, width=100)
        self._btn_deselect_all.pack(side="left", padx=6)

        self._btn_merge = _btn(btn_row, "🔗 Gộp Mod đã chọn",
                               command=self._on_merge,
                               color=Color.ACCENT, hover=Color.ACCENT_HOVER, width=180)
        self._btn_merge.pack(side="left", padx=6)

        self._btn_restore = _btn(btn_row, "♻️ Khôi phục tất cả",
                                 command=self._on_restore_all,
                                 color=Color.WARNING, hover=Color.WARNING_HOVER, width=160)
        self._btn_restore.pack(side="left", padx=6)

        self._btn_clean_all = _btn(btn_row, "🗑️ Dọn tất cả Backup",
                                   command=self._on_clean_all_backups,
                                   color=Color.ERROR, hover=Color.ERROR_HOVER, width=160)
        self._btn_clean_all.pack(side="left", padx=6)

        self._btn_consolidate = _btn(btn_row, "🧙 Hợp nhất (Mục đã chọn)",
                                     command=self._on_consolidate_all,
                                     color=Color.INFO, hover=Color.INFO_HOVER, width=180)
        self._btn_consolidate.pack(side="left", padx=6)

    # ─────────────────────────────────────────────────────────────────────────
    # Scan
    # ─────────────────────────────────────────────────────────────────────────

    def _on_scan(self) -> None:
        self._btn_scan.configure(state="disabled", text="⏳ Quét...")
        self._log("Đang quét thư mục Mods...")
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _scan_worker(self) -> None:
        pm = PackageMerger(
            self._config.mod_directory,
            backup_directory=self._config.backup_directory
        )
        stats = pm.scan()
        
        self.queue_ui_task(lambda: self._render_folders(stats))
        self.queue_ui_task(lambda: self._btn_scan.configure(state="normal", text="🔄 Quét lại"))

    def _render_folders(self, stats) -> None:
        
        pm = PackageMerger(
            self._config.mod_directory,
            backup_directory=self._config.backup_directory
        )

        # Clear
        for w in self._folder_scroll.winfo_children():
            w.destroy()
        self._folder_vars.clear()

        total_files = 0
        total_size = 0

        for i, stat in enumerate(stats):
            total_files += stat.package_count
            total_size += stat.total_size

            row = ctk.CTkFrame(self._folder_scroll, fg_color="transparent")
            row.grid(row=i, column=0, sticky="ew", pady=1)
            row.grid_columnconfigure(1, weight=1)

            var = ctk.BooleanVar(value=stat.can_merge)

            cb = ctk.CTkCheckBox(
                row, text="", variable=var,
                fg_color=Color.ACCENT,
                hover_color=Color.ACCENT_HOVER,
                width=24, height=24,
            )
            cb.grid(row=0, column=0, padx=(8, 4), pady=6)

            # Folder info
            info = ctk.CTkFrame(row, fg_color="transparent")
            info.grid(row=0, column=1, sticky="ew", padx=4)

            name_text = f"📁 {stat.folder_name}"
            if stat.already_merged:
                name_text += "  ✅ đã gộp"

            _label(info, name_text, size=13, weight="bold",
                   color=Color.ACCENT_LIGHT if stat.can_merge else Color.SUCCESS
                   ).pack(anchor="w")

            detail = f"{stat.package_count} lẻ"
            if stat.merged_count > 0:
                detail += f" + {stat.merged_count} gộp"
            detail += f"  •  {format_size(stat.total_size)}"
            _label(info, detail, size=11, color=Color.TEXT_MUTED).pack(anchor="w")

            # Badge
            if stat.package_count >= 500:
                badge_color = Color.ERROR
                badge_text = "🔥 Rất nhiều"
            elif stat.package_count >= 100:
                badge_color = Color.WARNING
                badge_text = "⚠️ Nhiều"
            else:
                badge_color = Color.INFO
                badge_text = f"{stat.package_count}"

            ctk.CTkLabel(
                row, text=f"  {badge_text}  ",
                fg_color=badge_color, corner_radius=6,
                text_color="#ffffff",
                font=ctk.CTkFont(size=11, weight="bold"),
            ).grid(row=0, column=2, padx=(4, 8), pady=6)

            # Nút xóa backup (nếu có)
            if pm.has_backup(stat.folder_path):
                btn_clean = ctk.CTkButton(
                    row, text="🗑️ Dọn dẹp", width=80, height=24,
                    fg_color="transparent", hover_color=Color.ERROR,
                    text_color=Color.TEXT_SECONDARY,
                    font=ctk.CTkFont(size=11),
                    command=lambda p=stat.folder_path: self._on_delete_backup(p)
                )
                btn_clean.grid(row=0, column=3, padx=(0, 12), pady=6)

            self._folder_vars.append((var, {
                "folder_path": stat.folder_path,
                "folder_name": stat.folder_name,
                "count": stat.package_count,
                "already_merged": stat.already_merged,
                "can_merge": stat.can_merge
            }))

        # Update stats
        self._stat_folders.configure(text=str(len(stats)))
        self._stat_files.configure(text=str(total_files))
        self._stat_size.configure(text=format_size(total_size))
        self._log(f"Tìm thấy {total_files} file trong {len(stats)} folder.")

    # ─────────────────────────────────────────────────────────────────────────
    # Merge
    # ─────────────────────────────────────────────────────────────────────────

    def _on_select_all(self) -> None:
        for var, info in self._folder_vars:
            if info["can_merge"]:
                var.set(True)

    def _on_deselect_all(self) -> None:
        for var, info in self._folder_vars:
            var.set(False)

    def _on_merge(self) -> None:
        selected = [
            info["folder_path"]
            for var, info in self._folder_vars
            if var.get() and info["can_merge"]
        ]

        if not selected:
            self._log("⚠️ Chưa chọn folder nào để gộp!")
            return

        total_files = sum(
            info["count"]
            for var, info in self._folder_vars
            if var.get() and info["can_merge"]
        )

        self._btn_merge.configure(state="disabled", text="⏳ Đang gộp...")
        self._btn_restore.configure(state="disabled")
        self._btn_scan.configure(state="disabled")
        self._progress.set(0)
        self._log(f"Bắt đầu gộp {len(selected)} folder ({total_files} files)...")

        threading.Thread(
            target=self._merge_worker, args=(selected, False), daemon=True
        ).start()

    def _on_consolidate_all(self) -> None:
        """Thực hiện gộp lại TẤT CẢ bao gồm cả những file đã gộp."""
        selected = [
            info["folder_path"]
            for var, info in self._folder_vars
            if var.get()
        ]

        if not selected:
            self._log("⚠️ Chưa chọn folder nào để hợp nhất!")
            return

        from tkinter import messagebox
        confirm = messagebox.askyesno(
            "Xác nhận Hợp nhất",
            f"Bạn có muốn gộp lại TẤT CẢ file lẻ và file đã gộp cũ bên trong {len(selected)} folder đã chọn không?\n\n"
            "Thao tác này sẽ 'nấu lại' các file gộp cũ để tối ưu hóa dung lượng cho các folder này."
        )
        if not confirm:
            return

        self._btn_merge.configure(state="disabled", text="⏳ Đang gộp...")
        self._btn_consolidate.configure(state="disabled")
        self._btn_restore.configure(state="disabled")
        self._btn_scan.configure(state="disabled")
        self._progress.set(0)
        self._log(f"🧙 Đang hợp nhất toàn bộ {len(selected)} folder...")
        
        threading.Thread(target=self._merge_worker, args=(selected, True), daemon=True).start()

    def _merge_worker(self, folders: list[str], consolidate: bool = False) -> None:

        def on_progress(current, total, msg):
            pct = current / max(total, 1)
            self.queue_ui_task(lambda: self._progress.set(pct))
            self.queue_ui_task(lambda: self._log(msg))

        pm = PackageMerger(
            self._config.mod_directory,
            backup_directory=self._config.backup_directory,
            progress_callback=on_progress
        )

        results = []
        for i, fp in enumerate(folders):
            folder_name = os.path.basename(fp)
            self.queue_ui_task(lambda n=folder_name, idx=i: self._log(
                f"[{idx+1}/{len(folders)}] Gộp {n}..."))

            result = pm.merge_folder(fp, consolidate=consolidate)
            if result:
                results.append(result)

        # Summary
        total_input = sum(r.input_files for r in results)
        total_res = sum(r.resources for r in results)
        total_dups = sum(r.duplicates for r in results)
        total_orig = sum(r.original_size for r in results)
        total_merged = sum(r.merged_size for r in results)

        total_output_files = sum(len(r.output_files) for r in results)
        summary = (
            f"✅ Hoàn tất! {total_input} files → {total_output_files} file gộp. "
            f"{total_res} resources, {total_dups} trùng lặp đã loại. "
            f"Dung lượng: {format_size(total_orig)} → {format_size(total_merged)}"
        )

        self.queue_ui_task(lambda: self._log(summary))
        def done():
            self._btn_merge.configure(state="normal", text="🔗 Gộp Mod đã chọn")
            self._btn_consolidate.configure(state="normal")
            self._btn_restore.configure(state="normal")
            self._btn_scan.configure(state="normal")
            self._progress.set(1.0)
            self._on_scan()

        self.queue_ui_task(done)

        # Refresh folder list
        self.queue_ui_task(lambda: self.after(500, self._on_scan))

    # ─────────────────────────────────────────────────────────────────────────
    # Restore
    # ─────────────────────────────────────────────────────────────────────────

    def _on_restore_all(self) -> None:
        # Tìm folder đã merged
        merged_folders = [
            info["folder_path"]
            for _, info in self._folder_vars
            if info["already_merged"]
        ]

        if not merged_folders:
            self._log("⚠️ Không có folder nào đã gộp để khôi phục!")
            return

        self._btn_restore.configure(state="disabled", text="⏳ Đang khôi phục...")
        self._btn_merge.configure(state="disabled")
        self._btn_scan.configure(state="disabled")
        self._log(f"Khôi phục {len(merged_folders)} folder...")

        threading.Thread(
            target=self._restore_worker, args=(merged_folders,), daemon=True
        ).start()

    def _restore_worker(self, folders: list[str]) -> None:

        pm = PackageMerger(
            self._config.mod_directory,
            backup_directory=self._config.backup_directory
        )
        restored = 0

        for fp in folders:
            folder_name = os.path.basename(fp)
            self.queue_ui_task(lambda n=folder_name: self._log(f"Khôi phục {n}..."))
            if pm.unmerge_folder(fp):
                restored += 1

        def done():
            self._log(f"✅ Đã khôi phục {restored}/{len(folders)} folder.")
            self._btn_restore.configure(state="normal", text="♻️ Khôi phục tất cả")
            self._btn_merge.configure(state="normal")
            self._btn_scan.configure(state="normal")
            self.after(500, self._on_scan)

        self.queue_ui_task(done)

    def _on_delete_backup(self, folder_path: str) -> None:
        """Xóa vĩnh viễn backup để giải phóng dung lượng."""
        from tkinter import messagebox
        
        folder_name = os.path.basename(folder_path)
        confirm = messagebox.askyesno(
            "Xác nhận dọn dẹp",
            f"Bạn có chắc chắn muốn xóa vĩnh viễn backup của '{folder_name}'?\n\n"
            "Hành động này sẽ giúp GIẢI PHÓNG DUNG LƯỢNG ổ đĩa, "
            "nhưng bạn sẽ KHÔNG THỂ khôi phục lại các file lẻ được nữa."
        )
        
        if confirm:
            pm = PackageMerger(self._config.mod_directory, backup_directory=self._config.backup_directory)
            if pm.delete_backup(folder_path):
                self._log(f"✅ Đã dọn dẹp backup cho {folder_name}.")
                self._on_scan()
            else:
                self._log(f"❌ Lỗi khi xóa backup for {folder_name}.")

    def _on_clean_all_backups(self) -> None:
        """Xóa vĩnh viễn toàn bộ backup để giải phóng dung lượng tối đa."""
        from tkinter import messagebox
        import os
        from core.file_utils import safe_delete
        
        backup_dir = self._config.backup_directory
        if not os.path.exists(backup_dir):
            self._log("⚠️ Thư mục backup không tồn tại!")
            return

        # Tìm tất cả các thư mục con trong folder backup có chứa _manifest.json
        backups_to_clean = []
        
        # 1. Thư mục backup hiện tại
        if os.path.exists(backup_dir):
            try:
                for item in os.listdir(backup_dir):
                    item_path = os.path.join(backup_dir, item)
                    if os.path.isdir(item_path) and os.path.exists(os.path.join(item_path, "_manifest.json")):
                        backups_to_clean.append(item_path)
            except OSError:
                pass

        # 2. Thư mục backup cũ trong Mods/_backup
        old_backup_root = os.path.join(self._config.mod_directory, "_backup")
        if os.path.exists(old_backup_root):
            try:
                for item in os.listdir(old_backup_root):
                    item_path = os.path.join(old_backup_root, item)
                    if os.path.isdir(item_path) and os.path.exists(os.path.join(item_path, "_manifest.json")):
                        if item_path not in backups_to_clean:
                            backups_to_clean.append(item_path)
            except OSError:
                pass
        
        if not backups_to_clean:
            self._log("⚠️ Không có backup nào để dọn dẹp!")
            return

        confirm = messagebox.askyesno(
            "Xác nhận DỌN TẤT CẢ",
            f"Bạn có chắc chắn muốn xóa vĩnh viễn {len(backups_to_clean)} bản backup?\n\n"
            "Hành động này sẽ giúp giải phóng dung lượng tối đa (bao gồm cả backup cũ)."
        )
        
        if confirm:
            cleaned = 0
            for path in backups_to_clean:
                if safe_delete(path):
                    cleaned += 1
            
            self._log(f"✅ Đã dọn dẹp xong {cleaned} thư mục backup.")
            self._on_scan()

    # ─────────────────────────────────────────────────────────────────────────
    # Log
    # ─────────────────────────────────────────────────────────────────────────

    def _log(self, msg: str) -> None:
        self.queue_ui_task(lambda: self._log_label.configure(text=msg))
        logger.info(msg)
