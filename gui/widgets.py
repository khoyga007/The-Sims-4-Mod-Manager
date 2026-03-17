"""
Widgets — Các widget tùy chỉnh dùng chung trong toàn bộ GUI.

Mỗi widget là một lớp tự-chứa (self-contained), không phụ thuộc vào
business logic hay state bên ngoài.
"""
from __future__ import annotations

import customtkinter as ctk
from typing import Callable, Optional

from ._constants import Color, Status


# ─── Status badge ─────────────────────────────────────────────────────────────

# Map trạng thái → màu nền badge
_STATUS_COLOR: dict[str, str] = {
    Status.WAITING:     Color.WARNING,
    Status.TICKET:      Color.VIOLET,
    Status.DELAY:       Color.ORANGE,
    Status.DOWNLOADING: Color.INFO,
    Status.UNPACKING:   Color.PURPLE,
    Status.SORTING:     Color.CYAN,
    Status.DONE:        Color.SUCCESS,
    Status.ERROR:       Color.ERROR,
}

_FALLBACK_COLOR = "#6b7280"


class StatusBadge(ctk.CTkLabel):
    """Badge nhỏ hiển thị trạng thái tải xuống với màu sắc ngữ nghĩa.

    Parameters
    ----------
    master:
        Widget cha.
    status:
        Trạng thái khởi đầu (dùng hằng số :class:`Status`).
    """

    def __init__(self, master: ctk.CTkBaseClass, status: str = Status.WAITING, **kwargs) -> None:
        color = _STATUS_COLOR.get(status, _FALLBACK_COLOR)
        super().__init__(
            master,
            text=f"  {status}  ",
            fg_color=color,
            corner_radius=6,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="white",
            **kwargs,
        )

    def set_status(self, status: str) -> None:
        """Cập nhật nhãn và màu badge.

        Parameters
        ----------
        status:
            Trạng thái mới (dùng hằng số :class:`Status`).
        """
        color = _STATUS_COLOR.get(status, _FALLBACK_COLOR)
        self.configure(text=f"  {status}  ", fg_color=color)


# ─── Download item widget ──────────────────────────────────────────────────────

class DownloadItemWidget(ctk.CTkFrame):
    """Hiển thị một mục trong hàng đợi tải xuống (URL, nguồn, tiến độ).

    Parameters
    ----------
    master:
        Widget cha.
    url:
        URL đang tải.
    source:
        Chuỗi nguồn (``"TSR"``, ``"SFS"`` hoặc khác).
    """

    _URL_MAX_LEN = 60
    _SOURCE_ICONS: dict[str, str] = {
        "TSR":    "🌐 TSR",
        "SFS":    "📁 SFS",
    }
    _SOURCE_FALLBACK = "🔗 DIRECT"

    def __init__(self, master: ctk.CTkBaseClass, url: str, source: str, on_delete: Optional[Callable[[], None]] = None, **kwargs) -> None:
        super().__init__(master, fg_color=Color.BG_CARD, corner_radius=8, **kwargs)
        self._url = url
        self._on_delete = on_delete
        self.grid_columnconfigure(1, weight=1)

        # Xác định icon nguồn
        source_text = next(
            (icon for key, icon in self._SOURCE_ICONS.items() if key in source),
            self._SOURCE_FALLBACK,
        )

        # ── Cột 0: Drag Handle (⠿) ──
        self._drag_handle = ctk.CTkLabel(
            self, text="⠿", font=ctk.CTkFont(size=18),
            width=30, cursor="fleur", text_color=Color.TEXT_DISABLED
        )
        self._drag_handle.grid(row=0, column=0, rowspan=3, padx=(5, 0), sticky="ns")

        # ── Cột 1: nhãn nguồn ──
        ctk.CTkLabel(
            self,
            text=source_text,
            font=ctk.CTkFont(size=12, weight="bold"),
            width=70,
            text_color=Color.ACCENT_LIGHT,
        ).grid(row=0, column=1, padx=(5, 5), pady=(8, 0), sticky="w")

        # ── Cột 1: URL (cắt ngắn nếu quá dài) ──
        display_url = url if len(url) < self._URL_MAX_LEN else url[:self._URL_MAX_LEN - 3] + "..."
        ctk.CTkLabel(
            self,
            text=display_url,
            font=ctk.CTkFont(size=11),
            text_color=Color.TEXT_SECONDARY,
            anchor="w",
        ).grid(row=0, column=2, padx=5, pady=(8, 0), sticky="ew")

        # ── Cột 2: badge trạng thái ──
        self._status_badge = StatusBadge(self, status=Status.WAITING)
        self._status_badge.grid(row=0, column=3, padx=(5, 5), pady=(8, 0))

        # ── Nút xóa (🗑️) ──
        self._delete_btn = ctk.CTkButton(
            self, text="×", width=24, height=24,
            fg_color="transparent", hover_color=Color.ERROR,
            text_color=Color.TEXT_DISABLED,
            command=self._on_delete_clicked
        )
        self._delete_btn.grid(row=0, column=4, padx=(0, 10), pady=(8, 0))

        # ── Hàng 1: thanh tiến trình ──
        self._progress_bar = ctk.CTkProgressBar(
            self, height=6, corner_radius=3,
            fg_color=Color.BG_INPUT, progress_color=Color.ACCENT,
        )
        self._progress_bar.grid(row=1, column=1, columnspan=4, padx=10, pady=(5, 3), sticky="ew")
        self._progress_bar.set(0)

        # ── Hàng 2: nhãn thông tin phụ ──
        self._info_label = ctk.CTkLabel(
            self, text="",
            font=ctk.CTkFont(size=10),
            text_color=Color.TEXT_MUTED,
            anchor="w",
        )
        self._info_label.grid(row=2, column=1, columnspan=4, padx=10, pady=(0, 8), sticky="ew")

    def _on_delete_clicked(self) -> None:
        if self._on_delete:
            self._on_delete()

    def bind_drag_events(self, on_start, on_drag, on_drop) -> None:
        """Gán các sự kiện kéo thả cho drag handle."""
        self._drag_handle.bind("<ButtonPress-1>", on_start)
        self._drag_handle.bind("<B1-Motion>", on_drag)
        self._drag_handle.bind("<ButtonRelease-1>", on_drop)

    def update_status(self, status: str, progress: float = 0.0, info: str = "") -> None:
        """Cập nhật badge, thanh tiến trình và nhãn thông tin."""
        self._status_badge.set_status(status)
        
        # Chỉ cập nhật progress nếu có sự thay đổi đáng kể (tránh làm GUI quá tải)
        current_p = self._progress_bar.get()
        new_p = max(0.0, min(1.0, progress))
        if abs(current_p - new_p) > 0.001:
            self._progress_bar.set(new_p)
            
        if info and self._info_label.cget("text") != info:
            self._info_label.configure(text=info)


