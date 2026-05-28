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

    t0 = time.perf_counter()
    cap = capture(win["hwnd"])
    if cap is None:
        if verbose:
            fail("capture failed (PrintWindow)")
        return None
    cap_ms = (time.perf_counter() - t0) * 1000

    texts, infer_s = ocr_image(cap)
    inf_ms = infer_s * 1000
    wheelspins = detect_wheelspins(texts)
    result = {
        "texts": texts,
        "image": cap,
        "window": win,
        "timing": {"capture_ms": cap_ms, "infer_ms": inf_ms},
        "ui": {"wheelspins": wheelspins},
    }

    if verbose:
        render_scan_result(result)

    return result


def _scan_silent(process_names):
    """Minimal scan — no prints, returns the same dict as :func:`scan`."""
    if not _any_process_running(process_names):
        return None
    win = ensure_window(process_names)
    if not win:
        return None
    t0 = time.perf_counter()
    cap = capture(win["hwnd"])
    if cap is None:
        return None
    cap_ms = (time.perf_counter() - t0) * 1000
    texts, infer_s = ocr_image(cap)
    inf_ms = infer_s * 1000
    wheelspins = detect_wheelspins(texts)
    return {
        "texts": texts,
        "image": cap,
        "window": win,
        "timing": {"capture_ms": cap_ms, "infer_ms": inf_ms},
        "ui": {"wheelspins": wheelspins},
    }


def scan_auto_resize(process_names=None, verbose=True):
    """Progressively enlarge the game window until both wheelspins are readable.

    Returns the last scan result dict (with an extra *resize_attempts* key)
    or *None* if the window cannot be found.
    """
    if process_names is None:
        process_names = ["forzahorizon6.exe", "forzahorizon5.exe"]

    WIDTH_STEPS = [700, 800, 900, 960, 1100, 1280]
    attempts = 0
    res = None

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
    assert win is not None

    current_w, current_h = win["w"], win["h"]
    aspect = current_h / current_w if current_w > 0 else 9 / 16
    targets = sorted(
        set(w for w in WIDTH_STEPS if w >= current_w) | {current_w}
    )

    if verbose:
        render_resize_start(current_w, current_h)

    for target_w in targets:
        if win is None:
            if verbose:
                render_resize_result(None, clear=False)
            break

        target_h = int(target_w * aspect)
        if target_h < 400:
            target_h = 400

        if target_w != current_w:
            if verbose:
                render_resize_attempt(target_w, target_h)
            resize_window(win["hwnd"], target_w, target_h)
            time.sleep(0.5)
            win = ensure_window(process_names)
        elif verbose:
            render_resize_attempt(target_w, target_h)

        res = _scan_silent(process_names)
        attempts += 1

        ws = res["ui"]["wheelspins"] if res else []

        if res and is_detection_clear(ws):
            if verbose:
                render_resize_result(res, clear=True)
            res["resize_attempts"] = attempts
            return res
        elif res:
            if verbose:
                render_resize_result(res, clear=False)
        else:
            if verbose:
                render_resize_result(None, clear=False)

    if verbose:
        render_resize_exhausted()
    if res is not None:
        res["resize_attempts"] = attempts
    return res
