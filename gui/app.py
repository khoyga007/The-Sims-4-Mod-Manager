"""
App — Cửa sổ chính Sims 4 Mod Manager.

Khởi tạo các service layer (config, download, clipboard),
xây dựng sidebar + các tab, và kết nối callbacks giữa các tầng.
"""
from __future__ import annotations

import logging
import os
import sys
import tempfile
from typing import Optional

import customtkinter as ctk
from tkinterdnd2 import TkinterDnD, DND_FILES

# Đảm bảo project root nằm trong sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gui._constants import Color
from gui.tab_downloads import TabDownloads
from gui.tab_mods import TabMods
from gui.tab_creators import TabCreators
from gui.tab_settings import TabSettings
from gui.tab_debug import TabDebug
from core.config_manager import ConfigManager
from core.download_manager import DownloadManager
from core.clipboard_monitor import ClipboardMonitor
from core.game_launcher import GameLauncher
from core.profile_manager import ProfileManager
from core.cache_manager import CacheManager
from gui.tab_profiles import TabProfiles
from gui.tab_merger import TabMerger
from gui.tab_orphans import TabOrphans

logger = logging.getLogger("ModManager.App")


# ─── Cấu hình điều hướng ─────────────────────────────────────────────────────

_NAV_ITEMS: list[tuple[str, str, int]] = [
    ("downloads", "⬇️  Tải xuống",   2),
    ("mods",      "📦  Quản lý Mod", 3),
    ("merger",    "🔗  Gộp Mod",    4),
    ("orphans",   "👻  Dọn Mod lỗi", 5),
    ("profiles",  "📄  Hồ sơ Mod",   6),
    ("creators",  "⭐  Tác giả",     7),
    ("debug",     "🔧  Gỡ lỗi",      8),
    ("settings",  "⚙️  Cài đặt",    9),
]; _SPACER_ROW = 10


# ─── Main window ─────────────────────────────────────────────────────────────

