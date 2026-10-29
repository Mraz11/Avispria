# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Start the window-based interface: register the screens and run the local web server."""

from __future__ import annotations

import socket

from nicegui import app, ui

from avispria.app.ui.layout import ASSETS
from avispria.app.ui.pages.check import check_page
from avispria.app.ui.pages.home import home_page
from avispria.app.ui.pages.plan import plan_page
from avispria.app.ui.pages.process import process_page

HOST = "127.0.0.1"  # this computer only: nothing is reachable from the network


def register_pages() -> None:
    """Attach every screen to its address. Called once per run (and once per test)."""
    app.add_static_files("/assets", ASSETS)  # the logo and the page icon
    ui.page("/")(home_page)
    ui.page("/check")(check_page)
    ui.page("/plan")(plan_page)
    ui.page("/process")(process_page)


def find_free_port(start: int, tries: int = 20) -> int:
    """``start`` if it is free, else the next free port above it."""
    for port in range(start, start + tries):
        with socket.socket() as probe:
            try:
                probe.bind((HOST, port))
            except OSError:
                continue
            return port
    raise OSError(f"no free port between {start} and {start + tries - 1}")


def run_app(port: int = 8080, open_browser: bool = True) -> None:
    register_pages()
    ui.run(
        host=HOST,
        port=find_free_port(port),
        show=open_browser,
        reload=False,
        title="Avispria",
        favicon=ASSETS / "favicon.png",
    )
