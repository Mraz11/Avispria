# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Capture quality assessment from photo metadata alone (no pixels needed).

Footprints assume nadir photos over flat ground at the takeoff level, so GSD and
overlap are estimates; terrain-aware footprints come with DEM support later.
"""

from __future__ import annotations

import itertools
import math
import statistics
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np
import shapely
from shapely.geometry import MultiPoint, Polygon

from avispria.core.camera import CameraProfile, gsd_m
from avispria.core.geometry import LocalFrame, utm_crs_for
from avispria.core.photo import PhotoRecord
from avispria.core.safety import Issue

MAX_GRID_SIDE = 160  # sample points per side for the multiplicity map


@dataclass(frozen=True)
class QaThresholds:
    nadir_tolerance_deg: float = 3.0
    max_blur_px: float = 1.0
    max_altitude_spread: float = 0.05  # (max - min) / median
    gap_factor: float = 3.0  # interval this many times the median = likely missed photos
    min_neighbour_overlap: float = 0.6
    min_views: int = 3
    good_views: int = 5


@dataclass(frozen=True)
class PhotoQa:
    name: str
    x: float
    y: float
    gsd_m: float
    blur_px: float | None
    overlap_prev: float | None
    best_overlap: float | None
    best_neighbour: str | None


@dataclass(frozen=True)
class CaptureReport:
    photos: tuple[PhotoQa, ...]
    issues: list[Issue]
    stats: dict[str, float]


@dataclass(frozen=True)
class _Footprint:
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


def _names(items: Sequence[str], limit: int = 5) -> str:
    shown = ", ".join(items[:limit])
    return shown + (f" and {len(items) - limit} more" if len(items) > limit else "")


def _height(r: PhotoRecord, agl: Mapping[str, float]) -> float:
    """Height above the surface if known (terrain-aware), else above the takeoff point."""
    assert r.relative_altitude_m is not None
    return agl.get(r.name, r.relative_altitude_m)


def _footprints(
    records: Sequence[PhotoRecord],
    camera_for: Callable[[PhotoRecord], CameraProfile],
    agl: Mapping[str, float],
) -> list[_Footprint]:
    lon0 = statistics.fmean(r.lon for r in records if r.lon is not None)
    lat0 = statistics.fmean(r.lat for r in records if r.lat is not None)
    frame = LocalFrame(utm_crs_for(lon0, lat0))
    out = []
    for r in records:
        assert r.lon is not None and r.lat is not None and r.relative_altitude_m is not None
        cam = camera_for(r)
        g = gsd_m(cam, _height(r, agl))
        xs, ys = frame.to_local([r.lon], [r.lat])
        yaw = math.radians(r.gimbal_yaw_deg or 0.0)
        out.append(
            _Footprint(
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


def _multiplicity(fps: Sequence[_Footprint]) -> np.ndarray:
    hull = MultiPoint([(f.x, f.y) for f in fps]).convex_hull
    if not isinstance(hull, Polygon) or hull.area < 1.0:
        hull = hull.buffer(min(min(f.half_w, f.half_h) for f in fps) / 2)
    minx, miny, maxx, maxy = hull.bounds
    step = max(maxx - minx, maxy - miny) / MAX_GRID_SIDE
    gx, gy = np.meshgrid(np.arange(minx, maxx + step, step), np.arange(miny, maxy + step, step))
    inside = shapely.contains_xy(hull, gx, gy)
    px, py = gx[inside], gy[inside]
    counts = np.zeros(px.shape, dtype=int)
    for f in fps:
        counts += f.covers(px, py)
    return counts


def analyse_capture(
    records: Sequence[PhotoRecord],
    camera_for: Callable[[PhotoRecord], CameraProfile],
    thresholds: QaThresholds | None = None,
    agl_m: Mapping[str, float] | None = None,
) -> CaptureReport:
    """Assess overlap, coverage, blur, gimbal, altitude and timing of a photo set.

    ``agl_m`` maps photo names to their height above the surface beneath them (see
    ``core.ground``). Photos without an entry use their height above takeoff, which
    is only right over flat ground at the takeoff level.
    """
    thr = thresholds or QaThresholds()
    agl = agl_m or {}
    issues: list[Issue] = []

    def warn(code: str, message: str, level: Literal["error", "warning"] = "warning") -> None:
        issues.append(Issue(level, code, message))

    missing = [r.name for r in records if None in (r.lat, r.lon, r.relative_altitude_m)]
    if missing:
        warn("QA007", f"missing position or altitude metadata: {_names(missing)}")
    located = [r for r in records if r.name not in missing and (r.relative_altitude_m or 0) > 0]
    oblique = [
        r.name
        for r in located
        if r.gimbal_pitch_deg is not None
        and abs(r.gimbal_pitch_deg + 90.0) > thr.nadir_tolerance_deg
    ]
    if oblique:
        warn("QA001", f"gimbal not pointing straight down (excluded): {_names(oblique)}")
    used = [r for r in located if r.name not in oblique]
    stats: dict[str, float] = {"photos_total": len(records), "photos_used": len(used)}
    if len(used) < thr.min_views:
        warn(
            "QA009",
            f"only {len(used)} usable nadir photo(s); at least {thr.min_views} needed",
            "error",
        )
    if not used:
        return CaptureReport((), issues, stats)

    fps = _footprints(used, camera_for, agl)
    polys = [f.polygon() for f in fps]
    rows: list[PhotoQa] = []
    for i, f in enumerate(fps):
        area = polys[i].area
        prev = polys[i].intersection(polys[i - 1]).area / area if i else None
        best, best_name = None, None
        for j, other in enumerate(polys):
            if j != i:
                share = polys[i].intersection(other).area / area
                if best is None or share > best:
                    best, best_name = share, fps[j].record.name
        r = f.record
        blur = (
            None
            if r.speed_ms is None or r.exposure_s is None
            else r.speed_ms * r.exposure_s / f.gsd
        )
        rows.append(PhotoQa(r.name, f.x, f.y, f.gsd, blur, prev, best, best_name))

    blurred = [p.name for p in rows if p.blur_px is not None and p.blur_px > thr.max_blur_px]
    if blurred:
        warn("QA002", f"motion blur over {thr.max_blur_px:g} px likely: {_names(blurred)}")
    alts = [_height(r, agl) for r in used]
    alt_med = statistics.median(alts)
    if (max(alts) - min(alts)) / alt_med > thr.max_altitude_spread:
        what = "height above the surface" if agl else "altitude"
        warn("QA003", f"{what} varies {min(alts):.1f}-{max(alts):.1f} m: mixed resolution")
    times = [r.time for r in used if r.time is not None]
    if len(times) >= 3:
        gaps = [(b - a).total_seconds() for a, b in itertools.pairwise(times)]
        med = statistics.median(gaps)
        stats |= {
            "interval_s_median": med,
            "interval_s_min": min(gaps),
            "interval_s_max": max(gaps),
        }
        if med > 0 and max(gaps) > thr.gap_factor * med:
            warn(
                "QA005",
                f"a {max(gaps):.0f} s gap between photos (median {med:.1f} s): missed photos?",
            )
    weak = [
        p.name
        for p in rows
        if p.best_overlap is not None and p.best_overlap < thr.min_neighbour_overlap
    ]
    if weak:
        warn(
            "QA010",
            f"overlap with nearest photo below {thr.min_neighbour_overlap:.0%}: {_names(weak)}",
        )

    views = _multiplicity(fps)
    pct3 = 100.0 * float(np.mean(views >= thr.min_views)) if views.size else 0.0
    pct5 = 100.0 * float(np.mean(views >= thr.good_views)) if views.size else 0.0
    if views.size and pct5 < 90.0:
        warn(
            "QA006",
            f"only {pct5:.0f}% of the area is seen by {thr.good_views}+ photos "
            f"({pct3:.0f}% by {thr.min_views}+); reconstruction needs more overlap",
        )
    overlaps = [p.overlap_prev for p in rows if p.overlap_prev is not None]
    stats |= {
        "gsd_cm_median": round(statistics.median(p.gsd_m for p in rows) * 100, 3),
        "altitude_m_median": alt_med,
        "terrain_aware": 1.0 if any(r.name in agl for r in used) else 0.0,
        "terrain_photos": float(sum(r.name in agl for r in used)),
        "overlap_prev_median": statistics.median(overlaps) if overlaps else float("nan"),
        "min_views": thr.min_views,
        "good_views": thr.good_views,
        "area_pct_min_views": round(pct3, 1),
        "area_pct_good_views": round(pct5, 1),
        "views_mean": float(np.mean(views)) if views.size else 0.0,
    }
    return CaptureReport(tuple(rows), issues, stats)
