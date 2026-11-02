# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Undo, and editing a shape's corners, for the drawing map (``AreaMap`` uses this).

Editing is by clicking, because the map reports every click with its position, which is the one
thing that is certain to reach this program. To move a corner: press Edit on the shape, press the
corner's number, and click on the map where it should go. Add a corner puts a new one in the middle
of the longest side; Remove takes the chosen one away; a circle has a centre to move and a radius to
type. A rectangle whose corner is moved becomes a polygon (its corners are no longer square).

Undo goes back one change at a time, whatever it was (a drawing, a role, a delete, an edit), so a
mistake costs one click.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from nicegui import events, ui

from avispria.core.shapes import (
    DrawnShape,
    ShapeError,
    corner_points,
    delete_corner,
    insert_corner,
    move_corner,
    with_radius,
)

HISTORY_LIMIT = 50
CORNER_COLOUR = "#1B766B"
SELECTED_COLOUR = "#D1495B"

EDIT_CSS = """
.leaflet-draw-section:has(.leaflet-draw-edit-edit) { display: none !important; }
.leaflet-draw-toolbar .leaflet-draw-edit-edit,
.leaflet-draw-toolbar .leaflet-draw-edit-remove { display: none !important; }
.avispria-corner { background: transparent; border: 0; box-shadow: none; color: #ffffff;
  font-weight: 700; padding: 0; }
.avispria-corner::before { display: none; }
"""
EDIT_HELP = (
    "Pick a corner by its number, then click on the map where it should go. You can click again to "
    "move it again."
)
CIRCLE_HELP = "Pick the centre, then click on the map where it should go; the radius is typed here."


