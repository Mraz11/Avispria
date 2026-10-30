# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import shutil
from pathlib import Path

import pytest
from nicegui import ui
from nicegui.testing import User

from avispria.app.ui.state import STATE
from uihelpers import eventually, set_text, value_of

pytestmark = [pytest.mark.anyio, pytest.mark.nicegui_main_file("tests/ui/ui_main.py")]


async def test_checking_a_folder_shows_verdict_numbers_map_and_table(
    user: User, photo_folder: Path
) -> None:
    await user.open("/check")
    set_text(user, "photos-input", str(photo_folder))
    user.find(marker="run").click()
    await user.should_see("Photos checked")
    await user.should_see("12 of 12")
    await user.should_see("Ground resolution")
    await user.should_see("Overlap")
    await user.should_see("Where the photos were taken")
    await user.should_see(kind=ui.echart)
    await user.should_see("All photos")
    await user.should_see("Make maps from these photos")
    assert STATE.photo_folder == str(photo_folder)  # remembered for the Make maps screen


async def test_a_folder_with_photos_in_subfolders_offers_them(
    user: User, photo_folder: Path, tmp_path: Path
) -> None:
    card = tmp_path / "card"
    (card / "DCIM").mkdir(parents=True)
    shutil.move(str(photo_folder), str(card / "DCIM" / "100MEDIA"))
    await user.open("/check")
    set_text(user, "photos-input", str(card))
    user.find(marker="run").click()
    await user.should_see("No photos directly in")
    await user.should_see("DCIM/100MEDIA  (12 photos)")
    user.find("DCIM/100MEDIA  (12 photos)").click()  # use it
    await eventually(lambda: value_of(user, "photos-input") == str(card / "DCIM" / "100MEDIA"))
    user.find(marker="run").click()
    await user.should_see("12 of 12")


async def test_a_folder_without_any_photos(user: User, tmp_path: Path) -> None:
    (tmp_path / "empty").mkdir()
    await user.open("/check")
    set_text(user, "photos-input", str(tmp_path / "empty"))
    user.find(marker="run").click()
    await user.should_see("No JPEG or DNG photos were found there.")


async def test_input_mistakes_get_plain_messages(
    user: User, photo_folder: Path, tmp_path: Path
) -> None:
    await user.open("/check")
    user.find(marker="run").click()
    await user.should_see("Choose the photo folder first.")  # a notification
    set_text(user, "photos-input", str(tmp_path / "nowhere"))
    user.find(marker="run").click()
    await user.should_see("That folder does not exist")
    set_text(user, "photos-input", str(photo_folder))
    set_text(user, "takeoff-input", "23.8, 90.4")
    user.find(marker="run").click()
    await user.should_see("only used together with an elevation model")
    set_text(user, "dem-input", str(tmp_path / "missing.tif"))
    user.find(marker="run").click()
    await user.should_see("That elevation model file does not exist")


async def test_terrain_options_use_the_elevation_model(
    user: User, photo_folder: Path, tmp_path: Path
) -> None:
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin

    surface = tmp_path / "surface.tif"
    with rasterio.open(
        surface,
        "w",
        driver="GTiff",
        height=60,
        width=60,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(91.775, 22.288, 0.0002, 0.0002),
    ) as dst:
        dst.write(np.full((60, 60), 100.0, "float32"), 1)
    await user.open("/check")
    set_text(user, "photos-input", str(photo_folder))
    set_text(user, "dem-input", str(surface))
    set_text(user, "takeoff-input", "north, east")
    user.find(marker="run").click()
    await user.should_see("Enter latitude and longitude as two numbers")
    set_text(user, "takeoff-input", "22.2820, 91.7790")
    user.find(marker="run").click()
    await user.should_see("above the surface (terrain used)")


async def test_the_folder_browser_picks_a_folder(user: User, tmp_path: Path) -> None:
    (tmp_path / "flights" / "site_a").mkdir(parents=True)
    (tmp_path / "flights" / "notes.txt").write_text("x")
    await user.open("/check")
    set_text(user, "photos-input", str(tmp_path / "flights"))
    user.find(marker="photos-browse").click()
    await user.should_see("Choose: Photo folder")
    await user.should_see("site_a")
    await user.should_not_see("notes.txt")  # only folders are offered when choosing a folder
    user.find("site_a").click()
    await user.should_see(str(tmp_path / "flights" / "site_a"))
    user.find("Use this folder").click()
    await eventually(lambda: value_of(user, "photos-input") == str(tmp_path / "flights" / "site_a"))


async def test_the_file_browser_lists_only_matching_files(user: User, tmp_path: Path) -> None:
    (tmp_path / "dem.tif").write_bytes(b"")
    (tmp_path / "notes.txt").write_text("x")
    await user.open("/check")
    set_text(user, "dem-input", str(tmp_path))
    user.find(marker="dem-browse").click()
    await user.should_see("dem.tif")
    await user.should_not_see("notes.txt")
    user.find("dem.tif").click()  # choosing a file closes the dialog
    await eventually(lambda: value_of(user, "dem-input") == str(tmp_path / "dem.tif"))


async def test_the_details_can_be_saved_as_a_spreadsheet(user: User, photo_folder: Path) -> None:
    await user.open("/check")
    set_text(user, "photos-input", str(photo_folder))
    user.find(marker="run").click()
    await user.should_see("Save details as a spreadsheet (CSV)")
    user.find("Save details as a spreadsheet (CSV)").click()
    download = await user.download.next()
    assert download.text.splitlines()[0].startswith("photo,gsd_cm")
    assert len(download.text.splitlines()) == 13  # header + 12 photos


async def test_photos_without_a_height_above_ground_are_explained_and_fixed_with_the_ground_height(
    user: User, autel_folder: Path
) -> None:
    await user.open("/check")
    set_text(user, "photos-input", str(autel_folder))
    user.find(marker="run").click()
    await user.should_see("Not enough usable photos", retries=100)  # the verdict
    await user.should_see("No height above the ground in the photos")  # the warning, in plain words
    await user.should_see("513-513 m above sea level")  # what the photos do record
    set_text(user, "ground-input", "463.7")
    user.find(marker="run").click()
    await user.should_see("12 of 12", retries=100)
    await user.should_see("above the ground (taken as 463.7 m above sea level)")
    await user.should_see("Camera angle not recorded")  # said aloud, not silently assumed
    set_text(user, "ground-input", "high")
    user.find(marker="run").click()
    await user.should_see("The ground height should be a number of metres above sea level.")
