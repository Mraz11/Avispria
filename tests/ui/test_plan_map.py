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

from avispria.app.ui.pages.plan_map_text import OSM_URL
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
        "map-tile-url",
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


# ------------------------------------------------------------------ place search and my location
def place(name: str, lat: float, lon: float, box=None):  # type: ignore[no-untyped-def]
    from avispria.adapters.geocode import Place

    return Place(name, lat, lon, box)


MADHUPUR = place(
    "Madhupur, Tangail, Dhaka Division, Bangladesh",
    24.6264,
    90.0383,
    (24.5764, 89.9883, 24.6764, 90.0883),
)
SYLHET = place(
    "Sylhet, Sylhet Division, Bangladesh", 24.8949, 91.8687, (24.80, 91.80, 24.95, 91.95)
)
THIRD = place("Madhupur, a village elsewhere", 10.0, 20.0)


@pytest.fixture
def search(monkeypatch):  # type: ignore[no-untyped-def]
    """Replace the internet: every search is recorded and answered with ``search.answer``."""
    from avispria.app.ui.pages import plan_map_places

    calls: list[tuple[str, str]] = []

    class Fake:
        answer: object = [MADHUPUR]

        def __call__(self, query: str, service: str = "", limit: int = 5):  # type: ignore[no-untyped-def]
            calls.append((query, service))
            if isinstance(self.answer, Exception):
                raise self.answer
            return self.answer

    fake = Fake()
    fake.calls = calls  # type: ignore[attr-defined]
    monkeypatch.setattr(plan_map_places, "search_places", fake)
    return fake


@pytest.mark.parametrize(
    ("text", "coordinates"),
    [
        ("51.5, -0.1", True),
        ("23.8°N 90.4°E", True),
        ("-12.5; 130.8", True),
        ("Dhaka", False),
        ("Road 5", False),
        ("Sylhet 3100", False),
        ("N", False),
        ("5 W", False),
    ],
)
def test_what_looks_like_coordinates_is_not_searched_for(text: str, coordinates: bool) -> None:
    from avispria.app.ui.pages.plan_map_places import looks_like_coordinates

    assert looks_like_coordinates(text) is coordinates


def test_the_map_zoom_fits_the_place() -> None:
    from avispria.app.ui.pages.plan_map_places import zoom_for

    assert zoom_for(place("a street", 1.0, 1.0)) == 15  # no box: a street-level view
    assert zoom_for(MADHUPUR) == 13  # a town: about 11 km across
    assert 5 <= zoom_for(place("a country", 23.7, 90.4, (20.6, 88.0, 26.6, 92.7))) <= 7
    assert zoom_for(place("the world", 0.0, 0.0, (-85.0, -180.0, 85.0, 180.0))) == 3
    assert zoom_for(place("a house", 1.0, 1.0, (1.0, 1.0, 1.0, 1.0))) == 17


async def test_typed_coordinates_go_straight_there_without_any_search(
    user: User, maps, search
) -> None:  # type: ignore[no-untyped-def]
    area = await draw_mode(user, maps)
    set_text(user, "map-goto-input", "51.5, -0.1")
    user.find(marker="map-goto").click()
    await eventually(lambda: area.map._props["center"] == (51.5, -0.1))
    assert search.calls == []  # nothing was sent anywhere


async def test_a_place_name_is_searched_for_and_the_map_moves_there(
    user: User, maps, search
) -> None:  # type: ignore[no-untyped-def]
    from avispria.app.ui.pages.plan_map_places import zoom_for

    area = await draw_mode(user, maps)
    set_text(user, "map-goto-input", "Madhupur")
    user.find(marker="map-goto").click()
    await user.should_see("Showing: Madhupur, Tangail", retries=100)
    assert area.map._props["center"] == (24.6264, 90.0383) and area.map._props["zoom"] == zoom_for(
        MADHUPUR
    )
    assert search.calls == [("Madhupur", "")]
    await user.should_see("OpenStreetMap contributors")  # the credit the service asks for


