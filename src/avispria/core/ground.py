# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Height of each photo above the surface beneath it, from an elevation model.

Two ways to relate the model to the photos, because the heights a drone records and
the heights in a model do not always share a reference (ellipsoid, sea level, takeoff):

* ``takeoff`` (preferred for any external model): the photo's height above takeoff plus
  the model's elevation at the takeoff point, minus the model's elevation under the
  photo. Only differences within the model matter, so its absolute accuracy and datum
  are irrelevant (the same idea as the planner's relative-to-start-point heights).
* ``absolute``: the photo's recorded altitude minus the model's elevation. Correct only
  when both use the same reference, e.g. the surface model made from these very photos
  by the processing engine. A plausibility check rejects models that clearly do not.

The surface under the camera (nadir point) is used; footprints on steep slopes are only
first-order accurate.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from avispria.core.photo import PhotoRecord
from avispria.core.safety import Issue
from avispria.core.terrain import Dem

MIN_AGL_M = 2.0  # a photo this close to (or under) the surface is not trusted
MAX_LOW_SHARE = 0.10  # more photos than this "below ground" means the model is mismatched
MAX_RATIO = 3.0  # median height above ground within this factor of the median height above takeoff

Mode = Literal["takeoff", "absolute", "ignored"]


@dataclass(frozen=True)
class GroundHeights:
    agl_m: dict[str, float]  # photo name -> height above the surface beneath it
    mode: Mode
    fallback: list[str] = field(default_factory=list)  # photos that kept their relative altitude
    issues: list[Issue] = field(default_factory=list)
    takeoff_elevation_m: float | None = None


def _ignored(reason: str, names: list[str], code: str = "QA011") -> GroundHeights:
    level: Literal["error", "warning"] = "error" if code == "QA012" else "warning"
    return GroundHeights({}, "ignored", names, [Issue(level, code, reason)])


def heights_above_ground(
    records: Sequence[PhotoRecord], dem: Dem, takeoff: tuple[float, float] | None = None
) -> GroundHeights:
    """Per-photo height above the surface. ``takeoff`` is (longitude, latitude)."""
    located = [r for r in records if r.lat is not None and r.lon is not None]
    names = [r.name for r in located]
    lons = np.array([r.lon for r in located], dtype=float)
    lats = np.array([r.lat for r in located], dtype=float)
    ground = dem.sample_lonlat(lons, lats)

    z0: float | None = None
    if takeoff is not None:
        z0 = float(dem.sample_lonlat([takeoff[0]], [takeoff[1]])[0])
        if not np.isfinite(z0):
            return _ignored(
                "the takeoff point is outside the elevation model (or on no-data); "
                "terrain was not used",
                names,
                "QA012",
            )
        mode: Mode = "takeoff"
        camera = np.array(
            [
                np.nan if r.relative_altitude_m is None else r.relative_altitude_m + z0
                for r in located
            ]
        )
    else:
        mode = "absolute"
        camera = np.array(
            [np.nan if r.absolute_altitude_m is None else r.absolute_altitude_m for r in located]
        )
        if not np.isfinite(camera).any():
            return _ignored(
                "the photos carry no absolute altitude; give the takeoff point (--takeoff) so "
                "the elevation model can be used",
                names,
            )

    agl = camera - ground
    finite = np.isfinite(agl)
    valid = finite & (agl >= MIN_AGL_M)

    if mode == "absolute" and finite.any():
        low_share = float(np.mean(agl[finite] < MIN_AGL_M))
        rel = [r.relative_altitude_m for r in located if r.relative_altitude_m]
        spread = (
            float(np.median(agl[valid])) / statistics.median(rel) if rel and valid.any() else None
        )
        if low_share > MAX_LOW_SHARE or (
            spread is not None and not 1 / MAX_RATIO <= spread <= MAX_RATIO
        ):
            return _ignored(
                "the elevation model seems to use a different height reference than the photos "
                f"({low_share:.0%} of photos would be below the ground); pass the takeoff point "
                "(--takeoff) so only height differences are used",
                names,
            )

    heights = {n: float(a) for n, a, ok in zip(names, agl, valid, strict=True) if ok}
    fallback = [n for n, ok in zip(names, valid, strict=True) if not ok]
    issues: list[Issue] = []
    if fallback and heights:
        issues.append(
            Issue(
                "warning",
                "QA013",
                f"{len(fallback)} of {len(names)} photos are outside the elevation model or "
                "too close to it; their height above takeoff was used instead",
            )
        )
    if not heights:
        return _ignored(
            "no photo could be related to the elevation model; terrain was not used", names
        )
    return GroundHeights(heights, mode, fallback, issues, z0)
