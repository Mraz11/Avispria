# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Finding a place on the drawing map: search by name, type coordinates, or ask where we are.

Kept apart from ``plan_map`` (which draws and lists shapes). Searching sends the words typed to the
place-search service (see ``adapters/geocode``), and only when the person presses the button; asking
for the location uses the browser's own location service. Both are opt-in; nothing is sent else.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any

from nicegui import ui

from avispria.adapters.geocode import DEFAULT_SERVICE, Place, search_places
from avispria.app.ui.inputs import parse_latlon_text
from avispria.app.ui.jobs import run_job
from avispria.app.ui.pages.plan_map_text import (
    BACKGROUND_NOTE,
    OSM_ATTRIBUTION,
    OSM_URL,
    PRIVACY_NOTE,
)

SEARCH_CREDIT = "Place names: © OpenStreetMap contributors (openstreetmap.org/copyright)."

_DENIED = (
    "The browser did not allow it. Allow location for this page (the icon left of the address), "
    "and open Avispria at an address starting with http://127.0.0.1 or http://localhost."
)

LOCATION_JS = """
return await new Promise((resolve) => {
  if (!navigator.geolocation) {
    resolve({error: "This browser cannot tell where you are."});
    return;
  }
  navigator.geolocation.getCurrentPosition(
    (p) => resolve({lat: p.coords.latitude, lon: p.coords.longitude, accuracy: p.coords.accuracy}),
    (e) => resolve({error: e.code === 1 ? __DENIED__
      : e.code === 3 ? "Finding the location took too long." : "The location could not be found."}),
    {enableHighAccuracy: true, timeout: 12000, maximumAge: 60000});
});
""".replace("__DENIED__", json.dumps(_DENIED))


def looks_like_coordinates(text: str) -> bool:
    """Only digits, signs, degree marks and compass letters: coordinates, not a place name."""
    return (
        bool(re.fullmatch(r"[\s0-9.,;:°'\"+\-NSEWnsew]+", text))
        and len(re.findall(r"\d", text)) >= 2
    )


def zoom_for(place: Place) -> int:
    """A map zoom that shows the whole place (its box), or a street-level view if it has none."""
    if place.bbox is None:
        return 15
    south, west, north, east = place.bbox
    span = max(north - south, (east - west) * math.cos(math.radians((north + south) / 2)), 1e-6)
    return int(max(3, min(17, math.log2(984.0 / span))))


def _short(text: str, limit: int = 90) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _distance(metres: float) -> str:
    return f"{metres / 1000:.1f} km" if metres >= 1000 else f"{metres:.0f} m"


