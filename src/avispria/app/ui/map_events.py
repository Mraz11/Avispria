# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read what the map widget (Leaflet.draw) reports when the person draws a shape.

The widget sends the layer type and the layer's own fields: ``_latlngs`` for a polygon, rectangle or
line, ``_latlng`` (and ``_mRadius``) for a circle or marker. A point is ``{"lat": ..., "lng": ...}``
(or a ``[lat, lng]`` pair); an area's ``_latlngs`` is a list of rings (a list of lists), a line's
is a flat list. This module accepts all of those, and says plainly when a shape makes no sense.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

SUPPORTED = ("polygon", "rectangle", "circle", "polyline", "marker")


@dataclass(frozen=True)
class Drawn:
    kind: str  # polygon, rectangle, circle, line or marker
    points: tuple[tuple[float, float], ...]  # (lon, lat)
    radius_m: float = 0.0


def _point(raw: Any) -> tuple[float, float]:
    if isinstance(raw, Mapping):
        lat = raw.get("lat")
        lng = raw.get("lng", raw.get("lon"))
    elif isinstance(raw, (list, tuple)) and len(raw) >= 2:
        lat, lng = raw[0], raw[1]
    else:
        raise ValueError("a point on the map was not understood")
    try:
        return float(lng), float(lat)
    except (TypeError, ValueError):
        raise ValueError("a point on the map was not understood") from None


def _is_point(raw: Any) -> bool:
    return isinstance(raw, Mapping) or (
        isinstance(raw, (list, tuple))
        and len(raw) >= 2
        and not isinstance(raw[0], (list, tuple, Mapping))
    )


def _ring(raw: Any) -> list[tuple[float, float]]:
    """The first ring of points: an area's list of rings, or a line's flat list."""
    if not isinstance(raw, (list, tuple)) or not raw:
        raise ValueError("the shape has no points")
    while not _is_point(raw[0]):
        raw = raw[0]
        if not isinstance(raw, (list, tuple)) or not raw:
            raise ValueError("the shape has no points")
    return [_point(p) for p in raw]


def parse_layer(layer_type: str, layer: Mapping[str, Any]) -> Drawn:
    """Turn a drawn layer into a :class:`Drawn`. Raises ValueError with a plain message."""
    if layer_type not in SUPPORTED:
        raise ValueError(f"'{layer_type}' shapes cannot be used here")
    if layer_type in ("circle", "marker"):
        centre = _point(layer.get("_latlng"))
        if layer_type == "marker":
            return Drawn("marker", (centre,))
        try:
            radius = float(layer.get("_mRadius", layer.get("radius", 0.0)))
        except (TypeError, ValueError):
            radius = 0.0
        if not radius > 0:
            raise ValueError("the circle has no radius")
        return Drawn("circle", (centre,), radius)
    points = _ring(layer.get("_latlngs"))
    if layer_type == "polyline":
        return Drawn("line", tuple(points))
    if len(points) > 3 and points[0] == points[-1]:
        points = points[:-1]  # a ring that repeats its first point
    return Drawn(layer_type, tuple(points))


def event_layer(args: Mapping[str, Any]) -> tuple[str, Mapping[str, Any]]:
    """The layer type and layer of a ``draw:created`` event's arguments."""
    layer_type = args.get("layerType")
    layer = args.get("layer")
    if not isinstance(layer_type, str) or not isinstance(layer, Mapping):
        raise ValueError("the map did not say what was drawn")
    return layer_type, layer
