# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Plan a flight: describe the area and what you want, get missions for DJI Fly."""

from __future__ import annotations

from pathlib import Path

from nicegui import ui

from avispria.adapters.profiles import load_profiles
from avispria.app.ui.jobs import run_job
from avispria.app.ui.layout import frame
from avispria.app.ui.pages.plan_results import show_plan
from avispria.app.ui.plan_job import FormError, PlanForm, execute_plan
from avispria.app.ui.state import STATE
from avispria.app.ui.widgets import PathField

FLY_FILE_HELP = (
    "On your phone, open DJI Fly, choose Waypoint Flight, add two points and save the mission "
    "(do not fly it). Then copy the .kmz file DJI Fly made for it to this computer: "
    "Android/data/dji.go.v5/files/waypoint/<long ID>/<long ID>.kmz. Avispria copies the exact "
    "format your DJI Fly uses from this file."
)


def _card(title: str) -> ui.column:
    with ui.card().classes("w-full"):
        ui.label(title).classes("text-lg font-bold")
        return ui.column().classes("w-full gap-3")


def _number(label: str, value: float, marker: str, **props: float) -> ui.number:
    field = ui.number(label, value=value, **props).props("outlined dense").mark(marker)
    return field.classes("w-40")


async def plan_page() -> None:
    profiles = load_profiles()
    names = {key: p.name for key, p in profiles.items()}
    first = "lito-x1" if "lito-x1" in names else next(iter(names))
    with frame("Plan a flight"):
        ui.label(
            "Describe the area you want to map and what you need from the photos. Avispria "
            "makes missions for DJI Fly and tells you what resolution and overlap you will "
            "really get over your terrain."
        ).classes("text-base")

        body = _card("1. The survey area")
        with body:
            mode = (
                ui.radio(
                    {"numbers": "Describe it with numbers", "file": "Use a map file"},
                    value="numbers",
                )
                .props("inline")
                .mark("area-mode")
            )
            with (
                ui.column()
                .classes("w-full gap-3")
                .bind_visibility_from(mode, "value", backward=lambda v: v == "numbers")
            ):
                centre = (
                    ui.input(
                        "Centre of the area: latitude, longitude", placeholder="23.8103, 90.4125"
                    )
                    .props("outlined dense")
                    .classes("w-full")
                    .mark("centre-input")
                )
                with ui.row().classes("gap-3"):
                    width = _number("Width (m)", 200.0, "width-input", min=5, max=5000)
                    length = _number("Length (m)", 300.0, "length-input", min=5, max=5000)
                    area_heading = _number(
                        "Direction of the long side (degrees, 0 = north)",
                        0.0,
                        "area-heading-input",
                        min=0,
                        max=360,
                    ).classes("w-72")
            with (
                ui.column()
                .classes("w-full gap-1")
                .bind_visibility_from(mode, "value", backward=lambda v: v == "file")
            ):
                aoi_file = PathField(
                    "Survey area file (GeoJSON)",
                    directory=False,
                    suffixes=(".geojson", ".json"),
                    marker="aoi",
                    hint="Draw your area on a map (for example at geojson.io) and save it "
                    "as GeoJSON.",
                )
            takeoff = (
                ui.input("Takeoff point: latitude, longitude (empty = the middle of the area)")
                .props("outlined dense")
                .classes("w-full")
                .mark("takeoff-input")
            )

        body = _card("2. Your drone")
        with body:
            with ui.row().classes("gap-3 items-center"):
                aircraft = (
                    ui.select(names, value=first, label="Aircraft")
                    .props("outlined dense")
                    .classes("w-64")
                    .mark("aircraft-select")
                )
                camera = (
                    ui.select(
                        list(profiles[first].modes),
                        value="12mp" if "12mp" in profiles[first].modes else None,
                        label="Photo size",
                    )
                    .props("outlined dense")
                    .classes("w-40")
                    .mark("camera-select")
                )
            note = ui.label().classes("text-sm text-amber-800")

            def aircraft_changed() -> None:
                profile = profiles[aircraft.value]
                camera.set_options(
                    list(profile.modes),
                    value="12mp" if "12mp" in profile.modes else next(iter(profile.modes)),
                )
                note.set_text(
                    ""
                    if profile.verified
                    else "The camera numbers for this aircraft have not been verified yet."
                )

            aircraft.on_value_change(aircraft_changed)
            aircraft_changed()
            template = PathField(
                "Your DJI Fly sample mission (.kmz)",
                directory=False,
                suffixes=(".kmz",),
                marker="template",
            )
            with ui.expansion("How do I get this file?", icon="help_outline").classes("w-full"):
                ui.label(FLY_FILE_HELP).classes("text-sm")

        body = _card("3. What you want")
        with body:
            target_kind = (
                ui.radio(
                    {"resolution": "A ground resolution", "height": "A flying height"},
                    value="resolution",
                )
                .props("inline")
                .mark("target-kind")
            )
            with ui.row().classes("gap-3 items-center"):
                target = _number("Value", 2.0, "target-input", min=0.1, max=300)
                unit = ui.label().classes("text-sm text-gray-700")
            unit.bind_text_from(
                target_kind,
                "value",
                backward=lambda v: (
                    "cm per pixel (smaller = more detail)"
                    if v == "resolution"
                    else "metres above the surface"
                ),
            )
            with ui.row().classes("gap-3"):
                front = _number(
                    "Overlap along the line (%)", 80.0, "front-input", min=10, max=95
                ).classes("w-60")
                side = _number(
                    "Overlap between lines (%)", 70.0, "side-input", min=10, max=95
                ).classes("w-60")
            photo_mode = (
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

        body = _card("4. The ground")
        with body:
            terrain = (
                ui.radio(
                    {"flat": "It is flat", "model": "It has hills (I have an elevation model)"},
                    value="flat",
                )
                .props("inline")
                .mark("terrain")
            )
            with (
                ui.column()
                .classes("w-full gap-1")
                .bind_visibility_from(terrain, "value", backward=lambda v: v == "model")
            ):
                dem = PathField(
                    "Elevation model (GeoTIFF)",
                    directory=False,
                    suffixes=(".tif", ".tiff"),
                    marker="dem",
                    hint="With hills, the route follows the terrain so the photos keep "
                    "their resolution.",
                )
            surface = _number(
                "Height of trees or buildings above the ground (m)",
                0.0,
                "surface-input",
                min=0,
                max=150,
            ).classes("w-96")
            ui.label(
                "In a forest enter the typical canopy height, so the canopy (not the ground) gets "
                "the height you asked for. Leave 0 for open ground."
            ).classes("text-xs text-gray-500")

        body = _card("5. Where to save")
        with body:
            out = PathField("Output folder", value=STATE.last_output, marker="out")
            name = (
                ui.input("Name for the missions", value="survey")
                .props("outlined dense")
                .classes("w-64")
                .mark("name-input")
            )

        with (
            ui.expansion("Advanced settings", icon="tune").classes("w-full border rounded-lg"),
            ui.column().classes("gap-3 p-2"),
        ):
            shutter = (
                ui.input("Shutter time you expect", value="1/1000")
                .props("outlined dense")
                .classes("w-60")
                .mark("shutter-input")
            )
            with ui.row().classes("gap-3"):
                wind = _number("Wind (m/s)", 0.0, "wind-input", min=0, max=30)
                max_height = _number(
                    "Highest allowed above takeoff (m)",
                    120.0,
                    "max-height-input",
                    min=10,
                    max=500,
                ).classes("w-72")
                max_distance = _number(
                    "Farthest from takeoff (m)", 500.0, "max-distance-input", min=50, max=5000
                ).classes("w-60")
                battery = _number(
                    "Flying time per battery (min)", 20.0, "battery-input", min=3, max=60
                ).classes("w-64")
            heading = (
                ui.input("Direction of the flight lines in degrees (empty = automatic)")
                .props("outlined dense")
                .classes("w-96")
                .mark("heading-input")
            )
            crosshatch = ui.switch(
                "Fly a second set of lines across the first (better 3D, twice the flying)"
            ).mark("crosshatch-switch")
            calibrate = ui.switch("Tune height and spacing to the real terrain", value=True).mark(
                "calibrate-switch"
            )
            straight = ui.switch("Straight legs between waypoints", value=True).mark(
                "straight-switch"
            )

        button = ui.button("Plan the flight", icon="flight").props("no-caps size=lg").mark("run")
        results = ui.column().classes("w-full gap-4")

    def collect() -> PlanForm:
        return PlanForm(
            area_mode=mode.value,
            centre=centre.value or "",
            width_m=width.value or 0.0,
            length_m=length.value or 0.0,
            area_heading_deg=area_heading.value or 0.0,
            aoi_file=aoi_file.value,
            takeoff=takeoff.value or "",
            aircraft=aircraft.value,
            camera_mode=camera.value or "",
            template=template.value,
            target_kind=target_kind.value,
            target_value=target.value or 0.0,
            front_percent=front.value or 0.0,
            side_percent=side.value or 0.0,
            photo_mode=photo_mode.value,
            terrain=terrain.value,
            dem_file=dem.value,
            surface_height_m=surface.value or 0.0,
            out_dir=out.value,
            name=name.value or "survey",
            shutter=shutter.value or "",
            wind_ms=wind.value or 0.0,
            max_height_m=max_height.value or 0.0,
            max_distance_m=max_distance.value or 0.0,
            battery_minutes=battery.value or 0.0,
            crosshatch=bool(crosshatch.value),
            heading_text=heading.value or "",
            calibrate=bool(calibrate.value),
            straight_legs=bool(straight.value),
        )

    async def run() -> None:
        results.clear()
        form = collect()
        button.disable()
        with results:
            ui.spinner(size="lg")
            ui.label("Planning the flight (hilly sites take a little longer)...")
        outcome = await run_job(execute_plan, form)
        button.enable()
        results.clear()
        if not outcome.ok or outcome.value is None:
            with results:
                ui.label(outcome.error or "The plan did not finish.").classes(
                    "text-red-700 font-medium"
                )
            return
        STATE.last_output = form.out_dir
        show_plan(results, outcome.value, Path(form.out_dir).expanduser())

    button.on_click(run)


__all__ = ["FormError", "plan_page"]