class EditingMixin:
    """Undo and corner editing. Expects the host to have ``shapes``, ``takeoff``, ``map``,
    ``_on_takeoff`` and ``_refresh``."""

    shapes: list[DrawnShape]
    takeoff: tuple[float, float] | None
    map: Any
    _on_takeoff: Callable[[str], None]
    _refresh: Callable[[], None]

    def _init_editing(self) -> None:
        self.editing: int | None = None  # the id of the shape whose corners are being edited
        self.selected: int | None = None  # the corner picked
        self._history: list[tuple[tuple[DrawnShape, ...], tuple[float, float] | None]] = []
        self._corner_layers: list[Any] = []
        self._same_change: tuple[Any, ...] | None = None
        self.undo_button: Any = None

    # ------------------------------------------------------------------------------- undo
    def _remember(self, same_change: tuple[Any, ...] | None = None) -> None:
        """Keep the state as it is now, so Undo can come back to it. Call before a change.

        Typing a number fires a change for every digit; consecutive changes with the same
        ``same_change`` key (the same field of the same shape) are one step to undo, not several.
        """
        if same_change is not None and same_change == self._same_change and self._history:
            return
        self._same_change = same_change
        self._history.append((tuple(self.shapes), self.takeoff))
        del self._history[:-HISTORY_LIMIT]

    def _forget_last(self) -> None:
        if self._history:
            self._history.pop()

    def undo(self) -> None:
        if not self._history:
            return
        shapes, takeoff = self._history.pop()
        self._same_change = None
        had = self.takeoff
        self.shapes = list(shapes)
        self.takeoff = takeoff
        if takeoff != had:
            self._on_takeoff("" if takeoff is None else f"{takeoff[1]:.6f}, {takeoff[0]:.6f}")
        if self.editing is not None and self._editing_shape() is None:
            self.editing = None
        self.selected = None
        self._refresh()

    def _sync_undo_button(self) -> None:
        if self.undo_button is not None:
            self.undo_button.set_enabled(bool(self._history))

    # ------------------------------------------------------------------------ editing state
    def _editing_shape(self) -> DrawnShape | None:
        return next((s for s in self.shapes if s.id == self.editing), None)

    def start_edit(self, shape_id: int) -> None:
        self.editing = shape_id
        self.selected = None
        self._refresh()

    def done_edit(self) -> None:
        self.editing = None
        self.selected = None
        self._refresh()

    def _stop_when_drawing(self, _: events.GenericEventArguments) -> None:
        if self.editing is not None:  # a drawing tool was picked: its clicks are not for editing
            self.done_edit()

    def select_corner(self, index: int) -> None:
        self.selected = index
        self._refresh()

    def _swap(self, shape: DrawnShape) -> None:
        self.shapes = [shape if s.id == shape.id else s for s in self.shapes]

    def _change(self, make: Callable[[DrawnShape], DrawnShape]) -> bool:
        """Apply an edit to the shape being edited, remembering the old state for Undo."""
        shape = self._editing_shape()
        if shape is None:
            return False
        try:
            new = make(shape)
        except ShapeError as exc:
            ui.notify(str(exc), type="warning")
            return False
        self._remember()
        self._swap(new)
        return True

    # --------------------------------------------------------------------------- the edits
    def _map_click(self, e: events.GenericEventArguments) -> None:
        """A click on the map moves the picked corner there (and does nothing otherwise)."""
        if self.editing is None or self.selected is None:
            return
        point = e.args.get("latlng") if isinstance(e.args, dict) else None
        try:
            lat, lon = float(point["lat"]), float(point["lng"])  # type: ignore[index]
        except (KeyError, TypeError, ValueError):
            return
        index = self.selected
        if self._change(lambda s: move_corner(s, index, lon, lat)):
            self._refresh()

    def add_corner(self) -> None:
        added: list[int] = []

        def grow(shape: DrawnShape) -> DrawnShape:
            grown, index = insert_corner(shape)
            added.append(index)
            return grown

        if self._change(grow):
            self.selected = added[0]  # ready to be moved where it belongs
            self._refresh()

    def remove_corner(self) -> None:
        if self.selected is None:
            ui.notify("Pick the corner to remove first.", type="warning")
            return
        index = self.selected
        if self._change(lambda s: delete_corner(s, index)):
            self.selected = None
            self._refresh()

    def set_radius(self, value: float | None) -> None:
        shape = self._editing_shape()
        if value is None or shape is None or value == shape.radius_m:
            return
        if self._change(lambda s: with_radius(s, float(value))):
            self._refresh()

    # --------------------------------------------------------------------------- drawing it
    def _draw_corners(self) -> None:
        """Numbered discs on the corners of the shape being edited; the picked one is red."""
        for layer in self._corner_layers:
            self.map.remove_layer(layer)
        self._corner_layers = []
        shape = self._editing_shape()
        if shape is None:
            return
        for i, (lon, lat) in enumerate(corner_points(shape)):
            picked = i == self.selected
            options = {
                "radius": 12 if picked else 10,
                "color": "#FFFFFF",
                "weight": 2,
                "fillColor": SELECTED_COLOUR if picked else CORNER_COLOUR,
                "fillOpacity": 1.0,
            }
            layer = self.map.generic_layer(name="circleMarker", args=[[lat, lon], options])
            label = "Centre" if shape.kind == "circle" else str(i + 1)
            layer.run_method(
                "bindTooltip",
                label,
                {"permanent": True, "direction": "center", "className": "avispria-corner"},
            )
            self._corner_layers.append(layer)

    def _edit_controls(self, shape: DrawnShape) -> None:
        """The controls shown under the shape being edited."""
        with ui.column().classes("w-full gap-2 pl-8"):
            ui.label(CIRCLE_HELP if shape.kind == "circle" else EDIT_HELP).classes("text-sm")
            with ui.row().classes("items-center gap-2"):
                for i in range(len(corner_points(shape))):
                    picked = i == self.selected
                    ui.button(
                        "Centre" if shape.kind == "circle" else str(i + 1),
                        on_click=lambda _, i=i: self.select_corner(i),
                    ).props(f"no-caps unelevated color={'negative' if picked else 'primary'}").mark(
                        f"corner-{shape.id}-{i}"
                    )
            with ui.row().classes("items-center gap-3"):
                if shape.kind == "circle":
                    ui.number(
                        "Radius (m)",
                        value=round(shape.radius_m, 1),
                        min=1,
                        max=5000,
                        on_change=lambda e: self.set_radius(e.value),
                    ).props("outlined dense").classes("w-36").mark("edit-radius")
                else:
                    ui.button("Add a corner", icon="add", on_click=self.add_corner).props(
                        "no-caps outline"
                    ).mark("edit-add-corner")
                    ui.button(
                        "Remove the picked corner", icon="remove", on_click=self.remove_corner
                    ).props("no-caps outline").mark("edit-remove-corner")
                ui.button("Done", icon="check", on_click=self.done_edit).props("no-caps").mark(
                    "edit-done"
                )
