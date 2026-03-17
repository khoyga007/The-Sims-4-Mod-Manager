"""
HTTP Utils — Tiện ích tải file dùng chung cho các downloader.

Tránh trùng lặp logic retry và rename .part giữa SFSDownloader và DirectDownloader.
"""
from __future__ import annotations

import os
import re
import time
import logging
import urllib.parse
from typing import Optional

import requests

logger = logging.getLogger("ModManager.HttpUtils")

# ─── Hằng số ─────────────────────────────────────────────────────────────────

#: Đuôi file mod hợp lệ (dùng để phát hiện URL và tên file)
MOD_URL_PATTERN = re.compile(r"\.(package|ts4script|zip|rar|7z)($|\?)", re.IGNORECASE)

#: Số byte tối thiểu để coi file là hợp lệ (tránh tải nhầm trang lỗi HTML)
MIN_FILE_SIZE = 100


def is_html_response(response: requests.Response) -> bool:
    """Kiểm tra response có phải trang HTML không."""
    return "text/html" in response.headers.get("Content-Type", "").lower()


def fetch_file_metadata(session: requests.Session, url: str) -> dict[str, str]:
    """Lấy thông tin file (tên, dung lượng) mà không cần tải file (HEAD request)."""
    try:
        r = session.head(url, allow_redirects=True, timeout=10)
        if r.status_code != 200:
            return {}
        
        filename = extract_filename_from_response(r, url)
        size = int(r.headers.get("Content-Length", 0))
        
        # Format size cho dễ đọc
        if size > 1024 * 1024:
            size_str = f"{size / (1024*1024):.1f} MB"
        else:
            size_str = f"{size / 1024:.0f} KB"
            
        return {"filename": filename, "size_str": size_str, "size_bytes": str(size)}
    except Exception:
        return {}


def extract_filename_from_response(
    response: requests.Response,
    url: str,
    fallback: str = "downloaded_file",
) -> str:
    """Lấy tên file từ response (Content-Disposition → URL → fallback).

    Parameters
    ----------
    response:
        HTTP response.
    url:
        URL gốc dùng để parse tên file nếu header không có.
    fallback:
        Tên dùng khi không tìm được bất kỳ tên nào.

    Returns
    -------
    str
        Tên file an toàn (đã loại ký tự không hợp lệ).
    """
    filename: Optional[str] = None

    # 1. Content-Disposition
    content_disp = response.headers.get("Content-Disposition", "")
    match = re.search(r'filename="?([^";\r\n]+)"?', content_disp)
    if match:
        raw = match.group(1).strip().strip('"')
        if "UTF-8''" in raw:
            raw = urllib.parse.unquote(raw.split("UTF-8''")[1])
        else:
            raw = urllib.parse.unquote(raw)
        filename = raw

    # 2. Query param f= (Kemono style)
    if not filename:
        parsed = urllib.parse.urlparse(url)
        params = urllib.parse.parse_qs(parsed.query)
        if "f" in params:
            filename = params["f"][0]

    # 3. Path component
    if not filename:
        path_name = urllib.parse.unquote(os.path.basename(urllib.parse.urlparse(url).path))
        if path_name and MOD_URL_PATTERN.search(path_name):
            filename = path_name

    if not filename:
        filename = fallback

    # Sau khi unquote, thay thế dấu '+' thành dấu cách (vì unquote không tự chuyển '+' thành ' ')
    filename = filename.replace("+", " ")

    # Loại ký tự Windows không hợp lệ
    filename = re.sub(r'[\\/:*?"<>|]', "_", filename)

    # Đảm bảo có đuôi mod
    if not MOD_URL_PATTERN.search(filename):
        filename += ".package"

    return filename


def rename_part_file(part_path: str, dest_path: str, max_retries: int = 3) -> str:
    """Đổi tên file ``.part`` sang tên thực sau khi tải xong.

    Thử lại nhiều lần để tránh Windows file lock.

    Parameters
    ----------
    part_path:
        Đường dẫn file tạm ``.part``.
    dest_path:
        Đường dẫn đích.
    max_retries:
        Số lần thử tối đa.

    Returns
    -------
    str
        Đường dẫn thực của file sau khi rename (có thể vẫn là ``part_path``
        nếu rename thất bại hoàn toàn).
    """
    for attempt in range(max_retries):
        try:
            time.sleep(0.3)
            if os.path.exists(dest_path):
                os.replace(part_path, dest_path)
            else:
                os.rename(part_path, dest_path)
            return dest_path
        except OSError:
            if attempt < max_retries - 1:
                time.sleep(1.0)
            else:
                logger.warning(f"Không thể rename {os.path.basename(part_path)} → giữ file .part")
                return part_path
    return part_path  # unreachable nhưng mypy cần


def stream_to_file(
    response: requests.Response,
    part_path: str,
    progress_callback=None,
    chunk_size: int = 256 * 1024,
    start_byte: int = 0,
) -> int:
    """Ghi stream response vào file, hỗ trợ nối tiếp (resume).

    Parameters
    ----------
    response:
        HTTP response đang stream.
    part_path:
        Đường dẫn file tạm để ghi.
    progress_callback:
        ``Callable[[float, float], None]`` nhận (tiến trình [0,1], tốc độ bytes/s).
    chunk_size:
        Kích thước mỗi chunk (bytes).
    start_byte:
        Vị trí bắt đầu (dùng khi resume).

    Returns
    -------
    int
        Tổng số byte đã ghi (bao gồm cả phần đã có trước đó).
    """
    content_len = int(response.headers.get("content-length", 0))
    total_size = content_len + start_byte
    downloaded = start_byte

    # 'ab' mode để append nếu start_byte > 0
    mode = "ab" if start_byte > 0 else "wb"
    
    start_time = time.time()
    last_update = start_time
    last_downloaded = downloaded

    with open(part_path, mode) as f:
        for chunk in response.iter_content(chunk_size=chunk_size):
            if not chunk:
                continue
            f.write(chunk)
            downloaded += len(chunk)
            
            now = time.time()
            if progress_callback and total_size > 0:
                elapsed = now - last_update
                if elapsed >= 0.5: # Cập nhật tốc độ mỗi 0.5s
                    speed = (downloaded - last_downloaded) / elapsed
                    progress_callback(downloaded / total_size, speed)
                    last_update = now
                    last_downloaded = downloaded

    return downloaded
