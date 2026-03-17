"""
TabDownloads — Tab quản lý hàng đợi tải xuống.

View-layer thuần túy: nhận dữ liệu qua public methods, không chứa
business logic download.
"""
import logging
import customtkinter as ctk
from typing import Optional

from ._constants import Color, Status
from .widgets import DownloadItemWidget, StatsCard, LinkGrabberDialog

logger = logging.getLogger("ModManager.TabDownloads")


class TabDownloads(ctk.CTkFrame):
    """Tab quản lý tải xuống.

    Parameters
    ----------
    master:
        Widget cha.
    download_manager:
        Instance :class:`core.download_manager.DownloadManager`.
    """

    # ── Nhãn nút / trạng thái ─────────────────────────────────────────────────
    _LABEL_PAUSE    = "⏸ Tạm dừng"
    _LABEL_RESUME   = "▶ Tiếp tục"
    _STATUS_RUNNING = ("▶ Đang chạy",  Color.SUCCESS)
    _STATUS_PAUSED  = ("⏸ Đã tạm dừng", Color.WARNING)
    _STATUS_CANCELED = ("🗑 Đã hủy hàng đợi", Color.ERROR)
    
    # Giới hạn số lượng widget hiển thị để tránh lag UI (chỉ hiện 100 mục mới nhất)
    _MAX_DISPLAY_ITEMS = 100

    def __init__(self, master: ctk.CTkBaseClass, download_manager=None, **kwargs) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)
        self._download_manager = download_manager
        self._download_widgets: dict[str, DownloadItemWidget] = {}
        self._build_ui()

    # ─────────────────────────────────────────────────────────────────────────
    # Build UI
    # ─────────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)

        self._build_stats_row()
        self._build_input_row()
        self._build_controls_row()
        self._build_download_list()

    def _build_stats_row(self) -> None:
        """Hàng thẻ thống kê trên cùng."""
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid(row=0, column=0, padx=15, pady=(15, 10), sticky="ew")
        frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self._stat_queue = StatsCard(frame, "Hàng đợi", "0", "⏳", Color.WARNING)
        self._stat_queue.grid(row=0, column=0, padx=5, sticky="ew")

        self._stat_active = StatsCard(frame, "Đang tải", "0", "⬇️", Color.INFO)
        self._stat_active.grid(row=0, column=1, padx=5, sticky="ew")

        self._stat_done = StatsCard(frame, "Hoàn tất", "0", "✅", Color.SUCCESS)
        self._stat_done.grid(row=0, column=2, padx=5, sticky="ew")

        self._stat_session = StatsCard(frame, "TSR Session", "Tự do", "🔑", Color.TEXT_MUTED)
        self._stat_session.grid(row=0, column=3, padx=5, sticky="ew")

    def _build_input_row(self) -> None:
        """Hàng nhập URL và nút thêm / paste."""
        frame = ctk.CTkFrame(self, fg_color=Color.BG_CARD, corner_radius=12)
        frame.grid(row=1, column=0, padx=15, pady=5, sticky="ew")
        frame.grid_columnconfigure(0, weight=1)

        self._url_entry = ctk.CTkEntry(
            frame,
            placeholder_text="Dán link TSR / SFS / Folder vào đây...",
            height=40,
            font=ctk.CTkFont(size=13),
            fg_color=Color.BG_INPUT,
            border_color=Color.BG_DIVIDER,
            text_color=Color.TEXT_PRIMARY,
        )
        self._url_entry.grid(row=0, column=0, padx=(12, 5), pady=12, sticky="ew")
        self._url_entry.bind("<Return>", lambda _e: self._on_add_url())

        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.grid(row=0, column=1, padx=(5, 12), pady=12)

        ctk.CTkButton(
            btn_frame, text="➕ Thêm", width=80, height=40,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=Color.ACCENT, hover_color=Color.ACCENT_HOVER,
            command=self._on_add_url,
        ).pack(side="left", padx=2)

        ctk.CTkButton(
            btn_frame, text="📋 Paste", width=80, height=40,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=Color.PURPLE, hover_color=Color.PURPLE_HOVER,
            command=self._on_paste_add,
        ).pack(side="left", padx=2)

    def _build_controls_row(self) -> None:
        """Hàng nút điều khiển (tạm dừng, hủy, thử lại, xóa lịch sử)."""
        ctrl = ctk.CTkFrame(self, fg_color="transparent")
        ctrl.grid(row=2, column=0, padx=15, pady=(5, 0), sticky="ew")

        self._pause_btn = ctk.CTkButton(
            ctrl, text=self._LABEL_PAUSE, width=110, height=34,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=Color.WARNING, hover_color=Color.WARNING_HOVER,
            text_color=Color.BG_CARD,
            command=self._on_toggle_pause,
        )
        self._pause_btn.pack(side="left", padx=(0, 5))

        ctk.CTkButton(
            ctrl, text="🗑 Hủy tất cả", width=110, height=34,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=Color.ERROR, hover_color=Color.ERROR_HOVER,
            command=self._on_cancel_all,
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            ctrl, text="🔄 Tải lại lỗi", width=110, height=34,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=Color.INFO, hover_color=Color.INFO_HOVER,
            command=self._on_retry_failed,
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            ctrl, text="🧹 Xóa lịch sử", width=110, height=34,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=Color.TEXT_MUTED, hover_color="#475569",
            text_color=Color.TEXT_PRIMARY,
            command=self._on_clear_history,
        ).pack(side="left", padx=5)

        self._status_label = ctk.CTkLabel(
            ctrl, text=self._STATUS_RUNNING[0],
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self._STATUS_RUNNING[1],
        )
        self._status_label.pack(side="left", padx=15)

    def _build_download_list(self) -> None:
        """Khu vực danh sách file đang tải."""
        ctk.CTkLabel(
            self, text="📥 Hàng đợi tải xuống",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=Color.TEXT_PRIMARY, anchor="w",
        ).grid(row=3, column=0, padx=20, pady=(10, 0), sticky="nw")

        self._download_list = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=Color.BG_DIVIDER,
            scrollbar_button_hover_color=Color.ACCENT,
        )
        self._download_list.grid(row=4, column=0, padx=15, pady=(5, 15), sticky="nsew")
        self._download_list.grid_columnconfigure(0, weight=1)

        self._empty_label = ctk.CTkLabel(
            self._download_list,
            text="🎮 Chưa có file nào trong hàng đợi\nCopy link TSR/SFS hoặc dán vào ô phía trên",
            font=ctk.CTkFont(size=13),
            text_color=Color.TEXT_MUTED,
        )
        self._empty_label.grid(row=0, column=0, pady=40)

    # ─────────────────────────────────────────────────────────────────────────
    # Event handlers (UI → logic)
    # ─────────────────────────────────────────────────────────────────────────

    def _on_toggle_pause(self) -> None:
        """Chuyển đổi trạng thái tạm dừng / tiếp tục."""
        if not self._download_manager:
            return

        if self._download_manager.is_paused:
            self._download_manager.resume()
            self._pause_btn.configure(
                text=self._LABEL_PAUSE,
                fg_color=Color.WARNING, hover_color=Color.WARNING_HOVER,
            )
            self._set_status(*self._STATUS_RUNNING)
        else:
            self._download_manager.pause()
            self._pause_btn.configure(
                text=self._LABEL_RESUME,
                fg_color=Color.SUCCESS, hover_color=Color.SUCCESS_HOVER,
            )
            self._set_status(*self._STATUS_PAUSED)

    def _on_cancel_all(self) -> None:
        """Hủy tất cả file trong hàng đợi."""
        if not self._download_manager:
            return
            
        canceled_urls = self._download_manager.cancel_all()
        for url in canceled_urls:
            widget = self._download_widgets.pop(url, None)
            if widget:
                widget.destroy()
        
        # Reset nút pause về trạng thái mặc định
        self._pause_btn.configure(
            text=self._LABEL_PAUSE,
            fg_color=Color.WARNING, hover_color=Color.WARNING_HOVER,
        )
        self._set_status(*self._STATUS_CANCELED)
        
        if not self._download_widgets:
            self._empty_label.grid(row=0, column=0, pady=40)

    def _on_retry_failed(self) -> None:
        """Thử lại các file bị lỗi."""
        if not self._download_manager:
            return
        count = self._download_manager.retry_failed()
        if count > 0:
            self._set_status(f"🔄 Tải lại {count} file lỗi", Color.INFO)
        else:
            self._set_status("✓ Không có file lỗi", Color.SUCCESS)

    def _on_clear_history(self) -> None:
        """Xóa lịch sử các file đã hoàn tất hoặc bị lỗi."""
        if not self._download_manager:
            return

        cleared_urls: list[str] = self._download_manager.clear_history()
        for url in cleared_urls:
            widget = self._download_widgets.pop(url, None)
            if widget:
                widget.destroy()

        self._repack_widgets()

        if cleared_urls:
            self._set_status(f"🧹 Đã xóa {len(cleared_urls)} mục", Color.SUCCESS)

        if not self._download_widgets:
            self._empty_label.grid(row=0, column=0, pady=40)

    def _on_delete_item(self, url: str) -> None:
        """Xóa một mục tải xuống cụ thể."""
        if not self._download_manager:
            return
        
        if self._download_manager.remove_item(url):
            widget = self._download_widgets.pop(url, None)
            if widget:
                widget.destroy() # Pack tự động co lại, không cần repack!
            
            if not self._download_widgets:
                self._empty_label.grid(row=0, column=0, pady=40)

    # ── Drag and Drop Logic ──
    def _on_drag_start(self, event, widget):
        self._drag_widget = widget
        self._drag_start_y = event.y_root
        widget.configure(fg_color="#3d3d5c") # Highlight khi kéo
        widget.lift() # Đưa lên trên cùng

    def _on_drag_motion(self, event):
        if not hasattr(self, "_drag_widget"): return
        # Tính toán vị trí tương đối để hiển thị feedback trực quan (nếu cần)
        # Ở phiên bản đơn giản này chúng ta chỉ chờ thả chuột.
        pass

    def _on_drag_drop(self, event):
        if not hasattr(self, "_drag_widget"): return
        
        widget = self._drag_widget
        widget.configure(fg_color=Color.BG_CARD)
        
        # Tìm vị trí mới dựa trên y_root
        new_row = -1
        y_mouse = event.y_root
        
        # Lấy danh sách widget hiện tại (trừ cái đang kéo)
        other_widgets = [w for w in self._download_list.winfo_children() if w != widget and isinstance(w, DownloadItemWidget)]
        
        # Tìm vị trí chèn
        for i, other in enumerate(other_widgets):
            if y_mouse < other.winfo_rooty() + other.winfo_height() // 2:
                new_row = i
                break
        
        if new_row == -1:
            new_row = len(other_widgets)

        # Cập nhật logic trong DownloadManager
        # Lưu ý: Cần map từ row UI sang index trong queue. 
        # Vì _download_widgets có cả DONE và PENDING, chúng ta chỉ cho phép reorder PENDING.
        
        # Đơn giản hóa: Sắp xếp lại toàn bộ dict _download_widgets
        widgets_list = list(self._download_widgets.values())
        old_idx = widgets_list.index(widget)
        
        if old_idx != new_row:
            # Reorder dict
            items = list(self._download_widgets.items())
            item = items.pop(old_idx)
            items.insert(new_row, item)
            self._download_widgets = dict(items)
            
            # Nếu item đang PENDING, cập nhật DownloadManager
            # Tìm xem item này là item PENDING thứ mấy
            pending_items = [url for url, w in items if w._status_badge.cget("text").strip() == Status.WAITING]
            try:
                url = item[0]
                if url in pending_items:
                    new_pending_idx = pending_items.index(url)
                    self._download_manager.move_queued_item_by_url(url, new_pending_idx)
            except Exception as e:
                logger.error(f"Lỗi đồng bộ hàng đợi: {e}")
            
        self._repack_widgets() # Chỉ repack khi kéo thả
        del self._drag_widget

    def _on_add_url(self) -> None:
        """Thêm URL từ ô nhập tay."""
        url = self._url_entry.get().strip()
        if not url:
            return
        
        from core.sfs_downloader import SFSDownloader
        if SFSDownloader.is_folder_url(url):
            self._handle_sfs_folder(url)
        elif self._download_manager:
            self._download_manager.add_url(url)
        
        self._url_entry.delete(0, "end")

    def _on_paste_add(self) -> None:
        """Paste nhiều URL từ clipboard và thêm vào hàng đợi."""
        try:
            import clipboard
            text = clipboard.paste()
            if not text:
                return
            
            from core.sfs_downloader import SFSDownloader
            
            for line in text.strip().splitlines():
                line = line.strip()
                if not line: continue
                
                if SFSDownloader.is_folder_url(line):
                    self._handle_sfs_folder(line)
                elif self._download_manager:
                    self._download_manager.add_url(line)
        except Exception:
            pass

    def _handle_sfs_folder(self, folder_url: str) -> None:
        """Xử lý folder SFS bằng LinkGrabber."""
        if not self._download_manager:
            return

        self._set_status("🔍 Đang quét folder SFS...", Color.INFO)
        
        def _scan():
            try:
                metadata = self._download_manager.get_sfs_metadata(folder_url)
                if metadata:
                    self.after(0, lambda: self._show_linkgrabber(folder_url, metadata))
                else:
                    self.after(0, lambda: self._set_status("❌ Không tìm thấy file trong folder", Color.ERROR))
            except Exception as e:
                logger.error(f"Lỗi quét folder: {e}")
                self.after(0, lambda: self._set_status("❌ Lỗi quét folder", Color.ERROR))

        import threading
        threading.Thread(target=_scan, daemon=True).start()

    def _show_linkgrabber(self, folder_url: str, metadata: list[dict]) -> None:
        """Hiển thị LinkGrabber dialog."""
        self._set_status("✓ Đã quét xong folder", Color.SUCCESS)
        
        def _on_confirm(selected_urls: list[str]):
            for url in selected_urls:
                self._download_manager.add_url(url)
        
        LinkGrabberDialog(
            self.master, 
            title=f"SFS Folder: {folder_url.split('/')[-2]}", 
            metadata=metadata,
            on_confirm=_on_confirm
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Public API (logic → view)
    # ─────────────────────────────────────────────────────────────────────────

    def add_download_widget(self, url: str, source: str) -> None:
        """Thêm một mục tải xuống mới vào danh sách hiển thị.

        Bỏ qua nếu URL đã tồn tại. Được gọi từ main thread (qua ``after``).

        Parameters
        ----------
        url:
            URL của mục tải xuống.
        source:
            Nguồn (``"TSR"``, ``"SFS"``...).
        """
        if url in self._download_widgets:
            return

        self._empty_label.grid_forget()

        widget = DownloadItemWidget(
            self._download_list, url=url, source=source,
            on_delete=lambda: self._on_delete_item(url)
        )
        # Bind drag events
        widget.bind_drag_events(
            lambda e, w=widget: self._on_drag_start(e, w),
            self._on_drag_motion,
            self._on_drag_drop
        )
        
        widget.pack(padx=5, pady=3, fill="x", side="top")
        self._download_widgets[url] = widget

        # Cập nhật GUI ngay lập tức để người dùng thấy mượt hơn (mỗi 5 file)
        if len(self._download_widgets) % 5 == 0:
            self.update_idletasks()

        # Nếu vượt quá giới hạn, xóa bớt widget cũ nhất trong UI
        if len(self._download_widgets) > self._MAX_DISPLAY_ITEMS:
            # Lấy URL cũ nhất (đầu tiên trong dict)
            oldest_url = next(iter(self._download_widgets))
            oldest_widget = self._download_widgets.pop(oldest_url)
            oldest_widget.destroy()

    # Alias cũ để tương thích với app.py
    _add_download_widget = add_download_widget

    def update_download_item(self, url: str, status: str, progress: float, info: str = "") -> None:
        """Cập nhật trạng thái và tiến trình của một mục tải xuống.

        Parameters
        ----------
        url:
            URL của mục cần cập nhật.
        status:
            Trạng thái mới.
        progress:
            Tiến trình ``[0.0, 1.0]``.
        info:
            Thông tin phụ (tên file, tốc độ...).
        """
        widget = self._download_widgets.get(url)
        if widget:
            widget.update_status(status, progress, info)

    def update_stats(
        self,
        queue: int,
        active: int,
        done: int,
        session_valid: bool,
    ) -> None:
        """Cập nhật toàn bộ thẻ thống kê trên đầu tab.

        Parameters
        ----------
        queue:
            Số lượng mục đang chờ.
        active:
            Số lượng mục đang tải.
        done:
            Số lượng mục hoàn tất.
        session_valid:
            Trạng thái phiên đăng nhập TSR.
        """
        self._stat_queue.update_value(str(queue))
        self._stat_active.update_value(str(active))
        self._stat_done.update_value(str(done))

        if session_valid:
            self._stat_session.update_value("Đã kết nối")
            self._stat_session.value_label.configure(text_color=Color.SUCCESS)
        else:
            self._stat_session.update_value("Tự do")
            self._stat_session.value_label.configure(text_color=Color.TEXT_MUTED)

    # ─────────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _set_status(self, text: str, color: str) -> None:
        """Cập nhật nhãn trạng thái phía dưới các nút điều khiển."""
        self._status_label.configure(text=text, text_color=color)

    def _repack_widgets(self) -> None:
        """Sắp xếp lại widget sau khi xóa hoặc kéo thả."""
        # Clean up existing packing
        for widget in self._download_widgets.values():
            widget.pack_forget()
        
        # Re-pack in new order
        for widget in self._download_widgets.values():
            widget.pack(padx=5, pady=3, fill="x", side="top")
