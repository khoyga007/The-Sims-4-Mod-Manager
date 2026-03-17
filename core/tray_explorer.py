import os
import struct
import logging
from typing import Set, Dict, List
from core.conflict_detector import _DBPFReader

logger = logging.getLogger("ModManager.TrayExplorer")

class TrayExplorer:
    """Quét thư mục Tray để tìm xem Nhân vật/Nhà đang dùng những file Mod nào."""
    
    @staticmethod
    def get_cc_for_tray_item(tray_folder: str, mod_folder: str) -> Dict[str, List[str]]:
        """Phân tích nội dung các file Tray để tìm các Mod file được tham chiếu."""
        
        # Bước 1: Quét toàn bộ Mod và Build Index của các Instance ID
        logger.info("Đang xây dựng Index từ thư mục Mod...")
        mod_instance_map: Dict[int, str] = {}
        for root, _, files in os.walk(mod_folder):
            if "_backup" in root or "__" in root: continue
            for fname in files:
                if not fname.endswith((".package")): continue
                path = os.path.join(root, fname)
                
                # dùng _DBPFReader có sẵn để lấy keys siêu tốc
                reader = _DBPFReader(path)
                keys = reader.read_keys()
                if keys:
                    for k in keys:
                        # Lưu Instance ID -> Mod path
                        if k.instance_id not in mod_instance_map:
                            mod_instance_map[k.instance_id] = path

        # Bước 2: Quét thư mục Tray
        logger.info("Đang đọc các file Tray...")
        tray_to_mods: Dict[str, Set[str]] = {}
        
        for root, _, files in os.walk(tray_folder):
            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in {".trayitem", ".sgi", ".hhi", ".bpi", ".rmi", ".room"}:
                    continue
                
                path = os.path.join(root, fname)
                found_mods = set()
                
                # Heuristic siêu tốc: Đọc toàn bộ binary của file Tray.
                # Do file Tray thường rất nhỏ (<1MB), ta quét raw memory tìm các cụm 8-bytes 
                # (64-bit integer) trùng với Instance ID trong Mod Index.
                try:
                    with open(path, "rb") as f:
                        data = f.read()
                        
                        # Quét trượt (sliding window) từng 8 byte? Hơi lâu bằng Python.
                        # Tối ưu (Performance skill): Convert sang mảng uint64 nếu có thể,
                        # hoặc tìm quét byte array nhanh.
                        # Do endianness, Sims 4 dùng little-endian format.
                        # Ta sẽ đọc mảng data thành một series of u64 ints.
                        
                        length = len(data)
                        # Đọc từ offset 0
                        for offset in range(0, length - 8, 4):  # Bước nhảy 4 byte
                            val = struct.unpack_from("<Q", data, offset)[0]
                            if val in mod_instance_map:
                                found_mods.add(mod_instance_map[val])
                except Exception as e:
                    logger.debug(f"Không thể phân tích file tray {fname}: {e}")
                    
                if found_mods:
                    # Gộp chung các file cùng 1 bộ Tray (cùng tên Prefix, khác đuôi)
                    prefix = fname.split('.')[0]
                    if prefix not in tray_to_mods:
                        tray_to_mods[prefix] = set()
                    tray_to_mods[prefix].update(found_mods)
                    
        return {k: list(v) for k, v in tray_to_mods.items()}
