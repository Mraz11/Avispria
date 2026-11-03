# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Small building blocks shared by the Plan a flight form's cards."""

from __future__ import annotations

from nicegui import ui


def card(
    title: str, *, radio: ui.radio | None = None, kinds: tuple[str, ...] | None = None
) -> ui.column:
    """A titled card. With ``radio`` and ``kinds`` it is only visible for those scan types."""
    with ui.card().classes("w-full") as outer:
        ui.label(title).classes("text-lg font-bold")
        inner = ui.column().classes("w-full gap-3")
    if radio is not None and kinds is not None:
        outer.bind_visibility_from(radio, "value", backward=lambda v: v in kinds)
    return inner


def number(
    label: str, value: float, marker: str, width: str = "w-40", **limits: float
) -> ui.number:
    field = ui.number(label, value=value, **limits).props("outlined dense").mark(marker)
    return field.classes(width)


def text(label: str, marker: str, value: str = "", width: str = "w-full", **kw: str) -> ui.input:
    field = ui.input(label, value=value, **kw).props("outlined dense").classes(width)
    return field.mark(marker)


def show_when(mode: ui.radio, wanted: str, gap: str = "gap-3") -> ui.column:
    """A column that is only visible while the radio group has the value ``wanted``."""
    column = ui.column().classes(f"w-full {gap}")
    column.bind_visibility_from(mode, "value", backward=lambda v: v == wanted)
    return column


def show_when_in(radio: ui.radio, wanted: tuple[str, ...], gap: str = "gap-3") -> ui.column:
    """A column that is only visible while the radio group has one of the values in ``wanted``."""
    column = ui.column().classes(f"w-full {gap}")
    column.bind_visibility_from(radio, "value", backward=lambda v: v in wanted)
    return column
