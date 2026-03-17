"""
Config Manager — Đọc/ghi cấu hình cho Sims 4 Mod Manager.

Sử dụng pattern Singleton: mọi nơi ``ConfigManager()`` đều trả về
cùng 1 instance trong suốt vòng đời ứng dụng.
"""
from __future__ import annotations

import json
import os
from threading import Lock
from typing import Any, Optional

_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_DIR = os.path.dirname(_CURRENT_DIR)
CONFIG_PATH = os.path.join(_PROJECT_DIR, "config.json")

DEFAULT_CONFIG: dict[str, Any] = {
    "mod_directory":              r"D:\The Sims 4 mods",
    "tray_directory":             r"D:\The Sims 4 Tray",
    "staging_directory":          r"D:\The Sims 4 mods\_staging",
    "max_downloads":              4,
    "auto_unpack":                True,
    "auto_sort":                  True,
    "clipboard_monitor":          True,
    "delete_archive_after_unpack": True,
    "save_download_queue":        True,
    "debug":                      False,
    "sort_rules":                 {},
    "game_path":                  r"E:\The.Sims.4_LinkNeverDie.Com\Game\Bin\TS4_x64.exe",
    "auto_clear_cache":           False,
    "turbo_mode":                 False,
    "dx11_mode":                  False,
    "ts4_docs_dir":               None,
    "backup_directory":           r"D:\Sims4ModManager_Backups",
    "appearance_mode":            "dark",
    "auto_rotate_warp":           False,
    "warp_cli_path":              "warp-cli",
}


