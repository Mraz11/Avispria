# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import math
import random

import pytest
from shapely.geometry import Polygon

from avispria.core.geometry import rectangle_polygon
from avispria.core.shapes import (
    DEFAULT_WIDTH_M,
    DrawnShape,
    Role,
    ShapeError,
    build_area,
    shape_size,
    suggest_role,
)

LAT, LON = 51.4769, -0.0015


def rect(
    i: int,
    width: float,
    length: float,
    dx: float = 0.0,
    dy: float = 0.0,
    role: Role = Role.INSIDE,
    **kw: float,
) -> DrawnShape:
    """A rectangle ``width`` x ``length`` metres, its centre moved dx metres east and dy north."""
    dlat = dy / 111_320.0
    dlon = dx / (111_320.0 * math.cos(math.radians(LAT)))
    ring = rectangle_polygon(LAT + dlat, LON + dlon, width, length, 0.0).exterior.coords
    return DrawnShape(i, "rectangle", tuple((x, y) for x, y in list(ring)[:4]), role=role, **kw)


def line(i: int, length: float, width: float = 20.0) -> DrawnShape:
    dlon = length / (111_320.0 * math.cos(math.radians(LAT)))
    return DrawnShape(i, "line", ((LON, LAT), (LON + dlon, LAT)), role=Role.CORRIDOR, width_m=width)


def circle(i: int, radius: float, role: Role = Role.INSIDE) -> DrawnShape:
    return DrawnShape(i, "circle", ((LON, LAT),), radius_m=radius, role=role)


def total(result) -> float:  # type: ignore[no-untyped-def]
    return sum(p.area_m2 for p in result.pieces)


def test_one_rectangle_is_that_area() -> None:
    result = build_area([rect(1, 100, 100)])
    assert len(result.pieces) == 1 and result.pieces[0].area_m2 == pytest.approx(10_000, rel=0.01)
    assert result.pieces[0].polygon.centroid.x == pytest.approx(LON, abs=1e-4)
    assert result.pieces[0].polygon.centroid.y == pytest.approx(LAT, abs=1e-4)  # back in lon/lat


def test_a_shape_inside_another_can_be_left_out_and_becomes_a_hole() -> None:
    result = build_area([rect(1, 200, 200), rect(2, 50, 50, role=Role.LEAVE_OUT)])
    (piece,) = result.pieces
    assert piece.area_m2 == pytest.approx(40_000 - 2_500, rel=0.01)
    assert len(piece.polygon.interiors) == 1  # the planner takes one polygon, with a hole


def test_leaving_out_a_strip_across_the_area_makes_two_pieces_largest_first() -> None:
    cut = rect(2, 400, 20, dx=0, dy=40, role=Role.LEAVE_OUT)  # a road 40 m north of the centre
    result = build_area([rect(1, 200, 200), cut])
    assert len(result.pieces) == 2
    assert result.pieces[0].area_m2 > result.pieces[1].area_m2
    assert total(result) == pytest.approx(200 * 200 - 200 * 20, rel=0.01)


def test_a_band_maps_the_outside_of_a_shape_and_not_the_shape_itself() -> None:
    """'Map the outside of the polygon': a ring of 30 m around a 50 m building."""
    result = build_area([rect(1, 50, 50, role=Role.BAND, width_m=30.0)])
    (piece,) = result.pieces
    # the outer outline has rounded corners: (50 + 60)^2 minus the cut corners, minus the building
    expected = (50 + 60) ** 2 - (4 - math.pi) * 30**2 - 50 * 50
    assert piece.area_m2 == pytest.approx(expected, rel=0.01)
    assert len(piece.polygon.interiors) == 1  # the building is the hole


def test_a_line_becomes_a_strip_of_its_width() -> None:
    result = build_area([line(1, 200.0, width=20.0)])
    assert total(result) == pytest.approx(200 * 20, rel=0.01)


def test_a_circle_is_a_round_area() -> None:
    assert total(build_area([circle(1, 40)])) == pytest.approx(math.pi * 40**2, rel=0.01)


def test_a_circle_can_be_left_out_of_a_rectangle() -> None:
    result = build_area([rect(1, 200, 200), circle(2, 30, role=Role.LEAVE_OUT)])
    assert total(result) == pytest.approx(40_000 - math.pi * 30**2, rel=0.01)


def test_a_leave_out_also_cuts_a_corridor() -> None:
    result = build_area([line(1, 200.0, width=20.0), rect(2, 40, 100, dx=100, role=Role.LEAVE_OUT)])
    assert len(result.pieces) == 2  # the line is cut in two by a gap in the middle


