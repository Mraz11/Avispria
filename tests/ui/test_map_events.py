# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest

from avispria.app.ui.map_events import Drawn, event_layer, parse_layer

CORNERS = [(51.0, -0.002), (51.0, 0.002), (51.002, 0.002), (51.002, -0.002)]  # (lat, lng)


def latlngs(pairs):  # type: ignore[no-untyped-def]
    return [{"lat": lat, "lng": lng} for lat, lng in pairs]


@pytest.mark.parametrize("kind", ["polygon", "rectangle"])
@pytest.mark.parametrize("nesting", ["rings", "flat", "pairs"])
def test_areas_are_read_from_every_shape_the_widget_may_send(kind: str, nesting: str) -> None:
    pts = latlngs(CORNERS)
    raw = {"rings": [pts], "flat": pts, "pairs": [[list(p) for p in CORNERS]]}[nesting]
    drawn = parse_layer(kind, {"_latlngs": raw})
    assert drawn == Drawn(
        kind, tuple((lng, lat) for lat, lng in CORNERS)
    )  # lon first, as everywhere else


def test_a_ring_that_repeats_its_first_point_loses_the_repeat() -> None:
    pts = latlngs([*CORNERS, CORNERS[0]])
    assert len(parse_layer("polygon", {"_latlngs": [pts]}).points) == 4


def test_a_line_is_a_flat_list_and_keeps_every_vertex() -> None:
    drawn = parse_layer("polyline", {"_latlngs": latlngs(CORNERS[:3])})
    assert drawn.kind == "line" and len(drawn.points) == 3 and drawn.points[0] == (-0.002, 51.0)


def test_a_circle_has_a_centre_and_a_radius_in_metres() -> None:
    drawn = parse_layer("circle", {"_latlng": {"lat": 51.0, "lng": 0.5}, "_mRadius": 42.5})
    assert drawn == Drawn("circle", ((0.5, 51.0),), 42.5)


def test_a_marker_is_one_point() -> None:
    assert parse_layer("marker", {"_latlng": {"lat": 51.0, "lng": 0.5}}) == Drawn(
        "marker", ((0.5, 51.0),)
    )


@pytest.mark.parametrize(
    ("layer_type", "layer", "message"),
    [
        ("circlemarker", {"_latlng": {"lat": 1, "lng": 1}}, "cannot be used here"),
        ("circle", {"_latlng": {"lat": 1, "lng": 1}, "_mRadius": 0}, "no radius"),
        ("circle", {"_latlng": {"lat": 1, "lng": 1}}, "no radius"),
        ("circle", {"_latlng": "nowhere", "_mRadius": 5}, "not understood"),
        ("polygon", {"_latlngs": []}, "no points"),
        ("polygon", {}, "no points"),
        ("polygon", {"_latlngs": [[{"lat": "x", "lng": 1}]]}, "not understood"),
        ("marker", {}, "not understood"),
    ],
)
def test_what_cannot_be_understood_is_said_plainly(
    layer_type: str, layer: dict, message: str
) -> None:  # type: ignore[type-arg]
    with pytest.raises(ValueError, match=message):
        parse_layer(layer_type, layer)


def test_the_event_arguments_are_checked() -> None:
    assert event_layer({"layerType": "marker", "layer": {"_latlng": {}}})[0] == "marker"
    for bad in ({}, {"layerType": "polygon"}, {"layerType": 3, "layer": {}}, {"layer": {}}):
        with pytest.raises(ValueError, match="did not say"):
            event_layer(bad)
