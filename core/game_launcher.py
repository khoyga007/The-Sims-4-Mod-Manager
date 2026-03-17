"""
Game Launcher — Khởi động và theo dõi tiến trình The Sims 4.

Hỗ trợ khởi động game trực tiếp và thông báo khi game tắt (hữu ích cho việc test mod).
"""
from __future__ import annotations

import logging
import os
import subprocess
import threading
import ctypes
from typing import Optional, Callable

logger = logging.getLogger("ModManager.Launcher")

class GameLauncher:
    """Quản lý việc chạy game và theo dõi tiến trình."""

    def __init__(self, game_path: str) -> None:
        self._game_path = game_path
        self._process: Optional[subprocess.Popen] = None
        self._monitor_thread: Optional[threading.Thread] = None

    def is_running(self) -> bool:
        """Kiểm tra game có đang chạy (do app khởi động) không."""
        if self._process is None:
            return False
        return self._process.poll() is None

    def launch(self, on_exit: Optional[Callable[[], None]] = None) -> bool:
        """Khởi động game.

        Parameters
        ----------
        on_exit:
            Callback được gọi khi game tắt.
        """
        if self.is_running():
            logger.warning("Game đã đang chạy.")
            return False

        if not os.path.exists(self._game_path):
            logger.error(f"Không tìm thấy file thực thi: {self._game_path}")
            return False

        try:
            # Chạy game với working directory là thư mục chứa exe
            work_dir = os.path.dirname(self._game_path)
            
            # Xây dựng danh sách đối số
            args = [self._game_path]
            from core.config_manager import ConfigManager
            config = ConfigManager()
            
            if config.dx11_mode:
                args.append("-dx11")
                logger.info("Kích hoạt DirectX 11 mode.")

            self._process = subprocess.Popen(
                args,
                cwd=work_dir,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            )
            
            # Tăng độ ưu tiên CPU nếu bật Turbo Mode
            if config.turbo_mode:
                try:
                    # Windows specific: HIGH_PRIORITY_CLASS = 0x00000080
                    HIGH_PRIORITY_CLASS = 0x00000080
                    kernel32 = ctypes.windll.kernel32
                    handle = kernel32.OpenProcess(0x0200 | 0x0400, False, self._process.pid)
                    if handle:
                        if kernel32.SetPriorityClass(handle, HIGH_PRIORITY_CLASS):
                            logger.info("🚀 Đã kích hoạt Turbo Mode: Set HIGH PRIORITY cho TS4.")
                        kernel32.CloseHandle(handle)
                except Exception as e:
                    logger.warning(f"Không thể set High Priority: {e}")

            logger.info(f"Đã khởi động game từ: {self._game_path}")

            if on_exit:
                self._monitor_thread = threading.Thread(
                    target=self._wait_for_exit,
                    args=(on_exit,),
                    daemon=True
                )
                self._monitor_thread.start()

            return True
        except Exception as exc:
            logger.error(f"Lỗi khởi động game: {exc}")
            return False

    def _wait_for_exit(self, callback: Callable[[], None]) -> None:
        if self._process:
            self._process.wait()
            logger.info("Game đã tắt.")
            callback()
