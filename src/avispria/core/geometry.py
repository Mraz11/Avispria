# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Area-of-interest parsing and a local metric (UTM) frame."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

import numpy as np
import shapely
from numpy.typing import ArrayLike, NDArray
from pyproj import Transformer
from shapely.geometry import Polygon, shape

FloatArray = NDArray[np.float64]

MAX_ABS_LAT = 80.0  # UTM is defined between 80 S and 84 N; stay conservative


class AoiError(ValueError):
    """The supplied area of interest cannot be planned."""


def _extract_geometry(obj: Mapping[str, Any]) -> Mapping[str, Any]:
    kind = obj.get("type")
    if kind == "FeatureCollection":
        features = obj.get("features") or []
        if len(features) != 1:
            raise AoiError(f"expected exactly one feature, found {len(features)}")
        return _extract_geometry(features[0])
    if kind == "Feature":
        geometry = obj.get("geometry")
        if not isinstance(geometry, Mapping):
            raise AoiError("feature has no geometry")
        return geometry
    return obj


def load_aoi(geojson: Mapping[str, Any]) -> Polygon:
    """Parse a GeoJSON Polygon / Feature / single-feature FeatureCollection (lon, lat)."""
    geometry = _extract_geometry(geojson)
    if geometry.get("type") != "Polygon":
        raise AoiError(f"AOI must be a single Polygon, got {geometry.get('type')!r}")
    try:
        poly = shape(dict(geometry))
    except Exception as exc:  # shapely raises several types for malformed input
        raise AoiError(f"invalid polygon coordinates: {exc}") from exc
    if not isinstance(poly, Polygon) or poly.is_empty:
        raise AoiError("AOI polygon is empty")
    minx, miny, maxx, maxy = poly.bounds
    if minx < -180 or maxx > 180 or miny < -MAX_ABS_LAT or maxy > MAX_ABS_LAT:
        raise AoiError("AOI coordinates must be lon in [-180, 180], lat in [-80, 80]")
    if maxx - minx > 3.0:
        raise AoiError("AOI is wider than 3 degrees of longitude; split it first")
    if not poly.is_valid:
        raise AoiError("AOI polygon is not valid (self-intersecting or malformed)")
    if poly.area <= 0:
        raise AoiError("AOI polygon has zero area")
    return poly


def utm_crs_for(lon: float, lat: float) -> str:
    """EPSG code of the UTM zone containing (lon, lat)."""
    zone = min(math.floor((lon + 180.0) / 6.0) + 1, 60)
    return f"EPSG:{32600 + zone if lat >= 0 else 32700 + zone}"


class LocalFrame:
    """Converts between WGS84 lon/lat and a metric UTM frame."""

    def __init__(self, crs: str) -> None:
        self.crs = crs
        self._fwd = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
        self._inv = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)

    @classmethod
    def for_polygon(cls, poly: Polygon) -> LocalFrame:
        c = poly.centroid
        return cls(utm_crs_for(c.x, c.y))

    def to_local(self, lons: ArrayLike, lats: ArrayLike) -> tuple[FloatArray, FloatArray]:
        xs, ys = self._fwd.transform(np.asarray(lons, float), np.asarray(lats, float))
        return np.asarray(xs, float), np.asarray(ys, float)

    def to_lonlat(self, xs: ArrayLike, ys: ArrayLike) -> tuple[FloatArray, FloatArray]:
        lons, lats = self._inv.transform(np.asarray(xs, float), np.asarray(ys, float))
        return np.asarray(lons, float), np.asarray(lats, float)

    def polygon_to_local(self, poly: Polygon) -> Polygon:
        def forward(coords: FloatArray) -> FloatArray:
            xs, ys = self._fwd.transform(coords[:, 0], coords[:, 1])
            return np.column_stack([xs, ys])

        result = shapely.transform(poly, forward)
        if not isinstance(result, Polygon):
            raise AoiError("projection did not return a polygon")
        return result
