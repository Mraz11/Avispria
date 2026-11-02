# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Object scans: rings of photos around a tree, a building or any other single object.

The object is modelled as an upright cylinder (radius ``object_radius_m``, from ``base_height_m``
up to ``object_height_m``). The aircraft flies rings around it at ``object_radius_m + standoff_m``
from the axis, stops at each waypoint, and takes a photo looking at the object, so that the whole
surface is seen from many directions and heights (what 3D reconstruction needs).

How the rings are chosen, so that coverage is guaranteed and not hoped for:

1. Each photo sees a patch of the object's surface as tall as the picture's short side (at that
   distance). The heights the rings must be CENTRED on are spaced evenly so that neighbouring
   patches overlap by ``side_overlap``, the lowest reaching ``base_height_m`` and the highest the
   top.
2. The camera tilts up a little at the bottom and down a little at the top (``look_up_deg`` to
   ``look_down_deg``), because views from different angles reconstruct better than level ones.
   Given the tilt, the ring's height follows: the camera must be where its line of sight meets the
   surface at the centre height. (Aiming every ring at one point instead squeezes the visible
   patches towards the middle by radius / ring radius, and the rings would have to be absurdly
   high.)
3. Around a ring, neighbouring photos are at most ``max_step_deg`` apart (reconstruction loses
   track of a point once the view turns more than about 15 degrees) and overlap by
   ``front_overlap`` on the surface, whichever needs more photos.
4. Optionally a top cap: a small grid of straight-down photos above the object.

The rings form a spiral: every ring is flown the same way round, starting at the bearing that
faces the takeoff point, so the climb to the next ring is a diagonal and never two waypoints on top
of each other (a pure vertical move is refused: DJI Fly mishandles waypoints in the same place).

