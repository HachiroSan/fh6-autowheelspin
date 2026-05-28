"""Live terminal dashboard for active wheelspin automation."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Literal

from rich import box
from rich.console import Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TaskProgressColumn, TextColumn
from rich.table import Table

from mega666.ui import console


def wheelspin_display_name(wheel_type: str) -> str:
    return "Super Wheelspin" if wheel_type == "super" else "Wheelspin"


WheelspinMenuSelection = Literal["super", "regular"]
WheelspinMenuMode = Literal["count", "all"]


@dataclass(frozen=True)
class WheelspinMenuChoice:
    wheel_type: WheelspinMenuSelection
    mode: WheelspinMenuMode


@dataclass(frozen=True)
class WheelspinMenuOption:
    key: str
    wheel_type: WheelspinMenuSelection | None
    mode: WheelspinMenuMode | None
    label: str
    enabled: bool = True


def _read_menu_key() -> str:
    """Read one keypress, including Windows arrow-key escape sequences."""
    try:
        import msvcrt
    except ImportError:
        return console.input("Select › ").strip().lower()

    key = msvcrt.getwch()
    if key in {"\x00", "\xe0"}:
        key = msvcrt.getwch()
        return {
            "H": "up",
            "P": "down",
            "K": "left",
            "M": "right",
        }.get(key, "")
    if key == "\r":
        return "enter"
    if key == "\x1b":
        return "escape"
    return key.lower()


def _next_enabled_index(
    options: list[WheelspinMenuOption], current: int, direction: int
) -> int:
    if not options:
        return current
    index = current
    for _ in range(len(options)):
        index = (index + direction) % len(options)
        if options[index].enabled:
            return index
    return current


def _render_wheelspin_menu(
    options: list[WheelspinMenuOption], selected_index: int, message: str = ""
):
    table = Table.grid(expand=True)
    table.add_column(justify="center", width=3)
    table.add_column(justify="center", width=5)
    table.add_column(ratio=1)
    table.add_column(justify="right")

    for index, option in enumerate(options):
        selected = index == selected_index
        cursor = "[bold bright_magenta]›[/]" if selected else " "

        if option.enabled:
            key_style = "bold cyan"
            label_style = "bold white" if selected else "white"
            if option.mode == "all":
                state = "[bright_magenta]until empty[/]"
            elif option.mode == "count":
                state = "[bright_black]ask amount[/]"
            else:
                state = ""
        else:
            key_style = "bright_black"
            label_style = "bright_black"
            state = "[bright_black]unavailable[/]"

        if selected and option.enabled:
            label = f"[reverse {label_style}] {option.label} [/]"
        else:
            label = f"[{label_style}]{option.label}[/]"

        table.add_row(cursor, f"[{key_style}]{option.key}[/]", label, state)

    help_text = (
        "[bright_black]↑/↓ move  Enter select  1-4 quick select  Esc/Q quit[/]"
    )
    if message:
        help_text = f"[yellow]{message}[/]\n{help_text}"

    return Panel(
        Group(table, help_text),
        title="WHEELSPIN MENU",
        border_style="bright_magenta",
        box=box.ROUNDED,
        padding=(1, 2),
    )


def select_wheelspin_menu(
    super_spin: dict | None, regular_spin: dict | None
) -> WheelspinMenuChoice | None:
    """Interactive TUI selector for the detected wheelspin tiles."""
    super_enabled = super_spin is not None and (super_spin.get("available") or 0) > 0
    regular_enabled = regular_spin is not None and (regular_spin.get("available") or 0) > 0
    options = [
        WheelspinMenuOption(
            key="1",
            wheel_type="super",
            mode="count",
            label="[green]Auto[/] Super Wheelspin",
            enabled=super_enabled,
        ),
        WheelspinMenuOption(
            key="2",
            wheel_type="regular",
            mode="count",
            label="[green]Auto[/] Wheelspin",
            enabled=regular_enabled,
        ),
        WheelspinMenuOption(
            key="3",
            wheel_type="super",
            mode="all",
            label="[green]Auto[/] Super Wheelspin [bright_magenta](Indefinitely)[/]",
            enabled=super_enabled,
        ),
        WheelspinMenuOption(
            key="4",
            wheel_type="regular",
            mode="all",
            label="[green]Auto[/] Wheelspin [bright_magenta](Indefinitely)[/]",
            enabled=regular_enabled,
        ),
        WheelspinMenuOption(key="0", wheel_type=None, mode=None, label="Exit", enabled=True),
    ]

    selected_index = next(
        (index for index, option in enumerate(options) if option.enabled),
        len(options) - 1,
    )
    message = ""

    with Live(
        _render_wheelspin_menu(options, selected_index, message),
        console=console,
        refresh_per_second=12,
        transient=False,
    ) as live:
        while True:
            key = _read_menu_key()
            if key in {"up", "left", "w", "k"}:
                selected_index = _next_enabled_index(options, selected_index, -1)
                message = ""
            elif key in {"down", "right", "s", "j"}:
                selected_index = _next_enabled_index(options, selected_index, 1)
                message = ""
            elif key in {"enter", " "}:
                option = options[selected_index]
                if option.enabled and option.wheel_type is not None and option.mode is not None:
                    return WheelspinMenuChoice(option.wheel_type, option.mode)
                if option.enabled:
                    return None
                message = f"{option.label} is unavailable."
            elif key in {"escape", "q", "e"}:
                return None
            elif key in {"0", "1", "2", "3", "4"}:
                option = next(option for option in options if option.key == key)
                if option.enabled and option.wheel_type is not None and option.mode is not None:
                    return WheelspinMenuChoice(option.wheel_type, option.mode)
                if option.enabled:
                    return None
                message = f"{option.label} is unavailable."
            else:
                message = "Choose an available option."

            live.update(_render_wheelspin_menu(options, selected_index, message))


def _format_duration(seconds: float | None) -> str:
    if seconds is None or seconds < 0:
        return "--:--"
    seconds = int(seconds)
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


@dataclass
class SpinSessionState:
    wheel_type: str
    start_count: int
    target_count: int
    current_count: int
    status: str = "Starting"
    latest_event: str = "Preparing automation"
    graceful_stop_requested: bool = False
    started_at: float = field(default_factory=time.perf_counter)
    last_update_at: float = field(default_factory=time.perf_counter)
    last_spin_completed_at: float | None = None
    seconds_per_spin_samples: list[float] = field(default_factory=list)

    @property
    def name(self) -> str:
        return wheelspin_display_name(self.wheel_type)

    @property
    def total_spins(self) -> int:
        return max(self.start_count - self.target_count, 0)

    @property
    def completed_spins(self) -> int:
        return min(max(self.start_count - self.current_count, 0), self.total_spins)

    @property
    def remaining_spins(self) -> int:
        return max(self.total_spins - self.completed_spins, 0)

    @property
    def elapsed(self) -> float:
        return max(time.perf_counter() - self.started_at, 0.0)

    @property
    def average_seconds_per_spin(self) -> float | None:
        if not self.seconds_per_spin_samples:
            return None

        lifetime_average = sum(self.seconds_per_spin_samples) / len(self.seconds_per_spin_samples)
        recent_samples = self.seconds_per_spin_samples[-5:]
        recent_average = sum(recent_samples) / len(recent_samples)

        # Blend long-term stability with recent performance.  This avoids ETA
        # jumping around on a single slow scan while still adapting over time.
        return (lifetime_average * 0.7) + (recent_average * 0.3)

    @property
    def eta_seconds(self) -> float | None:
        average = self.average_seconds_per_spin
        if average is None:
            return None
        return average * self.remaining_spins

    def event(
        self,
        message: str,
        *,
        status: str | None = None,
        current_count: int | None = None,
    ) -> None:
        now = time.perf_counter()
        self.latest_event = message
        if status is not None:
            self.status = status
        if current_count is not None:
            previous_count = self.current_count
            self.current_count = current_count
            completed = max(previous_count - current_count, 0)
            if completed:
                previous_completed_at = self.last_spin_completed_at or self.started_at
                seconds_per_spin = max((now - previous_completed_at) / completed, 0.0)
                self.seconds_per_spin_samples.extend([seconds_per_spin] * completed)
                self.last_spin_completed_at = now
        self.last_update_at = now


class SpinLiveView:
    """Small wrapper around Rich Live for a stable auto-spin dashboard."""

    def __init__(self, state: SpinSessionState, *, debug: bool = False) -> None:
        self.state = state
        self.debug = debug
        self._live: Live | None = None

    def __enter__(self) -> "SpinLiveView":
        live = Live(
            console=console,
            refresh_per_second=1,
            transient=False,
            get_renderable=self.render,
        )
        self._live = live
        live.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._live is not None:
            self._live.update(self.render())
            self._live.__exit__(exc_type, exc, tb)

    def event(
        self,
        message: str,
        *,
        status: str | None = None,
        current_count: int | None = None,
    ) -> None:
        self.state.event(message, status=status, current_count=current_count)
        if self.debug:
            console.print(message)
        self.refresh()

    def refresh(self) -> None:
        if self._live is not None:
            self._live.update(self.render())

    def poll_graceful_stop(self) -> bool:
        return self.state.graceful_stop_requested

    def request_graceful_stop(self) -> None:
        if self.state.graceful_stop_requested:
            return
        self.state.graceful_stop_requested = True
        self.event(
            "User-triggered stop received. Press Ctrl+C again to force exit.",
            status="User stop requested",
        )

    def render(self):
        average = self.state.average_seconds_per_spin
        avg_text = "--" if average is None else f"{average:.1f}s"

        summary = Table.grid(expand=True)
        summary.add_column(ratio=1)
        summary.add_column(justify="right")
        summary.add_row(
            f"[bold white]{self.state.name}[/]",
            f"[bold bright_magenta]{self.state.status}[/]",
        )
        summary.add_row(
            (
                f"[bright_black]Count[/] [bold yellow]{self.state.current_count}[/]"
                f" [bright_black]/ start[/] {self.state.start_count}"
                f" [bright_black]/ target[/] {self.state.target_count}"
            ),
            (
                f"[bright_black]Spins[/] [bold green]{self.state.completed_spins}[/]"
                f"[bright_black]/{self.state.total_spins}[/]"
            ),
        )

        progress = Progress(
            TextColumn("[bright_black]Progress[/]"),
            BarColumn(bar_width=None),
            TaskProgressColumn(),
            expand=True,
        )
        progress.add_task(
            "spins",
            total=max(self.state.total_spins, 1),
            completed=self.state.completed_spins,
        )

        metrics = Table(
            box=None,
            show_header=False,
            expand=True,
            padding=(0, 1),
        )
        metrics.add_column(style="bright_black")
        metrics.add_column(style="bold cyan", justify="right")
        metrics.add_column(style="bright_black")
        metrics.add_column(style="bold cyan", justify="right")
        metrics.add_column(style="bright_black")
        metrics.add_column(style="bold cyan", justify="right")
        metrics.add_row(
            "Elapsed",
            _format_duration(self.state.elapsed),
            "ETA",
            _format_duration(self.state.eta_seconds),
            "Avg/spin",
            avg_text,
        )
        metrics.add_row(
            "Remaining",
            str(self.state.remaining_spins),
            "Started",
            str(self.state.start_count),
            "Target",
            str(self.state.target_count),
        )

        latest = Panel(
            self.state.latest_event,
            title="CURRENT ACTION",
            border_style="yellow" if self.state.graceful_stop_requested else "bright_black",
            box=box.ROUNDED,
        )

        sections = [summary, progress, metrics]

        if self.state.graceful_stop_requested:
            sections.append(
                Panel(
                    "[bold bright_red]USER STOP TRIGGERED[/]\n"
                    "[white]Finishing the current reward flow. "
                    "press Ctrl+C again to force exit.",
                    title="USER-TRIGGERED STOP",
                    border_style="bright_red",
                    box=box.ROUNDED,
                )
            )

        sections.append(latest)

        shortcut = Panel(
            (
                "[bold bright_red]Stop queued. Press Ctrl+C again to force exit.[/]"
                if self.state.graceful_stop_requested
                else "[bold yellow]Ctrl+C[/] graceful stop after current spin"
            ),
            title="SHORTCUT",
            border_style="bright_red" if self.state.graceful_stop_requested else "bright_black",
            box=box.ROUNDED,
        )
        sections.append(shortcut)

        return Panel(
            Group(*sections),
            title="AUTO SPIN",
            border_style="bright_red" if self.state.graceful_stop_requested else "bright_magenta",
            box=box.ROUNDED,
            padding=(1, 2),
        )
