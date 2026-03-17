"""
TSR Downloader — Tích hợp tải từ The Sims Resource.

Hỗ trợ batch parallel:
    lấy ticket hàng loạt → chờ 10s 1 lần → tải song song.
"""
from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Callable, Optional

import requests


from ._http_utils import stream_to_file

logger = logging.getLogger("ModManager.TSR")


# ─── Exceptions ───────────────────────────────────────────────────────────────

class TSRError(Exception):
    """Lỗi chung từ API TSR."""


class InvalidURL(TSRError):
    """URL không phải link TSR hợp lệ."""
    def __init__(self, url: str) -> None:
        self.url = url
        super().__init__(f"URL TSR không hợp lệ: {url}")


class InvalidCaptchaCode(TSRError):
    """Mã captcha sai."""


class InvalidDownloadTicket(TSRError):
    """Ticket tải xuống không hợp lệ."""


# ─── TSRItem ──────────────────────────────────────────────────────────────────

@dataclass
class TSRItem:
    """Thông tin một item trên The Sims Resource.

    Attributes
    ----------
    url:
        URL trang item gốc.
    item_id:
        ID số học của item.
    download_url:
        URL tải xuống trực tiếp.
    is_vip:
        ``True`` nếu item yêu cầu tài khoản VIP.
    """

    url: str
    item_id: int
    download_url: str
    is_vip: bool = False

    # Regex để tìm item ID trong URL
    _ID_PATTERNS = (
        re.compile(r"(?<=/id/)(\d+)"),
        re.compile(r"(?<=/itemId/)(\d+)"),
        re.compile(r"(?<=\.com/downloads/)(\d+)"),
    )

    @classmethod
    def from_url(cls, url: str) -> "TSRItem":
        """Parse URL TSR để tạo TSRItem.

        Parameters
        ----------
        url:
            URL trang item TSR.

        Raises
        ------
        InvalidURL
            Nếu URL không chứa item_id hoặc không phải domain TSR.
        """
        if "thesimsresource.com" not in url:
            raise InvalidURL(url)

        item_id_str: Optional[str] = None
        for pattern in cls._ID_PATTERNS:
            m = pattern.search(url)
            if m:
                item_id_str = m.group(1)
                break

        if not item_id_str:
            raise InvalidURL(url)

        iid = int(item_id_str)
        return cls(
            url=url,
            item_id=iid,
            download_url=f"https://www.thesimsresource.com/downloads/download/itemId/{iid}",
        )

    @staticmethod
    def is_valid_url(url: str) -> bool:
        """Kiểm tra URL có phải link TSR hợp lệ không."""
        try:
            TSRItem.from_url(url)
            return True
        except (InvalidURL, Exception):
            return False


# ─── TSRSession ───────────────────────────────────────────────────────────────

class TSRSession:
    """Quản lý phiên TSR: lấy captcha và gửi mã để nhận session cookie.

    Session được lưu vào file ``.tsr_session`` cạnh thư mục ``core/``
    để tái sử dụng giữa các lần chạy.
    """

    _SESSION_FILENAME = ".tsr_session"

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session_id: Optional[str] = None
        self._session_file = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..",
            self._SESSION_FILENAME,
        )

    def load_session(self) -> bool:
        """Tải session đã lưu từ lần chạy trước.

        Returns
        -------
        bool
            ``True`` nếu tải thành công và session_id không rỗng.
        """
        if not os.path.exists(self._session_file):
            return False
        try:
            with open(self._session_file, "r", encoding="utf-8") as f:
                sid = f.read().strip()
            if sid:
                self.session_id = sid
                logger.info("Session TSR cũ đã được tải")
                return True
        except OSError:
            pass
        self.session_id = None
        return False

    def save_session(self) -> None:
        """Lưu session_id hiện tại xuống file."""
        if not self.session_id:
            return
        try:
            with open(self._session_file, "w", encoding="utf-8") as f:
                f.write(self.session_id)
        except OSError as exc:
            logger.warning(f"Không thể lưu TSR session: {exc}")

    def get_captcha_image(self) -> Optional[bytes]:
        """Lấy ảnh captcha từ TSR để hiển thị trên GUI.

        Returns
        -------
        bytes | None
            Dữ liệu ảnh PNG/JPEG, hoặc ``None`` nếu thất bại.
        """
        _ITEM_ID = "1646133"
        try:
            self.session.get(
                f"https://www.thesimsresource.com/ajax.php"
                f"?c=downloads&a=initDownload&itemid={_ITEM_ID}&setItems=&format=zip",
                timeout=10,
            )
            self.session.get(
                f"https://www.thesimsresource.com/downloads/session/itemId/{_ITEM_ID}",
                timeout=10,
            )
            r = self.session.get(
                "https://www.thesimsresource.com/downloads/captcha-image",
                timeout=10,
            )
            return r.content if r.content else None
        except Exception as exc:
            logger.error(f"Lỗi lấy captcha: {exc}")
            return None

    def submit_captcha(self, code: str) -> bool:
        """Gửi mã captcha và nhận session cookie.

        Parameters
        ----------
        code:
            Chuỗi mã người dùng nhập từ ảnh captcha.

        Returns
        -------
        bool
            ``True`` nếu mã đúng và session được tạo thành công.
        """
        _ITEM_ID = "1646133"
        try:
            r = self.session.post(
                f"https://www.thesimsresource.com/downloads/session/itemId/{_ITEM_ID}",
                data={"captchavalue": code},
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Origin": "https://www.thesimsresource.com",
                },
                allow_redirects=True,
                timeout=15,
            )
            expected_url = (
                f"https://www.thesimsresource.com/downloads/download/itemId/{_ITEM_ID}"
            )
            if r.url == expected_url:
                self.session_id = self.session.cookies.get_dict().get("tsrdlsession")
                self.save_session()
                logger.info("✅ Captcha đúng, session TSR đã được tạo")
                return True
        except Exception as exc:
            logger.error(f"Lỗi gửi captcha: {exc}")
        return False


