# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The map on the Plan a flight screen: draw shapes, give each a role, see the area that results.

The server owns the shapes. Every shape the person draws is stored here and drawn again in a colour
that shows its role, so editing is done in the list under the map (change the role, the width,
delete) and the browser's own editing state never has to be kept in step. The area that will be
planned is drawn in green on top, exactly as the planner will receive it.

The map background is a separate, optional layer: nothing is fetched from the internet unless the
person asks for it.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from nicegui import events, ui
from shapely.geometry import mapping

from avispria.app.ui.inputs import parse_latlon_text
from avispria.app.ui.map_events import event_layer, parse_layer
from avispria.core.shapes import (
    ALLOWED_ROLES,
    DEFAULT_WIDTH_M,
    AreaResult,
    DrawnShape,
    Role,
    ShapeError,
    build_area,
    shape_size,
    suggest_role,
)

OSM_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
OSM_ATTRIBUTION = (
    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
)
ROLE_LABELS = {
    Role.INSIDE: "Map inside it",
    Role.LEAVE_OUT: "Leave it out",
    Role.BAND: "Map a band around it (outside)",
    Role.CORRIDOR: "Map a strip along it",
}
ROLE_COLOURS = {
    Role.INSIDE: "#2D9A5B",
    Role.LEAVE_OUT: "#D1495B",
    Role.BAND: "#E08E2B",
    Role.CORRIDOR: "#2F7FD1",
}
KIND_ICONS = {
    "polygon": "polyline",
    "rectangle": "crop_square",
    "circle": "radio_button_unchecked",
    "line": "timeline",
}
HELP = (
    "Use the tools at the top left of the map: polygon, rectangle, circle, line, or the pin for "
    "the takeoff point. Each shape you draw appears in the list below with what it does. The "
    "area that will be planned is drawn in green."
)
BACKGROUND_NOTE = (
    "The background is OpenStreetMap, loaded from the internet only while this switch is on "
    "(their terms: openstreetmap.org/copyright). The map works without it: you then see only your "
    "shapes."
)
LEAVE_OUT_NOTE = (
    "Parts you leave out are not planned for coverage, but the aircraft may still fly over them to "
    "turn or to reach the next line. Do not rely on this for anything that must not be overflown."
)


def _latlngs(points: tuple[tuple[float, float], ...]) -> list[list[float]]:
    return [[lat, lon] for lon, lat in points]


