"""Preflight checks — verify process + environment before scanning."""

import ctypes
import ctypes.wintypes
import time

import psutil
import win32gui
from rich.progress import Progress, SpinnerColumn, TextColumn

from mega666.ui import console, preflight_summary


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


def preflight(process_names: list[str], *, verbose: bool = True) -> bool:
    """Run all preflight checks.

    Returns True if everything is ready, False otherwise.
    Callers should abort the scan when this returns False.
    """
    progress = None
    task = None
    if verbose:
        progress = Progress(
            SpinnerColumn("dots12", style="bright_magenta"),
            TextColumn("[bold cyan]{task.description}"),
            console=console,
            transient=True,
        )
        progress.start()
        task = progress.add_task("Checking capture stack", total=None)

    def step(message: str) -> None:
        if progress is not None and task is not None:
            progress.update(task, description=message)
            time.sleep(0.12)

    ok_status = True

    step("Checking target process")
    proc_found = check_process_running(process_names)
    if not proc_found:
        names = ", ".join(process_names)
        if verbose:
            console.print(f"[red]×[/] Target process not found; searched for {names}")
            console.print("[yellow]![/] Start Forza Horizon 6 before scanning")
        ok_status = False

    step("Checking Win32 desktop capture")
    try:
        hwnd = win32gui.GetDesktopWindow()
        rect = win32gui.GetWindowRect(hwnd)
        if rect[2] <= 0 or rect[3] <= 0:
            if verbose:
                console.print("[yellow]![/] Desktop has zero size; capture may fail")
    except Exception as e:
        if verbose:
            console.print(f"[red]×[/] Win32 desktop API error: {e}")
        ok_status = False

    step("Checking system libraries")
    try:
        _ = ctypes.windll.user32
        _ = ctypes.windll.gdi32
    except Exception as e:
        if verbose:
            console.print(f"[red]×[/] System libraries load failed: {e}")
        ok_status = False

    if progress is not None:
        progress.stop()

    if verbose and not ok_status:
        preflight_summary(ok_status)

    return ok_status
