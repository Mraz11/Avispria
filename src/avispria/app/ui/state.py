# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""What the screens remember between each other (one person, one computer)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SharedState:
    photo_folder: str = ""  # last photos checked: pre-fills "Make maps"
    last_output: str = ""  # last output folder: where the folder browser starts
    sample_mission: str = ""  # a mission copied from the phone: pre-fills the Plan screen
    adb_path: str = ""  # where adb is, if it is not found by itself
    last_plan_files: list[str] = field(default_factory=list)  # the last plan's missions


STATE = SharedState()


def reset() -> None:
    STATE.photo_folder = ""
    STATE.last_output = ""
    STATE.sample_mission = ""
    STATE.adb_path = ""
    STATE.last_plan_files = []
