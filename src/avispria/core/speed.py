# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Survey speed solver: the slowest of several independent limits wins."""

from __future__ import annotations

import math
from dataclasses import dataclass

from avispria.core.camera import CameraProfile


@dataclass(frozen=True)
class SpeedSolution:
    """Every limit (m/s), the chosen speed, and which limit is binding."""

    blur_ms: float
    skew_ms: float
    trigger_ms: float
    wind_ms: float
    drone_ms: float
    speed_ms: float
    binding: str
    feasible: bool


def _positive(label: str, value: float) -> None:
    if not (math.isfinite(value) and value > 0):
        raise ValueError(f"{label} must be positive, got {value!r}")


def solve_speed(
    cam: CameraProfile,
    gsd_m: float,
    shutter_s: float,
    photo_spacing_m: float,
    drone_max_ms: float,
    *,
    blur_px: float = 0.5,
    skew_px: float = 15.0,
    wind_ms: float = 0.0,
    min_speed_ms: float = 1.0,
) -> SpeedSolution:
    """Choose a ground speed that keeps blur, rolling-shutter skew and photo rate in budget.

    Limits:
      * blur: ground motion during the exposure stays under ``blur_px`` pixels;
      * skew: ground motion during sensor readout stays under ``skew_px`` pixels.
        The default (15 px) assumes rolling-shutter correction is enabled in the
        photogrammetry engine, which models this distortion; use ~1 px only if it
        is not;
      * trigger: the camera can sustain one photo per ``photo_spacing_m``;
      * wind: keep half the drone's top speed as headroom against wind;
      * drone: the aircraft's own maximum.
    If the result is below ``min_speed_ms`` the plan is reported infeasible.
    """
    for label, value in (
        ("gsd_m", gsd_m),
        ("shutter_s", shutter_s),
        ("photo_spacing_m", photo_spacing_m),
        ("drone_max_ms", drone_max_ms),
        ("blur_px", blur_px),
        ("skew_px", skew_px),
        ("min_speed_ms", min_speed_ms),
    ):
        _positive(label, value)
    if not (math.isfinite(wind_ms) and wind_ms >= 0):
        raise ValueError(f"wind_ms must be >= 0, got {wind_ms!r}")

    limits = {
        "motion blur": blur_px * gsd_m / shutter_s,
        "rolling-shutter skew": skew_px * gsd_m / cam.readout_s,
        "camera photo interval": photo_spacing_m / cam.min_interval_s,
        "wind headroom": 0.5 * drone_max_ms - wind_ms,
        "drone maximum": drone_max_ms,
    }
    binding = min(limits, key=lambda k: limits[k])
    raw = limits[binding]
    feasible = raw >= min_speed_ms
    return SpeedSolution(
        blur_ms=limits["motion blur"],
        skew_ms=limits["rolling-shutter skew"],
        trigger_ms=limits["camera photo interval"],
        wind_ms=limits["wind headroom"],
        drone_ms=drone_max_ms,
        speed_ms=raw if feasible else min_speed_ms,
        binding=binding,
        feasible=feasible,
    )
