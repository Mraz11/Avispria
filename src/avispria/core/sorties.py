# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Flight-time estimates and splitting a survey into battery-sized sorties."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from itertools import pairwise

from avispria.core.mission import Takeoff, Waypoint, haversine_m


def estimate_duration_s(
    waypoints: Sequence[Waypoint],
    takeoff: Takeoff,
    speed_ms: float,
    climb_rate_ms: float,
    photo_overhead_s: float,
) -> float:
    """Rough flight time: legs at survey speed, climb and descent, photo overhead."""
    if not waypoints:
        return 0.0
    first, last = waypoints[0], waypoints[-1]
    legs = haversine_m(takeoff.lon, takeoff.lat, first.lon, first.lat)
    legs += sum(haversine_m(a.lon, a.lat, b.lon, b.lat) for a, b in pairwise(waypoints))
    legs += haversine_m(last.lon, last.lat, takeoff.lon, takeoff.lat)
    top = max(max(w.height_m for w in waypoints), 0.0)
    photos = sum(1 for w in waypoints if w.take_photo)
    return legs / speed_ms + 2.0 * top / climb_rate_ms + photos * photo_overhead_s


def split_by_strip(
    waypoints: Sequence[Waypoint],
    strip_ids: Sequence[int],
    max_waypoints: int,
    max_duration_s: float,
    duration: Callable[[Sequence[Waypoint]], float],
) -> list[list[Waypoint]]:
    """Greedily group whole strips into sorties within waypoint and time limits.

    A single strip that alone exceeds a limit stays in its own sortie so the
    safety validator reports it instead of the plan silently changing.
    """
    if len(waypoints) != len(strip_ids):
        raise ValueError("waypoints and strip_ids must align")
    groups: list[list[Waypoint]] = []
    last_id: int | None = None
    for wp, sid in zip(waypoints, strip_ids, strict=True):
        if sid != last_id:
            groups.append([])
            last_id = sid
        groups[-1].append(wp)
    sorties: list[list[Waypoint]] = []
    current: list[Waypoint] = []
    for strip in groups:
        candidate = current + strip
        too_big = len(candidate) > max_waypoints or duration(candidate) > max_duration_s
        if current and too_big:
            sorties.append(current)
            current = list(strip)
        else:
            current = candidate
    if current:
        sorties.append(current)
    return sorties
