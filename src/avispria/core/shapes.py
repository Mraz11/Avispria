# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shapes drawn on a map, each with a role, become the area to survey.

A shape is a polygon, rectangle or circle (an area) or a line, and has a role:

* ``inside``: map this area;
* ``leave_out``: do not plan to cover this part of the mapped area (a lake, a building);
* ``band``: map a ring of ``width_m`` around the shape, OUTSIDE it (around a building, along a
  forest edge): "map the outside of the polygon";
* ``corridor`` (a line): map a strip ``width_m`` wide along it (a road, river, power line).

The result is one or more polygons (a polygon may have holes); the planner plans one polygon at a
time. All geometry is done in metres (a local UTM frame), never in degrees.

"Leave out" means "not planned for coverage": the aircraft may still fly over that part to turn
or to reach the next strip. A part that must NOT be overflown needs a different, later feature.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon, mapping
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from avispria.core.geometry import AoiError, LocalFrame, load_aoi, utm_crs_for

MIN_PIECE_M2 = 100.0  # something under 10 m x 10 m is not worth a flight
SIMPLIFY_M = 0.25  # drop vertices that change the outline by less than this
DEFAULT_WIDTH_M = 30.0


class ShapeError(ValueError):
    """The drawn shapes cannot be made into an area; the message says what to change."""


class Role(StrEnum):
    INSIDE = "inside"
    LEAVE_OUT = "leave_out"
    BAND = "band"
    CORRIDOR = "corridor"


AREA_KINDS = ("polygon", "rectangle", "circle")
ALLOWED_ROLES: dict[str, tuple[Role, ...]] = {
    "polygon": (Role.INSIDE, Role.LEAVE_OUT, Role.BAND),
    "rectangle": (Role.INSIDE, Role.LEAVE_OUT, Role.BAND),
    "circle": (Role.INSIDE, Role.LEAVE_OUT, Role.BAND),
    "line": (Role.CORRIDOR,),
}


@dataclass(frozen=True)
class DrawnShape:
    """One shape. ``points`` are (lon, lat): the corners of an area, the vertices of a line, or the
    centre of a circle (whose ``radius_m`` is in metres)."""

    id: int
    kind: str
    points: tuple[tuple[float, float], ...]
    radius_m: float = 0.0
    role: Role = Role.INSIDE
    width_m: float = DEFAULT_WIDTH_M  # of a band or a corridor

    @property
    def label(self) -> str:
        names = {"polygon": "Polygon", "rectangle": "Rectangle", "circle": "Circle", "line": "Line"}
        return f"{names.get(self.kind, self.kind)} {self.id}"


@dataclass(frozen=True)
class AreaPiece:
    polygon: Polygon  # lon/lat; may have holes
    area_m2: float


@dataclass(frozen=True)
class AreaResult:
    pieces: tuple[AreaPiece, ...]  # largest first
    dropped_m2: float  # slivers too small to fly, left out of ``pieces``


def _frame(shapes: Sequence[DrawnShape]) -> LocalFrame:
    lons = [p[0] for s in shapes for p in s.points]
    lats = [p[1] for s in shapes for p in s.points]
    return LocalFrame(utm_crs_for(float(np.mean(lons)), float(np.mean(lats))))


def _local_points(frame: LocalFrame, shape: DrawnShape) -> list[tuple[float, float]]:
    xs, ys = frame.to_local([p[0] for p in shape.points], [p[1] for p in shape.points])
    return list(zip(xs.tolist(), ys.tolist(), strict=True))


def _check(shape: DrawnShape) -> None:
    if shape.kind not in ALLOWED_ROLES:
        raise ShapeError(f"{shape.label}: unknown kind of shape")
    if shape.role not in ALLOWED_ROLES[shape.kind]:
        raise ShapeError(f"{shape.label}: a {shape.kind} cannot be set to '{shape.role.value}'")
    if not all(
        math.isfinite(v) and -180 <= p[0] <= 180 and -90 <= p[1] <= 90
        for p in shape.points
        for v in p
    ):
        raise ShapeError(f"{shape.label}: its coordinates are not valid")
    if shape.role in (Role.BAND, Role.CORRIDOR) and not (
        math.isfinite(shape.width_m) and 0 < shape.width_m <= 2000
    ):
        raise ShapeError(f"{shape.label}: the width must be between 0 and 2000 metres")


