import os
import struct
import logging
import io
from typing import List, Set, Dict, Tuple
from core.conflict_detector import _DBPFReader
from core.package_merger import _DBPFFullReader

logger = logging.getLogger("ModManager.OrphanScanner")

GEOM_TYPE = b"\x34\x0F\xD1\x01" # 0x01D10F34 in Little-Endian byte array

class OrphanScanner:
    """Máy quét đồ tàng hình: Tìm Mod Recolor bị thiếu Mesh gốc (Orphan Mesh)."""
    
    @staticmethod
    def scan_missing_meshes(mod_folder: str, progress_callback=None) -> List[str]:
        """Trả về danh sách các file .package chứa đồ Recolor nhưng không tìm thấy file có mã Mesh tương ứng."""
        
        all_packages = []
        for root, _, files in os.walk(mod_folder):
             if "_backup" in root or "__" in root: continue
             for f in files:
                 if f.endswith(".package"):
                     all_packages.append(os.path.join(root, f))
                     
        total = len(all_packages)
        logger.info(f"Đang quét {total} file tìm Orphan Mesh...")
        
        # Bước 1: Thu thập tất cả GEOM (0x01D10F34) keys có mặt trên hệ thống
        available_geom_instances: Set[int] = set()
        
        # Bước 2: Quét raw memory tìm các tham chiếu TGI trỏ đến GEOM
        required_geoms_per_file: Dict[str, Set[int]] = {}
        
        for i, filepath in enumerate(all_packages):
            if progress_callback:
                progress_callback(i + 1, total, f"Đang quét {os.path.basename(filepath)}")
                
            required = set()
            try:
                # Dùng full reader để load raw data của CAS Part
                reader = _DBPFFullReader()
                resources = reader.read(filepath)
                
                for res in resources:
                    if res.type_id == 0x01D10F34: # Khai báo cục Mesh Geometry có sẵn
                        available_geom_instances.add(res.instance_id)
                        
                    elif res.type_id == 0x025ED6F4: # CAS Part (quần áo, tóc)
                        # Heuristic: Quét mảng byte của CAS Part để tìm bộ TGI có TypeID = GEOM
                        data = res.get_data()
                        idx = 0
                        while True:
                            idx = data.find(GEOM_TYPE, idx)
                            if idx == -1: 
                                break
                            
                            # Đảm bảo đủ độ dài (Type: 4, Group: 4, Inst: 8) = 16 bytes
                            if idx + 16 <= len(data):
                                inst = struct.unpack_from("<Q", data, idx + 8)[0]
                                if inst != 0: # Bỏ qua null reference
                                    required.add(inst)
                            idx += 4
            except Exception as e:
                logger.debug(f"Bỏ qua file {filepath}: {e}")
                
            if required:
                required_geoms_per_file[filepath] = required
                
        # Bước 3: So khớp. Nếu một file gọi GEOM mà Instance ID không nằm trong `available_geom_instances`, 
        # và đồng thời KHÔNG nằm trong game base (rất khó biết chính xác, nhưng game base mesh 
        # thường có Group ID = 00000000. Do heuristic của ta bỏ qua Group ID, ta chỉ xét Instance).
        # Tạm thời để giảm false positive, giả sử mọi Mesh bị thiếu trên 3 LOD đều là Orphan. 
        
        orphan_files = []
        for filepath, required_insts in required_geoms_per_file.items():
            # Nếu 100% các mesh tham chiếu đều không tìm thấy trong đống mod, thì 99% thiếu mesh.
            missing_count = sum(1 for inst in required_insts if inst not in available_geom_instances)
            if missing_count > 0 and missing_count == len(required_insts):
                orphan_files.append(filepath)
                
        return orphan_files
