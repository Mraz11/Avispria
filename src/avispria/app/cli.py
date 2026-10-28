# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Command-line interface. Thin: parsing, printing and exit codes only."""

from __future__ import annotations

import time
from fractions import Fraction
from pathlib import Path
from typing import Annotated

import typer

from avispria.adapters.exif import ExifError
from avispria.adapters.photos import photo_subfolders
from avispria.adapters.profiles import load_profiles
from avispria.app.capture_workflow import camera_toml, report_csv, run_qa
from avispria.app.doctor import DoctorReport, run_doctor
from avispria.app.workflow import PlanBlockedError, PlanOptions, prepare_copy, run_plan
from avispria.core.errors import PlanningError
from avispria.core.feasibility import gb
from avispria.core.geometry import AoiError
from avispria.core.mission import PhotoMode
from avispria.core.safety import Issue, SafetyLimits
from avispria.core.version import __version__
from avispria.core.wpml.kmz import KmzError
from avispria.core.wpml.lint import LintLimits, lint_kmz
from avispria.core.wpml.reader import read_mission
from avispria.core.wpml.sheet import plan_hash, spot_check_csv

app = typer.Typer(
    name="avispria",
    help=(
        "Avispria: offline-first planning and QA for consumer RGB drone surveys. "
        "Canopy structure and change, seen from above."
    ),
    no_args_is_help=True,
    add_completion=False,
)


def _print_issues(issues: list[Issue]) -> None:
    for i in issues:
        colour = typer.colors.RED if i.level == "error" else typer.colors.YELLOW
        typer.secho(f"  {i.level.upper():7} {i.code}  {i.message}", fg=colour)


def _parse_latlon(text: str) -> tuple[float, float]:
    try:
        lat_s, lon_s = text.split(",")
        return float(lat_s), float(lon_s)
    except ValueError as exc:
        raise typer.BadParameter("use LAT,LON, e.g. 23.8103,90.4125") from exc


def _parse_shutter(text: str) -> float:
    try:
        value = float(Fraction(text))
    except (ValueError, ZeroDivisionError) as exc:
        raise typer.BadParameter("use a fraction like 1/1000 or seconds like 0.001") from exc
    if value <= 0:
        raise typer.BadParameter("shutter must be positive")
    return value


@app.command()
def version() -> None:
    """Print the Avispria version."""
    typer.echo(f"avispria {__version__}")


@app.command()
def drones() -> None:
    """List known aircraft profiles and camera modes."""
    for p in load_profiles().values():
        state = "verified" if p.verified else "UNVERIFIED"
        typer.echo(f"{p.key:12} {p.name:16} modes: {', '.join(p.modes)}  [{state}]")


@app.command()
def inspect(kmz: Annotated[Path, typer.Argument(exists=True, dir_okay=False)]) -> None:
    """Show what a DJI Fly mission file contains."""
    try:
        m = read_mission(kmz.read_bytes())
    except KmzError as exc:
        typer.secho(f"cannot read {kmz.name}: {exc}", fg=typer.colors.RED)
        raise typer.Exit(1) from exc
    photos = sum(1 for w in m.waypoints for a in w.actions if a.func == "takePhoto")
    typer.echo(f"file          {kmz.name}  (plan {plan_hash(kmz.read_bytes())})")
    typer.echo(f"namespace     {m.namespace}")
    typer.echo(f"drone enum    {m.drone_enum} / {m.drone_sub_enum}")
    typer.echo(f"height mode   {m.height_mode}")
    typer.echo(f"waypoints     {len(m.waypoints)}  (photo actions: {photos})")
    if m.waypoints:
        heights = [w.height_m for w in m.waypoints]
        typer.echo(f"heights       {min(heights):g} .. {max(heights):g} m above takeoff")
    typer.echo(f"speed         {m.auto_speed_ms:g} m/s")
    typer.echo(f"on finish     {m.finish_action}   on signal lost: {m.rc_lost_action}")


@app.command()
def lint(
    kmz: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    max_waypoints: Annotated[int, typer.Option(help="Waypoint cap to enforce")] = 99,
) -> None:
    """Check a mission file independently. Exit code 1 if any error is found."""
    issues = lint_kmz(kmz.read_bytes(), LintLimits(max_waypoints=max_waypoints))
    if not issues:
        typer.secho(f"{kmz.name}: OK", fg=typer.colors.GREEN)
        return
    _print_issues(issues)
    if any(i.level == "error" for i in issues):
        raise typer.Exit(1)


@app.command()
def sheet(
    kmz: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    out: Annotated[Path | None, typer.Option(help="CSV path (default: print)")] = None,
) -> None:
    """Write the RC spot-check sheet for a mission."""
    text = spot_check_csv(kmz.read_bytes())
    if out is None:
        typer.echo(text, nl=False)
    else:
        out.write_text(text, encoding="utf-8")
        typer.echo(f"wrote {out}")


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
    name: str = "avispria",
) -> None:
    """Plan a survey and write DJI Fly mission files, spot-check sheets and a report."""
    lat, lon = _parse_latlon(takeoff)
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
        shutter_s=_parse_shutter(shutter),
        wind_ms=wind,
        limits=SafetyLimits(
            max_height_above_takeoff_m=max_height,
            max_height_above_ground_m=max_height,
            max_distance_from_takeoff_m=max_distance,
            max_flight_time_s=max_flight_min * 60.0,
        ),
        straight_lines=not curved,
        name=name,
    )
    try:
        res = run_plan(aoi, template, profile, opts, out, now_ms=int(time.time() * 1000))
    except PlanBlockedError as exc:
        typer.secho("Plan blocked; nothing was written:", fg=typer.colors.RED)
        _print_issues(exc.issues)
        raise typer.Exit(1) from exc
    except (PlanningError, AoiError, KmzError, ValueError) as exc:
        typer.secho(f"Cannot plan: {exc}", fg=typer.colors.RED)
        raise typer.Exit(1) from exc

    s = res.result.summary
    typer.secho(f"Planned {len(res.kmz_paths)} mission(s) into {out}", fg=typer.colors.GREEN)
    typer.echo(
        f"  height {s.agl_m:.1f} m above surface  GSD {s.gsd_m * 100:.2f} cm/px  "
        f"lines {s.strips} @ {s.line_spacing_m:.1f} m  photos every {s.photo_spacing_m:.1f} m"
    )
    typer.echo(f"  speed {s.speed.speed_ms:.1f} m/s (limited by {s.speed.binding})")
    typer.echo(f"  terrain: {s.terrain_source}; takeoff elevation: {s.takeoff_elevation_source}")
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
        _print_issues(res.warnings)


