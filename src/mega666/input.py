"""Key-input simulation for a background game window.

Uses ``PostMessage`` so the window does **not** need to be in the foreground.
"""

import ctypes
import time

WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202

MK_LBUTTON = 0x0001

VK_SPACE = 0x20
VK_RETURN = 0x0D
VK_ESCAPE = 0x1B
VK_LEFT = 0x25
VK_DOWN = 0x28
VK_RIGHT = 0x27
VK_E = 0x45  # used by some Forza versions

user32 = ctypes.windll.user32


def _send_key(hwnd: int, vk_code: int) -> None:
    """Post a key-down + key-up message pair to *hwnd*."""
    user32.PostMessageW(hwnd, WM_KEYDOWN, vk_code, 0)
    time.sleep(0.05)
    user32.PostMessageW(hwnd, WM_KEYUP, vk_code, 0)


def _client_lparam(x: int, y: int) -> int:
    """Pack client coordinates into a Windows mouse-message LPARAM."""
    return (int(y) & 0xFFFF) << 16 | (int(x) & 0xFFFF)


def low_level_click_client(hwnd: int, x: int, y: int) -> None:
    """Post a client-area left click to *hwnd* without moving the user cursor."""
    lparam = _client_lparam(x, y)
    user32.PostMessageW(hwnd, WM_MOUSEMOVE, 0, lparam)
    time.sleep(0.05)
    user32.PostMessageW(hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lparam)
    time.sleep(0.05)
    user32.PostMessageW(hwnd, WM_LBUTTONUP, 0, lparam)


def press_space(hwnd: int) -> None:
    """Send Space (VK_SPACE) to *hwnd*."""
    _send_key(hwnd, VK_SPACE)


def press_enter(hwnd: int) -> None:
    """Send Enter (VK_RETURN) to *hwnd*."""
    _send_key(hwnd, VK_RETURN)


def press_left(hwnd: int) -> None:
    """Send Left Arrow (VK_LEFT) to *hwnd*."""
    _send_key(hwnd, VK_LEFT)


def press_down(hwnd: int) -> None:
    """Send Down Arrow (VK_DOWN) to *hwnd*."""
    _send_key(hwnd, VK_DOWN)


def press_right(hwnd: int) -> None:
    """Send Right Arrow (VK_RIGHT) to *hwnd*."""
    _send_key(hwnd, VK_RIGHT)


def press_e(hwnd: int) -> None:
    """Send the E key to *hwnd*."""
    _send_key(hwnd, VK_E)


def press_escape(hwnd: int) -> None:
    """Send Escape (VK_ESCAPE) to *hwnd*."""
    _send_key(hwnd, VK_ESCAPE)
