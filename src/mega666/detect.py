"""FH6 UI state detection from OCR output."""

import re

from mega666.color import B, C, G, N, Y


def _fuzzy_available(s: str) -> bool:
    s = s.strip().lower()
    return any(
        v in s
        for v in [
            "available",
            "avallable",
            "awailable",
            "awal",
            "avail",
        ]
    )


def detect_wheelspins(texts):
    """Parse OCR output to find Wheelspin widgets (Super + Regular).

    Returns a list of dicts with keys:
        label, type ("super"|"regular"), available (int or None),
        available_pos (tuple[int, int] or None), pos, score.
    """
    if not texts:
        return []

    labels, counts, av_words = [], [], []

    for box, text, score in texts:
        text_clean = text.strip()
        cx = int(sum(p[0] for p in box) / 4)
        cy = int(sum(p[1] for p in box) / 4)
        tl = text_clean.lower()

        if "wheelspin" in tl or tl.endswith("heelspin") or tl.endswith("eelspin"):
            labels.append((cx, cy, text_clean, float(score)))

        m = re.search(r"(\d+)\s*available", text_clean, re.IGNORECASE)
        if not m:
            m = re.match(r"(\d{2,})\s*\w{3,}", text_clean)
        if m:
            counts.append((cx, cy, int(m.group(1)), float(score)))
            continue

        if _fuzzy_available(text_clean) and not re.match(r"\d", text_clean):
            av_words.append((cx, cy))

    all_xs = [lx for lx, *_ in labels] + [cx for cx, *_ in counts]
    mid_x = (min(all_xs) + max(all_xs)) / 2 if all_xs else 250
    MAX_Y_DIST = 150

    wheelspins = []
    used_counts = set()

    for lx, ly, ltext, lscore in sorted(labels, key=lambda x: x[1]):
        best, best_dist, best_ci = None, MAX_Y_DIST, -1
        for i, (cx, cy, num, cscore) in enumerate(counts):
            if i in used_counts:
                continue
            same_side = (lx < mid_x and cx < mid_x) or (
                lx >= mid_x and cx >= mid_x
            )
            if not same_side:
                continue
            dist = abs(ly - cy)
            if dist < best_dist:
                best_dist, best, best_ci = dist, (num, cx, cy, cscore), i

        wtype = "super" if lx < mid_x else "regular"

        if best is not None:
            used_counts.add(best_ci)
            num, cx, cy, cscore = best
            existing = next(
                (w for w in wheelspins if w["type"] == wtype), None
            )
            if existing is None:
                wheelspins.append(
                    {
                        "label": ltext,
                        "type": wtype,
                        "available": num,
                        "available_pos": (cx, cy),
                        "pos": (lx, ly),
                        "score": lscore,
                    }
                )
        else:
            has_av_word = any(
                abs(ly - ay) < MAX_Y_DIST
                and (lx < mid_x and ax < mid_x or lx >= mid_x and ax >= mid_x)
                for ax, ay in av_words
            )
            if has_av_word:
                existing = next(
                    (w for w in wheelspins if w["type"] == wtype), None
                )
                if existing is None:
                    wheelspins.append(
                        {
                            "label": ltext,
                            "type": wtype,
                            "available": None,
                            "available_pos": None,
                            "pos": (lx, ly),
                            "score": lscore,
                        }
                    )

    return sorted(wheelspins, key=lambda w: w["pos"][1])


def ui_box(wheelspins) -> str:
    """Return a polished multi-line summary string."""
    if not wheelspins:
        return (
            f"  {Y}No wheelspins detected{N}\n"
            f"  {Y}→ Go to the {C}My Horizon{Y} tab in FH6{N}\n"
            f"  {Y}  If already there, try a larger window / higher resolution{N}"
        )
    _W = 36
    parts = []
    for w in wheelspins:
        raw = str(w["available"]) if w["available"] is not None else "?"
        clr = G if w["available"] is not None else Y
        name = "Super Wheelspin" if w["type"] == "super" else "Wheelspin"
        name_padded = f" {name} "
        gap = _W - len(name_padded) - 2
        fill = "─" * gap
        body = f" {clr}{raw:>4s}{N} available"
        pad = " " * (_W - len(raw) - 12)  # visible: " XXXX available" = raw_len + 11 + 1 space
        parts.append(
            f"  {B}{C}┌─{name_padded}{fill}┐{N}\n"
            f"  {B}{C}│{N}{body}{pad}{B}{C}│{N}\n"
            f"  {B}{C}└{'─' * (_W - 1)}┘{N}"
        )
    return "\n".join(parts)


def is_detection_clear(wheelspins) -> bool:
    """True when both wheelspin types are detected with known counts."""
    types_found = {w["type"] for w in wheelspins}
    have_both = "super" in types_found and "regular" in types_found
    return have_both and all(w["available"] is not None for w in wheelspins)
