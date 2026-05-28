"""Terminal colour / encoding helpers."""

import sys
from colorama import init, Fore, Style

init(autoreset=False)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

C = Fore.CYAN
G = Fore.GREEN
Y = Fore.YELLOW
R = Fore.RED
M = Fore.MAGENTA
B = Style.BRIGHT
N = Style.RESET_ALL


def say(msg: str, color: str = "") -> None:
    print(f"{color}{msg}{N}", flush=True)


def ok(msg: str) -> None:
    say(f"  ✓ {msg}", G)


def warn(msg: str) -> None:
    say(f"  ⚠ {msg}", Y)


def fail(msg: str) -> None:
    say(f"  ✗ {msg}", R)


def info(msg: str) -> None:
    say(f"  {msg}", "")


def head(msg: str) -> None:
    say(f"{B}{C}{msg}{N}")
