"""Rich terminal UI components for MEGA666."""

from __future__ import annotations

import time
from collections.abc import Iterable

from rich import box
from rich.align import Align
from rich.console import Console, Group
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text

console = Console(highlight=False)

ASCII_ART = r"""
███╗   ███╗███████╗ ██████╗  █████╗  ██████╗  ██████╗  ██████╗
████╗ ████║██╔════╝██╔════╝ ██╔══██╗██╔════╝ ██╔════╝ ██╔════╝
██╔████╔██║█████╗  ██║  ███╗███████║███████╗ ███████╗ ███████╗
██║╚██╔╝██║██╔══╝  ██║   ██║██╔══██║██╔═══██╗██╔═══██╗██╔═══██╗
██║ ╚═╝ ██║███████╗╚██████╔╝██║  ██║╚██████╔╝╚██████╔╝╚██████╔╝
╚═╝     ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝ ╚═════╝  ╚═════╝  ╚═════╝
""".strip("\n")


def banner(process_names: Iterable[str] | None = None) -> None:
    """Render the application hero banner."""
    subtitle = Text("by Hachiro", style="bright_black")
    console.print()
    console.print(
        Panel(
            Group(
                Align.center(Text(ASCII_ART, style="bold bright_magenta")),
                Align.center(subtitle),
            ),
            border_style="magenta",
            box=box.ROUNDED,
            padding=(0, 1),
        )
    )


def section(title: str, caption: str | None = None) -> None:
    """Render a compact section heading."""
    text = Text(title.upper(), style="bold cyan")
    if caption:
        text.append(f"  {caption}", style="bright_black")
    console.rule(text, style="bright_black")


def preflight_row(name: str, state: str, detail: str) -> None:
    """Print one preflight result row."""
    styles = {
        "ok": ("✓", "green"),
        "warn": ("!", "yellow"),
        "fail": ("×", "red"),
    }
    icon, style = styles.get(state, ("•", "white"))
    console.print(
        f"  [{style}]{icon}[/] [bold]{name}[/] [bright_black]—[/] {detail}"
    )


def preflight_summary(ok: bool) -> None:
    """Render final preflight result."""
    if ok:
        console.print(
            Panel.fit(
                "[bold green]SYSTEM READY[/] [bright_black]— capture, OCR, and Win32 checks are online[/]",
                border_style="green",
                box=box.ROUNDED,
            )
        )
    else:
        console.print(
            Panel.fit(
                "[bold red]PREFLIGHT BLOCKED[/] [bright_black]— fix the failed checks and run again[/]",
                border_style="red",
                box=box.ROUNDED,
            )
        )


def run_with_spinner(label: str, func):
    """Run a callable while showing a modern terminal spinner."""
    with Progress(
        SpinnerColumn("dots12", style="bright_magenta"),
        TextColumn("[bold cyan]{task.description}"),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task(label, total=None)
        started = time.perf_counter()
        result = func()
    elapsed_ms = (time.perf_counter() - started) * 1000
    console.print(f"  [green]✓[/] [bold]{label}[/] [bright_black]{elapsed_ms:.0f}ms[/]")
    return result


def render_scan_result(result: dict) -> None:
    """Render scanner output as a compact dashboard."""
    win = result["window"]
    wheelspins = result["ui"]["wheelspins"]

    process = Table.grid(expand=True)
    process.add_column(style="bright_black", ratio=1)
    process.add_column(ratio=2)
    process.add_column(style="bright_black", ratio=1)
    process.add_column(ratio=1)
    process.add_row("Process", f"[green]{win['name']}[/]", "Window", f"[magenta]{win['w']}×{win['h']}[/]")
    process.add_row("PID", str(win["pid"]), "Title", win["title"])

    rewards = _wheelspin_table(wheelspins)

    console.print(
        Panel(
            Group(process, rewards),
            title="MAIN",
            border_style="cyan",
            box=box.ROUNDED,
            padding=(1, 2),
        )
    )


def _wheelspin_table(wheelspins: list[dict]) -> Table | Panel:
    if not wheelspins:
        return Panel(
            "[bold yellow]No wheelspins detected[/]\n\n"
            "[white]Open Forza and go to [bold cyan]My Horizon tab[/][/]\n"
            "[bright_black]Make sure both wheelspin counts are visible and readable.[/]\n\n"
            "[bright_black]If the text is too small:[/]\n"
            "[bright_black]1.[/] Resize the window wider\n"
            "[bright_black]2.[/] Increase the desktop resolution\n"
            "[bright_black]3.[/] Or run with [cyan]--auto-resize[/]",
            border_style="yellow",
            box=box.ROUNDED,
            padding=(1, 2),
        )

    table = Table(
        box=box.SIMPLE,
        border_style="bright_black",
        header_style="bold bright_black",
        show_lines=False,
        expand=True,
        padding=(0, 1),
    )
    table.add_column("Reward", style="white")
    table.add_column("Available", justify="right", style="bold green")

    for wheelspin in wheelspins:
        count = wheelspin["available"]
        available = "?" if count is None else str(count)
        name = "Super Wheelspin" if wheelspin["type"] == "super" else "Wheelspin"
        table.add_row(name, available)

    return table


def render_wheelspins(wheelspins: list[dict]) -> None:
    """Render detected wheelspin state."""
    console.print(_wheelspin_table(wheelspins))


def render_resize_start(width: int, height: int) -> None:
    section("Auto-resize", f"starting at {width}×{height}")


def render_resize_attempt(width: int, height: int) -> None:
    console.print(f"  [cyan]↳[/] probing [bold]{width}×{height}[/]", end=" ")


def render_resize_result(result: dict | None, clear: bool) -> None:
    if result is None:
        console.print("[red]failed[/]")
        return

    wheelspins = result["ui"]["wheelspins"]
    super_spin = next((w for w in wheelspins if w["type"] == "super"), None)
    regular = next((w for w in wheelspins if w["type"] == "regular"), None)
    super_count = super_spin["available"] if super_spin else "?"
    regular_count = regular["available"] if regular else "?"
    state = "[bold green]clear[/]" if clear else "[yellow]partial[/]"
    console.print(f"{state}  Super={super_count}  Wheelspin={regular_count}")


def render_resize_exhausted() -> None:
    console.print(
        Panel(
            "[bold bright_red]Are you sure you are on the My Horizon tab?[/]\n"
            "[bright_white]If yes, manually resize the window wider (1280px+) or use a higher desktop resolution.[/]\n"
            "[bright_white]Also do not let the game window minimized.[/]\n"
            "[bright_black]Auto-resize exhausted; OCR is still not readable.[/]",
            border_style="yellow",
            box=box.ROUNDED,
        )
    )