async def test_several_matches_are_listed_and_the_one_clicked_is_shown(
    user: User, maps, search
) -> None:  # type: ignore[no-untyped-def]
    search.answer = [MADHUPUR, SYLHET, THIRD]
    area = await draw_mode(user, maps)
    set_text(user, "map-goto-input", "Madhupur")
    user.find(marker="map-goto").click()
    await user.should_see("Which one?", retries=100)
    for name in (MADHUPUR.name, SYLHET.name, THIRD.name):
        await user.should_see(name)
    assert area.map._props["center"] == (20.0, 0.0)  # nothing has moved yet
    user.find(marker="place-2").click()
    await eventually(lambda: area.map._props["center"] == (10.0, 20.0))
    await user.should_see("Showing: Madhupur, a village elsewhere")


async def test_nothing_found_and_a_failing_search_are_explained(user: User, maps, search) -> None:  # type: ignore[no-untyped-def]
    from avispria.adapters.geocode import GeocodeError

    search.answer = []
    area = await draw_mode(user, maps)
    set_text(user, "map-goto-input", "Zzqqxx")
    user.find(marker="map-goto").click()
    await user.should_see("No place found for 'Zzqqxx'", retries=100)
    search.answer = GeocodeError(
        "The search needs the internet and the service could not be reached."
    )
    set_text(user, "map-goto-input", "Dhaka")
    user.find(marker="map-goto").click()
    await user.should_see("The search needs the internet", retries=100)
    assert area.map._props["center"] == (20.0, 0.0)  # and the map did not move


async def test_an_empty_search_box_asks_for_something_to_search_for(
    user: User, maps, search
) -> None:  # type: ignore[no-untyped-def]
    await draw_mode(user, maps)
    user.find(marker="map-goto").click()
    user.notify.contains("Type a place name")
    assert search.calls == []


async def test_another_search_service_is_used_and_the_openstreetmap_credit_is_not_claimed_for_it(
    user: User, maps, search
) -> None:  # type: ignore[no-untyped-def]
    await draw_mode(user, maps)
    set_text(user, "map-search-service", "https://geo.example.org/search")
    set_text(user, "map-goto-input", "Dhaka")
    user.find(marker="map-goto").click()
    await user.should_see("Showing:", retries=100)
    assert search.calls == [("Dhaka", "https://geo.example.org/search")]
    await user.should_not_see("OpenStreetMap contributors")


class Browser:
    """Stands in for the browser's answer to 'where am I?'."""

    def __init__(self, answer: object) -> None:
        self.answer = answer

    async def __call__(self, *args: object) -> object:
        return self.answer


