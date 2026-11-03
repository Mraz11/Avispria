# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Where a flight project stands, and the one thing to do next.

Worked out from what the screens remember (the sample mission, the last plan, what was sent, the
photos checked), so a person never has to guess which step comes next.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from avispria.app.ui.state import STATE


@dataclass(frozen=True)
class Progress:
    has_sample: bool = False
    planned: int = 0  # missions in the last plan that are still on disk
    sent: int = 0  # missions last sent to the phone
    checked: bool = False  # photos have been checked


@dataclass(frozen=True)
class NextAction:
    step: int  # 0 = the one-time set-up, else the step of the journey
    title: str
    text: str
    path: str = ""  # where the button goes ('' = the action is on this screen)
    button: str = ""


def _present(paths: list[str]) -> int:
    return sum(1 for p in paths if Path(p).is_file())


def current_progress() -> Progress:
    return Progress(
        has_sample=bool(STATE.sample_mission) and Path(STATE.sample_mission).is_file(),
        planned=_present(STATE.last_plan_files),
        sent=len(STATE.last_sent_files),
        checked=bool(STATE.photo_folder) and Path(STATE.photo_folder).is_dir(),
    )


def step_done(number: int, p: Progress) -> bool:
    """Is a step done? Flying cannot be known: it counts once the photos have been checked."""
    return {1: p.planned > 0, 2: p.sent > 0, 3: p.checked, 4: p.checked}.get(number, False)


def _missions(n: int) -> str:
    return f"{n} mission{'s' if n != 1 else ''}"


def next_action(p: Progress) -> NextAction:
    if not p.has_sample:
        return NextAction(
            0,
            "First, once: get your sample mission from the phone",
            "Avispria needs one mission made by DJI Fly, to copy the exact format of your "
            "aircraft. You do this once; it is remembered.",
        )
    if p.planned == 0:
        return NextAction(
            1,
            "Plan your flight",
            "Choose what you want to capture, mark the place, and get missions for DJI Fly.",
            "/plan",
            "Start: 1. Plan a flight",
        )
    if p.sent == 0:
        return NextAction(
            2,
            f"Send your {_missions(p.planned)} to DJI Fly",
            "Put the missions into DJI Fly on your phone. The screen tells you if more "
            "placeholder missions are needed first.",
            "/phone",
            "Next: 2. Send to DJI Fly",
        )
    if not p.checked:
        return NextAction(
            3,
            "Fly, then check your photos",
            "Fly the missions in DJI Fly. After landing, copy the photos to this computer and "
            "check them.",
            "/fly",
            "Open the flight checklist",
        )
    return NextAction(
        5,
        "Make your map or 3D model",
        "Your photos are checked. Turn them into a map or a model with WebODM, on this computer.",
        "/process",
        "Next: 5. Make maps",
    )
