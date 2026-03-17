import os
import subprocess
import shutil
import logging

logger = logging.getLogger("ModManager.FileUtils")

def safe_delete(path: str) -> bool:
    """
    Xóa file hoặc thư mục một cách an toàn bằng cách đẩy vào Thùng rác (Recycle Bin) trên Windows.
    Nếu thất bại, sẽ log lỗi thay vì xóa vĩnh viễn.
    """
    if not os.path.exists(path):
        return False
        
    try:
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
        logger.info(f"Đã xóa vĩnh viễn: {path}")
        return True
    except Exception as e:
        logger.error(f"Lỗi khi xóa {path}: {e}")
        return False
def remove_empty_folders(path: str) -> int:
    """
    Xóa tất cả các thư mục trống bên trong đường dẫn cho trước (đệ quy).
    
    Returns
    -------
    int: Số lượng thư mục đã xóa.
    """
    if not os.path.exists(path) or not os.path.isdir(path):
        return 0

    removed_count = 0
    # Duyệt từ dưới lên (topdown=False) để xóa thư mục con trước, 
    # sau đó thư mục cha mới có thể trở thành trống và bị xóa.
    for root, dirs, files in os.walk(path, topdown=False):
        for name in dirs:
            dir_path = os.path.join(root, name)
            try:
                # Kiểm tra xem folder có thực sự trống không
                if not os.listdir(dir_path):
                    os.rmdir(dir_path)
                    removed_count += 1
                    logger.debug(f"Đã xóa thư mục trống: {dir_path}")
            except OSError:
                # Có thể folder đang bận hoặc không có quyền
                pass
                
    return removed_count