def _geometry(frame: LocalFrame, shape: DrawnShape) -> BaseGeometry:
    """The shape itself, in metres (a line becomes the strip around it)."""
    pts = _local_points(frame, shape)
    if shape.kind == "circle":
        if len(pts) != 1 or not (math.isfinite(shape.radius_m) and shape.radius_m > 0):
            raise ShapeError(f"{shape.label}: a circle needs a centre and a radius")
        return Point(pts[0]).buffer(shape.radius_m, quad_segs=24)
    if shape.kind == "line":
        line = LineString(pts)
        if len(pts) < 2 or line.length <= 0:
            raise ShapeError(f"{shape.label}: a line needs two different points")
        return line.buffer(shape.width_m / 2.0, cap_style="flat", join_style="round")
    if len(pts) < 3:
        raise ShapeError(f"{shape.label}: an area needs at least three corners")
    poly = Polygon(pts)
    if not poly.is_valid:
        raise ShapeError(f"{shape.label} crosses itself: draw it again without crossing")
    if poly.area <= 0:
        raise ShapeError(f"{shape.label} has no area")
    return poly


def _polygons(geom: BaseGeometry) -> list[Polygon]:
    parts = getattr(geom, "geoms", [geom])
    return [p for p in parts if isinstance(p, Polygon) and not p.is_empty]


def build_area(shapes: Sequence[DrawnShape]) -> AreaResult:
    """The mapped parts minus the left-out parts. Raises ShapeError if nothing is left."""
    if not shapes:
        raise ShapeError("Draw at least one shape on the map.")
    for s in shapes:
        _check(s)
    frame = _frame(shapes)
    mapped: list[BaseGeometry] = []
    left_out: list[BaseGeometry] = []
    for s in shapes:
        geometry = _geometry(frame, s)
        if s.role == Role.INSIDE or s.role == Role.CORRIDOR:
            mapped.append(geometry)
        elif s.role == Role.LEAVE_OUT:
            left_out.append(geometry)
        else:  # a band: the ring around the shape, outside it
            mapped.append(geometry.buffer(s.width_m, join_style="round").difference(geometry))
    if not mapped:
        raise ShapeError(
            "Nothing is set to be mapped. Set a shape to 'map inside it', or draw a line or a band."
        )
    area = unary_union(mapped)
    if left_out:
        area = area.difference(unary_union(left_out))
    if area.is_empty:
        raise ShapeError("Everything you set to be mapped is cut away by the parts you left out.")
    pieces: list[AreaPiece] = []
    dropped = 0.0
    for piece in _polygons(area.simplify(SIMPLIFY_M)):
        if piece.area < MIN_PIECE_M2:
            dropped += piece.area
            continue
        pieces.append(AreaPiece(_to_lonlat(frame, piece), piece.area))
    if not pieces:
        raise ShapeError(
            f"What is left to map is too small (under {MIN_PIECE_M2:.0f} square metres)."
        )
    pieces.sort(key=lambda p: -p.area_m2)
    return AreaResult(tuple(pieces), dropped)


def _to_lonlat(frame: LocalFrame, polygon: Polygon) -> Polygon:
    def inverse(coords: np.ndarray) -> np.ndarray:
        lons, lats = frame.to_lonlat(coords[:, 0], coords[:, 1])
        return np.column_stack([lons, lats])

    result = shapely.transform(polygon, inverse)
    if not isinstance(result, Polygon):
        raise ShapeError("the area could not be converted back to coordinates")
    try:
        load_aoi(mapping(result))  # the planner's own rules: size, validity
    except AoiError as exc:
        raise ShapeError(str(exc)) from exc
    return result


def shape_size(shape: DrawnShape) -> tuple[float, str]:
    """A size to show next to the shape: (value, 'm2' for an area or 'm' for a line)."""
    frame = _frame([shape])
    if shape.kind == "line":
        return LineString(_local_points(frame, shape)).length, "m"
    return _geometry(frame, shape).area, "m2"


