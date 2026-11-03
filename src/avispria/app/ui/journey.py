# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The order of a flight project, defined once.

The top bar, the Start page and every screen use this, so a person always knows where they are, what
comes before and what to do next.
"""

from __future__ import annotations

from dataclasses import dataclass

from nicegui import ui


@dataclass(frozen=True)
class Step:
    number: int
    title: str  # the screen's title
    path: str
    icon: str
    what: str  # what you do here, in one sentence


STEPS = (
    Step(
        1,
        "Plan a flight",
        "/plan",
        "edit_location_alt",
        "Choose what you want to capture, mark the place, and get missions for DJI Fly.",
    ),
    Step(
        2,
        "Send to DJI Fly",
        "/phone",
        "send",
        "Put the missions into DJI Fly on your phone, over a USB cable or Wi-Fi.",
    ),
    Step(
        3,
        "Fly",
        "/fly",
        "flight_takeoff",
        "Check the aircraft and the missions in DJI Fly, then fly. Nothing to do on the computer.",
    ),
    Step(
        4,
        "Check my photos",
        "/check",
        "photo_library",
        "Copy the photos to this computer and see whether they overlap enough.",
    ),
    Step(
        5,
        "Make maps",
        "/process",
        "map",
        "Turn the photos into a map or a 3D model with WebODM, on this computer.",
    ),
)
TOTAL = len(STEPS)
START = ("Start", "/")


def step_for(title: str) -> Step | None:
    return next((s for s in STEPS if s.title == title), None)


def nav_label(step: Step) -> str:
    return f"{step.number}. {step.title}"


def nav_items() -> tuple[tuple[str, str], ...]:
    """(label, path) of every item in the top bar, in the order a project goes."""
    return (START, *((nav_label(s), s.path) for s in STEPS))


def _link(step: Step | None, prefix: str) -> None:
    if step is not None:
        ui.link(f"{prefix} {nav_label(step)}", step.path).classes("text-sm")


def journey_bar(step: Step) -> None:
    """'Step 2 of 5': what you do here, and the steps either side."""
    with ui.card().classes("w-full av-note-info").mark("journey-bar"):
        with ui.row().classes("w-full items-center gap-3"):
            ui.badge(f"Step {step.number} of {TOTAL}").props("color=primary").mark("step-badge")
            ui.label(step.what).classes("text-sm font-medium")
        with ui.row().classes("gap-4"):
            before = STEPS[step.number - 2] if step.number > 1 else None
            after = STEPS[step.number] if step.number < TOTAL else None
            _link(before, "Before:")
            _link(after, "Next:")


def next_step_card(step: Step) -> None:
    """At the bottom of a screen: where to go once this one is done."""
    with ui.card().classes("w-full av-note-info").mark("next-step"):
        if step.number < TOTAL:
            after = STEPS[step.number]
            ui.label("When you are done here").classes("font-bold")
            ui.label(after.what).classes("text-sm")
            ui.button(
                f"Next: {nav_label(after)}",
                icon="arrow_forward",
                on_click=lambda: ui.navigate.to(after.path),
            ).props("no-caps").mark("next-step-button")
        else:
            ui.label("That is the whole journey").classes("font-bold")
            ui.label(
                "Open the results folder to see your map or model. To fly again, start from step 1."
            ).classes("text-sm")
            ui.button(
                "Start a new flight", icon="replay", on_click=lambda: ui.navigate.to("/plan")
            ).props("no-caps flat").mark("next-step-button")
