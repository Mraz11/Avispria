# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The drawing map on the Plan a flight screen.

The browser's drawing toolbar cannot run here, so a test hands the map what the toolbar would send
(``AreaMap.add_drawn``) and checks what the screen then shows and what the plan receives.
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from nicegui.testing import User

from avispria.app.ui.pages.plan_map import OSM_URL
from avispria.core.shapes import Role
from uihelpers import eventually, set_text, value_of

pytestmark = [pytest.mark.anyio, pytest.mark.nicegui_main_file("tests/ui/ui_main.py")]


def corners(lat0: float, lon0: float, dlat: float, dlon: float) -> dict:  # type: ignore[type-arg]
    pts = [(lat0, lon0), (lat0, lon0 + dlon), (lat0 + dlat, lon0 + dlon), (lat0 + dlat, lon0)]
    return {"_latlngs": [[{"lat": a, "lng": b} for a, b in pts]]}


BIG = corners(51.4760, -0.0030, 0.0018, 0.0030)  # about 200 m x 130 m
SMALL = corners(51.4766, -0.0020, 0.0004, 0.0006)  # inside it, about 25 m x 45 m
FAR = corners(51.4800, 0.0100, 0.0010, 0.0016)  # elsewhere, about 110 m x 110 m


async def draw_mode(user: User, maps: list) -> object:  # type: ignore[type-arg]
    await user.open("/plan")
    next(iter(user.find(marker="area-mode").elements)).set_value("drawn")
    await user.should_see("Show map background", retries=100)
    assert len(maps) == 1
    return maps[0]


async def test_the_map_appears_only_when_asked_for_and_loads_nothing_from_the_internet(
    user: User, maps
) -> None:  # type: ignore[no-untyped-def]
    await user.open("/plan")
    await user.should_not_see("Show map background")  # not built for the other two ways of choosing
    assert maps == []
    next(iter(user.find(marker="area-mode").elements)).set_value("drawn")
    await user.should_see("Show map background", retries=100)
    await user.should_see("Draw at least one shape on the map.")
    await user.should_not_see(marker="centre-input")  # the numbers are put away
    assert maps[0].map.layers == []  # no background, so nothing is fetched until the person asks


async def test_drawing_a_rectangle_shows_it_in_the_list_with_its_size(user: User, maps) -> None:  # type: ignore[no-untyped-def]
    area = await draw_mode(user, maps)
    area.add_drawn("rectangle", BIG)
    await user.should_see("Rectangle 1")
    await user.should_see("Map inside it")
    await user.should_see("Area to map:")
    assert json.loads(area.geojson())["type"] == "Polygon" and area.problem is None
    assert len(area.map.layers) == 2  # the shape itself, and the green area that will be planned


async def test_a_shape_drawn_inside_another_becomes_a_part_to_leave_out(user: User, maps) -> None:  # type: ignore[no-untyped-def]
    area = await draw_mode(user, maps)
    area.add_drawn("rectangle", BIG)
    whole = sum(p.area_m2 for p in area.result.pieces)
    area.add_drawn("rectangle", SMALL)
    assert area.shapes[1].role == Role.LEAVE_OUT
    assert sum(p.area_m2 for p in area.result.pieces) < whole
    assert len(json.loads(area.geojson())["coordinates"]) == 2  # outline plus a hole
    await user.should_see("Leave it out")
    await user.should_see("may still fly over them")  # the honest note about leaving out


async def test_changing_a_role_and_a_width_and_deleting_update_the_area(user: User, maps) -> None:  # type: ignore[no-untyped-def]
    area = await draw_mode(user, maps)
    area.add_drawn("rectangle", BIG)
    area.add_drawn("rectangle", SMALL)
    cut = sum(p.area_m2 for p in area.result.pieces)
    next(iter(user.find(marker="shape-role-2").elements)).set_value(
        Role.INSIDE
    )  # as a person would
    assert sum(p.area_m2 for p in area.result.pieces) > cut
    next(iter(user.find(marker="shape-role-2").elements)).set_value(Role.BAND)
    await user.should_see("Width (m)")
    narrow = sum(p.area_m2 for p in area.result.pieces)
    next(iter(user.find(marker="shape-width-2").elements)).set_value(80)
    assert sum(p.area_m2 for p in area.result.pieces) > narrow
    user.find(marker="shape-delete-2").click()
    await user.should_not_see("Rectangle 2")
    assert [s.id for s in area.shapes] == [1]


async def test_a_line_becomes_a_strip_and_a_circle_is_an_area(user: User, maps) -> None:  # type: ignore[no-untyped-def]
    area = await draw_mode(user, maps)
    area.add_drawn(
        "polyline",
        {"_latlngs": [{"lat": 51.4760, "lng": -0.0030}, {"lat": 51.4760, "lng": -0.0005}]},
    )
    await user.should_see("Line 1")
    await user.should_see("Map a strip along it")
    await user.should_see("m long")
    strip = area.result.pieces[0].area_m2
    assert strip == pytest.approx(30 * 170, rel=0.05)  # 30 m wide by about 170 m
    area.add_drawn("circle", {"_latlng": {"lat": 51.4790, "lng": 0.0}, "_mRadius": 40})
    assert len(area.result.pieces) == 2


