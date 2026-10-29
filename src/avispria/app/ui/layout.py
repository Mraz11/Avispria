# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The frame around every screen: header with logo and navigation, content, footer."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from nicegui import ui

from avispria.app.ui.theme import THEME_BOOT_JS, tokens_css
from avispria.app.ui.theme_state import ThemeState, attach
from avispria.core.version import __version__

ASSETS = Path(__file__).parent / "assets"
COMPONENT_CSS = (ASSETS / "avispria.css").read_text(encoding="utf-8")
TAGLINE = "Canopy structure and change, seen from above."

NAV = (
    ("Start", "/"),
    ("Check my photos", "/check"),
    ("Plan a flight", "/plan"),
    ("Make maps", "/process"),
)


def logo(classes: str = "") -> None:
    """The logo: the original colours on light pages, the dark-mode variant on dark ones."""
    ui.element("img").props('src="/assets/logo.png" alt="Avispria logo"').classes(
        f"av-logo av-logo-light {classes}"
    ).mark("logo-light")
    ui.element("img").props('src="/assets/logo-dark.png" alt=""').classes(
        f"av-logo av-logo-dark {classes}"
    ).mark("logo-dark")


def _theme_button(state: ThemeState) -> None:
    button = (
        ui.button(icon="dark_mode", on_click=state.toggle)
        .props('flat round dense aria-label="Switch between light and dark mode"')
        .classes("av-theme")
        .mark("theme-toggle")
    )
    button.tooltip("Light or dark")

    def show_icon(_palette: object) -> None:
        button.props(f"icon={'light_mode' if state.dark else 'dark_mode'}")
        button.update()

    state.on_change(show_icon)


@contextmanager
def frame(title: str) -> Iterator[None]:
    ui.page_title(f"{title} - Avispria")
    ui.add_head_html(f"<script>{THEME_BOOT_JS}</script>")  # the right colours from the first paint
    ui.add_css(tokens_css(quasar=True) + COMPONENT_CSS)
    state = ThemeState(ui.dark_mode(False))
    attach(state)
    ui.on("avispria_theme", lambda event: state.from_browser(event.args))
    ui.context.client.on_connect(
        lambda: ui.run_javascript(
            "emitEvent('avispria_theme', document.documentElement.getAttribute('data-theme'))"
        )
    )
    with ui.header().classes("items-center gap-3 no-wrap"):
        with ui.link(target="/").classes("av-brand row items-center gap-2 no-wrap"):
            logo()
            ui.label("Avispria").classes("av-brand-name")
        ui.label(TAGLINE).classes("av-tagline gt-sm")
        ui.space()
        for name, path in NAV:
            ui.link(name, path).classes("av-nav" + (" av-nav-active" if name == title else ""))
        _theme_button(state)
    with ui.column().classes("w-full max-w-5xl mx-auto p-4 gap-4 pb-16"):
        ui.label(title).classes("text-2xl font-bold")
        yield
    with ui.footer().classes("justify-center text-xs"):
        ui.label(
            f"Avispria {__version__} - early version, not yet flight-tested. "
            "You are responsible for every flight; check local rules."
        )
