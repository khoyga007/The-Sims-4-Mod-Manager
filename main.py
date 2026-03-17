"""
Sims 4 Mod Manager — Entry Point
"""
import sys
import os
import logging

# Ensure project root is in path
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

from core.config_manager import ConfigManager
from gui.app import ModManagerApp


def setup_logging(debug: bool = False):
    """Thiết lập logging."""
    log_level = logging.DEBUG if debug else logging.INFO
    log_format = "[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s"

    # File handler
    log_file = os.path.join(PROJECT_DIR, "mod_manager.log")
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(log_format))

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)


def main():
    """Hàm khởi chạy chính."""
    print("=" * 50)
    print("🎮 Sims 4 Mod Manager v1.0.0")
    print("=" * 50)

    # Load config
    config = ConfigManager()
    setup_logging(debug=config.debug)

    logger = logging.getLogger("ModManager")
    logger.info("Khởi động Sims 4 Mod Manager...")
    logger.info(f"Thư mục Mod: {config.mod_directory}")
    logger.info(f"Thư mục Staging: {config.staging_directory}")

    # Ensure mod directory exists
    if not os.path.exists(config.mod_directory):
        logger.warning(f"Thư mục Mod không tồn tại, tạo mới: {config.mod_directory}")
        os.makedirs(config.mod_directory, exist_ok=True)

    # Launch app
    app = ModManagerApp()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()


if __name__ == "__main__":
    main()
