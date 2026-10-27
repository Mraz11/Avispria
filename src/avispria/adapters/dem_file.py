# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read the part of a GeoTIFF DEM that covers an area of interest."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import transform_bounds
from rasterio.windows import Window, from_bounds

from avispria.core.errors import PlanningError
from avispria.core.terrain import Dem

BUFFER_DEG = 0.01  # ~1 km of context around the AOI and takeoff point


def load_dem_window(path: Path, bounds_lonlat: tuple[float, float, float, float]) -> Dem:
    """Crop ``path`` to ``bounds_lonlat`` (min lon, min lat, max lon, max lat) + buffer."""
    min_lon, min_lat, max_lon, max_lat = bounds_lonlat
    buffered = (
        min_lon - BUFFER_DEG,
        min_lat - BUFFER_DEG,
        max_lon + BUFFER_DEG,
        max_lat + BUFFER_DEG,
    )
    with rasterio.open(path) as src:
        if src.crs is None:
            raise PlanningError(f"{path} has no coordinate reference system")
        crs = src.crs.to_string()
        left, bottom, right, top = transform_bounds("EPSG:4326", src.crs, *buffered)
        if (
            right <= src.bounds.left
            or left >= src.bounds.right
            or top <= src.bounds.bottom
            or bottom >= src.bounds.top
        ):
            raise PlanningError(f"{path} does not cover the survey area")
        window = from_bounds(left, bottom, right, top, transform=src.transform)
        window = window.round_offsets().round_lengths()
        window = window.intersection(Window(0, 0, src.width, src.height))
        nodata = src.nodata
        data = src.read(1, window=window).astype("float64")
        transform = src.window_transform(window)
    values = data if nodata is None else np.where(data == nodata, np.nan, data)
    t = transform
    return Dem(
        values,
        (t.a, t.b, t.c, t.d, t.e, t.f),
        "EPSG:4326" if crs in ("EPSG:4326", "OGC:CRS84") else crs,
    )
