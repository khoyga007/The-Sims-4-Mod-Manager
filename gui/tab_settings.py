"""
TabSettings — Tab cài đặt ứng dụng.

Đọc cấu hình hiện tại từ :class:`core.config_manager.ConfigManager` và
lưu lại khi người dùng nhấn nút "Lưu cài đặt".
"""
from __future__ import annotations

from typing import Optional

import customtkinter as ctk

from ._constants import Color, ConfigKey
from core.config_manager import ConfigManager


class TabSettings(ctk.CTkFrame):
    """Tab cài đặt ứng dụng.

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
        self._build_ui()

    # ─────────────────────────────────────────────────────────────────────────
    # Build UI
    # ─────────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=Color.BG_DIVIDER,
            scrollbar_button_hover_color=Color.ACCENT,
        )
        scroll.grid(row=0, column=0, padx=15, pady=15, sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)

        row = 0

        # ── Thư mục ───────────────────────────────────────────────────────────
        row = self._add_section(scroll, "📁 Thư mục", row)
        row = self._add_path_row(
            scroll,
            label="Thư mục Mod chính:",
            desc="Nơi chứa toàn bộ mod (đã junction)",
            value=self.config.mod_directory,
            config_key=ConfigKey.MOD_DIRECTORY,
            row=row,
        )
        row = self._add_path_row(
            scroll,
            label="Thư mục tạm (Staging):",
            desc="Nơi lưu file trước khi giải nén & phân loại",
            value=self.config.staging_directory,
            config_key=ConfigKey.STAGING_DIRECTORY,
            row=row,
        )
        row = self._add_path_row(
            scroll,
            label="Thư mục Tray (Blueprint/Sims):",
            desc="Nơi chứa nhà cửa và thông tin nhân vật (thư viện)",
            value=self.config.tray_directory,
            config_key=ConfigKey.TRAY_DIRECTORY,
            row=row,
        )
        row = self._add_path_row(
            scroll,
            label="Thư mục TS4 (Documents):",
            desc="Nơi chứa LastException, cache và Tray (tự động tìm nếu để trống)",
            value=self.config.ts4_docs_dir or "",
            config_key=ConfigKey.TS4_DOCS_DIR,
            row=row,
        )

        # ── Tải xuống ─────────────────────────────────────────────────────────
        row = self._add_section(scroll, "⬇️ Tải xuống", row)
        row = self._add_max_downloads_row(scroll, row)

        # ── Tự động hóa ───────────────────────────────────────────────────────
        row = self._add_section(scroll, "⚡ Tự động hóa", row)

        self._auto_unpack_var = ctk.BooleanVar(value=self.config.auto_unpack)
        row = self._add_toggle_row(
            scroll, "Tự động giải nén",
            "Giải nén .zip/.rar/.7z sau khi tải về",
            self._auto_unpack_var, row,
        )

        self._auto_sort_var = ctk.BooleanVar(value=self.config.auto_sort)
        row = self._add_toggle_row(
            scroll, "Tự động phân loại",
            "Phân loại file .package vào đúng thư mục con",
            self._auto_sort_var, row,
        )

        self._clipboard_var = ctk.BooleanVar(value=self.config.clipboard_monitor_enabled)
        row = self._add_toggle_row(
            scroll, "Theo dõi Clipboard",
            "Tự động bắt link TSR/SFS khi bạn copy URL",
            self._clipboard_var, row,
        )

        self._auto_rotate_warp_var = ctk.BooleanVar(value=self.config.auto_rotate_warp)
        row = self._add_toggle_row(
            scroll, "Tự động đổi IP (Kemono)",
            "Tự động reconnect Warp khi tốc độ tải từ Kemono bị bóp xuống dưới 100KB/s",
            self._auto_rotate_warp_var, row,
        )

        self._del_archive_var = ctk.BooleanVar(value=self.config.delete_archive_after_unpack)
        row = self._add_toggle_row(
            scroll, "Xóa file nén sau giải nén",
            "Xóa .zip/.rar/.7z gốc sau khi đã giải nén thành công",
            self._del_archive_var, row,
        )

        self._auto_clear_cache_var = ctk.BooleanVar(value=self.config.auto_clear_cache)
        row = self._add_toggle_row(
            scroll, "Tự động xóa cache",
            "Xóa localthumbcache và các file rác sau khi tắt game",
            self._auto_clear_cache_var, row,
        )

        # ── Quy tắc phân loại ──────────────────────────────────────────────────
        row = self._add_section(scroll, "🔧 Quy tắc phân loại Mod", row)
        row = self._build_rules_editor(scroll, row)

        # ── Bảo trì & Dọn dẹp ──────────────────────────────────────────────────
        row = self._add_section(scroll, "🧹 Bảo trì & Dọn dẹp", row)
        row = self._add_maintenance_row(scroll, row)

        # ── Tối ưu hóa Game ────────────────────────────────────────────────────
        row = self._add_section(scroll, "🚀 Tối ưu hóa Game (Mạnh hơn EA)", row)
        
        self._turbo_mode_var = ctk.BooleanVar(value=self.config.turbo_mode)
        row = self._add_toggle_row(
            scroll, "Chế độ Turbo (Ưu tiên CPU)",
            "Ép Windows ưu tiên tài nguyên tối đa cho Sims 4 để giảm lag Autonomy.",
            self._turbo_mode_var, row
        )

        self._dx11_mode_var = ctk.BooleanVar(value=self.config.dx11_mode)
        row = self._add_toggle_row(
            scroll, "Sử dụng DirectX 11",
            "Sử dụng engine đồ họa mới để tăng FPS và ổn định khung hình.",
            self._dx11_mode_var, row
        )

        # ── Đường dẫn Game ─────────────────────────────────────────────────────
        row = self._add_section(scroll, "🎮 Đường dẫn Game", row)
        row = self._add_path_row(
            scroll,
            label="File thực thi (.exe):",
            desc="Đường dẫn đến TS4_x64.exe để khởi chạy nhanh",
            value=self.config.game_path,
            config_key=ConfigKey.GAME_PATH,
            row=row,
        )

        # ── Giao diện ──────────────────────────────────────────────────────────
        row = self._add_section(scroll, "🎨 Giao diện", row)
        row = self._add_appearance_row(scroll, row)

        # ── Nút lưu ───────────────────────────────────────────────────────────
        save_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        save_frame.grid(row=row, column=0, padx=5, pady=20, sticky="ew")

        ctk.CTkButton(
            save_frame, text="💾 Lưu cài đặt", height=45, width=200,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=Color.ACCENT, hover_color=Color.ACCENT_HOVER,
            corner_radius=10,
            command=self._on_save,
        ).pack(pady=10)

        self._save_status = ctk.CTkLabel(
            save_frame, text="",
            font=ctk.CTkFont(size=12),
            text_color=Color.SUCCESS,
        )
        self._save_status.pack()

    # ─────────────────────────────────────────────────────────────────────────
    # Row builders
    # ─────────────────────────────────────────────────────────────────────────

    def _add_section(self, parent: ctk.CTkScrollableFrame, title: str, row: int) -> int:
        """Thêm tiêu đề nhóm cài đặt.

        Returns
        -------
        int
            Chỉ số hàng tiếp theo.
        """
        ctk.CTkLabel(
            parent, text=title,
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=Color.ACCENT_LIGHT, anchor="w",
        ).grid(row=row, column=0, padx=10, pady=(20, 8), sticky="w")
        return row + 1

    def _add_path_row(
        self,
        parent: ctk.CTkScrollableFrame,
        label: str,
        desc: str,
        value: str,
        config_key: str,
        row: int,
    ) -> int:
        """Thêm một hàng cài đặt đường dẫn (label + mô tả + ô nhập).

        Parameters
        ----------
        parent:
            Frame cha.
        label:
            Tên cài đặt.
        desc:
            Mô tả ngắn bên dưới nhãn.
        value:
            Giá trị hiện tại.
        config_key:
            Khóa dùng để lưu (phải trùng thuộc tính ``entry_<config_key>``).
        row:
            Chỉ số hàng grid hiện tại.

        Returns
        -------
        int
            Chỉ số hàng tiếp theo.
        """
        frame = ctk.CTkFrame(parent, fg_color=Color.BG_CARD, corner_radius=10)
        frame.grid(row=row, column=0, padx=5, pady=3, sticky="ew")
        frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            frame, text=label,
            font=ctk.CTkFont(size=13), text_color=Color.TEXT_PRIMARY,
        ).grid(row=0, column=0, padx=15, pady=(12, 0), sticky="w")

        ctk.CTkLabel(
            frame, text=desc,
            font=ctk.CTkFont(size=10), text_color=Color.TEXT_MUTED,
        ).grid(row=1, column=0, padx=15, pady=(0, 2), sticky="w")

        entry = ctk.CTkEntry(
            frame,
            font=ctk.CTkFont(size=12), height=35,
            fg_color=Color.BG_INPUT, border_color=Color.BG_DIVIDER,
            text_color=Color.TEXT_PRIMARY,
        )
        entry.insert(0, value)
        entry.grid(row=0, column=1, rowspan=2, padx=(10, 15), pady=12, sticky="ew")

        # Lưu reference bằng tên động để _on_save có thể đọc
        setattr(self, f"_entry_{config_key}", entry)
        return row + 1

    def _add_max_downloads_row(self, parent: ctk.CTkScrollableFrame, row: int) -> int:
        """Thêm hàng cài đặt số lượng tải đồng thời (slider).

        Returns
        -------
        int
            Chỉ số hàng tiếp theo.
        """
        frame = ctk.CTkFrame(parent, fg_color=Color.BG_CARD, corner_radius=10)
        frame.grid(row=row, column=0, padx=5, pady=3, sticky="ew")
        frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            frame, text="Số lượng tải đồng thời tối đa:",
            font=ctk.CTkFont(size=13), text_color=Color.TEXT_PRIMARY,
        ).grid(row=0, column=0, padx=15, pady=12, sticky="w")

        self._max_dl_var = ctk.IntVar(value=self.config.max_downloads)

        ctk.CTkSlider(
            frame, from_=1, to=8, number_of_steps=7,
            variable=self._max_dl_var,
            fg_color=Color.BG_INPUT, progress_color=Color.ACCENT,
            button_color=Color.ACCENT_LIGHT, button_hover_color=Color.ACCENT,
            command=lambda _v: self._update_slider_label(),
        ).grid(row=0, column=1, padx=10, pady=12, sticky="ew")

        self._max_dl_label = ctk.CTkLabel(
            frame, text=str(self.config.max_downloads),
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=Color.ACCENT_LIGHT, width=30,
        )
        self._max_dl_label.grid(row=0, column=2, padx=(0, 15), pady=12)
        return row + 1

    def _add_toggle_row(
        self,
        parent: ctk.CTkScrollableFrame,
        title: str,
        desc: str,
        var: ctk.BooleanVar,
        row: int,
    ) -> int:
        """Thêm một hàng cài đặt kiểu bật/tắt (toggle switch).

        Returns
        -------
        int
            Chỉ số hàng tiếp theo.
        """
        frame = ctk.CTkFrame(parent, fg_color=Color.BG_CARD, corner_radius=10)
        frame.grid(row=row, column=0, padx=5, pady=3, sticky="ew")
        frame.grid_columnconfigure(0, weight=1)

        text_frame = ctk.CTkFrame(frame, fg_color="transparent")
        text_frame.grid(row=0, column=0, padx=15, pady=12, sticky="w")

        ctk.CTkLabel(
            text_frame, text=title,
            font=ctk.CTkFont(size=13, weight="bold"), text_color=Color.TEXT_PRIMARY,
        ).pack(anchor="w")

        ctk.CTkLabel(
            text_frame, text=desc,
            font=ctk.CTkFont(size=10), text_color=Color.TEXT_MUTED,
        ).pack(anchor="w")

        ctk.CTkSwitch(
            frame, text="", variable=var,
            progress_color=Color.ACCENT,
            button_color=Color.ACCENT_LIGHT,
            fg_color=Color.BG_INPUT,
        ).grid(row=0, column=1, padx=15, pady=12)
        return row + 1

    def _add_appearance_row(self, parent: ctk.CTkScrollableFrame, row: int) -> int:
        """Thêm hàng cài đặt chế độ hiển thị (Sáng / Tối / Hệ thống)."""
        frame = ctk.CTkFrame(parent, fg_color=Color.BG_CARD, corner_radius=10)
        frame.grid(row=row, column=0, padx=5, pady=3, sticky="ew")
        frame.grid_columnconfigure(0, weight=1)

        text_frame = ctk.CTkFrame(frame, fg_color="transparent")
        text_frame.grid(row=0, column=0, padx=15, pady=12, sticky="w")

        ctk.CTkLabel(
            text_frame, text="Chế độ hiển thị",
            font=ctk.CTkFont(size=13, weight="bold"), text_color=Color.TEXT_PRIMARY,
        ).pack(anchor="w")

        ctk.CTkLabel(
            text_frame, text="Chọn tông màu giao diện của ứng dụng",
            font=ctk.CTkFont(size=10), text_color=Color.TEXT_MUTED,
        ).pack(anchor="w")

        current = self.config.appearance_mode
        init_val = "☀️ Light" if current == "light" else "🌙 Dark" if current == "dark" else "🖥️ Auto"
        self._appearance_mode_var = ctk.StringVar(value=init_val)
        
        mode_btn = ctk.CTkSegmentedButton(
            frame, values=["☀️ Light", "🌙 Dark", "🖥️ Auto"],
            variable=self._appearance_mode_var,
            command=self._on_appearance_mode_change,
            selected_color=Color.ACCENT,
            selected_hover_color=Color.ACCENT_HOVER,
            unselected_color=Color.BG_INPUT,
            unselected_hover_color=Color.BG_DIVIDER,
            text_color=Color.TEXT_PRIMARY,
        )
        mode_btn.grid(row=0, column=1, padx=15, pady=12)
        return row + 1

    def _on_appearance_mode_change(self, mode_str: str) -> None:
        """Sự kiện đổi chế độ hiển thị ngay lập tức và đồng bộ sidebar."""
        mapping = {"☀️ Light": "light", "🌙 Dark": "dark", "🖥️ Auto": "system"}
        mode_lower = mapping.get(mode_str, mode_str.lower())
        
        ctk.set_appearance_mode(mode_lower)
        self.config.set("appearance_mode", mode_lower)
        
        # Đồng bộ với sidebar (app.py)
        try:
            # TabSettings -> ContentArea -> App
            app = self.master.master
            if hasattr(app, "_appearance_mode_var"):
                app._appearance_mode_var.set(mode_str)
        except Exception:
            pass


    def _add_maintenance_row(self, parent: ctk.CTkScrollableFrame, row: int) -> int:
        """Thêm hàng chứa các nút dọn dẹp thủ công."""
        frame = ctk.CTkFrame(parent, fg_color=Color.BG_CARD, corner_radius=10)
        frame.grid(row=row, column=0, padx=5, pady=3, sticky="ew")
        frame.grid_columnconfigure(0, weight=1)

        text_frame = ctk.CTkFrame(frame, fg_color="transparent")
        text_frame.grid(row=0, column=0, padx=15, pady=12, sticky="w")

        ctk.CTkLabel(
            text_frame, text="Dọn dẹp Cache thủ công",
            font=ctk.CTkFont(size=13, weight="bold"), text_color=Color.TEXT_PRIMARY,
        ).pack(anchor="w")

        ctk.CTkLabel(
            text_frame, text="Xóa localthumbcache và dữ liệu tạm để sửa lỗi Sim bị kẹt trạng thái cũ.",
            font=ctk.CTkFont(size=10), text_color=Color.TEXT_MUTED,
        ).pack(anchor="w")

        ctk.CTkButton(
            frame, text="⚡ Dọn ngay", width=100, height=32,
            fg_color=Color.WARNING, hover_color=Color.WARNING_HOVER,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._on_clear_cache
        ).grid(row=0, column=1, padx=15, pady=12)

        # ── Dọn thư mục trống ──────────────────────────────────────────────────
        row += 1
        frame2 = ctk.CTkFrame(parent, fg_color=Color.BG_CARD, corner_radius=10)
        frame2.grid(row=row, column=0, padx=5, pady=3, sticky="ew")
        frame2.grid_columnconfigure(0, weight=1)

        text_frame2 = ctk.CTkFrame(frame2, fg_color="transparent")
        text_frame2.grid(row=0, column=0, padx=15, pady=12, sticky="w")

        ctk.CTkLabel(
            text_frame2, text="Dọn thư mục trống",
            font=ctk.CTkFont(size=13, weight="bold"), text_color=Color.TEXT_PRIMARY,
        ).pack(anchor="w")

        ctk.CTkLabel(
            text_frame2, text="Xóa các thư mục không chứa file nào để thư mục Mod gọn gàng hơn.",
            font=ctk.CTkFont(size=10), text_color=Color.TEXT_MUTED,
        ).pack(anchor="w")

        self._btn_clear_empty = ctk.CTkButton(
            frame2, text="🗑️ Dọn Folder", width=100, height=32,
            fg_color=Color.BG_DIVIDER, hover_color=Color.BG_INPUT,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._on_clear_empty_folders
        )
        self._btn_clear_empty.grid(row=0, column=1, padx=15, pady=12)
        
        return row + 1

    def _build_rules_editor(self, parent: ctk.CTkScrollableFrame, row: int) -> int:
        """Xây dựng bộ soạn thảo quy tắc phân loại."""
        self._rules_container = ctk.CTkFrame(parent, fg_color="transparent")
        self._rules_container.grid(row=row, column=0, padx=5, pady=5, sticky="ew")
        self._rules_container.grid_columnconfigure(0, weight=1)

        self._rule_rows: list[dict] = []
        rules = self.config.sort_rules

        # Thư mục cố định (không cho sửa/xóa)
        for folder, keywords in rules.items():
            self._add_rule_row(folder, keywords)

        # Nút thêm
        self._add_rule_btn = ctk.CTkButton(
            parent, text="➕ Thêm quy tắc mới", height=32,
            font=ctk.CTkFont(size=12),
            fg_color=Color.BG_DIVIDER, hover_color=Color.BG_INPUT,
            command=lambda: self._add_rule_row("", [])
        )
        self._add_rule_btn.grid(row=row + 1, column=0, padx=10, pady=10, sticky="w")

        return row + 2

    def _add_rule_row(self, folder: str, keywords: list[str]) -> None:
        """Thêm một hàng quy tắc vào container."""
        f = ctk.CTkFrame(self._rules_container, fg_color=Color.BG_CARD, corner_radius=10)
        f.pack(fill="x", pady=2)

        # Folder entry
        folder_ent = ctk.CTkEntry(
            f, width=150, height=32, placeholder_text="Tên thư mục",
            fg_color=Color.BG_INPUT, border_color=Color.BG_DIVIDER
        )
        folder_ent.insert(0, folder)
        folder_ent.pack(side="left", padx=(12, 5), pady=10)

        # Arrow icon
        ctk.CTkLabel(f, text="←", font=ctk.CTkFont(size=16)).pack(side="left", padx=5)

        # Keywords entry
        kw_text = ", ".join(keywords)
        kw_ent = ctk.CTkEntry(
            f, height=32, placeholder_text="từ_khóa1, từ_khóa2...",
            fg_color=Color.BG_INPUT, border_color=Color.BG_DIVIDER
        )
        kw_ent.insert(0, kw_text)
        kw_ent.pack(side="left", fill="x", expand=True, padx=5, pady=10)

        # Action buttons
        btn_f = ctk.CTkFrame(f, fg_color="transparent")
        btn_f.pack(side="right", padx=(5, 12))

        def _move_up(idx):
            if idx > 0:
                self._rule_rows[idx], self._rule_rows[idx-1] = self._rule_rows[idx-1], self._rule_rows[idx]
                self._refresh_rules_ui()

        def _move_down(idx):
            if idx < len(self._rule_rows) - 1:
                self._rule_rows[idx], self._rule_rows[idx+1] = self._rule_rows[idx+1], self._rule_rows[idx]
                self._refresh_rules_ui()

        def _delete(idx):
            self._rule_rows.pop(idx)
            self._refresh_rules_ui()

        idx = len(self._rule_rows)
        ctk.CTkButton(btn_f, text="▲", width=28, height=28, command=lambda i=idx: _move_up(i)).pack(side="left", padx=1)
        ctk.CTkButton(btn_f, text="▼", width=28, height=28, command=lambda i=idx: _move_down(i)).pack(side="left", padx=1)
        ctk.CTkButton(btn_f, text="✕", width=28, height=28, fg_color=Color.ERROR, hover_color=Color.ERROR_HOVER,
                      command=lambda i=idx: _delete(i)).pack(side="left", padx=(5, 0))

        self._rule_rows.append({
            "frame": f,
            "folder": folder_ent,
            "keywords": kw_ent
        })

    def _refresh_rules_ui(self) -> None:
        """Xóa trắng container và vẽ lại theo thứ tự mới."""
        # Lưu trữ tạm các giá trị hiện tại trước khi pack_forget
        data = []
        for row in self._rule_rows:
            data.append({
                "folder": row["folder"].get(),
                "keywords": row["keywords"].get()
            })
            row["frame"].pack_forget()

        self._rule_rows.clear()
        for item in data:
            self._add_rule_row(item["folder"], [k.strip() for k in item["keywords"].split(",") if k.strip()])

    # ─────────────────────────────────────────────────────────────────────────
    # Event handlers
    # ─────────────────────────────────────────────────────────────────────────

    def _update_slider_label(self) -> None:
        """Đồng bộ nhãn hiển thị với giá trị slider."""
        self._max_dl_label.configure(text=str(self._max_dl_var.get()))

    def _on_save(self) -> None:
        """Đọc tất cả giá trị trên form và lưu vào ConfigManager."""
        self.config.set(ConfigKey.MOD_DIRECTORY,   self._entry_mod_directory.get())
        self.config.set(ConfigKey.TRAY_DIRECTORY,  self._entry_tray_directory.get())
        self.config.set(ConfigKey.STAGING_DIRECTORY, self._entry_staging_directory.get())
        self.config.set(ConfigKey.MAX_DOWNLOADS,   self._max_dl_var.get())
        self.config.set(ConfigKey.AUTO_UNPACK,     self._auto_unpack_var.get())
        self.config.set(ConfigKey.AUTO_SORT,       self._auto_sort_var.get())
        self.config.set(ConfigKey.CLIPBOARD_MONITOR, self._clipboard_var.get())
        self.config.set(ConfigKey.DELETE_ARCHIVE_AFTER_UNPACK, self._del_archive_var.get())
        self.config.set(ConfigKey.AUTO_CLEAR_CACHE, self._auto_clear_cache_var.get())
        self.config.set("auto_rotate_warp",        self._auto_rotate_warp_var.get())
        self.config.set(ConfigKey.TURBO_MODE,       self._turbo_mode_var.get())
        self.config.set(ConfigKey.DX11_MODE,        self._dx11_mode_var.get())
        self.config.set(ConfigKey.TS4_DOCS_DIR,     self._entry_ts4_docs_dir.get().strip() or None)
        self.config.set(ConfigKey.GAME_PATH,       self._entry_game_path.get())
        # Theme
        mapping = {"☀️ Light": "light", "🌙 Dark": "dark", "🖥️ Auto": "system"}
        mode_str = self._appearance_mode_var.get()
        self.config.set(ConfigKey.APPEARANCE_MODE, mapping.get(mode_str, mode_str.lower()))

        # Lưu quy tắc phân loại
        new_rules = {}
        for row in self._rule_rows:
            f = row["folder"].get().strip()
            k = [x.strip() for x in row["keywords"].get().split(",") if x.strip()]
            if f and k:
                new_rules[f] = k
        self.config.set(ConfigKey.SORT_RULES, new_rules)

        self._save_status.configure(text="✅ Đã lưu cài đặt!", text_color=Color.SUCCESS)
        self.after(3000, lambda: self._save_status.configure(text=""))

    def _on_clear_cache(self) -> None:
        """Xử lý nút dọn cache thủ công."""
        from core.cache_manager import CacheManager
        from tkinter import messagebox
        
        cm = CacheManager(self.config.ts4_docs_dir)
        if cm.clear_cache():
            messagebox.showinfo("Hoàn tất", "Đã dọn dẹp cache thành công!\nBạn có thể khởi động lại game để kiểm tra.")
        else:
            messagebox.showerror("Lỗi", "Không tìm thấy thư mục game để dọn cache. Hãy kiểm tra lại đường dẫn trong phần Thư mục TS4.")

    def _on_clear_empty_folders(self) -> None:
        """Xử lý nút dọn thư mục trống."""
        import threading
        from core.file_utils import remove_empty_folders
        from tkinter import messagebox
        
        mod_dir = self.config.mod_directory
        if not mod_dir or not os.path.exists(mod_dir):
            messagebox.showwarning("Cảnh báo", "Thư mục Mod không tồn tại.")
            return

        self._btn_clear_empty.configure(state="disabled", text="⏳ Đang dọn...")
        
        def run():
            count = remove_empty_folders(mod_dir)
            
            def done():
                self._btn_clear_empty.configure(state="normal", text="🗑️ Dọn Folder")
                messagebox.showinfo("Hoàn tất", f"Đã xóa {count} thư mục trống!")
            
            # Đẩy về main thread để hiện message box
            self.after(0, done)

        threading.Thread(target=run, daemon=True).start()

    # ─────────────────────────────────────────────────────────────────────────
    # Dynamic attribute helpers (generated bởi _add_path_row)
    # ─────────────────────────────────────────────────────────────────────────
    # Các thuộc tính _entry_mod_directory và _entry_staging_directory được tạo
    # động bởi setattr(...) bên trong _add_path_row, nên type-checker cần hint:

    if False:  # pragma: no cover – chỉ để IDE nhận diện
        _entry_mod_directory: ctk.CTkEntry
        _entry_staging_directory: ctk.CTkEntry
