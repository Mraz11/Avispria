# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Survey planner: AOI + camera + terrain -> validated, battery-sized missions."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import replace

import numpy as np
from numpy.typing import NDArray

from avispria.core.camera import altitude_for_gsd, gsd_m, spacing_m
from avispria.core.errors import PlanningError
from avispria.core.geometry import LocalFrame
from avispria.core.grid import auto_heading, lawnmower
from avispria.core.mission import Mission, PhotoMode, Takeoff, Waypoint
from avispria.core.plan_model import PlanRequest, PlanResult, PlanSummary
from avispria.core.plan_path import route_profile, strip_vertices
from avispria.core.predict import heights_above_surface, planned_photos, predict_plan
from avispria.core.profile import TerrainOptions
from avispria.core.safety import Issue, check_mission
from avispria.core.sorties import estimate_duration_s, split_by_strip
from avispria.core.speed import solve_speed

FloatArray = NDArray[np.float64]

__all__ = ["PlanRequest", "PlanResult", "PlanSummary", "PlanningError", "TerrainOptions", "plan"]


def _validate(req: PlanRequest) -> float:
    if (req.target_gsd_m is None) == (req.agl_m is None):
        raise PlanningError("give exactly one of target_gsd_m or agl_m")
    if not -90.0 <= req.gimbal_pitch_deg <= 0.0:
        raise PlanningError("gimbal pitch must be between -90 (nadir) and 0 (horizon)")
    if req.dem is None and not req.flat_terrain:
        raise PlanningError(
            "terrain data required: supply a DEM, or explicitly choose flat terrain"
        )
    if req.dem is not None and req.flat_terrain:
        raise PlanningError("choose either a DEM or flat terrain, not both")
    if req.surface_height_m < 0:
        raise PlanningError("surface_height_m must not be negative")
    if req.target_gsd_m is not None:
        return altitude_for_gsd(req.camera, req.target_gsd_m)
    assert req.agl_m is not None
    if req.agl_m <= 0:
        raise PlanningError("agl_m must be positive")
    return req.agl_m


MAX_CALIBRATION_PASSES = 4  # in total, including the first plan
MIN_REFERENCE_M = 5.0
SPACING_RANGE = (0.6, 1.4)  # spacing height relative to the target height
LOW_PERCENTILE = 10.0  # overlap is guaranteed down to this part of the lowest photos


def plan(req: PlanRequest) -> PlanResult:
    """Plan a survey. Raises PlanningError when no safe plan can be produced.

    Over terrain the route is tuned until the photos' real height above the surface matches
    the request (see ``_calibrated``); the result carries a prediction of what it achieves.
    """
    try:
        return _calibrated(req)
    except PlanningError:
        raise
    except ValueError as exc:
        raise PlanningError(str(exc)) from exc


def _photo_heights(result: PlanResult, req: PlanRequest) -> FloatArray | None:
    """Real height above the surface at every planned photo (None without a model)."""
    elevation = result.summary.takeoff_elevation_m
    if req.dem is None or elevation is None:
        return None
    photos = [p for m in result.missions for p in planned_photos(m)]
    if len(photos) < 3:
        return None
    heights = heights_above_surface(photos, elevation, req.dem, req.surface_height_m)
    heights = heights[np.isfinite(heights)]
    return heights if len(heights) >= 3 else None


def _calibrated(req: PlanRequest) -> PlanResult:
    target = _validate(req)
    terrain = req.dem is not None and req.calibrate_height
    margin = req.terrain.curve_dip_margin_m
    # the route is never planned lower than the clearance rule allows above the dilated surface
    lowest = max(req.limits.min_surface_clearance_m - margin, MIN_REFERENCE_M)
    reference = max(lowest, target - margin) if terrain else target
    spacing = target
    passes: list[tuple[float, PlanResult, float, float]] = []  # (miss, plan, reference, spacing)
    while True:
        result = _plan(req, target, reference, spacing)
        heights = _photo_heights(result, req) if terrain else None
        if heights is None:
            passes.append((0.0, result, reference, spacing))
            break
        typical = float(np.median(heights))
        low = float(np.percentile(heights, LOW_PERCENTILE))
        # a good pass has the typical height on target AND spacing computed for the height
        # its lowest photos really fly at (otherwise their overlap falls short)
        miss = (abs(typical - target) + abs(low - spacing)) / target
        passes.append((miss, result, reference, spacing))
        new_ref = min(max(reference + (target - typical), lowest), 2.0 * target)
        new_spacing = min(max(low, SPACING_RANGE[0] * target), SPACING_RANGE[1] * target)
        tolerance = max(0.02 * target, 0.5)
        if abs(new_ref - reference) <= tolerance and abs(new_spacing - spacing) <= tolerance:
            break
        if len(passes) >= MAX_CALIBRATION_PASSES:
            break
        reference, spacing = new_ref, new_spacing
    # the number of flight lines is a whole number, so passes do not improve monotonically:
    # keep the most consistent one (the first of equals)
    _, result, reference, spacing = min(passes, key=lambda item: item[0])

    prediction = predict_plan(
        result.missions,
        req.camera,
        req.aoi,
        dem=req.dem,
        takeoff_elevation_m=result.summary.takeoff_elevation_m,
        surface_height_m=req.surface_height_m,
        shutter_s=req.shutter_s,
        target_gsd_cm=gsd_m(req.camera, target) * 100.0,
    )
    summary = replace(
        result.summary,
        flight_reference_m=reference,
        spacing_height_m=spacing,
        calibration_steps=len(passes),
        prediction=prediction,
    )
    issues = (*result.issues, *(() if prediction is None else tuple(prediction.issues)))
    return PlanResult(result.missions, summary, issues)


