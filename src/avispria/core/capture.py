# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Capture quality assessment from photo metadata alone (no pixels needed).

Footprints assume nadir photos over flat ground at the takeoff level, so GSD and
overlap are estimates; terrain-aware footprints come with DEM support later.
"""

from __future__ import annotations

import itertools
import statistics
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np
import shapely
from shapely.geometry import Polygon

from avispria.core.camera import CameraProfile
from avispria.core.footprints import (
    footprints_for,
    height_above,
    local_frame,
    view_counts,
)
from avispria.core.photo import PhotoRecord
from avispria.core.safety import Issue


@dataclass(frozen=True)
class QaThresholds:
    nadir_tolerance_deg: float = 3.0
    max_blur_px: float = 1.0
    max_altitude_spread: float = 0.05  # (max - min) / median
    gap_factor: float = 3.0  # interval this many times the median = likely missed photos
    min_neighbour_overlap: float = 0.6
    min_side_overlap: float = 0.5  # overlap with the neighbouring flight line
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
    front_overlap: float | None = None  # with the neighbour ahead or behind (along the heading)
    side_overlap: float | None = None  # with the neighbour on the next flight line


@dataclass(frozen=True)
class CaptureReport:
    photos: tuple[PhotoQa, ...]
    issues: list[Issue]
    stats: dict[str, float]


def _names(items: Sequence[str], limit: int = 5) -> str:
    shown = ", ".join(items[:limit])
    return shown + (f" and {len(items) - limit} more" if len(items) > limit else "")


def analyse_capture(
    records: Sequence[PhotoRecord],
    camera_for: Callable[[PhotoRecord], CameraProfile],
    thresholds: QaThresholds | None = None,
    agl_m: Mapping[str, float] | None = None,
    region: Polygon | None = None,
) -> CaptureReport:
    """Assess overlap, coverage, blur, gimbal, altitude and timing of a photo set.

    ``agl_m`` maps photo names to their height above the surface beneath them (see
    ``core.ground``). Photos without an entry use their height above takeoff, which
    is only right over flat ground at the takeoff level. ``region`` (a longitude/latitude
    polygon, e.g. the survey area) is the area over which view coverage is measured; by
    default it is the hull of the photo positions.
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

    frame = local_frame(used)
    fps = footprints_for(used, camera_for, agl, frame)
    polys = [f.polygon() for f in fps]
    tree = shapely.STRtree(polys)
    rows: list[PhotoQa] = []
    for i, f in enumerate(fps):
        area = polys[i].area
        prev = polys[i].intersection(polys[i - 1]).area / area if i else None
        best: float | None = None
        best_name: str | None = None
        front: float | None = None
        side: float | None = None
        # only photos whose footprints touch this one can overlap it; ascending order keeps
        # the first of equally good neighbours, as a plain scan would
        for j in sorted(int(k) for k in tree.query(polys[i], predicate="intersects")):
            if j == i:
                continue
            share = polys[i].intersection(polys[j]).area / area
            if best is None or share > best:
                best, best_name = share, fps[j].record.name
            dx, dy = fps[j].x - f.x, fps[j].y - f.y
            along = dx * f.up[0] + dy * f.up[1]
            across = dx * f.right[0] + dy * f.right[1]
            if abs(across) > abs(along):
                side = share if side is None or share > side else side
            else:
                front = share if front is None or share > front else front
        if best is None and len(fps) > 1:  # nobody overlaps this photo at all
            best = front = side = 0.0
        r = f.record
        blur = (
            None
            if r.speed_ms is None or r.exposure_s is None
            else r.speed_ms * r.exposure_s / f.gsd
        )
        rows.append(PhotoQa(r.name, f.x, f.y, f.gsd, blur, prev, best, best_name, front, side))

    blurred = [p.name for p in rows if p.blur_px is not None and p.blur_px > thr.max_blur_px]
    if blurred:
        warn("QA002", f"motion blur over {thr.max_blur_px:g} px likely: {_names(blurred)}")
    alts = [height_above(r, agl) for r in used]
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

    weak_side = [
        p.name for p in rows if p.side_overlap is not None and p.side_overlap < thr.min_side_overlap
    ]
    if weak_side:
        warn(
            "QA014",
            f"overlap with the neighbouring flight line below {thr.min_side_overlap:.0%}: "
            f"{_names(weak_side)}",
        )

    views = view_counts(fps, None if region is None else frame.polygon_to_local(region))
    pct3 = 100.0 * float(np.mean(views >= thr.min_views)) if views.size else 0.0
    pct5 = 100.0 * float(np.mean(views >= thr.good_views)) if views.size else 0.0
    if views.size and pct5 < 90.0:
        warn(
            "QA006",
            f"only {pct5:.0f}% of the area is seen by {thr.good_views}+ photos "
            f"({pct3:.0f}% by {thr.min_views}+); reconstruction needs more overlap",
        )
    overlaps = [p.overlap_prev for p in rows if p.overlap_prev is not None]
    for key, values in (
        ("front", [p.front_overlap for p in rows if p.front_overlap is not None]),
        ("side", [p.side_overlap for p in rows if p.side_overlap is not None]),
    ):
        if values:
            stats[f"{key}_overlap_median"] = float(statistics.median(values))
            stats[f"{key}_overlap_p10"] = float(np.percentile(values, 10))
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
