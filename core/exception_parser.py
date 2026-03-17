"""
Exception Parser — Đọc và phân tích file LastException.txt của The Sims 4.

Tự động tìm file, trích xuất mod liên quan, loại lỗi và stack trace
theo định dạng dễ đọc cho người dùng không phải lập trình viên.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("ModManager.ExceptionParser")

# ─── Đường dẫn mặc định của TS4 ──────────────────────────────────────────────

_TS4_DOCS_PATHS = (
    Path.home() / "Documents" / "Electronic Arts" / "The Sims 4",
    Path("D:/") / "Electronic Arts" / "The Sims 4",
    Path("C:/Users") / os.environ.get("USERNAME", "") / "Documents" / "Electronic Arts" / "The Sims 4",
)

_EXCEPTION_FILENAME = "LastException.txt"
_EXCEPTION_GLOB = "LastException*.txt"

# ─── Known error patterns ─────────────────────────────────────────────────────

_ERROR_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    # (regex khớp với exception message, nhãn ngắn, giải thích thân thiện)
    (re.compile(r"AttributeError.*NilDescriptor", re.I),
     "NilDescriptor", "Mod dùng tính năng game bị xóa/đổi tên"),
    (re.compile(r"ImportError|ModuleNotFoundError", re.I),
     "Import thất bại", "Mod thiếu file hoặc cài đặt không đúng"),
    (re.compile(r"TypeError.*argument", re.I),
     "Sai tham số", "Mod không tương thích với phiên bản game hiện tại"),
    (re.compile(r"KeyError", re.I),
     "Key không tồn tại", "Mod tham chiếu đến dữ liệu đã bị xóa"),
    (re.compile(r"AttributeError", re.I),
     "Thuộc tính không tồn tại", "Mod dùng API game đã thay đổi"),
    (re.compile(r"NameError", re.I),
     "Tên không tồn tại", "Lỗi code trong mod — biến/hàm không được định nghĩa"),
    (re.compile(r"RuntimeError", re.I),
     "Runtime Error", "Lỗi xảy ra trong lúc chạy, thường do xung đột"),
    (re.compile(r"IndexError|list index out of range", re.I),
     "Index lỗi", "Mod đọc dữ liệu từ danh sách rỗng hoặc sai vị trí"),
    (re.compile(r"RecursionError|maximum recursion", re.I),
     "Vòng lặp vô hạn", "Mod gây ra vòng lặp đệ quy vô hạn"),
    (re.compile(r"MemoryError", re.I),
     "Hết bộ nhớ", "Mod tiêu thụ quá nhiều RAM"),
]

# ─── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class ModMention:
    """Thông tin về một mod được đề cập trong stack trace.

    Attributes
    ----------
    mod_name:
        Tên mod (tên folder hoặc file .ts4script).
    file_in_mod:
        File Python bên trong mod (ví dụ: ``module/handler.pyc``).
    line_number:
        Số dòng xảy ra lỗi.
    code_context:
        Dòng code tại điểm lỗi.
    """
    mod_name: str
    file_in_mod: str
    line_number: int
    code_context: str = ""


@dataclass
class ParsedError:
    """Kết quả phân tích một file LastException.

    Attributes
    ----------
    source_file:
        Đường dẫn file LastException.txt đã đọc.
    exception_type:
        Loại exception (ví dụ: ``AttributeError``).
    exception_message:
        Thông điệp lỗi đầy đủ.
    error_label:
        Nhãn ngắn thân thiện.
    explanation:
        Giải thích nguyên nhân bằng tiếng Việt.
    mods_involved:
        Danh sách mod xuất hiện trong stack trace.
    raw_lines:
        Toàn bộ nội dung file gốc (đã strip HTML tags).
    game_version:
        Phiên bản game nếu có trong file.
    """
    source_file: str
    exception_type: str
    exception_message: str
    error_label: str
    explanation: str
    mods_involved: list[ModMention] = field(default_factory=list)
    raw_lines: list[str] = field(default_factory=list)
    game_version: str = ""

    @property
    def primary_mod(self) -> Optional[ModMention]:
        """Mod đầu tiên trong stack trace — thường là thủ phạm."""
        return self.mods_involved[0] if self.mods_involved else None

    @property
    def summary(self) -> str:
        """Tóm tắt 1 dòng cho UI."""
        if self.primary_mod:
            return (
                f"[{self.error_label}] {self.exception_type} "
                f"← {self.primary_mod.mod_name}"
            )
        return f"[{self.error_label}] {self.exception_type}"


# ─── Parser ───────────────────────────────────────────────────────────────────

class ExceptionParser:
    """Tìm và phân tích file LastException.txt.

    Parameters
    ----------
    ts4_docs_dir:
        Thư mục tài liệu TS4. ``None`` → tự động tìm.
    """

    def __init__(self, ts4_docs_dir: Optional[str] = None) -> None:
        if ts4_docs_dir:
            self._ts4_dir = Path(ts4_docs_dir)
        else:
            self._ts4_dir = self._find_ts4_dir()

    # ─────────────────────────────────────────────────────────────────────────
    # Public
    # ─────────────────────────────────────────────────────────────────────────

    def find_exception_files(self) -> list[Path]:
        """Tìm tất cả file LastException*.txt trong thư mục TS4.

        Returns
        -------
        list[Path]
            Danh sách đường dẫn, mới nhất đầu tiên.
        """
        if not self._ts4_dir or not self._ts4_dir.exists():
            logger.warning(f"Không tìm thấy thư mục TS4: {self._ts4_dir}")
            return []

        files = list(self._ts4_dir.glob(_EXCEPTION_GLOB))
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        logger.info(f"Tìm thấy {len(files)} file exception")
        return files

    def parse_file(self, filepath: str | Path) -> Optional[ParsedError]:
        """Phân tích một file LastException.txt.

        Parameters
        ----------
        filepath:
            Đường dẫn đến file.

        Returns
        -------
        ParsedError | None
            Kết quả phân tích, hoặc ``None`` nếu file rỗng/không đọc được.
        """
        try:
            text = Path(filepath).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            logger.error(f"Không đọc được {filepath}: {exc}")
            return None

        lines = self._strip_html(text).splitlines()
        lines = [ln for ln in lines if ln.strip()]

        if not lines:
            return None

        exc_type, exc_msg = self._extract_exception(lines)
        label, explanation = self._classify_error(exc_type + " " + exc_msg)
        mods = self._extract_mods(lines)
        version = self._extract_version(lines)

        return ParsedError(
            source_file=str(filepath),
            exception_type=exc_type,
            exception_message=exc_msg,
            error_label=label,
            explanation=explanation,
            mods_involved=mods,
            raw_lines=lines,
            game_version=version,
        )

    def parse_latest(self) -> Optional[ParsedError]:
        """Phân tích file LastException mới nhất.

        Returns
        -------
        ParsedError | None
        """
        files = self.find_exception_files()
        if not files:
            logger.info("Không tìm thấy file LastException.txt")
            return None
        return self.parse_file(files[0])

    def parse_all(self) -> list[ParsedError]:
        """Phân tích tất cả file LastException tìm được.

        Returns
        -------
        list[ParsedError]
            Danh sách kết quả, mới nhất đầu tiên.
        """
        results = []
        for path in self.find_exception_files():
            parsed = self.parse_file(path)
            if parsed:
                results.append(parsed)
        return results

    @property
    def ts4_dir(self) -> Optional[Path]:
        """Thư mục TS4 đang dùng."""
        return self._ts4_dir

    @ts4_dir.setter
    def ts4_dir(self, path: str) -> None:
        self._ts4_dir = Path(path)

    # ─────────────────────────────────────────────────────────────────────────
    # Internal
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _find_ts4_dir() -> Optional[Path]:
        """Tự động tìm thư mục TS4."""
        for p in _TS4_DOCS_PATHS:
            if p.exists():
                logger.info(f"Tìm thấy thư mục TS4: {p}")
                return p
        # Tìm trong tất cả ổ đĩa Windows
        for drive in "CDEFGH":
            p = Path(f"{drive}:/") / "Electronic Arts" / "The Sims 4"
            if p.exists():
                return p
        return None

    @staticmethod
    def _strip_html(text: str) -> str:
        """Xóa HTML tags (TS4 đôi khi dùng <br> trong LastException)."""
        text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
        text = re.sub(r"<[^>]+>", "", text)
        return text

    @staticmethod
    def _extract_exception(lines: list[str]) -> tuple[str, str]:
        """Tìm loại exception và message từ cuối file.

        Returns
        -------
        tuple[str, str]
            (exception_type, full_message)
        """
        # Exception thường ở cuối file, dạng "ExcType: message"
        exc_pattern = re.compile(
            r"^([A-Za-z][A-Za-z0-9]*(?:Error|Exception|Warning|Interrupt))"
            r"(?::\s*(.+))?$"
        )
        # Tìm từ cuối lên
        for line in reversed(lines):
            m = exc_pattern.match(line.strip())
            if m:
                exc_type = m.group(1)
                exc_msg  = m.group(2) or ""
                return exc_type, exc_msg.strip()

        # Fallback: dùng dòng cuối
        return "UnknownError", lines[-1].strip() if lines else ""

    @staticmethod
    def _classify_error(text: str) -> tuple[str, str]:
        """Phân loại lỗi thành nhãn và giải thích thân thiện."""
        for pattern, label, explanation in _ERROR_PATTERNS:
            if pattern.search(text):
                return label, explanation
        return "Lỗi Script", "Lỗi Python không xác định trong mod"

    @staticmethod
    def _extract_mods(lines: list[str]) -> list[ModMention]:
        """Trích xuất tên mod từ stack trace.

        TS4 ghi đường dẫn dạng:
        ``...\\Mods\\FolderName\\mod.ts4script\\module\\file.pyc``
        """
        mods: list[ModMention] = []
        seen: set[str] = set()

        # Pattern cho đường dẫn trong Mods folder
        mod_re = re.compile(
            r'File\s+"(?:[^"]*[/\\]Mods[/\\]([^/\\"]+)[/\\][^"]*\.ts4script[/\\]([^"]+))"'
            r'(?:.*?line\s+(\d+))?',
            re.I,
        )
        # Pattern cho .ts4script trực tiếp (không trong subfolder)
        ts4_re = re.compile(
            r'File\s+"(?:[^"]*[/\\]Mods[/\\])([^"]+\.ts4script)[/\\]([^"]+)"'
            r'(?:.*?line\s+(\d+))?',
            re.I,
        )

        for i, line in enumerate(lines):
            for pattern in (mod_re, ts4_re):
                m = pattern.search(line)
                if m:
                    mod_name = m.group(1).strip()
                    file_in  = m.group(2).strip() if m.group(2) else ""
                    lineno   = int(m.group(3)) if m.group(3) else 0
                    # Lấy dòng code kế tiếp nếu có
                    ctx = lines[i + 1].strip() if i + 1 < len(lines) else ""

                    key = f"{mod_name}::{file_in}"
                    if key not in seen:
                        seen.add(key)
                        mods.append(ModMention(
                            mod_name=mod_name,
                            file_in_mod=file_in,
                            line_number=lineno,
                            code_context=ctx,
                        ))
                    break

        # Nếu không parse được đường dẫn, tìm pattern đơn giản hơn
        if not mods:
            simple_re = re.compile(
                r'[/\\]Mods[/\\]([^/\\"]+(?:\.ts4script|\.package))',
                re.I,
            )
            for line in lines:
                m = simple_re.search(line)
                if m:
                    mod_name = m.group(1)
                    if mod_name not in seen:
                        seen.add(mod_name)
                        mods.append(ModMention(
                            mod_name=mod_name,
                            file_in_mod="",
                            line_number=0,
                        ))

        return mods

    @staticmethod
    def _extract_version(lines: list[str]) -> str:
        """Tìm phiên bản game trong file."""
        ver_re = re.compile(r"Version\s*[:=]\s*([0-9.]+)", re.I)
        for line in lines[:30]:  # Thường ở đầu file
            m = ver_re.search(line)
            if m:
                return m.group(1)
        return ""
