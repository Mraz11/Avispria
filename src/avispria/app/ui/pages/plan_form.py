# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The Plan a flight form: the widgets, and how they become a plain ``PlanForm``."""

from __future__ import annotations

from nicegui import ui

from avispria.adapters.profiles import DroneProfile
from avispria.app.ui.pages.plan_results import FLY_FILE_HELP
from avispria.app.ui.plan_job import PlanForm
from avispria.app.ui.state import STATE
from avispria.app.ui.widgets import PathField


def _card(title: str) -> ui.column:
    with ui.card().classes("w-full"):
        ui.label(title).classes("text-lg font-bold")
        return ui.column().classes("w-full gap-3")


def _number(
    label: str, value: float, marker: str, width: str = "w-40", **limits: float
) -> ui.number:
    field = ui.number(label, value=value, **limits).props("outlined dense").mark(marker)
    return field.classes(width)


def _text(label: str, marker: str, value: str = "", width: str = "w-full", **kw: str) -> ui.input:
    field = ui.input(label, value=value, **kw).props("outlined dense").classes(width)
    return field.mark(marker)


def _show_when(mode: ui.radio, wanted: str, gap: str = "gap-3") -> ui.column:
    """A column that is only visible while the radio group has the value ``wanted``."""
    column = ui.column().classes(f"w-full {gap}")
    column.bind_visibility_from(mode, "value", backward=lambda v: v == wanted)
    return column


