import hashlib
import os
import logging
import shutil
import time
from typing import Optional

logger = logging.getLogger("ModManager.FileUtils")

def get_file_hash(filepath: str) -> Optional[str]:
    """Tính mã băm MD5 của file."""
    try:
        hasher = hashlib.md5()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception as e:
        logger.error(f"Lỗi tính hash {filepath}: {e}")
        return None

def are_files_identical(file1: str, file2: str) -> bool:
    """Kiểm tra hai file có nội dung giống hệt nhau không."""
    try:
        if os.path.getsize(file1) != os.path.getsize(file2):
            return False
        
        h1 = get_file_hash(file1)
        h2 = get_file_hash(file2)
        
        return h1 is not None and h2 is not None and h1 == h2
    except Exception:
        return False

def safe_move(src: str, dst: str, max_retries: int = 5, delay: float = 0.5) -> bool:
    """Di chuyển file với cơ chế thử lại (retry) để tránh WinError 32."""
    for i in range(max_retries):
        try:
            shutil.move(src, dst)
            return True
        except OSError as e:
            if i == max_retries - 1:
                logger.error(f"❌ Không thể di chuyển file sau {max_retries} lần thử: {src} -> {e}")
                return False
            time.sleep(delay * (i + 1)) # Exponential backoff nhẹ
    return False

def safe_remove(path: str, max_retries: int = 3, delay: float = 0.3) -> bool:
    """Xóa file hoặc thư mục với cơ chế thử lại."""
    for i in range(max_retries):
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
            return True
        except OSError:
            if i == max_retries - 1: return False
            time.sleep(delay)
    return False

def move_with_duplicate_check(src: str, dst_dir: str, filename: Optional[str] = None) -> str:
    """
    Di chuyển file với kiểm tra trùng lặp nội dung.
    Nếu trùng nội dung -> xóa src, trả về path file đã có.
    Nếu trùng tên nhưng khác nội dung -> thêm hậu tố số.
    """
    if filename is None:
        filename = os.path.basename(src)
        
    dest_path = os.path.join(dst_dir, filename)
    
    # 1. Kiểm tra trùng nội dung tại đích chính
    if os.path.exists(dest_path):
        if are_files_identical(src, dest_path):
            logger.info(f"✨ Trùng nội dung: {filename}. Đã xóa bản sao.")
            safe_remove(src)
            return dest_path

        # 2. Nếu tên trùng nhưng nội dung khác -> tìm path mới hoặc bản sao có sẵn trùng nội dung
        base, ext = os.path.splitext(filename)
        counter = 1
        while True:
            candidate = os.path.join(dst_dir, f"{base}_{counter}{ext}")
            if not os.path.exists(candidate):
                dest_path = candidate
                break
            else:
                if are_files_identical(src, candidate):
                    logger.info(f"✨ Trùng nội dung với bản sao {counter}: {filename}. Đã xóa.")
                    safe_remove(src)
                    return candidate
            counter += 1

    if safe_move(src, dest_path):
        return dest_path
    return src # Trả về src nếu move thất bại (để logic bên ngoài xử lý)
