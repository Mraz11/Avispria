# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Turning survey lines into a route: photo points along each line and the height profile."""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import NDArray

from avispria.core.geometry import LocalFrame
from avispria.core.grid import Strip, densify_path
from avispria.core.mission import PhotoMode
from avispria.core.plan_model import PlanRequest
from avispria.core.profile import HeightProfile, flat_profile, terrain_profile

FloatArray = NDArray[np.float64]


def strip_vertices(
    strip: Strip, photo_m: float, overrun: float, mode: PhotoMode
) -> list[tuple[float, float, bool]]:
    """Vertices along one strip: ends (no photo) and evenly spaced photo points."""
    if mode is PhotoMode.INTERVAL:
        return [(strip.x0, strip.y0, False), (strip.x1, strip.y1, False)]
    length = strip.length
    ux, uy = (strip.x1 - strip.x0) / length, (strip.y1 - strip.y0) / length
    inner = length - 2.0 * overrun
    if inner <= 1e-6:
        positions = [length / 2.0]
    else:
        n = max(1, math.ceil(inner / photo_m - 1e-9))
        positions = [overrun + inner * i / n for i in range(n + 1)]
    out: list[tuple[float, float, bool]] = []
    if overrun > 1e-6:
        out.append((strip.x0, strip.y0, False))
    out += [(strip.x0 + ux * s, strip.y0 + uy * s, True) for s in positions]
    if overrun > 1e-6:
        out.append((strip.x1, strip.y1, False))
    return out


def route_profile(
    req: PlanRequest, frame: LocalFrame, path: list[tuple[float, float]], reference_m: float
) -> tuple[FloatArray, FloatArray, list[int], HeightProfile]:
    xs, ys, d, vertex_idx = densify_path(path, req.terrain.sample_step_m)
    lons, lats = frame.to_lonlat(xs, ys)
    if req.dem is None:
        prof: HeightProfile = flat_profile(len(xs), vertex_idx, reference_m + req.surface_height_m)
    else:
        prof = terrain_profile(
            req.dem,
            lons,
            lats,
            d,
            vertex_idx,
            reference_m,
            (req.takeoff_lon, req.takeoff_lat),
            req.takeoff_elevation_m,
            req.terrain,
            req.surface_height_m,
        )
    return lons, lats, vertex_idx, prof
