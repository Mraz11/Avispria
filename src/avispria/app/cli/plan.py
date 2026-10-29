# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The `plan` command."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Annotated

import typer

from avispria.adapters.profiles import load_profiles
from avispria.app.cli._base import app, parse_latlon, parse_shutter, print_issues
from avispria.app.workflow import PlanBlockedError, PlanOptions, run_plan
from avispria.core.errors import PlanningError
from avispria.core.geometry import AoiError
from avispria.core.mission import PhotoMode
from avispria.core.plan_model import PlanSummary
from avispria.core.safety import SafetyLimits
from avispria.core.wpml.kmz import KmzError


@app.command()
def plan(
    aoi: Annotated[Path, typer.Argument(exists=True, dir_okay=False, help="AOI polygon (GeoJSON)")],
    template: Annotated[
        Path, typer.Option(exists=True, dir_okay=False, help="Your DJI Fly dummy KMZ")
    ],
    takeoff: Annotated[str, typer.Option(help="Takeoff point LAT,LON")],
    out: Annotated[Path, typer.Option(help="Output folder")],
    drone: str = "lito-x1",
    mode: Annotated[str, typer.Option(help="Camera mode, e.g. 12mp or 48mp")] = "12mp",
    gsd_cm: Annotated[float | None, typer.Option(help="Target ground resolution (cm/px)")] = None,
    agl: Annotated[float | None, typer.Option(help="Height above the surface (m)")] = None,
    dem: Annotated[
        Path | None, typer.Option(exists=True, dir_okay=False, help="GeoTIFF DEM")
    ] = None,
    flat: Annotated[bool, typer.Option("--flat", help="No DEM: assume flat ground")] = False,
    takeoff_elev: Annotated[
        float | None, typer.Option(help="Takeoff elevation (DEM datum, m)")
    ] = None,
    front: float = 0.8,
    side: float = 0.7,
    heading: Annotated[float | None, typer.Option(help="Line heading (deg); default auto")] = None,
    crosshatch: bool = False,
    photo_mode: Annotated[PhotoMode, typer.Option(case_sensitive=False)] = PhotoMode.INTERVAL,
    shutter: Annotated[str, typer.Option(help="Expected shutter, e.g. 1/1000")] = "1/1000",
    wind: Annotated[float, typer.Option(help="Wind speed (m/s)")] = 0.0,
    max_height: Annotated[float, typer.Option(help="Max height above takeoff (m)")] = 120.0,
    max_distance: Annotated[float, typer.Option(help="Max distance from takeoff (m)")] = 500.0,
    max_flight_min: Annotated[
        float, typer.Option(help="Usable flight time per battery (min)")
    ] = 20.0,
    curved: Annotated[bool, typer.Option(help="Keep DJI Fly's curved legs")] = False,
    surface_height: Annotated[
        float,
        typer.Option(
            help="Height of trees or buildings above the ground (m), so the canopy gets "
            "the requested height instead of the ground"
        ),
    ] = 0.0,
    calibrate: Annotated[
        bool,
        typer.Option(
            "--calibrate/--no-calibrate",
            help="Tune flight height and spacing so the photos really get the requested "
            "height above the terrain",
        ),
    ] = True,
    name: str = "avispria",
) -> None:
    """Plan a survey and write DJI Fly mission files, spot-check sheets and a report."""
    lat, lon = parse_latlon(takeoff)
    profile = load_profiles().get(drone)
    if profile is None:
        raise typer.BadParameter(f"unknown drone {drone!r}; see `avispria drones`")
    opts = PlanOptions(
        takeoff_lat=lat,
        takeoff_lon=lon,
        mode=mode,
        target_gsd_m=None if gsd_cm is None else gsd_cm / 100.0,
        agl_m=agl,
        front_overlap=front,
        side_overlap=side,
        heading_deg=heading,
        crosshatch=crosshatch,
        photo_mode=photo_mode,
        dem_path=dem,
        flat_terrain=flat,
        takeoff_elevation_m=takeoff_elev,
        shutter_s=parse_shutter(shutter),
        wind_ms=wind,
        limits=SafetyLimits(
            max_height_above_takeoff_m=max_height,
            max_height_above_ground_m=max_height,
            max_distance_from_takeoff_m=max_distance,
            max_flight_time_s=max_flight_min * 60.0,
        ),
        straight_lines=not curved,
        surface_height_m=surface_height,
        calibrate_height=calibrate,
        name=name,
    )
    try:
        res = run_plan(aoi, template, profile, opts, out, now_ms=int(time.time() * 1000))
    except PlanBlockedError as exc:
        typer.secho("Plan blocked; nothing was written:", fg=typer.colors.RED)
        print_issues(exc.issues)
        raise typer.Exit(1) from exc
    except (PlanningError, AoiError, KmzError, ValueError) as exc:
        typer.secho(f"Cannot plan: {exc}", fg=typer.colors.RED)
        raise typer.Exit(1) from exc

    s = res.result.summary
    typer.secho(f"Planned {len(res.kmz_paths)} mission(s) into {out}", fg=typer.colors.GREEN)
    typer.echo(
        f"  requested {s.agl_m:.1f} m above the surface = {s.gsd_m * 100:.2f} cm/px  "
        f"lines {s.strips} @ {s.line_spacing_m:.1f} m  photos every {s.photo_spacing_m:.1f} m"
    )
    typer.echo(f"  speed {s.speed.speed_ms:.1f} m/s (limited by {s.speed.binding})")
    typer.echo(f"  terrain: {s.terrain_source}; takeoff elevation: {s.takeoff_elevation_source}")
    _print_prediction(s)
    if s.photo_interval_s is not None:
        typer.secho(
            f"  Set DJI Fly timed shot to {s.photo_interval_s:.1f} s or shorter before starting.",
            fg=typer.colors.CYAN,
        )
    for m, path in zip(res.result.missions, res.kmz_paths, strict=True):
        typer.echo(
            f"  {path.name}: {len(m.waypoints)} waypoints, "
            f"~{m.estimated_duration_s / 60:.1f} min, "
            f"max {max(w.height_m for w in m.waypoints):.0f} m"
        )
    if res.warnings:
        typer.secho("Warnings:", fg=typer.colors.YELLOW)
        print_issues(res.warnings)


