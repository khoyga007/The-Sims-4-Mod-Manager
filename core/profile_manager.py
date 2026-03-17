from __future__ import annotations

import json
import os
import logging
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional
from core.config_manager import ConfigManager

logger = logging.getLogger("ModManager.ProfileManager")

@dataclass
class Profile:
    name: str
    description: str
    active_mods: List[str]  # Basenames of enabled mods
    disabled_mods: List[str]  # Basenames of disabled mods

class ProfileManager:
    """Quản lý các hồ sơ mod (lưu trạng thái bật/tắt của các file)."""

    def __init__(self, config: Optional[ConfigManager] = None):
        self.config = config or ConfigManager()
        self.profiles_dir = os.path.join(os.path.dirname(self.config.config_path), "profiles")
        os.makedirs(self.profiles_dir, exist_ok=True)
    
    def list_profiles(self) -> List[str]:
        """Trả về danh sách tên các hồ sơ hiện có."""
        return [f.replace(".json", "") for f in os.listdir(self.profiles_dir) if f.endswith(".json")]

    def get_profile(self, name: str) -> Optional[Profile]:
        """Tải thông tin chi tiết của một hồ sơ."""
        path = os.path.join(self.profiles_dir, f"{name}.json")
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return Profile(**data)
        except Exception as e:
            logger.error(f"Lỗi khi tải profile {name}: {e}")
            return None

    def create_profile(self, name: str) -> Optional[Profile]:
        """Lưu trạng thái hiện tại của thư mục Mods thành một hồ sơ mới."""
        active = []
        disabled = []
        mod_dir = self.config.mod_directory
        
        if not mod_dir or not os.path.exists(mod_dir):
            return None

        # Quét đệ quy để tìm tất cả các mod
        for root, dirs, files in os.walk(mod_dir):
            if "_backup" in root or "__" in root:
                continue
            for fname in files:
                if fname.endswith((".package", ".ts4script")):
                    active.append(fname)
                elif fname.endswith((".package.disabled", ".ts4script.disabled")):
                    disabled.append(fname)

        desc = f"{len(active)} active, {len(disabled)} disabled"
        profile = Profile(name=name, description=desc, active_mods=active, disabled_mods=disabled)

        
        # Lưu vào file JSON
        path = os.path.join(self.profiles_dir, f"{name}.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(asdict(profile), f, indent=4, ensure_ascii=False)
            return profile
        except Exception as e:
            logger.error(f"Lỗi khi lưu profile {name}: {e}")
            return None

    def apply_profile(self, name: str) -> bool:
        """Áp dụng một hồ sơ: đổi tên các file để khớp với trạng thái đã lưu."""
        profile = self.get_profile(name)
        if not profile:
            return False

        mod_dir = self.config.mod_directory
        if not mod_dir or not os.path.exists(mod_dir):
            return False

        # Để an toàn, chúng ta quét toàn bộ folder và khớp theo tên cơ sở (basename)
        # Lưu ý: Nếu có 2 file cùng tên ở 2 folder khác nhau, cách này có thể gây nhầm lẫn.
        # Nhưng thường trong Sims 4 người dùng cố gắng tránh trùng tên.
        
        # Tạo map để tra cứu trạng thái mong muốn O(1)
        desired_active = set(profile.active_mods)
        desired_disabled = set(profile.disabled_mods)

        for root, dirs, files in os.walk(mod_dir):
            if "_backup" in root or "__" in root:
                continue
            for fname in files:
                # Bỏ qua các file không liên quan
                if not (fname.endswith(".package") or fname.endswith(".ts4script") or 
                        fname.endswith(".package.disabled") or fname.endswith(".ts4script.disabled")):
                    continue

                current_path = os.path.join(root, fname)
                is_currently_disabled = fname.endswith(".disabled")
                base_name = fname[:-9] if is_currently_disabled else fname
                
                # Quyết định trạng thái mới
                should_be_active = base_name in desired_active
                should_be_disabled = base_name in desired_disabled
                
                # EAFP pattern: Rename thẳng, không cần kiểm tra exists() dài dòng
                try:
                    if should_be_active and is_currently_disabled:
                        os.rename(current_path, os.path.join(root, base_name))
                    elif should_be_disabled and not is_currently_disabled:
                        os.rename(current_path, current_path + ".disabled")
                except OSError as e:
                    logger.error(f"Lỗi khi chuyển trạng thái file {fname}: {e}")
        
        return True

    def delete_profile(self, name: str) -> bool:
        """Xóa một hồ sơ."""
        path = os.path.join(self.profiles_dir, f"{name}.json")
        if os.path.exists(path):
            os.remove(path)
            return True
        return False
