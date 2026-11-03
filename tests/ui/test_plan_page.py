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
        "1. What do you want to capture?",
        "2. Where: the area",
        "3. Your drone",
        "4. Settings",
        "5. Where to save",
        "Advanced settings",
        "Plan the flight",
        "cm per pixel (smaller = more detail)",
        "The ground",
    ):
        await user.should_see(text)
    await user.should_not_see("Elevation model (GeoTIFF)")  # only for hilly sites
    await user.should_not_see("have not been verified")  # the Lito X1 profile is verified


async def test_the_steps_are_numbered_in_the_order_they_are_filled_in(user: User) -> None:
    await user.open("/plan")
    await user.should_see("1. What do you want to capture?")
    await user.should_see("Get it from my phone")  # the sample mission, right here
    await user.should_not_see("Open step 2")  # no trip to another screen for it
    titles = [
        "1. What do you want to capture?",
        "2. Where: the area",
        "3. Your drone",
        "4. Settings",
        "5. Where to save",
    ]
    from nicegui import ui

    labels = [e for e in user.find(kind=ui.label).elements if e.text in titles]
    assert {e.text for e in labels} == set(titles)
    ids = {e.text: e.id for e in labels}  # element ids grow in the order the cards were built
    assert [ids[x] for x in titles] == sorted(ids[x] for x in titles)


async def test_a_flat_map_shows_only_what_a_flat_map_needs(user: User) -> None:
    await user.open("/plan")
    await user.should_see("Flat map of an area")
    await user.should_see("A top-down map")
    await user.should_see("Overlap along the line (%)")
    for hidden in (
        "Camera tilt (degrees from straight down)",
        "2. Where: the object",
        "4. Settings: the rings",
        "Distance from the object (m)",
    ):
        await user.should_not_see(hidden)


async def test_a_3d_model_of_an_area_adds_the_tilt_and_sets_its_own_values(user: User) -> None:
    await user.open("/plan")
    next(iter(user.find(marker="scan-type").elements)).set_value("area_3d")
    await user.should_see("Camera tilt (degrees from straight down)")
    await user.should_see("The lines are flown in two directions")
    await user.should_see("A 3D model of a site")
    assert value_of(user, "tilt-input") == "30.0" or value_of(user, "tilt-input") == "30"
    assert value_of(user, "target-input") in ("2.5", "2.5000000000000004")
    assert next(iter(user.find(marker="crosshatch-switch").elements)).value is True
    user.notify.contains("Settings set to what suits: 3D model of an area")
    await user.should_not_see("4. Settings: the rings")
    next(iter(user.find(marker="scan-type").elements)).set_value("flat")  # and back again
    await user.should_not_see("Camera tilt (degrees from straight down)")
    assert value_of(user, "target-input") == "2.0"
    assert next(iter(user.find(marker="crosshatch-switch").elements)).value is False


async def test_a_3d_model_of_one_object_swaps_the_area_cards_for_the_object_cards(
    user: User,
) -> None:
    await user.open("/plan")
    next(iter(user.find(marker="scan-type").elements)).set_value("object_3d")
    for shown in (
        "2. Where: the object",
        "4. Settings: the rings",
        "Position of the object: latitude, longitude",
        "Distance from the object (m)",
        "Camera looks up at the bottom by (degrees)",
        "A few photos straight down over the top",
        "Place it on a map",
        "circles the object in rings",
    ):
        await user.should_see(shown)
    for hidden in (
        "2. Where: the area",
        "Overlap along the line (%)",
        "Camera tilt (degrees from straight down)",
        "Describe it with numbers",
        "Tune height and spacing",
        "Shutter time you expect",
    ):
        await user.should_not_see(hidden)
    await user.should_see("Highest allowed above takeoff")  # the safety limits apply to every kind


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
    await user.should_see("If they do not, do not fly it.")  # what to compare with on the phone
    table = next(iter(user.find(kind=ui.table).elements))
    assert [c["label"] for c in table.columns][-1] == "DJI Fly should show"
    assert all("waypoints," in row["dji"] and " m, about " in row["dji"] for row in table.rows)
    await user.should_see("A photo is taken at every photo waypoint")  # the default now
    await user.should_not_see("set the camera to timed shot")
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


async def test_timed_shot_is_still_available_and_says_what_to_set_on_the_camera(
    user: User, plan_form: PlanForm
) -> None:
    await user.open("/plan")
    fill(user, plan_form)
    next(iter(user.find(marker="photo-mode-select").elements)).set_value("interval")
    user.find(marker="run").click()
    await user.should_see("set the camera to timed shot every", retries=300)
    await user.should_not_see("A photo is taken at every photo waypoint")


async def test_a_big_area_needs_several_missions_and_the_screen_says_how_many_slots(
    user: User, plan_form: PlanForm
) -> None:
    await user.open("/plan")
    fill(user, plan_form)
    set_text(user, "width-input", "400")
    set_text(user, "length-input", "400")
    user.find(marker="run").click()
    await user.should_see("placeholder missions (slots) in DJI Fly", retries=300)
    await user.should_see("The Phone screen sends them all in one go")


async def test_the_form_explains_the_two_ways_of_taking_photos(user: User) -> None:
    await user.open("/plan")
    await user.should_see("A photo at every photo point (recommended)")
    await user.should_see("DJI Fly takes about 99 waypoints in one")
    assert value_of(user, "photo-mode-select") in (
        "waypoint",
        "A photo at every photo point (recommended)",
    )


async def test_a_new_plan_is_not_yet_sent_and_its_sample_mission_is_remembered(
    user: User, plan_form: PlanForm
) -> None:
    STATE.last_sent_files = ["old_plan.kmz"]  # an earlier plan that was sent
    await user.open("/plan")
    fill(user, plan_form)
    user.find(marker="run").click()
    await user.should_see("The route", retries=300)
    assert STATE.last_sent_files == []  # the tracker must not call the new plan sent
    assert STATE.sample_mission == plan_form.template  # no need to look for it next time
    assert len(STATE.last_plan_files) >= 1


async def test_a_plan_that_could_not_be_made_keeps_what_was_remembered(
    user: User, plan_form: PlanForm
) -> None:
    STATE.last_sent_files = ["old_plan.kmz"]
    STATE.last_plan_files = ["old_plan.kmz"]
    await user.open("/plan")
    user.find(marker="run").click()  # an empty form: nothing is planned
    await user.should_see("Centre of the area", retries=100)
    assert STATE.last_sent_files == ["old_plan.kmz"] and STATE.last_plan_files == ["old_plan.kmz"]
