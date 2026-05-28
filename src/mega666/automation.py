"""First-phase wheelspin automation helpers."""

from __future__ import annotations

import re
import time

import cv2
import numpy as np

from mega666.detect import detect_wheelspins, is_detection_clear
from mega666.input import (
    low_level_click_client,
    press_down,
    press_enter,
    press_escape,
)
from mega666.ocr import ocr_image
from mega666.tui import SpinLiveView, SpinSessionState, select_wheelspin_menu
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
POST_TOTAL_CONFIRM_DELAY = 2.0
POST_ESCAPE_LANDING_TIMEOUT = 15.0
POST_ESCAPE_LANDING_INTERVAL = 0.3
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


def _wheelspin_display_name(wheel_type: str) -> str:
    return "Super Wheelspin" if wheel_type == "super" else "Wheelspin"


def _emit(view: SpinLiveView | None, message: str, *, status: str | None = None, current_count: int | None = None) -> None:
    if view is not None:
        view.event(message, status=status, current_count=current_count)
    else:
        console.print(message)


def _graceful_stop_requested(view: SpinLiveView | None) -> bool:
    return view is not None and view.poll_graceful_stop()


def _prompt_stop_at(wheel_type: str, available: int) -> int:
    """Ask how many wheelspins to roll and return the remaining-count target."""
    name = _wheelspin_display_name(wheel_type)
    while True:
        raw = console.input(
            f"[cyan]How many {name}s to roll[/] "
            f"[bright_black](1-{available}, default {available})[/]: "
        ).strip()
        if raw == "":
            return 0

        try:
            rolls = int(raw)
        except ValueError:
            console.print("[yellow]Enter a whole number.[/]")
            continue

        if 1 <= rolls <= available:
            return available - rolls

        console.print(f"[yellow]Enter a number from 1 to {available}.[/]")


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


def _scan_post_spin_outcome(
    hwnd: int, expected_total: int, wheel_type: str, view: SpinLiveView | None = None
) -> str | None:
    """Race scan for the next wheelspin total or Car Already Owned.

    Returns ``"total"`` when *expected_total* appears first, ``"owned"`` when
    the duplicate-car dialog appears first, or ``None`` on timeout/failure.
    """
    name = _wheelspin_display_name(wheel_type)
    _emit(view, f"Waiting for {name} result ({expected_total} remaining)", status="Reading result")
    deadline = time.perf_counter() + POST_RESULT_TIMEOUT
    while time.perf_counter() < deadline:
        _graceful_stop_requested(view)
        image = capture(hwnd)
        if image is None:
            time.sleep(POST_RESULT_INTERVAL)
            continue

        texts, _ = ocr_image(image)
        if _has_car_already_owned(texts):
            _emit(view, "Duplicate reward detected; selecting payout option", status="Resolving reward")
            return "owned"

        crop = _superwheelspin_total_crop(image)
        if crop is not None:
            crop_texts, _ = ocr_image(crop)
            if expected_total in _find_numbers(crop_texts):
                _emit(
                    view,
                    f"{name} result confirmed. {expected_total} remaining",
                    status="Result confirmed",
                    current_count=expected_total,
                )
                return "total"

        time.sleep(POST_RESULT_INTERVAL)

    _emit(
        view,
        f"Result was not confirmed in time for {expected_total} remaining; retrying scan",
        status="Awaiting result",
    )
    return None


def _select_duplicate_car_option(hwnd: int, view: SpinLiveView | None = None) -> None:
    press_down(hwnd)
    time.sleep(0.08)
    press_down(hwnd)
    time.sleep(0.08)
    press_enter(hwnd)
    _emit(view, "Duplicate reward handled; continuing automation", status="Reward resolved")


def _wait_for_wheelspin_landing_or_handle_owned(
    hwnd: int, view: SpinLiveView | None = None
) -> bool:
    """After leaving results, handle duplicate dialogs until landing is visible."""
    deadline = time.perf_counter() + POST_ESCAPE_LANDING_TIMEOUT
    while time.perf_counter() < deadline:
        image = capture(hwnd)
        if image is None:
            time.sleep(POST_ESCAPE_LANDING_INTERVAL)
            continue

        texts, _ = ocr_image(image)
        if _has_car_already_owned(texts):
            _emit(view, "Duplicate reward detected during exit; resolving before leaving", status="Resolving reward")
            _select_duplicate_car_option(hwnd, view)
            time.sleep(DUPLICATE_CAR_POST_SELECT_DELAY)
            continue

        h, w = image.shape[:2]
        wheelspins = detect_wheelspins(texts, height=h, width=w)
        if is_detection_clear(wheelspins):
            _emit(view, "Returned to the wheelspin menu successfully", status="Complete")
            return True

        time.sleep(POST_ESCAPE_LANDING_INTERVAL)

    _emit(view, "Exit confirmation timed out; please verify the game menu state", status="Exit timeout")
    return False