def _percent(value: float | None) -> str:
    return "-" if value is None else f"{value * 100:.0f}%"


def _print_prediction(s: PlanSummary) -> None:
    """What the plan will really achieve over the terrain, in plain words."""
    p = s.prediction
    if p is None:
        return
    typer.secho(f"  Predicted over the real surface ({p.photos} photos):", bold=True)
    typer.echo(
        f"    height above the surface  {p.height_min_m:.1f} m lowest, "
        f"{p.height_median_m:.1f} m typical, {p.height_max_m:.1f} m highest"
    )
    typer.echo(
        f"    resolution                {p.gsd_cm_median:.2f} cm/px typical, "
        f"{p.gsd_cm_p90:.2f} cm/px for the coarsest tenth"
    )
    if p.front_overlap_median is not None or p.side_overlap_median is not None:
        typer.echo(
            f"    overlap                   front {_percent(p.front_overlap_median)} typical "
            f"({_percent(p.front_overlap_p10)} at the low end), "
            f"side {_percent(p.side_overlap_median)} ({_percent(p.side_overlap_p10)})"
        )
    typer.echo(
        f"    coverage                  {p.area_pct_min_views:.0f}% of the area seen by "
        f"3+ photos, {p.area_pct_good_views:.0f}% by 5+"
    )
    if abs(s.flight_reference_m - s.agl_m) >= 2.0:
        typer.echo(
            f"    route built around {s.flight_reference_m:.1f} m (not {s.agl_m:.1f}): "
            "terrain following lifts the drone above that, so this is what the photos get"
        )
