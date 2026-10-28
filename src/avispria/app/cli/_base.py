# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared Typer app, helpers and small commands."""

from __future__ import annotations

from fractions import Fraction

import typer

from avispria.adapters.profiles import load_profiles
from avispria.core.safety import Issue
from avispria.core.version import __version__

app = typer.Typer(
    name="avispria",
    help=(
        "Avispria: offline-first planning and QA for consumer RGB drone surveys. "
        "Canopy structure and change, seen from above."
    ),
    no_args_is_help=True,
    add_completion=False,
)


def print_issues(issues: list[Issue]) -> None:
    for i in issues:
        colour = typer.colors.RED if i.level == "error" else typer.colors.YELLOW
        typer.secho(f"  {i.level.upper():7} {i.code}  {i.message}", fg=colour)


def parse_latlon(text: str) -> tuple[float, float]:
    try:
        lat_s, lon_s = text.split(",")
        return float(lat_s), float(lon_s)
    except ValueError as exc:
        raise typer.BadParameter("use LAT,LON, e.g. 23.8103,90.4125") from exc


def parse_shutter(text: str) -> float:
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