def test_the_order_in_which_shapes_were_drawn_does_not_matter() -> None:
    shapes = [
        rect(1, 200, 200),
        rect(2, 50, 50, role=Role.LEAVE_OUT),
        line(3, 150.0),
        circle(4, 25),
    ]
    reference = total(build_area(shapes))
    rng = random.Random(3)
    for _ in range(6):
        rng.shuffle(shapes)
        assert total(build_area(shapes)) == pytest.approx(reference, rel=1e-9)


def test_pieces_too_small_to_fly_are_dropped_and_reported() -> None:
    result = build_area([rect(1, 100, 100), rect(2, 6, 6, dx=300)])  # a 36 m2 speck far away
    assert len(result.pieces) == 1 and result.dropped_m2 == pytest.approx(36, rel=0.05)


@pytest.mark.parametrize(
    ("shapes", "message"),
    [
        ([], "Draw at least one shape"),
        ([rect(1, 100, 100, role=Role.LEAVE_OUT)], "Nothing is set to be mapped"),
        (
            [rect(1, 50, 50), rect(2, 200, 200, role=Role.LEAVE_OUT)],
            "cut away by the parts you left out",
        ),
        ([rect(1, 5, 5)], "too small"),
        ([line(1, 100.0, width=0.0)], "width must be between"),
        ([line(1, 100.0, width=5000.0)], "width must be between"),
        ([rect(1, 50, 50, role=Role.BAND, width_m=0.0)], "width must be between"),
        (
            [DrawnShape(1, "line", ((LON, LAT), (LON, LAT)), role=Role.CORRIDOR)],
            "two different points",
        ),
        (
            [DrawnShape(1, "line", ((LON, LAT), (LON + 0.001, LAT)), role=Role.INSIDE)],
            "cannot be set to",
        ),
        (
            [DrawnShape(1, "polygon", ((LON, LAT), (LON + 0.001, LAT)), role=Role.INSIDE)],
            "at least three",
        ),
        ([DrawnShape(1, "circle", ((LON, LAT),), radius_m=0.0)], "needs a centre and a radius"),
        (
            [DrawnShape(1, "polygon", ((LON, 95.0), (LON, 94.0), (LON + 0.1, 94.5)))],
            "coordinates are not valid",
        ),
        ([DrawnShape(1, "hexagon", ((LON, LAT),))], "unknown kind"),
        (  # a bow tie: the outline crosses itself
            [
                DrawnShape(
                    1,
                    "polygon",
                    (
                        (LON, LAT),
                        (LON + 0.001, LAT + 0.001),
                        (LON + 0.001, LAT),
                        (LON, LAT + 0.001),
                    ),
                )
            ],
            "crosses itself",
        ),
    ],
)
def test_shapes_that_cannot_make_an_area_say_what_to_change(shapes: list, message: str) -> None:  # type: ignore[type-arg]
    with pytest.raises(ShapeError, match=message):
        build_area(shapes)


def test_the_result_is_something_the_planner_accepts() -> None:
    from shapely.geometry import mapping

    from avispria.core.geometry import load_aoi

    result = build_area([rect(1, 200, 200), rect(2, 50, 50, role=Role.LEAVE_OUT)])
    again = load_aoi(mapping(result.pieces[0].polygon))
    assert isinstance(again, Polygon) and len(again.interiors) == 1


def test_a_sensible_first_role_for_each_new_shape() -> None:
    big = rect(1, 200, 200)
    assert suggest_role(big, []) == Role.INSIDE  # the first area is mapped
    assert (
        suggest_role(rect(2, 50, 50), [big]) == Role.LEAVE_OUT
    )  # drawn inside it: a part to leave out
    assert (
        suggest_role(rect(3, 50, 50, dx=500), [big]) == Role.INSIDE
    )  # somewhere else: another area
    assert (
        suggest_role(rect(4, 300, 300), [big]) == Role.INSIDE
    )  # bigger, so it does not fit inside
    assert suggest_role(line(5, 100.0), [big]) == Role.CORRIDOR
    assert suggest_role(rect(6, 50, 50), [rect(7, 100, 100, role=Role.LEAVE_OUT)]) == Role.INSIDE


def test_the_size_shown_beside_a_shape() -> None:
    value, unit = shape_size(rect(1, 100, 60))
    assert unit == "m2" and value == pytest.approx(6_000, rel=0.01)
    value, unit = shape_size(line(2, 250.0))
    assert unit == "m" and value == pytest.approx(250, rel=0.01)
    assert DEFAULT_WIDTH_M == 30.0


# ------------------------------------------------------------------------------ editing a shape
from avispria.core.shapes import (  # noqa: E402
    corner_points,
    delete_corner,
    insert_corner,
    move_corner,
    with_radius,
)


