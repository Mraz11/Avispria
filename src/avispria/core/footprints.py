# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Ground footprints of nadir photos, and how many photos see each point of an area."""

from __future__ import annotations

import math
import statistics
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

import numpy as np
import shapely
from shapely.geometry import MultiPoint, Polygon

from avispria.core.camera import CameraProfile, gsd_m
from avispria.core.geometry import LocalFrame, utm_crs_for
from avispria.core.photo import PhotoRecord

MAX_GRID_SIDE = 160  # sample points per side for the multiplicity map


@dataclass(frozen=True)
class Footprint:
    record: PhotoRecord
    x: float
    y: float
    gsd: float
    half_w: float
    half_h: float
    right: tuple[float, float]
    up: tuple[float, float]

    def polygon(self) -> Polygon:
        (rx, ry), (ux, uy) = self.right, self.up
        corners = [
            (
                self.x + sx * self.half_w * rx + sy * self.half_h * ux,
                self.y + sx * self.half_w * ry + sy * self.half_h * uy,
            )
            for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))
        ]
        return Polygon(corners)

    def covers(self, px: np.ndarray, py: np.ndarray) -> np.ndarray:
        dx, dy = px - self.x, py - self.y
        u = dx * self.right[0] + dy * self.right[1]
        v = dx * self.up[0] + dy * self.up[1]
        return (np.abs(u) <= self.half_w) & (np.abs(v) <= self.half_h)


def height_above(r: PhotoRecord, agl: Mapping[str, float]) -> float:
    """Height above the surface if known (terrain-aware), else above the takeoff point."""
    assert r.relative_altitude_m is not None
    return agl.get(r.name, r.relative_altitude_m)


def local_frame(records: Sequence[PhotoRecord]) -> LocalFrame:
    lon0 = statistics.fmean(r.lon for r in records if r.lon is not None)
    lat0 = statistics.fmean(r.lat for r in records if r.lat is not None)
    return LocalFrame(utm_crs_for(lon0, lat0))


def footprints_for(
    records: Sequence[PhotoRecord],
    camera_for: Callable[[PhotoRecord], CameraProfile],
    agl: Mapping[str, float],
    frame: LocalFrame,
) -> list[Footprint]:
    out = []
    for r in records:
        assert r.lon is not None and r.lat is not None and r.relative_altitude_m is not None
        cam = camera_for(r)
        g = gsd_m(cam, height_above(r, agl))
        xs, ys = frame.to_local([r.lon], [r.lat])
        yaw = math.radians(r.gimbal_yaw_deg or 0.0)
        out.append(
            Footprint(
                r,
                float(xs[0]),
                float(ys[0]),
                g,
                g * cam.image_width_px / 2,
                g * cam.image_height_px / 2,
                (math.cos(yaw), -math.sin(yaw)),
                (math.sin(yaw), math.cos(yaw)),
            )
        )
    return out


def view_counts(fps: Sequence[Footprint], region: Polygon | None = None) -> np.ndarray:
    """How many photos see each point of ``region`` (default: hull of the photo centres)."""
    if region is not None:
        hull: Polygon = region
    else:
        centres = MultiPoint([(f.x, f.y) for f in fps]).convex_hull
        if isinstance(centres, Polygon) and centres.area >= 1.0:
            hull = centres
        else:
            hull = centres.buffer(min(min(f.half_w, f.half_h) for f in fps) / 2)
    minx, miny, maxx, maxy = hull.bounds
    step = max(maxx - minx, maxy - miny) / MAX_GRID_SIDE
    gx, gy = np.meshgrid(np.arange(minx, maxx + step, step), np.arange(miny, maxy + step, step))
    inside = shapely.contains_xy(hull, gx, gy)
    px, py = gx[inside], gy[inside]
    counts = np.zeros(px.shape, dtype=int)
    for f in fps:
        counts += f.covers(px, py)
    return counts
