# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The Start screen: what the program does, what your computer can do, and where to go."""

from __future__ import annotations

from pathlib import Path

from nicegui import ui

from avispria.app.doctor import run_doctor
from avispria.app.ui.jobs import run_job
from avispria.app.ui.layout import TAGLINE, frame, logo
from avispria.app.ui.views import system_rows
from avispria.app.ui.widgets import status_rows

TASKS = (
    (
        "Check my photos",
        "See whether your photos overlap enough and where the weak spots are, before you "
        "spend hours processing them.",
        "/check",
        "photo_library",
    ),
    (
        "Plan a flight",
        "Describe the area you want to map and get missions for DJI Fly, with a prediction "
        "of the resolution and overlap you will really get.",
        "/plan",
        "flight",
    ),
    (
        "Make maps",
        "Turn your photos into an orthophoto, a surface model and a point cloud, using "
        "WebODM on this computer.",
        "/process",
        "map",
    ),
)


async def home_page() -> None:
    with frame("Start"):
        with ui.card().classes("w-full"), ui.row().classes("items-center gap-6 no-wrap"):
            logo("av-hero-logo")
            with ui.column().classes("gap-1"):
                ui.label("Welcome to Avispria").classes("text-xl font-bold")
                ui.label(TAGLINE).classes("av-muted")
                ui.label(
                    "Plan drone flights, check your photos and turn them into maps, all on your "
                    "own computer. Nothing is sent anywhere."
                )
        with ui.row().classes("w-full gap-4"):
            for title, text, target, icon in TASKS:
                with ui.card().classes("min-w-[16rem] grow"):
                    with ui.row().classes("items-center gap-2"):
                        ui.icon(icon).classes("text-3xl text-primary")
                        ui.label(title).classes("text-lg font-bold")
                    ui.label(text).classes("text-sm av-muted")
                    ui.button("Open", on_click=lambda t=target: ui.navigate.to(t)).props(
                        "no-caps"
                    ).mark(f"open-{target.strip('/')}")
        with ui.card().classes("w-full"):
            ui.label("Your computer").classes("text-lg font-bold")
            box = ui.column().classes("w-full")
            with box:
                ui.spinner()
                ui.label("Checking your computer...")
        with ui.card().classes("w-full av-note-caution"):
            ui.label("Before you fly").classes("font-bold")
            ui.label(
                "Plans and checks are aids, not guarantees. This early version has not been "
                "flown yet: try a small test area in open, flat terrain first, keep the drone "
                "in sight, and follow the rules that apply where you fly."
            ).classes("text-sm")
    await ui.context.client.connected()
    result = await run_job(run_doctor, Path.home())
    box.clear()
    with box:
        if result.ok and result.value is not None:
            status_rows(system_rows(result.value))
        else:
            ui.label(f"Could not check this computer: {result.error}").classes("av-problem-text")
