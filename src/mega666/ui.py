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
            border_style="bright_magenta",
            box=box.DOUBLE_EDGE,
            padding=(1, 2),
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


def watch_header(interval: float) -> None:
    console.print(
        Panel.fit(
            f"[bold cyan]LIVE WATCH[/] [bright_black]refresh[/] {interval:g}s  [bright_black]stop[/] Ctrl+C",
            border_style="cyan",
            box=box.ROUNDED,
        )
    )


def watch_tick() -> None:
    console.rule(f"[bright_black]{time.strftime('%H:%M:%S')}[/]", style="bright_black")


def render_scan_result(result: dict) -> None:
    """Render scanner output as a compact dashboard."""
    win = result["window"]
    timing = result["timing"]
    texts = result["texts"]
    total = timing["capture_ms"] + timing["infer_ms"]

    meta = Table.grid(expand=True)
    meta.add_column(ratio=1)
    meta.add_column(ratio=1)
    meta.add_column(ratio=1)
    meta.add_row(
        f"[bold cyan]Window[/]\n{win['title']}\n[bright_black]{win['w']}×{win['h']}[/]",
        f"[bold magenta]OCR[/]\n{len(texts)} text regions\n[bright_black]{timing['infer_ms']:.0f}ms inference[/]",
        f"[bold green]Cycle[/]\n{total:.0f}ms\n[bright_black]{timing['capture_ms']:.0f}ms capture[/]",
    )

    console.print(Panel(meta, title="SCAN", border_style="cyan", box=box.ROUNDED))
    render_wheelspins(result["ui"]["wheelspins"])


def render_wheelspins(wheelspins: list[dict]) -> None:
    """Render detected wheelspin state."""
    if not wheelspins:
        console.print(
            Panel(
                "[yellow]No wheelspins detected[/]\n"
                "[bright_black]Open the My Horizon tab. If you are already there, try using a larger game window or a higher resolution.[/]",
                title="UI STATE",
                border_style="yellow",
                box=box.ROUNDED,
            )
        )
        return

    table = Table(
        title="UI STATE",
        box=box.SIMPLE_HEAVY,
        border_style="bright_magenta",
        header_style="bold bright_magenta",
        show_lines=False,
    )
    table.add_column("Reward", style="cyan")
    table.add_column("Available", justify="right")
    table.add_column("Confidence", justify="right", style="bright_black")

    for wheelspin in wheelspins:
        count = wheelspin["available"]
        available = "[yellow]?[/]" if count is None else f"[bold green]{count}[/]"
        name = "Super Wheelspin" if wheelspin["type"] == "super" else "Wheelspin"
        table.add_row(name, available, f"{wheelspin['score']:.0%}")

    console.print(table)


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
            "[yellow]Auto-resize exhausted; OCR is still not readable.[/]\n"
            "[bright_black]Manually resize the window wider (1280px+) or use a higher desktop resolution.[/]",
            border_style="yellow",
            box=box.ROUNDED,
        )
    )
