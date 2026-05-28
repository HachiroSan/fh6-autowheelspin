"""CLI entry point — parses arguments and dispatches to scanner."""

import argparse
import sys
import time

from mega666.ocr import warmup as ocr_warmup
from mega666.automation import run_wheelspin_menu
from mega666.preflight import preflight
from mega666.scanner import scan, scan_auto_resize
from mega666.ui import banner, console, watch_header, watch_tick


def main():
    parser = argparse.ArgumentParser(
        description="FH6 OCR Scanner — background window OCR for Forza Horizon 6"
    )
    parser.add_argument(
        "--watch",
        "-w",
        type=float,
        default=0,
        help="Watch mode: scan every N seconds",
    )
    parser.add_argument(
        "--process",
        "-p",
        default="forzahorizon6.exe",
        help="Target process name",
    )
    parser.add_argument(
        "--auto-resize",
        "-r",
        action="store_true",
        help="Auto-resize window until OCR reads clearly",
    )
    parser.add_argument(
        "--no-preflight",
        action="store_true",
        help="Skip preflight checks",
    )
    args = parser.parse_args()

    names = [args.process]
    banner(names)

    if not args.no_preflight and not preflight(names):
        sys.exit(1)

    if not args.no_preflight:
        ocr_warmup()

    if args.watch > 0:
        scan(names, verbose=False)
        watch_header(args.watch)
        try:
            while True:
                watch_tick()
                scan(names)
                time.sleep(args.watch)
        except KeyboardInterrupt:
            console.print("\n[yellow]Stopped.[/]")
    elif args.auto_resize:
        result = scan_auto_resize(names)
        run_wheelspin_menu(result)
    else:
        result = scan(names)
        run_wheelspin_menu(result)


if __name__ == "__main__":
    main()
