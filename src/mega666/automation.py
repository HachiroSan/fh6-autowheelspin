"""First-phase wheelspin automation helpers."""

from __future__ import annotations

import re
import time

import cv2
import numpy as np
from rich import box
from rich.panel import Panel

from mega666.detect import detect_wheelspins, is_detection_clear
from mega666.input import (
    low_level_click_client,
    press_down,
    press_enter,
    press_left,
    press_right,
)
from mega666.ocr import ocr_image
from mega666.ui import console, render_wheelspins
from mega666.window import capture


SUPERWHEELSPIN_COUNT_X1 = 0.08
SUPERWHEELSPIN_COUNT_Y1 = 0.25
SUPERWHEELSPIN_COUNT_X2 = 0.32
SUPERWHEELSPIN_COUNT_Y2 = 0.75
POST_CLICK_SCAN_DELAY = 0.8
POST_RESULT_TIMEOUT = 15.0
POST_RESULT_INTERVAL = 0.25
POST_SPIN_LOOP_IDLE_LIMIT = 3
DUPLICATE_CAR_POST_SELECT_DELAY = 1.0
PRE_TOTAL_CONFIRM_ENTER_DELAY = 1.0
POST_TOTAL_CONFIRM_DELAY = 2.0
BOTTOM_CHANGE_FRACTION = 0.1
BOTTOM_CHANGE_TIMEOUT = 10.0
BOTTOM_CHANGE_INTERVAL = 0.2
BOTTOM_CHANGE_START_DELAY = 0.2
BOTTOM_CHANGE_CONFIRM_DELAY = 2.0
BOTTOM_CONFIRM_TIMEOUT = 5.0
BOTTOM_CONFIRM_RETRY_INTERVAL = 0.3
PROMPT_ROI_X1 = 0.00
PROMPT_ROI_Y1 = 0.30
PROMPT_ROI_X2 = 0.55
PROMPT_ROI_Y2 = 0.95
COMPARE_SIZE = (180, 32)
PIXEL_THRESHOLD = 12
RATIO_THRESHOLD = 0.035
MEAN_THRESHOLD = 2.0


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
    h, w = image.shape[:2]
    wheelspins = detect_wheelspins(texts, height=h, width=w)
    wheelspin = _find_wheelspin(wheelspins, wheel_type)
    if wheelspin is None or wheelspin.get("available") is None:
        return None
    return wheelspin


def _superwheelspin_total_crop(image):
    """Return only the Super Wheelspin count area in the middle 50% height.

    This avoids top-left car/header text such as model years (for example,
    ``2023Honda``) being mistaken for the available wheelspin total.
    """
    if image is None:
        return None

    height, width = image.shape[:2]
    if height <= 0 or width <= 0:
        return None

    left = int(width * SUPERWHEELSPIN_COUNT_X1)
    top = int(height * SUPERWHEELSPIN_COUNT_Y1)
    right = int(width * SUPERWHEELSPIN_COUNT_X2)
    bottom = int(height * SUPERWHEELSPIN_COUNT_Y2)
    if right <= left or bottom <= top:
        return None

    return image[top:bottom, left:right, :].copy()


def _find_numbers(texts) -> list[int]:
    """Return all OCR integers in the scanned region."""
    numbers = []
    for _, text, _ in texts:
        for match in re.finditer(r"(?<!\d)\d{1,5}(?!\d)", text):
            numbers.append(int(match.group(0)))
    return numbers


def _scan_for_superwheelspin_total(hwnd: int, expected: int) -> bool:
    """OCR the Super Wheelspin count ROI for expected total."""
    image = capture(hwnd)
    crop = _superwheelspin_total_crop(image)
    if crop is None:
        console.print(f"[yellow]Super Wheelspin total {expected} not found.[/]")
        return False

    texts, _ = ocr_image(crop)
    numbers = _find_numbers(texts)
    if expected not in numbers:
        console.print(f"[yellow]Super Wheelspin total {expected} not found.[/]")
        return False

    console.print(f"[green]✓[/] Super Wheelspin total {expected} found.")
    return True


def _has_car_already_owned(texts) -> bool:
    for _, text, _ in texts:
        compact = re.sub(r"[^a-z0-9]+", "", text.lower())
        if "caralreadyowned" in compact:
            return True
    return False


