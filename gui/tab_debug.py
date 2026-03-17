"""
Tab Debug — Giao diện gỡ lỗi Mod với 3 tính năng:

1. **Exception Parser** — Đọc & phân tích LastException.txt
2. **Conflict Detector** — Quét xung đột Resource ID trong .package
3. **Diagnostic Tool**  — Phương pháp 50/50 tìm mod thủ phạm
"""
from __future__ import annotations

import logging
import os
import threading
from typing import TYPE_CHECKING, Optional

import customtkinter as ctk

from gui._constants import Color
from gui.base_tab import BaseTab
from gui.ui_utils import _card, _label, _btn, _severity_color
from core.conflict_detector import ConflictDetector, ScanResult
from core.conflict_fixer import ConflictFixer

if TYPE_CHECKING:
    from core.config_manager import ConfigManager
    from core.diagnostic_tool import DiagnosticSession

logger = logging.getLogger("ModManager.TabDebug")


# ─── Tab ─────────────────────────────────────────────────────────────────────

class TabDebug(BaseTab):
    """Tab gỡ lỗi — gộp 3 tính năng chẩn đoán."""

    def __init__(self, parent, config: "ConfigManager", **kwargs):
        super().__init__(parent, **kwargs)
        self._config = config
        self._build_ui()
        self._try_load_diagnostic_state()
        self._last_scan_result: Optional[ScanResult] = None # Để lưu kết quả quét xung đột gần nhất

    # ─────────────────────────────────────────────────────────────────────────
    # UI Construction
    # ─────────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)

        # Header
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 0))
        _label(hdr, "🔧 Công cụ Gỡ lỗi", size=18, weight="bold").pack(side="left")
        _label(
            hdr, "Chẩn đoán, tìm xung đột và phân tích lỗi",
            size=12, color=Color.TEXT_SECONDARY,
        ).pack(side="left", padx=(12, 0))

        # Tabview nội dung
        tabs = ctk.CTkTabview(
            self,
            fg_color=Color.BG_CARD,
            segmented_button_fg_color=Color.BG_INPUT,
            segmented_button_selected_color=Color.ACCENT,
            segmented_button_selected_hover_color=Color.ACCENT_HOVER,
            segmented_button_unselected_color=Color.BG_INPUT,
            segmented_button_unselected_hover_color=Color.BG_DIVIDER,
            text_color=Color.TEXT_PRIMARY,
            text_color_disabled=Color.TEXT_MUTED,
            corner_radius=12,
        )
        tabs.grid(row=1, column=0, sticky="nsew", padx=20, pady=12)

        tabs.add("📄 Đọc Lỗi")
        tabs.add("⚡ Xung Đột")
        tabs.add("🔬 Chẩn Đoán 50/50")
        tabs.add("👥 CC Nhân Vật (Tray)")
        tabs.add("👻 Thiếu Mesh (Orphan)")

        self._build_exception_tab(tabs.tab("📄 Đọc Lỗi"))
        self._build_conflict_tab(tabs.tab("⚡ Xung Đột"))
        self._build_diagnostic_tab(tabs.tab("🔬 Chẩn Đoán 50/50"))
        self._build_tray_tab(tabs.tab("👥 CC Nhân Vật (Tray)"))
        self._build_orphan_tab(tabs.tab("👻 Thiếu Mesh (Orphan)"))

    # ── Tab 1: Exception Parser ───────────────────────────────────────────────

    def _build_exception_tab(self, parent) -> None:
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        # Controls
        ctrl = ctk.CTkFrame(parent, fg_color="transparent")
        ctrl.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 8))

        _label(
            ctrl,
            "Tự động tìm file LastException.txt và dịch lỗi sang tiếng Việt",
            color=Color.TEXT_SECONDARY, size=12,
        ).pack(side="left")

        self._exc_btn_scan = _btn(
            ctrl, "🔍 Quét lỗi mới nhất",
            command=self._on_scan_exception,
        )
        self._exc_btn_scan.pack(side="right", padx=(8, 0))

        self._exc_btn_all = _btn(
            ctrl, "📋 Xem tất cả",
            command=self._on_scan_all_exceptions,
            color=Color.BG_INPUT, hover=Color.BG_DIVIDER,
        )
        self._exc_btn_all.pack(side="right")

        # Scrollable result area
        scroll = ctk.CTkScrollableFrame(
            parent, fg_color=Color.BG_SURFACE, corner_radius=8,
        )
        scroll.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 12))
        scroll.grid_columnconfigure(0, weight=1)
        self._exc_scroll = scroll

        self._exc_placeholder = _label(
            scroll,
            "Nhấn \"Quét lỗi mới nhất\" để đọc LastException.txt",
            color=Color.TEXT_MUTED, size=13,
        )
        self._exc_placeholder.grid(row=0, column=0, pady=40)

    def _build_conflict_tab(self, parent) -> None:
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        # Controls
        ctrl = ctk.CTkFrame(parent, fg_color="transparent")
        ctrl.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 8))

        left = ctk.CTkFrame(ctrl, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True)

        _label(
            left,
            "Quét sâu vào file .package, tìm Resource ID bị trùng giữa các mod",
            color=Color.TEXT_SECONDARY, size=12,
        ).pack(anchor="w")

        # Filter severity
        filter_frame = ctk.CTkFrame(left, fg_color="transparent")
        filter_frame.pack(anchor="w", pady=(4, 0))
        _label(filter_frame, "Hiển thị:", size=12, color=Color.TEXT_MUTED).pack(side="left")

        self._cf_show_critical = ctk.BooleanVar(value=True)
        self._cf_show_warning  = ctk.BooleanVar(value=True)
        self._cf_show_info     = ctk.BooleanVar(value=False)

        for label, var, color in [
            ("CRITICAL", self._cf_show_critical, Color.ERROR),
            ("WARNING",  self._cf_show_warning,  Color.WARNING),
            ("INFO",     self._cf_show_info,      Color.INFO),
        ]:
            ctk.CTkCheckBox(
                filter_frame, text=label, variable=var,
                text_color=color, fg_color=color,
                hover_color=color, font=ctk.CTkFont(size=12),
                width=20, height=20,
            ).pack(side="left", padx=(8, 0))

        # Action buttons
        btn_frame = ctk.CTkFrame(ctrl, fg_color="transparent")
        btn_frame.pack(side="right")

        self._btn_clean_red = _btn(
            btn_frame, "🗑️ Dọn bản thừa",
            command=self._on_clean_redundancies,
            color=Color.BG_INPUT, hover=Color.BG_DIVIDER,
            width=120,
        )
        self._btn_clean_red.pack(side="left", padx=5)

        self._btn_repair = _btn(
            btn_frame, "🛠️ Phẫu thuật sửa lỗi",
            command=self._on_smart_repair,
            color=Color.ACCENT, hover=Color.ACCENT_HOVER,
            width=160,
        )
        # This button will be packed/unpacked dynamically based on scan results

        self._cf_btn_scan = _btn(
            btn_frame, "⚡ Quét xung đột",
            command=self._on_scan_conflicts,
            width=140,
        )
        self._cf_btn_scan.pack(side="left", padx=5)

        # Progress bar (hidden by default)
        self._cf_progress = ctk.CTkProgressBar(
            parent, fg_color=Color.BG_INPUT, progress_color=Color.ACCENT,
            height=4,
        )
        self._cf_progress.set(0)
        self._cf_progress_label = _label(
            parent, "", size=11, color=Color.TEXT_MUTED,
        )

        # Result scroll
        scroll = ctk.CTkScrollableFrame(
            parent, fg_color=Color.BG_SURFACE, corner_radius=8,
        )
        scroll.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 12))
        scroll.grid_columnconfigure(0, weight=1)
        self._cf_scroll = scroll

        self._cf_placeholder = _label(
            scroll,
            "Nhấn \"Quét xung đột\" để bắt đầu phân tích",
            color=Color.TEXT_MUTED, size=13,
        )
        self._cf_placeholder.grid(row=0, column=0, pady=40)
        self._cf_row = 0

    def _build_diagnostic_tab(self, parent) -> None:
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        # Instructions card
        info_card = _card(parent)
        info_card.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 8))
        info_card.grid_columnconfigure(0, weight=1)

        _label(
            info_card,
            "📖 Cách sử dụng",
            size=13, weight="bold",
        ).grid(row=0, column=0, sticky="w", padx=14, pady=(10, 2))
        _label(
            info_card,
            "Nhấn Bắt đầu → game sẽ chạy với 50% mod bật.\n"
            "Sau khi test, báo kết quả: Lỗi còn hay Lỗi mất.\n"
            "Tiếp tục cho đến khi tìm ra mod thủ phạm.",
            color=Color.TEXT_SECONDARY, size=12, justify="left",
        ).grid(row=1, column=0, sticky="w", padx=14, pady=(0, 10))

        # Main status card
        status_card = _card(parent)
        status_card.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 12))
        status_card.grid_columnconfigure(0, weight=1)
        status_card.grid_rowconfigure(3, weight=1)

        # Status display
        self._diag_status_label = _label(
            status_card, "Chưa có phiên chẩn đoán nào.",
            size=14, weight="bold", color=Color.TEXT_SECONDARY,
        )
        self._diag_status_label.grid(row=0, column=0, pady=(20, 4))

        self._diag_detail_label = _label(
            status_card, "",
            size=12, color=Color.TEXT_SECONDARY,
        )
        self._diag_detail_label.grid(row=1, column=0, pady=(0, 16))

        # Progress
        self._diag_progress = ctk.CTkProgressBar(
            status_card, fg_color=Color.BG_INPUT,
            progress_color=Color.ACCENT, height=6,
        )
        self._diag_progress.set(0)
        self._diag_progress.grid(
            row=2, column=0, sticky="ew", padx=24, pady=(0, 16),
        )

        # Mod list scroll
        self._diag_scroll = ctk.CTkScrollableFrame(
            status_card, fg_color=Color.BG_SURFACE, corner_radius=8,
            label_text="Mod đang test", label_font=ctk.CTkFont(size=12),
            label_text_color=Color.TEXT_SECONDARY,
        )
        self._diag_scroll.grid(row=3, column=0, sticky="nsew", padx=14, pady=(0, 14))
        self._diag_scroll.grid_columnconfigure(0, weight=1)

        # Buttons
        btn_row = ctk.CTkFrame(status_card, fg_color="transparent")
        btn_row.grid(row=4, column=0, pady=(0, 16))

        self._diag_btn_start = _btn(
            btn_row, "▶ Bắt đầu",
            command=self._on_diag_start,
            color=Color.SUCCESS, hover=Color.SUCCESS_HOVER,
        )
        self._diag_btn_start.pack(side="left", padx=6)

        self._diag_btn_bug_present = _btn(
            btn_row, "🐛 Lỗi còn",
            command=lambda: self._on_diag_report(True),
            color=Color.ERROR, hover=Color.ERROR_HOVER,
            state="disabled",
        )
        self._diag_btn_bug_present.pack(side="left", padx=6)

        self._diag_btn_bug_gone = _btn(
            btn_row, "✅ Lỗi mất",
            command=lambda: self._on_diag_report(False),
            color=Color.SUCCESS, hover=Color.SUCCESS_HOVER,
            state="disabled",
        )
        self._diag_btn_bug_gone.pack(side="left", padx=6)

        self._diag_btn_cancel = _btn(
            btn_row, "✕ Hủy & Phục hồi",
            command=self._on_diag_cancel,
            color=Color.BG_DIVIDER, hover=Color.BG_INPUT,
            state="disabled",
        )
        self._diag_btn_cancel.pack(side="left", padx=6)

    # ─────────────────────────────────────────────────────────────────────────
    # Exception Parser — Event Handlers
    # ─────────────────────────────────────────────────────────────────────────

    def _on_scan_exception(self) -> None:
        self._exc_btn_scan.configure(state="disabled", text="⏳ Đang đọc...")
        threading.Thread(target=self._exception_worker, args=(False,), daemon=True).start()

    def _on_scan_all_exceptions(self) -> None:
        self._exc_btn_all.configure(state="disabled", text="⏳ Đang đọc...")
        threading.Thread(target=self._exception_worker, args=(True,), daemon=True).start()

    def _exception_worker(self, all_files: bool) -> None:
        from core.exception_parser import ExceptionParser
        parser = ExceptionParser(self._config.get("ts4_docs_dir"))
        results = parser.parse_all() if all_files else []
        if not all_files:
            single = parser.parse_latest()
            if single:
                results = [single]

        self.after(0, lambda: self._render_exceptions(results))
        self.after(0, lambda: self._exc_btn_scan.configure(
            state="normal", text="🔍 Quét lỗi mới nhất"))
        self.after(0, lambda: self._exc_btn_all.configure(
            state="normal", text="📋 Xem tất cả"))

    def _render_exceptions(self, results) -> None:
        for widget in self._exc_scroll.winfo_children():
            widget.destroy()

        if not results:
            _label(
                self._exc_scroll,
                "✅ Không tìm thấy file LastException.txt — game ổn định!",
                color=Color.SUCCESS, size=13,
            ).grid(row=0, column=0, pady=40)
            return

        for i, parsed in enumerate(results):
            card = _card(self._exc_scroll)
            card.grid(row=i, column=0, sticky="ew", pady=(0, 10))
            card.grid_columnconfigure(1, weight=1)

            # Severity badge
            sev_color = Color.ERROR if parsed.primary_mod else Color.WARNING
            badge = ctk.CTkLabel(
                card, text=f"  {parsed.error_label}  ",
                fg_color=sev_color, corner_radius=6,
                text_color="#ffffff",
                font=ctk.CTkFont(size=11, weight="bold"),
            )
            badge.grid(row=0, column=0, sticky="w", padx=14, pady=(12, 4))

            # File name
            filename = os.path.basename(parsed.source_file)
            _label(card, filename, size=11, color=Color.TEXT_MUTED).grid(
                row=0, column=1, sticky="w", padx=8, pady=(12, 4))

            # Exception type
            _label(
                card, parsed.exception_type,
                size=15, weight="bold", color=Color.ERROR,
            ).grid(row=1, column=0, columnspan=2, sticky="w", padx=14, pady=(0, 2))

            if parsed.exception_message:
                _label(
                    card, parsed.exception_message,
                    size=12, color=Color.TEXT_SECONDARY,
                    wraplength=600, justify="left",
                ).grid(row=2, column=0, columnspan=2, sticky="w", padx=14, pady=(0, 4))

            # Explanation
            _label(
                card, f"💡 {parsed.explanation}",
                size=12, color=Color.WARNING,
            ).grid(row=3, column=0, columnspan=2, sticky="w", padx=14, pady=(0, 8))

            # Mods involved
            if parsed.mods_involved:
                mods_frame = ctk.CTkFrame(card, fg_color=Color.BG_SURFACE, corner_radius=8)
                mods_frame.grid(
                    row=4, column=0, columnspan=2,
                    sticky="ew", padx=14, pady=(0, 12),
                )
                _label(
                    mods_frame, "Mod liên quan:",
                    size=11, weight="bold", color=Color.TEXT_MUTED,
                ).pack(anchor="w", padx=10, pady=(8, 4))

                for j, mod in enumerate(parsed.mods_involved):
                    row_f = ctk.CTkFrame(mods_frame, fg_color="transparent")
                    row_f.pack(fill="x", padx=10, pady=1)

                    num_badge = ctk.CTkLabel(
                        row_f,
                        text=f"  #{j+1}  ",
                        fg_color=Color.BG_DIVIDER,
                        corner_radius=4,
                        text_color=Color.TEXT_MUTED,
                        font=ctk.CTkFont(size=10),
                    )
                    num_badge.pack(side="left")

                    _label(
                        row_f, mod.mod_name,
                        size=12, weight="bold", color=Color.ACCENT_LIGHT,
                    ).pack(side="left", padx=(6, 0))

                    if mod.file_in_mod:
                        _label(
                            row_f, f" / {mod.file_in_mod}",
                            size=11, color=Color.TEXT_MUTED,
                        ).pack(side="left")

                    if mod.line_number:
                        _label(
                            row_f, f" dòng {mod.line_number}",
                            size=11, color=Color.TEXT_MUTED,
                        ).pack(side="left")

                _label(mods_frame, "", size=4).pack()  # spacer

            if parsed.game_version:
                _label(
                    card, f"Phiên bản game: {parsed.game_version}",
                    size=10, color=Color.TEXT_DISABLED,
                ).grid(row=5, column=0, columnspan=2, sticky="w", padx=14, pady=(0, 8))

    # ─────────────────────────────────────────────────────────────────────────
    # Conflict Detector — Event Handlers
    # ─────────────────────────────────────────────────────────────────────────

    def _on_scan_conflicts(self) -> None:
        self._cf_btn_scan.configure(state="disabled", text="⏳ Đang quét...")
        self._btn_clean_red.configure(state="disabled")
        self._btn_repair.configure(state="disabled")
        self._cf_progress.grid(row=0, column=0, sticky="ew", padx=16, pady=(4, 0))
        self._cf_progress_label.grid(row=0, column=0, sticky="e", padx=16)
        self._cf_progress.set(0)
        threading.Thread(target=self._conflict_worker, daemon=True).start()

    def _conflict_worker(self) -> None:
        from core.conflict_detector import ConflictDetector

        mod_dir = self._config.mod_directory
        packages = ConflictDetector.find_packages(mod_dir)
        total = len(packages)

        def on_progress(current: int, _total: int, filename: str) -> None:
            pct = current / max(_total, 1)
            self.after(0, lambda: self._cf_progress.set(pct))
            self.after(0, lambda: self._cf_progress_label.configure(
                text=f"{current}/{_total} — {filename[:40]}"))

        detector = ConflictDetector(progress_callback=on_progress)

        severity_filter: Optional[set[str]] = set()
        if self._cf_show_critical.get():
            severity_filter.add("CRITICAL")
        if self._cf_show_warning.get():
            severity_filter.add("WARNING")
        if self._cf_show_info.get():
            severity_filter.add("INFO")

        result = detector.scan(packages, severity_filter if severity_filter else None)

        self.after(0, lambda: self._render_conflicts(result, total))
        self.after(0, lambda: self._cf_btn_scan.configure(
            state="normal", text="⚡ Quét xung đột"))
        self.after(0, lambda: self._btn_clean_red.configure(state="normal"))
        self.after(0, lambda: self._btn_repair.configure(state="normal"))
        self.after(0, lambda: self._cf_progress.grid_forget())
        self.after(0, lambda: self._cf_progress_label.grid_forget())

    def _render_conflicts(self, result: ScanResult, total_files: int) -> None:
        # Hủy phiên render cũ nếu có
        if hasattr(self, "_cf_render_id"):
            self.after_cancel(self._cf_render_id)

        for widget in self._cf_scroll.winfo_children():
            widget.destroy()

        self._last_scan_result = result
        logger.info(f"Quét xong {result.scanned} file. Xung đột: {len(result.conflicts)}, Dư thừa: {len(result.redundancies)}")
        
        # Hiện nút sửa lỗi nếu có xung đột nghiêm trọng
        if result.critical_count > 0 or result.warning_count > 0:
            self._btn_repair.pack(side="left", padx=5, before=self._btn_clean_red)
        else:
            self._btn_repair.pack_forget()

        # 1. Summary row (Hiển thị ngay lập tức)
        summary = _card(self._cf_scroll)
        summary.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        summary.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)

        self._cf_summary_labels = {}
        for col, (key, label, value, color) in enumerate([
            ("scanned", "File quét",  str(total_files),              Color.TEXT_PRIMARY),
            ("critical", "CRITICAL",   str(result.critical_count),    Color.ERROR),
            ("warning", "WARNING",    str(result.warning_count),     Color.WARNING),
            ("redundant", "Dư thừa",   str(len(result.redundancies)), Color.ACCENT),
            ("total",   "Tổng XC",    str(len(result.conflicts)),    Color.ACCENT_LIGHT),
        ]):
            f = ctk.CTkFrame(summary, fg_color="transparent")
            f.grid(row=0, column=col, padx=16, pady=12)
            lbl_val = _label(f, value, size=22, weight="bold", color=color)
            lbl_val.pack()
            _label(f, label, size=11, color=Color.TEXT_MUTED).pack()
            self._cf_summary_labels[key] = lbl_val

        if not result.conflicts and not result.redundancies:
            _label(
                self._cf_scroll,
                "🎉 Không tìm thấy xung đột hay bản trùng lặp nào!",
                color=Color.SUCCESS, size=14,
            ).grid(row=1, column=0, pady=30)
            return

        # 2. Thu thập danh sách các công việc cần render (Flatten)
        render_queue = []
        MAX_DISPLAY = 100  # Giới hạn số lượng hiển thị trên giao diện (Đã giảm từ 300 xuống 100)
        total_items = 0

        if result.redundancies:
            render_queue.append(('header_red', len(result.redundancies)))
            for red in result.redundancies:
                if total_items < MAX_DISPLAY:
                    render_queue.append(('redundancy', red))
                    total_items += 1
            render_queue.append(('divider', None))

        for sev in ("CRITICAL", "WARNING", "INFO"):
            group = [c for c in result.conflicts if c.severity == sev]
            if not group: continue
            
            # Chỉ thêm header nếu còn chỗ hoặc đợt này có thể hiển thị ít nhất vài cái
            if total_items < MAX_DISPLAY:
                render_queue.append(('header_sev', (sev, len(group))))
                for conflict in group:
                    if total_items < MAX_DISPLAY:
                        render_queue.append(('conflict', conflict))
                        total_items += 1
                    else:
                        break

        # 3. Nếu vượt quá giới hạn, thêm thông báo ở cuối
        if len(result.conflicts) + len(result.redundancies) > MAX_DISPLAY:
            render_queue.append(('footer_limit', (MAX_DISPLAY, len(result.conflicts) + len(result.redundancies))))

        # 4. Bắt đầu render từng đợt để không treo GUI
        self._curr_cf_row = 1
        self._process_render_queue(render_queue, 0)

    def _process_render_queue(self, queue: list, index: int) -> None:
        """Render từng cụm 20 item mỗi lần."""
        BATCH_SIZE = 20
        end_index = min(index + BATCH_SIZE, len(queue))
        
        from core.file_utils import safe_delete

        for i in range(index, end_index):
            msg_type, data = queue[i]
            
            if msg_type == 'header_red':
                f = ctk.CTkFrame(self._cf_scroll, fg_color="transparent")
                f.grid(row=self._curr_cf_row, column=0, sticky="w", pady=(8, 4))
                ctk.CTkLabel(f, text="  DƯ THỪA  ", fg_color=Color.ACCENT, corner_radius=6,
                             text_color="#ffffff", font=ctk.CTkFont(size=11, weight="bold")).pack(side="left")
                _label(f, f"  {data} file đã có trong bản gộp", size=12, color=Color.ACCENT_LIGHT).pack(side="left")

            elif msg_type == 'redundancy':
                f_path, m_path = data
                row = ctk.CTkFrame(self._cf_scroll, fg_color=Color.BG_CARD, corner_radius=8)
                row.grid(row=self._curr_cf_row, column=0, sticky="ew", pady=2)
                row.grid_columnconfigure(1, weight=1)
                _label(row, f"⚠️ {os.path.basename(f_path)}", size=12, weight="bold").grid(row=0, column=0, padx=12, pady=8)
                _label(row, f"Đã có trong: {os.path.basename(m_path)}", size=11, color=Color.TEXT_MUTED).grid(row=0, column=1, sticky="w")
                ctk.CTkButton(row, text="Xóa bản thừa", width=100, height=24, fg_color=Color.ERROR,
                              hover_color=Color.ERROR_HOVER, font=ctk.CTkFont(size=11),
                              command=lambda p=f_path, w=row: self._on_delete_redundancy(p, w)).grid(row=0, column=2, padx=12)

            elif msg_type == 'divider':
                ctk.CTkFrame(self._cf_scroll, fg_color=Color.BG_DIVIDER, height=2).grid(row=self._curr_cf_row, column=0, sticky="ew", pady=10)

            elif msg_type == 'header_sev':
                sev, count = data
                f = ctk.CTkFrame(self._cf_scroll, fg_color="transparent")
                f.grid(row=self._curr_cf_row, column=0, sticky="w", pady=(8, 4))
                badge_color = _severity_color(sev)
                ctk.CTkLabel(f, text=f"  {sev}  ", fg_color=badge_color, corner_radius=6,
                             text_color="#ffffff", font=ctk.CTkFont(size=11, weight="bold")).pack(side="left")
                _label(f, f"  {count} xung đột", size=12, color=Color.TEXT_SECONDARY).pack(side="left")

            elif msg_type == 'conflict':
                conflict = data
                badge_color = _severity_color(conflict.severity)
                row = ctk.CTkFrame(self._cf_scroll, fg_color=Color.BG_CARD, corner_radius=8)
                row.grid(row=self._curr_cf_row, column=0, sticky="ew", pady=2)
                row.grid_columnconfigure(1, weight=1)
                ctk.CTkLabel(row, text=f"  {conflict.type_name}  ", fg_color=badge_color, corner_radius=6,
                             text_color="#ffffff", font=ctk.CTkFont(size=11, weight="bold")).grid(row=0, column=0, padx=(10, 0), pady=8)
                
                file_labels = [f"📦 {os.path.basename(p)}" if os.path.basename(p).startswith("_MERGED_") else os.path.basename(p) for p in conflict.packages]
                lbl = _label(row, "  ↔  ".join(file_labels), size=12, color=Color.ACCENT_LIGHT if any(f.startswith("📦") for f in file_labels) else Color.TEXT_PRIMARY)
                lbl.grid(row=0, column=1, sticky="w", padx=10)
                if any(f.startswith("📦") for f in file_labels): lbl.configure(font=ctk.CTkFont(size=12, weight="bold"))
                _label(row, f"0x{conflict.key.instance_id:016X}", size=10, color=Color.TEXT_MUTED).grid(row=0, column=2, padx=(0, 12))

            elif msg_type == 'footer_limit':
                shown, total = data
                f = _card(self._cf_scroll, fg_color=Color.BG_DIVIDER)
                f.grid(row=self._curr_cf_row, column=0, sticky="ew", pady=15)
                _label(f, f"⚠️ Đang hiển thị {shown} / {total} xung đột để tránh treo máy.",
                       size=13, weight="bold", color=Color.WARNING).pack(pady=(12, 4))
                _label(f, "Hãy ưu tiên xử lý các mục CRITICAL và WARNING bên trên trước.\nBạn có thể xem danh sách đầy đủ trong file log.",
                       size=12, color=Color.TEXT_SECONDARY).pack(pady=(0, 12))
                
                # Nút mở log file
                def open_log():
                    log_path = os.path.abspath("mod_manager.log")
                    if os.path.exists(log_path): os.startfile(log_path)

                ctk.CTkButton(f, text="📄 Xem danh sách đầy đủ trong Log", width=220, height=28,
                              fg_color="#475569", hover_color="#64748b", font=ctk.CTkFont(size=11),
                              command=open_log).pack(pady=(0, 12))

            self._curr_cf_row += 1

        # Lên đợt tiếp theo
        if end_index < len(queue):
            self._cf_render_id = self.after(10, lambda: self._process_render_queue(queue, end_index))
        else:
            if hasattr(self, "_cf_render_id"):
                del self._cf_render_id

    def _on_delete_redundancy(self, path: str, widget: ctk.CTkFrame) -> None:
        """Xóa file dư thừa trong thread riêng để không treo GUI."""
        def worker():
            from core.file_utils import safe_delete
            if safe_delete(path):
                self.after(0, lambda: self._remove_conflict_widget(widget))

        threading.Thread(target=worker, daemon=True).start()

    def _remove_conflict_widget(self, widget: ctk.CTkFrame) -> None:
        """Xóa widget khỏi danh sách và cập nhật tóm tắt mà không cần quét lại."""
        widget.destroy()
        
        # Cập nhật số lượng dư thừa trong Summary (nếu label tồn tại)
        if hasattr(self, "_cf_summary_labels") and "redundant" in self._cf_summary_labels:
            try:
                curr = int(self._cf_summary_labels["redundant"].cget("text"))
                self._cf_summary_labels["redundant"].configure(text=str(max(0, curr - 1)))
            except Exception:
                pass

    def _on_clean_redundancies(self) -> None:
        """Xóa toàn bộ các file dư thừa đã tìm thấy."""
        if not hasattr(self, "_last_scan_result") or not self._last_scan_result.redundancies:
            return

        from tkinter import messagebox
        count = len(self._last_scan_result.redundancies)
        confirm = messagebox.askyesno(
            "Xác nhận xóa hết",
            f"Bạn có chắc chắn muốn xóa toàn bộ {count} bản mod dư thừa?\n\n"
            "Các file gốc này sẽ bị xóa vì chúng đã có bản sao trong các file Merged."
        )
        if not confirm:
            return

        self._btn_clean_red.configure(state="disabled", text="⏳ Đang xóa...")
        self._cf_btn_scan.configure(state="disabled")

        def worker():
            from core.file_utils import safe_delete
            cleaned = 0
            for f_path, _ in self._last_scan_result.redundancies:
                if safe_delete(f_path):
                    cleaned += 1
            
            def done():
                messagebox.showinfo("Hoàn tất", f"Đã xóa xong {cleaned} bản mod dư thừa.")
                self._btn_clean_red.configure(state="normal", text="🗑️ Dọn bản thừa")
                self._cf_btn_scan.configure(state="normal")
                self._on_scan_conflicts() # Quét lại để cập nhật list

            self.after(0, done)

        threading.Thread(target=worker, daemon=True).start()

    # ─────────────────────────────────────────────────────────────────────────
    # Smart Repair
    # ─────────────────────────────────────────────────────────────────────────

    def _on_smart_repair(self) -> None:
        """Thực hiện phẫu thuật sửa lỗi file .package."""
        if not hasattr(self, "_last_scan_result") or not self._last_scan_result.conflicts:
            return

        from tkinter import messagebox
        confirm = messagebox.askyesno(
            "Xác nhận PHẪU THUẬT",
            "Công cụ này sẽ trực tiếp sửa các file .package bị xung đột bằng cách:\n"
            "1. Tìm các Resource bị trùng lặp.\n"
            "2. Xóa bỏ chúng ở một bên và giữ lại bản duy nhất.\n\n"
            "LƯU Ý: Đây là thao tác can thiệp trực tiếp vào file. Bạn nên sao lưu (copy) "
            "folder Mods ra ngoài trước khi làm để đảm bảo an toàn.\n\n"
            "Bạn có muốn tiếp tục không?"
        )
        
        if not confirm:
            return

        self._btn_repair.configure(state="disabled", text="⏳ Đang phẫu thuật...")
        self._cf_btn_scan.configure(state="disabled")
        
        # Hiện progress bar
        self._cf_progress.grid(row=0, column=0, sticky="ew", padx=16, pady=(4, 0))
        self._cf_progress_label.grid(row=0, column=0, sticky="e", padx=16)
        self._cf_progress.set(0)
        
        def worker():
            fixer = ConflictFixer(progress_callback=self._update_repair_progress)
            count = fixer.fix_all(self._last_scan_result)
            
            self.after(0, lambda: self._on_repair_done(count))

        threading.Thread(target=worker, daemon=True).start()

    def _update_repair_progress(self, current: int, total: int, msg: str) -> None:
        pct = current / max(total, 1)
        self.after(0, lambda: self._cf_progress.set(pct))
        self.after(0, lambda: self._cf_progress_label.configure(text=msg))

    def _on_repair_done(self, count: int) -> None:
        from tkinter import messagebox
        messagebox.showinfo("Hoàn tất", f"Đã 'phẫu thuật' thành công {count} file.\n\nBây giờ hãy nhấn 'Quét xung đột' lại để kiểm tra kết quả.")
        self._btn_repair.configure(state="normal", text="🛠️ Phẫu thuật sửa lỗi")
        self._cf_btn_scan.configure(state="normal")
        self._cf_progress.set(1.0)
        self.after(500, lambda: self._cf_progress.grid_forget())
        self.after(500, lambda: self._cf_progress_label.grid_forget())
        self._on_scan_conflicts() # Tự động quét lại

    def _try_load_diagnostic_state(self) -> None:
        """Khi mở app, kiểm tra có phiên dở dang không."""
        try:
            from core.diagnostic_tool import DiagnosticTool
            tool = DiagnosticTool(self._config.mod_directory)
            session = tool.load_state()
            if session and session.is_active:
                self._diag_tool = tool
                self._diag_session = session
                self._refresh_diagnostic_ui()
        except Exception:
            pass

    def _on_diag_start(self) -> None:
        self._diag_btn_start.configure(state="disabled", text="⏳ Đang chuẩn bị...")
        threading.Thread(target=self._diag_start_worker, daemon=True).start()

    def _diag_start_worker(self) -> None:
        try:
            from core.diagnostic_tool import DiagnosticTool
            self._diag_tool = DiagnosticTool(self._config.mod_directory)
            self._diag_session = self._diag_tool.start_new_session()
            self.after(0, self._refresh_diagnostic_ui)
        except Exception as exc:
            logger.error(f"Lỗi bắt đầu chẩn đoán: {exc}")
            self.after(0, lambda: self._diag_status_label.configure(
                text=f"❌ Lỗi: {exc}",
                text_color=Color.ERROR,
            ))
            self.after(0, lambda: self._diag_btn_start.configure(
                state="normal", text="▶ Bắt đầu"))

    def _on_diag_report(self, bug_present: bool) -> None:
        self._diag_btn_bug_present.configure(state="disabled")
        self._diag_btn_bug_gone.configure(state="disabled")
        threading.Thread(
            target=self._diag_report_worker, args=(bug_present,), daemon=True
        ).start()

    def _diag_report_worker(self, bug_present: bool) -> None:
        try:
            self._diag_session = self._diag_tool.report_result(bug_present)
            self.after(0, self._refresh_diagnostic_ui)
        except Exception as exc:
            logger.error(f"Lỗi báo kết quả: {exc}")

    def _on_diag_cancel(self) -> None:
        if hasattr(self, "_diag_tool"):
            self._diag_tool.cancel_session()
        self._diag_session = None
        self._refresh_diagnostic_ui()

    def _refresh_diagnostic_ui(self) -> None:
        """Cập nhật toàn bộ UI chẩn đoán từ trạng thái session."""
        session = getattr(self, "_diag_session", None)

        # Clear mod list
        for widget in self._diag_scroll.winfo_children():
            widget.destroy()

        if not session:
            self._diag_status_label.configure(
                text="Chưa có phiên chẩn đoán nào.",
                text_color=Color.TEXT_SECONDARY,
            )
            self._diag_detail_label.configure(text="")
            self._diag_progress.set(0)
            self._diag_btn_start.configure(state="normal", text="▶ Bắt đầu")
            self._diag_btn_bug_present.configure(state="disabled")
            self._diag_btn_bug_gone.configure(state="disabled")
            self._diag_btn_cancel.configure(state="disabled")
            return

        # Tìm ra thủ phạm
        if session.found_mod:
            mod_name = os.path.basename(session.found_mod)
            self._diag_status_label.configure(
                text=f"🎯 Tìm ra thủ phạm: {mod_name}",
                text_color=Color.ERROR,
            )
            self._diag_detail_label.configure(
                text=f"Sau {session.steps_taken} bước. Tất cả mod đã được phục hồi.",
                text_color=Color.TEXT_SECONDARY,
            )
            self._diag_progress.set(1.0)
            self._diag_btn_start.configure(state="normal", text="▶ Bắt đầu lại")
            self._diag_btn_bug_present.configure(state="disabled")
            self._diag_btn_bug_gone.configure(state="disabled")
            self._diag_btn_cancel.configure(state="disabled")

            # Highlight mod thủ phạm
            result_frame = ctk.CTkFrame(
                self._diag_scroll, fg_color=Color.ERROR, corner_radius=8
            )
            result_frame.pack(fill="x", padx=4, pady=4)
            _label(
                result_frame, f"⚠️  {mod_name}",
                size=13, weight="bold", color="#ffffff",
            ).pack(padx=12, pady=8)
            _label(
                result_frame, session.found_mod,
                size=10, color="#ffcccc",
            ).pack(padx=12, pady=(0, 8))
            return

        # Phiên đang chạy
        if session.is_active and session.current_step:
            step = session.current_step
            total = len(session.all_mods)
            candidates = len(step.active_set) + len(step.disabled_set)

            # Progress = thu hẹp từ total → 1
            import math
            if total > 1:
                steps_total = math.ceil(math.log2(total))
                steps_done  = session.steps_taken - 1
                progress = min(steps_done / max(steps_total, 1), 0.95)
            else:
                progress = 0.5
            self._diag_progress.set(progress)

            self._diag_status_label.configure(
                text=f"🔬 Bước {step.step_number} — {candidates} candidates còn lại",
                text_color=Color.ACCENT_LIGHT,
            )
            self._diag_detail_label.configure(
                text=(
                    f"Đang bật {len(step.active_set)} / {total} mod. "
                    f"Ước tính còn ~{session.steps_remaining} bước nữa."
                ),
                text_color=Color.TEXT_SECONDARY,
            )

            # Hiển thị mod đang test
            _label(
                self._diag_scroll,
                f"Đang bật ({len(step.active_set)} mod) — Chạy game rồi báo kết quả:",
                size=12, weight="bold", color=Color.TEXT_MUTED,
            ).pack(anchor="w", pady=(4, 2))

            for filepath in list(step.active_set)[:50]:
                row = ctk.CTkFrame(self._diag_scroll, fg_color=Color.BG_CARD, corner_radius=6)
                row.pack(fill="x", pady=1)
                ctk.CTkLabel(
                    row, text="●",
                    text_color=Color.SUCCESS,
                    font=ctk.CTkFont(size=10),
                ).pack(side="left", padx=(8, 4))
                _label(
                    row, os.path.basename(filepath),
                    size=12, color=Color.TEXT_PRIMARY,
                ).pack(side="left", pady=4)

            if len(step.active_set) > 50:
                _label(
                    self._diag_scroll,
                    f"  ... và {len(step.active_set) - 50} mod khác",
                    size=11, color=Color.TEXT_DISABLED,
                ).pack(anchor="w", padx=8, pady=4)

            if step.disabled_set:
                _label(
                    self._diag_scroll,
                    f"Đang tắt ({len(step.disabled_set)} mod):",
                    size=12, weight="bold", color=Color.TEXT_MUTED,
                ).pack(anchor="w", pady=(8, 2))
                for filepath in step.disabled_set[:5]:
                    _label(
                        self._diag_scroll,
                        f"  ○  {os.path.basename(filepath)}",
                        size=11, color=Color.TEXT_DISABLED,
                    ).pack(anchor="w", padx=8)
                if len(step.disabled_set) > 5:
                    _label(
                        self._diag_scroll,
                        f"  ... và {len(step.disabled_set) - 5} mod khác",
                        size=11, color=Color.TEXT_DISABLED,
                    ).pack(anchor="w", padx=8)

            # Enable report buttons
            self._diag_btn_start.configure(state="disabled", text="▶ Bắt đầu")
            self._diag_btn_bug_present.configure(state="normal")
            self._diag_btn_bug_gone.configure(state="normal")
            self._diag_btn_cancel.configure(state="normal")
        else:
            # Phiên kết thúc không tìm ra thủ phạm
            self._diag_status_label.configure(
                text="⚠️ Không tìm ra thủ phạm",
                text_color=Color.WARNING,
            )
            self._diag_detail_label.configure(
                text="Có thể lỗi không phải do mod hoặc lỗi tạm thời.",
                text_color=Color.TEXT_SECONDARY,
            )
            self._diag_progress.set(0)
            self._diag_btn_start.configure(state="normal", text="▶ Bắt đầu lại")
            self._diag_btn_bug_present.configure(state="disabled")
            self._diag_btn_bug_gone.configure(state="disabled")
            self._diag_btn_cancel.configure(state="disabled")

    # ── Tab 4: Tray Explorer ──────────────────────────────────────────────────
    
    def _build_tray_tab(self, parent) -> None:
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        ctrl = ctk.CTkFrame(parent, fg_color="transparent")
        ctrl.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 8))
        _label(ctrl, "Quét thư mục Tray để biết nhân vật/nhà đang dùng mod nào", color=Color.TEXT_SECONDARY, size=12).pack(side="left")
        
        self._tray_btn_scan = _btn(ctrl, "🔍 Quét Tray", command=self._on_scan_tray)
        self._tray_btn_scan.pack(side="right", padx=(8, 0))

        self._tray_scroll = ctk.CTkScrollableFrame(parent, fg_color=Color.BG_SURFACE, corner_radius=8)
        self._tray_scroll.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 12))
        self._tray_scroll.grid_columnconfigure(0, weight=1)
        
        self._tray_placeholder = _label(self._tray_scroll, "Nhấn \"Quét Tray\" để bắt đầu", color=Color.TEXT_MUTED, size=13)
        self._tray_placeholder.grid(row=0, column=0, pady=40)

    def _on_scan_tray(self) -> None:
        self._tray_btn_scan.configure(state="disabled", text="⏳ Đang quét...")
        for child in self._tray_scroll.winfo_children(): child.destroy()
        
        def worker():
            from core.tray_explorer import TrayExplorer
            try:
                tray_dir = self._config.tray_directory
                mods_dir = self._config.mod_directory
                if not tray_dir or not mods_dir:
                    self.after(0, lambda: _label(self._tray_scroll, "Thư mục không hợp lệ", color=Color.ERROR).pack())
                    return
                
                results = TrayExplorer.get_cc_for_tray_item(tray_dir, mods_dir)
                self.after(0, lambda: self._render_tray(results))
            except Exception as e:
                logger.error(f"Lỗi quét Tray: {e}")
            finally:
                self.after(0, lambda: self._tray_btn_scan.configure(state="normal", text="🔍 Quét Tray"))
                
        threading.Thread(target=worker, daemon=True).start()

    def _render_tray(self, results: dict) -> None:
        if not results:
            _label(self._tray_scroll, "Không tìm thấy file liên kết", color=Color.TEXT_MUTED).pack(pady=40)
            return
            
        for prefix, mods in results.items():
            card = _card(self._tray_scroll)
            card.pack(fill="x", pady=6)
            _label(card, f"📂 Household/Room: {prefix}", size=14, weight="bold").pack(anchor="w", padx=12, pady=(12, 4))
            _label(card, f"Sử dụng {len(mods)} mod", size=12, color=Color.TEXT_SECONDARY).pack(anchor="w", padx=12, pady=(0, 8))
            
            for m in mods:
                _label(card, f" • {os.path.basename(m)}", size=11, color=Color.TEXT_PRIMARY).pack(anchor="w", padx=24, pady=2)
            ctk.CTkFrame(card, height=8, fg_color="transparent").pack()

    # ── Tab 5: Orphan Mesh Scanner ────────────────────────────────────────────
    
    def _build_orphan_tab(self, parent) -> None:
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        ctrl = ctk.CTkFrame(parent, fg_color="transparent")
        ctrl.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 8))
        _label(ctrl, "Tìm file Mod recolor bị tàng hình do thiếu Mesh gốc", color=Color.TEXT_SECONDARY, size=12).pack(side="left")
        
        self._orphan_btn_scan = _btn(ctrl, "👻 Quét Missing Mesh", command=self._on_scan_orphan)
        self._orphan_btn_scan.pack(side="right", padx=(8, 0))

        self._orphan_scroll = ctk.CTkScrollableFrame(parent, fg_color=Color.BG_SURFACE, corner_radius=8)
        self._orphan_scroll.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 12))
        self._orphan_scroll.grid_columnconfigure(0, weight=1)
        
        self._orphan_placeholder = _label(self._orphan_scroll, "Nhấn \"Quét Missing Mesh\" để bắt đầu", color=Color.TEXT_MUTED, size=13)
        self._orphan_placeholder.grid(row=0, column=0, pady=40)

    def _on_scan_orphan(self) -> None:
        self._orphan_btn_scan.configure(state="disabled", text="⏳ Đang quét...")
        for child in self._orphan_scroll.winfo_children(): child.destroy()
        
        def worker():
            from core.orphan_scanner import OrphanScanner
            try:
                mods_dir = self._config.mod_directory
                if not mods_dir: return
                
                results = OrphanScanner.scan_missing_meshes(mods_dir)
                self.after(0, lambda: self._render_orphan(results))
            except Exception as e:
                logger.error(f"Lỗi quét Orphan: {e}")
            finally:
                self.after(0, lambda: self._orphan_btn_scan.configure(state="normal", text="👻 Quét Missing Mesh"))
                
        threading.Thread(target=worker, daemon=True).start()

    def _render_orphan(self, results: list) -> None:
        if not results:
            _label(self._orphan_scroll, "🎉 Tuyệt vời! Không có file nào bị thiếu Mesh", color=Color.SUCCESS).pack(pady=40)
            return
            
        _label(self._orphan_scroll, f"Cảnh báo: Phát hiện {len(results)} file có nguy cơ bị tàng hình!", color=Color.ERROR, size=14, weight="bold").pack(anchor="w", pady=10)
        
        for p in results:
            card = _card(self._orphan_scroll)
            card.pack(fill="x", pady=4)
            _label(card, f"📄 {os.path.basename(p)}", size=13, weight="bold").pack(anchor="w", padx=12, pady=(10, 4))
            _label(card, f"Đường dẫn: {p}", size=11, color=Color.TEXT_MUTED).pack(anchor="w", padx=12, pady=(0, 10))
