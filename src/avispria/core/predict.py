# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Predict the capture quality of a planned mission before anyone flies it.

The photos a plan will take are placed along its route, the real height above the surface
beneath each is worked out from the elevation model, and the same analysis used for real
flights (``analyse_capture``) is run over the survey area. The numbers describe what the
plan will achieve over the real terrain, not what it was asked for.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
from shapely.geometry import Polygon

from avispria.core.camera import CameraProfile
from avispria.core.capture import QaThresholds, analyse_capture
from avispria.core.geometry import LocalFrame, utm_crs_for
from avispria.core.mission import Mission, PhotoMode
from avispria.core.photo import PhotoRecord
from avispria.core.safety import Issue
from avispria.core.terrain import Dem, FloatArray

MIN_HEIGHT_M = 2.0  # a photo this close to the surface is not assessed
NADIR_TOLERANCE_DEG = 3.0
GSD_MEDIAN_TOLERANCE = 0.15  # typical resolution within 15% of the target
GSD_P90_FACTOR = 1.3  # the coarsest tenth of the photos within 30% of the target
RELEVANT_QA = {"QA002", "QA006", "QA010", "QA014"}  # blur, coverage, front and side overlap


@dataclass(frozen=True)
class PlannedPhoto:
    lon: float
    lat: float
    height_rel_m: float  # height above the takeoff point
    course_deg: float  # direction of travel, clockwise from north


@dataclass(frozen=True)
class PlanPrediction:
    photos: int
    not_assessed: int  # photos outside the elevation model or too close to the surface
    terrain_aware: bool
    height_min_m: float  # height above the surface beneath the photo
    height_median_m: float
    height_max_m: float
    gsd_cm_median: float
    gsd_cm_p90: float  # the coarsest tenth of the photos are at least this coarse
    front_overlap_median: float | None
    front_overlap_p10: float | None
    side_overlap_median: float | None
    side_overlap_p10: float | None
    area_pct_min_views: float
    area_pct_good_views: float
    issues: list[Issue] = field(default_factory=list)


def _bearings(xs: FloatArray, ys: FloatArray) -> FloatArray:
    dx, dy = np.diff(xs), np.diff(ys)
    out = np.degrees(np.arctan2(dx, dy)) % 360.0
    still = np.hypot(dx, dy) < 1e-6  # duplicate waypoint: keep the previous direction
    for i in range(len(out)):
        if still[i]:
            out[i] = out[i - 1] if i else 0.0
    return out


def planned_photos(mission: Mission) -> list[PlannedPhoto]:
    """Where a mission takes its photos.

    Waypoint mode: at the waypoints that take a photo. Interval mode: along the whole route
    at speed x interval, including the turns, because timed shot runs from start to end.
    """
    wps = mission.waypoints
    if len(wps) < 2:
        return []
    frame = LocalFrame(utm_crs_for(wps[0].lon, wps[0].lat))
    xs, ys = frame.to_local([w.lon for w in wps], [w.lat for w in wps])
    heights = np.array([w.height_m for w in wps], dtype=float)
    bearings = _bearings(xs, ys)
    if mission.photo_mode is PhotoMode.WAYPOINT:
        last = len(wps) - 1
        return [
            PlannedPhoto(w.lon, w.lat, w.height_m, float(bearings[min(i, last - 1)]))
            for i, w in enumerate(wps)
            if w.take_photo
        ]
    if not mission.photo_interval_s or mission.photo_interval_s <= 0:
        return []
    cumulative = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(xs), np.diff(ys)))])
    step = mission.speed_ms * mission.photo_interval_s
    along = np.arange(0.0, cumulative[-1] + 1e-9, step)
    x, y, h = (np.interp(along, cumulative, v) for v in (xs, ys, heights))
    leg = np.clip(np.searchsorted(cumulative, along, side="right") - 1, 0, len(wps) - 2)
    lons, lats = frame.to_lonlat(x, y)
    return [
        PlannedPhoto(float(lo), float(la), float(hh), float(bearings[k]))
        for lo, la, hh, k in zip(lons, lats, h, leg, strict=True)
    ]


def heights_above_surface(
    photos: Sequence[PlannedPhoto],
    takeoff_elevation_m: float,
    dem: Dem,
    surface_offset_m: float = 0.0,
) -> FloatArray:
    """Height of each photo above the surface beneath it (NaN off the model).

    ``takeoff_elevation_m`` is in the model's own height reference, so only height
    differences within the model matter. ``surface_offset_m`` is the height of trees or
    buildings above the modelled ground.
    """
    lons = np.array([p.lon for p in photos], dtype=float)
    lats = np.array([p.lat for p in photos], dtype=float)
    rel = np.array([p.height_rel_m for p in photos], dtype=float)
    surface = dem.sample_lonlat(lons, lats) + surface_offset_m
    return takeoff_elevation_m + rel - surface


