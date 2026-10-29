# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The Plan a flight form as plain data, and what it takes to turn it into a plan.

The screen only fills in a ``PlanForm`` and draws what ``execute_plan`` returns, so every
rule below (validation, defaults, the survey rectangle, error messages) is tested without a
browser.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from shapely.geometry import Polygon, mapping

from avispria.adapters.profiles import DroneProfile, load_profiles
from avispria.app.ui.inputs import parse_latlon_text, parse_shutter_text
from avispria.app.workflow import PlanBlockedError, PlanOptions, PlanOutputs, run_plan
from avispria.core.geometry import load_aoi, rectangle_polygon
from avispria.core.mission import PhotoMode
from avispria.core.predict import planned_photos
from avispria.core.safety import Issue, SafetyLimits


class FormError(ValueError):
    """Something in the form is missing or wrong; the message says what to change."""


@dataclass(frozen=True)
class PlanForm:
    # survey area
    area_mode: str = "numbers"  # "numbers" or "file"
    centre: str = ""  # "latitude, longitude"
    width_m: float = 200.0
    length_m: float = 300.0
    area_heading_deg: float = 0.0
    aoi_file: str = ""
    takeoff: str = ""  # empty: the centre of the area
    # aircraft
    aircraft: str = "lito-x1"
    camera_mode: str = "12mp"
    template: str = ""
    # what is wanted
    target_kind: str = "resolution"  # "resolution" (cm/px) or "height" (m above the surface)
    target_value: float = 2.0
    front_percent: float = 80.0
    side_percent: float = 70.0
    photo_mode: str = "interval"
    # terrain
    terrain: str = "flat"  # "flat" or "model"
    dem_file: str = ""
    surface_height_m: float = 0.0
    # output
    out_dir: str = ""
    name: str = "survey"
    # advanced
    shutter: str = "1/1000"
    wind_ms: float = 0.0
    max_height_m: float = 120.0
    max_distance_m: float = 500.0
    battery_minutes: float = 20.0
    crosshatch: bool = False
    heading_text: str = ""  # empty: automatic
    calibrate: bool = True
    straight_legs: bool = True


@dataclass(frozen=True)
class PlanInputs:
    aoi_path: Path
    template: Path
    profile: DroneProfile
    options: PlanOptions
    out_dir: Path


@dataclass(frozen=True)
class PlanJobResult:
    outputs: PlanOutputs | None = None
    aoi: Polygon | None = None
    takeoff: tuple[float, float] = (0.0, 0.0)  # longitude, latitude
    photos: list[tuple[float, float]] = field(default_factory=list)
    blocked: list[Issue] = field(default_factory=list)


def _file(text: str, what: str, suffixes: tuple[str, ...] | None = None) -> Path:
    if not text.strip():
        raise FormError(f"Choose the {what}.")
    path = Path(text.strip()).expanduser()
    if not path.is_file():
        raise FormError(f"The {what} was not found: {path}")
    if suffixes and path.suffix.lower() not in suffixes:
        raise FormError(f"The {what} should be a {' or '.join(suffixes)} file: {path.name}")
    return path


def _area(form: PlanForm) -> tuple[Polygon, Path | None]:
    """The survey area, and the file it came from (None for a rectangle made from numbers)."""
    if form.area_mode == "numbers":
        try:
            lat, lon = parse_latlon_text(form.centre)
        except ValueError as exc:
            raise FormError(f"Centre of the area: {exc}") from None
        try:
            return rectangle_polygon(
                lat, lon, form.width_m, form.length_m, form.area_heading_deg
            ), None
        except ValueError as exc:
            raise FormError(f"Survey area: {exc}") from None
    path = _file(form.aoi_file, "survey area file", (".geojson", ".json"))
    try:
        return load_aoi(json.loads(path.read_text(encoding="utf-8"))), path
    except (ValueError, OSError) as exc:
        raise FormError(f"The survey area file could not be used: {exc}") from None