class PlacesMixin:
    """Search, coordinates and location for ``AreaMap`` and ``PinMap`` (which provide ``map``,
    ``add_drawn`` and the rest below)."""

    pin_name = "the takeoff point"  # what a pin made from "My location" is offered as
    map: Any
    goto: Any
    places_box: Any
    search_service: Any
    add_drawn: Any
    background: Any
    tile_url: Any
    _tile_layer: Any

    def go_to(self, text: str) -> None:
        try:
            lat, lon = parse_latlon_text(text)
        except ValueError as exc:
            ui.notify(str(exc), type="warning")
            return
        self.map.set_center((lat, lon))
        self.map.set_zoom(16)

    async def find(self) -> None:
        """Coordinates go straight there; anything else is a place name, searched for."""
        text = (self.goto.value or "").strip()
        if not text:
            ui.notify("Type a place name, or latitude and longitude.", type="warning")
            return
        if looks_like_coordinates(text):
            self.go_to(text)
            return
        self.places_box.clear()
        with self.places_box:
            ui.spinner()
            ui.label("Searching...")
        service = (self.search_service.value or "").strip()
        result = await run_job(search_places, text, service)
        self.places_box.clear()
        with self.places_box:
            if not result.ok or result.value is None:
                ui.label(result.error or "The search did not work.").classes("av-problem-text")
            elif not result.value:
                ui.label(
                    f"No place found for '{text}'. Try a bigger place name, or type coordinates."
                ).classes("av-problem-text")
            elif len(result.value) == 1:
                self.show_place(result.value[0], service)
            else:
                ui.label("Which one?").classes("font-medium")
                for n, place in enumerate(result.value):
                    ui.button(
                        _short(place.name), on_click=lambda _, p=place: self.show_place(p, service)
                    ).props("flat no-caps align=left").classes("w-full").mark(f"place-{n}")
                self._credit(service)

    def show_place(self, place: Place, service: str = "") -> None:
        """Move the map to a place found by name and say which place it is."""
        self.map.set_center((place.lat, place.lon))
        self.map.set_zoom(zoom_for(place))
        self.places_box.clear()
        with self.places_box:
            ui.label(f"Showing: {_short(place.name, 110)}").classes("text-sm")
            self._credit(service)

    @staticmethod
    def _credit(service: str) -> None:
        if not service or service.rstrip("/") == DEFAULT_SERVICE.rstrip("/"):
            ui.label(SEARCH_CREDIT).classes("text-xs av-muted")

    async def my_location(self) -> None:
        """Ask the browser where this computer is, and show it on the map."""
        self.places_box.clear()
        with self.places_box:
            ui.spinner()
            ui.label("Asking your browser for your location...")
        answer = await self._browser_location()
        self.places_box.clear()
        try:
            if not isinstance(answer, dict) or "error" in answer:
                raise ValueError(
                    answer.get("error")
                    if isinstance(answer, dict)
                    else "No answer from the browser."
                )
            self.use_location(float(answer["lat"]), float(answer["lon"]), float(answer["accuracy"]))
        except (KeyError, TypeError, ValueError) as exc:
            with self.places_box:
                ui.label(f"Your location could not be used: {exc}").classes("av-problem-text")

    async def _browser_location(self) -> Any:
        try:
            return await ui.run_javascript(LOCATION_JS, timeout=20.0)
        except TimeoutError:
            return {"error": "The browser did not answer in time."}

    def use_location(self, lat: float, lon: float, accuracy: float) -> None:
        if not (-90 <= lat <= 90 and -180 <= lon <= 180 and accuracy >= 0):
            raise ValueError("the position was not valid")
        for layer in self._here_layers:
            self.map.remove_layer(layer)
        self._here_layers = [self.map.marker(latlng=(lat, lon))]
        if accuracy >= 5:
            self._here_layers.append(
                self.map.generic_layer(
                    name="circle",
                    args=[
                        [lat, lon],
                        {"radius": accuracy, "color": "#2F7FD1", "weight": 1, "fillOpacity": 0.1},
                    ],
                )
            )
        self.map.set_center((lat, lon))
        self.map.set_zoom(16 if accuracy <= 300 else 14 if accuracy <= 3000 else 11)
        with self.places_box:
            ui.label(
                f"Your computer says it is here, to within about {_distance(accuracy)}."
            ).classes("text-sm")
            if accuracy > 1000:
                ui.label(
                    "A computer usually knows only roughly where it is (from its network). For an "
                    "exact position use the search, type coordinates, or place the pin."
                ).classes("text-sm av-muted")
            else:
                ui.button(
                    f"Use it as {self.pin_name}",
                    on_click=lambda: self.add_drawn(
                        "marker", {"_latlng": {"lat": lat, "lng": lon}}
                    ),
                ).props("no-caps flat").mark("map-takeoff-here")

    def _build_finder(self) -> None:
        """The background switch, the search row, and the search and background settings."""
        with ui.row().classes("w-full items-center gap-3"):
            self.background = ui.switch(
                "Show map background (uses the internet)", on_change=lambda _: self._background()
            ).mark("map-background")
        with ui.row().classes("w-full items-center gap-3"):
            self.goto = (
                ui.input("Find a place, or type latitude, longitude")
                .props("outlined dense")
                .classes("w-96")
                .mark("map-goto-input")
            )
            self.goto.on("keydown.enter", self.find)
            ui.button("Search", icon="search", on_click=self.find).props("no-caps outline").mark(
                "map-goto"
            )
            ui.button("My location", icon="my_location", on_click=self.my_location).props(
                "no-caps outline"
            ).mark("map-location")
        self.places_box = ui.column().classes("w-full gap-1")
        with ui.expansion("Map background and place search settings", icon="layers").classes(
            "w-full"
        ):
            self.search_service = (
                ui.input("Place search service address (empty = OpenStreetMap's)")
                .props("outlined dense")
                .classes("w-full")
                .mark("map-search-service")
            )
            self.tile_url = (
                ui.input("Tile address, like https://example.com/{z}/{x}/{y}.png")
                .props("outlined dense")
                .classes("w-full")
                .mark("map-tile-url")
            )
            ui.label(BACKGROUND_NOTE).classes("text-sm av-muted")
            ui.label(PRIVACY_NOTE).classes("text-sm av-muted")

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
