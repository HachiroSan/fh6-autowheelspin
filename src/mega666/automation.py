"""First-phase wheelspin automation helpers."""

from __future__ import annotations

import time

from rich import box
from rich.panel import Panel

from mega666.detect import detect_wheelspins
from mega666.input import low_level_click_client, press_enter, press_left, press_right
from mega666.ocr import ocr_image
from mega666.ui import console, render_wheelspins
from mega666.window import capture


def _find_wheelspin(wheelspins: list[dict], wheel_type: str) -> dict | None:
    return next((w for w in wheelspins if w.get("type") == wheel_type), None)


def _available_text(wheelspin: dict | None) -> str:
    if wheelspin is None or wheelspin.get("available") is None:
        return "[yellow]?[/]"

    available = wheelspin["available"]
    if available > 0:
        return f"[green]{available}[/]"
    return f"[bright_black]{available}[/]"


def _refresh_wheelspin(hwnd: int, wheel_type: str) -> dict | None:
    """Re-scan the current UI and return a wheelspin with a readable count."""
    image = capture(hwnd)
    if image is None:
        return None

    texts, _ = ocr_image(image)
    wheelspins = detect_wheelspins(texts)
    wheelspin = _find_wheelspin(wheelspins, wheel_type)
    if wheelspin is None or wheelspin.get("available") is None:
        return None
    return wheelspin


def prompt_wheelspin_selection(wheelspins: list[dict]) -> str | None:
    """Prompt for which detected wheelspin tile to automate.

    Returns ``"super"``, ``"regular"``, or ``None`` for exit.
    """
    super_spin = _find_wheelspin(wheelspins, "super")
    regular = _find_wheelspin(wheelspins, "regular")

    super_count = _available_text(super_spin)
    regular_count = _available_text(regular)

    console.print(
        Panel(
            "[bold cyan]1[/]  [magenta]Auto Super Spinwheel[/] "
            f"[bright_black](available:[/] {super_count}[bright_black])[/]\n"
            "[bold cyan]2[/]  [magenta]Auto Wheelspin[/] "
            f"[bright_black](available:[/] {regular_count}[bright_black])[/]\n"
            "[bold cyan]0[/]  [yellow]Exit[/]",
            title="MENU",
            border_style="bright_magenta",
            box=box.ROUNDED,
        )
    )

    choices = {
        "1": "super",
        "s": "super",
        "super": "super",
        "2": "regular",
        "r": "regular",
        "regular": "regular",
        "wheelspin": "regular",
        "0": None,
        "e": None,
        "exit": None,
        "q": None,
        "quit": None,
    }
    while True:
        raw = console.input("[cyan]Select[/] [bright_black](1/2/0)[/]: ").strip().lower()
        if raw in choices:
            return choices[raw]
        console.print("[yellow]Choose 1, 2, or 0.[/]")


def auto_spin_wheelspin(
    hwnd: int, wheel_type: str, wheelspin: dict | None = None
) -> None:
    """Select the requested wheelspin tile and trigger it once.

    The My Horizon wheelspin UI is laid out left-to-right: Super on the left,
    regular Wheelspin on the right. This first phase only sends one activation.
    """
    if wheel_type == "super":
        refreshed = _refresh_wheelspin(hwnd, wheel_type)
        if refreshed is None:
            render_wheelspins([])
            return

        wheelspin = refreshed
        label_pos = wheelspin.get("pos") if wheelspin else None
        if label_pos is not None:
            low_level_click_client(hwnd, label_pos[0], label_pos[1])
            console.print("[green]✓[/] Entering Super Wheelspin.")
            return

        press_left(hwnd)
    elif wheel_type == "regular":
        press_right(hwnd)
    else:
        raise ValueError(f"unknown wheelspin type: {wheel_type}")

    time.sleep(0.15)
    press_enter(hwnd)
    console.print(f"[green]✓[/] Triggered {wheel_type} wheelspin.")


def run_wheelspin_menu(result: dict | None) -> None:
    """Run the first-phase menu when wheelspin detection has succeeded."""
    if not result:
        return

    wheelspins = result.get("ui", {}).get("wheelspins", [])
    if not wheelspins:
        return

    selection = prompt_wheelspin_selection(wheelspins)
    if selection is None:
        console.print("[yellow]Good bye 😶‍🌫️.[/]")
        return

    hwnd = result["window"]["hwnd"]
    selected_wheelspin = _find_wheelspin(wheelspins, selection)
    auto_spin_wheelspin(hwnd, selection, selected_wheelspin)
