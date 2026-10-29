# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import socket

import pytest
from nicegui.testing import User

from avispria.app.ui.app import HOST, find_free_port

pytestmark = [pytest.mark.anyio, pytest.mark.nicegui_main_file("tests/ui/ui_main.py")]


async def test_start_screen_offers_the_three_tasks_and_checks_the_computer(
    user: User, fake_computer
) -> None:
    fake_computer(ram=16.0, webodm=True)
    await user.open("/")
    for text in ("Check my photos", "Plan a flight", "Make maps", "Avispria", "Before you fly"):
        await user.should_see(text)
    await user.should_see("Memory: 16 GB")
    await user.should_see("WebODM is running")
    await user.should_see("Canopy structure and change, seen from above.")


async def test_start_screen_explains_a_missing_engine(user: User, fake_computer) -> None:
    fake_computer(ram=6.0, webodm=False)
    await user.open("/")
    await user.should_see("Map-making engine: Not found")
    await user.should_see("webodm.org/download")


def test_finding_a_free_port_skips_busy_ones() -> None:
    with socket.socket() as busy:
        busy.bind((HOST, 0))
        taken = busy.getsockname()[1]
        assert find_free_port(taken) != taken
    assert find_free_port(taken) == taken  # free again once released
