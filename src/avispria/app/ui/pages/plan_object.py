# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The cards for 'a 3D model of one object': where it is, how big, and the rings around it."""

from __future__ import annotations

from nicegui import ui

from avispria.app.ui.pages.plan_form_parts import card, number, text
from avispria.app.ui.pages.plan_pin_map import PinMap

KINDS = ("object_3d",)
WHERE_HELP = (
    "The position is the object's axis: for a tree, its trunk. Place a pin on the map, or type "
    "latitude and longitude. The height is from the ground at its foot to its top; the radius is "
    "the widest distance from the axis to its edge (a crown, a building's corner)."
)
RINGS_HELP = (
    "The drone flies rings around the object at the distance below, from the lowest height up to "
    "the top, always facing it. Closer is sharper but riskier: under 5 m is refused, under 10 m "
    "warned. The camera tilts up at the bottom and down at the top so it keeps looking at the "
    "object."
)


class ObjectCards:
    """The two object cards. ``PlanFormUi`` builds them after the type chooser."""

    scan_type: ui.radio

    def _object_where_card(self) -> None:
        with card("2. Where: the object", radio=self.scan_type, kinds=KINDS):
            ui.label(WHERE_HELP).classes("text-sm av-muted")
            self.object_centre = text(
                "Position of the object: latitude, longitude",
                "object-centre-input",
                placeholder="12.3456, 98.7654",
            )
            self.pin_map: PinMap | None = None
            self._pin_box = ui.column().classes("w-full")
            self._pin_button = (
                ui.button("Place it on a map", icon="map", on_click=self._open_pin_map)
                .props("no-caps outline")
                .mark("object-open-map")
            )
            with ui.row().classes("gap-3"):
                self.object_height = number(
                    "Height of the object (m)", 15.0, "object-height-input", "w-64", min=1, max=300
                )
                self.object_radius = number(
                    "Widest radius (m)", 5.0, "object-radius-input", "w-56", min=0.5, max=100
                )
            self.object_takeoff = text(
                "Takeoff point: latitude, longitude (empty = south of the object, outside)",
                "object-takeoff-input",
            )

    def _open_pin_map(self) -> None:
        """Build the pin map the first time it is wanted (a map made while hidden draws wrongly)."""
        if self.pin_map is None:
            self._pin_button.set_visibility(False)
            with self._pin_box:
                self.pin_map = PinMap(on_pin=lambda value: self.object_centre.set_value(value))

    def _object_settings_card(self) -> None:
        with card("4. Settings: the rings", radio=self.scan_type, kinds=KINDS):
            ui.label(RINGS_HELP).classes("text-sm av-muted")
            with ui.row().classes("gap-3"):
                self.standoff = number(
                    "Distance from the object (m)", 14.0, "standoff-input", "w-64", min=3, max=100
                )
                self.base_height = number(
                    "Lowest height to photograph (m)",
                    0.0,
                    "base-height-input",
                    "w-72",
                    min=0,
                    max=300,
                )
                self.ground_offset = number(
                    "Ground at the object, above takeoff (m)",
                    0.0,
                    "ground-offset-input",
                    "w-80",
                    min=-100,
                    max=300,
                )
            with ui.row().classes("gap-3"):
                self.obj_front = number(
                    "Overlap around a ring (%)", 80.0, "obj-front-input", "w-60", min=10, max=95
                )
                self.obj_side = number(
                    "Overlap between rings (%)", 70.0, "obj-side-input", "w-60", min=10, max=95
                )
            with ui.row().classes("gap-3"):
                self.look_up = number(
                    "Camera looks up at the bottom by (degrees)",
                    10.0,
                    "look-up-input",
                    "w-96",
                    min=0,
                    max=40,
                )
                self.look_down = number(
                    "Camera looks down at the top by (degrees)",
                    20.0,
                    "look-down-input",
                    "w-96",
                    min=0,
                    max=90,
                )
            with ui.row().classes("gap-3"):
                self.hover = number(
                    "Stand still at each photo (s)", 1.0, "hover-input", "w-72", min=0, max=10
                )
                self.scan_speed = number(
                    "Flying speed (m/s)", 3.0, "scan-speed-input", "w-48", min=0.5, max=12
                )
            self.top_cap = ui.switch("A few photos straight down over the top", value=True).mark(
                "top-cap-switch"
            )
