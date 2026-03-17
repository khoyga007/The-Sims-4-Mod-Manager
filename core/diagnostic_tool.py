"""
Diagnostic Tool — Phương pháp "50/50" tự động để tìm mod gây lỗi.

Thuật toán bisect nhị phân:
1. Chia đống mod thành 2 nửa bằng nhau.
2. Tắt nửa B, giữ nửa A.
3. Người dùng chạy game và báo kết quả.
4. Nếu lỗi còn → thu hẹp sang nửa A.
   Nếu lỗi mất → thu hẹp sang nửa B.
5. Lặp lại cho đến khi còn 1 mod.

Trạng thái được lưu vào file JSON để tiếp tục sau khi restart.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from typing import Optional

logger = logging.getLogger("ModManager.Diagnostic")

_STATE_FILENAME = "diagnostic_state.json"
_DISABLED_SUFFIX = ".disabled"


# ─── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class BisectStep:
    """Một bước trong quá trình bisect.

    Attributes
    ----------
    step_number:
        Số thứ tự (bắt đầu từ 1).
    active_set:
        Danh sách filepath của mods đang bật (đang test).
    disabled_set:
        Danh sách filepath của mods đang tắt.
    total_candidates:
        Tổng số mod đang xem xét (active + disabled).
    bug_in_active:
        ``True`` = lỗi còn trong active_set,
        ``False`` = lỗi ở disabled_set (chưa biết ở bước này).
        ``None`` = chưa báo kết quả.
    """
    step_number:       int
    active_set:        list[str]
    disabled_set:      list[str]
    total_candidates:  int
    bug_in_active:     Optional[bool] = None


@dataclass
class DiagnosticSession:
    """Toàn bộ một phiên chẩn đoán.

    Attributes
    ----------
    session_id:
        Timestamp tạo phiên.
    all_mods:
        Danh sách filepath tất cả mod tham gia.
    steps:
        Lịch sử các bước bisect.
    found_mod:
        Filepath mod thủ phạm khi đã tìm ra.
    is_active:
        ``True`` nếu phiên đang chạy.
    """
    session_id:   str
    all_mods:     list[str]
    steps:        list[BisectStep] = field(default_factory=list)
    found_mod:    Optional[str]    = None
    is_active:    bool             = True

    @property
    def current_step(self) -> Optional[BisectStep]:
        return self.steps[-1] if self.steps else None

    @property
    def steps_taken(self) -> int:
        return len(self.steps)

    @property
    def steps_remaining(self) -> int:
        """Ước tính bước còn lại (log2 của số candidates)."""
        last = self.current_step
        if not last:
            return 0
        import math
        candidates = len(last.active_set) + len(last.disabled_set)
        return max(0, math.ceil(math.log2(max(candidates, 1))))

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "DiagnosticSession":
        steps = [BisectStep(**s) for s in data.get("steps", [])]
        return cls(
            session_id=data["session_id"],
            all_mods=data["all_mods"],
            steps=steps,
            found_mod=data.get("found_mod"),
            is_active=data.get("is_active", False),
        )


# ─── Diagnostic Tool ──────────────────────────────────────────────────────────

class DiagnosticTool:
    """Quản lý phiên chẩn đoán mod 50/50.

    Parameters
    ----------
    mod_directory:
        Thư mục Mods chính.
    state_dir:
        Thư mục lưu file trạng thái. Mặc định = ``mod_directory``.
    """

    def __init__(self, mod_directory: str, state_dir: Optional[str] = None) -> None:
        self._mod_dir   = mod_directory
        self._state_dir = state_dir or os.path.dirname(mod_directory)
        self._state_path = os.path.join(self._state_dir, _STATE_FILENAME)
        self._session: Optional[DiagnosticSession] = None

    # ─────────────────────────────────────────────────────────────────────────
    # Session management
    # ─────────────────────────────────────────────────────────────────────────

    def start_new_session(
        self,
        mod_filepaths: Optional[list[str]] = None,
    ) -> DiagnosticSession:
        """Bắt đầu phiên chẩn đoán mới.

        Nếu đang có phiên cũ, tự động phục hồi tất cả mod trước khi bắt đầu.

        Parameters
        ----------
        mod_filepaths:
            Danh sách filepath của mod cần test.
            ``None`` → tự động lấy tất cả mod đang bật trong mod_directory.

        Returns
        -------
        DiagnosticSession
        """
        # Phục hồi phiên cũ nếu có
        if self._session and self._session.is_active:
            self.restore_all()

        if mod_filepaths is None:
            mod_filepaths = self._find_enabled_mods()

        import time
        session = DiagnosticSession(
            session_id=str(int(time.time())),
            all_mods=mod_filepaths,
            is_active=True,
        )

        # Bước đầu tiên
        active, disabled = self._split(mod_filepaths)
        step = BisectStep(
            step_number=1,
            active_set=active,
            disabled_set=disabled,
            total_candidates=len(mod_filepaths),
        )
        session.steps.append(step)

        self._session = session
        self._apply_step(step)
        self._save_state()

        logger.info(
            f"Phiên mới: {len(mod_filepaths)} mod → "
            f"bật {len(active)}, tắt {len(disabled)}"
        )
        return session

    def report_result(self, bug_present: bool) -> Optional[DiagnosticSession]:
        """Người dùng báo kết quả sau khi chạy game.

        Parameters
        ----------
        bug_present:
            ``True`` nếu lỗi vẫn còn (mod thủ phạm nằm trong active_set).
            ``False`` nếu lỗi đã mất (mod thủ phạm nằm trong disabled_set).

        Returns
        -------
        DiagnosticSession
            Session sau khi cập nhật (có thể đã tìm ra ``found_mod``).
        """
        if not self._session or not self._session.is_active:
            logger.warning("Không có phiên đang chạy")
            return self._session

        current = self._session.current_step
        if not current:
            return self._session

        current.bug_in_active = bug_present

        # Candidates cho bước tiếp theo
        candidates = current.active_set if bug_present else current.disabled_set

        if len(candidates) == 1:
            # Đã tìm ra thủ phạm!
            found = candidates[0]
            self._session.found_mod = found
            self._session.is_active = False
            self.restore_all()
            logger.info(f"✅ Tìm ra mod thủ phạm: {os.path.basename(found)}")
            self._save_state()
            return self._session

        if len(candidates) == 0:
            # Không tìm thấy — có thể lỗi không phải do mod
            self._session.is_active = False
            self.restore_all()
            logger.warning("Không tìm thấy mod thủ phạm — có thể lỗi không phải mod")
            self._save_state()
            return self._session

        # Tạo bước tiếp theo
        active, disabled = self._split(candidates)
        step = BisectStep(
            step_number=current.step_number + 1,
            active_set=active,
            disabled_set=disabled,
            total_candidates=len(candidates),
        )
        self._session.steps.append(step)
        self._apply_step(step, restore_first=True)
        self._save_state()

        logger.info(
            f"Bước {step.step_number}: {len(candidates)} candidates → "
            f"bật {len(active)}, tắt {len(disabled)}"
        )
        return self._session

    def cancel_session(self) -> None:
        """Hủy phiên và phục hồi tất cả mod về trạng thái bật."""
        self.restore_all()
        if self._session:
            self._session.is_active = False
            self._save_state()
        logger.info("Đã hủy phiên chẩn đoán và phục hồi tất cả mod")

    def restore_all(self) -> int:
        """Phục hồi tất cả mod về trạng thái bật.

        Returns
        -------
        int
            Số mod đã bật lại.
        """
        if not self._session:
            return 0

        restored = 0
        # Tối ưu siêu tốc: Thay vì check exists cho 7000 files, nhảy thẳng vào thao tác rename
        # với những file có khả năng bị disable cao nhất (EAFP pattern)
        to_check = set(self._session.all_mods)
        if self._session.current_step:
            to_check = set(self._session.current_step.disabled_set)

        for filepath in to_check:
            disabled_path = filepath + _DISABLED_SUFFIX
            try:
                os.rename(disabled_path, filepath)
                restored += 1
            except OSError:
                pass

        # Quét lại toàn bộ all_mods một lần nữa phòng hờ lọt lưới, 
        # nhưng vẫn giữ EAFP cho tốc độ chớp xoáng
        if restored < len(to_check) and to_check != set(self._session.all_mods):
            for filepath in self._session.all_mods:
                disabled_path = filepath + _DISABLED_SUFFIX
                try:
                    os.rename(disabled_path, filepath)
                    restored += 1
                except OSError:
                    pass

        logger.info(f"Phục hồi {restored} mod")
        return restored


    # ─────────────────────────────────────────────────────────────────────────
    # State persistence
    # ─────────────────────────────────────────────────────────────────────────

    def load_state(self) -> Optional[DiagnosticSession]:
        """Tải phiên đang dở từ file JSON.

        Returns
        -------
        DiagnosticSession | None
        """
        if not os.path.exists(self._state_path):
            return None
        try:
            with open(self._state_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._session = DiagnosticSession.from_dict(data)
            logger.info(f"Tải phiên chẩn đoán: bước {self._session.steps_taken}")
            return self._session
        except Exception as exc:
            logger.error(f"Lỗi tải trạng thái: {exc}")
            return None

    def _save_state(self) -> None:
        if not self._session:
            return
        try:
            with open(self._state_path, "w", encoding="utf-8") as f:
                json.dump(self._session.to_dict(), f, ensure_ascii=False, indent=2)
        except OSError as exc:
            logger.error(f"Không lưu được trạng thái: {exc}")

    # ─────────────────────────────────────────────────────────────────────────
    # Properties
    # ─────────────────────────────────────────────────────────────────────────

    @property
    def session(self) -> Optional[DiagnosticSession]:
        """Phiên chẩn đoán hiện tại."""
        return self._session

    @property
    def has_active_session(self) -> bool:
        return self._session is not None and self._session.is_active

    # ─────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _find_enabled_mods(self) -> list[str]:
        """Lấy danh sách tất cả mod đang bật trong mod_directory."""
        enabled = []
        for root, dirs, files in os.walk(self._mod_dir):
            if "_backup" in root or "__" in root:
                continue
            for filename in files:
                _, ext = os.path.splitext(filename)
                if ext.lower() in {".package", ".ts4script"}:
                    enabled.append(os.path.join(root, filename))
        enabled.sort()
        return enabled

    @staticmethod
    def _split(mods: list[str]) -> tuple[list[str], list[str]]:
        """Chia danh sách mod thành 2 nửa bằng nhau.

        Returns
        -------
        tuple[list[str], list[str]]
            (active_set, disabled_set)
        """
        mid = len(mods) // 2
        return mods[:mid], mods[mid:]

    def _apply_step(
        self,
        step: BisectStep,
        restore_first: bool = False,
    ) -> None:
        """Áp dụng bước bisect: bật active_set, tắt disabled_set.

        Parameters
        ----------
        step:
            Bước cần áp dụng.
        restore_first:
            Nếu ``True``, phục hồi tất cả trước khi áp dụng (transition).
        """
        if restore_first:
            self.restore_all()

        # Bật active set (EAFP)
        for filepath in step.active_set:
            try:
                os.rename(filepath + _DISABLED_SUFFIX, filepath)
            except OSError:
                pass

        # Tắt disabled set (EAFP)
        for filepath in step.disabled_set:
            try:
                os.rename(filepath, filepath + _DISABLED_SUFFIX)
            except OSError:
                pass