class ModManagerApp(ctk.CTk, TkinterDnD.DnDWrapper):
    """Cửa sổ chính Sims 4 Mod Manager."""

    def __init__(self) -> None:
        super().__init__()
        self._init_dnd()
        self._init_config()
        self._init_window()
        self._init_services()
        self._current_tab_key: Optional[str] = None
        self._build_ui()
        self._autostart()

    # ─────────────────────────────────────────────────────────────────────────
    # Init helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _init_dnd(self) -> None:
        """Khởi tạo hỗ trợ Kéo-Thả (TkinterDnD)."""
        try:
            self.TkdndVersion = TkinterDnD._require(self)
        except Exception as exc:
            logger.warning(f"⚠️ Không thể khởi tạo Kéo-Thả (DnD): {exc}")

    def _init_config(self) -> None:
        """Tải cấu hình ứng dụng."""
        self.config = ConfigManager()

    def _init_window(self) -> None:
        """Thiết lập cửa sổ."""
        self.title("🎮 Sims 4 Mod Manager")
        self.geometry("1100x720")
        self.minsize(900, 600)
        ctk.set_appearance_mode(self.config.appearance_mode)
        ctk.set_default_color_theme("blue")

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        if hasattr(self, "TkdndVersion"):
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self._on_dnd_drop)

    def _init_services(self) -> None:
        """Khởi tạo DownloadManager và ClipboardMonitor."""
        self.download_manager = DownloadManager(self.config)
        self.profile_manager = ProfileManager(self.config)
        self.clipboard_monitor = ClipboardMonitor(on_url_detected=self._on_clipboard_url)
        self.game_launcher = GameLauncher(self.config.game_path)

        # Gắn callbacks từ DownloadManager về UI
        self.download_manager.on_item_added     = self._on_download_added
        self.download_manager.on_item_updated   = self._on_download_updated
        self.download_manager.on_item_completed = self._on_download_completed

    def _build_ui(self) -> None:
        """Xây dựng toàn bộ giao diện."""
        self._build_sidebar()
        self._build_content()

    def _autostart(self) -> None:
        """Khởi chạy các service ngay sau khi UI sẵn sàng."""
        self.download_manager.load_history()
        self.download_manager.start()
        if self.config.clipboard_monitor_enabled:
            self.clipboard_monitor.start()
        self.download_manager.tsr_session.load_session()
        self._schedule_periodic_update()

    # ─────────────────────────────────────────────────────────────────────────
    # Sidebar
    # ─────────────────────────────────────────────────────────────────────────

    def _build_sidebar(self) -> None:
        """Xây dựng thanh điều hướng bên trái."""
        sidebar = ctk.CTkFrame(self, width=220, corner_radius=0, fg_color=Color.BG_BASE)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_rowconfigure(_SPACER_ROW, weight=1)
        sidebar.grid_propagate(False)

        # Logo
        logo = ctk.CTkFrame(sidebar, fg_color="transparent")
        logo.grid(row=0, column=0, padx=15, pady=(20, 5), sticky="ew")
        ctk.CTkLabel(logo, text="🎮", font=ctk.CTkFont(size=32)).pack(pady=(0, 2))
        ctk.CTkLabel(logo, text="Sims 4",    font=ctk.CTkFont(size=20, weight="bold"), text_color=Color.ACCENT_LIGHT).pack()
        ctk.CTkLabel(logo, text="Mod Manager", font=ctk.CTkFont(size=14), text_color=Color.TEXT_MUTED).pack()

        # Separator
        ctk.CTkFrame(sidebar, height=1, fg_color=Color.BG_DIVIDER).grid(
            row=1, column=0, padx=15, pady=15, sticky="ew"
        )

        # Nav buttons
        self._nav_buttons: dict[str, ctk.CTkButton] = {}
        for key, text, grid_row in _NAV_ITEMS:
            btn = ctk.CTkButton(
                sidebar, text=text, height=42,
                font=ctk.CTkFont(size=13),
                fg_color="transparent",
                hover_color=Color.BG_CARD,
                text_color=Color.TEXT_SECONDARY,
                anchor="w",
                command=lambda k=key: self._switch_tab(k),
            )
            btn.grid(row=grid_row, column=0, padx=10, pady=2, sticky="ew")
            self._nav_buttons[key] = btn

        # TSR Session button
        self._tsr_btn = ctk.CTkButton(
            sidebar, text="🔑 TSR Session", height=38,
            font=ctk.CTkFont(size=12),
            fg_color=Color.BG_DIVIDER, hover_color="#3d3d5c",
            text_color=Color.TSR_ACTIVE,
            command=self._show_captcha_dialog,
        )
        self._tsr_btn.grid(row=11, column=0, padx=10, pady=5, sticky="ew")

        # Game Launch button
        self._launch_btn = ctk.CTkButton(
            sidebar, text="🎮 Khởi chạy Game", height=42,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=Color.SUCCESS, hover_color=Color.SUCCESS_HOVER,
            text_color="white",
            command=self._on_launch_game,
        )
        self._launch_btn.grid(row=12, column=0, padx=10, pady=(10, 5), sticky="ew")

        # Appearance Mode
        appearance_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        appearance_frame.grid(row=13, column=0, padx=10, pady=(10, 0), sticky="ew")
        
        self._appearance_mode_var = ctk.StringVar(value=self.config.appearance_mode.capitalize())
        self._appearance_mode_menu = ctk.CTkSegmentedButton(
            appearance_frame,
            values=["☀️ Light", "🌙 Dark", "🖥️ Auto"],
            variable=self._appearance_mode_var,
            command=self._on_appearance_mode_change,
            height=30,
            font=ctk.CTkFont(size=11),
            selected_color=Color.ACCENT,
            selected_hover_color=Color.ACCENT_HOVER,
            unselected_color=Color.BG_DIVIDER,
            unselected_hover_color=Color.BG_CARD,
            text_color=Color.TEXT_PRIMARY,
        )
        self._appearance_mode_menu.pack(fill="x", padx=5)

        # Trình khởi tạo ban đầu (Nếu config là 'system' thì chọn '🖥️ Auto')
        current = self.config.appearance_mode
        if current == "light": self._appearance_mode_var.set("☀️ Light")
        elif current == "dark": self._appearance_mode_var.set("🌙 Dark")
        else: self._appearance_mode_var.set("🖥️ Auto")

        # Version
        ctk.CTkLabel(
            sidebar, text="v1.0.0",
            font=ctk.CTkFont(size=10), text_color=Color.TEXT_DISABLED,
        ).grid(row=14, column=0, padx=15, pady=(5, 15))

    def _on_appearance_mode_change(self, mode_str: str) -> None:
        """Đổi chế độ hiển thị và lưu cài đặt."""
        mapping = {"☀️ Light": "light", "🌙 Dark": "dark", "🖥️ Auto": "system"}
        mode_lower = mapping.get(mode_str, mode_str.lower())
        
        ctk.set_appearance_mode(mode_lower)
        self.config.set("appearance_mode", mode_lower)
        
        # Đồng bộ với TabSettings nếu đang tồn tại
        if hasattr(self, "_tabs") and "settings" in self._tabs:
            tab_settings = self._tabs["settings"]
            if hasattr(tab_settings, "_appearance_mode_var"):
                 tab_settings._appearance_mode_var.set(mode_str)



    # ─────────────────────────────────────────────────────────────────────────
    # Content area
    # ─────────────────────────────────────────────────────────────────────────

    def _build_content(self) -> None:
        """Xây dựng khu vực nội dung với các tab."""
        self._content_area = ctk.CTkFrame(self, fg_color=Color.BG_SURFACE, corner_radius=0)
        self._content_area.grid(row=0, column=1, sticky="nsew")
        self._content_area.grid_columnconfigure(0, weight=1)
        self._content_area.grid_rowconfigure(0, weight=1)

        self._tabs: dict[str, ctk.CTkFrame] = {
            "downloads": TabDownloads(self._content_area, download_manager=self.download_manager),
            "mods":      TabMods(self._content_area, config=self.config),
            "merger":    TabMerger(self._content_area, config=self.config),
            "orphans":   TabOrphans(self._content_area, config=self.config),
            "creators":  TabCreators(self._content_area, self.config),
            "profiles":  TabProfiles(self._content_area, self.config, self.profile_manager),
            "debug":     TabDebug(self._content_area, self.config),
            "settings":  TabSettings(self._content_area, config=self.config),
        }
        self._switch_tab("downloads")

    # ─────────────────────────────────────────────────────────────────────────
    # Tab switching
    # ─────────────────────────────────────────────────────────────────────────

    def _switch_tab(self, tab_key: str) -> None:
        """Chuyển tab đang hiển thị và cập nhật style nút điều hướng."""
        if self._current_tab_key == tab_key:
            return

        # Ẩn tab cũ nếu có
        if self._current_tab_key and self._current_tab_key in self._tabs:
            self._tabs[self._current_tab_key].grid_forget()
        
        # Hiện tab mới
        self._tabs[tab_key].grid(row=0, column=0, sticky="nsew")
        self._current_tab_key = tab_key

        # Cập nhật style nút
        for key, btn in self._nav_buttons.items():
            if key == tab_key:
                btn.configure(
                    fg_color=Color.ACCENT,
                    text_color="white",
                    font=ctk.CTkFont(size=13, weight="bold"),
                )
            else:
                btn.configure(
                    fg_color="transparent",
                    text_color=Color.TEXT_SECONDARY,
                    font=ctk.CTkFont(size=13),
                )

    # ─────────────────────────────────────────────────────────────────────────
    # TSR Captcha dialog
    # ─────────────────────────────────────────────────────────────────────────

    def _show_captcha_dialog(self) -> None:
        """Hiển thị dialog nhập captcha TSR."""
        captcha_data: Optional[bytes] = None
        try:
            captcha_data = self.download_manager.tsr_session.get_captcha_image()
        except Exception:
            pass

        if captcha_data:
            captcha_path = os.path.join(tempfile.gettempdir(), "tsr_captcha.png")
            with open(captcha_path, "wb") as f:
                f.write(captcha_data)

            dialog = _CaptchaDialog(self, captcha_path)
            self.wait_window(dialog)

            if dialog.result:
                success = False
                try:
                    success = self.download_manager.tsr_session.submit_captcha(dialog.result)
                except Exception:
                    pass
                if success:
                    self._tsr_btn.configure(text="🔑 TSR: Đã kết nối", text_color=Color.SUCCESS)
                else:
                    self._tsr_btn.configure(text="🔑 TSR: Sai mã", text_color=Color.ERROR)
        else:
            # Không có captcha → kiểm tra session có hợp lệ không
            try:
                valid: bool = self.download_manager.tsr_session_valid
            except Exception:
                valid = False

            if valid:
                self._tsr_btn.configure(text="🔑 TSR: Đã kết nối", text_color=Color.SUCCESS)
            else:
                self._tsr_btn.configure(text="🔑 TSR: Không cần",  text_color=Color.TEXT_MUTED)

    # ─────────────────────────────────────────────────────────────────────────
    # Clipboard callbacks
    # ─────────────────────────────────────────────────────────────────────────

    def _on_clipboard_url(self, url: str) -> None:
        """Callback: ClipboardMonitor phát hiện URL mới.

        Parameters
        ----------
        url:
            URL vừa được copy vào clipboard.
        """
        from core.sfs_downloader import SFSDownloader

        if SFSDownloader.is_folder_url(url):
            self.after(0, lambda u=url: self._ask_folder_download(u))
        else:
            self.download_manager.add_url(url)

    def _ask_folder_download(self, folder_url: str) -> None:
        """Quét folder SFS trong background rồi hỏi xác nhận.

        Parameters
        ----------
        folder_url:
            URL của folder SimsFileShare.
        """
        import threading
        from core.sfs_downloader import SFSDownloader

        def _scan() -> None:
            sfs = SFSDownloader()
            links = sfs.get_folder_links(folder_url)
            if links:
                self.after(0, lambda: self._show_folder_dialog(folder_url, len(links)))

        threading.Thread(target=_scan, daemon=True).start()

    def _show_folder_dialog(self, folder_url: str, count: int) -> None:
        """Hiện dialog xác nhận tải toàn bộ folder.

        Parameters
        ----------
        folder_url:
            URL folder.
        count:
            Số file tìm thấy trong folder.
        """
        dialog = ctk.CTkToplevel(self)
        dialog.title("📁 Tải Folder SFS")
        dialog.geometry("420x200")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()
        dialog.configure(fg_color=Color.BG_CARD)

        # Canh giữa
        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width()  - 420) // 2
        y = self.winfo_y() + (self.winfo_height() - 200) // 2
        dialog.geometry(f"+{x}+{y}")

        ctk.CTkLabel(
            dialog, text="📁 Phát hiện folder SimsFileShare",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=Color.TEXT_PRIMARY,
        ).pack(pady=(20, 5))

        ctk.CTkLabel(
            dialog, text=f"Tìm thấy {count} file trong folder.\nBạn có muốn tải tất cả không?",
            font=ctk.CTkFont(size=13),
            text_color=Color.TEXT_SECONDARY,
        ).pack(pady=5)

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=15)

        ctk.CTkButton(
            btn_frame, text=f"✅ Tải {count} file", width=140, height=38,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=Color.SUCCESS, hover_color=Color.SUCCESS_HOVER,
            command=lambda: (dialog.destroy(), self.download_manager.add_url(folder_url)),
        ).pack(side="left", padx=10)

        ctk.CTkButton(
            btn_frame, text="❌ Bỏ qua", width=120, height=38,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=Color.TEXT_MUTED, hover_color="#475569",
            command=dialog.destroy,
        ).pack(side="left", padx=10)

    # ─────────────────────────────────────────────────────────────────────────
    # Download callbacks (gọi từ DownloadManager thread → đẩy về main thread)
    # ─────────────────────────────────────────────────────────────────────────

    def _on_download_added(self, item) -> None:
        """DownloadManager: item mới được thêm vào hàng đợi."""
        self.after(
            0,
            lambda u=item.url, s=item.source.value:
                self._tabs["downloads"].add_download_widget(u, s),
        )

    def _on_download_updated(self, item) -> None:
        """DownloadManager: tiến trình / trạng thái item thay đổi."""
        self.after(
            0,
            lambda u=item.url, s=item.status.value, p=item.progress, f=item.filename:
                self._tabs["downloads"].update_download_item(u, s, p, f),
        )

    def _on_download_completed(self, _item) -> None:
        """DownloadManager: một item hoàn tất."""
        self.after(0, self._refresh_stats)

    # ─────────────────────────────────────────────────────────────────────────
    # Stats update
    # ─────────────────────────────────────────────────────────────────────────

    def _refresh_stats(self) -> None:
        """Cập nhật thống kê hiển thị trên TabDownloads."""
        dm = self.download_manager
        self._tabs["downloads"].update_stats(
            dm.queue_count,
            dm.active_count,
            dm.completed_count,
            dm.tsr_session_valid,
        )

    def _schedule_periodic_update(self) -> None:
        """Lên lịch cập nhật stats mỗi 2 giây."""
        self._refresh_stats()
        self.after(2000, self._schedule_periodic_update)

    # ─────────────────────────────────────────────────────────────────────────
    # Drag-and-drop
    # ─────────────────────────────────────────────────────────────────────────

    def _on_dnd_drop(self, event) -> None:
        """Xử lý sự kiện kéo-thả file vào cửa sổ."""
        try:
            paths: list[str] = self.tk.splitlist(event.data)
        except Exception:
            import re
            raw = re.findall(r"\{[^}]+\}|[^\s]+", event.data)
            paths = [p.strip("{}") for p in raw]

        if not paths:
            return

        logger.info(f"Nhận {len(paths)} file từ kéo-thả")
        # Chuyển sang tab Mods để thấy log
        self._switch_tab("mods")
        self._tabs["mods"].process_manual_mods(paths)

    # ─────────────────────────────────────────────────────────────────────────
    # Lifecycle
    # ─────────────────────────────────────────────────────────────────────────

    # ─────────────────────────────────────────────────────────────────────────
    # Game Launcher
    # ─────────────────────────────────────────────────────────────────────────

    def _on_launch_game(self) -> None:
        """Sự kiện nhấn nút khởi chạy game."""
        if self.game_launcher.is_running():
            return

        self._launch_btn.configure(state="disabled", text="⏳ Đang chạy...")

        def _on_exit():
            self.after(0, lambda: self._launch_btn.configure(state="normal", text="🎮 Khởi chạy Game"))
            
            # Tự động xóa cache nếu bật
            if self.config.auto_clear_cache:
                logger.info("Tự động dọn dẹp cache sau khi tắt game...")
                cm = CacheManager(self.config.ts4_docs_dir)
                cm.clear_cache()

            # Nếu đang có phiên chẩn đoán 50/50, tự động chuyển sang tab Debug và hỏi kết quả
            self.after(0, self._check_diagnostic_after_exit)

        success = self.game_launcher.launch(on_exit=_on_exit)
        if not success:
            from tkinter import messagebox
            messagebox.showerror("Lỗi", f"Không thể khởi chạy game tại:\n{self.config.game_path}")
            self._launch_btn.configure(state="normal", text="🎮 Khởi chạy Game")

    def _check_diagnostic_after_exit(self) -> None:
        """Kiểm tra nếu đang test mod thì nhắc nhở người dùng báo cáo."""
        try:
            tab_debug = self._tabs.get("debug")
            if tab_debug and hasattr(tab_debug, "_diag_session"):
                session = tab_debug._diag_session
                if session and session.is_active:
                    self._switch_tab("debug")
                    from tkinter import messagebox
                    messagebox.showinfo(
                        "Chẩn đoán Mod",
                        "Game đã tắt. Vui lòng báo cáo kết quả lỗi (Còn hay Mất) trong tab Gỡ lỗi."
                    )
        except Exception as exc:
            logger.error(f"Lỗi kiểm tra trạng thái chẩn đoán: {exc}")

    def on_closing(self) -> None:
        """Dọn dẹp và tắt ứng dụng."""
        self.clipboard_monitor.stop()
        self.download_manager.stop()
        self.destroy()