# ─── TSRTicket ────────────────────────────────────────────────────────────────

@dataclass
class TSRTicket:
    """Ticket đã được fetch cho một item — sẵn sàng tải sau ``WAIT_SECONDS``.

    Attributes
    ----------
    item:
        Item TSR tương ứng.
    session:
        Session requests đã có cookie ticket.
    ticket_time:
        Timestamp (ms) khi fetch ticket.
    """

    item: TSRItem
    session: requests.Session
    ticket_time: float


# ─── TSRDownloader ────────────────────────────────────────────────────────────

class TSRDownloader:
    """Tải item từ TSR — hỗ trợ batch parallel download.

    Parameters
    ----------
    tsr_session:
        Instance :class:`TSRSession` đang hoạt động.
    """

    #: Thời gian tối thiểu chờ sau khi lấy ticket (giây)
    WAIT_SECONDS = 10

    def __init__(self, tsr_session: TSRSession) -> None:
        self._session = tsr_session

    def fetch_ticket(self, item: TSRItem) -> Optional[TSRTicket]:
        """Lấy ticket cho một item (bước 1 của batch download).

        Gọi hàm này song song cho nhiều item, sau đó chờ :attr:`WAIT_SECONDS`
        rồi gọi :meth:`download_with_ticket`.

        Parameters
        ----------
        item:
            Item TSR cần lấy ticket.

        Returns
        -------
        TSRTicket | None
            Ticket sẵn sàng tải, hoặc ``None`` nếu thất bại.
        """
        session = requests.Session()
        if self._session.session_id:
            session.cookies.set("tsrdlsession", self._session.session_id)

        try:
            session.get(
                f"https://www.thesimsresource.com/ajax.php"
                f"?c=downloads&a=initDownload&itemid={item.item_id}&format=zip",
                timeout=10,
            )
            session.get(item.download_url, timeout=10)
            logger.info(f"🎫 Ticket cho item {item.item_id}")
            return TSRTicket(item=item, session=session, ticket_time=time.time() * 1000)
        except Exception as exc:
            logger.error(f"❌ Lỗi fetch ticket {item.item_id}: {exc}")
            return None

    def download_with_ticket(
        self,
        ticket: TSRTicket,
        download_path: str,
        progress_callback: Optional[Callable[[float, float], None]] = None,
    ) -> Optional[str]:
        """Tải file dùng ticket đã fetch (bước 2 của batch download).

        Tự chờ nếu chưa đủ :attr:`WAIT_SECONDS`.

        Parameters
        ----------
        ticket:
            Ticket đã lấy được từ :meth:`fetch_ticket`.
        download_path:
            Thư mục lưu file.
        progress_callback:
            Callback tiến trình ``[0.0, 1.0]``.

        Returns
        -------
        str | None
            Đường dẫn file đã tải, hoặc ``None`` nếu thất bại.
        """
        item    = ticket.item
        session = ticket.session

        # Chờ nếu chưa đủ WAIT_SECONDS
        elapsed_ms  = time.time() * 1000 - ticket.ticket_time
        remaining_s = max(0.0, self.WAIT_SECONDS - elapsed_ms / 1000)
        if remaining_s > 0:
            logger.info(f"⏳ Chờ {remaining_s:.1f}s cho item {item.item_id}")
            time.sleep(remaining_s)

        try:
            # Lấy URL tải thực
            r = session.get(
                f"https://www.thesimsresource.com/ajax.php"
                f"?c=downloads&a=getdownloadurl&ajax=1&itemid={item.item_id}&mid=0&lk=0",
                timeout=10,
            )
            data = r.json()
            if data.get("error", ""):
                raise TSRError(f"TSR API error: {data['error']}")
            download_url: str = data["url"]

            # Lấy tên file từ HEAD request
            head = requests.get(download_url, stream=True, timeout=10)
            content_disp = head.headers.get("Content-Disposition", "")
            match = re.search(r'(?<=filename=").+(?=")', content_disp)
            filename = (
                re.sub(r'[\\<>/:|?*]', "", match[0])
                if match
                else f"tsr_{item.item_id}.zip"
            )
            head.close()

            # Tải file
            filepath  = os.path.join(download_path, filename)
            part_path = filepath + ".part"

            dl = session.get(download_url, stream=True, timeout=30)
            downloaded = stream_to_file(dl, part_path, progress_callback)
            dl.close()

            # Rename .part → file thực
            if os.path.exists(filepath):
                os.replace(part_path, filepath)
            else:
                os.rename(part_path, filepath)

            if progress_callback:
                progress_callback(1.0, 0.0)
            logger.info(f"✅ Tải xong TSR: {filename}")
            return filepath

        except Exception as exc:
            logger.error(f"❌ Lỗi tải TSR item {item.item_id}: {exc}")
            return None

    def download(
        self,
        item: TSRItem,
        download_path: str,
        progress_callback: Optional[Callable[[float, float], None]] = None,
    ) -> Optional[str]:
        """Tải tuần tự (fallback) — lấy ticket → chờ → tải.

        Parameters
        ----------
        item:
            Item TSR cần tải.
        download_path:
            Thư mục lưu file.
        progress_callback:
            Callback tiến trình ``[0.0, 1.0]``.
        """
        ticket = self.fetch_ticket(item)
        if not ticket:
            return None
        return self.download_with_ticket(ticket, download_path, progress_callback)
