# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The `ui` command: open the window-based interface."""

from __future__ import annotations

from typing import Annotated

import typer

from avispria.app.cli._base import app


@app.command()
def ui(
    port: Annotated[int, typer.Option(help="Port to listen on (next free one if taken)")] = 8080,
    no_browser: Annotated[bool, typer.Option(help="Do not open the browser automatically")] = False,
) -> None:
    """Open Avispria in your web browser (everything stays on this computer)."""
    from avispria.app.ui.app import run_app  # imported late: it loads the web framework

    typer.echo("Starting Avispria... close this window or press Ctrl+C to stop it.")
    run_app(port=port, open_browser=not no_browser)
