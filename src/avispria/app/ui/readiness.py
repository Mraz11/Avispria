# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Is everything in place to send a plan to DJI Fly? Said plainly, with the fix for what is not."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from avispria.app.phone_workflow import Slot
from avispria.app.ui.phone_job import PhoneStatus

MAKE_PLACEHOLDER = (
    "In DJI Fly open Waypoint Flight, add any two points and press Save. That is one placeholder "
    "mission. Do not fly it: Avispria replaces what is in it."
)


@dataclass(frozen=True)
class Check:
    ok: bool
    text: str
    fix: str = ""


def _missions(n: int) -> str:
    return f"{n} mission{'s' if n != 1 else ''}"


def usable_slots(slots: Sequence[Slot]) -> list[Slot]:
    """The placeholder missions Avispria can replace (it must be able to read them)."""
    return [s for s in slots if s.waypoints > 0]


def placeholders_missing(plan_files: Sequence[str], slots: Sequence[Slot]) -> int:
    """How many more placeholder missions must be made in DJI Fly for this plan (0 = enough)."""
    return max(0, len(plan_files) - len(usable_slots(slots)))


def readiness(status: PhoneStatus, plan_files: Sequence[str]) -> list[Check]:
    """The three things sending needs, in the order a person deals with them."""
    checks: list[Check] = []
    n = len(plan_files)
    if n:
        checks.append(Check(True, f"Your last plan has {_missions(n)} to send."))
    else:
        checks.append(
            Check(
                False,
                "There is no plan to send yet.",
                "Make one in step 1 (Plan a flight), or choose a mission file below.",
            )
        )
    if status.serial is None:
        checks.append(
            Check(
                False,
                "No phone is connected.",
                status.problem
                or "Plug the phone in with the USB cable, unlock it and allow USB debugging.",
            )
        )
        return checks
    checks.append(Check(True, f"Phone connected: {status.model or 'Android phone'}."))
    have = len(usable_slots(status.slots))
    need = max(n, 1)
    if have >= need:
        checks.append(
            Check(
                True,
                f"DJI Fly has {_missions(have)} that can be replaced: enough for "
                + ("your plan." if n else "one mission."),
            )
        )
    else:
        more = need - have
        checks.append(
            Check(
                False,
                f"DJI Fly has {_missions(have)} that can be replaced, "
                + (f"but your plan has {n}." if n else "and at least one is needed."),
                f"Make {more} more. {MAKE_PLACEHOLDER} Then press Check again.",
            )
        )
    return checks
