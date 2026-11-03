# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fly: step 3. Nothing to do on the computer: what to check, and what to do after landing."""

from __future__ import annotations

from nicegui import ui

from avispria.app.ui.layout import frame
from avispria.app.ui.state import STATE

FIELD_PAGE = "https://mraz11.github.io/Avispria/"
BEFORE = (
    "In DJI Fly, open each mission and compare its waypoints and heights with the spot-check "
    "sheet (the .csv next to each mission file). If they differ, do not fly it.",
    "Charge a battery for each mission, or for two or three short ones: the plan gives the "
    "minutes.",
    "The phone page has checklists, calculators and a flight log. It works without a signal "
    "once it has been opened (address below).",
)
AT_THE_SITE = (
    "Check the rules where you fly, the wind and the GPS lock before you take off.",
    "Keep the aircraft in sight. Your hand stays ready on the sticks: you can take over at any "
    "time.",
    "A photo at every photo point needs no camera setting. If you planned with timed shot, "
    "set that interval in DJI Fly first.",
    "The first time, fly a small test area in open, flat terrain. This early version has not "
    "been flown yet, so every first result is a test.",
)
AFTER = (
    "Copy the photos from the memory card to ONE folder on this computer (all missions of a "
    "flight together).",
    "Keep the folder as it is: do not rename or edit the photos.",
    "Then go on to the next step, which checks that the photos overlap enough.",
)


def _card(title: str, lines: tuple[str, ...], marker: str) -> None:
    with ui.card().classes("w-full gap-2").mark(marker):
        ui.label(title).classes("text-lg font-bold")
        for line in lines:
            with ui.row().classes("items-start gap-2 no-wrap"):
                ui.icon("check_circle_outline").classes("av-muted")
                ui.label(line).classes("text-sm")


async def fly_page() -> None:
    with frame("Fly"):
        count = len(STATE.last_plan_files)
        if count:
            plural = "missions" if count != 1 else "mission"
            ui.label(f"Your last plan has {count} {plural}.").classes("font-medium").mark(
                "fly-plan-count"
            )
        _card("Before you leave", BEFORE, "fly-before")
        ui.link(FIELD_PAGE, FIELD_PAGE, new_tab=True).classes("text-sm")
        _card("At the site", AT_THE_SITE, "fly-site")
        _card("After landing", AFTER, "fly-after")
