# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path

import numpy as np
import pytest
import rasterio
from nicegui import ui
from nicegui.testing import User
from rasterio.transform import from_origin

from avispria.app.ui.plan_job import PlanForm
from avispria.app.ui.state import STATE
from uihelpers import eventually, set_text, value_of

pytestmark = [pytest.mark.anyio, pytest.mark.nicegui_main_file("tests/ui/ui_main.py")]


def fill(user: User, form: PlanForm) -> None:
    """Type the values of a valid form into the screen, like a person would."""
    set_text(user, "centre-input", form.centre)
    set_text(user, "width-input", f"{form.width_m:g}")
    set_text(user, "length-input", f"{form.length_m:g}")
    set_text(user, "template-input", form.template)
    set_text(user, "out-input", form.out_dir)
    set_text(user, "target-input", "3")  # 3 cm/px keeps the test plan small


async def test_the_screen_asks_for_everything_in_plain_words(user: User) -> None:
    await user.open("/plan")
    for text in (
        "1. The survey area",
        "2. Your drone",
        "3. What you want",
        "4. The ground",
        "5. Where to save",
        "Advanced settings",
        "Plan the flight",
        "cm per pixel (smaller = more detail)",
    ):
        await user.should_see(text)
    await user.should_not_see("Elevation model (GeoTIFF)")  # only for hilly sites
    await user.should_not_see("have not been verified")  # the Lito X1 profile is verified


async def test_planning_end_to_end_shows_prediction_route_and_missions(
    user: User, plan_form: PlanForm
) -> None:
    await user.open("/plan")
    fill(user, plan_form)
    user.find(marker="run").click()
    await user.should_see("You asked for")
    await user.should_see("You will get")
    await user.should_see("Overlap")
    await user.should_see("The route")
    await user.should_see(kind=ui.echart)
    await user.should_see("Missions")
    await user.should_see("How do I get these missions onto my drone?")
    await user.should_see("set the camera to timed shot every")
    await user.should_see("Planned without terrain data")  # SAF008, explained
    assert (
        list(Path(plan_form.out_dir).glob("*.kmz"))
        and (Path(plan_form.out_dir) / "plan_report.json").is_file()
    )
    assert STATE.last_output == plan_form.out_dir


async def test_mistakes_in_the_form_are_explained(user: User, plan_form: PlanForm) -> None:
    await user.open("/plan")
    user.find(marker="run").click()
    await user.should_see("Centre of the area: Enter latitude and longitude")
    fill(user, plan_form)
    set_text(user, "template-input", "/nowhere/sample.kmz")
    user.find(marker="run").click()
    await user.should_see("DJI Fly sample mission file was not found")
    set_text(user, "template-input", plan_form.template)
    set_text(user, "takeoff-input", "far away")
    user.find(marker="run").click()
    await user.should_see("Takeoff point: Enter latitude and longitude")


async def test_a_plan_that_cannot_be_flown_says_why_and_saves_nothing(
    user: User, plan_form: PlanForm
) -> None:
    await user.open("/plan")
    fill(user, plan_form)
    set_text(user, "takeoff-input", "23.8140, 90.4125")  # ~340 m from the area
    set_text(user, "max-distance-input", "10")
    user.find(marker="run").click()
    await user.should_see("This plan cannot be flown as asked")
    await user.should_see("Too far from the takeoff point")
    await user.should_see("Nothing was saved.")
    assert list(Path(plan_form.out_dir).glob("*.kmz")) == []


async def test_choosing_an_unverified_aircraft_warns_and_resizes_the_choices(user: User) -> None:
    await user.open("/plan")
    aircraft = next(iter(user.find(marker="aircraft-select").elements))
    aircraft.set_value("mini-4-pro")
    await user.should_see("camera numbers for this aircraft have not been verified yet")
    aircraft.set_value("lito-x1")
    await user.should_not_see("have not been verified")


async def test_the_hills_option_asks_for_an_elevation_model(
    user: User, plan_form: PlanForm, tmp_path: Path
) -> None:
    surface = tmp_path / "dem.tif"
    n, cell = 300, 1 / 3600
    with rasterio.open(
        surface,
        "w",
        driver="GTiff",
        height=n,
        width=n,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(90.40, 23.82, cell, cell),
    ) as dst:
        dst.write(np.full((n, n), 25.0, "float32"), 1)
    await user.open("/plan")
    user.find("It has hills (I have an elevation model)").click()
    await user.should_see("Elevation model (GeoTIFF)")
    fill(user, plan_form)
    set_text(user, "dem-input", str(surface))
    user.find(marker="run").click()
    await user.should_see("Height above the surface")
    await user.should_see("You will get")


async def test_the_file_area_option_uses_a_file_picker(user: User, tmp_path: Path) -> None:
    (tmp_path / "area.geojson").write_text("{}")
    await user.open("/plan")
    await user.should_not_see("Survey area file (GeoJSON)")
    user.find("Use a map file").click()
    await user.should_see("Survey area file (GeoJSON)")
    set_text(user, "aoi-input", str(tmp_path))
    user.find(marker="aoi-browse").click()
    await user.should_see("area.geojson")
    user.find("area.geojson").click()
    await eventually(lambda: value_of(user, "aoi-input") == str(tmp_path / "area.geojson"))


async def test_asking_for_a_height_instead_of_a_resolution(user: User, plan_form: PlanForm) -> None:
    await user.open("/plan")
    user.find("A flying height").click()
    await user.should_see("metres above the surface")
    fill(user, plan_form)
    set_text(user, "target-input", "60")
    user.find(marker="run").click()
    await user.should_see("flying 60 m above the surface")
