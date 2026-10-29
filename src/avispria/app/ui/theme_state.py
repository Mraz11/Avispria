# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Light and dark mode for one open page.

The browser decides the first mode (its saved choice, else the system setting) before anything is
drawn, then tells the server by an event; the server never waits for the browser's answer. A
choice made here is saved in the browser. Charts register a listener to redraw in the new colours.
"""

from __future__ import annotations

from collections.abc import Callable

from nicegui import ui

from avispria.app.ui.theme import DARK, LIGHT, STORAGE_KEY, Palette

Listener = Callable[[Palette], bool | None]  # returning False removes the listener


class ThemeState:
    def __init__(self, dark_mode: ui.dark_mode) -> None:
        self.dark_mode = dark_mode
        self.dark = False
        self._listeners: list[Listener] = []

    @property
    def palette(self) -> Palette:
        return DARK if self.dark else LIGHT

    def on_change(self, listener: Listener) -> None:
        self._listeners.append(listener)

    def set_dark(self, dark: bool, *, remember: bool = True) -> None:
        changed = dark != self.dark
        self.dark = dark
        self.dark_mode.value = dark
        if remember:
            mode = "dark" if dark else "light"
            ui.run_javascript(
                f"try {{ localStorage.setItem('{STORAGE_KEY}', '{mode}'); }} catch (e) {{}}"
                f"document.documentElement.setAttribute('data-theme', '{mode}');"
            )
        if changed:
            self._listeners = [x for x in self._listeners if x(self.palette) is not False]

    def toggle(self) -> None:
        self.set_dark(not self.dark)

    def from_browser(self, value: object) -> None:
        """The browser says which mode it is showing (sent once when the page connects)."""
        self.set_dark(value == "dark", remember=False)


def attach(state: ThemeState) -> None:
    ui.context.client.avispria_theme = state  # type: ignore[attr-defined]


def current() -> ThemeState | None:
    """The theme of the page being built or handled, if it has a frame."""
    return getattr(ui.context.client, "avispria_theme", None)


def current_palette() -> Palette:
    state = current()
    return LIGHT if state is None else state.palette
