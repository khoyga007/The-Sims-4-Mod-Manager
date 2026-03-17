"""
Package Merger — Gộp nhiều file ``.package`` thành một file merged duy nhất.

Đọc raw resource data từ nhiều file DBPF 2.x, gộp lại và ghi ra 1 file
DBPF mới. Giữ nguyên compression gốc (không decompress/recompress).

Flow:
    1. ``scan()``    — Quét folder, trả về thống kê
    2. ``merge()``   — Gộp + backup file gốc
    3. ``unmerge()`` — Khôi phục file gốc từ backup
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import struct
import time
from core.file_utils import safe_delete
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator, Optional

logger = logging.getLogger("ModManager.PackageMerger")

# ─── DBPF Constants ───────────────────────────────────────────────────────────

_DBPF_MAGIC       = b"DBPF"
_SUPPORTED_MAJOR  = 2
_SUPPORTED_MINOR  = 1

# Header layout (96 bytes total)
_OFF_MAJOR        = 0x04
_OFF_MINOR        = 0x08
_OFF_INDEX_COUNT  = 0x24
_OFF_INDEX_SIZE   = 0x2C
_OFF_INDEX_VERSION= 0x3C
_OFF_INDEX_OFFSET = 0x40

# Index flags
_FLAG_TYPE_SHARED    = 0x01
_FLAG_GROUP_SHARED   = 0x02
_FLAG_INST_HI_SHARED = 0x04

# Merged file prefix
MERGED_PREFIX = "_MERGED_"

# Backup folder
BACKUP_DIR = "_backup"

# Folders to skip
_SKIP_FOLDERS = {"_staging", "_backup", "__pycache__"}

# Các file sẽ bị bỏ qua khi gộp
EXCLUDED_EXTENSIONS = {".ts4script", ".zip", ".rar", ".7z", ".txt", ".png", ".jpg"}


# ─── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class ResourceEntry:
    """Một resource entry đầy đủ (key + raw data)."""
    type_id:     int
    group_id:    int
    instance_id: int
    offset:      int    # Offset trong file gốc
    comp_size:   int    # Kích thước dữ liệu nén
    decompressed_size: int
    compressed_flags:  int
    source_file: str = ""
    is_compressed: bool = False
    committed: int = 0

    def get_data(self) -> bytes:
        """Đọc raw data của resource này từ file gốc."""
        if not self.source_file or not os.path.exists(self.source_file):
            return b""
        try:
            with open(self.source_file, "rb") as f:
                f.seek(self.offset)
                return f.read(self.comp_size)
        except Exception:
            return b""


@dataclass
class FolderStat:
    """Thống kê của một thư mục."""
    folder_path:  str
    folder_name:  str
    package_count: int
    total_size:    int  # bytes
    already_merged: bool = False
    can_merge: bool = False
    merged_count: int = 0


@dataclass
class MergeResult:
    """Kết quả gộp một thư mục."""
    folder_name:   str
    input_files:   int
    output_files:  list[str] # Thay đổi từ output_file -> list
    resources:     int
    duplicates:    int
    original_size: int
    merged_size:   int


# ─── DBPF Reader (full — đọc cả data) ────────────────────────────────────────

class _DBPFFullReader:
    """Đọc toàn bộ resource entries (key + data) từ file DBPF 2.x."""

    def read(self, filepath: str) -> list[ResourceEntry]:
        """Đọc file DBPF, trả về danh sách resource entries."""
        try:
            with open(filepath, "rb") as f:
                return self._parse(f, filepath) or []
        except Exception as exc:
            logger.debug(f"Lỗi đọc DBPF {os.path.basename(filepath)}: {exc}")
            return []

    def _parse(self, f, filepath: str) -> Optional[list[ResourceEntry]]:
        header = f.read(96)
        if len(header) < 96:
            return None
        if header[:4] != _DBPF_MAGIC:
            return None

        major = struct.unpack_from("<I", header, _OFF_MAJOR)[0]
        if major != _SUPPORTED_MAJOR:
            return None

        index_count  = struct.unpack_from("<I", header, _OFF_INDEX_COUNT)[0]
        index_offset = struct.unpack_from("<I", header, _OFF_INDEX_OFFSET)[0]

        if index_count == 0 or index_offset == 0:
            return []

        # Đọc index
        f.seek(index_offset)
        index_entries = list(self._read_index(f, index_count))

        # Không đọc data ngay, chỉ lưu thông tin
        entries: list[ResourceEntry] = []
        for type_id, group_id, inst_hi, inst_lo, offset, comp_size, decomp_size, flags, is_comp, comm in index_entries:
            instance_id = (inst_hi << 32) | inst_lo
            entries.append(ResourceEntry(
                type_id=type_id,
                group_id=group_id,
                instance_id=instance_id,
                offset=offset,
                comp_size=comp_size,
                decompressed_size=decomp_size,
                compressed_flags=flags,
                source_file=filepath,
                is_compressed=is_comp,
                committed=comm,
            ))

        return entries

    @staticmethod
    def _read_index(f, count: int) -> Iterator[tuple]:
        """Parse index, yield (type, group, inst_hi, inst_lo, offset, comp_size, decomp_size, flags)."""
        flags_data = f.read(4)
        if len(flags_data) < 4:
            return
        index_flags = struct.unpack("<I", flags_data)[0]

        shared_type:    Optional[int] = None
        shared_group:   Optional[int] = None
        shared_inst_hi: Optional[int] = None

        if index_flags & _FLAG_TYPE_SHARED:
            shared_type = struct.unpack("<I", f.read(4))[0]
        if index_flags & _FLAG_GROUP_SHARED:
            shared_group = struct.unpack("<I", f.read(4))[0]
        if index_flags & _FLAG_INST_HI_SHARED:
            shared_inst_hi = struct.unpack("<I", f.read(4))[0]

        # Tính kích thước mỗi entry
        entry_size = 0
        entry_size += 0 if shared_type is not None else 4
        entry_size += 0 if shared_group is not None else 4
        entry_size += 0 if shared_inst_hi is not None else 4
        entry_size += 20 # inst_lo(4) + offset(4) + comp_size(4) + decomp_size(4) + flags(2) + comm(2) = 20

        raw_data = f.read(entry_size * count)
        offset_ptr = 0

        for _ in range(count):
            try:
                if shared_type is not None:
                    type_id = shared_type
                else:
                    type_id = struct.unpack_from("<I", raw_data, offset_ptr)[0]
                    offset_ptr += 4
                    
                if shared_group is not None:
                    group_id = shared_group
                else:
                    group_id = struct.unpack_from("<I", raw_data, offset_ptr)[0]
                    offset_ptr += 4
                    
                if shared_inst_hi is not None:
                    inst_hi = shared_inst_hi
                else:
                    inst_hi = struct.unpack_from("<I", raw_data, offset_ptr)[0]
                    offset_ptr += 4

                inst_lo, offset, raw_32, decomp_size = struct.unpack_from("<IIII", raw_data, offset_ptr)
                offset_ptr += 16
                
                entry_flags, comm = struct.unpack_from("<HH", raw_data, offset_ptr)
                offset_ptr += 4

                comp_size = raw_32 & 0x7FFFFFFF  # bit 31 = compressed flag
                is_comp = bool(raw_32 & 0x80000000)

                yield (type_id, group_id, inst_hi, inst_lo, offset, comp_size, decomp_size, entry_flags, is_comp, comm)
            except struct.error:
                break



# ─── DBPF Writer ──────────────────────────────────────────────────────────────

class _DBPFWriter:
    """Ghi file DBPF 2.1 từ danh sách ResourceEntry (Lazy copy)."""

    def write(self, filepath: str, entries: list[ResourceEntry]) -> None:
        """Ghi file DBPF bằng cách đọc trực tiếp từ file gốc sang file mới."""
        # Gom nhóm entries theo source file để mở file hiệu quả
        files_to_entries: dict[str, list[ResourceEntry]] = {}
        for entry in entries:
            files_to_entries.setdefault(entry.source_file, []).append(entry)

        with open(filepath, "wb") as f_out:
            # Placeholder header
            header = bytearray(96)
            f_out.write(header)

            new_offsets: list[int] = []

            
            # Mở sẵn cache các file pointer để khỏi open/close liên tục
            # Giới hạn số file mở cùng lúc nếu cần, nhưng thường < 1000 open file handles là an toàn
            # Để an toàn nhất: mở từng file tại thời điểm cần
            
            last_opened_path = ""
            f_in = None
            
            for entry in entries:
                if entry.source_file != last_opened_path:
                    if f_in: f_in.close()
                    try:
                        f_in = open(entry.source_file, "rb")
                        last_opened_path = entry.source_file
                    except Exception as e:
                        logger.error(f"Lỗi mở {entry.source_file}: {e}")
                        new_offsets.append(f_out.tell())
                        continue

                new_offsets.append(f_out.tell())
                if f_in:
                    f_in.seek(entry.offset)
                    # Optimize: Read in chunks of 1MB to avoid memory limits and OS stalling
                    remaining = entry.comp_size
                    chunk_size = 1024 * 1024  # 1MB
                    while remaining > 0:
                        size_to_read = min(remaining, chunk_size)
                        chunk = f_in.read(size_to_read)
                        if not chunk:
                            break
                        f_out.write(chunk)
                        remaining -= len(chunk)

            if f_in: f_in.close()

            # Ghi index
            index_offset = f_out.tell()
            self._write_index(f_out, entries, new_offsets)
            index_end = f_out.tell()
            index_size = index_end - index_offset

            # Cập nhật header
            f_out.seek(0)
            f_out.write(self._make_header(
                index_count=len(entries),
                index_offset=index_offset,
                index_size=index_size,
            ))

    def _make_header(self, index_count: int, index_offset: int, index_size: int) -> bytes:
        """Tạo DBPF 2.1 header (96 bytes)."""
        h = bytearray(96)

        # Magic
        h[0:4] = _DBPF_MAGIC

        # Version
        struct.pack_into("<I", h, _OFF_MAJOR, _SUPPORTED_MAJOR)
        struct.pack_into("<I", h, _OFF_MINOR, _SUPPORTED_MINOR)

        # Index count
        struct.pack_into("<I", h, _OFF_INDEX_COUNT, index_count)

        # Index size
        struct.pack_into("<I", h, _OFF_INDEX_SIZE, index_size)

        # Index version
        struct.pack_into("<I", h, _OFF_INDEX_VERSION, 3)

        # Index offset (Sims 4 uses 0x40)
        struct.pack_into("<I", h, _OFF_INDEX_OFFSET, index_offset)

        return bytes(h)

    @staticmethod
    def _write_index(f, entries: list[ResourceEntry], offsets: list[int]) -> None:
        """Ghi index tối ưu dùng shared flags (giống S4S)."""
        if not entries:
            f.write(struct.pack("<I", 0))
            return

        # Kiểm tra tính đồng nhất để dùng Shared Flags (Tiết kiệm ~12 byte/resource)
        first = entries[0]
        all_same_type = all(e.type_id == first.type_id for e in entries)
        all_same_group = all(e.group_id == first.group_id for e in entries)
        
        first_inst_hi = (first.instance_id >> 32) & 0xFFFFFFFF
        all_same_inst_hi = all(((e.instance_id >> 32) & 0xFFFFFFFF) == first_inst_hi for e in entries)

        flags = 0
        if all_same_type:    flags |= _FLAG_TYPE_SHARED
        if all_same_group:   flags |= _FLAG_GROUP_SHARED
        if all_same_inst_hi: flags |= _FLAG_INST_HI_SHARED

        # 1. Ghi flags
        f.write(struct.pack("<I", flags))

        # 2. Ghi các giá trị shared (nếu có)
        if all_same_type:    f.write(struct.pack("<I", first.type_id))
        if all_same_group:   f.write(struct.pack("<I", first.group_id))
        if all_same_inst_hi: f.write(struct.pack("<I", first_inst_hi))

        # 3. Ghi từng entry (bỏ qua các cột đã shared)
        for entry, offset in zip(entries, offsets):
            inst_lo = entry.instance_id & 0xFFFFFFFF
            size_field = entry.comp_size
            if entry.is_compressed:
                size_field |= 0x80000000

            if not all_same_type:    f.write(struct.pack("<I", entry.type_id))
            if not all_same_group:   f.write(struct.pack("<I", entry.group_id))
            if not all_same_inst_hi: f.write(struct.pack("<I", (entry.instance_id >> 32) & 0xFFFFFFFF))
            
            f.write(struct.pack("<I", inst_lo))
            f.write(struct.pack("<I", offset))
            f.write(struct.pack("<I", size_field))
            f.write(struct.pack("<I", entry.decompressed_size))
            f.write(struct.pack("<H", entry.compressed_flags))
            f.write(struct.pack("<H", entry.committed))


# ─── Package Merger ──────────────────────────────────────────────────────────

class PackageMerger:
    """Gộp file .package trong thư mục Mods.

    Parameters
    ----------
    mod_directory:
        Đường dẫn gốc thư mục Mods.
    progress_callback:
        ``(current, total, message) -> None``
    """

    def __init__(
        self,
        mod_directory: str,
        backup_directory: Optional[str] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> None:
        self._mod_dir = mod_directory
        self._backup_dir = backup_directory or os.path.join(mod_directory, BACKUP_DIR)
        self._progress = progress_callback
        self._reader = _DBPFFullReader()
        self._writer = _DBPFWriter()

    # ─────────────────────────────────────────────────────────────────────────
    # Scan
    # ─────────────────────────────────────────────────────────────────────────

    def scan(self) -> list[FolderStat]:
        """Quét tất cả folder và subfolder, trả về thống kê.

        Returns
        -------
        list[FolderStat]
            Danh sách folder có file .package, sắp theo số file giảm dần.
        """
        stats: list[FolderStat] = []

        for root, dirs, files in os.walk(self._mod_dir):
            # Bỏ qua các thư mục hệ thống
            dirs[:] = [d for d in dirs if d.lower() not in _SKIP_FOLDERS]

            packages = [f for f in files if f.lower().endswith(".package")]
            if not packages:
                continue

            rel_path = os.path.relpath(root, self._mod_dir)
            if rel_path == ".":
                # File .package ở gốc — bỏ qua (thường là script mod)
                continue

            total_size = sum(
                os.path.getsize(os.path.join(root, f)) for f in packages
            )
            has_merged = any(f.startswith(MERGED_PREFIX) for f in packages)

            # Đếm chỉ file chưa merged
            unmerged = [f for f in packages if not f.startswith(MERGED_PREFIX)]
            
            # Cho phép gộp nếu:
            # 1. Có >= 2 file chưa gộp
            # 2. Hoặc có >= 1 file chưa gộp VÀ đã có file gộp rồi (để gộp thêm)
            can_merge = len(unmerged) >= 2 or (len(unmerged) >= 1 and has_merged)

            stats.append(FolderStat(
                folder_path=root,
                folder_name=rel_path,
                package_count=len(unmerged),
                total_size=total_size,
                already_merged=has_merged,
                can_merge=can_merge,
                # Thống kê thêm cả file đã gộp
                merged_count=len([f for f in packages if f.startswith(MERGED_PREFIX)])
            ))

        stats.sort(key=lambda s: s.package_count, reverse=True)
        return stats

    # ─────────────────────────────────────────────────────────────────────────
    # Merge
    # ─────────────────────────────────────────────────────────────────────────

    def merge_folder(self, folder_path: str, consolidate: bool = False) -> Optional[MergeResult]:
        """Gộp tất cả .package trong một folder.

        Parameters
        ----------
        folder_path:
            Đường dẫn đến folder cần gộp.

        Returns
        -------
        MergeResult | None
            Kết quả gộp, hoặc None nếu lỗi.
        """
        folder_name = os.path.basename(folder_path)
        # Kiểm tra xem có file đã gộp sẵn chưa
        all_packages = self._find_packages_in_folder(folder_path)
        
        if consolidate:
            # Gộp tất cả: file lẻ + file đã gộp cũ
            packages = all_packages
        else:
            # Chỉ gộp các file lẻ (không bắt đầu bằng _MERGED_)
            packages = [p for p in all_packages if not os.path.basename(p).startswith(MERGED_PREFIX)]

        if not packages:
            logger.info(f"Bỏ qua {folder_name}: không có file lẻ nào để gộp (có thể đã gộp hết rồi)")
            return None

        logger.info(f"Gộp {len(packages)} file trong {folder_name}...")

        # 1. Đọc tất cả resource
        all_entries: list[ResourceEntry] = []
        duplicates = 0
        seen_keys: dict[tuple, ResourceEntry] = {}
        original_size = 0

        for i, pkg_path in enumerate(packages):
            if self._progress:
                self._progress(
                    i + 1, len(packages),
                    f"Đọc {os.path.basename(pkg_path)}..."
                )

            original_size += os.path.getsize(pkg_path)
            entries = self._reader.read(pkg_path)
            if entries is None:
                logger.warning(f"Bỏ qua file không đọc được: {os.path.basename(pkg_path)}")
                continue

            for entry in entries:
                key = (entry.type_id, entry.group_id, entry.instance_id)
                if key in seen_keys:
                    duplicates += 1
                    # Giữ entry từ file mới hơn
                    old_mtime = os.path.getmtime(seen_keys[key].source_file)
                    new_mtime = os.path.getmtime(entry.source_file)
                    if new_mtime > old_mtime:
                        seen_keys[key] = entry
                else:
                    seen_keys[key] = entry

        all_entries = list(seen_keys.values())

        if not all_entries:
            logger.warning(f"Không có resource nào trong {folder_name}")
            return None

        # 2. Backup file gốc (di chuyển cực nhanh)
        if self._progress:
            self._progress(0, 1, f"Backup {folder_name}...")
        backup_map = self._backup_folder(folder_path, packages, folder_name)

        # Cập nhật source_file mới cho các entries sau khi file đã bị move
        for entry in all_entries:
            if entry.source_file in backup_map:
                entry.source_file = backup_map[entry.source_file]

        # 3. Phân đoạn và Ghi merged file (giới hạn 3.7GB để tránh lỗi 32-bit offset)
        MAX_PART_SIZE = 3700 * 1024 * 1024 # 3.7 GB
        
        chunks: list[list[ResourceEntry]] = []
        current_chunk: list[ResourceEntry] = []
        current_size = 0
        
        for entry in all_entries:
            entry_est = entry.comp_size + 32
            if current_size + entry_est > MAX_PART_SIZE and current_chunk:
                chunks.append(current_chunk)
                current_chunk = []
                current_size = 0
            current_chunk.append(entry)
            current_size += entry_est
        if current_chunk:
            chunks.append(current_chunk)

        # TÌM TÊN FILE CHƯA TỒN TẠI (ĐỂ MERGE THÊM)
        def find_next_version(base_name: str) -> str:
            # Nếu đã có _MERGED_Name.package, tìm _MERGED_Name_v2.package...
            idx = 1
            while True:
                suffix = "" if idx == 1 else f"_v{idx}"
                test_name = f"{MERGED_PREFIX}{base_name}{suffix}.package"
                # Kiểm tra xem có bất kỳ part nào của version này tồn tại không
                if not any(f.startswith(f"{MERGED_PREFIX}{base_name}{suffix}") for f in os.listdir(folder_path)):
                    return f"{MERGED_PREFIX}{base_name}{suffix}"
                idx += 1

        ver_prefix = find_next_version(folder_name)
        output_paths = []
        merged_size_total = 0

        try:
            for i, chunk in enumerate(chunks):
                if len(chunks) > 1:
                    merged_filename = f"{ver_prefix}_Part{i+1}.package"
                else:
                    merged_filename = f"{ver_prefix}.package"
                
                merged_path = os.path.join(folder_path, merged_filename)
                
                if self._progress:
                    msg = f"Ghi {merged_filename}"
                    if len(chunks) > 1:
                        msg += f" (Phần {i+1}/{len(chunks)})"
                    self._progress(i, len(chunks), msg)

                self._writer.write(merged_path, chunk)
                merged_size_total += os.path.getsize(merged_path)
                output_paths.append(merged_path)

            # 4. Cập nhật manifest với danh sách file kết quả
            self._update_manifest_with_outputs(folder_path, output_paths)

        except Exception as e:
            logger.error(f"Lỗi khi ghi file gộp {folder_name}: {e}")
            # Tự động khôi phục nếu ghi bị lỗi
            self.unmerge_folder(folder_path)
            return None

        return MergeResult(
            folder_name=folder_name,
            input_files=len(packages),
            output_files=output_paths,
            resources=len(all_entries),
            duplicates=duplicates,
            original_size=original_size,
            merged_size=merged_size_total,
        )

    def merge_folders(self, folder_paths: list[str]) -> list[MergeResult]:
        """Gộp nhiều folder.

        Parameters
        ----------
        folder_paths:
            Danh sách đường dẫn folder cần gộp.
        """
        results: list[MergeResult] = []
        for i, fp in enumerate(folder_paths):
            if self._progress:
                fname = os.path.basename(fp)
                self._progress(i + 1, len(folder_paths), f"Gộp folder {fname}...")
            result = self.merge_folder(fp)
            if result:
                results.append(result)
        return results

    # ─────────────────────────────────────────────────────────────────────────
    # Unmerge (khôi phục)
    # ─────────────────────────────────────────────────────────────────────────

    def unmerge_folder(self, folder_path: str) -> bool:
        """Khôi phục file gốc từ backup.

        Parameters
        ----------
        folder_path:
            Đường dẫn folder cần khôi phục.

        Returns
        -------
        bool
            True nếu khôi phục thành công.
        """
        folder_name = os.path.basename(folder_path)
        # Hỗ trợ folder_name dạng relative path (ví dụ: 10_Clothing\HQ)
        rel_name = os.path.relpath(folder_path, self._mod_dir)
        safe_name = rel_name.replace(os.sep, "__").replace("/", "__")
        backup_dir = os.path.join(self._backup_dir, safe_name)

        if not os.path.exists(backup_dir):
            # Fallback: Kiểm tra vị trí cũ bên trong thư mục Mods
            old_backup_dir = os.path.join(self._mod_dir, "_backup", safe_name)
            if os.path.exists(old_backup_dir):
                backup_dir = old_backup_dir
            else:
                logger.error(f"Không tìm thấy backup cho {folder_name} ở cả {backup_dir} và {old_backup_dir}")
                return False

        manifest_path = os.path.join(backup_dir, "_manifest.json")
        if not os.path.exists(manifest_path):
            logger.error(f"Không tìm thấy manifest cho {folder_name}")
            return False

        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except Exception as exc:
            logger.error(f"Lỗi đọc manifest: {exc}")
            return False

        # 1. Theo yêu cầu người dùng: KHÔNG xóa file merged khi khôi phục.
        # Lưu ý: Việc này có thể dẫn đến trùng lặp mod trong game (vừa có file gốc vừa có file gộp).
        merged_to_delete = manifest.get("merged_outputs", [])
        if merged_to_delete:
            logger.info(f"Giữ lại các file gộp theo yêu cầu: {merged_to_delete}")

        # 2. Khôi phục file gốc bằng cách move siêu tốc
        restored = 0
        for file_info in manifest.get("files", []):
            backup_file = os.path.join(backup_dir, file_info["name"])
            target_file = os.path.join(folder_path, file_info["name"])

            if os.path.exists(backup_file):
                shutil.move(backup_file, target_file)
                restored += 1

        # 3. Đưa backup folder vào Thùng rác
        safe_delete(backup_dir)

        logger.info(f"Đã khôi phục {restored} file cho {folder_name}")
        return True

    def delete_backup(self, folder_path: str) -> bool:
        """Xóa vĩnh viễn backup để giải phóng dung lượng. (Commit)"""
        rel_name = os.path.relpath(folder_path, self._mod_dir)
        safe_name = rel_name.replace(os.sep, "__").replace("/", "__")
        backup_dir = os.path.join(self._backup_dir, safe_name)

        if not os.path.exists(backup_dir):
            # Fallback
            old_dir = os.path.join(self._mod_dir, "_backup", safe_name)
            if os.path.exists(old_dir):
                backup_dir = old_dir

        if os.path.exists(backup_dir):
            if safe_delete(backup_dir):
                logger.info(f"Đã đưa backup của {os.path.basename(folder_path)} vào Thùng rác.")
                return True
            return False
        return False

    def has_backup(self, folder_path: str) -> bool:
        """Kiểm tra folder có backup không."""
        rel_name = os.path.relpath(folder_path, self._mod_dir)
        safe_name = rel_name.replace(os.sep, "__").replace("/", "__")
        backup_dir = os.path.join(self._backup_dir, safe_name)
        if os.path.exists(os.path.join(backup_dir, "_manifest.json")):
            return True
            
        # Fallback
        old_dir = os.path.join(self._mod_dir, "_backup", safe_name)
        return os.path.exists(os.path.join(old_dir, "_manifest.json"))

    # ─────────────────────────────────────────────────────────────────────────
    # Internals
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _find_packages_in_folder(folder_path: str) -> list[str]:
        """Tìm file .package trong folder (không đệ quy vào subfolder)."""
        result: list[str] = []
        try:
            for name in os.listdir(folder_path):
                ext = os.path.splitext(name)[1].lower()
                if ext == ".package":
                    full = os.path.join(folder_path, name)
                    if os.path.isfile(full):
                        result.append(full)
                elif ext == ".ts4script":
                    logger.warning(f"⚠️ Phát hiện file Script trong thư mục gộp: {name}. Script KHÔNG được gộp, game sẽ bị lag/lỗi!")
                elif ext in EXCLUDED_EXTENSIONS:
                    logger.debug(f"Bỏ qua file không gộp: {name}")
        except OSError:
            pass
        return sorted(result)

    def _backup_folder(self, folder_path: str, packages: list[str], folder_name: str) -> dict[str, str]:
        """Backup các file gốc bằng cách move vào _backup/ siêu tốc. Trả về mapping path cũ -> mới."""
        rel_name = os.path.relpath(folder_path, self._mod_dir)
        safe_name = rel_name.replace(os.sep, "__").replace("/", "__")
        backup_dir = os.path.join(self._backup_dir, safe_name)
        os.makedirs(backup_dir, exist_ok=True)

        manifest_path = os.path.join(backup_dir, "_manifest.json")
        if os.path.exists(manifest_path):
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
            except Exception:
                manifest = {"folder": folder_name, "files": [], "merged_outputs": []}
        else:
            manifest = {
                "folder": folder_name,
                "files": [],
                "merged_outputs": []
            }

        manifest["timestamp"] = time.time()

        backup_map = {}

        for pkg_path in packages:
            name = os.path.basename(pkg_path)
            dest = os.path.join(backup_dir, name)
            # Move thay vì copy -> tốc độ tức thời O(1) nếu cùng ổ đĩa
            shutil.move(pkg_path, dest)
            backup_map[pkg_path] = dest
            # Kiểm tra xem file đã có trong manifest chưa (tránh trùng lặp nếu gộp lại)
            if not any(f["name"] == name for f in manifest["files"]):
                manifest["files"].append({
                    "name": name,
                    "size": os.path.getsize(dest),
                })

        manifest_path = os.path.join(backup_dir, "_manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

        logger.info(f"Đã backup (move) {len(packages)} file vào {backup_dir}")
        return backup_map

    def _update_manifest_with_outputs(self, folder_path: str, output_paths: list[str]) -> None:
        """Cập nhật manifest để ghi lại các file gộp đã được tạo ra."""
        rel_name = os.path.relpath(folder_path, self._mod_dir)
        safe_name = rel_name.replace(os.sep, "__").replace("/", "__")
        manifest_path = os.path.join(self._backup_dir, safe_name, "_manifest.json")
        
        if os.path.exists(manifest_path):
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                if "merged_outputs" not in data:
                    data["merged_outputs"] = []
                
                for p in output_paths:
                    name = os.path.basename(p)
                    if name not in data["merged_outputs"]:
                        data["merged_outputs"].append(name)
                
                with open(manifest_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.error(f"Lỗi cập nhật manifest: {e}")


def format_size(size_bytes: int) -> str:
    """Format bytes thành chuỗi đọc được (KB/MB/GB)."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024*1024):.1f} MB"
    else:
        return f"{size_bytes / (1024*1024*1024):.2f} GB"
