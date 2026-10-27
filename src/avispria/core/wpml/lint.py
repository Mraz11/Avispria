# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Independent KMZ linter. It re-reads a finished file and trusts nothing upstream."""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import pairwise

from avispria.core.mission import haversine_m
from avispria.core.safety import Issue
from avispria.core.wpml.kmz import KmzError
from avispria.core.wpml.reader import KmzMission, read_mission

DJI_FLY_NAMESPACE = "http://www.uav.com/wpmz/1.0.2"


@dataclass(frozen=True)
class LintLimits:
    max_waypoints: int = 99  # DJI Fly's real limit per aircraft is not documented
    min_height_m: float = -200.0  # relative to takeoff (valleys below the launch point)
    max_height_m: float = 500.0
    max_speed_ms: float = 15.0
    min_segment_m: float = 0.5
    max_segment_m: float = 2000.0


def lint_kmz(data: bytes, limits: LintLimits) -> list[Issue]:
    """Every problem found in ``data``; an empty list means the file passed."""
    try:
        mission = read_mission(data)
    except KmzError as exc:
        return [Issue("error", "WPML001", str(exc))]
    issues: list[Issue] = []
    _check_header(mission, issues)
    _check_waypoints(mission, limits, issues)
    _check_actions(mission, issues)
    return issues


def _check_header(m: KmzMission, issues: list[Issue]) -> None:
    if m.namespace != m.template_namespace:
        issues.append(Issue("error", "WPML002", "template.kml and waylines.wpml namespaces differ"))
    elif m.namespace != DJI_FLY_NAMESPACE:
        issues.append(
            Issue(
                "warning",
                "WPML003",
                f"namespace {m.namespace} is not DJI Fly's {DJI_FLY_NAMESPACE}",
            )
        )
    if m.height_mode != "relativeToStartPoint":
        issues.append(
            Issue(
                "error", "WPML004", f"height mode {m.height_mode!r} (must be relativeToStartPoint)"
            )
        )
    if m.finish_action != "goHome" or m.rc_lost_action != "goBack":
        issues.append(
            Issue(
                "warning",
                "WPML016",
                f"finish action {m.finish_action!r} / signal-lost action {m.rc_lost_action!r}: "
                "DJI Fly defaults are goHome / goBack",
            )
        )


def _check_waypoints(m: KmzMission, limits: LintLimits, issues: list[Issue]) -> None:
    wps = m.waypoints

    def err(code: str, msg: str) -> None:
        issues.append(Issue("error", code, msg))

    if len(wps) < 2:
        err("WPML005", f"mission has {len(wps)} waypoint(s); DJI Fly needs at least two")
    if [w.index for w in wps] != list(range(len(wps))):
        err("WPML006", "waypoint indices are not 0..n-1 in order")
    if len(wps) > limits.max_waypoints:
        err("WPML010", f"{len(wps)} waypoints exceed the configured cap of {limits.max_waypoints}")
    speeds = [m.auto_speed_ms, m.transit_speed_ms]
    for w in wps:
        if not (
            math.isfinite(w.lon)
            and math.isfinite(w.lat)
            and -180 <= w.lon <= 180
            and -90 <= w.lat <= 90
        ):
            err("WPML007", f"waypoint {w.index}: invalid coordinates ({w.lon}, {w.lat})")
        if not (
            math.isfinite(w.height_m) and limits.min_height_m <= w.height_m <= limits.max_height_m
        ):
            err("WPML008", f"waypoint {w.index}: height {w.height_m} m out of range")
        if w.gimbal_pitch_deg is not None and not -90 <= w.gimbal_pitch_deg <= 0:
            err("WPML013", f"waypoint {w.index}: gimbal pitch {w.gimbal_pitch_deg} out of range")
        speeds.append(w.speed_ms)
    if any(not (math.isfinite(s) and 0 < s <= limits.max_speed_ms) for s in speeds):
        err("WPML009", f"a speed is outside (0, {limits.max_speed_ms}] m/s")
    for a, b in pairwise(wps):
        if not all(math.isfinite(v) for v in (a.lon, a.lat, b.lon, b.lat)):
            continue
        dist = haversine_m(a.lon, a.lat, b.lon, b.lat)
        if dist < limits.min_segment_m:
            err("WPML011", f"waypoints {a.index} and {b.index} are only {dist:.2f} m apart")
        elif dist > limits.max_segment_m:
            issues.append(
                Issue("warning", "WPML012", f"segment {a.index}->{b.index} is {dist:.0f} m long")
            )


def _check_actions(m: KmzMission, issues: list[Issue]) -> None:
    n = len(m.waypoints)
    ids: list[int] = []
    for w in m.waypoints:
        for a in w.actions:
            ids.append(a.action_id)
            if not (0 <= a.start <= a.end < max(n, 1)) or a.start != w.index:
                issues.append(
                    Issue(
                        "error",
                        "WPML014",
                        f"waypoint {w.index}: action group {a.group_id} spans {a.start}..{a.end}",
                    )
                )
    if len(ids) != len(set(ids)):
        issues.append(Issue("error", "WPML015", "action ids are not unique"))