def _scan_post_spin_outcome(hwnd: int, expected_total: int) -> str | None:
    """Race scan for the next Super Wheelspin total or Car Already Owned.

    Returns ``"total"`` when *expected_total* appears first, ``"owned"`` when
    the duplicate-car dialog appears first, or ``None`` on timeout/failure.
    """
    deadline = time.perf_counter() + POST_RESULT_TIMEOUT
    while time.perf_counter() < deadline:
        image = capture(hwnd)
        if image is None:
            time.sleep(POST_RESULT_INTERVAL)
            continue

        texts, _ = ocr_image(image)
        if _has_car_already_owned(texts):
            console.print("[green]✓[/] Car Already Owned found.")
            return "owned"

        crop = _superwheelspin_total_crop(image)
        if crop is not None:
            crop_texts, _ = ocr_image(crop)
            if expected_total in _find_numbers(crop_texts):
                console.print(
                    f"[green]✓[/] Super Wheelspin total {expected_total} found."
                )
                return "total"

        time.sleep(POST_RESULT_INTERVAL)

    console.print(
        f"[yellow]Neither Super Wheelspin total {expected_total} nor "
        "Car Already Owned appeared before timeout.[/]"
    )
    return None


def _select_duplicate_car_option(hwnd: int) -> None:
    press_down(hwnd)
    time.sleep(0.08)
    press_down(hwnd)
    time.sleep(0.08)
    press_enter(hwnd)
    console.print("[green]✓[/] Selected duplicate-car option with Down, Down, Enter.")


def _confirm_spin_result(hwnd: int, total: int) -> bool:
    """Press through the result sequence after a decremented total is visible."""
    time.sleep(PRE_TOTAL_CONFIRM_ENTER_DELAY)
    press_enter(hwnd)
    console.print(
        f"[green]✓[/] Pressed Enter after confirmed Super Wheelspin total {total}."
    )
    time.sleep(POST_TOTAL_CONFIRM_DELAY)
    if not _wait_for_bottom_change(hwnd):
        return False

    time.sleep(BOTTOM_CHANGE_CONFIRM_DELAY)
    return _press_enter_until_bottom_changes(hwnd)


def _run_superwheelspin_result_loop(hwnd: int, before_total: int) -> None:
    """Loop through Super Wheelspin result handling using dynamic totals.

    Each spin lowers the available count by one.  After every result confirm,
    the UI may either show a duplicate-car dialog or the next decremented total.
    Duplicate cars are resolved with Down, Down, Enter, then scanning continues
    for the same expected decremented total.
    """
    expected = max(before_total - 1, 0)
    idle_timeouts = 0

    time.sleep(POST_CLICK_SCAN_DELAY)
    while expected >= 0:
        outcome = _scan_post_spin_outcome(hwnd, expected)

        if outcome == "owned":
            _select_duplicate_car_option(hwnd)
            idle_timeouts = 0
            time.sleep(DUPLICATE_CAR_POST_SELECT_DELAY)
            continue

        if outcome != "total":
            idle_timeouts += 1
            if idle_timeouts >= POST_SPIN_LOOP_IDLE_LIMIT:
                console.print(
                    "[yellow]Stopping Super Wheelspin loop after repeated scan timeouts.[/]"
                )
                return
            continue

        idle_timeouts = 0
        if not _confirm_spin_result(hwnd, expected):
            return

        if expected == 0:
            console.print("[yellow]Super Wheelspin total reached 0; loop complete.[/]")
            return
        expected -= 1


def _crop_bottom_prompt_area(frame_bgr):
    """Crop normalized prompt ROI inside the bottom scan area."""
    if frame_bgr is None:
        return None

    height, width = frame_bgr.shape[:2]
    if height <= 0 or width <= 0:
        return None

    bottom_y1 = int(height * (1.0 - BOTTOM_CHANGE_FRACTION))
    bottom = frame_bgr[bottom_y1:height, 0:width]
    bottom_height, bottom_width = bottom.shape[:2]

    x1 = int(bottom_width * PROMPT_ROI_X1)
    y1 = int(bottom_height * PROMPT_ROI_Y1)
    x2 = int(bottom_width * PROMPT_ROI_X2)
    y2 = int(bottom_height * PROMPT_ROI_Y2)
    if x2 <= x1 or y2 <= y1:
        return None

    return bottom[y1:y2, x1:x2].copy()


def _capture_prompt_area(hwnd: int):
    image = capture(hwnd)
    return _crop_bottom_prompt_area(image)


