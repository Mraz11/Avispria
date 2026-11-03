# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The Plan a flight form: the widgets, and how they become a plain ``PlanForm``."""

from __future__ import annotations

from nicegui import ui

from avispria.adapters.profiles import DroneProfile
from avispria.app.ui.pages.plan_form_parts import card, number, show_when, text
from avispria.app.ui.pages.plan_map import AreaMap
from avispria.app.ui.pages.plan_object import ObjectCards
from avispria.app.ui.pages.plan_results import FLY_FILE_HELP
from avispria.app.ui.pages.plan_settings import AREA_KINDS, SettingsCards
from avispria.app.ui.pages.plan_type import TypeCard
from avispria.app.ui.plan_job import PlanForm
from avispria.app.ui.state import STATE
from avispria.app.ui.widgets import PathField

SAMPLE_HELP = (
    "Avispria copies the exact format your DJI Fly uses from a sample mission. If you have none "
    "yet: in DJI Fly make a Waypoint Flight with two points and save it (do not fly it), connect "
    "the phone to this computer, open step 2 and press 'Use as my sample mission'. You do this "
    "once."
)


class PlanFormUi(TypeCard, ObjectCards, SettingsCards):
    """Builds the five cards of the form; ``collect`` reads them into a ``PlanForm``."""

    def __init__(self, profiles: dict[str, DroneProfile]) -> None:
        self.profiles = profiles
        names = {key: p.name for key, p in profiles.items()}
        self.first = "lito-x1" if "lito-x1" in names else next(iter(names))
        self._type_card()
        self._area_card()
        self._object_where_card()
        self._drone_card(names)
        self._wants_card()
        self._object_settings_card()
        self._save_card()
        self._advanced()

    # ---------------------------------------------------------------- 1. the area
    def _area_card(self) -> None:
        with card("2. Where: the area", radio=self.scan_type, kinds=AREA_KINDS):
            self.mode = (
                ui.radio(
                    {
                        "numbers": "Describe it with numbers",
                        "drawn": "Draw it on a map",
                        "file": "Use a map file",
                    },
                    value="numbers",
                )
                .props("inline")
                .mark("area-mode")
            )
            with show_when(self.mode, "numbers"):
                self.centre = text(
                    "Centre of the area: latitude, longitude",
                    "centre-input",
                    placeholder="23.8103, 90.4125",
                )
                with ui.row().classes("gap-3"):
                    self.width = number("Width (m)", 200.0, "width-input", min=5, max=5000)
                    self.length = number("Length (m)", 300.0, "length-input", min=5, max=5000)
                    self.area_heading = number(
                        "Direction of the long side (degrees, 0 = north)",
                        0.0,
                        "area-heading-input",
                        "w-72",
                        min=0,
                        max=360,
                    )
            self.area_map: AreaMap | None = None
            self._map_box = show_when(self.mode, "drawn")
            self.mode.on_value_change(lambda _: self._open_map())
            with show_when(self.mode, "file", gap="gap-1"):
                self.aoi_file = PathField(
                    "Survey area file (GeoJSON)",
                    directory=False,
                    suffixes=(".geojson", ".json"),
                    marker="aoi",
                    hint="Draw your area on a map (for example at geojson.io) and save it "
                    "as GeoJSON.",
                )
            self.takeoff = text(
                "Takeoff point: latitude, longitude (empty = the middle of the area)",
                "takeoff-input",
            )

    def _open_map(self) -> None:
        """Build the map the first time it is wanted (a map made while hidden draws wrongly)."""
        if self.mode.value == "drawn" and self.area_map is None:
            with self._map_box:
                self.area_map = AreaMap(on_takeoff=lambda text: self.takeoff.set_value(text))

    # --------------------------------------------------------------- 2. the drone
    def _drone_card(self, names: dict[str, str]) -> None:
        with card("3. Your drone"):
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
            ui.label(SAMPLE_HELP).classes("text-sm av-muted").mark("sample-help")
            ui.link("Open step 2: Send to DJI Fly", "/phone").classes("text-sm")
            self.template = PathField(
                "Your DJI Fly sample mission (.kmz)",
                directory=False,
                suffixes=(".kmz",),
                value=STATE.sample_mission,
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

    # ---------------------------------------------------------------- 4. the ground

    # ------------------------------------------------------------- 5. where to save

    # ----------------------------------------------------------------- advanced

    # ------------------------------------------------------------------ reading it
    def _drawn_geojson(self) -> str:
        if self.mode.value == "drawn" and self.area_map is not None:
            return self.area_map.geojson()
        return ""

    def _drawn_problem(self) -> str:
        if self.mode.value == "drawn" and self.area_map is not None:
            return self.area_map.problem or ""
        return ""

    def collect(self) -> PlanForm:
        kind = self.scan_type.value
        is_object = kind == "object_3d"
        return PlanForm(
            scan_type=kind,
            tilt_deg=float(self.tilt.value or 0.0) if kind == "area_3d" else 0.0,
            object_centre=self.object_centre.value or "",
            object_height_m=self.object_height.value or 0.0,
            object_radius_m=self.object_radius.value or 0.0,
            standoff_m=self.standoff.value or 0.0,
            base_height_m=self.base_height.value or 0.0,
            ground_offset_m=self.ground_offset.value or 0.0,
            look_up_deg=self.look_up.value or 0.0,
            look_down_deg=self.look_down.value or 0.0,
            top_cap=bool(self.top_cap.value),
            hover_s=self.hover.value or 0.0,
            scan_speed_ms=self.scan_speed.value or 0.0,
            area_mode=self.mode.value,
            centre=self.centre.value or "",
            width_m=self.width.value or 0.0,
            length_m=self.length.value or 0.0,
            area_heading_deg=self.area_heading.value or 0.0,
            aoi_file=self.aoi_file.value,
            drawn_area_geojson=self._drawn_geojson(),
            drawn_area_problem=self._drawn_problem(),
            takeoff=(self.object_takeoff.value if is_object else self.takeoff.value) or "",
            aircraft=self.aircraft.value,
            camera_mode=self.camera.value or "",
            template=self.template.value,
            target_kind=self.target_kind.value,
            target_value=self.target.value or 0.0,
            front_percent=(self.obj_front.value if is_object else self.front.value) or 0.0,
            side_percent=(self.obj_side.value if is_object else self.side.value) or 0.0,
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
