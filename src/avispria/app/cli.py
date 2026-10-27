# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Command-line interface."""

import typer

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


@app.command()
def version() -> None:
    """Print the Avispria version."""
    typer.echo(f"avispria {__version__}")


@app.command()
def plan() -> None:
    """Plan a survey mission (not implemented yet)."""
    typer.echo("not implemented")
    raise typer.Exit(code=2)
