# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""What the Plan screen does for 'a 3D model of one object': validate the form, plan, write."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from avispria.adapters.profiles import DroneProfile, load_profiles
from avispria.app.scan_workflow import ScanOutputs, run_scan
from avispria.app.ui.inputs import parse_latlon_text
from avispria.app.ui.plan_job import FormError, PlanForm, _file
from avispria.app.workflow import PlanBlockedError
from avispria.core.safety import Issue, SafetyLimits
from avispria.core.scan import ScanRequest


@dataclass(frozen=True)
class ScanJobResult:
    outputs: ScanOutputs | None = None
    blocked: list[Issue] = field(default_factory=list)
    centre: tuple[float, float] | None = None  # (lon, lat) of the object
    takeoff: tuple[float, float] | None = None


def build_scan(
    form: PlanForm, profiles: dict[str, DroneProfile] | None = None
) -> tuple[ScanRequest, DroneProfile, Path, Path]:
    """Validate the form top to bottom, like the screen, and prepare the planning."""
    known = profiles if profiles is not None else load_profiles()
    # 1. where the object is
    try:
        lat, lon = parse_latlon_text(form.object_centre)
    except ValueError as exc:
        raise FormError(f"Position of the object: {exc}") from None
    takeoff_lat = takeoff_lon = None
    if form.takeoff.strip():
        try:
            takeoff_lat, takeoff_lon = parse_latlon_text(form.takeoff)
        except ValueError as exc:
            raise FormError(f"Takeoff point: {exc}") from None
    # 2. the drone
    profile = known.get(form.aircraft)
    if profile is None:
        raise FormError(f"Unknown aircraft {form.aircraft!r}.")
    if form.camera_mode not in profile.modes:
        raise FormError(f"{profile.name} has no camera mode {form.camera_mode!r}.")
    template = _file(form.template, "DJI Fly sample mission file", (".kmz",))
    # 3. the object and the flight (the planner checks the numbers and says what is wrong)
    for percent, what in (
        (form.front_percent, "around a ring"),
        (form.side_percent, "between rings"),
    ):
        if not 10.0 <= percent <= 95.0:
            raise FormError(f"The overlap {what} must be between 10% and 95%.")
    # 4. where to save
    if not form.out_dir.strip():
        raise FormError("Choose the folder where the plan should be saved.")
    out_dir = Path(form.out_dir.strip()).expanduser()
    request = ScanRequest(
        centre_lon=lon,
        centre_lat=lat,
        camera=profile.modes[form.camera_mode],
        drone_max_speed_ms=profile.max_speed_ms,
        object_height_m=form.object_height_m,
        object_radius_m=form.object_radius_m,
        standoff_m=form.standoff_m,
        base_height_m=form.base_height_m,
        front_overlap=form.front_percent / 100.0,
        side_overlap=form.side_percent / 100.0,
        look_up_deg=form.look_up_deg,
        look_down_deg=form.look_down_deg,
        top_cap=form.top_cap,
        speed_ms=form.scan_speed_ms,
        hover_s=form.hover_s,
        takeoff_lon=takeoff_lon,
        takeoff_lat=takeoff_lat,
        ground_offset_m=form.ground_offset_m,
        name=form.name or "scan",
        limits=SafetyLimits(
            max_height_above_takeoff_m=form.max_height_m,
            max_distance_from_takeoff_m=form.max_distance_m,
            max_flight_time_s=form.battery_minutes * 60.0,
        ),
    )
    return request, profile, template, out_dir


def execute_scan(form: PlanForm, *, now_ms: int | None = None) -> ScanJobResult:
    """Plan the rings and write the missions; a blocked plan comes back with its reasons."""
    request, profile, template, out_dir = build_scan(form)
    try:
        outputs = run_scan(
            request,
            template,
            profile,
            out_dir,
            int(time.time() * 1000) if now_ms is None else now_ms,
        )
    except PlanBlockedError as exc:
        return ScanJobResult(blocked=list(exc.issues))
    first = outputs.plan.missions[0].takeoff
    return ScanJobResult(
        outputs, [], (request.centre_lon, request.centre_lat), (first.lon, first.lat)
    )
