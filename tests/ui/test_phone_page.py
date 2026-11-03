# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import zipfile
from pathlib import Path

import pytest
from nicegui.testing import User

from avispria.adapters.adb import Adb, AdbNotFound
from avispria.app.phone_workflow import kmz_path
from avispria.app.ui.plan_job import PlanForm
from avispria.app.ui.state import STATE
from uihelpers import eventually, fill_plan_form, set_text, value_of

pytestmark = [pytest.mark.anyio, pytest.mark.nicegui_main_file("tests/ui/ui_main.py")]


def my_plan(tmp_path: Path, sample: Path) -> Path:
    out = tmp_path / "survey_01.kmz"
    with zipfile.ZipFile(sample) as src, zipfile.ZipFile(out, "w") as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            dst.writestr(
                item.filename,
                data + b"\n<!-- mine -->\n" if item.filename.endswith("wpml") else data,
            )
    return out


def choose_slot(user: User, marker: str, guid: str) -> None:
    next(iter(user.find(marker=marker).elements)).set_value(guid)


async def test_the_screen_shows_the_phone_and_the_missions_dji_fly_holds(
    user: User, fake_phone
) -> None:  # type: ignore[no-untyped-def]
    await user.open("/phone")
    await user.should_see("Is the phone connected?")
    await user.should_see("Redmi K90 is connected (USB)", retries=100)
    await user.should_see("2 missions found")
    await user.should_see("Placeholder missions in DJI Fly")
    await user.should_see("Mission 59B88CA7...")
    await user.should_see("Use as my sample mission")
    await user.should_see("Send the plan")