def suggest_role(new: DrawnShape, existing: Sequence[DrawnShape]) -> Role:
    """A sensible first role: a line is a corridor; an area drawn entirely inside something
    already being mapped is a part to leave out; any other area is mapped."""
    if new.kind == "line":
        return Role.CORRIDOR
    mapped = [s for s in existing if s.role == Role.INSIDE and s.kind in AREA_KINDS]
    if not mapped:
        return Role.INSIDE
    try:
        frame = _frame([new, *mapped])
        inside = unary_union([_geometry(frame, s) for s in mapped])
        return Role.LEAVE_OUT if inside.contains(_geometry(frame, new)) else Role.INSIDE
    except ShapeError:
        return Role.INSIDE


# ---------------------------------------------------------------------------------- editing a shape
MIN_CORNERS = {"polygon": 3, "rectangle": 3, "line": 2}


def corner_points(shape: DrawnShape) -> tuple[tuple[float, float], ...]:
    """The points a person can move: an area's corners, a line's vertices, a circle's centre."""
    return shape.points


def move_corner(shape: DrawnShape, index: int, lon: float, lat: float) -> DrawnShape:
    """Move one corner (or a circle's centre). A rectangle whose corner moves becomes a polygon."""
    if not 0 <= index < len(shape.points):
        raise ShapeError(f"{shape.label} has no corner {index + 1}")
    points = list(shape.points)
    points[index] = (lon, lat)
    kind = "polygon" if shape.kind == "rectangle" else shape.kind
    moved = DrawnShape(shape.id, kind, tuple(points), shape.radius_m, shape.role, shape.width_m)
    _check(moved)
    _geometry(_frame([moved]), moved)  # refuses an outline that crosses itself, right now
    return moved


def insert_corner(shape: DrawnShape) -> tuple[DrawnShape, int]:
    """A new corner in the middle of the longest side: the shape and the new corner's index."""
    if shape.kind == "circle":
        raise ShapeError("A circle has no corners to add; change its radius instead.")
    frame = _frame([shape])
    local = _local_points(frame, shape)
    closed = shape.kind != "line"
    count = len(local)
    edges = [(i, (i + 1) % count) for i in range(count if closed else count - 1)]
    start, end = max(
        edges,
        key=lambda e: math.hypot(local[e[1]][0] - local[e[0]][0], local[e[1]][1] - local[e[0]][1]),
    )
    mid_x = (local[start][0] + local[end][0]) / 2.0
    mid_y = (local[start][1] + local[end][1]) / 2.0
    lons, lats = frame.to_lonlat([mid_x], [mid_y])
    points = list(shape.points)
    points.insert(start + 1, (float(lons[0]), float(lats[0])))
    kind = "polygon" if shape.kind == "rectangle" else shape.kind
    grown = DrawnShape(shape.id, kind, tuple(points), shape.radius_m, shape.role, shape.width_m)
    return grown, start + 1


def delete_corner(shape: DrawnShape, index: int) -> DrawnShape:
    """Take one corner away; an area keeps at least three, a line two."""
    if shape.kind == "circle":
        raise ShapeError("A circle has no corners to remove.")
    if not 0 <= index < len(shape.points):
        raise ShapeError(f"{shape.label} has no corner {index + 1}")
    if len(shape.points) <= MIN_CORNERS[shape.kind]:
        word = "line" if shape.kind == "line" else "area"
        raise ShapeError(f"A {word} needs at least {MIN_CORNERS[shape.kind]} corners.")
    points = shape.points[:index] + shape.points[index + 1 :]
    kind = "polygon" if shape.kind == "rectangle" else shape.kind
    smaller = DrawnShape(shape.id, kind, points, shape.radius_m, shape.role, shape.width_m)
    _geometry(_frame([smaller]), smaller)
    return smaller


def with_radius(shape: DrawnShape, radius_m: float) -> DrawnShape:
    if shape.kind != "circle":
        raise ShapeError("Only a circle has a radius.")
    changed = DrawnShape(shape.id, shape.kind, shape.points, radius_m, shape.role, shape.width_m)
    _geometry(_frame([changed]), changed)  # refuses a radius that is not a positive number
    return changed
