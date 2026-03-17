"""
Mod Manager — Quản lý bật/tắt/xóa/quét mod trong thư mục Mods.

Scan tìm cả file ``.package`` / ``.ts4script`` (enabled) lẫn
``.package.disabled`` / ``.ts4script.disabled`` (disabled).
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

from core.config_manager import ConfigManager

logger = logging.getLogger("ModManager.ModManager")

_ENABLED_EXTENSIONS: frozenset[str] = frozenset({".package", ".ts4script"})
_DISABLED_SUFFIX = ".disabled"


# ─── Data model ───────────────────────────────────────────────────────────────

@dataclass
class ModInfo:
    """Thông tin chi tiết của một mod.

    Attributes
    ----------
    name:
        Tên hiển thị (không có đuôi file).
    filename:
        Tên file thực trên đĩa (bao gồm đuôi, có thể kèm ``.disabled``).
    filepath:
        Đường dẫn tuyệt đối đến file.
    category:
        Tên thư mục con chứa mod (ví dụ ``"09_Hair"``).
    extension:
        Đuôi thực của mod (``".package"`` hoặc ``".ts4script"``).
    size_bytes:
        Kích thước file tính bằng byte.
    enabled:
        ``True`` nếu mod đang bật.
    modified_time:
        Thời điểm sửa đổi cuối (Unix timestamp).
    """

    name: str
    filename: str
    filepath: str
    category: str
    extension: str
    size_bytes: int
    enabled: bool
    modified_time: float = 0.0

    # ── Computed properties ───────────────────────────────────────────────────

    @property
    def size_mb(self) -> float:
        """Kích thước tính bằng MB (làm tròn 2 chữ số)."""
        return round(self.size_bytes / (1024 * 1024), 2)

    @property
    def size_display(self) -> str:
        """Kích thước dạng chuỗi có đơn vị (``"12.3 MB"``, ``"512.0 KB"``)."""
        if self.size_bytes < 1024:
            return f"{self.size_bytes} B"
        if self.size_bytes < 1024 * 1024:
            return f"{self.size_bytes / 1024:.1f} KB"
        return f"{self.size_mb} MB"


# ─── Manager ──────────────────────────────────────────────────────────────────

class ModManager:
    """Quản lý toàn bộ mod trong thư mục Mods.

    Parameters
    ----------
    config:
        Instance :class:`ConfigManager`. ``None`` dùng instance mặc định.
    """

    def __init__(self, config: Optional[ConfigManager] = None) -> None:
        self.config = config or ConfigManager()
        self._mods: list[ModInfo] = []

    # ─────────────────────────────────────────────────────────────────────────
    # Scan
    # ─────────────────────────────────────────────────────────────────────────

    def scan_mods(self) -> list[ModInfo]:
        """Quét toàn bộ thư mục Mods và trả về danh sách mod.

        Bao gồm cả file ``.disabled``.
        Bỏ qua thư mục staging.

        Returns
        -------
        list[ModInfo]
            Danh sách mod, sắp xếp theo (category, name).
        """
        self._mods.clear()
        mod_dir = self.config.mod_directory

        if not os.path.exists(mod_dir):
            logger.error(f"Thư mục Mods không tồn tại: {mod_dir}")
            return self._mods

        staging = os.path.abspath(self.config.staging_directory)

        for root, _dirs, files in os.walk(mod_dir):
            if staging and os.path.abspath(root).startswith(staging):
                continue

            rel     = os.path.relpath(root, mod_dir)
            category = rel.split(os.sep)[0] if rel != "." else "Root"

            for filename in files:
                mod = self._parse_file(
                    filepath=os.path.join(root, filename),
                    filename=filename,
                    category=category,
                )
                if mod:
                    self._mods.append(mod)

        self._mods.sort(key=lambda m: (m.category, m.name.lower()))
        logger.info(
            f"Quét xong: {len(self._mods)} mod "
            f"(enabled: {self.enabled_count}, disabled: {self.disabled_count})"
        )
        return self._mods

    # ─────────────────────────────────────────────────────────────────────────
    # Enable / Disable / Delete
    # ─────────────────────────────────────────────────────────────────────────

    def enable_mod(self, mod: ModInfo) -> bool:
        """Bật mod: bỏ đuôi ``.disabled``.

        Parameters
        ----------
        mod:
            Mod cần bật.

        Returns
        -------
        bool
            ``True`` nếu thành công (bao gồm cả trường hợp đã bật rồi).
        """
        if mod.enabled:
            logger.debug(f"Mod đã bật rồi: {mod.name}")
            return True

        new_path = mod.filepath[: -len(_DISABLED_SUFFIX)]
        return self._rename_mod(mod, new_path, enabled=True, action="Bật")

    def disable_mod(self, mod: ModInfo) -> bool:
        """Tắt mod: thêm đuôi ``.disabled``.

        Parameters
        ----------
        mod:
            Mod cần tắt.

        Returns
        -------
        bool
            ``True`` nếu thành công.
        """
        if not mod.enabled:
            logger.debug(f"Mod đã tắt rồi: {mod.name}")
            return True

        new_path = mod.filepath + _DISABLED_SUFFIX
        return self._rename_mod(mod, new_path, enabled=False, action="Tắt")

    def toggle_mod(self, mod: ModInfo) -> bool:
        """Bật ↔ Tắt mod.

        Parameters
        ----------
        mod:
            Mod cần toggle.
        """
        return self.disable_mod(mod) if mod.enabled else self.enable_mod(mod)

    def delete_mod(self, mod: ModInfo) -> bool:
        """Xóa mod vĩnh viễn khỏi đĩa.

        Parameters
        ----------
        mod:
            Mod cần xóa.

        Returns
        -------
        bool
            ``True`` nếu xóa thành công.
        """
        try:
            os.remove(mod.filepath)
            self._mods.remove(mod)
            logger.info(f"🗑️ Đã xóa mod: {mod.name}")
            return True
        except (OSError, ValueError) as exc:
            logger.error(f"Lỗi xóa mod {mod.name}: {exc}")
            return False

    # ─────────────────────────────────────────────────────────────────────────
    # Query helpers
    # ─────────────────────────────────────────────────────────────────────────

    def search_mods(self, query: str) -> list[ModInfo]:
        """Tìm kiếm mod theo tên (không phân biệt hoa/thường).

        Parameters
        ----------
        query:
            Chuỗi tìm kiếm.
        """
        q = query.lower()
        return [m for m in self._mods if q in m.name.lower()]

    def get_mods_by_category(self, category: str) -> list[ModInfo]:
        """Lấy danh sách mod thuộc một danh mục.

        Parameters
        ----------
        category:
            Tên danh mục (tên thư mục con).
        """
        return [m for m in self._mods if m.category == category]

    def get_categories(self) -> list[str]:
        """Lấy danh sách tất cả danh mục có ít nhất 1 mod, sắp xếp A–Z."""
        return sorted({m.category for m in self._mods})

    # ─────────────────────────────────────────────────────────────────────────
    # Aggregated stats
    # ─────────────────────────────────────────────────────────────────────────

    @property
    def all_mods(self) -> list[ModInfo]:
        return list(self._mods)

    @property
    def total_count(self) -> int:
        return len(self._mods)

    @property
    def enabled_count(self) -> int:
        return sum(1 for m in self._mods if m.enabled)

    @property
    def disabled_count(self) -> int:
        return sum(1 for m in self._mods if not m.enabled)

    @property
    def total_size_bytes(self) -> int:
        return sum(m.size_bytes for m in self._mods)

    @property
    def total_size_display(self) -> str:
        """Tổng dung lượng dạng chuỗi có đơn vị."""
        total = self.total_size_bytes
        if total < 1024 * 1024:
            return f"{total / 1024:.1f} KB"
        if total < 1024 ** 3:
            return f"{total / (1024 * 1024):.1f} MB"
        return f"{total / (1024 ** 3):.2f} GB"

    # ─────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_file(filepath: str, filename: str, category: str) -> Optional[ModInfo]:
        """Parse một file thành ModInfo, hoặc ``None`` nếu không phải mod.

        Parameters
        ----------
        filepath:
            Đường dẫn tuyệt đối.
        filename:
            Tên file.
        category:
            Thư mục con chứa file.
        """
        _, ext = os.path.splitext(filename)
        ext_lower = ext.lower()
        enabled = True
        actual_ext = ext_lower

        if ext_lower == _DISABLED_SUFFIX:
            # *.package.disabled hoặc *.ts4script.disabled
            inner_ext = os.path.splitext(filename[: -len(_DISABLED_SUFFIX)])[1].lower()
            if inner_ext not in _ENABLED_EXTENSIONS:
                return None
            enabled    = False
            actual_ext = inner_ext
        elif ext_lower not in _ENABLED_EXTENSIONS:
            return None

        try:
            stat = os.stat(filepath)
            size, mtime = stat.st_size, stat.st_mtime
        except OSError:
            size, mtime = 0, 0.0

        clean_name = os.path.splitext(filename.replace(_DISABLED_SUFFIX, ""))[0]
        return ModInfo(
            name=clean_name,
            filename=filename,
            filepath=filepath,
            category=category,
            extension=actual_ext,
            size_bytes=size,
            enabled=enabled,
            modified_time=mtime,
        )

    @staticmethod
    def _rename_mod(mod: ModInfo, new_path: str, *, enabled: bool, action: str) -> bool:
        """Rename file mod và cập nhật fields của ModInfo.

        Parameters
        ----------
        mod:
            ModInfo cần cập nhật.
        new_path:
            Đường dẫn mới.
        enabled:
            Trạng thái bật/tắt sau khi rename.
        action:
            Chuỗi hiển thị trong log (``"Bật"`` hoặc ``"Tắt"``).
        """
        try:
            os.rename(mod.filepath, new_path)
            mod.filepath = new_path
            mod.filename = os.path.basename(new_path)
            mod.enabled  = enabled
            logger.info(f"{'✅' if enabled else '⛔'} {action} mod: {mod.name}")
            return True
        except OSError as exc:
            logger.error(f"Lỗi {action.lower()} mod {mod.name}: {exc}")
            return False
