# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""What the screens remember between each other (one person, one computer)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SharedState:
    photo_folder: str = ""  # last photos checked: pre-fills "Make maps"
    last_output: str = ""  # last output folder: where the folder browser starts


STATE = SharedState()


def reset() -> None:
    STATE.photo_folder = ""
    STATE.last_output = ""
