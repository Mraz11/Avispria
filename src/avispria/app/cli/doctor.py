# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The `doctor` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from avispria.app.cli._base import app
from avispria.app.doctor import DoctorDetails, DoctorReport, collect_details, run_doctor
from avispria.core.feasibility import gb

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
    webodm = next((e for e in r.engines if e.name == "WebODM" and e.reachable), None)
    node = next((e for e in r.engines if e.name == "Processing node" and e.reachable), None)
    if webodm is not None and webodm.reachable:
        typer.secho(f"  WebODM     running at {webodm.url}", fg=typer.colors.GREEN)
    elif node is not None and node.reachable:
        typer.secho(
            f"  Engine     processing node at {node.url} ({node.detail})", fg=typer.colors.GREEN
        )
    else:
        typer.secho("  WebODM     not found running on this computer", fg=typer.colors.YELLOW)
        typer.echo("             If it is not installed: https://webodm.org/download (free).")
        typer.echo("             If it is installed, start it and run `avispria doctor` again,")
        typer.echo("             or give its address: avispria doctor --webodm-url http://...")
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
    webodm_url: Annotated[
        str | None, typer.Option(help="WebODM address if it is not found automatically")
    ] = None,
    details: Annotated[
        bool, typer.Option("--details", help="List WebODM services and its processing nodes")
    ] = False,
) -> None:
    """Check this computer, and whether it can process a photo folder."""
    mp = 1e9 if full_resolution else None
    report = run_doctor(
        workdir, folder, recursive=recursive, processing_mp=mp, webodm_url=webodm_url
    )
    _print_doctor(report, workdir.resolve())
    if details:
        _print_details(collect_details(report.engines))
    if report.assessment is not None and report.assessment.verdict == "not-possible":
        raise typer.Exit(1)


def _print_details(d: DoctorDetails) -> None:
    typer.echo("")
    typer.secho("Details", bold=True)
    if not d.services:
        typer.echo("  No WebODM-related programs are listening on this computer.")
    for name, pid, host, port, what in d.services:
        typer.echo(f"  {name} (pid {pid})  {host}:{port}  ->  {what}")
    if d.api is None:
        return
    typer.echo(f"  WebODM API at {d.api_url}")
    if d.api.needs_login:
        typer.secho(
            "    needs a login (Avispria will ask for it when processing)", fg=typer.colors.YELLOW
        )
    elif d.api.error:
        typer.secho(f"    did not answer: {d.api.error}", fg=typer.colors.YELLOW)
    elif not d.api.nodes:
        typer.secho(
            f"    answered HTTP {d.api.status} but listed no processing nodes",
            fg=typer.colors.YELLOW,
        )
    for node in d.api.nodes:
        state = "online" if node.get("online") else "offline"
        engine = f"{node.get('engine', '')} {node.get('engine_version', '')}".strip()
        typer.echo(
            f"    processing node {node.get('label') or node.get('id')}: "
            f"{node.get('hostname')}:{node.get('port')}, {state}, {engine or 'engine unknown'}"
        )
