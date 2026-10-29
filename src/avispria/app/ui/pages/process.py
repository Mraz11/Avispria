# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Make maps: turn a folder of photos into an orthophoto, surface model and point cloud."""

from __future__ import annotations

import threading
from pathlib import Path

from nicegui import ui

from avispria.app.ui.jobs import QueueReporter, run_job
from avispria.app.ui.layout import frame
from avispria.app.ui.pages.process_progress import ProgressPanel
from avispria.app.ui.pages.process_results import show_feasibility, show_result
from avispria.app.ui.process_job import (
    PHOTO_SIZES,
    ProcessForm,
    ProcessFormError,
    build_request,
    check_computer,
    default_output,
    execute_process,
)
from avispria.app.ui.state import STATE
from avispria.app.ui.widgets import PathField

PRESET_TEXT = {
    "fast": "Fast: the map only, quickest and needs the least memory",
    "standard": "Standard: the map, a surface model and a point cloud (recommended)",
    "detailed": "Detailed: adds a terrain model and a denser point cloud (slower)",
}


def _problem(box: ui.column, text: str) -> None:
    with box:
        ui.label(text).classes("text-red-700 font-medium")


async def process_page() -> None:
    cancel = threading.Event()
    suggested = {"out": ""}
    with frame("Make maps"):
        ui.label(
            "Turn your photos into an orthophoto (a map made of your photos), a surface model "
            "and a point cloud. This uses WebODM on this computer, so WebODM must be running. "
            "Nothing is uploaded to the internet."
        ).classes("text-base")

        def folder_changed() -> None:
            wanted = default_output(folder.value)
            if not out.value or out.value == suggested["out"]:
                out.set(wanted)
                suggested["out"] = wanted

        folder = PathField(
            "Photo folder",
            value=STATE.photo_folder,
            marker="photos",
            on_change=folder_changed,
            hint="Use the original photos from your drone.",
        )
        recursive = ui.switch("Include photos in subfolders").mark("recursive-switch")
        out = PathField(
            "Where to save the results",
            marker="out",
            value=default_output(STATE.photo_folder),
            hint="A new folder is made. Results can be several gigabytes.",
        )
        suggested["out"] = out.value
        preset = ui.radio(PRESET_TEXT, value="standard").mark("preset-radio")
        with (
            ui.expansion("Advanced", icon="tune").classes("w-full border rounded-lg"),
            ui.column().classes("gap-3 p-2"),
        ):
            size = (
                ui.select(PHOTO_SIZES, value="12.2", label="Photo size for processing")
                .props("outlined dense")
                .classes("w-80")
                .mark("size-select")
            )
            ui.label(
                "Smaller photos need much less memory and time, at the cost of some detail. "
                "12 MP is the usual choice."
            ).classes("text-xs text-gray-500")
            force = ui.switch("Start even if this computer looks too small").mark("force-switch")
        with ui.row().classes("gap-3 items-center"):
            check_button = (
                ui.button("Check this computer for this job", icon="memory")
                .props("outline no-caps")
                .mark("check-button")
            )
            start_button = (
                ui.button("Start making maps", icon="play_arrow")
                .props("no-caps size=lg")
                .mark("start-button")
            )
            cancel_button = (
                ui.button("Cancel", icon="stop", color="negative")
                .props("no-caps")
                .mark("cancel-button")
            )
            cancel_button.set_visibility(False)
        check_box = ui.column().classes("w-full gap-3")
        progress_box = ui.column().classes("w-full gap-2")
        result_box = ui.column().classes("w-full gap-3")

    def collect() -> ProcessForm:
        return ProcessForm(
            folder=folder.value,
            out_dir=out.value,
            preset=preset.value,
            recursive=bool(recursive.value),
            photo_size=str(size.value),
            force=bool(force.value),
        )

    async def check() -> None:
        check_box.clear()
        form = collect()
        try:
            build_request(form)
        except ProcessFormError as exc:
            _problem(check_box, str(exc))
            return
        with check_box:
            ui.spinner(size="lg")
            ui.label("Checking this computer and your photos...")
        outcome = await run_job(check_computer, form)
        check_box.clear()
        if not outcome.ok or outcome.value is None:
            _problem(check_box, outcome.error or "The check did not finish.")
            return
        show_feasibility(check_box, outcome.value)

    async def start() -> None:
        check_box.clear()
        progress_box.clear()
        result_box.clear()
        form = collect()
        try:
            build_request(form)
        except ProcessFormError as exc:
            _problem(result_box, str(exc))
            return
        cancel.clear()
        reporter = QueueReporter()
        panel = ProgressPanel(progress_box)
        with progress_box:
            timer = ui.timer(0.3, lambda: panel.apply(reporter.drain()))
        start_button.disable()
        check_button.disable()
        cancel_button.set_visibility(True)
        outcome = await run_job(execute_process, form, reporter, cancel)
        timer.cancel()
        panel.apply(reporter.drain())
        cancel_button.set_visibility(False)
        start_button.enable()
        check_button.enable()
        STATE.photo_folder = form.folder
        done = outcome.ok and outcome.value is not None and outcome.value.outcome is not None
        completed = done and outcome.value.outcome.completed  # type: ignore[union-attr]
        panel.finish(ok=bool(completed))
        if not outcome.ok or outcome.value is None:
            _problem(result_box, outcome.error or "The job did not finish.")
            return
        out_dir = Path(form.out_dir.strip() or default_output(form.folder)).expanduser()
        show_result(result_box, outcome.value, out_dir)

    def stop() -> None:
        cancel.set()
        ui.notify(
            "Stopping... if photos are still being sent, this happens when sending is done.",
            type="info",
        )

    check_button.on_click(check)
    start_button.on_click(start)
    cancel_button.on_click(stop)
