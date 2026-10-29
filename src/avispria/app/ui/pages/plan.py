# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Plan a flight: describe the area and what you want, get missions for DJI Fly."""

from __future__ import annotations

from pathlib import Path

from nicegui import ui

from avispria.adapters.profiles import load_profiles
from avispria.app.ui.jobs import run_job
from avispria.app.ui.layout import frame
from avispria.app.ui.pages.plan_form import PlanFormUi
from avispria.app.ui.pages.plan_results import show_plan
from avispria.app.ui.plan_job import execute_plan
from avispria.app.ui.state import STATE


async def plan_page() -> None:
    with frame("Plan a flight"):
        ui.label(
            "Describe the area you want to map and what you need from the photos. Avispria "
            "makes missions for DJI Fly and tells you what resolution and overlap you will "
            "really get over your terrain."
        ).classes("text-base")
        form_ui = PlanFormUi(load_profiles())
        button = ui.button("Plan the flight", icon="flight").props("no-caps size=lg").mark("run")
        results = ui.column().classes("w-full gap-4")

    async def run() -> None:
        results.clear()
        form = form_ui.collect()
        button.disable()
        with results:
            ui.spinner(size="lg")
            ui.label("Planning the flight (hilly sites take a little longer)...")
        outcome = await run_job(execute_plan, form)
        button.enable()
        results.clear()
        if not outcome.ok or outcome.value is None:
            with results:
                ui.label(outcome.error or "The plan did not finish.").classes(
                    "av-problem-text font-medium"
                )
            return
        STATE.last_output = form.out_dir
        show_plan(results, outcome.value, Path(form.out_dir).expanduser())

    button.on_click(run)
