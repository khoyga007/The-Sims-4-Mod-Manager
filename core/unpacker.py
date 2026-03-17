"""
Auto-Unpacker — Tự động giải nén ``.zip``, ``.rar``, ``.7z`` và lọc file mod.

Ưu tiên dùng 7-Zip (nếu có) cho tất cả định dạng.
Fallback sang thư viện Python thuần cho ``.zip``,
``rarfile`` / ``patoolib`` cho ``.rar``,
``py7zr`` cho ``.7z``.

Hỗ trợ giải nén đệ quy (archive lồng trong archive).
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import zipfile
from typing import Optional

from core._file_utils import move_with_duplicate_check, safe_remove
from gui._constants import TRAY_EXTENSIONS, MOD_EXTENSIONS

logger = logging.getLogger("ModManager.Unpacker")

# ─── Constants ────────────────────────────────────────────────────────────────

#: Đuôi file mod hợp lệ cần giữ lại
VALID_MOD_EXTENSIONS: frozenset[str] = MOD_EXTENSIONS | TRAY_EXTENSIONS

#: Đuôi file archive được hỗ trợ
ARCHIVE_EXTENSIONS: frozenset[str] = frozenset({".zip", ".rar", ".7z"})

#: Đuôi file rác không cần thiết (sẽ bị bỏ qua trong archive)
_JUNK_EXTENSIONS: frozenset[str] = frozenset({
    ".txt", ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp",
    ".url", ".pdf", ".html", ".htm", ".doc", ".docx", ".rtf",
    ".md", ".log", ".ini", ".cfg", ".xml", ".json",
})

_SEVEN_ZIP_PATHS: tuple[str, ...] = (
    r"C:\Program Files\7-Zip\7z.exe",
    r"C:\Program Files (x86)\7-Zip\7z.exe",
)


# ─── 7-Zip detection ──────────────────────────────────────────────────────────

def _find_7zip() -> Optional[str]:
    """Tìm đường dẫn ``7z.exe`` trong các vị trí phổ biến và trong PATH."""
    for path in _SEVEN_ZIP_PATHS:
        if os.path.exists(path):
            return path
    try:
        result = subprocess.run(["where", "7z"], capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip().splitlines()[0]
    except Exception:
        pass
    return None


SEVEN_ZIP: Optional[str] = _find_7zip()
if SEVEN_ZIP:
    logger.info(f"7-Zip tìm thấy: {SEVEN_ZIP}")


# ─── Public helpers ───────────────────────────────────────────────────────────

def is_archive(filepath: str) -> bool:
    """Kiểm tra file có phải archive được hỗ trợ không.

    Parameters
    ----------
    filepath:
        Đường dẫn file.
    """
    _, ext = os.path.splitext(filepath)
    return ext.lower() in ARCHIVE_EXTENSIONS


def is_valid_mod_file(filepath: str) -> bool:
    """Kiểm tra file có phải mod hợp lệ không.

    Parameters
    ----------
    filepath:
        Đường dẫn file.
    """
    _, ext = os.path.splitext(filepath)
    return ext.lower() in VALID_MOD_EXTENSIONS


# ─── Backend extractors ───────────────────────────────────────────────────────

def _extract_7zip(archive_path: str, extract_to: str) -> list[str]:
    """Giải nén bằng 7-Zip (hỗ trợ zip, rar, 7z và nhiều hơn).

    Parameters
    ----------
    archive_path:
        Đường dẫn file archive.
    extract_to:
        Thư mục đích.

    Returns
    -------
    list[str]
        Danh sách đường dẫn file đã giải nén, rỗng nếu thất bại.
    """
    if not SEVEN_ZIP:
        return []
    try:
        result = subprocess.run(
            [SEVEN_ZIP, "x", archive_path, f"-o{extract_to}", "-y", "-bso0", "-bsp0"],
            capture_output=True, text=True, timeout=3600,
        )
        if result.returncode == 0:
            files = [
                os.path.join(root, f)
                for root, _, fs in os.walk(extract_to)
                for f in fs
            ]
            logger.info(
                f"7-Zip: {os.path.basename(archive_path)} → {len(files)} file"
            )
            return files
        logger.warning(f"7-Zip lỗi (code {result.returncode}): {result.stderr[:200]}")
    except Exception as exc:
        logger.warning(f"7-Zip exception: {exc}")
    return []


def _extract_zip(archive_path: str, extract_to: str) -> list[str]:
    """Giải nén ``.zip`` bằng thư viện Python chuẩn.

    Parameters
    ----------
    archive_path:
        Đường dẫn file ``.zip``.
    extract_to:
        Thư mục đích.
    """
    try:
        with zipfile.ZipFile(archive_path, "r") as zf:
            zf.extractall(extract_to)
            files = [
                os.path.join(extract_to, name)
                for name in zf.namelist()
                if not name.endswith("/")
            ]
        logger.info(f"ZIP: {os.path.basename(archive_path)} → {len(files)} file")
        return files
    except zipfile.BadZipFile:
        logger.error(f"File ZIP bị hỏng: {os.path.basename(archive_path)}")
    except Exception as exc:
        logger.error(f"Lỗi giải nén ZIP: {exc}")
    return []


def _extract_rar(archive_path: str, extract_to: str) -> list[str]:
    """Giải nén ``.rar``: thử 7-Zip → rarfile → patoolib.

    Parameters
    ----------
    archive_path:
        Đường dẫn file ``.rar``.
    extract_to:
        Thư mục đích.
    """
    result = _extract_7zip(archive_path, extract_to)
    if result:
        return result

    try:
        import rarfile  # type: ignore[import]
        with rarfile.RarFile(archive_path, "r") as rf:
            rf.extractall(extract_to)
            return [
                os.path.join(extract_to, name)
                for name in rf.namelist()
                if not name.endswith("/")
            ]
    except Exception:
        pass

    try:
        import patoolib  # type: ignore[import]
        patoolib.extract_archive(archive_path, outdir=extract_to, verbosity=-1)
        return [
            os.path.join(root, f)
            for root, _, fs in os.walk(extract_to)
            for f in fs
        ]
    except Exception as exc:
        logger.error(f"Không thể giải nén RAR: {exc}. Cài 7-Zip hoặc WinRAR.")
    return []


def _extract_7z(archive_path: str, extract_to: str) -> list[str]:
    """Giải nén ``.7z``: thử 7-Zip → py7zr.

    Parameters
    ----------
    archive_path:
        Đường dẫn file ``.7z``.
    extract_to:
        Thư mục đích.
    """
    result = _extract_7zip(archive_path, extract_to)
    if result:
        return result

    try:
        import py7zr  # type: ignore[import]
        with py7zr.SevenZipFile(archive_path, mode="r") as sz:
            sz.extractall(path=extract_to)
            return [os.path.join(extract_to, name) for name in sz.getnames()]
    except Exception as exc:
        logger.error(f"Lỗi giải nén 7Z: {exc}")
    return []


# ─── Main unpack ──────────────────────────────────────────────────────────────

_EXTRACTORS = {
    ".zip": lambda p, d: _extract_7zip(p, d) or _extract_zip(p, d),
    ".rar": _extract_rar,
    ".7z":  _extract_7z,
}


def unpack(
    archive_path: str,
    extract_to: Optional[str] = None,
    delete_after: bool = True,
) -> list[str]:
    """Giải nén archive và trả về danh sách file mod hợp lệ.

    Hỗ trợ giải nén đệ quy (archive lồng nhau).
    Lọc bỏ file rác, chỉ giữ ``.package`` và ``.ts4script``.

    Parameters
    ----------
    archive_path:
        Đường dẫn file archive.
    extract_to:
        Thư mục đích. Mặc định là thư mục chứa archive.
    delete_after:
        Xóa file archive gốc sau khi giải nén thành công.

    Returns
    -------
    list[str]
        Danh sách đường dẫn tuyệt đối của các file mod hợp lệ.
    """
    if extract_to is None:
        extract_to = os.path.dirname(archive_path)

    _, ext = os.path.splitext(archive_path)
    extractor = _EXTRACTORS.get(ext.lower())
    if not extractor:
        logger.warning(f"Định dạng nén không được hỗ trợ: {ext}")
        return []

    # Tạo thư mục tạm riêng để tránh lẫn với file đang có
    archive_stem = os.path.splitext(os.path.basename(archive_path))[0]
    temp_dir = os.path.join(extract_to, f"_unpack_{archive_stem}")
    os.makedirs(temp_dir, exist_ok=True)

    extractor(archive_path, temp_dir)

    # Thu thập file mod hợp lệ (đệ quy)
    valid_files: list[str] = []
    for root, _dirs, files in os.walk(temp_dir):
        for filename in files:
            filepath = os.path.join(root, filename)

            if is_archive(filepath):
                # Archive lồng nhau → giải nén đệ quy
                nested = unpack(filepath, temp_dir, delete_after=True)
                valid_files.extend(nested)
            elif is_valid_mod_file(filepath):
                # Di chuyển ra thư mục đích với kiểm tra trùng lặp
                dest = move_with_duplicate_check(filepath, extract_to)
                valid_files.append(dest)
                logger.info(f"  ✓ {os.path.basename(dest)}")
            else:
                logger.debug(f"  ✗ Bỏ qua: {filename}")

    # Dọn dẹp
    safe_remove(temp_dir)
 
    if delete_after and os.path.exists(archive_path):
        if safe_remove(archive_path):
            logger.info(f"Đã xóa archive gốc: {os.path.basename(archive_path)}")

    logger.info(
        f"{len(valid_files)} file mod từ {os.path.basename(archive_path)}"
    )
    return valid_files


# _unique_dest removed, replaced by move_with_duplicate_check in _file_utils
