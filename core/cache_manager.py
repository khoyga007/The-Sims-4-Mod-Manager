"""
Cache Manager — Xử lý dọn dẹp các file cache của The Sims 4.

Giúp game chạy mượt hơn, tránh lỗi dữ liệu cũ sau khi cài mod mới.
"""
from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger("ModManager.CacheManager")

class CacheManager:
    """Quản lý các file cache của game."""

    def __init__(self, ts4_dir: Optional[str] = None) -> None:
        """
        Parameters
        ----------
        ts4_dir:
            Đường dẫn thư mục The Sims 4 (trong Documents).
            Nếu None sẽ tự tìm.
        """
        if ts4_dir:
            self._ts4_dir = Path(ts4_dir)
        else:
            from core.exception_parser import ExceptionParser
            self._ts4_dir = ExceptionParser._find_ts4_dir()

    def clear_cache(self) -> bool:
        """Thực hiện xóa toàn bộ cache.

        Returns
        -------
        bool: True nếu thành công hoặc không có gì để xóa.
        """
        if not self._ts4_dir or not self._ts4_dir.exists():
            logger.warning(f"Không tìm thấy thư mục TS4 để xóa cache: {self._ts4_dir}")
            return False

        logger.info(f"Bắt đầu dọn dẹp cache tại: {self._ts4_dir}")

        # Các file lẻ cần xóa
        files_to_delete = [
            "localthumbcache.package",
            "avatarcache.package",
            "clientDB.package",
            "notify.glob",
        ]

        # Các thư mục cần làm trống (không xóa chính thư mục đó)
        folders_to_empty = [
            "cache",
            "cachestr",
            "onlinethumbnailcache",
            "lotcachedata",
            "saves/scratch", # Lưu trữ tạm của save game, hay gây lỗi rollback
        ]

        # Các pattern file rác (log, crash dump)
        patterns_to_delete = [
            "lastException*.txt",
            "lastUIException*.txt",
            "lastVersion.txt",
            "*.mdmp",
        ]

        for filename in files_to_delete:
            fpath = self._ts4_dir / filename
            if fpath.exists():
                try:
                    fpath.unlink()
                    logger.debug(f"Đã xóa file cache: {filename}")
                except Exception as exc:
                    logger.error(f"Lỗi xóa {filename}: {exc}")

        # Xóa theo pattern
        for pattern in patterns_to_delete:
            for fpath in self._ts4_dir.glob(pattern):
                try:
                    fpath.unlink()
                    logger.debug(f"Đã xóa file rác: {fpath.name}")
                except Exception as exc:
                    logger.error(f"Lỗi xóa pattern {pattern}: {exc}")

        for foldername in folders_to_empty:
            dpath = self._ts4_dir / foldername
            if dpath.exists() and dpath.is_dir():
                try:
                    # Xóa toàn bộ nội dung trong thư mục
                    for item in dpath.iterdir():
                        if item.is_file():
                            item.unlink()
                        elif item.is_dir():
                            shutil.rmtree(item)
                    logger.debug(f"Đã làm trống thư mục cache: {foldername}")
                except Exception as exc:
                    logger.error(f"Lỗi dọn dẹp {foldername}: {exc}")

        logger.info("Hoàn tất dọn dẹp cache.")
        return True
