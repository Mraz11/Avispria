# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Helpers for tests that drive the window interface with NiceGUI's simulated user."""

from __future__ import annotations

from collections.abc import Callable

import anyio
from nicegui.testing import User


def value_of(user: User, marker: str) -> str:
    """The current text of the field with this marker."""
    return str(next(iter(user.find(marker=marker).elements)).value or "")


def set_text(user: User, marker: str, text: str) -> None:
    """Replace a field's text (a plain ``type`` would append to what is there)."""
    user.find(marker=marker).clear().type(text)


async def eventually(check: Callable[[], bool], timeout: float = 5.0) -> None:
    """Wait for something a background handler does (a dialog closing, a job ending)."""
    with anyio.fail_after(timeout):
        while not check():
            await anyio.sleep(0.02)
