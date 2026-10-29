# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The frame around every screen: header with navigation, content column, footer."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from nicegui import ui

from avispria.core.version import __version__

NAV = (
    ("Start", "/"),
    ("Check my photos", "/check"),
    ("Plan a flight", "/plan"),
    ("Make maps", "/process"),
)


@contextmanager
def frame(title: str) -> Iterator[None]:
    ui.page_title(f"{title} - Avispria")
    ui.colors(primary="#2e7d32", secondary="#546e7a")
    with ui.header(elevated=True).classes("items-center gap-4 bg-primary"):
        ui.label("Avispria").classes("text-xl font-bold")
        ui.label("Canopy structure and change, seen from above.").classes("text-sm opacity-80")
        ui.space()
        for name, path in NAV:
            ui.link(name, path).classes("text-white font-medium").style("text-decoration: none")
    with ui.column().classes("w-full max-w-5xl mx-auto p-4 gap-4 pb-16"):
        ui.label(title).classes("text-2xl font-bold")
        yield
    with ui.footer().classes("bg-gray-100 text-gray-700 text-xs justify-center"):
        ui.label(
            f"Avispria {__version__} - early version, not yet flight-tested. "
            "You are responsible for every flight; check local rules."
        )
