"""
SimsFileShare Downloader — Tải file từ simfileshare.net.

Hỗ trợ:
- Link download đơn lẻ: ``simfileshare.net/download/<id>/``
- Link folder: ``simfileshare.net/folder/<id>/`` (tải tất cả file)

SFS ``/download/ID/`` là DIRECT download — server trả file trực tiếp.
"""
from __future__ import annotations

import logging
import os
import re
import time
from typing import Callable, Optional

import requests

from ._http_utils import (
    MIN_FILE_SIZE,
    is_html_response,
    rename_part_file,
    stream_to_file,
)

logger = logging.getLogger("ModManager.SFS")

_SFS_DOWNLOAD_RE = re.compile(r"simfileshare\.net/download/(\d+)", re.IGNORECASE)
_SFS_FOLDER_RE   = re.compile(r"simfileshare\.net/folder/(\d+)", re.IGNORECASE)

_MAX_RETRIES   = 5
_RATE_DELAY    = 1.5   # giây tối thiểu giữa các request


class SFSDownloader:
    """Tải file từ SimsFileShare — hỗ trợ cả download đơn và folder.

    Rate-limiting được tích hợp sẵn để tránh bị server chặn.
    """

    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/octet-stream, application/zip, */*",
        })
        self._last_request_time = 0.0

    # ─────────────────────────────────────────────────────────────────────────
    # URL helpers
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def is_valid_url(url: str) -> bool:
        """Kiểm tra URL có phải link SFS (download hoặc folder) không."""
        return bool(_SFS_DOWNLOAD_RE.search(url)) or bool(_SFS_FOLDER_RE.search(url))

    @staticmethod
    def is_folder_url(url: str) -> bool:
        """Kiểm tra URL có phải link folder SFS không."""
        return bool(_SFS_FOLDER_RE.search(url))

    @staticmethod
    def extract_file_id(url: str) -> Optional[str]:
        """Trích xuất ID file từ URL SFS download.

        Parameters
        ----------
        url:
            URL SFS download.

        Returns
        -------
        str | None
            ID dạng chuỗi, hoặc ``None`` nếu URL không hợp lệ.
        """
        match = _SFS_DOWNLOAD_RE.search(url)
        return match.group(1) if match else None

    # ─────────────────────────────────────────────────────────────────────────
    # Folder scan
    # ─────────────────────────────────────────────────────────────────────────

    def get_folder_links(self, folder_url: str) -> list[str]:
        """Lấy danh sách link download từ một folder SFS."""
        metadata = self.get_folder_metadata(folder_url)
        return [item["url"] for item in metadata]

    def get_folder_metadata(self, folder_url: str) -> list[dict]:
        """Lấy danh sách metadata (tên, size, url) từ một folder SFS.
        
        Returns
        -------
        list[dict]
            Danh sách chi tiết: [{"name": str, "size": str, "url": str, "id": str}]
        """
        try:
            logger.info(f"📁 Đang quét metadata folder SFS: {folder_url}")
            resp = self._session.get(folder_url, timeout=15)

            if resp.status_code != 200:
                logger.error(f"Truy cập folder SFS thất bại: HTTP {resp.status_code}")
                return []

            # Trích xuất các khối file trong HTML của SFS folder
            # SFS folder thường có cấu trúc: <a href="/download/ID/">Filename</a> ... <td>Size</td>
            results = []
            
            # Regex tìm các cụm: ID, Filename
            # Cấu trúc SFS có thể là: <a href="/download/123/">Tên file</a>
            # Ta dùng regex linh hoạt hơn để bỏ qua các attributes khác nếu có
            items = re.findall(r'href="/download/(\d+)/?[^"]*">([^<]+)</a>', resp.text)
            
            for fid, fname in items:
                # Tìm size bằng cách tìm đoạn text gần đó (thường nằm trong thẻ td tiếp theo)
                # Cấu trúc mẫu: <td><a ...></a></td><td>1.2 MB</td>
                size_match = re.search(rf'/download/{fid}/.*?</td>\s*<td[^>]*>([^<]+)</td>', resp.text, re.DOTALL)
                fsize = size_match.group(1).strip() if size_match else "Unknown"
                
                results.append({
                    "id": fid,
                    "name": fname.strip(),
                    "size": fsize,
                    "url": f"https://simfileshare.net/download/{fid}/"
                })

            logger.info(f"📁 Tìm thấy {len(results)} file trong folder kèm metadata")
            return results

        except Exception as exc:
            logger.error(f"❌ Lỗi quét metadata folder SFS: {exc}")
            return []

    # ─────────────────────────────────────────────────────────────────────────
    # Single file download
    # ─────────────────────────────────────────────────────────────────────────

    def download(
        self,
        url: str,
        download_path: str,
        progress_callback: Optional[Callable[[float, float], None]] = None,
        max_retries: int = _MAX_RETRIES,
    ) -> Optional[str]:
        """Tải một file từ SFS và lưu vào ``download_path``.

        Parameters
        ----------
        url:
            URL SFS download.
        download_path:
            Thư mục đích.
        progress_callback:
            Callback nhận tiến trình ``[0.0, 1.0]``.
        max_retries:
            Số lần thử tối đa (mặc định :data:`_MAX_RETRIES`).

        Returns
        -------
        str | None
            Đường dẫn tuyệt đối file đã tải, hoặc ``None`` nếu thất bại.
        """
        file_id = self.extract_file_id(url)
        if not file_id:
            logger.error(f"URL SFS không hợp lệ: {url}")
            return None

        download_url = f"https://simfileshare.net/download/{file_id}/"

        for attempt in range(1, max_retries + 1):
            result = self._attempt_download(
                download_url, download_path, progress_callback, attempt, max_retries
            )
            if result is not None:
                return result

        logger.error(f"❌ Hết số lần thử cho: {url}")
        return None

    def _attempt_download(
        self,
        url: str,
        download_path: str,
        progress_callback: Optional[Callable[[float, float], None]],
        attempt: int,
        max_retries: int,
    ) -> Optional[str]:
        """Thực hiện một lần tải. Trả về đường dẫn hoặc ``None``."""
        file_id = self.extract_file_id(url)
        try:
            self._rate_limit()
            logger.info(f"⬇️ Tải SFS [{attempt}/{max_retries}]: {url}")
            r = self._session.get(url, stream=True, timeout=60, allow_redirects=True)

            # 503 = server quá tải → chờ và thử lại
            if r.status_code == 503:
                wait = attempt * 5
                logger.warning(f"⚠️ SFS 503 — chờ {wait}s rồi thử lại...")
                r.close()
                time.sleep(wait)
                return None

            if r.status_code != 200:
                logger.error(f"SFS HTTP {r.status_code}")
                r.close()
                time.sleep(attempt * 3)
                return None

            # HTML → rate-limit hoặc lỗi từ SFS
            if is_html_response(r):
                wait = attempt * 5
                logger.warning(f"⚠️ SFS trả HTML thay vì file — chờ {wait}s...")
                r.close()
                time.sleep(wait)
                return None

            # 🚀 JDownloader style: Sử dụng trực tiếp CDN nếu có thể trích xuất ID
            cdn_url = f"https://cdn.simfileshare.net/download/{file_id}/?dl"
            
            # Lấy tên file thực tế (thử dùng HEAD trên CDN trước để lấy metadata chính xác)
            meta = self._session.head(cdn_url, allow_redirects=True, timeout=10)
            from ._http_utils import extract_filename_from_response
            filename = extract_filename_from_response(meta, cdn_url)
            
            filepath  = os.path.join(download_path, filename)
            part_path = filepath + ".part"
            
            # --- Hỗ trợ Resume (Nối tiếp) ---
            start_byte = 0
            headers = {}
            if os.path.exists(part_path):
                start_byte = os.path.getsize(part_path)
                # Kiểm tra size tổng để xem có thực sự cần resume không
                total_size = int(meta.headers.get("Content-Length", 0))
                if 0 < start_byte < total_size:
                    headers["Range"] = f"bytes={start_byte}-"
                    logger.info(f"🔄 Resume SFS từ byte {start_byte}...")
                elif start_byte >= total_size and total_size > 0:
                    # Đã tải xong nhưng chưa đổi tên
                    return rename_part_file(part_path, filepath)

            # Thực hiện tải thực tế từ CDN
            r_cdn = self._session.get(cdn_url, stream=True, timeout=60, headers=headers)
            
            if r_cdn.status_code not in (200, 206):
                logger.warning(f"CDN trả về {r_cdn.status_code}, fallback về URL chính.")
                r_cdn.close()
                # Nếu CDN lỗi, dùng luôn stream từ request cũ (r)
                downloaded = stream_to_file(r, part_path, progress_callback)
            else:
                downloaded = stream_to_file(r_cdn, part_path, progress_callback, start_byte=start_byte)
                r_cdn.close()
            
            r.close()

            if downloaded < MIN_FILE_SIZE:
                logger.warning(f"⚠️ File quá nhỏ ({downloaded} bytes)")
                os.remove(part_path)
                time.sleep(attempt * 5)
                return None

            final_path = rename_part_file(part_path, filepath)
            if progress_callback:
                progress_callback(1.0, 0.0)
            logger.info(f"✅ Tải xong SFS: {filename} ({downloaded / 1024:.0f} KB)")
            return final_path

        except requests.exceptions.ConnectionError as exc:
            logger.warning(f"⚠️ Connection error [{attempt}]: {exc}")
            time.sleep(attempt * 5)
            return None
        except Exception as exc:
            logger.error(f"❌ Lỗi tải SFS [{attempt}]: {exc}")
            if attempt < max_retries:
                time.sleep(attempt * 3)
            return None

    # ─────────────────────────────────────────────────────────────────────────
    # Rate limiting
    # ─────────────────────────────────────────────────────────────────────────

    def _rate_limit(self) -> None:
        """Chờ đủ khoảng cách tối thiểu giữa các request."""
        elapsed = time.time() - self._last_request_time
        if elapsed < _RATE_DELAY:
            time.sleep(_RATE_DELAY - elapsed)
        self._last_request_time = time.time()
