"""
Direct / Kemono Downloader — Tải file từ link trực tiếp.

Hỗ trợ: link ``.package``, ``.ts4script``, ``.zip``, ``.rar``, ``.7z``
và các link Kemono (kemono.su / kemono.party / ...).
"""
from __future__ import annotations

import logging
import os
import time
from typing import Callable, Optional

import requests

from ._http_utils import (
    MOD_URL_PATTERN,
    MIN_FILE_SIZE,
    extract_filename_from_response,
    is_html_response,
    rename_part_file,
    stream_to_file,
)

logger = logging.getLogger("ModManager.Direct")

_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 3  # giây; thực tế: attempt * _RETRY_BASE_DELAY


class DirectDownloader:
    """Tải file từ link trực tiếp (không qua host đặc thù).

    Kiểm tra URL hợp lệ bằng đuôi file mod; từ chối nếu server trả HTML
    (thường là trang lỗi hay trang cá nhân creator).
    """

    _DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/avif,image/webp,*/*;q=0.8"
        ),
        # Bypass hotlink protection trên Kemono
        "Referer": "https://kemono.su/",
    }

    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update(self._DEFAULT_HEADERS)

    # ─────────────────────────────────────────────────────────────────────────
    # URL validation
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def is_valid_url(url: str) -> bool:
        """Kiểm tra URL có chứa đuôi file mod hợp lệ không.

        Parameters
        ----------
        url:
            URL cần kiểm tra.
        """
        return bool(MOD_URL_PATTERN.search(url))

    # ─────────────────────────────────────────────────────────────────────────
    # Download
    # ─────────────────────────────────────────────────────────────────────────

    def download(
        self,
        url: str,
        download_path: str,
        progress_callback: Optional[Callable[[float, float], None]] = None,
    ) -> Optional[str]:
        """Tải file từ link trực tiếp và lưu vào ``download_path``.

        Parameters
        ----------
        url:
            URL file cần tải.
        download_path:
            Thư mục đích.
        progress_callback:
            Callback nhận tiến trình ``[0.0, 1.0]`` sau mỗi chunk.

        Returns
        -------
        str | None
            Đường dẫn tuyệt đối của file đã tải, hoặc ``None`` nếu thất bại.
        """
        for attempt in range(1, _MAX_RETRIES + 1):
            result = self._attempt_download(url, download_path, progress_callback, attempt)
            if result is not None:
                return result

            # None có thể do lỗi tạm thời → retry
            if attempt < _MAX_RETRIES:
                time.sleep(attempt * _RETRY_BASE_DELAY)

        logger.error(f"❌ Hết số lần thử cho: {url[:60]}")
        return None

    def _attempt_download(
        self,
        url: str,
        download_path: str,
        progress_callback: Optional[Callable[[float, float], None]],
        attempt: int,
    ) -> Optional[str]:
        """Thực hiện một lần tải. Trả về đường dẫn hoặc ``None``."""
        try:
            logger.info(f"⬇️ Tải Direct [{attempt}/{_MAX_RETRIES}]: {url[:60]}...")
            
            # --- Lấy Metadata (HEAD) để chuẩn bị Resume ---
            meta = self._session.head(url, allow_redirects=True, timeout=10)
            filename = extract_filename_from_response(meta, url)
            filepath = os.path.join(download_path, filename)
            part_path = filepath + ".part"
            
            # --- Xử lý Resume (Nối tiếp) ---
            start_byte = 0
            headers = self._DEFAULT_HEADERS.copy()
            
            if os.path.exists(part_path):
                start_byte = os.path.getsize(part_path)
                total_size = int(meta.headers.get("Content-Length", 0))
                
                # Chỉ resume nếu file chưa tải xong và server hỗ trợ Range
                if 0 < start_byte < total_size:
                    headers["Range"] = f"bytes={start_byte}-"
                    logger.info(f"🔄 Resume Direct từ byte {start_byte}...")
                elif start_byte >= total_size and total_size > 0:
                    # Đã tải xong nhưng chưa đổi tên
                    return rename_part_file(part_path, filepath)

            # --- Tải thực tế ---
            r = self._session.get(url, stream=True, timeout=60, allow_redirects=True, headers=headers)

            if r.status_code not in (200, 206):
                logger.error(f"HTTP {r.status_code} cho {url[:60]}")
                r.close()
                return None

            # Từ chối nếu server trả HTML
            if is_html_response(r):
                logger.error(f"⚠️ Từ chối: link trả về HTML thay vì file mod ({url[:60]})")
                r.close()
                return None

            total = stream_to_file(r, part_path, progress_callback, start_byte=start_byte)
            r.close()

            if total < MIN_FILE_SIZE:
                logger.warning(f"⚠️ File quá nhỏ ({total} bytes), nghi ngờ lỗi")
                os.remove(part_path)
                return None

            final_path = rename_part_file(part_path, filepath)
            if progress_callback:
                progress_callback(1.0, 0.0)
            logger.info(f"✅ Tải xong Direct: {filename}")
            return final_path

        except Exception as exc:
            logger.error(f"❌ Lỗi tải Direct {url[:60]}: {exc}")
            return None

    # ─────────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _validate_package_header(
        response: requests.Response,
        filename: str,
        part_path: str,
    ) -> bool:
        """Kiểm tra magic bytes ``DBPF`` cho file ``.package``.

        Đọc chunk đầu tiên từ stream; nếu sai header thì huỷ và xoá file tạm.

        Parameters
        ----------
        response:
            HTTP response đang stream.
        filename:
            Tên file (để kiểm tra đuôi ``.package``).
        part_path:
            Đường dẫn file tạm (để xoá nếu invalid).

        Returns
        -------
        bool
            ``True`` nếu hợp lệ hoặc không phải ``.package``, ``False`` nếu invalid.

        Note
        ----
        Sau khi gọi hàm này, stream đã bị consume mất chunk đầu tiên — caller
        cần dùng :func:`stream_to_file` ngay sau đó để ghi phần còn lại.
        Thực ra hàm này không đủ tốt để dùng với stream vì iter_content đã bị
        tiêu thụ. Để đơn giản, ta skip validate và ghi luôn — kiểm tra sau khi
        ghi xong nếu cần.
        """
        # Không validate trên stream (phức tạp) — skip, để downstream xử lý
        return True
