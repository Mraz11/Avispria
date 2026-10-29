# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path

import pytest
from nicegui.testing import User

from avispria.app.ui.state import STATE
from fakes.nodeodx import fake_engine
from photobuild import make_dji_jpeg
from uihelpers import eventually, set_text, value_of

pytestmark = [pytest.mark.anyio, pytest.mark.nicegui_main_file("tests/ui/ui_main.py")]
LONG = 200  # retries: a job takes a moment


def survey_photos(tmp_path: Path, n: int = 6) -> Path:
    folder = tmp_path / "hillside" / "images"
    folder.mkdir(parents=True)
    for i in range(n):
        make_dji_jpeg(
            folder / f"DJI_{i:04d}.JPG",
            size=(800, 600),
            lat=22.2820 + (i % 3) * 0.0001,
            lon=91.7790 + (i // 3) * 0.0002,
        )
    return folder


def next_to(folder: Path) -> str:
    return str(folder.parent / "hillside_avispria")


async def test_the_screen_explains_itself_and_offers_the_choices(user: User) -> None:
    await user.open("/process")
    for text in (
        "Make maps",
        "Photo folder",
        "Where to save the results",
        "Standard: the map, a surface model",
        "Check this computer for this job",
        "Start making maps",
        "WebODM must be running",
    ):
        await user.should_see(text)
    await user.should_not_see("Cancel")  # only while a job runs


async def test_choosing_the_photos_suggests_where_to_save(user: User, tmp_path: Path) -> None:
    folder = survey_photos(tmp_path)
    await user.open("/process")
    set_text(user, "photos-input", str(folder))
    await eventually(lambda: value_of(user, "out-input") == next_to(folder))
    set_text(user, "out-input", str(tmp_path / "mine"))  # a chosen folder is kept
    set_text(user, "photos-input", str(folder.parent))
    assert value_of(user, "out-input") == str(tmp_path / "mine")


async def test_photos_checked_earlier_are_prefilled(user: User, tmp_path: Path) -> None:
    folder = survey_photos(tmp_path)
    STATE.photo_folder = str(folder)
    await user.open("/process")
    assert value_of(user, "photos-input") == str(folder)
    assert value_of(user, "out-input") == next_to(folder)


async def test_the_computer_check_says_whether_the_job_fits(
    user: User, machine, tmp_path: Path
) -> None:
    folder = survey_photos(tmp_path)
    machine(port=1)
    await user.open("/process")
    set_text(user, "photos-input", str(folder))
    user.find(marker="check-button").click()
    await user.should_see("This computer can process these photos", retries=LONG)
    await user.should_see("Photos are processed at")
    await user.should_see("WebODM is running")


async def test_a_too_small_computer_is_told_what_to_do(user: User, machine, tmp_path: Path) -> None:
    folder = survey_photos(tmp_path)
    machine(port=1, ram=2.0, swap=0.0)
    await user.open("/process")
    set_text(user, "photos-input", str(folder))
    user.find(marker="check-button").click()
    await user.should_see("Not possible on this computer as it is", retries=LONG)
    await user.should_see("What you can do")


async def test_a_full_job_shows_progress_then_the_results(
    user: User, machine, tmp_path: Path
) -> None:
    folder = survey_photos(tmp_path)
    with fake_engine("t") as (port, state):
        machine(port)
        await user.open("/process")
        set_text(user, "photos-input", str(folder))
        user.find("Fast: the map only, quickest and needs the least memory").click()
        user.find(marker="start-button").click()
        await user.should_see("Maps are ready", retries=LONG)
    for text in (
        "Reading your photos",
        "Sending the photos to the engine",
        "Making the maps",
        "Collecting the results",
        "Your results",
        "Orthophoto (the map)",
        "Open the results folder",
        "avispria_provenance.json",
    ):
        await user.should_see(text)
    assert state.uploads == 6
    out = Path(next_to(folder))
    assert (out / "avispria_provenance.json").is_file() and (out / "results").is_dir()
    assert STATE.photo_folder == str(folder)


async def test_a_blocked_job_can_be_forced(user: User, machine, tmp_path: Path) -> None:
    folder = survey_photos(tmp_path)
    with fake_engine("t") as (port, state):
        machine(port, ram=2.0, swap=0.0)
        await user.open("/process")
        set_text(user, "photos-input", str(folder))
        user.find(marker="start-button").click()
        await user.should_see("Not started", retries=LONG)
        await user.should_see("What you can do")
        assert state.uploads == 0
        user.find(marker="force-switch").click()  # "start even if this computer looks too small"
        user.find(marker="start-button").click()
        await user.should_see("Your results", retries=LONG)
    assert state.uploads == 6


async def test_a_job_can_be_cancelled(user: User, machine, tmp_path: Path) -> None:
    folder = survey_photos(tmp_path)
    with fake_engine("t", outcome="hang") as (port, state):  # a task that never finishes
        machine(port)
        await user.open("/process")
        set_text(user, "photos-input", str(folder))
        user.find(marker="start-button").click()
        await user.should_see("Making the maps", retries=LONG)
        await user.should_see("Cancel")
        user.find(marker="cancel-button").click()
        await user.should_see("Processing was cancelled", retries=LONG)
        assert state.cancelled
    await user.should_see("Stopped")
    await user.should_not_see("Your results")
    await user.should_not_see("Cancel")  # the button goes away again


async def test_an_engine_failure_shows_what_it_said(user: User, machine, tmp_path: Path) -> None:
    folder = survey_photos(tmp_path)
    with fake_engine("t", outcome="fail") as (port, _):
        machine(port)
        await user.open("/process")
        set_text(user, "photos-input", str(folder))
        user.find(marker="start-button").click()
        await user.should_see("Processing did not finish", retries=LONG)
    await user.should_see("What the engine said")


async def test_form_mistakes_are_explained(user: User, machine, tmp_path: Path) -> None:
    folder = survey_photos(tmp_path)
    machine(port=1)
    await user.open("/process")
    user.find(marker="start-button").click()
    await user.should_see("Choose the folder with your photos.")
    set_text(user, "photos-input", str(folder))
    set_text(user, "out-input", str(folder / "results"))
    user.find(marker="start-button").click()
    await user.should_see("Save the results outside the photo folder")


async def test_the_check_screen_leads_here_with_the_photos_filled_in(
    user: User, tmp_path: Path
) -> None:
    folder = survey_photos(tmp_path, n=8)
    await user.open("/check")
    set_text(user, "photos-input", str(folder))
    user.find(marker="run").click()
    await user.should_see("Make maps from these photos", retries=LONG)
    user.find("Make maps from these photos").click()
    await user.should_see("Start making maps", retries=LONG)
    await eventually(lambda: value_of(user, "photos-input") == str(folder))
