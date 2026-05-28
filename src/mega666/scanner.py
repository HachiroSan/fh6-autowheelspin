"""High-level scan orchestration — tie window capture, OCR, and detection together."""

import time

import psutil

from mega666.color import fail, warn
from mega666.detect import detect_wheelspins, is_detection_clear
from mega666.ocr import ocr_image
from mega666.ui import (
    render_resize_attempt,
    render_resize_exhausted,
    render_resize_result,
    render_resize_start,
    render_scan_result,
)
from mega666.window import capture, ensure_window, resize_window


EARLY_DETECTION_HEIGHT_FRACTION = 0.8


def _any_process_running(process_names: list[str]) -> bool:
    """Quick process existence check — useful before enumerating windows."""
    names_lower = {n.lower() for n in process_names}
    for proc in psutil.process_iter(["name"]):
        try:
            name = proc.info["name"]
            if name and name.lower() in names_lower:
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return False


def _format_result(texts, cap_ms, inf_ms):
    parts = [f"capture={cap_ms:.0f}ms", f"infer={inf_ms:.0f}ms"]
    if not texts:
        return f"  Timing: {', '.join(parts)}\n  No text detected"
    lines = [
        f"  Timing: {', '.join(parts)}",
        f"  {len(texts)} text regions",
    ]
    for i, (box, text, score) in enumerate(texts):
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        cx, cy = int(sum(xs) / 4), int(sum(ys) / 4)
        lines.append(
            f"  [{i:3d}] \"{text}\" score={score} at ({cx:4d},{cy:4d})"
        )
    return "\n".join(lines)


def _middle_vertical_crop(image, fraction: float = EARLY_DETECTION_HEIGHT_FRACTION):
    """Return the middle vertical slice and its top offset."""
    if image is None:
        return None, 0

    height, width = image.shape[:2]
    if height <= 0 or width <= 0:
        return None, 0

    crop_h = max(1, int(height * fraction))
    top = max((height - crop_h) // 2, 0)
    return image[top : top + crop_h, :, :].copy(), top


def _translate_ocr_boxes(texts, dx: int = 0, dy: int = 0):
    """Translate OCR boxes from crop coordinates back to full-window coordinates."""
    if not texts or (dx == 0 and dy == 0):
        return texts

    translated = []
    for box, text, score in texts:
        moved_box = [[point[0] + dx, point[1] + dy] for point in box]
        translated.append((moved_box, text, score))
    return translated


def _ocr_early_detection_area(image):
    """OCR only the middle 80% of the window for initial wheelspin detection."""
    crop, top = _middle_vertical_crop(image)
    if crop is None:
        return [], 0.0

    texts, infer_s = ocr_image(crop)
    return _translate_ocr_boxes(texts, dy=top), infer_s


def scan(process_names=None, verbose=True):
    """Find the FH6 window → capture → OCR → detect wheelspins.

    Returns a dict with keys *texts*, *image*, *window*, *timing*, *ui*,
    or *None* on failure.
    """
    if process_names is None:
        process_names = ["forzahorizon6.exe", "forzahorizon5.exe"]

    if not _any_process_running(process_names):
        if verbose:
            fail("Process is not running")
            names = ", ".join(process_names)
            warn(f"Searched for: {names}")
        return None

    win = ensure_window(process_names)
    if not win:
        if verbose:
            fail("FH6 window not found (process is running but no visible window)")
        return None

    result = _scan_window(win)
    if result is None:
        if verbose:
            fail("capture failed (PrintWindow)")
        return None

    if verbose:
        render_scan_result(result)

    return result


def _scan_window(win):
    t0 = time.perf_counter()
    cap = capture(win["hwnd"])
    if cap is None:
        return None
    cap_ms = (time.perf_counter() - t0) * 1000
    texts, infer_s = _ocr_early_detection_area(cap)
    inf_ms = infer_s * 1000
    h, w = cap.shape[:2]
    wheelspins = detect_wheelspins(texts, height=h, width=w)
    return {
        "texts": texts,
        "image": cap,
        "window": win,
        "timing": {"capture_ms": cap_ms, "infer_ms": inf_ms},
        "ui": {"wheelspins": wheelspins},
    }


def _scan_silent(process_names):
    if not _any_process_running(process_names):
        return None
    win = ensure_window(process_names)
    if not win:
        return None
    return _scan_window(win)


def scan_auto_resize(process_names=None, verbose=True):
    if process_names is None:
        process_names = ["forzahorizon6.exe", "forzahorizon5.exe"]

    width_steps = [700, 800, 900, 960, 1100, 1280]
    attempts = 0
    result = None

    if not _any_process_running(process_names):
        if verbose:
            fail("Process is not running")
            names = ", ".join(process_names)
            warn(f"Searched for: {names}")
        return None

    win = ensure_window(process_names)
    if not win:
        if verbose:
            fail("FH6 window not found (process is running but no visible window)")
        return None

    current_w, current_h = win["w"], win["h"]
    aspect = current_h / current_w if current_w > 0 else 9 / 16
    targets = sorted(set(w for w in width_steps if w >= current_w) | {current_w})

    if verbose:
        render_resize_start(current_w, current_h)

    for target_w in targets:
        target_h = max(int(target_w * aspect), 400)

        if verbose:
            render_resize_attempt(target_w, target_h)

        if target_w != current_w:
            resize_window(win["hwnd"], target_w, target_h)
            time.sleep(0.5)
            win = ensure_window(process_names)
            if not win:
                if verbose:
                    render_resize_result(None, clear=False)
                break

        result = _scan_silent(process_names)
        attempts += 1
        wheelspins = result["ui"]["wheelspins"] if result else []

        if result and is_detection_clear(wheelspins):
            if verbose:
                render_resize_result(result, clear=True)
            result["resize_attempts"] = attempts
            return result

        if verbose:
            render_resize_result(result, clear=False)

    if verbose:
        render_resize_exhausted()
    if result is not None:
        result["resize_attempts"] = attempts
    return result
