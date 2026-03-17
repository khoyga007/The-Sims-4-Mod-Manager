"""
Clipboard Monitor — Theo dõi clipboard tự động phát hiện link TSR / SFS / Direct.

Chạy trên daemon thread, kiểm tra clipboard mỗi 300ms.
Chỉ xử lý dòng bắt đầu bằng ``http`` để tránh trigger nhầm.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger("ModManager.Clipboard")

_POLL_INTERVAL = 0.3  # giây


class ClipboardMonitor:
    """Daemon thread theo dõi clipboard và phát hiện link TSR/SFS/Direct.

    Parameters
    ----------
    on_url_detected:
        Callback nhận URL hợp lệ vừa copy. Được gọi từ background thread —
        GUI caller cần dùng ``widget.after(0, ...)`` để đẩy về main thread.
    """

    def __init__(
        self,
        on_url_detected: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_text = ""
        self.on_url_detected = on_url_detected

    # ─────────────────────────────────────────────────────────────────────────
    # Lifecycle
    # ─────────────────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Bắt đầu theo dõi clipboard (no-op nếu đang chạy)."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.info("📋 Clipboard monitor đã bật")

    def stop(self) -> None:
        """Dừng theo dõi clipboard và chờ thread kết thúc (tối đa 2s)."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        logger.info("📋 Clipboard monitor đã tắt")

    @property
    def is_running(self) -> bool:
        """``True`` nếu monitor đang chạy."""
        return self._running

    # ─────────────────────────────────────────────────────────────────────────
    # Monitor loop
    # ─────────────────────────────────────────────────────────────────────────

    def _monitor_loop(self) -> None:
        """Vòng lặp kiểm tra clipboard (chạy trên daemon thread)."""
        try:
            import clipboard  # type: ignore[import]
        except ImportError:
            logger.error(
                "Thư viện 'clipboard' chưa được cài. Chạy: pip install clipboard"
            )
            self._running = False
            return

        # Ghi nhận text hiện tại để không trigger ngay lần đầu
        try:
            self._last_text = clipboard.paste() or ""
        except Exception:
            self._last_text = ""

        while self._running:
            try:
                current = clipboard.paste() or ""
                if current != self._last_text and current.strip():
                    self._last_text = current
                    self._process_text(current)
            except Exception as exc:
                logger.debug(f"Lỗi đọc clipboard: {exc}")

            time.sleep(_POLL_INTERVAL)

    # ─────────────────────────────────────────────────────────────────────────
    # URL detection
    # ─────────────────────────────────────────────────────────────────────────

    def _process_text(self, text: str) -> None:
        """Phân tích text từ clipboard, tìm và xử lý link hợp lệ.

        Parameters
        ----------
        text:
            Nội dung clipboard vừa thay đổi.
        """
        # Import lazy để tránh circular imports lúc khởi động
        from core.tsr_downloader import TSRItem
        from core.sfs_downloader import SFSDownloader
        from core.direct_downloader import DirectDownloader

        for line in text.strip().splitlines():
            line = line.strip()
            if not line or not line.lower().startswith("http"):
                continue

            if TSRItem.is_valid_url(line):
                logger.info(f"📋 TSR: {line}")
                self._notify(line)
            elif SFSDownloader.is_valid_url(line):
                logger.info(f"📋 SFS: {line}")
                self._notify(line)
            elif DirectDownloader.is_valid_url(line):
                logger.info(f"📋 Direct: {line}")
                self._notify(line)

    def _notify(self, url: str) -> None:
        """Gọi callback nếu được cấu hình.

        Parameters
        ----------
        url:
            URL hợp lệ vừa phát hiện.
        """
        if self.on_url_detected:
            try:
                self.on_url_detected(url)
            except Exception as exc:
                logger.debug(f"Lỗi callback URL: {exc}")
