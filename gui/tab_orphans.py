"""
TabOrphans — Tab tìm và xóa mod "tàng hình" (missing mesh).
"""
from __future__ import annotations

import logging
import os
import threading
from typing import TYPE_CHECKING, List

import customtkinter as ctk

from gui._constants import Color

if TYPE_CHECKING:
    from core.config_manager import ConfigManager

logger = logging.getLogger("ModManager.TabOrphans")


class TabOrphans(ctk.CTkFrame):
    """Tab tìm các file Recolor bị thiếu Mesh."""

    def __init__(self, parent, config: "ConfigManager", **kwargs):
        super().__init__(parent, fg_color=Color.BG_SURFACE, **kwargs)
        self._config = config
        self._orphan_files: List[str] = []
        self._build_ui()

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Header
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 0))
        
        ctk.CTkLabel(hdr, text="👻 Tìm Mod Tàng Hình (Orphan Mesh)", 
                     font=ctk.CTkFont(size=18, weight="bold")).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(hdr, text="Tìm các file Recolor (quần áo, tóc...) bị thiếu Mesh gốc khiến nhân vật bị tàng hình trong game.",
               font=ctk.CTkFont(size=12), text_color=Color.TEXT_SECONDARY).grid(row=1, column=0, sticky="w")

        # Main Scrollable Area
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=1, column=0, sticky="nsew", padx=20, pady=12)
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(0, weight=1)

        self._scroll = ctk.CTkScrollableFrame(
            main, fg_color=Color.BG_CARD, corner_radius=10,
            label_text="📋 Danh sách mod thiếu Mesh",
            label_font=ctk.CTkFont(size=13, weight="bold"),
        )
        self._scroll.grid(row=0, column=0, sticky="nsew")
        self._scroll.grid_columnconfigure(0, weight=1)

        # Status & Action Bar
        bottom = ctk.CTkFrame(self, fg_color=Color.BG_CARD, corner_radius=10)
        bottom.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 20))
        bottom.grid_columnconfigure(0, weight=1)

        self._progress = ctk.CTkProgressBar(bottom, height=6)
        self._progress.set(0)
        self._progress.grid(row=0, column=0, columnspan=2, sticky="ew", padx=16, pady=(12, 4))

        self._status_lbl = ctk.CTkLabel(bottom, text="Sẵn sàng quét.", font=ctk.CTkFont(size=12), text_color=Color.TEXT_SECONDARY)
        self._status_lbl.grid(row=1, column=0, sticky="w", padx=16, pady=(0, 12))

        btn_row = ctk.CTkFrame(bottom, fg_color="transparent")
        btn_row.grid(row=2, column=0, columnspan=2, pady=(0, 12))

        self._btn_scan = ctk.CTkButton(
            btn_row, text="🔍 Bắt đầu quét", command=self._on_scan,
            fg_color=Color.ACCENT, hover_color=Color.ACCENT_HOVER, width=150
        )
        self._btn_scan.pack(side="left", padx=10)

        self._btn_delete = ctk.CTkButton(
            btn_row, text="🗑️ Xóa tất cả đã chọn", command=self._on_delete_selected,
            fg_color=Color.ERROR, hover_color=Color.ERROR_HOVER, width=150, state="disabled"
        )
        self._btn_delete.pack(side="left", padx=10)

    def _on_scan(self):
        self._btn_scan.configure(state="disabled", text="⏳ Đang quét...")
        self._btn_delete.configure(state="disabled")
        self._progress.set(0)
        
        for w in self._scroll.winfo_children():
            w.destroy()
            
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _scan_worker(self):
        from core.orphan_scanner import OrphanScanner
        
        def on_progress(cur, total, msg):
            self.after(0, lambda: self._progress.set(cur / total))
            self.after(0, lambda: self._status_lbl.configure(text=msg))

        orphans = OrphanScanner.scan_missing_meshes(self._config.mod_directory, on_progress)
        self.after(0, lambda: self._render_results(orphans))

    def _render_results(self, orphans: List[str]):
        self._orphan_files = orphans
        self._btn_scan.configure(state="normal", text="🔍 Quét lại")
        
        if not orphans:
            self._status_lbl.configure(text="✅ Không tìm thấy mod nào thiếu mesh!")
            ctk.CTkLabel(self._scroll, text="Tuyệt vời! Tất cả recolor đều đã có mesh.", 
                         text_color=Color.SUCCESS).pack(pady=40)
            return

        self._status_lbl.configure(text=f"⚠️ Tìm thấy {len(orphans)} file thiếu mesh.")
        self._btn_delete.configure(state="normal")

        for i, path in enumerate(orphans):
            row = ctk.CTkFrame(self._scroll, fg_color="transparent")
            row.pack(fill="x", pady=2)
            
            name = os.path.basename(path)
            rel = os.path.relpath(path, self._config.mod_directory)
            
            lbl_name = ctk.CTkLabel(row, text=name, font=ctk.CTkFont(size=12, weight="bold"), anchor="w")
            lbl_name.pack(side="top", fill="x", padx=10)
            
            lbl_path = ctk.CTkLabel(row, text=rel, font=ctk.CTkFont(size=10), text_color=Color.TEXT_MUTED, anchor="w")
            lbl_path.pack(side="top", fill="x", padx=10)
            
            ctk.CTkFrame(self._scroll, height=1, fg_color=Color.BG_DIVIDER).pack(fill="x", padx=10)

    def _on_delete_selected(self):
        from tkinter import messagebox
        if not self._orphan_files: return
        
        confirm = messagebox.askyesno("Xác nhận xóa", f"Bạn có chắc muốn xóa {len(self._orphan_files)} file thiếu mesh này?")
        if confirm:
            deleted = 0
            for f in self._orphan_files:
                try:
                    os.remove(f)
                    deleted += 1
                except:
                    pass
            
            messagebox.showinfo("Hoàn tất", f"Đã xóa {deleted} file.")
            self._on_scan()
