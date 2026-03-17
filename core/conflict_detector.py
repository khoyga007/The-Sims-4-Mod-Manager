"""
Conflict Detector — Quét file ``.package`` để tìm xung đột Resource ID.

Phân tích định dạng nhị phân DBPF 2.x, trích xuất index các resource,
sau đó tìm các resource key (type/group/instance) xuất hiện trong nhiều
file khác nhau — đây là dấu hiệu chắc chắn của xung đột.

Các loại xung đột:
- **CRITICAL**: cùng Tuning ID → mod ghi đè lẫn nhau, hành vi không đoán được
- **WARNING**: cùng CAS Part → game chọn 1 bản, bản kia bị bỏ qua
- **INFO**: cùng String Table → bản dịch bị đè
"""
from __future__ import annotations

import logging
import os
import struct
from dataclasses import dataclass, field
from typing import Iterator, Optional

logger = logging.getLogger("ModManager.ConflictDetector")

# ─── DBPF Constants ───────────────────────────────────────────────────────────

_DBPF_MAGIC       = b"DBPF"
_SUPPORTED_MAJOR  = 2

# Header offsets
_OFF_MAJOR        = 0x04
_OFF_MINOR        = 0x08
_OFF_INDEX_COUNT  = 0x24
_OFF_INDEX_OFFSET = 0x40   # DBPF 2.1

# Index flags
_FLAG_TYPE_SHARED      = 0x01
_FLAG_GROUP_SHARED     = 0x02
_FLAG_INST_HI_SHARED   = 0x04

# Resource type IDs (Sims 4)
_RESOURCE_TYPES: dict[int, tuple[str, str]] = {
    0x025ED6F4: ("CAS Part",       "WARNING"),
    0x03B33DDF: ("CAS Mesh",       "WARNING"),
    0x034AEECB: ("Tuning",         "CRITICAL"),
    0x62ECC59A: ("String Table",   "INFO"),
    0x220557DA: ("Sim Data",       "WARNING"),
    0x545AC67A: ("STBL",           "INFO"),
    0x00B2D882: ("Object Catalog", "WARNING"),
    0x319E4F1D: ("Object Def",     "WARNING"),
    0x02D5DF13: ("Slot",           "INFO"),
    0xEC3712BE: ("Bone",           "INFO"),
    0x736884F1: ("Interaction",    "CRITICAL"),
    0x8B18FF6E: ("Lot Def",        "WARNING"),
}

_DEFAULT_SEVERITY = "INFO"


# ─── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class ResourceKey:
    """Khóa định danh duy nhất của một resource trong DBPF."""
    type_id:     int
    group_id:    int
    instance_id: int

    def __hash__(self) -> int:
        return hash((self.type_id, self.group_id, self.instance_id))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ResourceKey):
            return NotImplemented
        return (
            self.instance_id == other.instance_id and
            self.type_id     == other.type_id and
            self.group_id    == other.group_id
        )

    @property
    def type_name(self) -> str:
        info = _RESOURCE_TYPES.get(self.type_id)
        return info[0] if info else f"0x{self.type_id:08X}"

    @property
    def severity(self) -> str:
        info = _RESOURCE_TYPES.get(self.type_id)
        return info[1] if info else _DEFAULT_SEVERITY

    def __str__(self) -> str:
        return (
            f"{self.type_name} "
            f"[G:{self.group_id:08X} I:{self.instance_id:016X}]"
        )


@dataclass
class Conflict:
    """Một xung đột resource giữa nhiều file.

    Attributes
    ----------
    key:
        Resource key bị trùng.
    packages:
        Danh sách file ``.package`` cùng chứa resource này.
    severity:
        ``"CRITICAL"`` / ``"WARNING"`` / ``"INFO"``
    """
    key:      ResourceKey
    packages: list[str]
    severity: str

    @property
    def count(self) -> int:
        return len(self.packages)

    @property
    def type_name(self) -> str:
        return self.key.type_name

    @property
    def description(self) -> str:
        names = [os.path.basename(p) for p in self.packages]
        return f"{self.type_name}: {' ↔ '.join(names)}"


