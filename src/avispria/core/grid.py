# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Survey line generation in a local metric frame (x = east, y = north)."""

from __future__ import annotations

import itertools
import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import shapely
from numpy.typing import NDArray
from shapely import affinity
from shapely.geometry import LineString, Polygon

Point2 = tuple[float, float]


@dataclass(frozen=True)
class Strip:
    """One straight survey line, flown from (x0, y0) to (x1, y1)."""

    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def length(self) -> float:
        return math.hypot(self.x1 - self.x0, self.y1 - self.y0)


def _pieces(geom: shapely.Geometry) -> list[LineString]:
    if isinstance(geom, LineString):
        return [geom] if geom.length > 1e-6 else []
    parts = getattr(geom, "geoms", [])
    return [g for g in parts if isinstance(g, LineString) and g.length > 1e-6]


def lawnmower(
    area: Polygon, heading_deg: float, line_spacing_m: float, overrun_m: float
) -> list[Strip]:
    """Parallel lines along ``heading_deg`` (compass degrees), boustrophedon order.

    Lines are centred so the outermost line is at most half a spacing from the
    area's edge. Each strip is extended by ``overrun_m`` at both ends so that turns
    happen outside the photographed area.
    """
    if not (math.isfinite(line_spacing_m) and line_spacing_m > 0):
        raise ValueError("line_spacing_m must be positive")
    if not (math.isfinite(overrun_m) and overrun_m >= 0):
        raise ValueError("overrun_m must be >= 0")
    origin = area.centroid
    rot = heading_deg - 90.0  # rotate so the flight direction becomes +x
    rotated = affinity.rotate(area, rot, origin=origin)
    minx, miny, maxx, maxy = rotated.bounds
    height = maxy - miny
    n_lines = max(1, math.ceil(height / line_spacing_m))
    first = miny + (height - (n_lines - 1) * line_spacing_m) / 2.0

    strips: list[Strip] = []
    flip = False
    for k in range(n_lines):
        y = first + k * line_spacing_m
        sweep = LineString([(minx - 1.0, y), (maxx + 1.0, y)])
        pieces = sorted(_pieces(sweep.intersection(rotated)), key=lambda g: g.bounds[0])
        if flip:
            pieces = pieces[::-1]
        for piece in pieces:
            x_lo, _, x_hi, _ = piece.bounds
            a, b = (x_lo - overrun_m, y), (x_hi + overrun_m, y)
            line = LineString([b, a] if flip else [a, b])
            back = affinity.rotate(line, -rot, origin=origin)
            (x0, y0), (x1, y1) = back.coords
            strips.append(Strip(x0, y0, x1, y1))
        if pieces:
            flip = not flip
    return strips


def auto_heading(area: Polygon) -> float:
    """Heading (0-180 deg) along the longer side of the minimum-area bounding rectangle.

    Uses rotating calipers over the convex hull in plain NumPy so the result is
    identical on every platform (no library-internal division by zero).
    """
    hull = area.convex_hull
    if not isinstance(hull, Polygon):  # degenerate (line-like) area
        raise ValueError("area has no extent to orient lines along")
    pts = np.asarray(hull.exterior.coords, dtype=float)[:-1]
    best: tuple[float, float, float, float, float] | None = None
    for (xa, ya), (xb, yb) in zip(pts, np.roll(pts, -1, axis=0), strict=True):
        length = math.hypot(xb - xa, yb - ya)
        if length < 1e-9:
            continue
        ux, uy = (xb - xa) / length, (yb - ya) / length
        along = pts @ np.array([ux, uy])
        across = pts @ np.array([-uy, ux])
        width = float(along.max() - along.min())
        height = float(across.max() - across.min())
        if best is None or width * height < best[0] - 1e-9:
            best = (width * height, ux, uy, width, height)
    if best is None:
        raise ValueError("area has no extent to orient lines along")
    _, ux, uy, width, height = best
    if height > width:  # follow the longer side
        ux, uy = -uy, ux
    heading = math.degrees(math.atan2(ux, uy)) % 180.0
    return 0.0 if math.isclose(heading, 180.0, abs_tol=1e-9) else heading


def flight_path(strips: Sequence[Strip]) -> list[Point2]:
    """Ordered vertices: start and end of every strip in flight order."""
    path: list[Point2] = []
    for s in strips:
        path.extend([(s.x0, s.y0), (s.x1, s.y1)])
    return path


def densify_path(
    path: Sequence[Point2], step_m: float
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64], list[int]]:
    """Sample a polyline at <= ``step_m`` spacing, always keeping its vertices.

    Returns sample x, y, cumulative distance and the sample index of each vertex.
    """
    if step_m <= 0:
        raise ValueError("step_m must be positive")
    if not path:
        raise ValueError("path is empty")
    xs: list[float] = [path[0][0]]
    ys: list[float] = [path[0][1]]
    vertex_idx = [0]
    for (xa, ya), (xb, yb) in itertools.pairwise(path):
        seg = math.hypot(xb - xa, yb - ya)
        if seg < 1e-9:
            vertex_idx.append(len(xs) - 1)
            continue
        n = max(1, math.ceil(seg / step_m))
        for i in range(1, n + 1):
            t = i / n
            xs.append(xa + t * (xb - xa))
            ys.append(ya + t * (yb - ya))
        vertex_idx.append(len(xs) - 1)
    x_arr, y_arr = np.asarray(xs), np.asarray(ys)
    d = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(x_arr), np.diff(y_arr)))])
    return x_arr, y_arr, d, vertex_idx
