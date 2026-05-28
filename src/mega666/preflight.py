"""Preflight checks — verify process + environment before scanning."""

import ctypes
import ctypes.wintypes

import psutil
import win32gui

from mega666.ui import preflight_row, preflight_summary, section


def check_process_running(process_names: list[str]) -> bool:
    """Return True if at least one *process_names* is running (exact .exe match)."""
    names_lower = {n.lower() for n in process_names}
    for proc in psutil.process_iter(["name"]):
        try:
            name = proc.info["name"]
            if name and name.lower() in names_lower:
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return False


def preflight(process_names: list[str]) -> bool:
    """Run all preflight checks.

    Returns True if everything is ready, False otherwise.
    Callers should abort the scan when this returns False.
    """
    section("Preflight", "validating capture stack")
    ok_status = True

    # ── 1. Process existence ─────────────────────────────────────────────
    proc_found = check_process_running(process_names)
    if not proc_found:
        names = ", ".join(process_names)
        preflight_row("Target process", "fail", f"not found; searched for {names}")
        preflight_row("Launch hint", "warn", "start Forza Horizon 6 before scanning")
        ok_status = False
    else:
        preflight_row("Target process", "ok", "running and visible to psutil")

    # ── 2. Win32 / GDI accessibility ─────────────────────────────────────
    try:
        hwnd = win32gui.GetDesktopWindow()
        rect = win32gui.GetWindowRect(hwnd)
        if rect[2] > 0 and rect[3] > 0:
            preflight_row("Win32 desktop", "ok", "GDI capture surface is accessible")
        else:
            preflight_row("Win32 desktop", "warn", "desktop has zero size; capture may fail")
    except Exception as e:
        preflight_row("Win32 desktop", "fail", f"API error: {e}")
        ok_status = False

    # ── 3. GDI / User32 library load (warmup) ───────────────────────────
    try:
        _ = ctypes.windll.user32
        _ = ctypes.windll.gdi32
        preflight_row("System libraries", "ok", "User32 and GDI32 are loaded")
    except Exception as e:
        preflight_row("System libraries", "fail", f"load failed: {e}")
        ok_status = False

    preflight_summary(ok_status)

    return ok_status
