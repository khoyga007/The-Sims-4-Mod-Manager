"""
TabCreators — Tab quản lý danh sách tác giả yêu thích.

Dữ liệu được đọc/ghi từ ``creators.json`` cạnh thư mục gốc project.
"""
from __future__ import annotations

import json
import os
import webbrowser
from typing import Optional

import customtkinter as ctk

from ._constants import Color
from core.config_manager import ConfigManager


# ─── Dữ liệu mặc định ────────────────────────────────────────────────────────

_DEFAULT_CREATORS: list[dict[str, str]] = [
    {"name": "DallasGirl",              "url": "https://dallasgirl79.tumblr.com/"},
    {"name": "Sentate",                 "url": "https://www.patreon.com/sentate"},
    {"name": "Gorilla Gorilla Gorilla", "url": "https://kemono.su/patreon/user/29845322"},
    {"name": "Darte77",                 "url": "https://www.patreon.com/darte77"},
]

_URL_MAX_LEN = 60


# ─── Tab chính ───────────────────────────────────────────────────────────────

class TabCreators(ctk.CTkFrame):
    """Tab quản lý danh sách Creator yêu thích.

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

        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self._creators_file = os.path.join(project_root, "creators.json")

        self._creators: list[dict[str, str]] = self._load_creators()
        self._item_widgets: list[ctk.CTkFrame] = []

        self._build_ui()
        self._refresh_list()

    # ─────────────────────────────────────────────────────────────────────────
    # Persistence
    # ─────────────────────────────────────────────────────────────────────────

    def _load_creators(self) -> list[dict[str, str]]:
        """Đọc danh sách creators từ file JSON (hoặc trả về mặc định)."""
        if os.path.exists(self._creators_file):
            try:
                with open(self._creators_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return list(_DEFAULT_CREATORS)

    def _save_creators(self) -> None:
        """Lưu danh sách creators xuống file JSON."""
        try:
            with open(self._creators_file, "w", encoding="utf-8") as f:
                json.dump(self._creators, f, indent=4, ensure_ascii=False)
        except OSError as exc:
            print(f"Lỗi lưu danh sách creators: {exc}")

    # ─────────────────────────────────────────────────────────────────────────
    # Build UI
    # ─────────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, padx=15, pady=(15, 10), sticky="ew")
        header.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            header, text="⭐ Tác giả yêu thích",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=Color.TEXT_PRIMARY,
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            header, text="➕ Thêm tác giả",
            width=120, height=36,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=Color.ACCENT, hover_color=Color.ACCENT_HOVER,
            command=self._on_add,
        ).grid(row=0, column=2, sticky="e")

        # Scrollable list
        self._scroll = ctk.CTkScrollableFrame(
            self, fg_color=Color.BG_SURFACE,
            scrollbar_button_color=Color.BG_DIVIDER,
            scrollbar_button_hover_color=Color.ACCENT,
            corner_radius=10,
        )
        self._scroll.grid(row=1, column=0, padx=15, pady=(0, 15), sticky="nsew")
        self._scroll.grid_columnconfigure(0, weight=1)

    # ─────────────────────────────────────────────────────────────────────────
    # List rendering
    # ─────────────────────────────────────────────────────────────────────────

    def _refresh_list(self) -> None:
        """Xóa và vẽ lại toàn bộ danh sách creators."""
        for widget in self._item_widgets:
            widget.destroy()
        self._item_widgets.clear()

        if not self._creators:
            lbl = ctk.CTkLabel(
                self._scroll,
                text="Chưa có tác giả nào trong danh sách.",
                font=ctk.CTkFont(size=14),
                text_color=Color.TEXT_MUTED,
            )
            lbl.grid(row=0, column=0, pady=50)
            self._item_widgets.append(lbl)
            return

        for i, creator in enumerate(self._creators):
            item = _CreatorItemWidget(
                self._scroll, creator,
                on_delete=self._on_delete,
                on_edit=self._on_edit,
            )
            item.grid(row=i, column=0, padx=5, pady=5, sticky="ew")
            self._item_widgets.append(item)

    # ─────────────────────────────────────────────────────────────────────────
    # Event handlers
    # ─────────────────────────────────────────────────────────────────────────

    def _on_add(self) -> None:
        dialog = _CreatorDialog(self, title="Thêm tác giả")
        self.wait_window(dialog)
        if dialog.result:
            self._creators.append(dialog.result)
            self._save_creators()
            self._refresh_list()

    def _on_edit(self, creator: dict[str, str]) -> None:
        dialog = _CreatorDialog(self, title="Sửa tác giả", creator_data=creator)
        self.wait_window(dialog)
        if dialog.result:
            try:
                idx = self._creators.index(creator)
                self._creators[idx] = dialog.result
            except ValueError:
                pass
            self._save_creators()
            self._refresh_list()

    def _on_delete(self, creator: dict[str, str]) -> None:
        try:
            self._creators.remove(creator)
        except ValueError:
            pass
        self._save_creators()
        self._refresh_list()


# ─── Widget một dòng creator ─────────────────────────────────────────────────

class _CreatorItemWidget(ctk.CTkFrame):
    """Hiển thị một tác giả (icon + tên + URL + nút Edit/Delete).

    Parameters
    ----------
    master:
        Widget cha.
    creator:
        Dict ``{"name": str, "url": str}``.
    on_delete:
        Callback nhận ``creator`` dict khi nhấn xóa.
    on_edit:
        Callback nhận ``creator`` dict khi nhấn sửa.
    """

    def __init__(
        self,
        master: ctk.CTkBaseClass,
        creator: dict[str, str],
        on_delete,
        on_edit,
        **kwargs,
    ) -> None:
        super().__init__(master, fg_color=Color.BG_CARD, corner_radius=8, **kwargs)
        self._creator = creator
        self.grid_columnconfigure(1, weight=1)

        # Icon
        ctk.CTkLabel(self, text="🎭", font=ctk.CTkFont(size=24)).grid(
            row=0, column=0, padx=15, pady=10
        )

        # Tên + URL
        info = ctk.CTkFrame(self, fg_color="transparent")
        info.grid(row=0, column=1, pady=10, sticky="ew")

        ctk.CTkLabel(
            info, text=creator.get("name", "Unknown"),
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=Color.TEXT_PRIMARY,
        ).pack(anchor="w")

        url = creator.get("url", "")
        display_url = url if len(url) < _URL_MAX_LEN else url[:_URL_MAX_LEN - 3] + "..."
        url_lbl = ctk.CTkLabel(
            info, text=display_url,
            font=ctk.CTkFont(size=11),
            text_color=Color.TEXT_SECONDARY,
            cursor="hand2",
        )
        url_lbl.pack(anchor="w")
        url_lbl.bind("<Button-1>", lambda _e: webbrowser.open(url))
        url_lbl.bind("<Enter>", lambda _e: url_lbl.configure(text_color=Color.ACCENT_LIGHT))
        url_lbl.bind("<Leave>", lambda _e: url_lbl.configure(text_color=Color.TEXT_SECONDARY))

        # Nút
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=0, column=2, padx=15, pady=10, sticky="e")

        ctk.CTkButton(
            btn_frame, text="✏️", width=30, height=30,
            fg_color="transparent", hover_color=Color.BG_DIVIDER,
            command=lambda: on_edit(self._creator),
        ).pack(side="left", padx=2)

        ctk.CTkButton(
            btn_frame, text="🗑", width=30, height=30,
            fg_color="transparent", hover_color=Color.ERROR,
            text_color=Color.ERROR,
            command=lambda: on_delete(self._creator),
        ).pack(side="left", padx=2)


# ─── Dialog thêm / sửa ───────────────────────────────────────────────────────

class _CreatorDialog(ctk.CTkToplevel):
    """Dialog nhập tên và link tác giả.

    Attributes
    ----------
    result:
        ``{"name": str, "url": str}`` nếu người dùng nhấn Lưu, ngược lại ``None``.
    """

    def __init__(
        self,
        parent: ctk.CTkBaseClass,
        title: str,
        creator_data: Optional[dict[str, str]] = None,
    ) -> None:
        super().__init__(parent)
        self.result: Optional[dict[str, str]] = None

        self.title(title)
        self.geometry("450x250")
        self.resizable(False, False)
        self.configure(fg_color=Color.BG_SURFACE)
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self._center_on(parent)

        # Form
        form = ctk.CTkFrame(self, fg_color=Color.BG_CARD, corner_radius=10)
        form.pack(fill="both", expand=True, padx=15, pady=15)

        ctk.CTkLabel(form, text="Tên tác giả:", font=ctk.CTkFont(size=13)).grid(
            row=0, column=0, padx=15, pady=(20, 5), sticky="w"
        )
        self._name_entry = ctk.CTkEntry(
            form, width=300, fg_color=Color.BG_INPUT, border_color=Color.BG_DIVIDER
        )
        self._name_entry.grid(row=0, column=1, padx=(0, 15), pady=(20, 5), sticky="w")

        ctk.CTkLabel(form, text="Đường link:", font=ctk.CTkFont(size=13)).grid(
            row=1, column=0, padx=15, pady=10, sticky="w"
        )
        self._url_entry = ctk.CTkEntry(
            form, width=300, fg_color=Color.BG_INPUT, border_color=Color.BG_DIVIDER
        )
        self._url_entry.grid(row=1, column=1, padx=(0, 15), pady=10, sticky="w")

        if creator_data:
            self._name_entry.insert(0, creator_data.get("name", ""))
            self._url_entry.insert(0, creator_data.get("url", ""))

        # Buttons
        btn_frame = ctk.CTkFrame(form, fg_color="transparent")
        btn_frame.grid(row=2, column=0, columnspan=2, pady=(15, 0))

        ctk.CTkButton(
            btn_frame, text="Lưu", width=100, height=36,
            fg_color=Color.SUCCESS, hover_color=Color.SUCCESS_HOVER,
            command=self._on_save,
        ).pack(side="left", padx=10)

        ctk.CTkButton(
            btn_frame, text="Hủy", width=100, height=36,
            fg_color=Color.TEXT_MUTED, hover_color="#475569",
            command=self.destroy,
        ).pack(side="left", padx=10)

    def _center_on(self, parent: ctk.CTkBaseClass) -> None:
        """Canh giữa dialog trên parent."""
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - 450) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - 250) // 2
        self.geometry(f"+{x}+{y}")

    def _on_save(self) -> None:
        name = self._name_entry.get().strip()
        url = self._url_entry.get().strip()
        if name and url:
            self.result = {"name": name, "url": url}
            self.destroy()
