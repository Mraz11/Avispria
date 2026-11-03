# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Plan a flight for each kind of scan, through the screen like a person would."""

from pathlib import Path

import pytest
from nicegui.testing import User

from avispria.app.ui.plan_job import PlanForm
from avispria.app.ui.state import STATE
from avispria.core.wpml.reader import read_mission
from uihelpers import set_text, value_of

pytestmark = [pytest.mark.anyio, pytest.mark.nicegui_main_file("tests/ui/ui_main.py")]


def choose(user: User, kind: str) -> None:
    next(iter(user.find(marker="scan-type").elements)).set_value(kind)


def fill_files(user: User, form: PlanForm) -> None:
    set_text(user, "template-input", form.template)
    set_text(user, "out-input", form.out_dir)


def fill_object(user: User, form: PlanForm, **changes: str) -> None:
    fill_files(user, form)
    values = {
        "object-centre-input": "12.3456, 98.7654",
        "object-height-input": "25",
        "object-radius-input": "6",
        "standoff-input": "14",
    } | changes
    for marker, value in values.items():
        set_text(user, marker, value)


@pytest.fixture
def pins(monkeypatch: pytest.MonkeyPatch) -> list:  # type: ignore[type-arg]
    """Every pin map the object card creates, so a test can place a pin like a person would."""
    from avispria.app.ui.pages import plan_object, plan_pin_map

    created: list = []  # type: ignore[type-arg]

    class Recording(plan_pin_map.PinMap):
        def __init__(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
            super().__init__(*args, **kwargs)
            created.append(self)

    monkeypatch.setattr(plan_object, "PinMap", Recording)
    return created


async def test_a_3d_model_of_an_area_is_planned_with_its_camera_tilt(
    user: User, plan_form: PlanForm
) -> None:
    await user.open("/plan")
    choose(user, "area_3d")
    set_text(user, "centre-input", plan_form.centre)
    set_text(user, "width-input", "80")
    set_text(user, "length-input", "80")
    fill_files(user, plan_form)
    user.find(marker="run").click()
    await user.should_see("Resolution across a picture", retries=300)
    await user.should_see("camera tilted 30 degrees")
    await user.should_see("One picture covers")
    await user.should_not_see("You will get")  # no prediction exists for tilted photos
    files = sorted(Path(plan_form.out_dir).glob("*.kmz"))
    assert files
    pitches = {w.gimbal_pitch_deg for f in files for w in read_mission(f.read_bytes()).waypoints}
    assert pitches == {-60.0}
    assert STATE.last_plan_files == [str(f) for f in files]


async def test_the_tilt_typed_on_the_screen_reaches_the_flight(
    user: User, plan_form: PlanForm
) -> None:
    await user.open("/plan")
    choose(user, "area_3d")
    set_text(user, "centre-input", plan_form.centre)
    set_text(user, "width-input", "80")
    set_text(user, "length-input", "80")
    set_text(user, "tilt-input", "40")
    fill_files(user, plan_form)
    user.find(marker="run").click()
    await user.should_see("camera tilted 40 degrees", retries=300)
    pitches = {
        w.gimbal_pitch_deg
        for f in Path(plan_form.out_dir).glob("*.kmz")
        for w in read_mission(f.read_bytes()).waypoints
    }
    assert pitches == {-50.0}


async def test_a_3d_model_of_one_object_is_planned_from_the_screen(
    user: User, plan_form: PlanForm
) -> None:
    await user.open("/plan")
    choose(user, "object_3d")
    fill_object(user, plan_form)
    user.find(marker="run").click()
    await user.should_see("The rings", retries=300)
    await user.should_see("25 m tall, radius 6 m")
    await user.should_see("176 photos in 4 rings")
    await user.should_see("32 straight down over the top")
    await user.should_see("At every photo point the drone stops")
    await user.should_see("Camera height")
    user.find(marker="scan-rings")
    user.find(marker="to-phone")
    files = sorted(Path(plan_form.out_dir).glob("*.kmz"))
    assert len(files) == 3 and (Path(plan_form.out_dir) / "scan_report.json").is_file()
    assert STATE.last_plan_files == [str(f) for f in files]
    await user.should_see("Next: 2. Send to DJI Fly")  # the way on, at the bottom of the screen


async def test_the_object_settings_typed_on_the_screen_change_the_plan(
    user: User, plan_form: PlanForm
) -> None:
    await user.open("/plan")
    choose(user, "object_3d")
    fill_object(user, plan_form, **{"object-height-input": "10", "object-radius-input": "3"})
    set_text(user, "obj-front-input", "90")
    next(iter(user.find(marker="top-cap-switch").elements)).set_value(False)
    user.find(marker="run").click()
    await user.should_see("10 m tall, radius 3 m", retries=300)
    await user.should_see("no top cap")


async def test_mistakes_in_the_object_form_are_explained(user: User, plan_form: PlanForm) -> None:
    await user.open("/plan")
    choose(user, "object_3d")
    fill_files(user, plan_form)
    user.find(marker="run").click()
    await user.should_see("Position of the object", retries=100)
    set_text(user, "object-centre-input", "12.3456, 98.7654")
    set_text(user, "object-takeoff-input", "far away")
    user.find(marker="run").click()
    await user.should_see("Takeoff point", retries=100)
    set_text(user, "object-takeoff-input", "")
    set_text(user, "object-radius-input", "0.5")
    set_text(user, "object-height-input", "0.6")
    set_text(user, "base-height-input", "2")
    user.find(marker="run").click()
    await user.should_see("higher than", retries=100)  # the planner's own words, shown as they are


async def test_a_plan_too_close_to_the_object_is_refused_and_explained(
    user: User, plan_form: PlanForm
) -> None:
    await user.open("/plan")
    choose(user, "object_3d")
    fill_object(user, plan_form, **{"standoff-input": "3"})
    user.find(marker="run").click()
    await user.should_see("This plan cannot be flown as asked", retries=300)
    await user.should_see("Too close to the object")
    await user.should_see("at least 5 m")
    assert not list(Path(plan_form.out_dir).glob("*.kmz"))


async def test_a_close_but_allowed_plan_is_flagged_for_care(
    user: User, plan_form: PlanForm
) -> None:
    await user.open("/plan")
    choose(user, "object_3d")
    fill_object(user, plan_form, **{"standoff-input": "9"})
    user.find(marker="run").click()
    await user.should_see("Plan ready, but please read the notes", retries=300)
    await user.should_see("Close to the object")
    await user.should_see("The top is covered by photos straight down")  # SC005 is explained too
    assert list(Path(plan_form.out_dir).glob("*.kmz"))


async def test_closer_in_means_looking_up_more_so_a_ring_that_would_fly_too_low_is_refused(
    user: User, plan_form: PlanForm
) -> None:
    await user.open("/plan")
    choose(user, "object_3d")
    fill_object(user, plan_form, **{"standoff-input": "8"})  # the lowest ring would be 2.9 m up
    user.find(marker="run").click()
    await user.should_see("This plan cannot be flown as asked", retries=300)
    await user.should_see("A ring would fly too low")
    await user.should_see("Raise the lowest height to photograph")
    assert not list(Path(plan_form.out_dir).glob("*.kmz"))


async def test_the_object_is_placed_with_a_pin_on_a_map(
    user: User, plan_form: PlanForm, pins: list
) -> None:  # type: ignore[type-arg]
    await user.open("/plan")
    choose(user, "object_3d")
    user.find(marker="object-open-map").click()
    assert len(pins) == 1
    pin = pins[0]
    await user.should_see("No pin yet.")
    pin.add_drawn("marker", {"_latlng": {"lat": 12.3456, "lng": 98.7654}})
    assert value_of(user, "object-centre-input") == "12.345600, 98.765400"
    await user.should_see("Pin at 12.345600, 98.765400")
    pin.add_drawn(
        "marker", {"_latlng": {"lat": 12.3460, "lng": 98.7660}}
    )  # a second pin replaces it
    assert value_of(user, "object-centre-input") == "12.346000, 98.766000" and pin.pin == (
        98.766,
        12.346,
    )
    user.find(marker="pin-remove").click()
    assert pin.pin is None and value_of(user, "object-centre-input") == ""
    await user.should_see("No pin yet.")


async def test_only_a_pin_is_used_on_the_object_map(user: User, pins: list) -> None:  # type: ignore[type-arg]
    await user.open("/plan")
    choose(user, "object_3d")
    user.find(marker="object-open-map").click()
    pins[0].add_drawn(
        "rectangle",
        {
            "_latlngs": [
                [{"lat": 1.0, "lng": 1.0}, {"lat": 1.0, "lng": 2.0}, {"lat": 2.0, "lng": 2.0}]
            ]
        },
    )
    user.notify.contains("Only the pin is used here")
    assert pins[0].pin is None and value_of(user, "object-centre-input") == ""


async def test_the_pin_map_is_built_once_and_a_location_can_become_the_object(
    user: User,
    pins: list,
    monkeypatch: pytest.MonkeyPatch,  # type: ignore[type-arg]
) -> None:
    await user.open("/plan")
    choose(user, "object_3d")
    user.find(marker="object-open-map").click()
    with pytest.raises(AssertionError):
        user.find(marker="object-open-map")  # the button is hidden after use: the map exists once
    assert len(pins) == 1
    pins[0].use_location(12.3456, 98.7654, 20.0)
    await user.should_see("Use it as the object's position")
    user.find(marker="map-takeoff-here").click()
    assert value_of(user, "object-centre-input") == "12.345600, 98.765400"
