# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A small map for placing ONE pin, for example on the tree or building to be scanned.

It has the same finder as the area map (search a place, type coordinates, use my location, an
optional background), and the pin's position goes to the form as ``latitude, longitude``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from nicegui import events, ui

from avispria.app.ui.map_events import event_layer, parse_layer
from avispria.app.ui.pages.plan_map_edit import EDIT_CSS
from avispria.app.ui.pages.plan_map_places import PlacesMixin


class PinMap(PlacesMixin):
    pin_name = "the object's position"

    def __init__(self, on_pin: Callable[[str], None], what: str = "the object") -> None:
        self._on_pin = on_pin
        self.pin: tuple[float, float] | None = None  # (lon, lat)
        self._pin_layer: Any = None
        self._tile_layer: Any = None
        self._here_layers: list[Any] = []
        self._build(what)

    def _build(self, what: str) -> None:
        ui.add_css(EDIT_CSS)  # Leaflet's own edit tool cannot work here
        ui.label(
            f"Use the pin tool at the top left of the map (the last button) to mark {what}. "
            "You can search for the place or use your location first."
        ).classes("text-sm av-muted")
        self._build_finder()
        self.map = (
            ui.leaflet(
                center=(20.0, 0.0),
                zoom=2,
                draw_control={
                    "draw": {
                        "polygon": False,
                        "rectangle": False,
                        "circle": False,
                        "polyline": False,
                        "marker": True,
                        "circlemarker": False,
                    },
                    "edit": {"remove": False},
                },
                hide_drawn_items=True,
            )
            .classes("w-full")
            .style("height: 380px")
        )
        self.map.layers.clear()  # nothing may reach the internet unasked
        self.map.on("draw:created", self._created)
        with ui.row().classes("items-center gap-3"):
            self.status = ui.label("No pin yet.").classes("text-sm").mark("pin-status")
            ui.button("Remove the pin", icon="delete", on_click=self.remove).props(
                "no-caps flat"
            ).mark("pin-remove")

    def _created(self, e: events.GenericEventArguments) -> None:
        try:
            layer_type, layer = event_layer(e.args)
            self.add_drawn(layer_type, layer)
        except ValueError as exc:
            ui.notify(f"That was not used: {exc}", type="warning")

    def add_drawn(self, layer_type: str, layer: Any) -> None:
        """A pin was placed (or, in tests, handed over). A second pin replaces the first."""
        drawn = parse_layer(layer_type, layer)
        if drawn.kind != "marker":
            ui.notify("Only the pin is used here: it marks the position.", type="warning")
            return
        self.set_pin(*drawn.points[0])

    def set_pin(self, lon: float, lat: float) -> None:
        self.pin = (lon, lat)
        self._show()
        self._on_pin(f"{lat:.6f}, {lon:.6f}")

    def remove(self) -> None:
        self.pin = None
        self._show()
        self._on_pin("")

    def _show(self) -> None:
        if self._pin_layer is not None:
            self.map.remove_layer(self._pin_layer)
            self._pin_layer = None
        if self.pin is None:
            self.status.set_text("No pin yet.")
            return
        lon, lat = self.pin
        self._pin_layer = self.map.marker(latlng=(lat, lon))
        self.status.set_text(f"Pin at {lat:.6f}, {lon:.6f}")