# ─── Captcha dialog ───────────────────────────────────────────────────────────

class _CaptchaDialog(ctk.CTkToplevel):
    """Dialog hiển thị ảnh captcha TSR và nhận mã xác nhận từ người dùng.

    Attributes
    ----------
    result:
        Chuỗi mã người dùng nhập, hoặc ``None`` nếu đóng dialog.
    """

    def __init__(self, parent: ctk.CTkBaseClass, captcha_image_path: str) -> None:
        super().__init__(parent)
        self.result: Optional[str] = None

        self.title("🔑 TSR Captcha")
        self.geometry("400x300")
        self.resizable(False, False)
        self.configure(fg_color=Color.BG_SURFACE)

        # Ảnh captcha
        try:
            from PIL import Image
            img = Image.open(captcha_image_path)
            ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(300, 80))
            ctk.CTkLabel(self, text="", image=ctk_img).pack(pady=(20, 10))
        except Exception as exc:
            ctk.CTkLabel(
                self, text=f"Không hiển thị được captcha\n{exc}",
                text_color=Color.ERROR,
            ).pack(pady=20)

        ctk.CTkLabel(
            self, text="Nhập mã captcha bên dưới:",
            font=ctk.CTkFont(size=13), text_color=Color.TEXT_SECONDARY,
        ).pack(pady=5)

        self._entry = ctk.CTkEntry(
            self, width=200, height=40,
            font=ctk.CTkFont(size=16),
            fg_color=Color.BG_INPUT,
            border_color=Color.ACCENT,
            text_color=Color.TEXT_PRIMARY,
            justify="center",
        )
        self._entry.pack(pady=10)
        self._entry.focus()
        self._entry.bind("<Return>", lambda _e: self._on_submit())

        ctk.CTkButton(
            self, text="Xác nhận", height=40, width=150,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=Color.ACCENT, hover_color=Color.ACCENT_HOVER,
            command=self._on_submit,
        ).pack(pady=10)

    def _on_submit(self) -> None:
        value = self._entry.get().strip()
        if value:
            self.result = value
        self.destroy()
