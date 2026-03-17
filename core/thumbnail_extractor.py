import os
import struct
import zlib
import io
import logging
from PIL import Image

logger = logging.getLogger("ModManager.ThumbnailExtractor")

# Magic
_DBPF_MAGIC = b"DBPF"
_OFF_INDEX_COUNT = 0x24
_OFF_INDEX_OFFSET = 0x40

_FLAG_TYPE_SHARED = 0x01
_FLAG_GROUP_SHARED = 0x02
_FLAG_INST_HI_SHARED = 0x04

# Known Image Types
TYPE_THUM = 0x3C1AF1F2
TYPE_DST_IMAGE = 0x00B2D882  # Object catalog thumb
TYPE_PNG = 0x2D5DF13   # Sometimes PNG

class ThumbnailExtractor:
    @staticmethod
    def extract_thumbnail(filepath: str) -> Image.Image | None:
        """Đọc nhanh một file DBPF và bóc tách ảnh Thumbnail đầu tiên nằm bên trong."""
        try:
            with open(filepath, "rb") as f:
                header = f.read(96)
                if len(header) < 96 or header[:4] != _DBPF_MAGIC:
                    return None
                
                index_count: int = struct.unpack_from("<I", header, _OFF_INDEX_COUNT)[0]
                index_offset: int = struct.unpack_from("<I", header, _OFF_INDEX_OFFSET)[0]
                
                if index_count == 0 or index_offset == 0:
                    return None
                    
                f.seek(index_offset)
                
                # Setup
                flags_data = f.read(4)
                if len(flags_data) < 4: return None
                index_flags = struct.unpack("<I", flags_data)[0]

                shared_type = struct.unpack("<I", f.read(4))[0] if (index_flags & _FLAG_TYPE_SHARED) else None
                shared_group = struct.unpack("<I", f.read(4))[0] if (index_flags & _FLAG_GROUP_SHARED) else None
                shared_inst_hi = struct.unpack("<I", f.read(4))[0] if (index_flags & _FLAG_INST_HI_SHARED) else None
                
                # Tính kích thước mỗi entry
                entry_size = 0
                entry_size += 0 if shared_type is not None else 4
                entry_size += 0 if shared_group is not None else 4
                entry_size += 0 if shared_inst_hi is not None else 4
                entry_size += 20 

                raw_data = f.read(entry_size * index_count)
                offset_ptr = 0
                
                target_offset = 0
                target_comp_size = 0
                target_decomp_size = 0
                target_is_comp = False
                
                for _ in range(index_count):
                    type_id = shared_type if shared_type is not None else struct.unpack_from("<I", raw_data, offset_ptr)[0]
                    if shared_type is None: offset_ptr += 4
                    
                    group_id = shared_group if shared_group is not None else struct.unpack_from("<I", raw_data, offset_ptr)[0]
                    if shared_group is None: offset_ptr += 4
                    
                    inst_hi = shared_inst_hi if shared_inst_hi is not None else struct.unpack_from("<I", raw_data, offset_ptr)[0]
                    if shared_inst_hi is None: offset_ptr += 4
                    
                    inst_lo, offset, raw_32, decomp_size = struct.unpack_from("<IIII", raw_data, offset_ptr)
                    offset_ptr += 16
                    offset_ptr += 4 # flags & comm
                    
                    if type_id == TYPE_THUM or type_id == TYPE_DST_IMAGE or type_id == 0x03B33DDF:
                        target_offset = offset
                        target_comp_size = raw_32 & 0x7FFFFFFF
                        target_is_comp = bool(raw_32 & 0x80000000)
                        target_decomp_size = decomp_size
                        break # Found one!
                
                if target_offset == 0:
                    return None # No thumbnail found
                
                # Fetch bytes
                f.seek(target_offset)
                data = f.read(target_comp_size)
                
                if target_is_comp:
                    # DBPF uses standard zlib, or maybe 4 bytes of uncompressed size header
                    # actually TS4 compression is: 4 bytes identifier + 2 bytes zlib header
                    # Standard Sims 4 compression header: b'ZLIB' or just standard headers.
                    # We will try to decompress normally, ignoring an optional 4-byte prefix if it fails.
                    try:
                        data = zlib.decompress(data)
                    except Exception:
                        try:
                            data = zlib.decompress(data[4:])
                        except Exception as e:
                            logger.error(f"Cannot decompress thumbnail in {os.path.basename(filepath)}: {e}")
                            return None
                            
                return Image.open(io.BytesIO(data))
                
        except Exception as e:
            logger.debug(f"Thumbnail extract error for {filepath}: {e}")
            return None
