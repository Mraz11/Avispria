# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The Start screen: what the program does, what your computer can do, and where to go."""

from __future__ import annotations

from pathlib import Path

from nicegui import ui

from avispria.app.doctor import run_doctor
from avispria.app.ui.jobs import run_job
from avispria.app.ui.journey import STEPS, nav_label
from avispria.app.ui.layout import TAGLINE, frame, logo
from avispria.app.ui.views import system_rows
from avispria.app.ui.widgets import status_rows


async def home_page() -> None:
    with frame("Start"):
        with ui.card().classes("w-full"), ui.row().classes("items-center gap-6 no-wrap"):
            logo("av-hero-logo")
            with ui.column().classes("gap-1"):
                ui.label("Welcome to Avispria").classes("text-xl font-bold")
                ui.label(TAGLINE).classes("av-muted")
                ui.label(
                    "Plan drone flights, check your photos and turn them into maps, all on your "
                    "own computer. Nothing is sent anywhere unless you ask: the map background "
                    "and the place search in the map contact OpenStreetMap, only when you use them."
                )
        ui.label("A flight project has five steps. Do them in this order.").classes(
            "text-lg font-bold"
        )
        for step in STEPS:
            first = step.number == 1
            with (
                ui.card()
                .classes("w-full" + (" av-note-info" if first else ""))
                .mark(f"step-{step.number}"),
                ui.row().classes("w-full items-center gap-4 no-wrap"),
            ):
                ui.badge(str(step.number)).props("color=primary rounded").classes("text-lg")
                ui.icon(step.icon).classes("text-3xl text-primary")
                with ui.column().classes("gap-0 grow"):
                    with ui.row().classes("items-center gap-2"):
                        ui.label(step.title).classes("text-lg font-bold")
                        if first:
                            ui.badge("Start here").props("color=positive")
                    ui.label(step.what).classes("text-sm av-muted")
                ui.button(
                    "Open" if not first else f"Start: {nav_label(step)}",
                    on_click=lambda t=step.path: ui.navigate.to(t),
                ).props("no-caps").mark(f"open-{step.path.strip('/')}")
        with ui.card().classes("w-full"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("Your computer").classes("text-lg font-bold")
                again = (
                    ui.button("Check again", icon="refresh")
                    .props("flat no-caps")
                    .mark("check-again")
                )
            box = ui.column().classes("w-full")
        with ui.card().classes("w-full av-note-caution"):
            ui.label("Before you fly").classes("font-bold")
            ui.label(
                "Plans and checks are aids, not guarantees. This early version has not been "
                "flown yet: try a small test area in open, flat terrain first, keep the drone "
                "in sight, and follow the rules that apply where you fly."
            ).classes("text-sm")

    async def check() -> None:
        again.disable()
        box.clear()
        with box:
            ui.spinner()
            ui.label("Checking your computer...")
        result = await run_job(run_doctor, Path.home())
        box.clear()
        with box:
            if result.ok and result.value is not None:
                status_rows(system_rows(result.value))
            else:
                ui.label(f"Could not check this computer: {result.error}").classes(
                    "av-problem-text"
                )
        again.enable()

    again.on_click(check)
    await ui.context.client.connected()
    await check()
