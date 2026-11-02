# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Helpers for tests that drive the window interface with NiceGUI's simulated user."""

from __future__ import annotations

from collections.abc import Callable

import anyio
from nicegui.testing import User

from avispria.app.ui.plan_job import PlanForm


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


def fill_plan_form(user: User, form: "PlanForm") -> None:  # noqa: UP037
    """Type the values of a valid Plan a flight form into the screen, like a person would."""
    set_text(user, "centre-input", form.centre)
    set_text(user, "width-input", f"{form.width_m:g}")
    set_text(user, "length-input", f"{form.length_m:g}")
    set_text(user, "template-input", form.template)
    set_text(user, "out-input", form.out_dir)
    set_text(user, "target-input", "3")  # 3 cm/px keeps the test plan small