def _confirm_spin_result(
    hwnd: int,
    total: int,
    wheel_type: str,
    bottom_reference=None,
    view: SpinLiveView | None = None,
) -> bool:
    """Press through the result sequence after a decremented total is visible."""
    name = _wheelspin_display_name(wheel_type)
    _wait_for_bottom_change(hwnd, bottom_reference, view)
    _emit(
        view,
        f"Confirming {total} remaining",
        status="Confirming result",
    )
    press_enter(hwnd)
    _emit(
        view,
        f"Confirmed {name} result; preparing next roll",
        status="Preparing next roll",
    )
    time.sleep(POST_TOTAL_CONFIRM_DELAY)
    if not _wait_for_bottom_change(hwnd, bottom_reference, view):
        return False

    time.sleep(BOTTOM_CHANGE_CONFIRM_DELAY)
    return _press_enter_until_bottom_changes(hwnd, view)


def _confirm_and_exit_at_target(
    hwnd: int,
    total: int,
    wheel_type: str,
    bottom_reference=None,
    view: SpinLiveView | None = None,
) -> None:
    """Confirm target result, then leave once the second bottom change appears."""
    name = _wheelspin_display_name(wheel_type)
    _wait_for_bottom_change(hwnd, bottom_reference, view)
    _emit(
        view,
        f"Confirming final result at {total} remaining",
        status="Confirming final result",
    )
    press_enter(hwnd)
    _emit(
        view,
        f"Final {name} result confirmed; preparing safe exit",
        status="Preparing exit",
    )

    time.sleep(POST_TOTAL_CONFIRM_DELAY)
    if not _wait_for_bottom_change(hwnd, bottom_reference, view):
        _emit(view, "Target reached; exit prompt did not appear in time", status="Exit timeout")
        return

    time.sleep(BOTTOM_CHANGE_CONFIRM_DELAY)
    press_escape(hwnd)
    _emit(
        view,
        f"Leaving reward flow at {total} remaining",
        status="Returning to landing",
    )
    _wait_for_wheelspin_landing_or_handle_owned(hwnd, view)
    _emit(view, f"{name} automation complete. {total} remaining", status="Complete")


def _run_wheelspin_result_loop(
    hwnd: int,
    before_total: int,
    wheel_type: str,
    stop_at: int = 0,
    initial_bottom_reference=None,
    view: SpinLiveView | None = None,
) -> None:
    """Loop through wheelspin result handling using dynamic totals.

    Each spin lowers the available count by one.  After every result confirm,
    the UI may either show a duplicate-car dialog or the next decremented total.
    Duplicate cars are resolved with Down, Down, Enter, then scanning continues
    for the same expected decremented total.
    """
    name = _wheelspin_display_name(wheel_type)
    stop_at = max(stop_at, 0)
    expected = max(before_total - 1, 0)
    idle_timeouts = 0
    bottom_reference = initial_bottom_reference

    _emit(view, f"Running {name} automation until {stop_at} remain", status="Rolling")

    time.sleep(POST_CLICK_SCAN_DELAY)
    while expected >= stop_at:
        _graceful_stop_requested(view)
        outcome = _scan_post_spin_outcome(hwnd, expected, wheel_type, view)

        if outcome == "owned":
            _select_duplicate_car_option(hwnd, view)
            idle_timeouts = 0
            time.sleep(DUPLICATE_CAR_POST_SELECT_DELAY)
            continue

        if outcome != "total":
            idle_timeouts += 1
            if idle_timeouts >= POST_SPIN_LOOP_IDLE_LIMIT:
                _emit(view, f"Stopping {name} automation after repeated result timeouts", status="Stopped")
                return
            continue

        idle_timeouts = 0
        if expected == stop_at or _graceful_stop_requested(view):
            _confirm_and_exit_at_target(hwnd, expected, wheel_type, bottom_reference, view)
            return

        if not _confirm_spin_result(hwnd, expected, wheel_type, bottom_reference, view):
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


def _wait_for_bottom_change(
    hwnd: int, reference=None, view: SpinLiveView | None = None
) -> bool:
    """Watch bottom 10% until two consecutive screenshots differ."""
    time.sleep(BOTTOM_CHANGE_START_DELAY)
    previous = reference if reference is not None else _capture_prompt_area(hwnd)
    if previous is None:
        _emit(view, "Unable to verify the next prompt because capture failed", status="Capture failed")
        return False

    deadline = time.perf_counter() + BOTTOM_CHANGE_TIMEOUT
    current = previous
    while time.perf_counter() < deadline:
        _graceful_stop_requested(view)
        time.sleep(BOTTOM_CHANGE_INTERVAL)
        current = _capture_prompt_area(hwnd)
        if _screenshots_are_different(previous, current):
            _emit(view, "Next prompt detected", status="Prompt ready")
            return True
        if reference is None and current is not None:
            previous = current

    _emit(view, "Next prompt was not detected before timeout", status="Prompt timeout")
    return False


