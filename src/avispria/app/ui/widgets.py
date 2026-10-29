# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reusable pieces of the screens: verdict banner, tiles, explained warnings, folder browser."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from nicegui import ui

from avispria.app.ui.files import list_entries, start_folder, windows_drives
from avispria.app.ui.theme import LIGHT, Palette
from avispria.app.ui.theme_state import current
from avispria.app.ui.views import ExplainedIssue, StatusRow, Tile, Verdict

BANNER = {  # level -> (banner class, icon, icon colour class)
    "good": ("av-good", "check_circle", "av-good-text"),
    "caution": ("av-caution", "warning", "av-caution-text"),
    "problem": ("av-problem", "error", "av-problem-text"),
}
DOT = {
    "good": ("check_circle", "av-good-text"),
    "caution": ("warning", "av-caution-text"),
    "problem": ("error", "av-problem-text"),
}


def verdict_banner(verdict: Verdict) -> None:
    tone, icon, icon_colour = BANNER[verdict.level]
    with ui.row().classes(f"w-full items-center gap-3 p-4 no-wrap av-banner {tone}"):
        ui.icon(icon).classes(f"text-4xl {icon_colour}")
        with ui.column().classes("gap-0"):
            ui.label(verdict.headline).classes("text-lg font-bold")
            if verdict.detail:
                ui.label(verdict.detail)


def tile_row(tiles: Sequence[Tile]) -> None:
    with ui.row().classes("w-full gap-3"):
        for tile in tiles:
            with ui.card().classes("min-w-[13rem] grow shadow-sm"):
                ui.label(tile.label).classes("text-xs uppercase tracking-wide av-muted")
                ui.label(tile.value).classes("text-xl font-semibold")
                if tile.hint:
                    ui.label(tile.hint).classes("text-sm av-muted")


def status_rows(rows: Sequence[StatusRow]) -> None:
    with ui.column().classes("w-full gap-2"):
        for row in rows:
            icon, colour = DOT[row.level]
            with ui.row().classes("w-full items-start gap-3 no-wrap"):
                ui.icon(icon).classes(f"text-2xl {colour}")
                with ui.column().classes("gap-0"):
                    ui.label(f"{row.label}: {row.value}").classes("font-medium")
                    if row.hint:
                        ui.label(row.hint).classes("text-sm av-muted")


def issue_cards(issues: Sequence[ExplainedIssue]) -> None:
    """Each warning with what it means and what to do, errors opened first."""
    for issue in issues:
        title = issue.title + (f"  (x{issue.count})" if issue.count > 1 else "")
        icon = "error" if issue.level == "error" else "info"
        with (
            ui.expansion(title, icon=icon, value=issue.level == "error").classes(
                "w-full border rounded-lg"
            ),
            ui.column().classes("gap-1 p-2"),
        ):
            if issue.meaning:
                ui.label(issue.meaning)
            if issue.action:
                ui.label("What to do: " + issue.action).classes("font-medium")
            ui.label(f"{issue.code}: {issue.detail}").classes("text-xs av-muted break-all")


def echart(builder: Callable[[Palette], dict[str, Any]]) -> None:
    """A chart in the page's colours; it redraws itself when light or dark mode changes."""
    state = current()
    options = builder(LIGHT if state is None else state.palette)
    if not options:
        return
    chart = ui.echart(options).classes("w-full h-[26rem]")
    if state is None:
        return

    def redraw(palette: Palette) -> bool:
        if chart.is_deleted:
            return False  # the result was cleared: stop listening
        chart.options.clear()
        chart.options.update(builder(palette))
        chart.update()
        return True

    state.on_change(redraw)


# --------------------------------------------------------- folder and file browser
async def pick_path(
    start: str, *, directory: bool, suffixes: Sequence[str] | None, title: str
) -> str | None:
    """Let the user browse this computer; returns the chosen path or None."""
    where = {"folder": start_folder(start)}
    with ui.dialog() as dialog, ui.card().classes("w-[42rem] max-w-full"):
        ui.label(title).classes("text-lg font-bold")
        location = ui.label().classes("text-sm av-muted break-all")
        listing = ui.column().classes("w-full max-h-[22rem] overflow-auto gap-0")
        with ui.row().classes("w-full justify-between"):
            if directory:
                ui.button(
                    "Use this folder",
                    icon="check",
                    on_click=lambda: dialog.submit(str(where["folder"])),
                )
            ui.button("Cancel", on_click=lambda: dialog.submit(None)).props("flat")

    def go(folder: Path) -> None:
        where["folder"] = folder
        refresh()

    def refresh() -> None:
        folder = where["folder"]
        location.set_text(str(folder))
        listing.clear()
        with listing:
            drives = windows_drives()
            if drives:
                with ui.row().classes("gap-1 pb-2"):
                    for drive in drives:
                        ui.button(str(drive), on_click=lambda d=drive: go(d)).props("dense outline")
            if folder.parent != folder:
                ui.button(
                    "Up one level", icon="arrow_upward", on_click=lambda: go(folder.parent)
                ).props("flat no-caps align=left").classes("w-full")
            for entry in list_entries(folder, directories_only=directory, suffixes=suffixes):
                if entry.is_dir:
                    ui.button(entry.name, icon="folder", on_click=lambda p=entry.path: go(p)).props(
                        "flat no-caps align=left"
                    ).classes("w-full")
                else:
                    ui.button(
                        entry.name,
                        icon="description",
                        on_click=lambda p=entry.path: dialog.submit(str(p)),
                    ).props("flat no-caps align=left").classes("w-full")

    refresh()
    result = await dialog
    dialog.delete()
    return result


class PathField:
    """A text box with a Browse button, for a folder or a file."""

    def __init__(
        self,
        label: str,
        *,
        directory: bool = True,
        suffixes: Sequence[str] | None = None,
        value: str = "",
        hint: str = "",
        on_change: Callable[[], None] | None = None,
        marker: str = "",
    ) -> None:
        self.label, self.directory, self.suffixes = label, directory, suffixes
        self._on_change = on_change
        with ui.column().classes("w-full gap-0"):
            with ui.row().classes("w-full items-center gap-2 no-wrap"):
                self.input = (
                    ui.input(label, value=value, on_change=self._changed)
                    .classes("grow")
                    .props("outlined dense")
                )
                browse = ui.button("Browse...", icon="folder_open", on_click=self.browse).props(
                    "outline no-caps"
                )
                if marker:  # a stable name to find each field by (used by the tests)
                    self.input.mark(f"{marker}-input")
                    browse.mark(f"{marker}-browse")
            if hint:
                ui.label(hint).classes("text-xs av-muted")

    def _changed(self) -> None:
        if self._on_change is not None:
            self._on_change()

    @property
    def value(self) -> str:
        return (self.input.value or "").strip()

    def set(self, value: str) -> None:
        self.input.set_value(value)

    async def browse(self) -> None:
        picked = await pick_path(
            self.value,
            directory=self.directory,
            suffixes=self.suffixes,
            title=f"Choose: {self.label}",
        )
        if picked:
            self.input.set_value(picked)
