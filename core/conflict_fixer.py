"""
Conflict Fixer — "Phẫu thuật" file .package để loại bỏ các Resource ID trùng lặp.

Công cụ này cực kỳ hữu ích khi người dùng đã lỡ xóa backup của các file merged.
Nó sẽ đọc file merged, lọc bỏ các resource gây xung đột, và ghi lại file sạch.
"""
from __future__ import annotations

import logging
import os
import shutil
import threading
from typing import Callable, Optional

from core.conflict_detector import ScanResult, ResourceKey
from core.package_merger import _DBPFFullReader, _DBPFWriter, ResourceEntry

logger = logging.getLogger("ModManager.ConflictFixer")

class ConflictFixer:
    """Xử lý "phẫu thuật" loại bỏ xung đột trực tiếp trên file .package."""

    def __init__(self, progress_callback: Optional[Callable[[int, int, str], None]] = None):
        self._progress = progress_callback
        self._reader = _DBPFFullReader()
        self._writer = _DBPFWriter()

    def fix_all(self, scan_result: ScanResult) -> int:
        """
        Xử lý toàn bộ xung đột trong kết quả quét.
        Trả về số lượng file đã được "phẫu thuật" thành công.
        """
        if not scan_result.conflicts:
            return 0

        # 1. Xác định file nào cần xóa cái gì
        # path -> set of (type, group, inst)
        remove_map: dict[str, set[tuple[int, int, int]]] = {}
        
        for conflict in scan_result.conflicts:
            # Nguyên tắc: File đầu tiên trong danh sách giữ lại, các file sau phải xóa
            # Ưu tiên giữ lại file có tên xếp trước (thường là folder 01, 02...)
            sorted_pkgs = sorted(conflict.packages)
            winner = sorted_pkgs[0]
            losers = sorted_pkgs[1:]
            
            key_tuple = (conflict.key.type_id, conflict.key.group_id, conflict.key.instance_id)
            
            for loser in losers:
                if loser not in remove_map:
                    remove_map[loser] = set()
                remove_map[loser].add(key_tuple)

        if not remove_map:
            return 0

        total_files = len(remove_map)
        fixed_count = 0

        # 2. Thực hiện phẫu thuật từng file
        for i, (filepath, keys_to_remove) in enumerate(remove_map.items()):
            filename = os.path.basename(filepath)
            if self._progress:
                self._progress(i + 1, total_files, f"Đang phẫu thuật {filename}...")

            success = self._surgery(filepath, keys_to_remove)
            if success:
                fixed_count += 1
                logger.info(f"Đã phẫu thuật xong: {filename} (Xóa {len(keys_to_remove)} resources)")

        return fixed_count

    def _surgery(self, filepath: str, keys_to_remove: set[tuple[int, int, int]]) -> bool:
        """Thực hiện đọc -> lọc -> ghi đè file."""
        try:
            # Đọc toàn bộ entries
            entries = self._reader.read(filepath)
            if not entries:
                return False

            # Lọc bỏ các entries trùng lặp
            cleaned_entries = [
                e for e in entries 
                if (e.type_id, e.group_id, e.instance_id) not in keys_to_remove
            ]

            if len(cleaned_entries) == len(entries):
                return True # Không có gì thay đổi (có thể file thắng ở các xung đột khác)

            # Tạo bản backup tạm .bak (Phòng hờ lỗi ghi nửa chừng)
            bak_path = filepath + ".bak"
            shutil.copy2(filepath, bak_path)

            try:
                # Ghi đè file gốc bằng bản sạch
                # Lưu ý: _DBPFWriter ghi theo kiểu lazy copy từ source_file của entries.
                # Vì chúng ta đang ghi đè chính source_file, ta cần trỏ entries vào bản .bak
                for e in cleaned_entries:
                    e.source_file = bak_path

                self._writer.write(filepath, cleaned_entries)
                
                # Thành công -> Xóa backup tạm
                os.remove(bak_path)
                return True
            except Exception as e:
                logger.error(f"Lỗi khi ghi file phẫu thuật {filepath}: {e}")
                # Thất bại -> Khôi phục từ .bak
                if os.path.exists(bak_path):
                    shutil.move(bak_path, filepath)
                return False

        except Exception as e:
            logger.error(f"Lỗi phẫu thuật {filepath}: {e}")
            return False