async def test_the_takeoff_pin_fills_in_the_takeoff_box_and_can_be_removed(
    user: User, maps
) -> None:  # type: ignore[no-untyped-def]
    area = await draw_mode(user, maps)
    area.add_drawn("rectangle", BIG)
    area.add_drawn("marker", {"_latlng": {"lat": 51.4755, "lng": -0.0031}})
    assert value_of(user, "takeoff-input") == "51.475500, -0.003100"
    await user.should_see("Takeoff point: 51.475500, -0.003100")
    assert area.takeoff_text() == "51.475500, -0.003100"
    area.add_drawn(
        "marker", {"_latlng": {"lat": 51.4756, "lng": -0.0032}}
    )  # a second pin replaces it
    assert area.takeoff_text() == "51.475600, -0.003200"
    user.find(marker="map-remove-takeoff").click()
    await eventually(lambda: area.takeoff is None)
    assert value_of(user, "takeoff-input") == ""


async def test_separate_areas_are_planned_one_at_a_time(user: User, maps) -> None:  # type: ignore[no-untyped-def]
    area = await draw_mode(user, maps)
    area.add_drawn("rectangle", BIG)
    area.add_drawn("rectangle", FAR)
    assert [s.role for s in area.shapes] == [Role.INSIDE, Role.INSIDE]
    await user.should_see("2 separate pieces")
    await user.should_see("Plan this piece now")
    first = json.loads(area.geojson())
    next(iter(user.find(marker="map-piece").elements)).set_value(1)
    assert json.loads(area.geojson()) != first  # now the other piece


async def test_everything_cut_away_says_so_and_nothing_is_planned(user: User, maps) -> None:  # type: ignore[no-untyped-def]
    area = await draw_mode(user, maps)
    area.add_drawn("rectangle", SMALL)
    area.add_drawn("rectangle", SMALL)  # drawn exactly on top of the first: it is inside it
    await user.should_see("cut away by the parts you left out")
    assert area.geojson() == "" and area.problem is not None


async def test_the_background_is_opt_in_attributed_and_can_use_another_source(
    user: User, maps
) -> None:  # type: ignore[no-untyped-def]
    area = await draw_mode(user, maps)
    assert area.map.layers == []
    area.background.set_value(True)
    (tile,) = area.map.layers
    assert tile.url_template == OSM_URL and "OpenStreetMap" in tile.options["attribution"]
    area.background.set_value(False)
    assert area.map.layers == []
    set_text(
        user,
        "map-tile-url-input" if False else "map-tile-url",
        "https://tiles.example.org/{z}/{x}/{y}.png",
    )
    area.background.set_value(True)
    (tile,) = area.map.layers
    assert tile.url_template == "https://tiles.example.org/{z}/{x}/{y}.png"
    assert "OpenStreetMap" not in tile.options["attribution"]  # not claimed for another source


async def test_go_to_moves_the_map_and_a_bad_address_is_explained(user: User, maps) -> None:  # type: ignore[no-untyped-def]
    area = await draw_mode(user, maps)
    area.go_to("51.5, -0.1")
    assert area.map._props["center"] == (51.5, -0.1) and area.map._props["zoom"] == 16
    area.go_to("somewhere")
    user.notify.contains("latitude")


async def test_a_shape_the_browser_sends_wrongly_is_reported_not_swallowed(
    user: User, maps
) -> None:  # type: ignore[no-untyped-def]
    area = await draw_mode(user, maps)
    area._created(SimpleNamespace(args={"layerType": "polygon", "layer": {"_latlngs": []}}))
    user.notify.contains("That shape was not used")
    area._created(SimpleNamespace(args={}))
    assert area.shapes == []


async def test_clearing_removes_every_shape_and_the_pin(user: User, maps) -> None:  # type: ignore[no-untyped-def]
    area = await draw_mode(user, maps)
    area.add_drawn("rectangle", BIG)
    area.add_drawn("marker", {"_latlng": {"lat": 51.4755, "lng": -0.0031}})
    assert value_of(user, "takeoff-input") == "51.475500, -0.003100"
    user.find(marker="map-clear").click()
    await user.should_not_see("Rectangle 1")
    assert area.shapes == [] and area.takeoff is None and area.geojson() == ""
    assert value_of(user, "takeoff-input") == ""  # no stale takeoff point is left in the form


async def test_a_plan_made_from_a_drawn_area_with_a_hole_keeps_the_hole(
    user: User, maps, plan_form
) -> None:  # type: ignore[no-untyped-def]
    area = await draw_mode(user, maps)
    area.add_drawn("rectangle", corners(23.8100, 90.4120, 0.0018, 0.0020))
    area.add_drawn("rectangle", corners(23.8106, 90.4128, 0.0004, 0.0004))
    area.add_drawn("marker", {"_latlng": {"lat": 23.8099, "lng": 90.4121}})
    set_text(user, "template-input", plan_form.template)
    set_text(user, "out-input", plan_form.out_dir)
    set_text(user, "target-input", "3")
    user.find(marker="run").click()
    await user.should_see("Missions", retries=300)
    saved = json.loads((Path(plan_form.out_dir) / "survey_area.geojson").read_text())
    assert len(saved["coordinates"]) == 2  # the plan was made for an area with a hole


async def test_planning_without_a_drawn_area_asks_for_one(user: User, maps, plan_form) -> None:  # type: ignore[no-untyped-def]
    await draw_mode(user, maps)
    set_text(user, "template-input", plan_form.template)
    set_text(user, "out-input", plan_form.out_dir)
    user.find(marker="run").click()
    await user.should_see("Draw at least one shape on the map.", retries=100)
