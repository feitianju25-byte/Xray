from __future__ import annotations

import ctypes
from ctypes import wintypes
from pathlib import Path
from tempfile import gettempdir

from .contract import FrameImage


user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

SRCCOPY = 0x00CC0020
BI_RGB = 0
DIB_RGB_COLORS = 0


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [
        ("bmiHeader", BITMAPINFOHEADER),
        ("bmiColors", wintypes.DWORD * 3),
    ]


def _capture_screen_win32() -> FrameImage:
    width = user32.GetSystemMetrics(0)
    height = user32.GetSystemMetrics(1)
    if width <= 0 or height <= 0:
        raise RuntimeError("Unable to resolve screen size.")

    hdesktop = user32.GetDesktopWindow()
    hdc_screen = user32.GetWindowDC(hdesktop)
    if not hdc_screen:
        raise RuntimeError("Unable to get screen device context.")

    hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
    hbitmap = gdi32.CreateCompatibleBitmap(hdc_screen, width, height)
    if not hdc_mem or not hbitmap:
        user32.ReleaseDC(hdesktop, hdc_screen)
        raise RuntimeError("Unable to create capture bitmap.")

    old_bitmap = gdi32.SelectObject(hdc_mem, hbitmap)
    try:
        if not gdi32.BitBlt(hdc_mem, 0, 0, width, height, hdc_screen, 0, 0, SRCCOPY):
            raise RuntimeError("Screen copy failed.")

        header = BITMAPINFOHEADER()
        header.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        header.biWidth = width
        header.biHeight = -height
        header.biPlanes = 1
        header.biBitCount = 32
        header.biCompression = BI_RGB
        header.biSizeImage = width * height * 4

        bmi = BITMAPINFO()
        bmi.bmiHeader = header

        buffer = (ctypes.c_ubyte * (width * height * 4))()
        bits = gdi32.GetDIBits(
            hdc_mem,
            hbitmap,
            0,
            height,
            ctypes.byref(buffer),
            ctypes.byref(bmi),
            DIB_RGB_COLORS,
        )
        if bits == 0:
            raise RuntimeError("Unable to read bitmap pixels.")

        rgb = bytearray()
        for i in range(0, len(buffer), 4):
            rgb.extend((buffer[i + 2], buffer[i + 1], buffer[i]))

        return FrameImage(width=width, height=height, rgb_bytes=bytes(rgb))
    finally:
        gdi32.SelectObject(hdc_mem, old_bitmap)
        gdi32.DeleteObject(hbitmap)
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(hdesktop, hdc_screen)


def _fallback_frame(width: int = 1280, height: int = 720) -> FrameImage:
    rgb = bytearray()
    for y in range(height):
        color = b"\x16\x1a\x1f" if (y // 32) % 2 == 0 else b"\x20\x26\x2e"
        rgb.extend(color * width)
    return FrameImage(width=width, height=height, rgb_bytes=bytes(rgb), source="fallback")


def capture_screen() -> FrameImage:
    try:
        return _capture_screen_win32()
    except Exception:
        return _fallback_frame()


def write_frame_to_ppm(frame: FrameImage, path: Path | None = None) -> Path:
    target = path or Path(gettempdir()) / "screen_recognition_preview.ppm"
    header = f"P6\n{frame.width} {frame.height}\n255\n".encode("ascii")
    target.write_bytes(header + frame.rgb_bytes)
    return target
