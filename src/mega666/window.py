"""Window discovery, GDI background capture (PrintWindow), and resizing."""

import ctypes
import ctypes.wintypes

import numpy as np
import psutil
import win32gui
import win32process

_cached_win = None


def find_window(target_names: list[str]):
    """Enumerate all visible windows whose process name matches *target_names*."""
    wins = []

    def cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        try:
            p = psutil.Process(pid)
            pn = p.name().lower()
            if any(t in pn for t in target_names):
                title = win32gui.GetWindowText(hwnd)
                if title:
                    rect = win32gui.GetWindowRect(hwnd)
                    if rect[2] > rect[0] and rect[3] > rect[1]:
                        wins.append(
                            {
                                "hwnd": hwnd,
                                "pid": pid,
                                "title": title,
                                "name": p.name(),
                                "rect": rect,
                                "w": rect[2] - rect[0],
                                "h": rect[3] - rect[1],
                            }
                        )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    win32gui.EnumWindows(cb, None)
    return wins[0] if wins else None


def ensure_window(target_names: list[str]):
    """Return the cached window info (refreshing rects), or re-enumerate."""
    global _cached_win
    if _cached_win is not None:
        hwnd = _cached_win["hwnd"]
        if win32gui.IsWindow(hwnd) and win32gui.IsWindowVisible(hwnd):
            rect = win32gui.GetWindowRect(hwnd)
            if rect[2] > rect[0] and rect[3] > rect[1]:
                _cached_win["rect"] = rect
                _cached_win["w"] = rect[2] - rect[0]
                _cached_win["h"] = rect[3] - rect[1]
                return _cached_win
    _cached_win = find_window(target_names)
    return _cached_win


PW_RENDERFULLCONTENT = 2

gdi32 = ctypes.windll.gdi32
user32 = ctypes.windll.user32


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", ctypes.wintypes.DWORD),
        ("biWidth", ctypes.wintypes.LONG),
        ("biHeight", ctypes.wintypes.LONG),
        ("biPlanes", ctypes.wintypes.WORD),
        ("biBitCount", ctypes.wintypes.WORD),
        ("biCompression", ctypes.wintypes.DWORD),
        ("biSizeImage", ctypes.wintypes.DWORD),
        ("biXPelsPerMeter", ctypes.wintypes.LONG),
        ("biYPelsPerMeter", ctypes.wintypes.LONG),
        ("biClrUsed", ctypes.wintypes.DWORD),
        ("biClrImportant", ctypes.wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [
        ("bmiHeader", BITMAPINFOHEADER),
        ("bmiColors", ctypes.wintypes.DWORD * 3),
    ]


def _cleanup_gdi(hwnd, hdc_window, hdc_mem, hbmp):
    gdi32.DeleteObject(hbmp)
    gdi32.DeleteDC(hdc_mem)
    user32.ReleaseDC(hwnd, hdc_window)


def capture_window(hwnd):
    """Return a numpy BGR array of the window client area via PrintWindow.

    Uses ``PW_RENDERFULLCONTENT`` so the game does **not** need to be in
    the foreground.
    """
    left, top, right, bottom = win32gui.GetClientRect(hwnd)
    width = right - left
    height = bottom - top
    if width <= 0 or height <= 0:
        return None

    hdc_window = user32.GetDC(hwnd)
    hdc_mem = gdi32.CreateCompatibleDC(hdc_window)
    hbmp = gdi32.CreateCompatibleBitmap(hdc_window, width, height)
    gdi32.SelectObject(hdc_mem, hbmp)

    ok = user32.PrintWindow(hwnd, hdc_mem, PW_RENDERFULLCONTENT)
    if not ok:
        _cleanup_gdi(hwnd, hdc_window, hdc_mem, hbmp)
        return None

    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = width
    bmi.bmiHeader.biHeight = -height  # top-down
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = 0  # BI_RGB

    buf_size = width * height * 4
    buf = ctypes.create_string_buffer(buf_size)

    ret = gdi32.GetDIBits(hdc_mem, hbmp, 0, height, buf, ctypes.byref(bmi), 0)
    if not ret:
        _cleanup_gdi(hwnd, hdc_window, hdc_mem, hbmp)
        return None

    img = np.frombuffer(buf, dtype=np.uint8).reshape(height, width, 4)
    img = img[..., :3].copy()  # BGRA → BGR
    _cleanup_gdi(hwnd, hdc_window, hdc_mem, hbmp)
    return img


def capture(hwnd):
    """Safe wrapper around :func:`capture_window` (returns None on error)."""
    try:
        return capture_window(hwnd)
    except Exception:
        return None


def crop_bottom(img, fraction: float = 0.2):
    """Return the bottom *fraction* of a numpy BGR image."""
    if img is None:
        return None
    h = img.shape[0]
    cut = int(h * (1 - fraction))
    return img[cut:, :, :].copy()


def resize_window(hwnd, target_w: int, target_h: int) -> bool:
    """MoveWindow to the given dimensions. Returns True on success."""
    try:
        rect = win32gui.GetWindowRect(hwnd)
        x, y = rect[0], rect[1]
        win32gui.MoveWindow(hwnd, x, y, target_w, target_h, True)
        return True
    except Exception:
        return False
