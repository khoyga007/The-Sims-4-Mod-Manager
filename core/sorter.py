"""
Auto-Sorter — Tự động phân loại file mod vào đúng thư mục con.

Phân loại dựa trên từ khóa trong tên file theo quy tắc trong ``config.json``.
File ``.ts4script`` luôn vào ``15_Script_Mods``; file không khớp bất kỳ
từ khóa nào sẽ vào ``99_Other``.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Optional

from core._file_utils import move_with_duplicate_check
from core.config_manager import ConfigManager
from gui._constants import TRAY_EXTENSIONS

logger = logging.getLogger("ModManager.Sorter")

# ─── HQ detection patterns ────────────────────────────────────────────────────

_NON_HQ_MARKERS: tuple[str, ...] = ("nonhq", "non_hq", "non-hq", "nohq", "no_hq")
_HQ_MARKERS:     tuple[str, ...] = ("_hq", ".hq", "-hq", " hq")
_HQ_SUFFIX_RE = re.compile(r"hq\.\w+$")

# ─── Sorter ───────────────────────────────────────────────────────────────────

class ModSorter:
    """Phân loại file mod dựa trên từ khóa trong tên file.

    Parameters
    ----------
    config:
        Instance :class:`ConfigManager`. ``None`` sẽ dùng instance mặc định.
    """

    SCRIPT_FOLDER = "15_Script_Mods"
    OTHER_FOLDER  = "99_Other"

    # Các từ khóa của mod phức tạp (không nên tự động di chuyển)
    COMPLEX_MOD_KEYWORDS = (
        "mcc", "mc_", "mccc", "mc_cmd_center", "wicked", "whim", "ww", 
        "extreme", "violence", "basemental", "nisa",
        "tmex", "betterbuildbuy", "tool_", "ui_cheats"
    )

    def __init__(self, config: Optional[ConfigManager] = None) -> None:
        self.config = config or ConfigManager()

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    def sort_file(self, filepath: str) -> str:
        """Phân loại và di chuyển một file mod vào đúng thư mục con.

        Parameters
        ----------
        filepath:
            Đường dẫn tuyệt đối tới file cần phân loại.

        Returns
        -------
        str
            Đường dẫn mới sau khi đã di chuyển.
        """
        filename = os.path.basename(filepath)
        _, ext   = os.path.splitext(filename)

        # 1. Cơ chế bảo vệ: 
        # - Tuyệt đối không di chuyển nếu là mod phức tạp (kể cả ở root).
        # - Nếu là script và đã ở folder con: Giữ nguyên.
        filename_lower = filename.lower()
        is_complex = any(kw in filename_lower for kw in self.COMPLEX_MOD_KEYWORDS)
        is_script = ext.lower() == ".ts4script"

        if is_complex:
            logger.info(f"🛡️ Bảo vệ {filename} (mod phức tạp): Giữ nguyên vị trí.")
            return filepath

        rel_path = os.path.relpath(filepath, self.config.mod_directory)
        is_in_subfolder = os.sep in rel_path

        if is_in_subfolder and is_script:
            logger.info(f"🛡️ Bảo vệ {filename} (script đã ở folder con): Giữ nguyên.")
            return filepath

        # 2. Scripts ở root -> chuyển vào folder script mặc định
        if is_script:
            logger.info(f"📂 {filename} → {self.SCRIPT_FOLDER} (script mod)")
            return self._move(filepath, self.SCRIPT_FOLDER)

        # 3. Tray items (.blueprint, .trayitem, ...) → thư mục Tray
        if ext.lower() in TRAY_EXTENSIONS:
            logger.info(f"📦 {filename} → Thư mục Tray")
            return self._move(filepath, "", base_dir=self.config.tray_directory)

        # 4. Tìm thư mục khớp từ khóa
        folder = self._match_folder(filename_lower)

        # Phát hiện HQ / NonHQ → thư mục con
        hq_sub = self._detect_hq(filename_lower)
        target = os.path.join(folder, hq_sub) if hq_sub else folder

        return self._move(filepath, target)

    def sort_files(self, file_list: list[str]) -> list[str]:
        """Phân loại danh sách file mod.

        Parameters
        ----------
        file_list:
            Danh sách đường dẫn tuyệt đối.

        Returns
        -------
        list[str]
            Danh sách đường dẫn mới sau khi phân loại.
        """
        results: list[str] = []
        for filepath in file_list:
            if os.path.isfile(filepath):
                results.append(self.sort_file(filepath))
        logger.info(f"✅ Phân loại {len(results)}/{len(file_list)} file")
        return results

    def get_category_for_file(self, filename: str) -> str:
        """Xác định danh mục của file mà không di chuyển.

        Parameters
        ----------
        filename:
            Tên file (không cần đường dẫn đầy đủ).
        """
        _, ext = os.path.splitext(filename)
        if ext.lower() == ".ts4script":
            return self.SCRIPT_FOLDER
        return self._match_folder(filename.lower())

    def is_protected(self, filename: str) -> bool:
        """Kiểm tra xem file có thuộc diện bảo vệ (không tự động gom nhóm sâu) hay không."""
        filename_lower = filename.lower()
        ext = os.path.splitext(filename_lower)[1]
        return (
            ext == ".ts4script" or 
            any(kw in filename_lower for kw in self.COMPLEX_MOD_KEYWORDS)
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _match_folder(self, filename_lower: str) -> str:
        """Tìm thư mục phù hợp dựa trên từ khóa (trả về ``99_Other`` nếu không khớp).

        Parameters
        ----------
        filename_lower:
            Tên file đã lowercase.
        """
        sort_rules = self.config.sort_rules
        for folder, keywords in sort_rules.items():
            if folder in (self.SCRIPT_FOLDER, self.OTHER_FOLDER):
                continue
            for keyword in keywords:
                if keyword in filename_lower:
                    logger.info(f"📂 khớp '{keyword}' → {folder}")
                    return folder

        logger.info(f"📂 không khớp từ khóa → {self.OTHER_FOLDER}")
        return self.OTHER_FOLDER

    @staticmethod
    def _detect_hq(filename_lower: str) -> Optional[str]:
        """Phát hiện phiên bản HQ / NonHQ từ tên file.

        Kiểm tra NonHQ trước (vì ``"nonhq"`` chứa ``"hq"``).

        Parameters
        ----------
        filename_lower:
            Tên file đã lowercase.

        Returns
        -------
        str | None
            ``"NonHQ"``, ``"HQ"``, hoặc ``None`` nếu không xác định được.
        """
        if any(m in filename_lower for m in _NON_HQ_MARKERS):
            return "NonHQ"
        if any(m in filename_lower for m in _HQ_MARKERS):
            return "HQ"
        if _HQ_SUFFIX_RE.search(filename_lower):
            return "HQ"
        return None

    def _move(self, filepath: str, folder_name: str, base_dir: Optional[str] = None) -> str:
        """Di chuyển file vào thư mục đích.

        Parameters
        ----------
        filepath:
            Đường dẫn nguồn.
        folder_name:
            Tên thư mục con.
        base_dir:
            Thư mục gốc (mặc định là mod_directory).
        """
        root = base_dir or self.config.mod_directory
        target_dir = os.path.join(root, folder_name) if folder_name else root
        os.makedirs(target_dir, exist_ok=True)

        return move_with_duplicate_check(filepath, target_dir)
