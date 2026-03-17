from __future__ import annotations

import logging
from typing import Optional, List

import customtkinter as ctk
from gui._constants import Color
from core.config_manager import ConfigManager
from core.profile_manager import ProfileManager, Profile

logger = logging.getLogger("ModManager.TabProfiles")

class TabProfiles(ctk.CTkFrame):
    """Tab quản lý Hồ sơ Mod (Profiles)."""

    def __init__(
        self,
        master: any,
        config: Optional[ConfigManager] = None,
        profile_manager: Optional[ProfileManager] = None,
        **kwargs
    ):
        super().__init__(master, **kwargs)
        self.config = config or ConfigManager()
        self.pm = profile_manager or ProfileManager(self.config)
        self._profiles: List[str] = []

        self._build_ui()
        self.refresh_list()

    def _build_ui(self) -> None:
        """Xây dựng giao diện tab."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # Header & Save Section
        header_frame = ctk.CTkFrame(self, fg_color=Color.BG_CARD, corner_radius=12)
        header_frame.grid(row=0, column=0, padx=15, pady=15, sticky="ew")
        header_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            header_frame, text="📄 Quản lý Hồ sơ Mod",
            font=ctk.CTkFont(size=18, weight="bold")
        ).grid(row=0, column=0, columnspan=3, padx=20, pady=(15, 5), sticky="w")

        ctk.CTkLabel(
            header_frame, text="Lưu trạng thái bật/tắt của tất cả mod hiện tại thành một hồ sơ để đổi nhanh.",
            font=ctk.CTkFont(size=12), text_color=Color.TEXT_SECONDARY
        ).grid(row=1, column=0, columnspan=3, padx=20, pady=(0, 15), sticky="w")

        # Create Profile Input
        ctk.CTkLabel(header_frame, text="Tên hồ sơ mới:").grid(row=2, column=0, padx=(20, 5), pady=15)
        self._name_entry = ctk.CTkEntry(header_frame, placeholder_text="Ví dụ: Chỉ mod xây dựng, Full CC...", height=35)
        self._name_entry.grid(row=2, column=1, padx=5, pady=15, sticky="ew")
        
        self._save_btn = ctk.CTkButton(
            header_frame, text="💾 Lưu Hồ sơ",
            fg_color=Color.ACCENT, hover_color=Color.ACCENT_HOVER,
            command=self._on_save_clicked, height=35
        )
        self._save_btn.grid(row=2, column=2, padx=(5, 20), pady=15)

        # Profiles List Header
        ctk.CTkLabel(
            self, text="📋 Danh sách Hồ sơ đã lưu",
            font=ctk.CTkFont(size=15, weight="bold")
        ).grid(row=1, column=0, padx=20, pady=(10, 5), sticky="w")

        # Scrollable Area for Profiles
        self._scroll_frame = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=Color.BG_DIVIDER
        )
        self._scroll_frame.grid(row=2, column=0, padx=15, pady=5, sticky="nsew")
        self._scroll_frame.grid_columnconfigure(0, weight=1)

        self._empty_label = ctk.CTkLabel(
            self._scroll_frame, text="Chưa có hồ sơ nào. Hãy lưu trạng thái mod của bạn ở trên!",
            text_color=Color.TEXT_DISABLED, pady=40
        )

    def refresh_list(self) -> None:
        """Tải lại danh sách hồ sơ từ ổ đĩa và vẽ lại UI."""
        # Xóa các item cũ
        for child in self._scroll_frame.winfo_children():
            child.destroy()

        self._profiles = self.pm.list_profiles()
        
        if not self._profiles:
            self._empty_label = ctk.CTkLabel(
                self._scroll_frame, text="Chưa có hồ sơ nào. Hãy lưu trạng thái mod của bạn ở trên!",
                text_color=Color.TEXT_DISABLED, pady=40
            )
            self._empty_label.pack()
            return

        for name in sorted(self._profiles):
            self._add_profile_card(name)

    def _add_profile_card(self, name: str) -> None:
        """Thêm một card hiển thị hồ sơ."""
        profile = self.pm.get_profile(name)
        if not profile:
            return

        card = ctk.CTkFrame(self._scroll_frame, fg_color=Color.BG_CARD, corner_radius=10)
        card.pack(fill="x", pady=5)
        card.grid_columnconfigure(0, weight=1)

        # Info
        info_frame = ctk.CTkFrame(card, fg_color="transparent")
        info_frame.grid(row=0, column=0, padx=15, pady=10, sticky="w")
        
        ctk.CTkLabel(
            info_frame, text=name,
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w")
        
        ctk.CTkLabel(
            info_frame, text=profile.description,
            font=ctk.CTkFont(size=11), text_color=Color.TEXT_SECONDARY
        ).pack(anchor="w")

        # Actions
        actions_frame = ctk.CTkFrame(card, fg_color="transparent")
        actions_frame.grid(row=0, column=1, padx=15, pady=10, sticky="e")

        apply_btn = ctk.CTkButton(
            actions_frame, text="🚀 Áp dụng", width=100, height=30,
            fg_color=Color.SUCCESS, hover_color=Color.SUCCESS_HOVER,
            command=lambda n=name: self._on_apply_clicked(n)
        )
        apply_btn.pack(side="left", padx=5)

        delete_btn = ctk.CTkButton(
            actions_frame, text="🗑️ Xóa", width=70, height=30,
            fg_color="#e74c3c", hover_color="#c0392b",
            command=lambda n=name: self._on_delete_clicked(n)
        )
        delete_btn.pack(side="left", padx=5)

    def _on_save_clicked(self) -> None:
        name = self._name_entry.get().strip()
        if not name:
            return
        
        # Kiểm tra trùng tên (có thể ghi đè)
        if name in self._profiles:
            # Ở đây có thể thêm box xác nhận, nhưng đơn giản thì cứ ghi đè
            pass

        self._save_btn.configure(state="disabled", text="⏳ Đang lưu...")
        self.after(100, lambda: self._do_save(name))

    def _do_save(self, name: str) -> None:
        p = self.pm.create_profile(name)
        self._save_btn.configure(state="normal", text="💾 Lưu Hồ sơ")
        if p:
            self._name_entry.delete(0, "end")
            self.refresh_list()

    def _on_apply_clicked(self, name: str) -> None:
        # Trong một ứng dụng thực tế, nên dùng thread để tránh treo UI nếu mod dir quá lớn
        # Nhưng với mod dir bình thường (~vài trăm file), os.rename rất nhanh.
        success = self.pm.apply_profile(name)
        if success:
            # Thông báo cho người dùng (có thể dùng một toast hoặc label)
            logger.info(f"Đã áp dụng hồ sơ: {name}")

    def _on_delete_clicked(self, name: str) -> None:
        if self.pm.delete_profile(name):
            self.refresh_list()
