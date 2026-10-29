# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Chart descriptions (Apache ECharts options) for the photo map and the route map.

Pure functions returning plain dictionaries, so they are tested without a browser. Both
charts use metres around the centre of the area, with equal scales on the two axes.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

from shapely.geometry import Polygon

from avispria.app.ui.theme import LIGHT, Palette
from avispria.core.capture import CaptureReport
from avispria.core.geometry import LocalFrame
from avispria.core.plan_model import PlanResult

MAX_PHOTO_DOTS = 600


def _square(xs: Sequence[float], ys: Sequence[float], pad: float = 0.08) -> dict[str, float]:
    """Axis ranges with the same span on both axes, so shapes are not distorted."""
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    half = max(max(xs) - min(xs), max(ys) - min(ys), 1.0) / 2 * (1 + pad)
    return {
        "xmin": round(cx - half, 1),
        "xmax": round(cx + half, 1),
        "ymin": round(cy - half, 1),
        "ymax": round(cy + half, 1),
    }


def _axes(box: dict[str, float], p: Palette) -> dict[str, Any]:
    def axis(name: str, low: float, high: float) -> dict[str, Any]:
        return {
            "type": "value",
            "name": name,
            "min": low,
            "max": high,
            "nameTextStyle": {"color": p.muted},
            "axisLabel": {"color": p.muted},
            "axisLine": {"lineStyle": {"color": p.border_strong}},
            "splitLine": {"lineStyle": {"color": p.border}},
        }

    return {
        "backgroundColor": "transparent",
        "textStyle": {"color": p.text},
        "xAxis": axis("metres east", box["xmin"], box["xmax"]),
        "yAxis": axis("metres north", box["ymin"], box["ymax"]),
        "grid": {"left": 60, "right": 20, "top": 30, "bottom": 50},
    }


def photo_map(report: CaptureReport, palette: Palette = LIGHT) -> dict[str, Any]:
    """Where each photo was taken, coloured by how much it overlaps its nearest neighbour."""
    photos = report.photos
    if not photos:
        return {}
    cx = sum(p.x for p in photos) / len(photos)
    cy = sum(p.y for p in photos) / len(photos)
    points = [
        {
            "name": p.name,
            "value": [round(p.x - cx, 1), round(p.y - cy, 1), round(p.best_overlap or 0.0, 3)],
        }
        for p in photos
    ]
    box = _square([v["value"][0] for v in points], [v["value"][1] for v in points])
    return {
        **_axes(box, palette),
        "tooltip": {"trigger": "item"},
        "visualMap": {
            "min": 0.3,
            "max": 0.8,
            "dimension": 2,
            "orient": "horizontal",
            "left": "center",
            "bottom": 0,
            "text": ["more overlap", "less"],
            "calculable": False,
            "textStyle": {"color": palette.muted},
            "inRange": {"color": list(palette.ramp)},
        },
        "series": [{"type": "scatter", "symbolSize": 11, "data": points}],
    }


def route_map(
    result: PlanResult,
    aoi: Polygon,
    takeoff: tuple[float, float],
    photos: Sequence[tuple[float, float]] = (),
    palette: Palette = LIGHT,
) -> dict[str, Any]:
    """The survey area, each mission's route, the takeoff point and (optionally) photo spots.

    ``takeoff`` and ``photos`` are (longitude, latitude).
    """
    frame = LocalFrame.for_polygon(aoi)
    cx, cy = (float(v[0]) for v in frame.to_local([aoi.centroid.x], [aoi.centroid.y]))

    def local(lonlat: Sequence[tuple[float, float]]) -> list[list[float]]:
        xs, ys = frame.to_local([p[0] for p in lonlat], [p[1] for p in lonlat])
        return [
            [round(float(x) - cx, 1), round(float(y) - cy, 1)] for x, y in zip(xs, ys, strict=True)
        ]

    outline = local(list(aoi.exterior.coords))
    series: list[dict[str, Any]] = [
        {
            "name": "Survey area",
            "type": "line",
            "data": outline,
            "showSymbol": False,
            "lineStyle": {"type": "dashed", "color": palette.outline, "width": 2},
        }
    ]
    every: list[list[float]] = list(outline)
    for n, mission in enumerate(result.missions):
        route = local([(w.lon, w.lat) for w in mission.waypoints])
        every += route
        series.append(
            {
                "name": f"Mission {n + 1}",
                "type": "line",
                "data": route,
                "showSymbol": False,
                "lineStyle": {"width": 3, "color": palette.missions[n % len(palette.missions)]},
            }
        )
    if photos:
        step = max(1, math.ceil(len(photos) / MAX_PHOTO_DOTS))
        series.append(
            {
                "name": "Photos",
                "type": "scatter",
                "data": local(list(photos)[::step]),
                "symbolSize": 4,
                "itemStyle": {"color": palette.points, "opacity": 0.7},
            }
        )
    series.append(
        {
            "name": "Takeoff",
            "type": "scatter",
            "data": local([takeoff]),
            "symbol": "diamond",
            "symbolSize": 16,
            "itemStyle": {"color": palette.marker},
        }
    )
    every += local([takeoff])
    box = _square([p[0] for p in every], [p[1] for p in every])
    return {
        **_axes(box, palette),
        "legend": {
            "data": [s["name"] for s in series],
            "bottom": 0,
            "textStyle": {"color": palette.text},
        },
        "tooltip": {"trigger": "item"},
        "series": series,
    }
