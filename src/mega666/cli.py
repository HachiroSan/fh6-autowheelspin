"""CLI entry point."""

import argparse
import sys

from mega666.ocr import warmup as ocr_warmup
from mega666.automation import run_wheelspin_menu
from mega666.preflight import preflight
from mega666.scanner import scan, scan_auto_resize
from mega666.ui import banner, console


PROCESS_NAMES = ["forzahorizon6.exe"]


def main():
    parser = argparse.ArgumentParser(
        description="FH6 Auto WheelSpin Bot"
    )
    parser.add_argument(
        "--auto-resize",
        "-r",
        action="store_true",
        help="Auto-resize the game window until OCR reads clearly",
    )
    args = parser.parse_args()

    if not preflight(PROCESS_NAMES):
        sys.exit(1)

    ocr_warmup()

    console.clear()
    banner(PROCESS_NAMES)

    try:
        result = scan_auto_resize(PROCESS_NAMES) if args.auto_resize else scan(PROCESS_NAMES)
        run_wheelspin_menu(result)
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopped.[/]")
        sys.exit(130)


if __name__ == "__main__":
    main()
