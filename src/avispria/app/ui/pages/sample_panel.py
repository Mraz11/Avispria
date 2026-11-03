# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The sample mission, where it is needed: one button takes it from the phone.

Planning needs one mission made by DJI Fly, to copy the exact format of this aircraft. It used to be
fetched on another screen; this panel does it in place (Plan a flight, Start).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from nicegui import ui

from avispria.app.ui.jobs import run_job
from avispria.app.ui.pages.phone_help import FIRST_TIME
from avispria.app.ui.phone_job import fetch_sample
from avispria.app.ui.state import STATE

WHY = (
    "Avispria copies the exact format your DJI Fly uses from one mission that DJI Fly made. You do "
    "this once; it is remembered the next time."
)
HOW = (
    "Connect the phone to this computer with the USB cable, unlock it, and press the button. "
    "DJI Fly must hold at least one saved waypoint mission (Waypoint Flight, two points, Save)."
)


def sample_exists() -> bool:
    return bool(STATE.sample_mission) and Path(STATE.sample_mission).is_file()


class SamplePanel:
    """Shows whether a sample mission is known and gets one from the phone on request."""

    def __init__(self, on_found: Callable[[str], None] | None = None) -> None:
        self._on_found = on_found
        with ui.column().classes("w-full gap-2").mark("sample-panel"):
            self.status = ui.label().classes("font-medium").mark("sample-status")
            self.help = ui.label(f"{WHY} {HOW}").classes("text-sm av-muted")
            with ui.row().classes("items-center gap-3"):
                self.button = (
                    ui.button("Get it from my phone", icon="phone_android", on_click=self.fetch)
                    .props("no-caps outline")
                    .mark("sample-from-phone")
                )
                self.spinner = ui.spinner(size="sm")
                self.spinner.set_visibility(False)
            self.message = ui.label().classes("text-sm av-problem-text").mark("sample-message")
            with ui.expansion("First time? Switch on USB debugging on the phone (once)").classes(
                "w-full"
            ):
                ui.label(FIRST_TIME).classes("text-sm whitespace-pre-line")
        self.refresh()

    def refresh(self) -> None:
        if sample_exists():
            self.status.set_text(f"Sample mission: {Path(STATE.sample_mission).name}")
            self.status.classes(remove="av-problem-text")
            self.help.set_visibility(False)
            self.button.set_text("Get a different one from my phone")
        else:
            self.status.set_text("No sample mission yet.")
            self.help.set_visibility(True)
            self.button.set_text("Get it from my phone")
        self.message.set_text("")

    async def fetch(self) -> None:
        self.button.disable()
        self.spinner.set_visibility(True)
        self.message.set_text("")
        result = await run_job(fetch_sample, STATE.adb_path)
        self.spinner.set_visibility(False)
        self.button.enable()
        if not result.ok or result.value is None:
            self.message.set_text(result.error or "The sample mission could not be copied.")
            return
        STATE.sample_mission = str(result.value)
        self.refresh()
        ui.notify(f"Got {result.value.name} from your phone.", type="positive")
        if self._on_found is not None:
            self._on_found(str(result.value))