def build_inputs(form: PlanForm, profiles: dict[str, DroneProfile] | None = None) -> PlanInputs:
    """Validate the form (top to bottom, like the screen) and prepare what planning needs."""
    known = profiles if profiles is not None else load_profiles()
    # 1. the survey area, and where takeoff is
    polygon, aoi_file = _area(form)
    if form.takeoff.strip():
        try:
            takeoff_lat, takeoff_lon = parse_latlon_text(form.takeoff)
        except ValueError as exc:
            raise FormError(f"Takeoff point: {exc}") from None
    else:
        takeoff_lat, takeoff_lon = polygon.centroid.y, polygon.centroid.x
    # 2. the drone
    profile = known.get(form.aircraft)
    if profile is None:
        raise FormError(f"Unknown aircraft {form.aircraft!r}.")
    if form.camera_mode not in profile.modes:
        raise FormError(f"{profile.name} has no camera mode {form.camera_mode!r}.")
    template = _file(form.template, "DJI Fly sample mission file", (".kmz",))
    # 3. what is wanted
    if form.target_value <= 0:
        raise FormError("The resolution or height you ask for must be more than zero.")
    for percent, what in ((form.front_percent, "front"), (form.side_percent, "side")):
        if not 10.0 <= percent <= 95.0:
            raise FormError(f"The {what} overlap must be between 10% and 95%.")
    # 4. the ground
    dem_path = (
        _file(form.dem_file, "elevation model", (".tif", ".tiff"))
        if form.terrain == "model"
        else None
    )
    # 5. where to save
    if not form.out_dir.strip():
        raise FormError("Choose the folder where the plan should be saved.")
    out_dir = Path(form.out_dir.strip()).expanduser()
    # advanced
    heading = None
    if form.heading_text.strip():
        try:
            heading = float(form.heading_text)
        except ValueError:
            raise FormError(
                "The flight line direction must be a number of degrees (0 to 360)."
            ) from None
    try:
        shutter = parse_shutter_text(form.shutter)
    except ValueError as exc:
        raise FormError(str(exc)) from None
    if aoi_file is None:  # everything is valid: now keep the rectangle with the plan
        out_dir.mkdir(parents=True, exist_ok=True)
        aoi_file = out_dir / "survey_area.geojson"
        aoi_file.write_text(json.dumps(mapping(polygon)), encoding="utf-8")
    wants_resolution = form.target_kind == "resolution"
    options = PlanOptions(
        takeoff_lat=takeoff_lat,
        takeoff_lon=takeoff_lon,
        mode=form.camera_mode,
        target_gsd_m=form.target_value / 100.0 if wants_resolution else None,
        agl_m=None if wants_resolution else form.target_value,
        front_overlap=form.front_percent / 100.0,
        side_overlap=form.side_percent / 100.0,
        heading_deg=heading,
        crosshatch=form.crosshatch,
        photo_mode=PhotoMode.INTERVAL if form.photo_mode == "interval" else PhotoMode.WAYPOINT,
        dem_path=dem_path,
        flat_terrain=form.terrain != "model",
        shutter_s=shutter,
        wind_ms=form.wind_ms,
        limits=SafetyLimits(
            max_height_above_takeoff_m=form.max_height_m,
            max_height_above_ground_m=form.max_height_m,
            max_distance_from_takeoff_m=form.max_distance_m,
            max_flight_time_s=form.battery_minutes * 60.0,
        ),
        straight_lines=form.straight_legs,
        surface_height_m=form.surface_height_m,
        calibrate_height=form.calibrate,
        name=form.name.strip() or "survey",
    )
    return PlanInputs(aoi_file, template, profile, options, out_dir)


def execute_plan(form: PlanForm, *, now_ms: int | None = None) -> PlanJobResult:
    """Plan and write the mission files; a blocked plan comes back with its reasons."""
    inputs = build_inputs(form)
    try:
        outputs = run_plan(
            inputs.aoi_path,
            inputs.template,
            inputs.profile,
            inputs.options,
            inputs.out_dir,
            now_ms=int(time.time() * 1000) if now_ms is None else now_ms,
        )
    except PlanBlockedError as exc:
        return PlanJobResult(blocked=list(exc.issues))
    aoi = load_aoi(json.loads(inputs.aoi_path.read_text(encoding="utf-8")))
    photos = [(p.lon, p.lat) for m in outputs.result.missions for p in planned_photos(m)]
    takeoff = (inputs.options.takeoff_lon, inputs.options.takeoff_lat)
    return PlanJobResult(outputs, aoi, takeoff, photos)