# ─── Mod item widget ───────────────────────────────────────────────────────────

class ModItemWidget(ctk.CTkFrame):
    """Hiển thị một mod trong danh sách quản lý với toggle bật/tắt.

    Parameters
    ----------
    master:
        Widget cha.
    name:
        Tên mod.
    category:
        Thể loại / thư mục.
    size:
        Kích thước dạng chuỗi (``"12.3 MB"``).
    enabled:
        Trạng thái bật/tắt ban đầu.
    on_toggle:
        Callback nhận giá trị bool mới khi người dùng toggle.
    on_delete:
        Callback khi người dùng nhấn nút xóa.
    """

    def __init__(
        self,
        master: ctk.CTkBaseClass,
        name: str,
        category: str,
        size: str,
        enabled: bool = True,
        on_toggle: Optional[Callable[[bool], None]] = None,
        on_delete: Optional[Callable[[], None]] = None,
        **kwargs,
    ) -> None:
        super().__init__(master, fg_color=Color.BG_CARD, corner_radius=8, height=45, **kwargs)
        self.grid_columnconfigure(1, weight=1)

        # Toggle
        self._toggle = ctk.CTkSwitch(
            self, text="", width=40,
            onvalue=True, offvalue=False,
            command=lambda: on_toggle(self._toggle.get()) if on_toggle else None,
            progress_color=Color.ACCENT,
            button_color=Color.ACCENT_LIGHT,
            fg_color=Color.BG_INPUT,
        )
        if enabled:
            self._toggle.select()
        else:
            self._toggle.deselect()
        self._toggle.grid(row=0, column=0, padx=(10, 5), pady=8)

        # Tên mod
        ctk.CTkLabel(
            self, text=name,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=Color.TEXT_PRIMARY, anchor="w",
        ).grid(row=0, column=1, padx=5, pady=8, sticky="w")

        # Thể loại
        ctk.CTkLabel(
            self, text=category,
            font=ctk.CTkFont(size=10),
            fg_color=Color.BG_INPUT, corner_radius=4,
            text_color=Color.TEXT_SECONDARY,
        ).grid(row=0, column=2, padx=5, pady=8)

        # Kích thước
        ctk.CTkLabel(
            self, text=size,
            font=ctk.CTkFont(size=10),
            text_color=Color.TEXT_MUTED,
        ).grid(row=0, column=3, padx=5, pady=8)

        # Nút xóa
        ctk.CTkButton(
            self, text="🗑", width=30, height=30,
            fg_color="transparent", hover_color=Color.ERROR,
            font=ctk.CTkFont(size=14),
            command=on_delete,
        ).grid(row=0, column=4, padx=(5, 10), pady=8)


# ─── Stats card ───────────────────────────────────────────────────────────────