@dataclass
class ScanResult:
    """Kết quả quét xung đột.

    Attributes
    ----------
    scanned:
        Số file ``.package`` đã đọc thành công.
    skipped:
        Số file bỏ qua (không phải DBPF hoặc lỗi đọc).
    conflicts:
        Danh sách xung đột tìm được.
    redundancies:
        Danh sách file dư thừa (bị chứa trọn vẹn trong file khác - thường là merged).
    """
    scanned:     int
    skipped:     int
    conflicts:    list[Conflict] = field(default_factory=list)
    redundancies: list[tuple[str, str]] = field(default_factory=list) # (redundant_path, containers_path)

    @property
    def critical_count(self) -> int:
        return sum(1 for c in self.conflicts if c.severity == "CRITICAL")

    @property
    def warning_count(self) -> int:
        return sum(1 for c in self.conflicts if c.severity == "WARNING")

    @property
    def info_count(self) -> int:
        return sum(1 for c in self.conflicts if c.severity == "INFO")

    @property
    def has_issues(self) -> bool:
        return self.critical_count > 0 or self.warning_count > 0


# ─── DBPF Reader ──────────────────────────────────────────────────────────────

class _DBPFReader:
    """Đọc index của một file DBPF 2.x."""

    def __init__(self, filepath: str) -> None:
        self._filepath = filepath

    def read_keys(self) -> Optional[list[ResourceKey]]:
        """Đọc toàn bộ resource key từ index.

        Returns
        -------
        list[ResourceKey] | None
            Danh sách key, hoặc ``None`` nếu không phải DBPF hợp lệ.
        """
        try:
            with open(self._filepath, "rb") as f:
                return self._parse(f)
        except Exception as exc:
            logger.debug(f"Lỗi đọc DBPF {os.path.basename(self._filepath)}: {exc}")
            return None

    def _parse(self, f) -> Optional[list[ResourceKey]]:
        header = f.read(96)
        if len(header) < 96:
            return None

        # Validate magic
        if header[:4] != _DBPF_MAGIC:
            return None

        major = struct.unpack_from("<I", header, _OFF_MAJOR)[0]
        if major != _SUPPORTED_MAJOR:
            return None

        index_count  = struct.unpack_from("<I", header, _OFF_INDEX_COUNT)[0]
        index_offset = struct.unpack_from("<I", header, _OFF_INDEX_OFFSET)[0]

        if index_count == 0 or index_offset == 0:
            return []

        f.seek(index_offset)
        return list(self._read_index(f, index_count))

    @staticmethod
    def _read_index(f, count: int) -> Iterator[ResourceKey]:
        """Parse index entries theo format DBPF 2.1 với tốc độ cao."""
        header_data = f.read(4)
        if len(header_data) < 4: return
        flags = struct.unpack("<I", header_data)[0]

        # Đọc shared values
        shared_type = struct.unpack("<I", f.read(4))[0] if flags & _FLAG_TYPE_SHARED else None
        shared_group = struct.unpack("<I", f.read(4))[0] if flags & _FLAG_GROUP_SHARED else None
        shared_inst_hi = struct.unpack("<I", f.read(4))[0] if flags & _FLAG_INST_HI_SHARED else None

        # Tính kích thước mỗi entry
        entry_size = 20 # inst_lo (4) + offset (4) + size (4) + decomp (4) + flags (2) + unk (2)
        entry_size += 0 if shared_type is not None else 4
        entry_size += 0 if shared_group is not None else 4
        entry_size += 0 if shared_inst_hi is not None else 4

        raw_data = f.read(entry_size * count)
        if len(raw_data) < entry_size * count: return
        
        offset = 0
        shared_inst_hi_shifted = (shared_inst_hi << 32) if shared_inst_hi is not None else 0

        # Vòng lặp tối ưu hóa tốc độ
        for _ in range(count):
            if shared_type is not None:
                tid = shared_type
            else:
                tid = struct.unpack_from("<I", raw_data, offset)[0]
                offset += 4
                
            if shared_group is not None:
                gid = shared_group
            else:
                gid = struct.unpack_from("<I", raw_data, offset)[0]
                offset += 4
                
            if shared_inst_hi is not None:
                iid_hi = shared_inst_hi_shifted
            else:
                iid_hi = struct.unpack_from("<I", raw_data, offset)[0] << 32
                offset += 4

            iid_lo = struct.unpack_from("<I", raw_data, offset)[0]
            instance_id = iid_hi | iid_lo
            
            yield ResourceKey(tid, gid, instance_id)
            offset += 20 # Skip metadata (16) + inst_lo (4 đã đọc)



