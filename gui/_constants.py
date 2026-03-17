"""
Constants — Màu sắc, chuỗi và hằng số dùng chung toàn bộ GUI.

Tập trung tất cả magic strings / magic colors vào một chỗ để dễ bảo trì.
"""

# ─── Palette ──────────────────────────────────────────────────────────────────
class Color:
    # Backgrounds
    BG_BASE        = ("#f2f2f7", "#11111b")   # Sidebar, cửa sổ gốc
    BG_SURFACE     = ("#ffffff", "#13131d")   # Content area
    BG_CARD        = ("#ebebef", "#1e1e2e")   # Card, input frame
    BG_INPUT       = ("#d1d1d6", "#2d2d3f")   # Entry, combobox
    BG_DIVIDER     = ("#c7c7cc", "#3d3d5c")   # Separator, scrollbar

    # Brand / Accent
    ACCENT         = ("#6366f1", "#6366f1")   # Primary action
    ACCENT_HOVER   = ("#4f46e5", "#4f46e5")
    ACCENT_LIGHT   = ("#4338ca", "#a5b4fc")   # Label, slider thumb

    PURPLE         = ("#8b5cf6", "#8b5cf6")
    PURPLE_HOVER   = ("#7c3aed", "#7c3aed")

    # Semantic
    SUCCESS        = ("#10b981", "#10b981")
    SUCCESS_HOVER  = ("#059669", "#059669")
    WARNING        = ("#f59e0b", "#f59e0b")
    WARNING_HOVER  = ("#d97706", "#d97706")
    ERROR          = ("#ef4444", "#ef4444")
    ERROR_HOVER    = ("#dc2626", "#dc2626")
    INFO           = ("#3b82f6", "#3b82f6")
    INFO_HOVER     = ("#2563eb", "#2563eb")

    # Text
    TEXT_PRIMARY   = ("#1c1c1e", "#e2e8f0")
    TEXT_SECONDARY = ("#48484a", "#94a3b8")
    TEXT_MUTED     = ("#8e8e93", "#64748b")
    TEXT_DISABLED  = ("#aeaeb2", "#3d3d5c")

    # Special
    TSR_ACTIVE     = ("#d97706", "#f59e0b")
    CYAN           = ("#0891b2", "#06b6d4")
    VIOLET         = ("#9333ea", "#a855f7")
    ORANGE         = ("#ea580c", "#f97316")


# ─── Status labels (phải khớp với StatusBadge.STATUS_COLORS) ─────────────────
class Status:
    WAITING    = "Đợi"
    TICKET     = "Lấy ticket"
    DELAY      = "Chờ 10s"
    DOWNLOADING = "Đang tải"
    UNPACKING  = "Giải nén"
    SORTING    = "Phân loại"
    DONE       = "Hoàn tất"
    ERROR      = "Lỗi"


# ─── Mod file extensions ──────────────────────────────────────────────────────
MOD_EXTENSIONS: frozenset[str] = frozenset({".package", ".ts4script"})

# ─── Tray file extensions ─────────────────────────────────────────────────────
TRAY_EXTENSIONS: frozenset[str] = frozenset({
    ".trayitem", ".blueprint", ".bpi", ".householdbinary", 
    ".sgi", ".hhi", ".rmi"
})

# ─── Archive extensions ───────────────────────────────────────────────────────
ARCHIVE_EXTENSIONS: frozenset[str] = frozenset({".zip", ".rar", ".7z"})

# ─── Config keys ─────────────────────────────────────────────────────────────
class ConfigKey:
    MOD_DIRECTORY              = "mod_directory"
    TRAY_DIRECTORY             = "tray_directory"
    STAGING_DIRECTORY          = "staging_directory"
    MAX_DOWNLOADS              = "max_downloads"
    AUTO_UNPACK                = "auto_unpack"
    AUTO_SORT                  = "auto_sort"
    CLIPBOARD_MONITOR          = "clipboard_monitor"
    DELETE_ARCHIVE_AFTER_UNPACK = "delete_archive_after_unpack"
    SORT_RULES                 = "sort_rules"
    GAME_PATH                  = "game_path"
    AUTO_CLEAR_CACHE           = "auto_clear_cache"
    TURBO_MODE                 = "turbo_mode"
    DX11_MODE                  = "dx11_mode"
    TS4_DOCS_DIR               = "ts4_docs_dir"
    APPEARANCE_MODE            = "appearance_mode"
