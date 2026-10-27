# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Mission safety validation. Errors block export; warnings must be acknowledged."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from avispria.core.mission import Mission, PhotoMode, haversine_m


@dataclass(frozen=True)
class SafetyLimits:
    """Operational limits. Defaults are conservative; set them to your local rules."""

    max_height_above_takeoff_m: float = 120.0
    max_height_above_ground_m: float = 120.0
    min_surface_clearance_m: float = 20.0
    max_distance_from_takeoff_m: float = 500.0
    max_waypoints: int = 99
    max_flight_time_s: float = 20 * 60.0
    max_speed_ms: float = 12.0


@dataclass(frozen=True)
class Issue:
    level: Literal["error", "warning"]
    code: str
    message: str


def check_mission(
    mission: Mission, limits: SafetyLimits, *, camera_min_interval_s: float | None = None
) -> list[Issue]:
    """Return every rule the mission breaks."""
    issues: list[Issue] = []
    wps = mission.waypoints
    t = mission.takeoff

    def err(code: str, msg: str) -> None:
        issues.append(Issue("error", code, msg))

    top = max(w.height_m for w in wps)
    if top > limits.max_height_above_takeoff_m:
        err(
            "SAF001",
            f"height {top:.1f} m above takeoff exceeds {limits.max_height_above_takeoff_m} m",
        )

    agl = [w.height_above_ground_m for w in wps if w.height_above_ground_m is not None]
    if agl and max(agl) > limits.max_height_above_ground_m:
        err(
            "SAF002",
            f"estimated height above ground {max(agl):.1f} m exceeds "
            f"{limits.max_height_above_ground_m} m",
        )

    clear = [w.surface_clearance_m for w in wps if w.surface_clearance_m is not None]
    if clear and min(clear) < limits.min_surface_clearance_m:
        err(
            "SAF003",
            f"clearance {min(clear):.1f} m above the surface model is below "
            f"{limits.min_surface_clearance_m} m",
        )

    far = max(haversine_m(t.lon, t.lat, w.lon, w.lat) for w in wps)
    if far > limits.max_distance_from_takeoff_m:
        err(
            "SAF004",
            f"waypoint {far:.0f} m from takeoff exceeds {limits.max_distance_from_takeoff_m} m "
            "(keep visual line of sight)",
        )

    if len(wps) > limits.max_waypoints:
        err("SAF005", f"{len(wps)} waypoints exceed the limit of {limits.max_waypoints}")

    if mission.estimated_duration_s > limits.max_flight_time_s:
        err(
            "SAF006",
            f"estimated flight time {mission.estimated_duration_s / 60:.1f} min exceeds "
            f"{limits.max_flight_time_s / 60:.1f} min",
        )

    fastest = max([mission.speed_ms, *(w.speed_ms for w in wps)])
    if fastest > limits.max_speed_ms:
        err("SAF007", f"speed {fastest:.1f} m/s exceeds {limits.max_speed_ms} m/s")

    if not clear:
        issues.append(
            Issue(
                "warning",
                "SAF008",
                "planned without terrain data: heights assume flat ground at takeoff level",
            )
        )

    if (
        mission.photo_mode is PhotoMode.INTERVAL
        and camera_min_interval_s is not None
        and mission.photo_interval_s is not None
        and mission.photo_interval_s < camera_min_interval_s
    ):
        err(
            "SAF009",
            f"photo interval {mission.photo_interval_s:.2f} s is shorter than the camera's "
            f"minimum {camera_min_interval_s:.2f} s",
        )
    return issues