def _plan(req: PlanRequest, target_m: float, reference_m: float, spacing_m_: float) -> PlanResult:
    """One planning pass. ``reference_m`` is the height the route is built around,
    ``spacing_m_`` the height the photo and line spacing are computed for and
    ``target_m`` the height the user asked for (it fixes the reported resolution)."""
    cam = req.camera
    frame = LocalFrame.for_polygon(req.aoi)
    area = frame.polygon_to_local(req.aoi)
    sp = spacing_m(cam, spacing_m_, req.front_overlap, req.side_overlap)
    heading = auto_heading(area) if req.heading_deg is None else req.heading_deg % 360.0
    overrun = sp.photo_m if req.overrun_m is None else req.overrun_m
    strips = lawnmower(area, heading, sp.line_m, overrun)
    if req.crosshatch:
        strips += lawnmower(area, heading + 90.0, sp.line_m, overrun)
    if not strips:
        raise PlanningError("the area is too small to fit a survey line")

    ground_sample = gsd_m(cam, target_m)
    speed_gsd = gsd_m(cam, spacing_m_)  # the lowest photos set the motion-blur limit
    speed = solve_speed(
        cam, speed_gsd, req.shutter_s, sp.photo_m, req.drone_max_speed_ms, wind_ms=req.wind_ms
    )
    # DJI Fly works in 0.1 m/s steps; round down (slower is the safe direction)
    speed = replace(speed, speed_ms=math.floor(speed.speed_ms * 10 + 1e-9) / 10)
    if not speed.feasible or speed.speed_ms < 1.0:
        raise PlanningError(
            f"no usable speed: '{speed.binding}' limits the drone to "
            f"{speed.speed_ms:.2f} m/s; use a faster shutter, more height or less overlap"
        )

    path: list[tuple[float, float]] = []
    photo_flags: list[bool] = []
    strip_of_vertex: list[int] = []
    strip_end_vertices: list[int] = []
    for k, strip in enumerate(strips):
        verts = strip_vertices(strip, sp.photo_m, overrun, req.photo_mode)
        strip_end_vertices += [len(path), len(path) + len(verts) - 1]
        for x, y, photo in verts:
            path.append((x, y))
            photo_flags.append(photo)
            strip_of_vertex.append(k)

    lons, lats, vertex_idx, prof = route_profile(req, frame, path, reference_m)
    photo_at = {vertex_idx[j]: f for j, f in enumerate(photo_flags) if f}
    stop_at = {vertex_idx[j] for j in strip_end_vertices}
    strip_end = {}
    for j, k in enumerate(strip_of_vertex):
        strip_end[k] = vertex_idx[j]
    ends = sorted(strip_end.items())

    def strip_id(sample: int) -> int:
        return next(k for k, end in ends if sample <= end)

    wps: list[Waypoint] = []
    ids: list[int] = []
    for j, s in enumerate(prof.keep):
        wps.append(
            Waypoint(
                lon=float(lons[s]),
                lat=float(lats[s]),
                height_m=float(prof.keep_height_rel_m[j]),
                speed_ms=speed.speed_ms,
                gimbal_pitch_deg=req.gimbal_pitch_deg,
                take_photo=photo_at.get(s, False),
                surface_clearance_m=None
                if prof.surface_clearance_m is None
                else float(prof.surface_clearance_m[j]),
                height_above_ground_m=None
                if prof.above_ground_m is None
                else float(prof.above_ground_m[j]),
                stop=s in stop_at,
            )
        )
        ids.append(strip_id(s))

    takeoff = Takeoff(
        req.takeoff_lon, req.takeoff_lat, prof.takeoff_elevation_m, prof.takeoff_elevation_source
    )
    interval = sp.photo_m / speed.speed_ms if req.photo_mode is PhotoMode.INTERVAL else None

    def duration(group: Sequence[Waypoint]) -> float:
        return estimate_duration_s(
            group, takeoff, speed.speed_ms, req.climb_rate_ms, req.photo_overhead_s
        )

    groups = split_by_strip(
        wps,
        ids,
        req.limits.max_waypoints,
        req.limits.max_flight_time_s,
        duration,
    )
    missions: list[Mission] = []
    issues: list[Issue] = []
    for n, group in enumerate(groups, start=1):
        mission = Mission(
            name=f"{req.name}_{n:02d}",
            waypoints=tuple(group),
            takeoff=takeoff,
            photo_mode=req.photo_mode,
            photo_interval_s=interval,
            speed_ms=speed.speed_ms,
            estimated_duration_s=duration(group),
        )
        missions.append(mission)
        for issue in check_mission(mission, req.limits, camera_min_interval_s=cam.min_interval_s):
            issues.append(Issue(issue.level, issue.code, f"{mission.name}: {issue.message}"))

    summary = PlanSummary(
        agl_m=target_m,
        gsd_m=ground_sample,
        photo_spacing_m=sp.photo_m,
        line_spacing_m=sp.line_m,
        heading_deg=heading,
        strips=len(strips),
        speed=speed,
        photo_interval_s=interval,
        terrain_source=prof.terrain_source,
        takeoff_elevation_m=prof.takeoff_elevation_m,
        takeoff_elevation_source=prof.takeoff_elevation_source,
    )
    return PlanResult(tuple(missions), summary, tuple(issues))
