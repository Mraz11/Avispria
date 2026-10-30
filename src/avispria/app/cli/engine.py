# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The `engine` command: find and check the photogrammetry engine."""

from __future__ import annotations

from typing import Annotated

import typer

from avispria.adapters import system_probe
from avispria.adapters.engine import EngineError, connect, describe
from avispria.app.cli._base import app
from avispria.core.feasibility import gb

KEY_OPTIONS = ("dsm", "dtm", "fast-orthophoto", "pc-quality", "feature-quality", "rolling-shutter")


@app.command()
def engine(
    url: Annotated[
        str | None, typer.Option(help="Engine address (default: find WebODM's engine)")
    ] = None,
    token: Annotated[
        str | None, typer.Option(help="Engine access token (default: read from the engine)")
    ] = None,
) -> None:
    """Find the processing engine (NodeODX), connect, and show what it supports."""
    if url is None:
        local = system_probe.find_engine()
        if local is None:
            typer.secho("No processing engine is running on this computer.", fg=typer.colors.RED)
            typer.echo("Start WebODM (it starts its engine), then run `avispria engine` again.")
            raise typer.Exit(1)
        url = local.url
        if token is None:
            token = local.token
        source = "read from the running engine (kept in memory only)"
        typer.echo(
            f"Engine found   nodeodx (pid {local.pid}) at {url}"
            if local.pid
            else f"Engine found   processing node at {url}"
        )
    else:
        source = "given on the command line"
        typer.echo(f"Engine         {url}")
    typer.echo(f"Access token   {source if token else 'none'}")
    try:
        info = describe(connect(url, token))
    except EngineError as exc:
        typer.secho(f"Cannot use the engine: {exc}", fg=typer.colors.RED)
        raise typer.Exit(1) from exc
    typer.secho(
        f"Connected      {info.engine} {info.engine_version} (API {info.api_version})",
        fg=typer.colors.GREEN,
    )
    memory = "" if info.total_memory_gb is None else f", {gb(info.total_memory_gb)} GB memory"
    typer.echo(f"Resources      {info.cpu_cores or '?'} CPU cores{memory}")
    limit = "no limit" if info.max_images is None else f"max {info.max_images} images per task"
    typer.echo(f"Queue          {info.queue} task(s) waiting or running; {limit}")
    available = [o for o in KEY_OPTIONS if o in info.options]
    missing = [o for o in KEY_OPTIONS if o not in info.options]
    typer.echo(f"Options        {len(info.options)} supported, including: {', '.join(available)}")
    if missing:
        typer.secho(
            f"               not offered by this engine: {', '.join(missing)}",
            fg=typer.colors.YELLOW,
        )
