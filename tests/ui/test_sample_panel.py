# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The sample mission is taken from the phone on the Plan screen itself: no other screen."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from nicegui.testing import User

from avispria.app.phone_workflow import WAYPOINT_DIR
from avispria.app.ui import state
from avispria.app.ui.state import STATE, settings_path
from uihelpers import value_of

pytestmark = [pytest.mark.anyio, pytest.mark.nicegui_main_file("tests/ui/ui_main.py")]


async def test_without_a_sample_the_plan_screen_says_so_and_offers_to_get_it(user: User) -> None:
    await user.open("/plan")
    await user.should_see("No sample mission yet.")
    await user.should_see("Get it from my phone")
    await user.should_see("Connect the phone to this computer with the USB cable")
    await user.should_not_see("Open step 2")  # no more trip to another screen
    assert value_of(user, "template-input") == ""


async def test_one_press_takes_the_sample_from_the_phone_and_fills_the_field(
    user: User, fake_phone: SimpleNamespace, tmp_path: Path
) -> None:
    await user.open("/plan")
    user.find(marker="sample-from-phone").click()
    await user.should_see("Sample mission:", retries=200)
    await user.should_see("Get a different one from my phone")
    saved = sorted((tmp_path / "samples").glob("*.kmz"))  # the fixture's own folder
    assert len(saved) == 1
    assert STATE.sample_mission == str(saved[0])
    assert value_of(user, "template-input") == str(saved[0])  # no typing, no browsing
    await user.should_not_see("No sample mission yet.")


async def test_the_sample_is_remembered_so_the_next_visit_needs_no_phone(
    user: User, fake_phone: SimpleNamespace
) -> None:
    await user.open("/plan")
    user.find(marker="sample-from-phone").click()
    await user.should_see("Sample mission:", retries=200)
    got = STATE.sample_mission
    await user.open("/")  # away and back
    await user.open("/plan")
    assert value_of(user, "template-input") == got
    await user.should_see("Sample mission:")


async def test_it_is_remembered_between_runs_of_the_program(
    user: User, fake_phone: SimpleNamespace
) -> None:
    STATE.load()  # what the program does at start-up
    await user.open("/plan")
    user.find(marker="sample-from-phone").click()
    await user.should_see("Sample mission:", retries=200)
    got = STATE.sample_mission
    assert settings_path().is_file()
    state.reset()  # the program is closed ...
    STATE.load()  # ... and started again
    assert STATE.sample_mission == got


async def test_no_phone_is_explained_on_the_spot(
    user: User, fake_phone: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_ADB_STATE", "none")
    await user.open("/plan")
    user.find(marker="sample-from-phone").click()
    await user.should_see("No phone is connected", retries=200)
    await user.should_see("No sample mission yet.")
    assert STATE.sample_mission == "" and value_of(user, "template-input") == ""


async def test_a_phone_without_a_saved_mission_is_told_how_to_make_one(
    user: User, fake_phone: SimpleNamespace
) -> None:
    for kmz in (fake_phone.root / WAYPOINT_DIR.lstrip("/")).glob("*/*.kmz"):
        kmz.write_bytes(b"not a mission")
    await user.open("/plan")
    user.find(marker="sample-from-phone").click()
    await user.should_see("no waypoint mission yet", retries=200)
    await user.should_see("Waypoint Flight, add two points and press Save")


async def test_a_sample_that_was_deleted_is_not_pretended_to_exist(
    user: User, tmp_path: Path
) -> None:
    gone = tmp_path / "gone.kmz"
    STATE.sample_mission = str(gone)
    await user.open("/plan")
    await user.should_see("No sample mission yet.")


async def test_the_how_do_i_get_this_file_help_points_at_the_button_not_at_another_screen(
    user: User,
) -> None:
    from avispria.app.ui.pages.plan_results import FLY_FILE_HELP

    assert "Get it from my phone" in FLY_FILE_HELP and "Phone screen" not in FLY_FILE_HELP
