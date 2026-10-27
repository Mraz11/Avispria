# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import itertools
import math

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from shapely import affinity
from shapely.geometry import LineString, Point, Polygon, box

from avispria.core.grid import auto_heading, densify_path, flight_path, lawnmower


def _unit(heading_deg: float) -> tuple[float, float]:
    r = math.radians(heading_deg)
    return math.sin(r), math.cos(r)


def test_rectangle_north_heading_lines_are_vertical() -> None:
    strips = lawnmower(box(0, 0, 100, 200), heading_deg=0.0, line_spacing_m=20.0, overrun_m=5.0)
    assert len(strips) == 5
    for s in strips:
        assert s.x0 == pytest.approx(s.x1)
        assert abs(s.y1 - s.y0) == pytest.approx(210.0)
    xs = sorted(s.x0 for s in strips)
    assert np.allclose(np.diff(xs), 20.0)


def test_boustrophedon_alternates_direction() -> None:
    strips = lawnmower(box(0, 0, 100, 200), 0.0, 20.0, 0.0)
    dirs = [math.copysign(1, s.y1 - s.y0) for s in strips]
    assert all(a != b for a, b in itertools.pairwise(dirs))


def test_rejects_bad_parameters() -> None:
    with pytest.raises(ValueError):
        lawnmower(box(0, 0, 10, 10), 0.0, 0.0, 0.0)
    with pytest.raises(ValueError):
        lawnmower(box(0, 0, 10, 10), 0.0, 5.0, -1.0)


def test_auto_heading_follows_long_side() -> None:
    long_east_west = box(0, 0, 500, 50)
    assert auto_heading(long_east_west) == pytest.approx(90.0)
    tilted = affinity.rotate(long_east_west, 30, origin=(0, 0))
    assert auto_heading(tilted) == pytest.approx(60.0, abs=1e-6)


@st.composite
def rotated_rectangles(draw: st.DrawFn) -> Polygon:
    w = draw(st.floats(60, 600))
    h = draw(st.floats(60, 600))
    angle = draw(st.floats(0, 180))
    return affinity.rotate(box(0, 0, w, h), angle, origin=(0, 0))


@settings(max_examples=60, deadline=None)
@given(rotated_rectangles(), st.floats(0, 179.9), st.floats(5, 40))
def test_strips_cover_area_and_stay_inside(area: Polygon, heading: float, spacing: float) -> None:
    strips = lawnmower(area, heading, spacing, overrun_m=0.0)
    assert strips, "an area larger than the spacing must produce strips"
    ux, uy = _unit(heading)
    lines = []
    for s in strips:
        line = LineString([(s.x0, s.y0), (s.x1, s.y1)])
        assert area.buffer(1e-6).covers(line)
        if line.length > 1e-9:
            dx, dy = (s.x1 - s.x0) / line.length, (s.y1 - s.y0) / line.length
            assert abs(dx * ux + dy * uy) == pytest.approx(1.0, abs=1e-6)
        lines.append(line)
    # every point of the area lies within half a spacing (+ tolerance) of some sweep line
    minx, miny, maxx, maxy = area.bounds
    rng = np.random.default_rng(0)
    for _ in range(50):
        p = Point(rng.uniform(minx, maxx), rng.uniform(miny, maxy))
        if area.contains(p):
            nearest = min(line.distance(p) for line in lines)
            assert nearest <= spacing / 2 + 1e-6 or _near_end(area, p, spacing)


def _near_end(area: Polygon, p: Point, spacing: float) -> bool:
    # points close to the boundary may sit beyond the clipped end of a line
    return area.exterior.distance(p) <= spacing


def test_flight_path_and_densify() -> None:
    strips = lawnmower(box(0, 0, 40, 100), 0.0, 20.0, 0.0)
    path = flight_path(strips)
    assert len(path) == 2 * len(strips)
    xs, ys, d, vertex_idx = densify_path(path, step_m=5.0)
    assert len(vertex_idx) == len(path)
    assert d[0] == 0.0 and np.all(np.diff(d) > 0)
    assert np.all(np.diff(d) <= 5.0 + 1e-9)
    for i, (x, y) in zip(vertex_idx, path, strict=True):
        assert (xs[i], ys[i]) == pytest.approx((x, y))
