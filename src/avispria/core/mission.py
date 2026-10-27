# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Immutable mission model shared by the planner, validators and writers."""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from enum import StrEnum

EARTH_RADIUS_M = 6_371_008.8


class PhotoMode(StrEnum):
    """How photos are triggered."""

    WAYPOINT = "waypoint"  # a takePhoto action at every photo waypoint
    INTERVAL = "interval"  # camera timed-shot mode, set by the pilot in DJI Fly


@dataclass(frozen=True)
class Takeoff:
    """Launch point. ``elevation_m`` is in the DEM's vertical datum (None if flat)."""

    lon: float
    lat: float
    elevation_m: float | None
    elevation_source: str


@dataclass(frozen=True)
class Waypoint:
    """One waypoint. ``height_m`` is relative to the takeoff point."""

    lon: float
    lat: float
    height_m: float
    speed_ms: float
    gimbal_pitch_deg: float
    take_photo: bool
    surface_clearance_m: float | None
    height_above_ground_m: float | None


@dataclass(frozen=True)
class Mission:
    """A single flyable mission (one battery, one DJI Fly mission slot)."""

    name: str
    waypoints: tuple[Waypoint, ...]
    takeoff: Takeoff
    photo_mode: PhotoMode
    photo_interval_s: float | None
    speed_ms: float
    estimated_duration_s: float

    @property
    def photo_count(self) -> int:
        return sum(1 for w in self.waypoints if w.take_photo)

    def path_length_m(self) -> float:
        pts = self.waypoints
        return sum(haversine_m(a.lon, a.lat, b.lon, b.lat) for a, b in itertools.pairwise(pts))


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Great-circle distance in metres."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(h)))
