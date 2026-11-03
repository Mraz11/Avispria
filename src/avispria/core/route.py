# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The length and flying time of a route from waypoint to waypoint, as DJI Fly shows on its map."""

from __future__ import annotations

import math
from collections.abc import Sequence

from avispria.core.geometry import LocalFrame, utm_crs_for
from avispria.core.mission import Waypoint


def leg_lengths_m(waypoints: Sequence[Waypoint]) -> list[float]:
    """The distance of each leg, from a waypoint to the next one, in metres on the ground."""
    if len(waypoints) < 2:
        return []
    frame = LocalFrame(utm_crs_for(waypoints[0].lon, waypoints[0].lat))
    xs, ys = frame.to_local([w.lon for w in waypoints], [w.lat for w in waypoints])
    return [math.hypot(xs[i + 1] - xs[i], ys[i + 1] - ys[i]) for i in range(len(waypoints) - 1)]


def route_length_m(waypoints: Sequence[Waypoint]) -> float:
    return float(sum(leg_lengths_m(waypoints)))


def route_seconds(waypoints: Sequence[Waypoint], default_speed_ms: float = 0.0) -> float:
    """Time to fly the route when each leg is flown at the speed set on the waypoint it starts from.

    A waypoint with no usable speed uses ``default_speed_ms``; with no speed at all the time is 0.
    """
    total = 0.0
    for leg, w in zip(leg_lengths_m(waypoints), waypoints, strict=False):
        speed = w.speed_ms if w.speed_ms > 0 else default_speed_ms
        if speed > 0:
            total += leg / speed
    return total


def clock(seconds: float) -> str:
    """m:ss, the way DJI Fly writes a flight time."""
    whole = round(seconds)
    return f"{whole // 60}:{whole % 60:02d}"