class AreaMap:
    """The drawing map and its list of shapes; the result is ``geojson`` and ``takeoff_text``."""

    def __init__(self, on_takeoff: Callable[[str], None]) -> None:
        self.shapes: list[DrawnShape] = []
        self.takeoff: tuple[float, float] | None = None  # (lon, lat)
        self.result: AreaResult | None = None
        self.problem: str | None = "Draw the survey area on the map first."
        self.chosen = 0  # which separate area is planned now
        self._next_id = 1
        self._on_takeoff = on_takeoff
        self._shape_layers: list[Any] = []
        self._result_layers: list[Any] = []
        self._takeoff_layer: Any = None
        self._tile_layer: Any = None
        self._build()

    # ------------------------------------------------------------------ building
    def _build(self) -> None:
        ui.label(HELP).classes("text-sm av-muted")
        with ui.row().classes("w-full items-center gap-3"):
            self.background = ui.switch(
                "Show map background (uses the internet)", on_change=lambda _: self._background()
            ).mark("map-background")
            self.goto = (
                ui.input("Go to: latitude, longitude")
                .props("outlined dense")
                .classes("w-64")
                .mark("map-goto-input")
            )
            ui.button("Go", on_click=lambda: self.go_to(self.goto.value or "")).props(
                "no-caps outline"
            ).mark("map-goto")
        with ui.expansion("Use a different map background", icon="layers").classes("w-full"):
            self.tile_url = (
                ui.input("Tile address, like https://example.com/{z}/{x}/{y}.png")
                .props("outlined dense")
                .classes("w-full")
                .mark("map-tile-url")
            )
            ui.label(BACKGROUND_NOTE).classes("text-sm av-muted")
        self.map = (
            ui.leaflet(
                center=(20.0, 0.0),
                zoom=2,
                draw_control={
                    "draw": {
                        "polygon": True,
                        "rectangle": True,
                        "circle": True,
                        "polyline": True,
                        "marker": True,
                        "circlemarker": False,
                    },
                    "edit": {"remove": False},
                },
                hide_drawn_items=True,
            )
            .classes("w-full")
            .style("height: 480px")
        )
        # the widget adds an OpenStreetMap layer by itself: nothing may reach the internet unasked
        self.map.layers.clear()
        self.map.on("draw:created", self._created)
        self.summary = ui.label().classes("font-medium").mark("map-summary")
        self.notes = ui.column().classes("w-full gap-1")
        self.chooser_box = ui.row().classes("w-full items-center gap-3")
        self.list = ui.column().classes("w-full gap-2")
        with ui.row().classes("gap-3"):
            ui.button("Remove all shapes", icon="delete_sweep", on_click=self.clear).props(
                "no-caps flat"
            ).mark("map-clear")
        self._refresh()

    # ------------------------------------------------------------------- drawing
    def _created(self, e: events.GenericEventArguments) -> None:
        try:
            layer_type, layer = event_layer(e.args)
            self.add_drawn(layer_type, layer)
        except ValueError as exc:
            ui.notify(f"That shape was not used: {exc}", type="warning")

    def add_drawn(self, layer_type: str, layer: Any) -> None:
        """A shape was drawn (or, in tests, handed over): keep it and show what it does."""
        drawn = parse_layer(layer_type, layer)
        if drawn.kind == "marker":
            self.takeoff = drawn.points[0]
            lon, lat = self.takeoff
            self._on_takeoff(f"{lat:.6f}, {lon:.6f}")
        else:
            shape = DrawnShape(self._next_id, drawn.kind, drawn.points, drawn.radius_m)
            self._next_id += 1
            shape = replace(shape, role=suggest_role(shape, self.shapes))
            self.shapes.append(shape)
        self._refresh()

    def go_to(self, text: str) -> None:
        try:
            lat, lon = parse_latlon_text(text)
        except ValueError as exc:
            ui.notify(str(exc), type="warning")
            return
        self.map.set_center((lat, lon))
        self.map.set_zoom(16)

    def clear(self) -> None:
        self.shapes.clear()
        if self.takeoff is not None:
            self.takeoff = None
            self._on_takeoff("")  # the pin goes, and so must the coordinates it put in the form
        self.chosen = 0
        self._refresh()

    def _background(self) -> None:
        if self._tile_layer is not None:
            self.map.remove_layer(self._tile_layer)
            self._tile_layer = None
        if self.background.value:
            url = (self.tile_url.value or "").strip() or OSM_URL
            attribution = OSM_ATTRIBUTION if url == OSM_URL else "Map background: your own source"
            self._tile_layer = self.map.tile_layer(
                url_template=url, options={"maxZoom": 19, "attribution": attribution}
            )

    # ----------------------------------------------------------------- the result
    def _refresh(self) -> None:
        try:
            self.result = build_area(self.shapes)
            self.problem = None
        except ShapeError as exc:
            self.result = None
            self.problem = str(exc)
        if self.result is not None:
            self.chosen = min(self.chosen, len(self.result.pieces) - 1)
        self._redraw_map()
        self._render_text()
        self._render_list()

    def _redraw_map(self) -> None:
        for layer in [*self._shape_layers, *self._result_layers]:
            self.map.remove_layer(layer)
        self._shape_layers, self._result_layers = [], []
        for shape in self.shapes:
            style = {
                "color": ROLE_COLOURS[shape.role],
                "weight": 2,
                "dashArray": "6",
                "fill": False,
            }
            if shape.kind == "circle":
                centre = _latlngs(shape.points)[0]
                layer = self.map.generic_layer(
                    name="circle", args=[centre, {**style, "radius": shape.radius_m}]
                )
            elif shape.kind == "line":
                layer = self.map.generic_layer(
                    name="polyline", args=[_latlngs(shape.points), style]
                )
            else:
                layer = self.map.generic_layer(name="polygon", args=[_latlngs(shape.points), style])
            self._shape_layers.append(layer)
        if self.result is not None:
            for n, piece in enumerate(self.result.pieces):
                rings = [
                    list(piece.polygon.exterior.coords),
                    *(list(r.coords) for r in piece.polygon.interiors),
                ]
                latlngs = [[[lat, lon] for lon, lat in ring] for ring in rings]
                style = {
                    "color": "#1B766B",
                    "weight": 3 if n == self.chosen else 1,
                    "fillColor": "#2D9A5B",
                    "fillOpacity": 0.3 if n == self.chosen else 0.12,
                }
                self._result_layers.append(
                    self.map.generic_layer(name="polygon", args=[latlngs, style])
                )
        if self._takeoff_layer is not None:
            self.map.remove_layer(self._takeoff_layer)
            self._takeoff_layer = None
        if self.takeoff is not None:
            self._takeoff_layer = self.map.marker(latlng=(self.takeoff[1], self.takeoff[0]))

    def _render_text(self) -> None:
        if self.result is None:
            self.summary.set_text(self.problem or "")
            self.summary.classes(add="av-problem-text", remove="av-ok-text")
        else:
            total = sum(p.area_m2 for p in self.result.pieces)
            pieces = len(self.result.pieces)
            text = f"Area to map: {_area_text(total)}"
            if pieces > 1:
                text += f", in {pieces} separate pieces (one is planned at a time)"
            self.summary.set_text(text)
            self.summary.classes(add="av-ok-text", remove="av-problem-text")
        self.notes.clear()
        with self.notes:
            if self.result is not None and self.result.dropped_m2 > 0:
                ui.label(
                    f"{_area_text(self.result.dropped_m2)} was left out: too small to fly."
                ).classes("text-sm av-muted")
            if any(s.role == Role.LEAVE_OUT for s in self.shapes):
                ui.label(LEAVE_OUT_NOTE).classes("text-sm av-muted")
        self.chooser_box.clear()
        with self.chooser_box:
            if self.result is not None and len(self.result.pieces) > 1:
                options = {
                    n: f"Piece {n + 1}: {_area_text(p.area_m2)}"
                    for n, p in enumerate(self.result.pieces)
                }
                ui.select(
                    options,
                    value=self.chosen,
                    label="Plan this piece now",
                    on_change=lambda e: self._choose(e.value),
                ).props("outlined dense").classes("w-72").mark("map-piece")

    def _choose(self, index: int) -> None:
        self.chosen = int(index)
        self._redraw_map()

    def _render_list(self) -> None:
        self.list.clear()
        with self.list:
            for shape in self.shapes:
                self._row(shape)
            if self.takeoff is not None:
                lon, lat = self.takeoff
                with ui.row().classes("w-full items-center gap-3"):
                    ui.icon("flight_takeoff")
                    ui.label(f"Takeoff point: {lat:.6f}, {lon:.6f}").classes("font-medium")
                    ui.button("Remove", on_click=self._remove_takeoff).props("no-caps flat").mark(
                        "map-remove-takeoff"
                    )

    def _row(self, shape: DrawnShape) -> None:
        with ui.row().classes("w-full items-center gap-3"):
            ui.icon(KIND_ICONS.get(shape.kind, "crop_square")).style(
                f"color: {ROLE_COLOURS[shape.role]}"
            )
            ui.label(shape.label).classes("font-medium w-28")
            ui.select(
                {r: ROLE_LABELS[r] for r in ALLOWED_ROLES[shape.kind]},
                value=shape.role,
                on_change=lambda e, i=shape.id: self.set_role(i, Role(e.value)),
            ).props("outlined dense").classes("w-72").mark(f"shape-role-{shape.id}")
            if shape.role in (Role.BAND, Role.CORRIDOR):
                ui.number(
                    "Width (m)",
                    value=shape.width_m,
                    min=1,
                    max=2000,
                    on_change=lambda e, i=shape.id: self.set_width(i, e.value),
                ).props("outlined dense").classes("w-32").mark(f"shape-width-{shape.id}")
            value, unit = _safe_size(shape)
            ui.label(_area_text(value) if unit == "m2" else f"{value:,.0f} m long").classes(
                "text-sm av-muted"
            )
            ui.button(icon="delete", on_click=lambda i=shape.id: self.delete(i)).props(
                "flat round"
            ).mark(f"shape-delete-{shape.id}")

    # ------------------------------------------------------------------ editing
    def _replace(self, shape_id: int, **changes: Any) -> None:
        self.shapes = [replace(s, **changes) if s.id == shape_id else s for s in self.shapes]
        self._refresh()

    def set_role(self, shape_id: int, role: Role) -> None:
        self._replace(shape_id, role=role)

    def set_width(self, shape_id: int, width: float | None) -> None:
        if width is not None and width > 0:
            self._replace(shape_id, width_m=float(width))

    def delete(self, shape_id: int) -> None:
        self.shapes = [s for s in self.shapes if s.id != shape_id]
        self._refresh()

    def _remove_takeoff(self) -> None:
        self.takeoff = None
        self._on_takeoff("")
        self._refresh()

    # ---------------------------------------------------------------- the result
    def geojson(self) -> str:
        """The area to plan now, as GeoJSON; empty if there is nothing (see ``problem``)."""
        if self.result is None:
            return ""
        return json.dumps(mapping(self.result.pieces[self.chosen].polygon))

    def takeoff_text(self) -> str:
        if self.takeoff is None:
            return ""
        return f"{self.takeoff[1]:.6f}, {self.takeoff[0]:.6f}"


def _area_text(m2: float) -> str:
    return f"{m2 / 10_000:.2f} ha ({m2:,.0f} m²)" if m2 >= 10_000 else f"{m2:,.0f} m²"


def _safe_size(shape: DrawnShape) -> tuple[float, str]:
    try:
        return shape_size(shape)
    except ShapeError:
        return 0.0, "m2"


__all__ = ["DEFAULT_WIDTH_M", "AreaMap"]
