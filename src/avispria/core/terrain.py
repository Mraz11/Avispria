# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""In-memory elevation model: bilinear sampling and extreme-value filters.

``transform`` uses the rasterio/GDAL affine order (a, b, c, d, e, f):
x = c + a * col + b * row,  y = f + d * col + e * row  (pixel corner convention).
Missing data is NaN and is never silently filled.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from numpy.typing import ArrayLike, NDArray

FloatArray = NDArray[np.float64]
Affine6 = tuple[float, float, float, float, float, float]

METRES_PER_DEGREE = 111_320.0
GEOGRAPHIC_CRS = {"EPSG:4326", "OGC:CRS84", "EPSG:4979"}


@dataclass(frozen=True, eq=False)
class Dem:
    """A north-up elevation grid in a single CRS."""

    data: FloatArray
    transform: Affine6
    crs: str

    def __post_init__(self) -> None:
        a, b, _c, d, e, _f = self.transform
        if b != 0.0 or d != 0.0:
            raise ValueError("rotated or sheared rasters are not supported")
        if a == 0.0 or e == 0.0:
            raise ValueError("pixel size must be non-zero")
        if self.data.ndim != 2 or min(self.data.shape) < 1:
            raise ValueError("DEM data must be a non-empty 2-D array")

    @property
    def is_geographic(self) -> bool:
        return self.crs.upper() in GEOGRAPHIC_CRS

    def sample(self, xs: ArrayLike, ys: ArrayLike) -> FloatArray:
        """Bilinear elevation at (xs, ys) in the DEM CRS; NaN outside or near no-data."""
        a, _b, c, _d, e, f = self.transform
        x = np.asarray(xs, dtype=float)
        y = np.asarray(ys, dtype=float)
        rows, cols = self.data.shape
        col = (x - c) / a - 0.5
        row = (y - f) / e - 0.5
        inside = (col >= -0.5) & (col <= cols - 0.5) & (row >= -0.5) & (row <= rows - 0.5)
        col = np.clip(col, 0.0, cols - 1.0)
        row = np.clip(row, 0.0, rows - 1.0)
        c0 = np.minimum(np.floor(col).astype(int), max(cols - 2, 0))
        r0 = np.minimum(np.floor(row).astype(int), max(rows - 2, 0))
        c1 = np.minimum(c0 + 1, cols - 1)
        r1 = np.minimum(r0 + 1, rows - 1)
        tc = col - c0
        tr = row - r0
        z = self.data
        top = z[r0, c0] * (1 - tc) + z[r0, c1] * tc
        bottom = z[r1, c0] * (1 - tc) + z[r1, c1] * tc
        value = top * (1 - tr) + bottom * tr
        return np.where(inside, value, np.nan)

    def pixel_size_m(self, lat: float) -> tuple[float, float]:
        """Approximate pixel (width, height) in metres at latitude ``lat``."""
        a, _b, _c, _d, e, _f = self.transform
        if self.is_geographic:
            return (
                abs(a) * METRES_PER_DEGREE * math.cos(math.radians(lat)),
                abs(e) * METRES_PER_DEGREE,
            )
        return abs(a), abs(e)


def window_radius_px(dem: Dem, radius_m: float, lat: float) -> tuple[int, int]:
    """Filter half-widths (x, y) in pixels that cover at least ``radius_m``."""
    if radius_m < 0:
        raise ValueError("radius_m must be >= 0")
    px, py = dem.pixel_size_m(lat)
    return math.ceil(radius_m / px - 1e-9), math.ceil(radius_m / py - 1e-9)


def _filter_axis(values: FloatArray, radius: int, axis: int, mode: str) -> FloatArray:
    if radius == 0:
        return values
    fill = -np.inf if mode == "max" else np.inf
    pad = [(0, 0), (0, 0)]
    pad[axis] = (radius, radius)
    padded = np.pad(values, pad, constant_values=fill)
    windows = sliding_window_view(padded, 2 * radius + 1, axis=axis)
    reducer = np.max if mode == "max" else np.min
    return np.asarray(reducer(windows, axis=-1), dtype=float)


def filter_extreme(dem: Dem, rx: int, ry: int, mode: Literal["max", "min"]) -> Dem:
    """Rectangular max (dilation) or min (erosion) filter, ignoring NaN cells."""
    if rx < 0 or ry < 0:
        raise ValueError("filter radii must be >= 0")
    fill = -np.inf if mode == "max" else np.inf
    values = np.where(np.isnan(dem.data), fill, dem.data)
    values = _filter_axis(values, rx, axis=1, mode=mode)
    values = _filter_axis(values, ry, axis=0, mode=mode)
    values = np.where(np.isinf(values), np.nan, values)
    return Dem(values, dem.transform, dem.crs)
