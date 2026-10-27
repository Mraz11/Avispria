# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Survey planner: AOI + camera + terrain -> validated, battery-sized missions."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray
from shapely.geometry import Polygon

from avispria.core.camera import CameraProfile, altitude_for_gsd, gsd_m, spacing_m
from avispria.core.errors import PlanningError
from avispria.core.geometry import LocalFrame
from avispria.core.grid import Strip, auto_heading, densify_path, lawnmower
from avispria.core.mission import Mission, PhotoMode, Takeoff, Waypoint
from avispria.core.profile import HeightProfile, TerrainOptions, flat_profile, terrain_profile
from avispria.core.safety import Issue, SafetyLimits, check_mission
from avispria.core.sorties import estimate_duration_s, split_by_strip
from avispria.core.speed import SpeedSolution, solve_speed
from avispria.core.terrain import Dem

FloatArray = NDArray[np.float64]

__all__ = ["PlanRequest", "PlanResult", "PlanSummary", "PlanningError", "TerrainOptions", "plan"]


@dataclass(frozen=True)
class PlanRequest:
    aoi: Polygon
    camera: CameraProfile
    drone_max_speed_ms: float
    takeoff_lon: float
    takeoff_lat: float
    target_gsd_m: float | None = None
    agl_m: float | None = None
    front_overlap: float = 0.8
    side_overlap: float = 0.7
    heading_deg: float | None = None
    crosshatch: bool = False
    gimbal_pitch_deg: float = -90.0
    photo_mode: PhotoMode = PhotoMode.WAYPOINT
    dem: Dem | None = None
    flat_terrain: bool = False
    takeoff_elevation_m: float | None = None
    terrain: TerrainOptions = field(default_factory=TerrainOptions)
    shutter_s: float = 1 / 1000
    wind_ms: float = 0.0
    overrun_m: float | None = None
    limits: SafetyLimits = field(default_factory=SafetyLimits)
    photo_overhead_s: float = 1.0
    climb_rate_ms: float = 3.0
    name: str = "avispria"


@dataclass(frozen=True)
class PlanSummary:
    agl_m: float
    gsd_m: float
    photo_spacing_m: float
    line_spacing_m: float
    heading_deg: float
    strips: int
    speed: SpeedSolution
    photo_interval_s: float | None
    terrain_source: str
    takeoff_elevation_m: float | None
    takeoff_elevation_source: str


@dataclass(frozen=True)
class PlanResult:
    missions: tuple[Mission, ...]
    summary: PlanSummary
    issues: tuple[Issue, ...]

    @property
    def ok(self) -> bool:
        return not any(i.level == "error" for i in self.issues)


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
    if req.target_gsd_m is not None:
        return altitude_for_gsd(req.camera, req.target_gsd_m)
    assert req.agl_m is not None
    if req.agl_m <= 0:
        raise PlanningError("agl_m must be positive")
    return req.agl_m


def _strip_vertices(
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


def _profile(
    req: PlanRequest, frame: LocalFrame, path: list[tuple[float, float]], agl: float
) -> tuple[FloatArray, FloatArray, list[int], HeightProfile]:
    xs, ys, d, vertex_idx = densify_path(path, req.terrain.sample_step_m)
    lons, lats = frame.to_lonlat(xs, ys)
    if req.dem is None:
        prof: HeightProfile = flat_profile(len(xs), vertex_idx, agl)
    else:
        prof = terrain_profile(
            req.dem,
            lons,
            lats,
            d,
            vertex_idx,
            agl,
            (req.takeoff_lon, req.takeoff_lat),
            req.takeoff_elevation_m,
            req.terrain,
        )
    return lons, lats, vertex_idx, prof


def plan(req: PlanRequest) -> PlanResult:
    """Plan a survey. Raises PlanningError when no safe plan can be produced."""
    try:
        return _plan(req)
    except PlanningError:
        raise
    except ValueError as exc:
        raise PlanningError(str(exc)) from exc


def _plan(req: PlanRequest) -> PlanResult:
    agl = _validate(req)
    cam = req.camera
    frame = LocalFrame.for_polygon(req.aoi)
    area = frame.polygon_to_local(req.aoi)
    sp = spacing_m(cam, agl, req.front_overlap, req.side_overlap)
    heading = auto_heading(area) if req.heading_deg is None else req.heading_deg % 360.0
    overrun = sp.photo_m if req.overrun_m is None else req.overrun_m
    strips = lawnmower(area, heading, sp.line_m, overrun)
    if req.crosshatch:
        strips += lawnmower(area, heading + 90.0, sp.line_m, overrun)
    if not strips:
        raise PlanningError("the area is too small to fit a survey line")

    ground_sample = gsd_m(cam, agl)
    speed = solve_speed(
        cam, ground_sample, req.shutter_s, sp.photo_m, req.drone_max_speed_ms, wind_ms=req.wind_ms
    )
    if not speed.feasible:
        raise PlanningError(
            f"no usable speed: '{speed.binding}' limits the drone to "
            f"{speed.speed_ms:.2f} m/s; use a faster shutter, more height or less overlap"
        )

    path: list[tuple[float, float]] = []
    photo_flags: list[bool] = []
    strip_of_vertex: list[int] = []
    for k, strip in enumerate(strips):
        for x, y, photo in _strip_vertices(strip, sp.photo_m, overrun, req.photo_mode):
            path.append((x, y))
            photo_flags.append(photo)
            strip_of_vertex.append(k)

    lons, lats, vertex_idx, prof = _profile(req, frame, path, agl)
    photo_at = {vertex_idx[j]: f for j, f in enumerate(photo_flags) if f}
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
        agl_m=agl,
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