def test_moving_a_corner_changes_only_that_corner_and_the_area() -> None:
    square = rect(1, 100, 100)
    corner = square.points[2]
    moved = move_corner(square, 2, corner[0] + 0.0005, corner[1])  # about 35 m east
    assert [p for i, p in enumerate(moved.points) if i != 2] == [
        p for i, p in enumerate(square.points) if i != 2
    ]
    assert moved.points[2][0] == pytest.approx(corner[0] + 0.0005)
    assert total(build_area([moved])) > total(build_area([square]))
    assert (moved.id, moved.role, moved.width_m) == (square.id, square.role, square.width_m)


def test_a_rectangle_whose_corner_moves_becomes_a_polygon_so_its_roles_still_apply() -> None:
    moved = move_corner(rect(1, 100, 100, role=Role.LEAVE_OUT), 0, LON - 0.001, LAT - 0.001)
    assert moved.kind == "polygon" and moved.role == Role.LEAVE_OUT and len(moved.points) == 4


def test_a_circle_moves_by_its_centre_and_keeps_its_radius() -> None:
    moved = move_corner(circle(1, 40), 0, LON + 0.001, LAT)
    assert moved.kind == "circle" and moved.radius_m == 40 and moved.points == ((LON + 0.001, LAT),)
    assert corner_points(moved) == moved.points


def test_a_corner_dragged_to_make_the_outline_cross_itself_is_refused() -> None:
    p0, p1, p2, _ = rect(1, 100, 100).points
    # past the side p1-p2, level with its middle: the side p3-p0 now cuts across it (a bow tie)
    far = (
        p1[0] + (p1[0] - p0[0]) + (p2[0] - p1[0]) / 2,
        p1[1] + (p1[1] - p0[1]) + (p2[1] - p1[1]) / 2,
    )
    with pytest.raises(ShapeError, match="crosses itself"):
        move_corner(rect(1, 100, 100), 0, far[0], far[1])


def test_there_is_no_corner_that_is_not_there() -> None:
    with pytest.raises(ShapeError, match="no corner 9"):
        move_corner(rect(1, 100, 100), 8, LON, LAT)
    with pytest.raises(ShapeError, match="no corner 9"):
        delete_corner(rect(1, 100, 100), 8)


def test_a_new_corner_goes_in_the_middle_of_the_longest_side_and_changes_nothing_else() -> None:
    wide = rect(1, 200, 50)  # the long sides run east to west
    grown, index = insert_corner(wide)
    assert len(grown.points) == 5 and grown.kind == "polygon" and index in (1, 2, 3, 4)
    assert total(build_area([grown])) == pytest.approx(
        total(build_area([wide])), rel=0.001
    )  # same outline
    new_lon, new_lat = grown.points[index]
    before, after = grown.points[index - 1], grown.points[(index + 1) % 5]
    assert new_lon == pytest.approx((before[0] + after[0]) / 2, abs=1e-7)
    assert new_lat == pytest.approx((before[1] + after[1]) / 2, abs=1e-7)


def test_a_new_vertex_on_a_line_goes_on_its_longest_leg() -> None:
    bent = DrawnShape(
        1, "line", ((LON, LAT), (LON + 0.0002, LAT), (LON + 0.0010, LAT)), role=Role.CORRIDOR
    )
    grown, index = insert_corner(bent)
    assert (
        index == 2
        and len(grown.points) == 4
        and grown.points[2][0] == pytest.approx(LON + 0.0006, abs=1e-6)
    )


def test_a_circle_has_no_corner_to_add_or_remove() -> None:
    with pytest.raises(ShapeError, match="no corners to add"):
        insert_corner(circle(1, 40))
    with pytest.raises(ShapeError, match="no corners to remove"):
        delete_corner(circle(1, 40), 0)


def test_an_area_keeps_three_corners_and_a_line_two() -> None:
    four = rect(1, 100, 100)
    three = delete_corner(four, 1)
    assert len(three.points) == 3 and three.kind == "polygon"
    with pytest.raises(ShapeError, match="at least 3 corners"):
        delete_corner(three, 0)
    with pytest.raises(ShapeError, match="at least 2 corners"):
        delete_corner(line(2, 100.0), 0)


def test_a_circles_radius_can_change_but_not_to_nothing() -> None:
    assert with_radius(circle(1, 40), 55).radius_m == 55
    for bad in (0.0, -5.0, float("nan")):
        with pytest.raises(ShapeError, match="needs a centre and a radius"):
            with_radius(circle(1, 40), bad)
    with pytest.raises(ShapeError, match="Only a circle"):
        with_radius(rect(1, 10, 10), 5)
