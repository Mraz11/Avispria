# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Waypoint heights along a flight path, with or without a terrain model."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from pyproj import Transformer

from avispria.core.clearance import along_track_envelope, enforce_slope, fit_profile
from avispria.core.errors import PlanningError
from avispria.core.terrain import Dem, filter_extreme, window_radius_px

FloatArray = NDArray[np.float64]


@dataclass(frozen=True)
class TerrainOptions:
    """How conservatively terrain is followed."""

    dilation_radius_m: float = 30.0  # max-filter radius: obstacles near the line count
    ground_radius_m: float = 30.0  # min-filter radius: estimate of ground under canopy
    max_slope: float = 0.5  # climb/descent rise over run
    max_excess_m: float = 5.0  # allowed extra height between waypoints (GSD consistency)
    sample_step_m: float = 5.0  # path sampling interval
    takeoff_search_radius_m: float = 45.0  # for the conservative takeoff elevation
    # DJI Fly flies curved routes, and DJI's Lito X1 manual warns the aircraft can
    # drop below waypoint altitudes between waypoints. Extra margin until measured.
    curve_dip_margin_m: float = 10.0
    along_track_window_m: float = 30.0  # smooths the requirement; never lowers it
    lift_m: float = 3.0  # small dips are fixed by lifting segment ends, not new waypoints


@dataclass(frozen=True, eq=False)
class HeightProfile:
    """Per-sample heights (relative to takeoff) and the samples kept as waypoints."""

    keep: list[int]
    height_rel_m: FloatArray  # requirement-shaped height at every sample
    keep_height_rel_m: FloatArray  # final height of each kept waypoint (>= height_rel_m)
    surface_clearance_m: FloatArray | None
    above_ground_m: FloatArray | None
    takeoff_elevation_m: float | None
    takeoff_elevation_source: str
    terrain_source: str


def flat_profile(n_samples: int, mandatory: Sequence[int], agl_m: float) -> HeightProfile:
    """Constant height above the takeoff point (explicitly requested flat terrain)."""
    keep = sorted({0, n_samples - 1, *mandatory})
    return HeightProfile(
        keep=keep,
        height_rel_m=np.full(n_samples, float(agl_m)),
        keep_height_rel_m=np.full(len(keep), float(agl_m)),
        surface_clearance_m=None,
        above_ground_m=None,
        takeoff_elevation_m=None,
        takeoff_elevation_source="flat terrain (no DEM)",
        terrain_source="none (flat terrain assumed)",
    )


def _to_dem_crs(dem: Dem, lons: FloatArray, lats: FloatArray) -> tuple[FloatArray, FloatArray]:
    if dem.is_geographic:
        return lons, lats
    xs, ys = Transformer.from_crs("EPSG:4326", dem.crs, always_xy=True).transform(lons, lats)
    return np.asarray(xs, float), np.asarray(ys, float)


def _takeoff_elevation(dem: Dem, lon: float, lat: float, radius_m: float) -> tuple[float, str]:
    rx, ry = window_radius_px(dem, radius_m, lat)
    lowest = filter_extreme(dem, rx, ry, "min")
    x, y = _to_dem_crs(dem, np.array([lon]), np.array([lat]))
    value = float(lowest.sample(x, y)[0])
    if np.isnan(value):
        raise PlanningError("DEM has no data at the takeoff point; pass the takeoff elevation")
    return value, f"DEM minimum within {radius_m:.0f} m of takeoff (conservative)"


def terrain_profile(
    dem: Dem,
    lons: FloatArray,
    lats: FloatArray,
    d: FloatArray,
    mandatory: Sequence[int],
    agl_m: float,
    takeoff: tuple[float, float],
    takeoff_elevation_m: float | None,
    opts: TerrainOptions,
) -> HeightProfile:
    """Follow the dilated surface at ``agl_m`` with slope limits and segment clearance."""
    lat_ref = float(np.mean(lats))
    high = filter_extreme(dem, *window_radius_px(dem, opts.dilation_radius_m, lat_ref), "max")
    low = filter_extreme(dem, *window_radius_px(dem, opts.ground_radius_m, lat_ref), "min")
    x, y = _to_dem_crs(dem, lons, lats)
    surface = high.sample(x, y)
    ground = low.sample(x, y)
    missing = np.isnan(surface) | np.isnan(ground)
    if np.any(missing):
        i = int(np.argmax(missing))
        raise PlanningError(
            f"DEM has no data along the flight path near lon {lons[i]:.6f}, lat {lats[i]:.6f}"
        )
    if takeoff_elevation_m is None:
        elevation, source = _takeoff_elevation(dem, *takeoff, opts.takeoff_search_radius_m)
    else:
        elevation, source = float(takeoff_elevation_m), "user supplied"
    required = surface + agl_m + opts.curve_dip_margin_m - elevation
    envelope = along_track_envelope(d, required, opts.along_track_window_m)
    shaped = enforce_slope(d, envelope, opts.max_slope)
    keep, keep_heights = fit_profile(
        d, shaped, mandatory, opts.max_excess_m, lift_m=opts.lift_m, max_slope=opts.max_slope
    )
    return HeightProfile(
        keep=keep,
        height_rel_m=shaped,
        keep_height_rel_m=keep_heights,
        surface_clearance_m=keep_heights + elevation - surface[keep],
        above_ground_m=keep_heights + elevation - ground[keep],
        takeoff_elevation_m=elevation,
        takeoff_elevation_source=source,
        terrain_source=(
            f"DEM ({dem.crs}), dilated {opts.dilation_radius_m:.0f} m, "
            f"curve margin {opts.curve_dip_margin_m:.0f} m"
        ),
    )
