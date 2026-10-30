# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Mission-file commands: inspect, lint, sheet, prepare-copy."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Annotated

import typer

from avispria.app.cli._base import app, print_issues
from avispria.app.workflow import PlanBlockedError, prepare_copy
from avispria.core.wpml.kmz import KmzError
from avispria.core.wpml.lint import LintLimits, lint_kmz
from avispria.core.wpml.reader import read_mission
from avispria.core.wpml.sheet import plan_hash, spot_check_csv


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
    print_issues(issues)
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


@app.command("prepare-copy")
def prepare_copy_cmd(
    kmz: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    out: Annotated[Path, typer.Option(help="Folder to create the copy layout in")],
    slot: Annotated[
        str | None,
        typer.Option(
            help="GUID of the DJI Fly placeholder mission to replace. Leave it out to make a "
            "NEW mission id (an experiment: does DJI Fly list a mission it did not create?)"
        ),
    ] = None,
) -> None:
    """Create <GUID>/<GUID>.kmz to copy over a DJI Fly placeholder mission (manual install)."""
    brand_new = slot is None
    if slot is None:
        slot = str(uuid.uuid4()).upper()
    try:
        target = prepare_copy(kmz, slot, out)
    except PlanBlockedError as exc:
        typer.secho("File failed lint; not prepared:", fg=typer.colors.RED)
        print_issues(exc.issues)
        raise typer.Exit(1) from exc
    except ValueError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(1) from exc
    typer.secho(f"Ready: {target}", fg=typer.colors.GREEN)
    if brand_new:
        typer.echo(
            "A NEW mission id was made. Copy the whole folder into "
            "Android/data/dji.go.v5/files/waypoint/ on the phone, close DJI Fly completely "
            "and open it again. DJI Fly may not list a mission it did not create itself: "
            "if it does not, delete the folder and use a placeholder mission instead."
        )
    else:
        typer.echo(
            "Copy it over Android/data/dji.go.v5/files/waypoint/"
            f"{slot}/{slot}.kmz on the phone (keep a backup of the original first)."
        )