async def test_without_adb_the_screen_says_where_to_get_it(user: User, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def missing(cls, explicit=None):  # type: ignore[no-untyped-def]
        raise AdbNotFound("adb was not found. Download 'SDK Platform-Tools' and choose the folder.")

    monkeypatch.setattr(Adb, "find", classmethod(missing))
    await user.open("/phone")
    await user.should_see("Debugging tool (adb): Not found", retries=100)
    await user.should_see("Platform-Tools")
    await user.should_not_see("Placeholder missions in DJI Fly")  # nothing to choose from yet
    user.find(marker="adb-input")  # and a place to say where it is


async def test_a_phone_that_has_not_allowed_the_computer_says_what_to_tap(
    user: User, fake_phone, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("FAKE_ADB_STATE", "unauthorized")
    await user.open("/phone")
    await user.should_see("Waiting for you to allow this computer", retries=100)
    await user.should_see("Allow")


async def test_check_again_finds_a_phone_that_was_plugged_in_meanwhile(
    user: User, fake_phone, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("FAKE_ADB_STATE", "none")
    await user.open("/phone")
    await user.should_see("Not connected", retries=100)
    monkeypatch.setenv("FAKE_ADB_STATE", "device")  # the person plugs it in and unlocks it
    user.find(marker="phone-refresh").click()
    await user.should_see("Redmi K90 is connected", retries=100)


async def test_a_mission_from_the_phone_becomes_the_sample_on_the_plan_screen(
    user: User, fake_phone
) -> None:  # type: ignore[no-untyped-def]
    await user.open("/phone")
    await user.should_see("Mission 59B88CA7...", retries=100)
    user.find(marker="use-59B88CA7").click()
    await eventually(lambda: bool(STATE.sample_mission))
    assert Path(STATE.sample_mission).read_bytes() == fake_phone.sample.read_bytes()
    await user.open("/plan")
    assert value_of(user, "template-input") == STATE.sample_mission  # no file to find by hand


async def test_sending_a_plan_replaces_the_slot_and_keeps_the_original(
    user: User, fake_phone, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    plan, slot = my_plan(tmp_path, fake_phone.sample), fake_phone.ids[0]
    original = (fake_phone.root / kmz_path(slot).lstrip("/")).read_bytes()
    await user.open("/phone")
    await user.should_see("Mission 59B88CA7...", retries=100)
    set_text(user, "send-file-0-input", str(plan))
    user.find(marker="confirm-send").click()
    user.find(marker="send-button").click()
    await user.should_see("Sent survey_01.kmz to 59B88CA7", retries=100)
    await user.should_see("Next, on the phone")
    await user.should_see("Close DJI Fly completely")
    assert (fake_phone.root / kmz_path(slot).lstrip("/")).read_bytes() == plan.read_bytes()
    assert next(fake_phone.backups.glob("*_original.kmz")).read_bytes() == original
    await user.should_see("last sent: survey_01.kmz", retries=100)  # the list remembers it
    # the refresh that shows "last sent" must not wipe the message the person has to read
    await user.should_see("Next, on the phone")
    await user.should_see("Sent survey_01.kmz to 59B88CA7")
    user.notify.contains(
        "Sent. Now close DJI Fly completely"
    )  # and a notice that stays until dismissed


async def test_nothing_is_sent_until_the_replacement_is_confirmed(
    user: User, fake_phone, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    plan, slot = my_plan(tmp_path, fake_phone.sample), fake_phone.ids[0]
    original = (fake_phone.root / kmz_path(slot).lstrip("/")).read_bytes()
    await user.open("/phone")
    await user.should_see("Mission 59B88CA7...", retries=100)
    set_text(user, "send-file-0-input", str(plan))
    user.find(marker="send-button").click()  # the box is not ticked
    await user.should_see("Tick the box above")
    assert (fake_phone.root / kmz_path(slot).lstrip("/")).read_bytes() == original
    assert not fake_phone.backups.exists()


async def test_choices_that_cannot_be_right_are_refused(
    user: User, fake_phone, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    plan = my_plan(tmp_path, fake_phone.sample)
    await user.open("/phone")
    await user.should_see("Mission 59B88CA7...", retries=100)
    user.find(marker="confirm-send").click()
    set_text(user, "send-file-0-input", str(tmp_path / "missing.kmz"))
    user.find(marker="send-button").click()
    await user.should_see("was not found")
    set_text(user, "send-file-0-input", str(plan))
    user.find(marker="add-row").click()
    set_text(user, "send-file-1-input", str(plan))
    choose_slot(user, "send-slot-1", fake_phone.ids[0])  # the same slot as the first
    user.find(marker="send-button").click()
    await user.should_see("chosen twice")
    assert not fake_phone.backups.exists()  # still nothing has been touched


async def test_a_whole_plan_goes_from_planning_to_the_phone(
    user: User, fake_phone, plan_form: PlanForm, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    await user.open("/plan")
    fill_plan_form(user, plan_form)
    user.find(marker="run").click()
    await user.should_see("Missions", retries=200)
    await user.should_see("Send to DJI Fly...")
    assert STATE.last_plan_files and all(p.endswith(".kmz") for p in STATE.last_plan_files)
    user.find(marker="to-phone").click()
    await user.should_see("Send the plan", retries=100)
    assert value_of(user, "send-file-0-input") == STATE.last_plan_files[0]  # already filled in


async def test_wifi_pairing_from_the_screen(user: User, fake_phone) -> None:  # type: ignore[no-untyped-def]
    await user.open("/phone")
    await user.should_see("Is the phone connected?")
    set_text(user, "pair-address-input", "192.168.1.5:37123")
    set_text(user, "pair-code-input", "123456")
    user.find(marker="pair-button").click()
    await user.should_see("Successfully paired", retries=100)
    set_text(user, "pair-code-input", "000000")
    user.find(marker="pair-button").click()
    await user.should_see("Pairing failed", retries=100)


async def test_a_mission_that_cannot_be_read_is_shown_but_never_offered(
    user: User, fake_phone
) -> None:  # type: ignore[no-untyped-def]
    junk = "AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA"
    base = fake_phone.root / "sdcard/Android/data/dji.go.v5/files/waypoint" / junk
    base.mkdir(parents=True)
    (base / f"{junk}.kmz").write_bytes(b"not a waypoint mission")
    await user.open("/phone")
    await user.should_see("Mission AAAAAAAA...", retries=100)
    await user.should_see("Avispria cannot read this mission")
    await user.should_not_see(marker="use-AAAAAAAA")  # no sample button for it
    options = next(iter(user.find(marker="send-slot-0").elements)).options
    assert junk not in options and fake_phone.ids[0] in options  # and not in the slot list


async def test_the_page_says_what_is_needed_before_sending_and_what_is_in_place(
    user: User, fake_phone, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    STATE.last_plan_files = [str(tmp_path / "survey_01.kmz"), str(tmp_path / "survey_02.kmz")]
    await user.open("/phone")
    await user.should_see("Before you send", retries=100)
    await user.should_see("Your last plan has 2 missions to send.")
    await user.should_see("Phone connected: Redmi K90.")
    await user.should_see("DJI Fly has 2 missions that can be replaced: enough for your plan.")
    await user.should_not_see("Make 1 more")


async def test_too_few_placeholder_missions_says_how_many_more_to_make_before_anything_is_sent(
    user: User, fake_phone, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    STATE.last_plan_files = [str(tmp_path / f"survey_0{n}.kmz") for n in (1, 2, 3)]
    await user.open("/phone")
    await user.should_see(
        "DJI Fly has 2 missions that can be replaced, but your plan has 3.", retries=100
    )
    await user.should_see("Make 1 more.")
    await user.should_see("Waypoint Flight, add any two points and press Save")
    await user.should_see("Then press Check again.")


async def test_a_missing_plan_points_back_to_step_one(user: User, fake_phone) -> None:  # type: ignore[no-untyped-def]
    await user.open("/phone")
    await user.should_see("There is no plan to send yet.", retries=100)
    await user.should_see("Make one in step 1 (Plan a flight)")


async def test_no_phone_is_the_first_thing_the_checklist_says(
    user: User, fake_phone, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("FAKE_ADB_STATE", "none")
    STATE.last_plan_files = [str(tmp_path / "survey_01.kmz")]
    await user.open("/phone")
    await user.should_see("Before you send", retries=100)
    await user.should_see("No phone is connected.")
    await user.should_see("Your last plan has 1 mission to send.")
    await user.should_not_see("can be replaced")


async def test_a_successful_send_is_remembered_for_the_progress_tracker(
    user: User, fake_phone, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    plan = my_plan(tmp_path, fake_phone.sample)
    assert STATE.last_sent_files == []
    await user.open("/phone")
    await user.should_see("Mission 59B88CA7...", retries=100)
    set_text(user, "send-file-0-input", str(plan))
    user.find(marker="confirm-send").click()
    user.find(marker="send-button").click()
    await user.should_see("Sent survey_01.kmz to 59B88CA7", retries=100)
    assert STATE.last_sent_files == [str(plan)]