def _is_nadir(missions: Sequence[Mission]) -> bool:
    return all(
        abs(w.gimbal_pitch_deg + 90.0) <= NADIR_TOLERANCE_DEG for m in missions for w in m.waypoints
    )


def predict_plan(
    missions: Sequence[Mission],
    camera: CameraProfile,
    aoi: Polygon,
    *,
    dem: Dem | None,
    takeoff_elevation_m: float | None,
    surface_height_m: float = 0.0,
    shutter_s: float | None = None,
    target_gsd_cm: float | None = None,
) -> PlanPrediction | None:
    """What the planned photos will achieve over the real surface; None if it cannot say.

    It cannot say for oblique plans (the analysis is for straight-down photos) or when
    fewer than three photos can be assessed.
    """
    if not _is_nadir(missions):
        return None
    photos = [(m, p) for m in missions for p in planned_photos(m)]
    if dem is not None and takeoff_elevation_m is not None:
        raw = heights_above_surface(
            [p for _, p in photos], takeoff_elevation_m, dem, surface_height_m
        )
    else:  # flat ground at the takeoff level, plus objects of the given height
        raw = np.array([p.height_rel_m - surface_height_m for _, p in photos], dtype=float)
    keep = np.isfinite(raw) & (raw >= MIN_HEIGHT_M)
    if int(keep.sum()) < 3:
        return None
    records = [
        PhotoRecord(
            f"P{k:05d}",
            None,
            p.lat,
            p.lon,
            float(h),
            -90.0,
            p.course_deg,
            m.speed_ms,
            shutter_s,
            None,
            camera.focal_mm,
            None,
            camera.image_width_px,
            camera.image_height_px,
            None,
            None,
            None,
        )
        for k, ((m, p), h, ok) in enumerate(zip(photos, raw, keep, strict=True))
        if ok
    ]
    report = analyse_capture(records, lambda r: camera, QaThresholds(), region=aoi)
    heights = raw[keep]
    gsd = np.array([row.gsd_m for row in report.photos]) * 100.0
    s = report.stats
    median, p90 = float(np.median(gsd)), float(np.percentile(gsd, 90))
    issues = [
        Issue(i.level, i.code, "predicted: " + i.message)
        for i in report.issues
        if i.code in RELEVANT_QA
    ]
    dropped = len(photos) - len(records)
    if dropped:
        issues.append(
            Issue(
                "warning",
                "PL003",
                f"{dropped} of {len(photos)} planned photos are off the elevation model or too "
                "close to the surface, so they are not included in this prediction",
            )
        )
    if target_gsd_cm and abs(median / target_gsd_cm - 1.0) > GSD_MEDIAN_TOLERANCE:
        issues.append(
            Issue(
                "warning",
                "PL001",
                f"typical resolution will be {median:.2f} cm/px, not the {target_gsd_cm:.2f} "
                "requested; reaching it would need flying lower than the clearance allows",
            )
        )
    if target_gsd_cm and p90 > GSD_P90_FACTOR * target_gsd_cm:
        issues.append(
            Issue(
                "warning",
                "PL002",
                f"the coarsest tenth of the photos will be {p90:.2f} cm/px or worse "
                f"(requested {target_gsd_cm:.2f}): the terrain relief and the clearance "
                "margins are large for this height",
            )
        )
    return PlanPrediction(
        photos=len(records),
        not_assessed=dropped,
        terrain_aware=dem is not None,
        height_min_m=float(heights.min()),
        height_median_m=float(np.median(heights)),
        height_max_m=float(heights.max()),
        gsd_cm_median=median,
        gsd_cm_p90=p90,
        front_overlap_median=s.get("front_overlap_median"),
        front_overlap_p10=s.get("front_overlap_p10"),
        side_overlap_median=s.get("side_overlap_median"),
        side_overlap_p10=s.get("side_overlap_p10"),
        area_pct_min_views=s["area_pct_min_views"],
        area_pct_good_views=s["area_pct_good_views"],
        issues=issues,
    )


__all__ = [
    "PlanPrediction",
    "PlannedPhoto",
    "heights_above_surface",
    "planned_photos",
    "predict_plan",
]
