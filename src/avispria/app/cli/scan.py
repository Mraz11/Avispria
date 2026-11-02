# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The `scan` command: rings of photos around a tree or other object."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Annotated

import typer

from avispria.adapters.profiles import load_profiles
from avispria.app.cli._base import app, parse_latlon, print_issues
from avispria.app.scan_workflow import run_scan
from avispria.app.workflow import PlanBlockedError
from avispria.core.errors import PlanningError
from avispria.core.safety import SafetyLimits
from avispria.core.scan import ScanRequest
from avispria.core.wpml.kmz import KmzError


@app.command()
def scan(
    centre: Annotated[str, typer.Argument(help="The object's centre, LAT,LON")],
    template: Annotated[
        Path, typer.Option(exists=True, dir_okay=False, help="Your DJI Fly sample mission (.kmz)")
    ],
    out: Annotated[Path, typer.Option(help="Output folder")],
    object_height: Annotated[float, typer.Option(help="Height of the object's top (m)")],
    object_radius: Annotated[float, typer.Option(help="Widest radius of the object (m)")],
    standoff: Annotated[
        float, typer.Option(help="Distance from its surface to the camera (m)")
    ] = 15.0,
    base_height: Annotated[float, typer.Option(help="Lowest height to photograph (m)")] = 0.0,
    takeoff: Annotated[str | None, typer.Option(help="Takeoff point LAT,LON")] = None,
    ground_offset: Annotated[
        float, typer.Option(help="Ground at the object above (+) or below (-) takeoff (m)")
    ] = 0.0,
    drone: str = "lito-x1",
    mode: Annotated[str, typer.Option(help="Camera mode, e.g. 12mp or 48mp")] = "12mp",
    front: Annotated[float, typer.Option(help="Overlap around a ring")] = 0.8,
    side: Annotated[float, typer.Option(help="Overlap between rings")] = 0.7,
    max_step: Annotated[float, typer.Option(help="Largest angle between photos (deg)")] = 10.0,
    look_up: Annotated[float, typer.Option(help="Camera tilt up on the lowest ring (deg)")] = 10.0,
    look_down: Annotated[float, typer.Option(help="Camera tilt down on the top ring (deg)")] = 20.0,
    top_cap: Annotated[bool, typer.Option(help="Add straight-down photos above the top")] = True,
    top_clearance: Annotated[
        float, typer.Option(help="How far above the top the cap flies (m)")
    ] = 8.0,
    speed: Annotated[float, typer.Option(help="Flight speed (m/s)")] = 3.0,
    hover: Annotated[float, typer.Option(help="Seconds standing still at each photo")] = 1.0,
    max_height: Annotated[float, typer.Option(help="Max height above takeoff (m)")] = 120.0,
    max_distance: Annotated[float, typer.Option(help="Max distance from takeoff (m)")] = 500.0,
    max_flight_min: Annotated[
        float, typer.Option(help="Usable flight time per battery (min)")
    ] = 20.0,
    name: str = "scan",
) -> None:
    """Plan rings of photos around a tree, a building or any other object (for 3D models)."""
    profiles = load_profiles()
    if drone not in profiles:
        raise typer.BadParameter(f"unknown drone {drone!r}; try `avispria drones`")
    profile = profiles[drone]
    if mode not in profile.modes:
        raise typer.BadParameter(
            f"{drone} has no camera mode {mode!r}; choose {sorted(profile.modes)}"
        )
    lat, lon = parse_latlon(centre)
    takeoff_lat, takeoff_lon = parse_latlon(takeoff) if takeoff else (None, None)
    request = ScanRequest(
        centre_lon=lon,
        centre_lat=lat,
        camera=profile.modes[mode],
        drone_max_speed_ms=profile.max_speed_ms,
        object_height_m=object_height,
        object_radius_m=object_radius,
        standoff_m=standoff,
        base_height_m=base_height,
        front_overlap=front,
        side_overlap=side,
        max_step_deg=max_step,
        look_up_deg=look_up,
        look_down_deg=look_down,
        top_cap=top_cap,
        top_clearance_m=top_clearance,
        speed_ms=speed,
        hover_s=hover,
        takeoff_lon=takeoff_lon,
        takeoff_lat=takeoff_lat,
        ground_offset_m=ground_offset,
        name=name,
        limits=SafetyLimits(
            max_height_above_takeoff_m=max_height,
            max_distance_from_takeoff_m=max_distance,
            max_flight_time_s=max_flight_min * 60.0,
        ),
    )
    try:
        outputs = run_scan(request, template, profile, out, int(time.time() * 1000))
    except PlanBlockedError as exc:
        print_issues(list(exc.issues))
        typer.secho("Not written: fix the problems above.", fg=typer.colors.RED)
        raise typer.Exit(1) from None
    except (PlanningError, KmzError, ValueError) as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(1) from None
    s = outputs.plan.summary
    typer.echo(
        f"{len(s.rings)} rings of {s.rings[0].photos} photos at {s.ring_radius_m:g} m from the axis"
        + (f", and a top cap of {s.cap_photos}" if s.cap_photos else "")
        + f": {s.photos} photos, {s.gsd_cm_best:.2f}-{s.gsd_cm_worst:.2f} cm/px on the object."
    )
    for k, r in enumerate(s.rings, start=1):
        typer.echo(
            f"  ring {k}: camera {r.height_m:.1f} m up, tilt {r.pitch_deg:+.0f} deg, "
            f"looking at {r.centre_height_m:.1f} m on the object"
        )
    for mission, path in zip(outputs.plan.missions, outputs.kmz_paths, strict=True):
        typer.echo(
            f"  {path.name}: {len(mission.waypoints)} waypoints, "
            f"about {mission.estimated_duration_s / 60:.0f} min"
        )
    print_issues(outputs.warnings)
    typer.secho(f"Saved in {out}", fg=typer.colors.GREEN)