def _screenshots_are_different(before, after) -> bool:
    if before is None or after is None:
        return False

    before_gray = cv2.cvtColor(before, cv2.COLOR_BGR2GRAY)
    after_gray = cv2.cvtColor(after, cv2.COLOR_BGR2GRAY)
    before_small = cv2.resize(before_gray, COMPARE_SIZE, interpolation=cv2.INTER_AREA)
    after_small = cv2.resize(after_gray, COMPARE_SIZE, interpolation=cv2.INTER_AREA)
    before_small = cv2.GaussianBlur(before_small, (3, 3), 0)
    after_small = cv2.GaussianBlur(after_small, (3, 3), 0)
    diff = cv2.absdiff(before_small, after_small)
    changed_ratio = np.count_nonzero(diff >= PIXEL_THRESHOLD) / diff.size
    mean_diff = float(np.mean(diff))
    return changed_ratio >= RATIO_THRESHOLD or mean_diff >= MEAN_THRESHOLD


def _wait_for_bottom_change(hwnd: int) -> bool:
    """Watch bottom 10% until two consecutive screenshots differ."""
    time.sleep(BOTTOM_CHANGE_START_DELAY)
    previous = _capture_prompt_area(hwnd)
    if previous is None:
        console.print("[yellow]Bottom change not detected: screenshot failed.[/]")
        return False

    deadline = time.perf_counter() + BOTTOM_CHANGE_TIMEOUT
    current = previous
    while time.perf_counter() < deadline:
        time.sleep(BOTTOM_CHANGE_INTERVAL)
        current = _capture_prompt_area(hwnd)
        if _screenshots_are_different(previous, current):
            console.print("[green]✓[/] Bottom 10% visual change detected.")
            return True
        if current is not None:
            previous = current

    console.print("[yellow]Bottom 10% visual change not detected before timeout.[/]")
    return False


def _press_enter_until_bottom_changes(hwnd: int) -> bool:
    """Press Enter until the bottom prompt area changes, retrying for 5 seconds."""
    before = _capture_prompt_area(hwnd)
    if before is None:
        console.print("[yellow]Bottom confirm retry skipped: screenshot failed.[/]")
        return False

    deadline = time.perf_counter() + BOTTOM_CONFIRM_TIMEOUT
    attempts = 0
    while time.perf_counter() < deadline:
        attempts += 1
        press_enter(hwnd)
        console.print("[green]✓[/] Pressed Enter after bottom visual change.")
        time.sleep(BOTTOM_CONFIRM_RETRY_INTERVAL)

        after = _capture_prompt_area(hwnd)
        if _screenshots_are_different(before, after):
            if attempts > 1:
                console.print(
                    f"[green]✓[/] Bottom 10% changed after Enter retry #{attempts}."
                )
            return True

    console.print("[yellow]Bottom 10% did not change after Enter retries.[/]")
    return False


def _scan_superwheelspin_total_after_click(hwnd: int, before_total: int | None) -> None:
    if before_total is None:
        console.print("[yellow]Super Wheelspin total not checked: starting count unknown.[/]")
        return

    _run_superwheelspin_result_loop(hwnd, before_total)


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
        before_total = wheelspin.get("available") if wheelspin else None
        if label_pos is not None:
            low_level_click_client(hwnd, label_pos[0], label_pos[1])
            console.print("[green]✓[/] Entering Super Wheelspin.")
            _scan_superwheelspin_total_after_click(hwnd, before_total)
            return

        press_left(hwnd)
    elif wheel_type == "regular":
        press_right(hwnd)
    else:
        raise ValueError(f"unknown wheelspin type: {wheel_type}")

    time.sleep(0.15)
    press_enter(hwnd)
    console.print(f"[green]✓[/] Triggered {wheel_type} wheelspin.")
    if wheel_type == "super":
        before_total = wheelspin.get("available") if wheelspin else None
        _scan_superwheelspin_total_after_click(hwnd, before_total)


def run_wheelspin_menu(result: dict | None) -> None:
    """Run the first-phase menu when wheelspin detection has succeeded."""
    if not result:
        return

    wheelspins = result.get("ui", {}).get("wheelspins", [])
    if not wheelspins:
        return
    if not is_detection_clear(wheelspins):
        render_wheelspins([])
        return

    selection = prompt_wheelspin_selection(wheelspins)
    if selection is None:
        console.print("[yellow]Good bye 😶‍🌫️.[/]")
        return

    hwnd = result["window"]["hwnd"]
    selected_wheelspin = _find_wheelspin(wheelspins, selection)
    auto_spin_wheelspin(hwnd, selection, selected_wheelspin)