Every waypoint faces the object (DJI Fly's "Face POI" heading), stops, hovers and takes one photo;
the camera tilt is written explicitly (the verified encoding), not left for the aircraft to work
out.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

from avispria.core.camera import CameraProfile, footprint_m, gsd_m
from avispria.core.errors import PlanningError
from avispria.core.geometry import LocalFrame, utm_crs_for
from avispria.core.mission import Mission, PhotoMode, Takeoff, Waypoint, haversine_m
from avispria.core.safety import Issue, SafetyLimits, check_mission
from avispria.core.sorties import estimate_duration_s

GIMBAL_MIN_DEG = -90.0  # the Lito X1's own limits
GIMBAL_MAX_DEG = 40.0
MIN_STANDOFF_M = 5.0  # below this: refused (a few metres of GPS error, and wind)
COMFORT_STANDOFF_M = 10.0  # below this: a warning
MIN_CAMERA_HEIGHT_M = 3.0  # above the ground at the object
CLIMB_RATE_MS = 2.5
STOP_AND_GO_S = 2.0  # slowing down and speeding up at every stop


@dataclass(frozen=True)
class ScanRequest:
    centre_lon: float  # the object's axis
    centre_lat: float
    camera: CameraProfile
    drone_max_speed_ms: float
    object_height_m: float  # top of the object, above the ground at its foot
    object_radius_m: float  # its widest horizontal radius (a crown, a trunk, a building)
    standoff_m: float = 15.0  # horizontal distance from the object's surface to the camera ring
    base_height_m: float = 0.0  # the lowest height to photograph
    front_overlap: float = 0.80  # between neighbouring photos around a ring (on the surface)
    side_overlap: float = 0.70  # between rings (on the surface)
    max_step_deg: float = 10.0  # never more than this between neighbouring photos around a ring
    look_up_deg: float = 10.0  # camera tilt of the lowest ring (positive = looking up)
    look_down_deg: float = 20.0  # camera tilt of the highest ring (looking down)
    top_cap: bool = True
    top_clearance_m: float = 8.0  # how far above the top the cap flies
    speed_ms: float = 3.0
    hover_s: float = 1.0  # stand still this long at each photo
    takeoff_lon: float | None = None  # default: outside the ring, on the south side
    takeoff_lat: float | None = None
    ground_offset_m: float = 0.0  # the ground at the object, relative to the takeoff point
    name: str = "scan"
    limits: SafetyLimits = field(default_factory=SafetyLimits)


@dataclass(frozen=True)
class Ring:
    height_m: float  # camera height above the ground at the object
    pitch_deg: float
    centre_height_m: float  # the height on the object the camera looks at
    photos: int
    gsd_cm: float  # on the surface, at the centre of the picture


@dataclass(frozen=True)
class ScanSummary:
    ring_radius_m: float
    rings: tuple[Ring, ...]
    cap_photos: int
    photos: int
    gsd_cm_best: float
    gsd_cm_worst: float


@dataclass(frozen=True)
class ScanPlan:
    missions: tuple[Mission, ...]
    summary: ScanSummary
    issues: tuple[Issue, ...]


def _validate(req: ScanRequest) -> None:
    def bad(message: str) -> None:
        raise PlanningError(message)

    values = (
        req.object_height_m,
        req.object_radius_m,
        req.standoff_m,
        req.base_height_m,
        req.top_clearance_m,
        req.speed_ms,
        req.hover_s,
        req.ground_offset_m,
        req.max_step_deg,
        req.look_up_deg,
        req.look_down_deg,
    )
    if not all(math.isfinite(v) for v in values):
        bad("every number must be a real number")
    if req.object_radius_m <= 0:
        bad("the object's radius must be more than zero")
    if req.object_height_m <= req.base_height_m:
        bad("the top of the object must be higher than the lowest height to photograph")
    if req.base_height_m < 0:
        bad("the lowest height to photograph cannot be below the ground")
    if req.standoff_m <= 0:
        bad("the distance from the object must be more than zero")
    for label, value in (("front", req.front_overlap), ("side", req.side_overlap)):
        if not 0.0 <= value < 0.96:
            bad(f"the {label} overlap must be between 0 and 95%")
    if not 1.0 <= req.max_step_deg <= 30.0:
        bad("the largest angle between photos must be between 1 and 30 degrees")
    if not 0.0 < req.speed_ms <= req.drone_max_speed_ms:
        bad(f"the speed must be between 0 and {req.drone_max_speed_ms:g} m/s")
    if req.hover_s < 0:
        bad("the hover time cannot be negative")
    if not 0.0 <= req.look_up_deg <= GIMBAL_MAX_DEG:
        bad(f"looking up can be at most {GIMBAL_MAX_DEG:g} degrees (the camera's limit)")
    if not 0.0 <= req.look_down_deg <= -GIMBAL_MIN_DEG:
        bad("looking down can be at most 90 degrees")
    if req.top_cap and req.top_clearance_m < 3.0:
        bad("the top cap must fly at least 3 m above the top of the object")


def _ring_centres(req: ScanRequest, along_m: float) -> list[float]:
    """Heights on the object the rings are centred on: even, overlapping, reaching base and top."""
    span = req.object_height_m - req.base_height_m
    if span <= along_m:
        return [(req.base_height_m + req.object_height_m) / 2.0]
    step = along_m * (1.0 - req.side_overlap)
    count = math.ceil((span - along_m) / step - 1e-9) + 1
    first = req.base_height_m + along_m / 2.0
    last = req.object_height_m - along_m / 2.0
    return [first + (last - first) * k / (count - 1) for k in range(count)]


def _photos_around(req: ScanRequest, distance_m: float) -> int:
    across, _ = footprint_m(req.camera, distance_m)
    step_surface = across * (1.0 - req.front_overlap)  # metres along the surface between photos
    step_deg = min(req.max_step_deg, math.degrees(step_surface / req.object_radius_m))
    return max(8, math.ceil(360.0 / step_deg - 1e-9))


def _cap_lattice(req: ScanRequest, top_distance_m: float) -> list[tuple[float, float]]:
    """Straight-down photo positions (east, north) over a disc covering the object's top."""
    across, along = footprint_m(req.camera, top_distance_m)
    along_step = max(along * (1.0 - req.side_overlap), 0.5)
    across_step = max(across * (1.0 - req.front_overlap), 0.5)
    reach = req.object_radius_m + 0.5 * min(across, along) * (1.0 - req.side_overlap)
    xs = _axis(reach, across_step)
    ys = _axis(reach, along_step)
    points = []
    for row, y in enumerate(ys):
        row_xs = xs if row % 2 == 0 else xs[::-1]  # serpentine: no long jumps back
        points += [(x, y) for x in row_xs if math.hypot(x, y) <= reach + 1e-9]
    return points


def _axis(reach: float, step: float) -> list[float]:
    n = max(1, math.ceil(2.0 * reach / step - 1e-9))
    return [-reach + 2.0 * reach * i / n for i in range(n + 1)]


def plan_scan(req: ScanRequest) -> ScanPlan:
    """Plan the rings (and the cap), split them into missions, and check every mission."""
    _validate(req)
    cam = req.camera
    ring_r = req.object_radius_m + req.standoff_m
    surface_d = req.standoff_m  # horizontal distance from the camera ring to the surface
    _, along_level = footprint_m(cam, surface_d)
    centres = _ring_centres(req, along_level)
    n = len(centres)
    # tilt schedule: looking up at the bottom, down at the top
    pitches = [
        req.look_up_deg + (-req.look_down_deg - req.look_up_deg) * (k / (n - 1) if n > 1 else 0.5)
        for k in range(n)
    ]
    heights = [
        c - math.tan(math.radians(p)) * surface_d for c, p in zip(centres, pitches, strict=True)
    ]
    issues: list[Issue] = []

    def issue(level: str, code: str, message: str) -> None:
        issues.append(Issue(level, code, message))  # type: ignore[arg-type]

    if req.standoff_m < MIN_STANDOFF_M:
        issue(
            "error",
            "SC001",
            f"{req.standoff_m:g} m from the object is too close: use at least {MIN_STANDOFF_M:g} m",
        )
    elif req.standoff_m < COMFORT_STANDOFF_M:
        issue(
            "warning",
            "SC002",
            f"{req.standoff_m:g} m from the object is close: GPS is only good to a few metres",
        )
    low = [(k, h) for k, h in enumerate(heights) if h < MIN_CAMERA_HEIGHT_M]
    if low:
        k, h = low[0]
        issue(
            "error",
            "SC003",
            f"ring {k + 1} would fly {h:.1f} m above the ground (at least "
            f"{MIN_CAMERA_HEIGHT_M:g} m is needed): raise the lowest height to photograph, "
            "or look up less",
        )

    takeoff_lon, takeoff_lat = req.takeoff_lon, req.takeoff_lat
    frame = LocalFrame(utm_crs_for(req.centre_lon, req.centre_lat))
    cx, cy = (float(v[0]) for v in frame.to_local([req.centre_lon], [req.centre_lat]))
    if takeoff_lon is None or takeoff_lat is None:  # south of the object, outside the ring
        lons, lats = frame.to_lonlat([cx], [cy - (ring_r + 15.0)])
        takeoff_lon, takeoff_lat = float(lons[0]), float(lats[0])
    takeoff = Takeoff(takeoff_lon, takeoff_lat, None, "flat ground assumed")
    tx, ty = (float(v[0]) for v in frame.to_local([takeoff_lon], [takeoff_lat]))
    start_bearing = math.degrees(math.atan2(tx - cx, ty - cy)) % 360.0  # from the object to takeoff

    aim_height = (req.base_height_m + req.object_height_m) / 2.0
    poi = (req.centre_lon, req.centre_lat, aim_height + req.ground_offset_m)

    def waypoint(east: float, north: float, height: float, pitch: float, *, ring: bool) -> Waypoint:
        lons, lats = frame.to_lonlat([cx + east], [cy + north])
        return Waypoint(
            lon=float(lons[0]),
            lat=float(lats[0]),
            height_m=height + req.ground_offset_m,
            speed_ms=req.speed_ms,
            gimbal_pitch_deg=max(GIMBAL_MIN_DEG, min(GIMBAL_MAX_DEG, round(pitch, 1))),
            take_photo=True,
            surface_clearance_m=None,
            height_above_ground_m=height,
            stop=True,
            poi=poi if ring else None,
            heading_deg=None if ring else 0.0,
            hover_s=req.hover_s,
        )

    units: list[list[Waypoint]] = []  # one unit per ring, then the cap: kept whole when splitting
    rings: list[Ring] = []
    for k in range(n):
        slant = math.hypot(surface_d, centres[k] - heights[k])
        count = _photos_around(req, slant)
        step = 360.0 / count
        unit = []
        for i in range(count):
            theta = math.radians(start_bearing + step * i)
            unit.append(
                waypoint(
                    ring_r * math.sin(theta),
                    ring_r * math.cos(theta),
                    heights[k],
                    pitches[k],
                    ring=True,
                )
            )
        units.append(unit)
        rings.append(Ring(heights[k], pitches[k], centres[k], count, gsd_m(cam, slant) * 100.0))
    cap_count = 0
    if req.top_cap:
        cap_height = req.object_height_m + req.top_clearance_m
        lattice = _cap_lattice(req, req.top_clearance_m)
        # start where the last ring ended, not at the far side of the object
        end = units[-1][-1]
        ex, ey = (
            float(v[0]) - c
            for v, c in zip(frame.to_local([end.lon], [end.lat]), (cx, cy), strict=True)
        )
        if math.hypot(lattice[0][0] - ex, lattice[0][1] - ey) > math.hypot(
            lattice[-1][0] - ex, lattice[-1][1] - ey
        ):
            lattice = lattice[::-1]
        units.append([waypoint(x, y, cap_height, -90.0, ring=False) for x, y in lattice])
        cap_count = len(lattice)
        issue(
            "warning",
            "SC005",
            "the top cap covers the top with straight-down photos; check it on the first flight",
        )

    missions = _split(req, units, takeoff, issues)
    gsds = [r.gsd_cm for r in rings] + (
        [gsd_m(cam, req.top_clearance_m) * 100.0] if req.top_cap else []
    )
    summary = ScanSummary(
        ring_radius_m=ring_r,
        rings=tuple(rings),
        cap_photos=cap_count,
        photos=sum(r.photos for r in rings) + cap_count,
        gsd_cm_best=min(gsds),
        gsd_cm_worst=max(gsds),
    )
    for mission in missions:
        issues.extend(check_mission(mission, req.limits))
    unique = list(dict.fromkeys(issues))  # one terrain warning, not one per mission
    return ScanPlan(tuple(missions), summary, tuple(unique))


def _duration(req: ScanRequest, group: Sequence[Waypoint], takeoff: Takeoff) -> float:
    return estimate_duration_s(
        group, takeoff, req.speed_ms, CLIMB_RATE_MS, req.hover_s + STOP_AND_GO_S
    )


def _split(
    req: ScanRequest, units: list[list[Waypoint]], takeoff: Takeoff, issues: list[Issue]
) -> list[Mission]:
    """Pack whole rings into missions within the waypoint and flight-time limits."""
    limit = req.limits.max_waypoints
    groups: list[list[Waypoint]] = []
    current: list[Waypoint] = []
    for unit in units:
        pieces = [
            unit[i : i + limit] for i in range(0, len(unit), limit)
        ]  # a ring bigger than the limit
        for piece in pieces:
            joined = [*current, *piece]
            fits = (
                len(joined) <= limit
                and _duration(req, joined, takeoff) <= req.limits.max_flight_time_s
            )
            if current and not fits:
                groups.append(current)
                current = []
            current = [*current, *piece]
    if current:
        groups.append(current)
    if any(len(u) > limit for u in units):
        issues.append(
            Issue(
                "warning",
                "SC006",
                f"a ring has more than {limit} waypoints, so it is split across missions",
            )
        )
    return [
        Mission(
            name=f"{req.name}_{n:02d}",
            waypoints=tuple(g),
            takeoff=takeoff,
            photo_mode=PhotoMode.WAYPOINT,
            photo_interval_s=None,
            speed_ms=req.speed_ms,
            estimated_duration_s=_duration(req, g, takeoff),
        )
        for n, g in enumerate(groups, start=1)
    ]


def farthest_from_takeoff_m(mission: Mission) -> float:
    t = mission.takeoff
    return max(haversine_m(t.lon, t.lat, w.lon, w.lat) for w in mission.waypoints)