class ConfigManager:
    """Singleton quản lý cấu hình ứng dụng.

    Đọc từ ``config.json`` lần đầu tiên, mọi lần ``ConfigManager()`` sau đó
    đều trả về cùng instance đã tải.

    Examples
    --------
    >>> cfg = ConfigManager()
    >>> cfg.mod_directory
    'D:\\\\The Sims 4 mods'
    >>> cfg.set("max_downloads", 6)
    """

    _instance: "ConfigManager | None" = None
    _init_lock = Lock()

    def __new__(cls) -> "ConfigManager":
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:   # double-check locking
                    inst = super().__new__(cls)
                    inst._config: dict[str, Any] = {}
                    inst._load()
                    cls._instance = inst
        return cls._instance

    # ─────────────────────────────────────────────────────────────────────────
    # Persistence
    # ─────────────────────────────────────────────────────────────────────────

    def _load(self) -> None:
        """Tải cấu hình từ JSON hoặc tạo file mặc định."""
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    self._config = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._config = DEFAULT_CONFIG.copy()
                self._save()
        else:
            self._config = DEFAULT_CONFIG.copy()
            self._save()

        # Đảm bảo thư mục staging tồn tại
        staging = self._config.get("staging_directory", DEFAULT_CONFIG["staging_directory"])
        try:
            os.makedirs(staging, exist_ok=True)
        except OSError:
            pass  # Thư mục không hợp lệ — sẽ báo lỗi khi dùng thực sự

    def _save(self) -> None:
        """Ghi cấu hình hiện tại ra file JSON."""
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self._config, f, indent=4, ensure_ascii=False)
        except OSError as exc:
            import logging
            logging.getLogger("ModManager.Config").error(f"Không thể lưu config: {exc}")

    # Public aliases giữ backward-compat
    def load(self) -> None:
        """Tải lại cấu hình từ file (dùng khi file bị chỉnh tay)."""
        self._load()

    def save(self) -> None:
        """Lưu cấu hình hiện tại xuống file."""
        self._save()

    # ─────────────────────────────────────────────────────────────────────────
    # Generic get/set
    # ─────────────────────────────────────────────────────────────────────────

    def get(self, key: str, default: Any = None) -> Any:
        """Đọc giá trị theo khóa.

        Parameters
        ----------
        key:
            Tên khóa cấu hình.
        default:
            Giá trị mặc định nếu khóa không tồn tại.
        """
        return self._config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Ghi giá trị và lưu ngay lập tức xuống file.

        Parameters
        ----------
        key:
            Tên khóa cấu hình.
        value:
            Giá trị mới.
        """
        self._config[key] = value
        self._save()

    # ─────────────────────────────────────────────────────────────────────────
    # Typed properties
    # ─────────────────────────────────────────────────────────────────────────

    @property
    def mod_directory(self) -> str:
        """Thư mục chứa toàn bộ mod."""
        return self._config.get("mod_directory", DEFAULT_CONFIG["mod_directory"])

    @property
    def tray_directory(self) -> str:
        """Thư mục Tray của game."""
        val = self._config.get("tray_directory")
        if val: return val

        # Thử lấy từ ts4_docs_dir
        docs = self.ts4_docs_dir
        if docs:
            tray = os.path.join(docs, "Tray")
            if os.path.exists(tray):
                return tray

        # Fallback cũ
        parent = os.path.dirname(self.mod_directory)
        return os.path.join(parent, "Tray")

    @property
    def staging_directory(self) -> str:
        """Thư mục tạm để giải nén trước khi phân loại."""
        return self._config.get("staging_directory", DEFAULT_CONFIG["staging_directory"])

    @property
    def max_downloads(self) -> int:
        """Số lượng tải xuống đồng thời tối đa."""
        return int(self._config.get("max_downloads", DEFAULT_CONFIG["max_downloads"]))

    @property
    def sort_rules(self) -> dict[str, list[str]]:
        """Quy tắc phân loại ``{thư_mục: [từ_khóa, ...]}``. """
        return self._config.get("sort_rules", {})

    @property
    def auto_unpack(self) -> bool:
        """Tự động giải nén sau khi tải xong."""
        return bool(self._config.get("auto_unpack", True))

    @property
    def auto_sort(self) -> bool:
        """Tự động phân loại file vào thư mục con."""
        return bool(self._config.get("auto_sort", True))

    @property
    def clipboard_monitor_enabled(self) -> bool:
        """Bật theo dõi clipboard để tự động bắt link."""
        return bool(self._config.get("clipboard_monitor", True))

    @property
    def delete_archive_after_unpack(self) -> bool:
        """Xóa file nén sau khi giải nén thành công."""
        return bool(self._config.get("delete_archive_after_unpack", True))

    @property
    def debug(self) -> bool:
        """Bật chế độ debug (log chi tiết hơn)."""
        return bool(self._config.get("debug", False))

    @property
    def game_path(self) -> str:
        """Đường dẫn đến file thực thi của game."""
        return self._config.get("game_path", DEFAULT_CONFIG["game_path"])

    @property
    def auto_clear_cache(self) -> bool:
        """Tự động xóa cache sau khi tắt game."""
        return bool(self._config.get("auto_clear_cache", DEFAULT_CONFIG["auto_clear_cache"]))

    @property
    def turbo_mode(self) -> bool:
        """Bật ưu tiên CPU (High Priority) khi chạy game."""
        return bool(self._config.get("turbo_mode", False))

    @property
    def dx11_mode(self) -> bool:
        """Sử dụng DirectX 11 khi chạy game."""
        return bool(self._config.get("dx11_mode", False))

    @property
    def backup_directory(self) -> str:
        """Thư mục lưu trữ backup các file nén đã gộp."""
        return self._config.get("backup_directory", DEFAULT_CONFIG["backup_directory"])

    @property
    def appearance_mode(self) -> str:
        """Chế độ hiển thị (dark, light, system)."""
        return self._config.get("appearance_mode", "dark")

    @property
    def auto_rotate_warp(self) -> bool:
        """Tự động đổi IP bằng Warp khi bị bóp băng thông."""
        return bool(self._config.get("auto_rotate_warp", False))

    @property
    def warp_cli_path(self) -> str:
        """Đường dẫn đến thực thi warp-cli."""
        return self._config.get("warp_cli_path", "warp-cli")

    @property
    def ts4_docs_dir(self) -> Optional[str]:
        """Thư mục tài liệu của The Sims 4 (chứa cache, Tray, Mods)."""
        val = self._config.get("ts4_docs_dir")
        if val: return val

        # Auto detect
        from core.exception_parser import ExceptionParser
        found = ExceptionParser._find_ts4_dir()
        return str(found) if found else None

    @property
    def config_path(self) -> str:
        """Trả về đường dẫn đến file config.json."""
        return CONFIG_PATH