# ─── Conflict Detector ────────────────────────────────────────────────────────

class ConflictDetector:
    """Quét nhiều file ``.package`` và tìm xung đột resource key.

    Parameters
    ----------
    progress_callback:
        ``Callable[[int, int, str], None]`` nhận (current, total, filename).
        Gọi từ worker thread.
    """

    def __init__(self, progress_callback=None) -> None:
        self._progress = progress_callback

    def scan(
        self,
        package_files: list[str],
        severity_filter: Optional[set[str]] = None,
    ) -> ScanResult:
        """Quét danh sách file ``.package`` tìm xung đột.

        Parameters
        ----------
        package_files:
            Danh sách đường dẫn tuyệt đối đến file ``.package``.
        severity_filter:
            Chỉ trả về xung đột với severity trong tập này.
            ``None`` = trả về tất cả.

        Returns
        -------
        ScanResult
        """
        total    = len(package_files)
        scanned  = 0
        skipped  = 0

        # key → [filepath, ...]
        key_index: dict[ResourceKey, list[str]] = {}

        for i, filepath in enumerate(package_files):
            filename = os.path.basename(filepath)
            if self._progress:
                self._progress(i + 1, total, filename)

            reader = _DBPFReader(filepath)
            keys   = reader.read_keys()

            if keys is None:
                skipped += 1
                continue

            scanned += 1
            for key in keys:
                if key not in key_index:
                    key_index[key] = []
                key_index[key].append(filepath)

        # Tìm xung đột (key có trong > 1 file)
        conflicts: list[Conflict] = []
        for key, files in key_index.items():
            if len(files) < 2:
                continue
            c = Conflict(key=key, packages=files, severity=key.severity)
            if severity_filter is None or c.severity in severity_filter:
                conflicts.append(c)

        # Tìm các file dư thừa (Toàn bộ resource của file A đều nằm trong file B - Merged)
        redundancies = self._find_redundancies(package_files, key_index)

        # Sắp xếp: CRITICAL trước, sau đó theo số lượng file bị ảnh hưởng
        _order = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}
        conflicts.sort(key=lambda c: (_order.get(c.severity, 3), -c.count))

        logger.info(
            f"Quét xong {scanned} file, bỏ qua {skipped}. "
            f"Xung đột: {len(conflicts)}, Dư thừa: {len(redundancies)}"
        )
        return ScanResult(
            scanned=scanned, skipped=skipped, 
            conflicts=conflicts, redundancies=redundancies
        )

    def _find_redundancies(self, package_files: list[str], key_index: dict) -> list[tuple[str, str]]:
        """Xác định các file mà 100% tài nguyên đã có trong một file _MERGED_ khác."""
        redundancies = []
        
        # Chỉ xét các file lẻ (không phải _MERGED_) để xem nó có bị dư thừa không
        normal_files = [f for f in package_files if not os.path.basename(f).startswith("_MERGED_")]
        merged_files = [f for f in package_files if os.path.basename(f).startswith("_MERGED_")]
        
        if not merged_files:
            return []

        # merged_file -> set of resource keys
        merged_content = {}
        for m_path in merged_files:
            reader = _DBPFReader(m_path)
            keys = reader.read_keys()
            if keys:
                merged_content[m_path] = set(keys)

        for f_path in normal_files:
            reader = _DBPFReader(f_path)
            f_keys = reader.read_keys()
            if not f_keys: continue
            
            f_set = set(f_keys)
            total_r = len(f_set)
            if total_r == 0: continue

            for m_path, m_set in merged_content.items():
                # Nếu > 90% resource trùng khớp thì coi như là bản cài lại (Dư thừa)
                matches = len(f_set.intersection(m_set))
                pct = matches / total_r
                if pct >= 0.9:
                    redundancies.append((f_path, m_path))
                    break
        
        return redundancies

    @staticmethod
    def find_packages(mod_directory: str) -> list[str]:
        """Tìm tất cả file ``.package`` trong thư mục Mods.

        Parameters
        ----------
        mod_directory:
            Đường dẫn thư mục Mods.
        """
        result: list[str] = []
        for root, dirs, files in os.walk(mod_directory):
            # Skip _backup and __ folders
            if "_backup" in root or "__" in root:
                continue
            for name in files:
                if name.lower().endswith(".package"):
                    result.append(os.path.join(root, name))
        return result

