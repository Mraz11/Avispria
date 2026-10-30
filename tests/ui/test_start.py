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


@pytest.mark.parametrize(
    ("marker", "heading", "marker_text"),
    [
        ("open-check", "Check my photos", "Check photos"),
        ("open-plan", "Plan a flight", "Plan the flight"),
        ("open-process", "Make maps", "Start making maps"),
    ],
)
async def test_each_task_card_opens_its_screen(
    user: User, fake_computer, marker: str, heading: str, marker_text: str
) -> None:
    fake_computer()
    await user.open("/")
    user.find(marker=marker).click()
    await user.should_see(marker_text)
    await user.should_see(heading)


@pytest.mark.parametrize("page", ["/", "/check", "/plan", "/process"])
async def test_every_screen_has_the_same_header_and_footer(
    user: User, fake_computer, page: str
) -> None:
    fake_computer()
    await user.open(page)
    for text in (
        "Avispria",
        "Start",
        "Check my photos",
        "Plan a flight",
        "Make maps",
        "not yet flight-tested",
    ):
        await user.should_see(text)


def test_finding_a_free_port_skips_busy_ones() -> None:
    with socket.socket() as busy:
        busy.bind((HOST, 0))
        taken = busy.getsockname()[1]
        assert find_free_port(taken) != taken
    assert find_free_port(taken) == taken  # free again once released


async def test_check_again_notices_that_webodm_has_been_started(user: User, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from avispria.adapters.system_probe import EngineStatus
    from avispria.app import doctor as doctor_module
    from avispria.core.feasibility import SystemSpec

    spec = SystemSpec("Windows 11", 12, 16.0, 8.0, 4.0, 200.0)
    state = {"up": False}
    monkeypatch.setattr(doctor_module, "probe_system", lambda workdir: spec)
    monkeypatch.setattr(doctor_module, "running_engine_programs", lambda: [])
    monkeypatch.setattr(
        doctor_module,
        "probe_engines",
        lambda: [EngineStatus("WebODM", "http://localhost:8000/", state["up"], "x")],
    )
    await user.open("/")
    await user.should_see("Not found")
    await user.should_see("not only installed")
    state["up"] = True  # the person starts WebODM, waits for its dashboard, and presses the button
    user.find(marker="check-again").click()
    await user.should_see("WebODM is running", retries=100)
    await user.should_not_see("Not found")
