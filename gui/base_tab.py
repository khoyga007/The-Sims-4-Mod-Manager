"""
Base Tab — Lớp cơ sở cho tất cả các tab trong Mod Manager.
Cung cấp cơ chế queue UI an toàn để background threads có thể cập nhật giao diện.
"""
from __future__ import annotations
import queue
import customtkinter as ctk
from typing import Callable, Any

class BaseTab(ctk.CTkFrame):
    """
    Lớp cơ sở hỗ trợ hàng đợi UI (Thread-safe).
    """
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self._ui_queue: queue.Queue[Callable] = queue.Queue()
        self._process_ui_queue()

    def queue_ui_task(self, task: Callable[[], Any]) -> None:
        """Thêm một tác vụ giao diện vào hàng đợi để thực thi trên main thread."""
        self._ui_queue.put(task)

    def _process_ui_queue(self) -> None:
        """Đọc và thực thi các tác vụ trong hàng đợi UI mỗi 100ms."""
        try:
            while True:
                task = self._ui_queue.get_nowait()
                task()
        except queue.Empty:
            pass
        finally:
            self.after(100, self._process_ui_queue)
