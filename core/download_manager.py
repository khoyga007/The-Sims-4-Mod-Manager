"""
Download Manager — Quản lý hàng đợi tải xuống.

Luồng xử lý:
- **TSR**: Batch parallel — lấy ticket hàng loạt → chờ 10s → tải song song.
- **SFS**: Song song tối đa 2 file cùng lúc (rate-limit tự nhiên).
- **Direct**: Song song tối đa 10 file cùng lúc.

Callbacks về GUI được gọi từ worker threads → GUI bắt buộc dùng
``widget.after(0, ...)`` để đẩy về main thread.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

from core.config_manager import ConfigManager
from core.direct_downloader import DirectDownloader
from core.sfs_downloader import SFSDownloader
from core.sorter import ModSorter
from core.tsr_downloader import TSRDownloader, TSRItem, TSRSession, TSRTicket
from core.unpacker import is_archive, unpack

logger = logging.getLogger("ModManager.DownloadManager")


class DownloadCanceledError(Exception):
    """Lỗi ném ra khi người dùng chủ động hủy tải xuống."""


# ─── Enums ────────────────────────────────────────────────────────────────────

class DownloadStatus(Enum):
    """Trạng thái của một DownloadItem.

    Giá trị (``.value``) phải khớp với key trong ``StatusBadge.STATUS_COLORS``
    ở ``gui/widgets.py``.
    """
    PENDING     = "Đợi"
    TICKET      = "Lấy ticket"
    WAITING     = "Chờ 10s"     # ← trước là "Chờ", không khớp badge
    DOWNLOADING = "Đang tải"
    UNPACKING   = "Giải nén"
    SORTING     = "Phân loại"
    DONE        = "Hoàn tất"
    ERROR       = "Lỗi"


class DownloadSource(Enum):
    TSR     = "The Sims Resource"
    SFS     = "SimsFileShare"
    DIRECT  = "Direct Link"
    UNKNOWN = "Unknown"


# ─── Status display helpers ───────────────────────────────────────────────────

_STATUS_ICONS: dict[DownloadStatus, str] = {
    DownloadStatus.PENDING:     "⏳",
    DownloadStatus.TICKET:      "🎫",
    DownloadStatus.WAITING:     "⏱️",
    DownloadStatus.DOWNLOADING: "⬇️",
    DownloadStatus.UNPACKING:   "📦",
    DownloadStatus.SORTING:     "📂",
    DownloadStatus.DONE:        "✅",
    DownloadStatus.ERROR:       "❌",
}

# ─── Data model ───────────────────────────────────────────────────────────────

@dataclass
class DownloadItem:
    """Thông tin một mục trong hàng đợi tải xuống.

    Attributes
    ----------
    url:
        URL nguồn.
    source:
        Loại nguồn (:class:`DownloadSource`).
    status:
        Trạng thái hiện tại.
    progress:
        Tiến trình ``[0.0, 1.0]``.
    filename:
        Tên file sau khi tải.
    error_message:
        Thông báo lỗi (rỗng nếu không có lỗi).
    filepath:
        Đường dẫn file đã tải (sau khi hoàn tất).
    sorted_files:
        Danh sách đường dẫn sau khi phân loại.
    """

    url: str
    source: DownloadSource
    status: DownloadStatus = DownloadStatus.PENDING
    progress: float = 0.0
    filename: str = ""
    error_message: str = ""
    filepath: Optional[str] = None
    sorted_files: list[str] = field(default_factory=list)
    is_canceled: bool = False  # Tín hiệu hủy cho worker threads

    # Internal — TSR ticket (không serialize)
    _ticket: Optional[TSRTicket] = field(default=None, repr=False)
    _last_ui_update: float = field(default=0.0, repr=False)

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def status_display(self) -> str:
        """Chuỗi hiển thị có icon (ví dụ ``"⬇️ Đang tải"``)."""
        icon = _STATUS_ICONS.get(self.status, "")
        return f"{icon} {self.status.value}".strip()

    @property
    def progress_percent(self) -> int:
        """Tiến trình dạng phần trăm nguyên (0–100)."""
        return int(self.progress * 100)

    # ── Serialization ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Chuyển thành dict để lưu JSON."""
        return {
            "url":           self.url,
            "source":        self.source.name,
            "status":        self.status.name,
            "progress":      self.progress,
            "filename":      self.filename,
            "error_message": self.error_message,
            "filepath":      self.filepath,
            "sorted_files":  self.sorted_files,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DownloadItem":
        """Tạo lại từ dict đã lưu JSON.

        Mọi item đang dở dang (không phải DONE/ERROR) sẽ được đặt lại
        thành PENDING để tải lại.
        """
        try:
            status = DownloadStatus[data.get("status", "PENDING")]
        except KeyError:
            status = DownloadStatus.PENDING

        # Reset trạng thái dở dang
        if status not in (DownloadStatus.DONE, DownloadStatus.ERROR):
            status = DownloadStatus.PENDING

        return cls(
            url=data["url"],
            source=DownloadSource[data["source"]],
            status=status,
            progress=data.get("progress", 0.0) if status != DownloadStatus.PENDING else 0.0,
            filename=data.get("filename", ""),
            error_message=data.get("error_message", ""),
            filepath=data.get("filepath"),
            sorted_files=data.get("sorted_files", []),
        )


# ─── Manager ──────────────────────────────────────────────────────────────────

class DownloadManager:
    """Quản lý toàn bộ vòng đời tải xuống: xếp hàng → tải → giải nén → phân loại.

    Parameters
    ----------
    config:
        Instance :class:`ConfigManager`. Nếu ``None`` sẽ dùng instance mặc định.
    """

    #: Chờ 2s để gom thêm TSR link trước khi batch
    BATCH_WAIT = 2.0

    #: Số lượng SFS tải đồng thời tối đa (Tăng lên JDownloader style)
    MAX_SFS_CONCURRENT = 4

    #: Số lượng Direct tải đồng thời tối đa
    MAX_DIRECT_CONCURRENT = 10

    def __init__(self, config: Optional[ConfigManager] = None) -> None:
        self.config = config or ConfigManager()

        # Downloaders
        self.tsr_session    = TSRSession()
        self.tsr_downloader = TSRDownloader(self.tsr_session)
        self.sfs_downloader = SFSDownloader()
        self.direct_downloader = DirectDownloader()
        self.sorter = ModSorter(self.config)

        # History
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self._history_file = os.path.join(project_dir, "history.json")

        # State
        self._queue: list[DownloadItem] = []
        self._active: list[DownloadItem] = []
        self._completed: list[DownloadItem] = []
        self._is_saving = False  # Flag ngăn spam thread lưu file
        self._lock = threading.Lock()
        self._running = False
        self._paused = False
        self._worker: Optional[threading.Thread] = None

        # Warp / IP Rotation state
        self._warp_lock = threading.Lock()
        self._rotation_wait = threading.Condition()
        self._is_rotating = False
        self._last_rotation_time = 0.0
        self._low_speed_counters: dict[str, int] = {} # url -> count of consecutive low speeds

        # GUI callbacks (chạy từ worker thread → GUI dùng after(0, ...))
        self.on_item_added:     Optional[Callable[[DownloadItem], None]] = None
        self.on_item_updated:   Optional[Callable[[DownloadItem], None]] = None
        self.on_item_completed: Optional[Callable[[DownloadItem], None]] = None

    # ─────────────────────────────────────────────────────────────────────────
    # Lifecycle
    # ─────────────────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Khởi động worker loop."""
        if self._running:
            return
        self._running = True
        self._worker = threading.Thread(target=self._process_loop, daemon=True)
        self._worker.start()
        logger.info("🚀 Download Manager đã khởi động")

    def stop(self) -> None:
        """Dừng worker loop (chờ tối đa 5s)."""
        self._running = False
        if self._worker:
            self._worker.join(timeout=5)
        logger.info("⛔ Download Manager đã dừng")

    def pause(self) -> None:
        """Tạm dừng — không khởi tải mới, file đang tải vẫn chạy."""
        self._paused = True
        logger.info("⏸️ Download Manager đã tạm dừng")

    def resume(self) -> None:
        """Tiếp tục nhận và tải file mới."""
        self._paused = False
        logger.info("▶️ Download Manager đã tiếp tục")

    @property
    def is_paused(self) -> bool:
        return self._paused

    # ─────────────────────────────────────────────────────────────────────────
    # LinkGrabber helpers
    # ─────────────────────────────────────────────────────────────────────────

    def get_sfs_metadata(self, url: str) -> list[dict]:
        """Lấy metadata từ SFS folder (cho LinkGrabber UI)."""
        if SFSDownloader.is_folder_url(url):
            return self.sfs_downloader.get_folder_metadata(url)
        return []

    # ─────────────────────────────────────────────────────────────────────────
    # Queue management
    # ─────────────────────────────────────────────────────────────────────────

    def add_url(self, url: str) -> Optional[DownloadItem]:
        """Thêm URL vào hàng đợi.

        Nếu là folder SFS, quét trước rồi thêm từng link vào hàng đợi.

        Parameters
        ----------
        url:
            URL cần tải.

        Returns
        -------
        DownloadItem | None
            Item vừa thêm (hoặc item đầu tiên nếu là folder),
            ``None`` nếu URL không hợp lệ hoặc đã tồn tại.
        """
        url = url.strip()
        if SFSDownloader.is_folder_url(url):
            return self._add_sfs_folder(url)

        source = self._detect_source(url)
        if source == DownloadSource.UNKNOWN:
            logger.warning(f"URL không được nhận diện: {url}")
            return None

        # Kiểm tra trùng (trong hàng đợi, đang tải, hoặc đã hoàn tất)
        with self._lock:
            if any(i.url == url for i in self.all_items):
                logger.info(f"⏭️ Bỏ qua URL đã tồn tại trong danh sách: {url}")
                return None

        item = DownloadItem(url=url, source=source)
        with self._lock:
            self._queue.append(item)

        logger.info(f"➕ [{source.value}]: {url}")
        self._fire(self.on_item_added, item)
        self.save_history()
        return item

    def cancel_all(self) -> list[str]:
        """Xóa toàn bộ hàng đợi và hủy các tiến trình đang tải.
        
        Returns
        -------
        list[str]
            Danh sách các URL đã bị hủy.
        """
        canceled_urls = []
        with self._lock:
            # Hủy hàng đợi chờ
            count_queue = len(self._queue)
            for item in self._queue:
                canceled_urls.append(item.url)
            self._queue.clear()
            
            # Đánh dấu tín hiệu hủy cho các item đang hoạt động
            count_active = len(self._active)
            for item in self._active:
                item.is_canceled = True
                canceled_urls.append(item.url)
            
        self._paused = False
        logger.info(f"🗑️ Đã hủy {count_queue} item chờ và {count_active} item đang tải")
        self.save_history()
        return canceled_urls

    def retry_failed(self) -> int:
        """Đưa các item lỗi trở lại hàng đợi.

        Returns
        -------
        int
            Số item được đưa lại vào hàng đợi.
        """
        with self._lock:
            failed = [i for i in self._completed if i.status == DownloadStatus.ERROR]
            for item in failed:
                self._completed.remove(item)
                item.status = DownloadStatus.PENDING
                item.progress = 0.0
                item.error_message = ""
                self._queue.append(item)

        for item in failed:
            self._fire(self.on_item_updated, item)

        logger.info(f"🔄 Đưa {len(failed)} file lỗi trở lại hàng đợi")
        return len(failed)

    def clear_history(self) -> list[str]:
        """Xóa lịch sử (file đã hoàn tất và bị lỗi).

        Returns
        -------
        list[str]
            Danh sách URL đã xóa (để GUI remove widget tương ứng).
        """
        with self._lock:
            urls = [i.url for i in self._completed]
            self._completed.clear()
        self.save_history()
        logger.info(f"🧹 Đã xóa {len(urls)} item khỏi lịch sử")
        return urls

    def move_queued_item(self, old_index: int, new_index: int) -> bool:
        """Thay đổi thứ tự ưu tiên trong hàng đợi.
        
        Chỉ cho phép di chuyển các item đang ở trạng thái PENDING (trong self._queue).
        """
        with self._lock:
            if 0 <= old_index < len(self._queue) and 0 <= new_index < len(self._queue):
                item = self._queue.pop(old_index)
                self._queue.insert(new_index, item)
                logger.info(f"🔃 Di chuyển hàng đợi: {item.url} từ {old_index} -> {new_index}")
                self.save_history()
                return True
        return False

    def move_queued_item_by_url(self, url: str, new_index: int) -> bool:
        """Di chuyển một item trong hàng đợi dựa trên URL."""
        with self._lock:
            for i, item in enumerate(self._queue):
                if item.url == url:
                    self._queue.pop(i)
                    self._queue.insert(new_index, item)
                    logger.info(f"🔃 Di chuyển hàng đợi: {url} tới vị trí {new_index}")
                    self.save_history()
                    return True
        return False

    def remove_item(self, url: str) -> bool:
        """Xóa một item cụ thể khỏi hàng đợi hoặc lịch sử."""
        with self._lock:
            # Tìm trong hàng đợi
            for i, item in enumerate(self._queue):
                if item.url == url:
                    self._queue.pop(i)
                    logger.info(f"🗑️ Đã xóa khỏi hàng đợi: {url}")
                    self.save_history()
                    return True
            
            # Tìm trong lịch sử hoàn tất
            for i, item in enumerate(self._completed):
                if item.url == url:
                    self._completed.pop(i)
                    logger.info(f"🗑️ Đã xóa khỏi lịch sử: {url}")
                    self.save_history()
                    return True

            # Tìm trong các tiến trình đang hoạt động
            for item in self._active:
                if item.url == url:
                    item.is_canceled = True
                    logger.info(f"🚫 Đã gửi tín hiệu hủy cho tiến trình đang chạy: {url}")
                    # Chú ý: Worker thread sẽ tự xóa khỏi self._active khi bắt được lỗi
                    return True
        return False

    # ─────────────────────────────────────────────────────────────────────────
    # History persistence
    # ─────────────────────────────────────────────────────────────────────────

    def load_history(self) -> None:
        """Tải lịch sử tải xuống từ file JSON (gọi lúc khởi động)."""
        if not os.path.exists(self._history_file):
            return

        try:
            with open(self._history_file, "r", encoding="utf-8") as f:
                data: list[dict] = json.load(f)

            items: list[DownloadItem] = []
            for entry in data:
                try:
                    items.append(DownloadItem.from_dict(entry))
                except Exception as exc:
                    logger.warning(f"Bỏ qua item lịch sử lỗi: {exc}")

            with self._lock:
                for item in items:
                    if item.status in (DownloadStatus.DONE, DownloadStatus.ERROR):
                        self._completed.append(item)
                    else:
                        self._queue.append(item)

            logger.info(f"Tải {len(items)} item từ lịch sử")

            # Thông báo GUI để hiển thị lại
            for item in items:
                self._fire(self.on_item_added, item)
                self._fire(self.on_item_updated, item)

        except Exception as exc:
            logger.error(f"Lỗi tải lịch sử: {exc}")

    def save_history(self) -> None:
        """Lưu toàn bộ trạng thái xuống file JSON (chạy ngầm)."""
        with self._lock:
            if self._is_saving:
                return # Đang lưu rồi, bỏ qua lượt này để tránh spam thread
            
            try:
                # Thu thập dữ liệu nhanh chóng trong lock
                all_items = self._queue + self._active + self._completed
                data = [i.to_dict() for i in all_items]
                self._is_saving = True # Đánh dấu bắt đầu lưu
                
                # Thực hiện ghi file vật lý trong thread riêng biệt
                t = threading.Thread(
                    target=self._save_history_worker, 
                    args=(data,), 
                    daemon=True,
                    name="HistorySaver"
                )
                t.start()
            except Exception as exc:
                self._is_saving = False
                logger.error(f"Lỗi chuẩn bị lưu lịch sử: {exc}")

    def _save_history_worker(self, data: list[dict]) -> None:
        """Thực hiện ghi file JSON từ dữ liệu đã snapshot."""
        try:
            with open(self._history_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.error(f"Lỗi ghi file lịch sử: {exc}")
        finally:
            with self._lock:
                self._is_saving = False # Hoàn tất, cho phép lượt lưu tiếp theo

    # ─────────────────────────────────────────────────────────────────────────
    # Stats (readonly)
    # ─────────────────────────────────────────────────────────────────────────

    @property
    def queue_count(self) -> int:
        return len(self._queue)

    @property
    def active_count(self) -> int:
        return len(self._active)

    @property
    def completed_count(self) -> int:
        return len(self._completed)

    @property
    def all_items(self) -> list[DownloadItem]:
        return self._queue + self._active + self._completed

    @property
    def tsr_session_valid(self) -> bool:
        """``True`` nếu phiên TSR đang hoạt động."""
        return self.tsr_session.session_id is not None

    # ─────────────────────────────────────────────────────────────────────────
    # Worker loop
    # ─────────────────────────────────────────────────────────────────────────

    def _process_loop(self) -> None:
        """Vòng lặp chính — chạy trên daemon thread."""
        while self._running:
            if self._paused:
                time.sleep(0.5)
                continue

            with self._lock:
                if not self._queue:
                    time.sleep(0.5)
                    continue

                active_sfs    = sum(1 for i in self._active if i.source == DownloadSource.SFS)
                active_direct = sum(1 for i in self._active if i.source == DownloadSource.DIRECT)

                tsr_items    = [i for i in self._queue if i.source == DownloadSource.TSR]
                sfs_items    = [i for i in self._queue if i.source == DownloadSource.SFS]
                direct_items = [i for i in self._queue if i.source == DownloadSource.DIRECT]

                # SFS — tối đa MAX_SFS_CONCURRENT
                sfs_to_start: Optional[DownloadItem] = None
                if sfs_items and active_sfs < self.MAX_SFS_CONCURRENT:
                    sfs_to_start = sfs_items[0]
                    self._queue.remove(sfs_to_start)
                    self._active.append(sfs_to_start)

                # Direct — tối đa MAX_DIRECT_CONCURRENT
                direct_to_start: list[DownloadItem] = []
                slots = self.MAX_DIRECT_CONCURRENT - active_direct
                if direct_items and slots > 0:
                    direct_to_start = direct_items[:slots]
                    for i in direct_to_start:
                        self._queue.remove(i)
                        self._active.append(i)

            # Khởi thread SFS
            if sfs_to_start:
                threading.Thread(
                    target=self._process_simple_item,
                    args=(sfs_to_start, self.sfs_downloader.download),
                    daemon=True,
                ).start()

            # Khởi thread Direct
            for item in direct_to_start:
                threading.Thread(
                    target=self._process_simple_item,
                    args=(item, self.direct_downloader.download),
                    daemon=True,
                ).start()

            # TSR batch
            if tsr_items:
                # Chờ gom thêm link
                time.sleep(self.BATCH_WAIT)
                with self._lock:
                    batch = [i for i in self._queue if i.source == DownloadSource.TSR]
                    for i in batch:
                        self._queue.remove(i)
                        self._active.append(i)
                if batch:
                    self._process_tsr_batch(batch)

            time.sleep(0.5)

    # ─────────────────────────────────────────────────────────────────────────
    # Simple downloader (SFS + Direct — không cần ticket/wait)
    # ─────────────────────────────────────────────────────────────────────────

    def _process_simple_item(
        self,
        item: DownloadItem,
        download_fn: Callable,
    ) -> None:
        """Worker chung cho SFS và Direct.

        Parameters
        ----------
        item:
            Item cần tải.
        download_fn:
            Hàm ``download(url, path, progress_callback)`` của downloader tương ứng.
        """
        staging = self.config.staging_directory
        os.makedirs(staging, exist_ok=True)

        item.status = DownloadStatus.DOWNLOADING
        self._notify_update(item)

        max_tries = 3
        for attempt in range(max_tries):
            try:
                filepath = download_fn(
                    item.url, staging,
                    progress_callback=lambda p, s: self._update_progress(item, p, s),
                )
                if filepath is None:
                    # Nếu trả về None mà không tung exception, có thể lỗi logic hoặc đã retry hết bên trong
                    self._fail_item(item, "Tải xuống thất bại")
                    return

                item.filepath = filepath
                item.filename = os.path.basename(filepath)
                self._post_download(item, filepath)
                return

            except DownloadCanceledError:
                logger.info(f"🚫 Đã hủy tải: {item.url}")
                with self._lock:
                    if item in self._active:
                        self._active.remove(item)
                # Cleanup .part
                part_path = os.path.join(staging, os.path.basename(item.url) + ".part")
                if os.path.exists(part_path):
                    try: os.remove(part_path)
                    except: pass
                return

            except Exception as exc:
                # Kiểm tra xem có phải do đang đổi IP không
                if self._is_rotating or (type(exc).__name__ in ('ProxyError', 'ConnectionError', 'Timeout', 'RequestException')):
                    if self._is_rotating:
                        logger.info(f"🔁 Connection drop do đang đổi IP. Chờ tải lại {item.filename}...")
                        with self._rotation_wait:
                            if self._is_rotating:
                                self._rotation_wait.wait(timeout=60)
                    
                    if attempt < max_tries - 1:
                        logger.warning(f"⚠️ Lỗi mạng trên {item.filename}, thử lại lần {attempt + 2}/{max_tries}: {exc}")
                        time.sleep(2)
                        continue

                logger.error(f"❌ Lỗi tải {item.source.value} {item.url}: {exc}")
                self._fail_item(item, str(exc))
                return

    # ─────────────────────────────────────────────────────────────────────────
    # TSR batch
    # ─────────────────────────────────────────────────────────────────────────

    def _process_tsr_batch(self, batch: list[DownloadItem]) -> None:
        """Xử lý batch TSR theo 3 bước:
        1. Lấy ticket song song.
        2. Chờ đủ 10s (tính từ ticket cũ nhất).
        3. Tải song song.
        """
        logger.info(f"⚡ Batch TSR: {len(batch)} item")

        # Bước 1: lấy ticket song song
        for item in batch:
            if item.is_canceled: continue
            item.status = DownloadStatus.TICKET
            self._notify_update(item)

        threads = [
            threading.Thread(target=self._fetch_ticket, args=(item,), daemon=True)
            for item in batch if not item.is_canceled
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        # Hủy các item bị đánh dấu trong khi lấy ticket
        with self._lock:
            for item in list(batch):
                if item.is_canceled:
                    if item in self._active: self._active.remove(item)
                    batch.remove(item)

        ready  = [i for i in batch if i._ticket is not None]
        failed = [i for i in batch if i._ticket is None and i.status != DownloadStatus.ERROR]
        for item in failed:
            self._fail_item(item, "Không thể lấy ticket TSR")

        if not ready:
            logger.warning("❌ Không có item nào lấy được ticket hoặc tất cả bị hủy")
            return

        # Bước 2: chờ đủ WAIT_SECONDS từ ticket cũ nhất
        earliest = min(i._ticket.ticket_time for i in ready)
        remaining = max(0.0, TSRDownloader.WAIT_SECONDS - (time.time() * 1000 - earliest) / 1000)
        if remaining > 0:
            logger.info(f"⏱️ Chờ {remaining:.1f}s cho batch {len(ready)} item...")
            for item in ready:
                item.status = DownloadStatus.WAITING
                self._notify_update(item)
            
            # Chờ có khả năng ngắt (interruptible sleep)
            end_time = time.time() + remaining
            while time.time() < end_time:
                # Nếu tất cả item trong batch bị hủy, thoát luôn
                if all(i.is_canceled for i in ready):
                    break
                time.sleep(0.2)

        # Lọc lại item sẵn sàng (xóa những cái bị hủy trong lúc chờ)
        with self._lock:
            for item in list(ready):
                if item.is_canceled:
                    if item in self._active: self._active.remove(item)
                    ready.remove(item)

        if not ready:
            return

        # Bước 3: tải song song
        logger.info(f"⬇️ Tải song song {len(ready)} file!")
        dl_threads = [
            threading.Thread(target=self._download_tsr_item, args=(item,), daemon=True)
            for item in ready
        ]
        for t in dl_threads:
            t.start()
            item.status = DownloadStatus.DOWNLOADING
            self._notify_update(ready[dl_threads.index(t)])
        for t in dl_threads:
            t.join(timeout=120)

        logger.info(f"✅ Batch TSR hoàn tất: {len(ready)} item")

    def _fetch_ticket(self, item: DownloadItem) -> None:
        """Lấy ticket cho 1 TSR item (chạy trên thread)."""
        max_tries = 3
        for attempt in range(max_tries):
            try:
                tsr_item = TSRItem.from_url(item.url)
                item._ticket = self.tsr_downloader.fetch_ticket(tsr_item)
                return
            except Exception as exc:
                if self._is_rotating or (type(exc).__name__ in ('ProxyError', 'ConnectionError', 'Timeout', 'RequestException')):
                    if self._is_rotating:
                        logger.info(f"🔁 Đang đổi IP, chờ lấy ticket cho {item.url}...")
                        with self._rotation_wait:
                            if self._is_rotating:
                                self._rotation_wait.wait(timeout=60)
                    
                    if attempt < max_tries - 1:
                        time.sleep(2)
                        continue

                logger.error(f"❌ Lỗi ticket {item.url}: {exc}")
                item.status = DownloadStatus.ERROR
                item.error_message = str(exc)
                return
    

    def _download_tsr_item(self, item: DownloadItem) -> None:
        """Tải 1 TSR item bằng ticket đã fetch (chạy trên thread)."""
        staging = self.config.staging_directory
        os.makedirs(staging, exist_ok=True)

        max_tries = 3
        for attempt in range(max_tries):
            try:
                filepath = self.tsr_downloader.download_with_ticket(
                    item._ticket, staging,
                    progress_callback=lambda p, s: self._update_progress(item, p, s),
                )
                if filepath is None:
                    # Thử lại nếu thất bại (TSR thỉnh thoảng lỗi link)
                    if attempt < max_tries - 1:
                        time.sleep(2)
                        continue
                    self._fail_item(item, "Tải xuống TSR thất bại")
                    return

                item.filepath = filepath
                item.filename = os.path.basename(filepath)
                self._post_download(item, filepath)
                return

            except DownloadCanceledError:
                logger.info(f"🚫 Đã hủy TSR: {item.url}")
                with self._lock:
                    if item in self._active: self._active.remove(item)
                return

            except Exception as exc:
                # Kiểm tra xem có phải do đang đổi IP không
                if self._is_rotating or (type(exc).__name__ in ('ProxyError', 'ConnectionError', 'Timeout', 'RequestException')):
                    if self._is_rotating:
                        logger.info(f"🔁 Connection drop (TSR) do đang đổi IP. Chờ tải lại {item.filename}...")
                        with self._rotation_wait:
                            if self._is_rotating:
                                self._rotation_wait.wait(timeout=60)
                    
                    if attempt < max_tries - 1:
                        logger.warning(f"⚠️ Lỗi mạng TSR {item.filename}, thử lại lần {attempt + 2}/{max_tries}")
                        time.sleep(2)
                        continue

                logger.error(f"❌ Lỗi tải TSR {item.url}: {exc}")
                self._fail_item(item, str(exc))
                return

    # ─────────────────────────────────────────────────────────────────────────
    # Post-download: unpack + sort
    # ─────────────────────────────────────────────────────────────────────────

    def _post_download(self, item: DownloadItem, filepath: str) -> None:
        """Sau khi tải xong: giải nén → phân loại → đánh dấu DONE."""
        try:
            # Giải nén
            if self.config.auto_unpack and is_archive(filepath):
                item.status = DownloadStatus.UNPACKING
                self._notify_update(item)
                mod_files = unpack(
                    filepath,
                    extract_to=self.config.staging_directory,
                    delete_after=self.config.delete_archive_after_unpack,
                )
            else:
                mod_files = [filepath]

            if not mod_files:
                item.status = DownloadStatus.DONE
                item.error_message = "Không tìm thấy file mod trong archive"
                self._finish_item(item)
                return

            # Phân loại
            if self.config.auto_sort:
                item.status = DownloadStatus.SORTING
                self._notify_update(item)
                item.sorted_files = self.sorter.sort_files(mod_files)
            else:
                import shutil
                for f in mod_files:
                    dest = os.path.join(self.config.mod_directory, os.path.basename(f))
                    shutil.move(f, dest)
                    item.sorted_files.append(dest)

            item.status   = DownloadStatus.DONE
            item.progress = 1.0
            logger.info(f"✅ Hoàn tất: {item.filename} ({len(item.sorted_files)} file)")

        except Exception as exc:
            logger.error(f"❌ Post-download lỗi: {exc}")
            item.status = DownloadStatus.ERROR
            item.error_message = str(exc)

        self._finish_item(item)

    # ─────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _detect_source(self, url: str) -> DownloadSource:
        if TSRItem.is_valid_url(url):
            return DownloadSource.TSR
        if SFSDownloader.is_valid_url(url):
            return DownloadSource.SFS
        if DirectDownloader.is_valid_url(url):
            return DownloadSource.DIRECT
        return DownloadSource.UNKNOWN

    def _add_sfs_folder(self, folder_url: str) -> Optional[DownloadItem]:
        """Quét folder SFS và thêm từng file vào hàng đợi."""
        logger.info(f"📁 Quét folder SFS: {folder_url}")
        links = self.sfs_downloader.get_folder_links(folder_url)
        if not links:
            logger.warning(f"Không tìm thấy file nào trong folder: {folder_url}")
            return None

        first: Optional[DownloadItem] = None
        for link in links:
            with self._lock:
                already = any(
                    i.url == link
                    for i in self._queue + self._active + self._completed
                )
                if already:
                    continue

            item = DownloadItem(url=link, source=DownloadSource.SFS)
            with self._lock:
                self._queue.append(item)
            self._fire(self.on_item_added, item)
            if first is None:
                first = item

        self.save_history()
        logger.info(f"✅ Thêm {len(links)} file từ folder SFS")
        return first

    def _update_progress(self, item: DownloadItem, progress: float, speed: float = 0.0) -> None:
        """Cập nhật phần trăm tiến trình và báo về GUI."""
        if item.is_canceled:
            raise DownloadCanceledError() # Ngắt kết nối ngay lập tức!

        # Nếu đang đổi IP, tạm dừng chờ
        if self._is_rotating:
            with self._rotation_wait:
                if self._is_rotating:
                    logger.debug(f"⏳ {item.filename} đang chờ đổi IP...")
                    self._rotation_wait.wait(timeout=30)
            
        item.progress = progress
        self._notify_update(item)

        # Kiểm tra bóp băng thông (chỉ áp dụng cho Kemono và nếu tính năng được bật)
        if self.config.auto_rotate_warp and "kemono" in item.url.lower():
            self._check_throttling(item, speed)

    def _check_throttling(self, item: DownloadItem, speed: float) -> None:
        """Kiểm tra xem file có đang bị bóp băng thông không (dưới 100 KB/s)."""
        # 100 KB/s = 100 * 1024 bytes/s
        THRESHOLD = 100 * 1024
        
        if speed > 0 and speed < THRESHOLD:
            count = self._low_speed_counters.get(item.url, 0) + 1
            self._low_speed_counters[item.url] = count
            
            # Nếu bị chậm liên tục trong ~15s (mỗi update cách nhau 0.5s -> 30 lần)
            if count >= 30:
                logger.warning(f"⚠️ Phát hiện bóp băng thông trên {item.filename} ({speed/1024:.1f} KB/s). Đang chuẩn bị đổi IP...")
                self._low_speed_counters[item.url] = 0
                threading.Thread(target=self.rotate_ip, daemon=True).start()
        else:
            self._low_speed_counters[item.url] = 0

    def rotate_ip(self) -> None:
        """Thực hiện ngắt kết nối và kết nối lại Warp để đổi IP."""
        if not self._warp_lock.acquire(blocking=False):
            return # Đang có tiến trình rotate khác chạy rồi
            
        try:
            now = time.time()
            # Tránh rotate quá dày (ít nhất 2 phút giữa các lần)
            if now - self._last_rotation_time < 120:
                logger.info("⏭️ Bỏ qua đổi IP vì vừa mới thực hiện gần đây.")
                return

            with self._rotation_wait:
                self._is_rotating = True

            logger.info("🔄 Đang thực hiện đổi IP qua Warp CLI...")
            import subprocess
            
            warp_path = self.config.warp_cli_path
            
            # 1. Disconnect
            subprocess.run([warp_path, "disconnect"], capture_output=True, check=False)
            time.sleep(2)
            
            # 2. Connect
            subprocess.run([warp_path, "connect"], capture_output=True, check=False)
            
            # Chờ một chút để connection ổn định
            time.sleep(5)
            
            self._last_rotation_time = time.time()
            logger.info("✅ Đã đổi IP thành công (hy vọng thế!)")
            
        except Exception as exc:
            logger.error(f"❌ Lỗi khi thực hiện đổi IP: {exc}")
        finally:
            with self._rotation_wait:
                self._is_rotating = False
                self._rotation_wait.notify_all()
            self._warp_lock.release()

    def _notify_update(self, item: DownloadItem) -> None:
        """Thông báo về GUI. Có cơ chế throttling để tránh lag main thread."""
        now = time.time()
        
        # Chỉ giới hạn với trạng thái DOWNLOADING
        # Luôn cho phép với các trạng thái quan trọng hoặc lần đầu tải
        if item.status == DownloadStatus.DOWNLOADING:
            if now - item._last_ui_update < 0.2: # Tối đa 5 lần mỗi giây (200ms)
                return
        
        item._last_ui_update = now
        self._fire(self.on_item_updated, item)

    def _fail_item(self, item: DownloadItem, message: str) -> None:
        item.status = DownloadStatus.ERROR
        item.error_message = message
        self._finish_item(item)

    def _finish_item(self, item: DownloadItem) -> None:
        """Di chuyển item từ active → completed và kích callbacks."""
        with self._lock:
            if item in self._active:
                self._active.remove(item)
            self._completed.append(item)
        self._notify_update(item)
        self._fire(self.on_item_completed, item)
        self.save_history()

    @staticmethod
    def _fire(callback: Optional[Callable], *args) -> None:
        """Gọi callback an toàn (bỏ qua nếu ``None`` hoặc exception)."""
        if callback:
            try:
                callback(*args)
            except Exception as exc:
                logger.debug(f"Callback error: {exc}")