def _press_enter_until_bottom_changes(
    hwnd: int, view: SpinLiveView | None = None
) -> bool:
    """Press Enter until the bottom prompt area changes, retrying for 5 seconds."""
    before = _capture_prompt_area(hwnd)
    if before is None:
        _emit(view, "Unable to advance because capture failed", status="Capture failed")
        return False

    deadline = time.perf_counter() + BOTTOM_CONFIRM_TIMEOUT
    attempts = 0
    while time.perf_counter() < deadline:
        _graceful_stop_requested(view)
        attempts += 1
        press_enter(hwnd)
        _emit(view, "Advancing to the next screen", status="Advancing")
        time.sleep(BOTTOM_CONFIRM_RETRY_INTERVAL)

        after = _capture_prompt_area(hwnd)
        if _screenshots_are_different(before, after):
            if attempts > 1:
                _emit(
                    view,
                    f"Advanced after retry {attempts}",
                    status="Advanced",
                )
            return True

    _emit(view, "Unable to advance after multiple confirmation attempts", status="Advance timeout")
    return False


def _scan_wheelspin_total_after_click(
    hwnd: int,
    before_total: int | None,
    wheel_type: str,
    stop_at: int = 0,
    initial_bottom_reference=None,
    view: SpinLiveView | None = None,
) -> None:
    name = _wheelspin_display_name(wheel_type)
    if before_total is None:
        _emit(view, f"Cannot start {name} automation because the starting count is unreadable", status="Stopped")
        return

    _run_wheelspin_result_loop(
        hwnd, before_total, wheel_type, stop_at, initial_bottom_reference, view
    )


def prompt_wheelspin_selection(wheelspins: list[dict]) -> tuple[str, int] | None:
    """Prompt for which detected wheelspin tile to automate.

    Returns ``(wheel_type, stop_at)`` or ``None`` for exit.
    """
    super_spin = _find_wheelspin(wheelspins, "super")
    regular = _find_wheelspin(wheelspins, "regular")

    choice = select_wheelspin_menu(super_spin, regular)
    if choice is None:
        return None

    selection = choice.wheel_type
    selected_spin = _find_wheelspin(wheelspins, selection)
    available = int(selected_spin["available"]) if selected_spin else 0
    if choice.mode == "all":
        return selection, 0

    return selection, _prompt_stop_at(selection, available)


def auto_spin_wheelspin(
    hwnd: int,
    wheel_type: str,
    wheelspin: dict | None = None,
    stop_at: int = 0,
) -> None:
    """Select the requested wheelspin tile and trigger it once.

    The My Horizon wheelspin UI is laid out left-to-right: Super on the left,
    regular Wheelspin on the right. This first phase only sends one activation.
    """
    if wheel_type not in {"super", "regular"}:
        raise ValueError(f"unknown wheelspin type: {wheel_type}")

    name = _wheelspin_display_name(wheel_type)
    refreshed = _refresh_wheelspin(hwnd, wheel_type)
    if refreshed is None:
        render_wheelspins([])
        return

    wheelspin = refreshed
    click_pos = wheelspin.get("pos")
    before_total = wheelspin.get("available")
    if before_total is not None and before_total <= stop_at:
        console.print(
            f"[yellow]{name} count is already at/below target "
            f"{stop_at}; nothing to roll.[/]"
        )
        return
    if click_pos is None:
        render_wheelspins([])
        return

    start_count = int(before_total or 0)
    state = SpinSessionState(
        wheel_type=wheel_type,
        start_count=start_count,
        target_count=stop_at,
        current_count=start_count,
    )
    with SpinLiveView(state) as view:
        view.event(f"Selecting {name}", status="Starting")
        low_level_click_client(hwnd, click_pos[0], click_pos[1])
        initial_bottom_reference = _capture_prompt_area(hwnd)
        view.event(f"{name} selected; waiting for the first result", status="In progress")
        _scan_wheelspin_total_after_click(
            hwnd, before_total, wheel_type, stop_at, initial_bottom_reference, view
        )


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

    menu_choice = prompt_wheelspin_selection(wheelspins)
    if menu_choice is None:
        console.print("[yellow]Good bye 😶‍🌫️.[/]")
        return

    selection, stop_at = menu_choice

    hwnd = result["window"]["hwnd"]
    selected_wheelspin = _find_wheelspin(wheelspins, selection)
    auto_spin_wheelspin(hwnd, selection, selected_wheelspin, stop_at or 0)