@app.command("prepare-copy")
def prepare_copy_cmd(
    kmz: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    slot: Annotated[str, typer.Option(help="GUID of the DJI Fly dummy mission to replace")],
    out: Annotated[Path, typer.Option(help="Folder to create the copy layout in")],
) -> None:
    """Create <GUID>/<GUID>.kmz to copy over a DJI Fly dummy mission (manual install)."""
    try:
        target = prepare_copy(kmz, slot, out)
    except PlanBlockedError as exc:
        typer.secho("File failed lint; not prepared:", fg=typer.colors.RED)
        _print_issues(exc.issues)
        raise typer.Exit(1) from exc
    except ValueError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(1) from exc
    typer.secho(f"Ready: {target}", fg=typer.colors.GREEN)
    typer.echo(
        "Copy it over Android/data/dji.go.v5/files/waypoint/"
        f"{slot}/{slot}.kmz on the phone (keep a backup of the original first)."
    )


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
        _print_issues(report.issues)
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


_VERDICT_TEXT = {
    "ok": ("This computer can process these photos.", typer.colors.GREEN),
    "slow": ("Possible, but slow: it will rely on virtual memory.", typer.colors.YELLOW),
    "not-possible": ("Not possible on this computer as it is.", typer.colors.RED),
}


def _print_doctor(r: DoctorReport, workdir: Path) -> None:
    s = r.system
    typer.secho("Avispria system check", bold=True)
    typer.echo(f"  Computer   {s.os_name}, {s.cpu_logical} CPU threads")
    typer.echo(
        f"  Memory     {s.ram_total_gb:.1f} GB total, {s.ram_available_gb:.1f} GB free now, "
        f"{s.swap_total_gb:.1f} GB virtual memory"
    )
    typer.echo(f"  Disk       {s.disk_free_gb:.0f} GB free at {workdir}")
    webodm = next((e for e in r.engines if e.name == "WebODM"), None)
    node = next((e for e in r.engines if e.name == "Processing node"), None)
    if webodm is not None and webodm.reachable:
        typer.secho(f"  WebODM     running at {webodm.url}", fg=typer.colors.GREEN)
    elif node is not None and node.reachable:
        typer.secho(
            f"  Engine     processing node at {node.url} ({node.detail})", fg=typer.colors.GREEN
        )
    else:
        typer.secho("  WebODM     not found on this computer", fg=typer.colors.YELLOW)
        typer.echo("             Install it free from https://webodm.org/download and start it,")
        typer.echo("             then run `avispria doctor` again.")
    if r.assessment is None or r.job is None:
        if r.unreadable:
            typer.secho(
                f"  {r.unreadable} photo file(s) could not be read.", fg=typer.colors.YELLOW
            )
        return
    j, a = r.job, r.assessment
    typer.echo("")
    typer.echo(
        f"Photos  {j.photos} photos, {j.native_mp:.1f} MP each, {j.input_gb:.2f} GB "
        f"(processed at {a.processing_mp:g} MP)"
    )
    typer.echo(
        f"Needs   about {gb(a.ram_gb)} GB memory and {gb(a.disk_gb)} GB free disk (estimate)"
    )
    text, colour = _VERDICT_TEXT[a.verdict]
    typer.secho(f"Result  {text}", fg=colour, bold=True)
    for reason in a.reasons:
        typer.echo(f"        - {reason}")
    if a.options:
        typer.echo("What you can do:")
        for n, o in enumerate(a.options, start=1):
            mark = ("works, but slow" if o.slow else "works") if o.fits else "not enough alone"
            need = "" if o.ram_gb is None else f"about {gb(o.ram_gb)} GB, "
            typer.echo(f"  {n}. {o.description}  [{need}{mark}]")


@app.command()
def doctor(
    folder: Annotated[
        Path | None, typer.Argument(exists=True, file_okay=False, help="Photo folder to check")
    ] = None,
    workdir: Annotated[Path, typer.Option(help="Where processing will store its files")] = Path(
        "."
    ),
    recursive: Annotated[bool, typer.Option("--recursive", "-r")] = False,
    full_resolution: Annotated[
        bool, typer.Option(help="Process photos at full size instead of 12 MP")
    ] = False,
) -> None:
    """Check this computer, and whether it can process a photo folder."""
    mp = 1e9 if full_resolution else None
    report = run_doctor(workdir, folder, recursive=recursive, processing_mp=mp)
    _print_doctor(report, workdir.resolve())
    if report.assessment is not None and report.assessment.verdict == "not-possible":
        raise typer.Exit(1)
