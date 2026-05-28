"""OCR engine setup and inference."""

import time

import numpy as np
from rapidocr_onnxruntime import RapidOCR

from mega666.ui import run_with_spinner

_engine: RapidOCR | None = None


def _get_engine() -> RapidOCR:
    """Lazy-init the OCR engine on first use."""
    global _engine
    if _engine is None:
        _engine = RapidOCR()
    return _engine


def warmup() -> None:
    """Explicitly load and warm the OCR model (call after preflight)."""
    def _warm() -> None:
        _get_engine()(np.zeros((100, 100, 3), dtype=np.uint8))

    run_with_spinner("Warming OCR neural runtime", _warm)


def ocr_image(img: np.ndarray):
    """Run OCR on a numpy BGR image.

    Returns (texts, infer_seconds) where *texts* is the list of
    (box, text, score) tuples from RapidOCR (empty list on no text).
    """
    t0 = time.perf_counter()
    result, _ = _get_engine()(img)
    return (result or []), time.perf_counter() - t0