async def ask_location(user: User, area, answer: object, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(type(area), "_browser_location", Browser(answer))
    user.find(marker="map-location").click()


async def test_my_location_shows_where_the_computer_is_with_its_accuracy(
    user: User, maps, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    area = await draw_mode(user, maps)
    await ask_location(user, area, {"lat": 23.8, "lon": 90.4, "accuracy": 25.0}, monkeypatch)
    await user.should_see("to within about 25 m", retries=100)
    assert area.map._props["center"] == (23.8, 90.4) and area.map._props["zoom"] == 16
    assert len(area.map.layers) == 2  # a marker and the circle of uncertainty
    await user.should_see("Use it as the takeoff point")
    user.find(marker="map-takeoff-here").click()
    await eventually(lambda: area.takeoff == (90.4, 23.8))
    assert value_of(user, "takeoff-input") == "23.800000, 90.400000"


async def test_a_rough_location_says_so_and_does_not_offer_to_be_the_takeoff_point(
    user: User, maps, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    area = await draw_mode(user, maps)
    await ask_location(user, area, {"lat": 23.8, "lon": 90.4, "accuracy": 5000.0}, monkeypatch)
    await user.should_see("to within about 5.0 km", retries=100)
    await user.should_see("knows only roughly where it is")
    await user.should_not_see("Use it as the takeoff point")
    assert area.map._props["zoom"] == 11


async def test_asking_again_replaces_the_old_marker(user: User, maps, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    area = await draw_mode(user, maps)
    await ask_location(user, area, {"lat": 23.8, "lon": 90.4, "accuracy": 25.0}, monkeypatch)
    await user.should_see("to within about 25 m", retries=100)
    await ask_location(user, area, {"lat": 23.9, "lon": 90.5, "accuracy": 40.0}, monkeypatch)
    await eventually(lambda: area.map._props["center"] == (23.9, 90.5))
    assert len(area.map.layers) == 2  # not four


@pytest.mark.parametrize(
    ("answer", "message"),
    [
        (
            {"error": "The browser did not allow it. Allow location for this page"},
            "did not allow it",
        ),
        ({"error": "Finding the location took too long."}, "took too long"),
        (None, "No answer from the browser"),
        ({"lat": "x", "lon": 1, "accuracy": 3}, "Your location could not be used"),
        ({"lat": 95.0, "lon": 1.0, "accuracy": 3.0}, "not valid"),
        ({"lat": 5.0, "lon": 1.0}, "Your location could not be used"),
    ],
)
async def test_a_location_that_does_not_come_is_explained(
    user: User, maps, monkeypatch, answer: object, message: str
) -> None:  # type: ignore[no-untyped-def]
    area = await draw_mode(user, maps)
    await ask_location(user, area, answer, monkeypatch)
    await user.should_see(message, retries=100)
    assert area.map._props["center"] == (20.0, 0.0) and area.map.layers == []


async def test_a_browser_that_never_answers_is_reported_not_waited_for_forever(
    user: User, maps, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    from avispria.app.ui.pages import plan_map, plan_map_places

    async def silent(*args: object, **kwargs: object) -> object:
        raise TimeoutError

    area = await draw_mode(user, maps)
    monkeypatch.setattr(plan_map.ui, "run_javascript", silent)
    assert await area._browser_location() == {"error": "The browser did not answer in time."}
    assert (
        "navigator.geolocation" in plan_map_places.LOCATION_JS
        and "http://127.0.0.1" in plan_map_places.LOCATION_JS
    )


# ------------------------------------------------------------------------ editing and undo
def click_at(lat: float, lon: float) -> SimpleNamespace:
    """What the map sends when the person clicks it."""
    return SimpleNamespace(args={"latlng": {"lat": lat, "lng": lon}})


def corner_of(area, shape_id: int, index: int):  # type: ignore[no-untyped-def]
    shape = next(s for s in area.shapes if s.id == shape_id)
    return shape.points[index]


def total_area(area) -> float:  # type: ignore[no-untyped-def]
    return sum(p.area_m2 for p in area.result.pieces)


def test_leaflets_own_edit_tool_that_cannot_work_here_is_hidden_and_corner_labels_are_styled() -> (
    None
):
    from avispria.app.ui.pages.plan_map_edit import EDIT_CSS

    assert ".leaflet-draw-edit-edit" in EDIT_CSS and "display: none" in EDIT_CSS
    assert ".avispria-corner" in EDIT_CSS


async def test_a_corner_is_moved_by_picking_it_and_clicking_the_map(user: User, maps) -> None:  # type: ignore[no-untyped-def]
    area = await draw_mode(user, maps)
    area.add_drawn("rectangle", BIG)
    before = total_area(area)
    original = corner_of(area, 1, 2)
    user.find(marker="shape-edit-1").click()
    await user.should_see("Pick a corner by its number")
    assert len(area._corner_layers) == 4  # a numbered disc on each corner
    area._map_click(
        click_at(original[1] + 0.0005, original[0] + 0.0005)
    )  # nothing picked yet: ignored
    assert corner_of(area, 1, 2) == original
    user.find(marker="corner-1-2").click()
    assert area.selected == 2
    area._map_click(click_at(original[1] + 0.0004, original[0] + 0.0006))
    assert corner_of(area, 1, 2) == pytest.approx((original[0] + 0.0006, original[1] + 0.0004))
    assert area.shapes[0].kind == "polygon"  # a rectangle whose corner moved is a polygon now
    assert total_area(area) != before
    await user.should_see("Polygon 1")


async def test_clicking_the_map_does_nothing_when_no_shape_is_being_edited(
    user: User, maps
) -> None:  # type: ignore[no-untyped-def]
    area = await draw_mode(user, maps)
    area.add_drawn("rectangle", BIG)
    shapes = list(area.shapes)
    area._map_click(click_at(51.4770, -0.0010))
    area._map_click(SimpleNamespace(args={"latlng": "nowhere"}))  # and nonsense is ignored too
    assert area.shapes == shapes


async def test_a_corner_can_be_added_in_the_middle_of_the_longest_side_and_removed_again(
    user: User, maps
) -> None:  # type: ignore[no-untyped-def]
    area = await draw_mode(user, maps)
    area.add_drawn("rectangle", BIG)
    before = total_area(area)
    user.find(marker="shape-edit-1").click()
    user.find(marker="edit-add-corner").click()
    assert len(area.shapes[0].points) == 5 and area.selected is not None
    await user.should_see("Remove the picked corner")
    assert total_area(area) == pytest.approx(before, rel=0.001)  # a new corner changes no outline
    added = area.selected
    user.find(marker="edit-remove-corner").click()  # the new corner is picked: take it away again
    assert len(area.shapes[0].points) == 4 and area.selected is None and added is not None


async def test_removing_with_nothing_picked_and_below_the_minimum_is_explained(
    user: User, maps
) -> None:  # type: ignore[no-untyped-def]
    area = await draw_mode(user, maps)
    area.add_drawn("rectangle", BIG)
    user.find(marker="shape-edit-1").click()
    user.find(marker="edit-remove-corner").click()
    user.notify.contains("Pick the corner to remove first")
    user.find(marker="corner-1-0").click()
    user.find(marker="edit-remove-corner").click()  # 4 -> 3 corners: allowed
    assert len(area.shapes[0].points) == 3
    user.find(marker="corner-1-0").click()
    user.find(marker="edit-remove-corner").click()
    user.notify.contains("at least 3 corners")
    assert len(area.shapes[0].points) == 3


async def test_a_move_that_makes_the_outline_cross_itself_is_refused_and_leaves_the_shape_alone(
    user: User, maps
) -> None:  # type: ignore[no-untyped-def]
    area = await draw_mode(user, maps)
    area.add_drawn("rectangle", BIG)
    p0, p1, p2, _ = area.shapes[0].points
    far = (
        p1[1] + (p1[1] - p0[1]) + (p2[1] - p1[1]) / 2,
        p1[0] + (p1[0] - p0[0]) + (p2[0] - p1[0]) / 2,
    )
    user.find(marker="shape-edit-1").click()
    user.find(marker="corner-1-0").click()
    steps = len(area._history)
    area._map_click(click_at(*far))
    user.notify.contains("crosses itself")
    assert area.shapes[0].points[0] == p0 and area.shapes[0].kind == "rectangle"
    assert len(area._history) == steps  # a refused change is not a step to undo


async def test_a_circles_centre_is_moved_by_a_click_and_its_radius_is_typed(
    user: User, maps
) -> None:  # type: ignore[no-untyped-def]
    area = await draw_mode(user, maps)
    area.add_drawn("circle", {"_latlng": {"lat": 51.4790, "lng": 0.0}, "_mRadius": 40})
    user.find(marker="shape-edit-1").click()
    await user.should_see("the radius is typed here")
    assert len(area._corner_layers) == 1
    user.find(marker="corner-1-0").click()
    area._map_click(click_at(51.4800, 0.0010))
    assert area.shapes[0].points == ((0.0010, 51.4800),) and area.shapes[0].radius_m == 40
    small = total_area(area)
    next(iter(user.find(marker="edit-radius").elements)).set_value(80)
    assert area.shapes[0].radius_m == 80 and total_area(area) > small * 3.5


async def test_done_and_starting_to_draw_and_deleting_all_leave_editing(user: User, maps) -> None:  # type: ignore[no-untyped-def]
    area = await draw_mode(user, maps)
    area.add_drawn("rectangle", BIG)
    user.find(marker="shape-edit-1").click()
    user.find(marker="edit-done").click()
    assert area.editing is None and area._corner_layers == []
    await user.should_not_see("Pick a corner by its number")
    user.find(marker="shape-edit-1").click()
    area._stop_when_drawing(SimpleNamespace(args={}))  # a drawing tool was picked
    assert area.editing is None
    user.find(marker="shape-edit-1").click()
    user.find(marker="shape-delete-1").click()  # deleting the shape that is being edited
    assert area.editing is None and area.shapes == [] and area._corner_layers == []


async def test_undo_takes_back_one_change_at_a_time_whatever_it_was(user: User, maps) -> None:  # type: ignore[no-untyped-def]
    area = await draw_mode(user, maps)
    assert area.undo_button.enabled is False  # nothing to undo yet
    area.add_drawn("rectangle", BIG)
    assert area.undo_button.enabled is True
    area.add_drawn("rectangle", SMALL)
    assert [s.role for s in area.shapes] == [Role.INSIDE, Role.LEAVE_OUT]
    next(iter(user.find(marker="shape-role-2").elements)).set_value(Role.INSIDE)
    user.find(marker="shape-delete-2").click()
    assert len(area.shapes) == 1
    user.find(marker="map-undo").click()  # the delete
    assert len(area.shapes) == 2 and area.shapes[1].role == Role.INSIDE
    user.find(marker="map-undo").click()  # the role
    assert area.shapes[1].role == Role.LEAVE_OUT
    user.find(marker="map-undo").click()  # the second shape
    assert [s.id for s in area.shapes] == [1]
    user.find(marker="map-undo").click()  # the first
    assert area.shapes == [] and area.undo_button.enabled is False
    user.find(marker="map-undo").click()  # and past the start: nothing happens
    assert area.shapes == []


async def test_undo_brings_back_everything_removed_and_the_takeoff_pin_and_its_box(
    user: User, maps
) -> None:  # type: ignore[no-untyped-def]
    area = await draw_mode(user, maps)
    area.add_drawn("rectangle", BIG)
    area.add_drawn("marker", {"_latlng": {"lat": 51.4755, "lng": -0.0031}})
    assert value_of(user, "takeoff-input") == "51.475500, -0.003100"
    user.find(marker="map-clear").click()
    assert area.shapes == [] and value_of(user, "takeoff-input") == ""
    user.find(marker="map-undo").click()
    assert len(area.shapes) == 1 and area.takeoff == (-0.0031, 51.4755)
    assert value_of(user, "takeoff-input") == "51.475500, -0.003100"  # the box follows the pin back
    user.find(marker="map-undo").click()  # the pin itself
    assert area.takeoff is None and value_of(user, "takeoff-input") == ""


async def test_an_edit_is_one_step_to_undo_and_undo_returns_the_old_corner(
    user: User, maps
) -> None:  # type: ignore[no-untyped-def]
    area = await draw_mode(user, maps)
    area.add_drawn("rectangle", BIG)
    original = corner_of(area, 1, 1)
    user.find(marker="shape-edit-1").click()
    user.find(marker="corner-1-1").click()
    area._map_click(click_at(original[1] + 0.0003, original[0]))
    assert corner_of(area, 1, 1) != original
    user.find(marker="map-undo").click()
    assert corner_of(area, 1, 1) == original and area.shapes[0].kind == "rectangle"


async def test_typing_a_width_digit_by_digit_is_one_step_to_undo(user: User, maps) -> None:  # type: ignore[no-untyped-def]
    area = await draw_mode(user, maps)
    area.add_drawn(
        "polyline",
        {"_latlngs": [{"lat": 51.4760, "lng": -0.0030}, {"lat": 51.4760, "lng": -0.0005}]},
    )
    steps = len(area._history)
    for width in (5, 50, 500):  # what typing "500" sends, one digit at a time
        next(iter(user.find(marker="shape-width-1").elements)).set_value(width)
    assert area.shapes[0].width_m == 500
    assert len(area._history) == steps + 1
    user.find(marker="map-undo").click()
    assert area.shapes[0].width_m == 30.0  # back to what it was before typing began
