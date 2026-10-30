# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Capture QA commands: qa, camera-from-photo."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from avispria.adapters.exif import ExifError
from avispria.adapters.photos import photo_subfolders
from avispria.adapters.profiles import load_profiles
from avispria.app.capture_workflow import camera_toml, report_csv, run_qa
from avispria.app.cli._base import app, parse_latlon, print_issues
from avispria.core.errors import PlanningError


@app.command()
def qa(
    folder: Annotated[Path, typer.Argument(exists=True, file_okay=False, help="Photo folder")],
    drone: Annotated[str | None, typer.Option(help="Profile to use; default: from EXIF")] = None,
    csv_out: Annotated[Path | None, typer.Option("--csv", help="Per-photo CSV report")] = None,
    recursive: Annotated[
        bool, typer.Option("--recursive", "-r", help="Include photos in subfolders")
    ] = False,
    dem: Annotated[
        Path | None,
        typer.Option(
            "--dem",
            exists=True,
            dir_okay=False,
            help="Elevation model (GeoTIFF) to use the terrain",
        ),
    ] = None,
    takeoff: Annotated[
        str | None,
        typer.Option(
            help="Takeoff point LAT,LON (use with --dem unless it is the surface model made "
            "from these same photos)"
        ),
    ] = None,
    ground_elev: Annotated[
        float | None,
        typer.Option(
            "--ground-elev",
            help="Height of the ground above sea level in metres, for a flat site. For drones "
            "that record only a height above sea level (not DJI): the height above the ground "
            "is the photo's GPS height minus this",
        ),
    ] = None,
) -> None:
    """Check overlap, coverage, blur, gimbal, altitude and timing of survey photos."""
    if takeoff is not None and dem is None:
        raise typer.BadParameter("--takeoff only makes sense together with --dem")
    takeoff_lonlat = None
    if takeoff is not None:
        lat, lon = parse_latlon(takeoff)
        takeoff_lonlat = (lon, lat)
    profile = None
    if drone is not None:
        profile = load_profiles().get(drone)
        if profile is None:
            raise typer.BadParameter(f"unknown drone {drone!r}; see `avispria drones`")
    try:
        report, skipped, ground = run_qa(
            folder,
            profile,
            recursive=recursive,
            dem_path=dem,
            takeoff=takeoff_lonlat,
            ground_elevation_m=ground_elev,
        )
    except PlanningError as exc:
        typer.secho(f"Cannot use the elevation model: {exc}", fg=typer.colors.RED)
        raise typer.Exit(1) from exc
    s = report.stats
    if s["photos_total"] == 0 and not skipped:
        typer.secho(f"No photos directly in {folder}", fg=typer.colors.YELLOW)
        hints = [] if recursive else photo_subfolders(folder)
        if hints:
            typer.echo("Photos were found in these subfolders:")
            for sub, count in hints:
                typer.echo(f"  {sub} ({count} photos)")
            typer.echo("Point qa at one of them, or add --recursive to include them all.")
        raise typer.Exit(1)
    typer.echo(f"photos: {int(s['photos_total'])} found, {int(s['photos_used'])} used")
    for name, reason in skipped:
        typer.secho(f"  skipped {name}: {reason}", fg=typer.colors.YELLOW)
    if "gsd_cm_median" in s:
        if "ground_elev_m" in s:  # set only when no elevation model was given
            above = f"the ground (taken as {s['ground_elev_m']:.1f} m above sea level)"
        elif s["terrain_aware"]:
            above = "the surface"
        else:
            above = "takeoff"
        typer.echo(
            f"height {s['altitude_m_median']:.1f} m above {above}   "
            f"GSD {s['gsd_cm_median']:.2f} cm/px"
        )
        if ground is not None and ground.agl_m:
            how = (
                "height differences from the takeoff point"
                if ground.mode == "takeoff"
                else "photo altitudes compared with the model"
            )
            typer.echo(
                f"terrain used for {int(s['terrain_photos'])} of {int(s['photos_used'])} photos "
                f"({how})"
            )
        if "front_overlap_median" in s or "side_overlap_median" in s:
            parts = []
            for label, key in (("front", "front_overlap"), ("side", "side_overlap")):
                if f"{key}_median" in s:
                    parts.append(
                        f"{label} {s[f'{key}_median'] * 100:.0f}% typical, "
                        f"{s[f'{key}_p10'] * 100:.0f}% at the low end"
                    )
            typer.echo("overlap       " + "   ".join(parts))
        typer.echo(
            f"area seen by {int(s['min_views'])}+ photos: {s['area_pct_min_views']:.0f}%   "
            f"by {int(s['good_views'])}+: {s['area_pct_good_views']:.0f}%   "
            f"mean views {s['views_mean']:.1f}"
        )
    if "interval_s_median" in s:
        typer.echo(
            f"photo interval median {s['interval_s_median']:.1f} s "
            f"(min {s['interval_s_min']:.1f}, max {s['interval_s_max']:.1f})"
        )
    for p in report.photos:
        prev = "  -" if p.overlap_prev is None else f"{p.overlap_prev * 100:3.0f}"
        best = "  -" if p.best_overlap is None else f"{p.best_overlap * 100:3.0f}"
        typer.echo(f"  {p.name:34} overlap prev {prev}%  best {best}%")
    if csv_out is not None:
        csv_out.write_text(report_csv(report), encoding="utf-8")
        typer.echo(f"wrote {csv_out}")
    if report.issues:
        print_issues(report.issues)
    if any(i.level == "error" for i in report.issues):
        raise typer.Exit(1)


@app.command("camera-from-photo")
def camera_from_photo(
    photo: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    key: Annotated[str, typer.Option(help="Profile key to use in the snippet")] = "my-drone",
) -> None:
    """Print a camera profile (TOML) derived from an original photo's EXIF."""
    try:
        typer.echo(camera_toml(photo, key), nl=False)
    except (ExifError, ValueError) as exc:
        typer.secho(f"cannot derive camera: {exc}", fg=typer.colors.RED)
        raise typer.Exit(1) from exc
