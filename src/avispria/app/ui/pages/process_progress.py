# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The live progress of a processing job: friendly steps, a progress bar and notes."""

from __future__ import annotations

from collections.abc import Sequence

from nicegui import ui

from avispria.app.ui.jobs import JobEvent

STEP_TEXT = {
    "Photos": "Reading your photos",
    "Capture check": "Checking the photos",
    "Processing engine": "Connecting to the map-making engine",
    "This computer": "Checking this computer",
    "Preparing photos": "Preparing the photos",
    "Uploading": "Sending the photos to the engine",
    "Processing": "Making the maps (this takes a while)",
    "Downloading results": "Collecting the results",
    "Result quality": "Checking the result",
}


class ProgressPanel:
    """Shows what a running job reports. Feed it the events a ``QueueReporter`` collected."""

    def __init__(self, box: ui.column) -> None:
        with box:
            ui.label("Progress").classes("text-lg font-bold")
            self._steps = ui.column().classes("w-full gap-1")
            self._bar = ui.linear_progress(value=0, show_value=False).classes("w-full")
            self._status = ui.label("").classes("text-sm text-gray-700")
        self._current: ui.column | None = None
        self._header: ui.row | None = None
        self._title = ""

    def apply(self, events: Sequence[JobEvent]) -> None:
        for event in events:
            if event.kind == "step":
                self._start(event.text)
            elif event.kind == "info":
                self._line(event.text, "text-sm text-gray-700")
            elif event.kind == "warn":
                self._line(f"Note: {event.text}", "text-sm text-amber-800")
            elif event.kind == "upload":
                self._bar.set_value(event.percent / 100.0)
                self._status.set_text(f"Sending photos to the engine: {event.percent:.0f}%")
            else:
                self._bar.set_value(event.percent / 100.0)
                self._status.set_text(f"{event.text.capitalize()}: {event.percent:.0f}%")

    def _start(self, title: str) -> None:
        self._close(done=True)
        with self._steps:
            self._current = ui.column().classes("gap-0 w-full")
        with self._current:
            self._header = ui.row().classes("items-center gap-2 no-wrap")
        self._title = STEP_TEXT.get(title, title)
        with self._header:
            ui.spinner(size="sm")
            ui.label(self._title).classes("font-medium")

    def _line(self, text: str, classes: str) -> None:
        if self._current is not None:
            with self._current:
                ui.label(text).classes(f"{classes} pl-8")

    def _close(self, *, done: bool) -> None:
        if self._header is None:
            return
        self._header.clear()
        with self._header:
            ui.icon("check_circle" if done else "cancel").classes(
                "text-xl " + ("text-green-700" if done else "text-red-700")
            )
            ui.label(self._title).classes("font-medium")
        self._header = None

    def finish(self, *, ok: bool) -> None:
        """Mark the last step as finished (or failed) and stop the bar."""
        self._close(done=ok)
        self._bar.set_value(1.0 if ok else self._bar.value)
