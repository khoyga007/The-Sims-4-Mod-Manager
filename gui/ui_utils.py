"""
UI Utilities — Các thành phần giao diện dùng chung cho toàn bộ ứng dụng.
Đảm bảo tính nhất quán về thẩm mỹ và phong cách code.
"""
from __future__ import annotations
import customtkinter as ctk
from gui._constants import Color

def _card(parent, **kwargs) -> ctk.CTkFrame:
    """Tạo một khung card bo góc tiêu chuẩn."""
    fg = kwargs.pop("fg_color", Color.BG_CARD)
    radius = kwargs.pop("corner_radius", 10)
    return ctk.CTkFrame(parent, fg_color=fg, corner_radius=radius, **kwargs)

def _label(parent, text: str, size: int = 13, weight: str = "normal",
           color: str = Color.TEXT_PRIMARY, **kwargs) -> ctk.CTkLabel:
    """Tạo nhãn chữ với font và màu sắc tiêu chuẩn."""
    txt_color = kwargs.pop("text_color", color)
    return ctk.CTkLabel(
        parent, text=text,
        font=ctk.CTkFont(size=size, weight=weight),
        text_color=txt_color, **kwargs,
    )

def _btn(parent, text: str, command=None, color: str = Color.ACCENT,
         hover: str = Color.ACCENT_HOVER, width: int = 140,
         **kwargs) -> ctk.CTkButton:
    """Tạo nút bấm với phong cách tiêu chuẩn."""
    return ctk.CTkButton(
        parent, text=text, command=command,
        fg_color=color, hover_color=hover,
        font=ctk.CTkFont(size=13, weight="bold"),
        corner_radius=8, width=width, height=34,
        **kwargs,
    )

def _severity_color(severity: str) -> str:
    """Trả về màu sắc tương ứng với mức độ nghiêm trọng."""
    return {
        "CRITICAL": Color.ERROR,
        "WARNING":  Color.WARNING,
        "INFO":     Color.INFO,
    }.get(severity, Color.TEXT_SECONDARY)