class PlanFormUi:
    """Builds the five cards of the form; ``collect`` reads them into a ``PlanForm``."""

    def __init__(self, profiles: dict[str, DroneProfile]) -> None:
        self.profiles = profiles
        names = {key: p.name for key, p in profiles.items()}
        self.first = "lito-x1" if "lito-x1" in names else next(iter(names))
        self._area_card()
        self._drone_card(names)
        self._wants_card()
        self._ground_card()
        self._save_card()
        self._advanced()

    # ---------------------------------------------------------------- 1. the area
    def _area_card(self) -> None:
        with _card("1. The survey area"):
            self.mode = (
                ui.radio(
                    {"numbers": "Describe it with numbers", "file": "Use a map file"},
                    value="numbers",
                )
                .props("inline")
                .mark("area-mode")
            )
            with _show_when(self.mode, "numbers"):
                self.centre = _text(
                    "Centre of the area: latitude, longitude",
                    "centre-input",
                    placeholder="23.8103, 90.4125",
                )
                with ui.row().classes("gap-3"):
                    self.width = _number("Width (m)", 200.0, "width-input", min=5, max=5000)
                    self.length = _number("Length (m)", 300.0, "length-input", min=5, max=5000)
                    self.area_heading = _number(
                        "Direction of the long side (degrees, 0 = north)",
                        0.0,
                        "area-heading-input",
                        "w-72",
                        min=0,
                        max=360,
                    )
            with _show_when(self.mode, "file", gap="gap-1"):
                self.aoi_file = PathField(
                    "Survey area file (GeoJSON)",
                    directory=False,
                    suffixes=(".geojson", ".json"),
                    marker="aoi",
                    hint="Draw your area on a map (for example at geojson.io) and save it "
                    "as GeoJSON.",
                )
            self.takeoff = _text(
                "Takeoff point: latitude, longitude (empty = the middle of the area)",
                "takeoff-input",
            )

    # --------------------------------------------------------------- 2. the drone
    def _drone_card(self, names: dict[str, str]) -> None:
        with _card("2. Your drone"):
            modes = list(self.profiles[self.first].modes)
            with ui.row().classes("gap-3 items-center"):
                self.aircraft = (
                    ui.select(names, value=self.first, label="Aircraft")
                    .props("outlined dense")
                    .classes("w-64")
                    .mark("aircraft-select")
                )
                self.camera = (
                    ui.select(
                        modes, value="12mp" if "12mp" in modes else modes[0], label="Photo size"
                    )
                    .props("outlined dense")
                    .classes("w-40")
                    .mark("camera-select")
                )
            self.note = ui.label().classes("text-sm av-caution-text")
            self.aircraft.on_value_change(self._aircraft_changed)
            self._aircraft_changed()
            self.template = PathField(
                "Your DJI Fly sample mission (.kmz)",
                directory=False,
                suffixes=(".kmz",),
                marker="template",
            )
            with ui.expansion("How do I get this file?", icon="help_outline").classes("w-full"):
                ui.label(FLY_FILE_HELP).classes("text-sm")

    def _aircraft_changed(self) -> None:
        profile = self.profiles[self.aircraft.value]
        modes = list(profile.modes)
        self.camera.set_options(modes, value="12mp" if "12mp" in modes else modes[0])
        self.note.set_text(
            ""
            if profile.verified
            else "The camera numbers for this aircraft have not been verified yet."
        )

    # ------------------------------------------------------------- 3. what you want
    def _wants_card(self) -> None:
        with _card("3. What you want"):
            self.target_kind = (
                ui.radio(
                    {"resolution": "A ground resolution", "height": "A flying height"},
                    value="resolution",
                )
                .props("inline")
                .mark("target-kind")
            )
            with ui.row().classes("gap-3 items-center"):
                self.target = _number("Value", 2.0, "target-input", min=0.1, max=300)
                unit = ui.label().classes("text-sm av-muted")
            unit.bind_text_from(
                self.target_kind,
                "value",
                backward=lambda v: (
                    "cm per pixel (smaller = more detail)"
                    if v == "resolution"
                    else "metres above the surface"
                ),
            )
            with ui.row().classes("gap-3"):
                self.front = _number(
                    "Overlap along the line (%)", 80.0, "front-input", "w-60", min=10, max=95
                )
                self.side = _number(
                    "Overlap between lines (%)", 70.0, "side-input", "w-60", min=10, max=95
                )
            self.photo_mode = (
                ui.select(
                    {
                        "interval": "Timed shot (recommended)",
                        "waypoint": "A photo at each waypoint (experimental)",
                    },
                    value="interval",
                    label="How photos are taken",
                )
                .props("outlined dense")
                .classes("w-80")
                .mark("photo-mode-select")
            )

    # ---------------------------------------------------------------- 4. the ground
    def _ground_card(self) -> None:
        with _card("4. The ground"):
            self.terrain = (
                ui.radio(
                    {"flat": "It is flat", "model": "It has hills (I have an elevation model)"},
                    value="flat",
                )
                .props("inline")
                .mark("terrain")
            )
            with _show_when(self.terrain, "model", gap="gap-1"):
                self.dem = PathField(
                    "Elevation model (GeoTIFF)",
                    directory=False,
                    suffixes=(".tif", ".tiff"),
                    marker="dem",
                    hint="With hills, the route follows the terrain so the photos keep "
                    "their resolution.",
                )
            self.surface = _number(
                "Height of trees or buildings above the ground (m)",
                0.0,
                "surface-input",
                "w-96",
                min=0,
                max=150,
            )
            ui.label(
                "In a forest enter the typical canopy height, so the canopy (not the ground) "
                "gets the height you asked for. Leave 0 for open ground."
            ).classes("text-xs av-muted")

    # ------------------------------------------------------------- 5. where to save
    def _save_card(self) -> None:
        with _card("5. Where to save"):
            self.out = PathField("Output folder", value=STATE.last_output, marker="out")
            self.name = _text("Name for the missions", "name-input", "survey", "w-64")

    # ----------------------------------------------------------------- advanced
    def _advanced(self) -> None:
        with (
            ui.expansion("Advanced settings", icon="tune").classes("w-full border rounded-lg"),
            ui.column().classes("gap-3 p-2"),
        ):
            self.shutter = _text("Shutter time you expect", "shutter-input", "1/1000", "w-60")
            with ui.row().classes("gap-3"):
                self.wind = _number("Wind (m/s)", 0.0, "wind-input", min=0, max=30)
                self.max_height = _number(
                    "Highest allowed above takeoff (m)",
                    120.0,
                    "max-height-input",
                    "w-72",
                    min=10,
                    max=500,
                )
                self.max_distance = _number(
                    "Farthest from takeoff (m)",
                    500.0,
                    "max-distance-input",
                    "w-60",
                    min=50,
                    max=5000,
                )
                self.battery = _number(
                    "Flying time per battery (min)", 20.0, "battery-input", "w-64", min=3, max=60
                )
            self.heading = _text(
                "Direction of the flight lines in degrees (empty = automatic)",
                "heading-input",
                width="w-96",
            )
            self.crosshatch = ui.switch(
                "Fly a second set of lines across the first (better 3D, twice the flying)"
            ).mark("crosshatch-switch")
            self.calibrate = ui.switch(
                "Tune height and spacing to the real terrain", value=True
            ).mark("calibrate-switch")
            self.straight = ui.switch("Straight legs between waypoints", value=True).mark(
                "straight-switch"
            )

    # ------------------------------------------------------------------ reading it
    def collect(self) -> PlanForm:
        return PlanForm(
            area_mode=self.mode.value,
            centre=self.centre.value or "",
            width_m=self.width.value or 0.0,
            length_m=self.length.value or 0.0,
            area_heading_deg=self.area_heading.value or 0.0,
            aoi_file=self.aoi_file.value,
            takeoff=self.takeoff.value or "",
            aircraft=self.aircraft.value,
            camera_mode=self.camera.value or "",
            template=self.template.value,
            target_kind=self.target_kind.value,
            target_value=self.target.value or 0.0,
            front_percent=self.front.value or 0.0,
            side_percent=self.side.value or 0.0,
            photo_mode=self.photo_mode.value,
            terrain=self.terrain.value,
            dem_file=self.dem.value,
            surface_height_m=self.surface.value or 0.0,
            out_dir=self.out.value,
            name=self.name.value or "survey",
            shutter=self.shutter.value or "",
            wind_ms=self.wind.value or 0.0,
            max_height_m=self.max_height.value or 0.0,
            max_distance_m=self.max_distance.value or 0.0,
            battery_minutes=self.battery.value or 0.0,
            crosshatch=bool(self.crosshatch.value),
            heading_text=self.heading.value or "",
            calibrate=bool(self.calibrate.value),
            straight_legs=bool(self.straight.value),
        )