class StatsCard(ctk.CTkFrame):
    """Thẻ hiển thị một chỉ số thống kê (icon + giá trị + tiêu đề).

    Parameters
    ----------
    master:
        Widget cha.
    title:
        Tiêu đề bên dưới.
    value:
        Giá trị hiển thị lớn.
    icon:
        Emoji icon phía trên.
    color:
        Màu chữ cho nhãn giá trị.
    """

    def __init__(
        self,
        master: ctk.CTkBaseClass,
        title: str,
        value: str,
        icon: str = "",
        color: str = Color.ACCENT,
        **kwargs,
    ) -> None:
        super().__init__(master, fg_color=Color.BG_CARD, corner_radius=12, **kwargs)

        ctk.CTkLabel(self, text=icon, font=ctk.CTkFont(size=24)).pack(pady=(12, 0))

        self.value_label = ctk.CTkLabel(
            self, text=value,
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=color,
        )
        self.value_label.pack(pady=(2, 0))

        ctk.CTkLabel(
            self, text=title,
            font=ctk.CTkFont(size=11),
            text_color=Color.TEXT_SECONDARY,
        ).pack(pady=(0, 12))

    def update_value(self, value: str) -> None:
        """Cập nhật giá trị hiển thị.

        Parameters
        ----------
        value:
            Chuỗi giá trị mới.
        """
        self.value_label.configure(text=value)

# ─── LinkGrabber Dialog (JDownloader style) ──────────────────────────────────

class LinkGrabberDialog(ctk.CTkToplevel):
    """Dialog hiển thị danh sách file trong folder SFS để chọn lọc trước khi tải.
    
    Parameters
    ----------
    master:
        Widget cha.
    title:
        Tiêu đề dialog.
    metadata:
        Danh sách [{"name": str, "size": str, "url": str, ...}]
    on_confirm:
        Callback nhận danh sách URL được chọn.
    """

    def __init__(self, master, title: str, metadata: list[dict], on_confirm: Callable[[list[str]], None]):
        super().__init__(master)
        self.title(title)
        self.geometry("600x500")
        self.after(10, self.focus_force) # Đưa lên trên cùng
        self.grab_set() # Ngăn tương tác với cửa sổ chính

        self._on_confirm = on_confirm
        self._metadata = metadata
        self._checkboxes: list[ctk.CTkCheckBox] = []

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # ── Header ──
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, padx=20, pady=15, sticky="ew")
        
        ctk.CTkLabel(
            header, text="🔍 LinkGrabber: Chọn file cần tải",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=Color.ACCENT
        ).pack(side="left")

        # ── Nút chọn nhanh ──
        btn_all = ctk.CTkFrame(self, fg_color="transparent")
        btn_all.grid(row=0, column=0, padx=20, pady=(0, 5), sticky="e")
        
        ctk.CTkButton(
            btn_all, text="Tất cả", width=60, height=24, font=ctk.CTkFont(size=11),
            fg_color=Color.BG_DIVIDER, text_color=Color.TEXT_PRIMARY,
            command=self._select_all
        ).pack(side="left", padx=2)
        
        ctk.CTkButton(
            btn_all, text="Bỏ chọn", width=60, height=24, font=ctk.CTkFont(size=11),
            fg_color=Color.BG_DIVIDER, text_color=Color.TEXT_PRIMARY,
            command=self._deselect_all
        ).pack(side="left", padx=2)

        # ── Danh sách file (Scrollable) ──
        self._scroll_frame = ctk.CTkScrollableFrame(
            self, fg_color=Color.BG_CARD, border_width=1, border_color=Color.BG_DIVIDER
        )
        self._scroll_frame.grid(row=1, column=0, padx=20, pady=5, sticky="nsew")
        self._scroll_frame.grid_columnconfigure(0, weight=1)

        for i, item in enumerate(metadata):
            cb_frame = ctk.CTkFrame(self._scroll_frame, fg_color="transparent")
            cb_frame.pack(fill="x", padx=10, pady=5)
            
            cb = ctk.CTkCheckBox(
                cb_frame, text=item["name"], 
                font=ctk.CTkFont(size=12),
                checkmark_color=Color.ACCENT,
                border_color=Color.ACCENT_LIGHT
            )
            cb.select() # Mặc định chọn tất cả
            cb.pack(side="left", fill="x", expand=True)
            self._checkboxes.append(cb)
            
            ctk.CTkLabel(
                cb_frame, text=item["size"], 
                font=ctk.CTkFont(size=11),
                text_color=Color.TEXT_MUTED
            ).pack(side="right", padx=5)

        # ── Footer ──
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=2, column=0, padx=20, pady=20, sticky="ew")
        
        ctk.CTkButton(
            footer, text="🚀 Thêm vào hàng đợi", 
            fg_color=Color.ACCENT, hover_color=Color.ACCENT_HOVER,
            command=self._confirm
        ).pack(side="right", padx=5)
        
        ctk.CTkButton(
            footer, text="Hủy", 
            fg_color="transparent", border_width=1, border_color=Color.BG_DIVIDER,
            command=self.destroy
        ).pack(side="right", padx=5)

    def _select_all(self):
        for cb in self._checkboxes: cb.select()

    def _deselect_all(self):
        for cb in self._checkboxes: cb.deselect()

    def _confirm(self):
        selected_urls = []
        for i, cb in enumerate(self._checkboxes):
            if cb.get():
                selected_urls.append(self._metadata[i]["url"])
        
        if selected_urls:
            self._on_confirm(selected_urls)
            self.destroy()
        else:
            # Thông báo nếu không chọn cái nào? Cho đơn giản là đóng luôn
            self.destroy()
