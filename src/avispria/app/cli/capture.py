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
from avispria.app.cli._base import app, print_issues


@app.command()
def qa(
    folder: Annotated[Path, typer.Argument(exists=True, file_okay=False, help="Photo folder")],
    drone: Annotated[str | None, typer.Option(help="Profile to use; default: from EXIF")] = None,
    csv_out: Annotated[Path | None, typer.Option("--csv", help="Per-photo CSV report")] = None,
    recursive: Annotated[
        bool, typer.Option("--recursive", "-r", help="Include photos in subfolders")
    ] = False,
) -> None:
    """Check overlap, coverage, blur, gimbal, altitude and timing of survey photos."""
    profile = None
    if drone is not None:
        profile = load_profiles().get(drone)
        if profile is None:
            raise typer.BadParameter(f"unknown drone {drone!r}; see `avispria drones`")
    report, skipped = run_qa(folder, profile, recursive=recursive)
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
        typer.echo(
            f"height {s['altitude_m_median']:.1f} m above takeoff   "
            f"GSD {s['gsd_cm_median']:.2f} cm/px"
        )
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
