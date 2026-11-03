# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Step 1 of Plan a flight: what do you want to capture? Each answer sets its own settings."""

from __future__ import annotations

from typing import Any

from nicegui import events, ui

from avispria.app.ui.pages.plan_form_parts import card, show_when
from avispria.core.scan_types import DEFAULT_TYPE, SCAN_TYPES, ScanType

INTRO = (
    "This decides how the camera points, how the drone flies and what you enter below. Pick the "
    "one that matches the result you want; the settings below are set to what suits it."
)


class TypeCard:
    """The chooser. Expects the host to have the widgets ``_apply_preset`` sets."""

    scan_type: ui.radio

    def _type_card(self) -> None:
        with card("1. What do you want to capture?"):
            ui.label(INTRO).classes("text-sm av-muted")
            self.scan_type = (
                ui.radio({k: t.title for k, t in SCAN_TYPES.items()}, value=DEFAULT_TYPE)
                .props("color=primary")
                .classes("text-base font-medium")
                .mark("scan-type")
            )
            for key, kind in SCAN_TYPES.items():
                with show_when(self.scan_type, key, gap="gap-1").classes(
                    "av-note-info p-3 rounded"
                ):
                    self._describe(key, kind)
        self.scan_type.on_value_change(self._type_changed)

    @staticmethod
    def _describe(key: str, kind: ScanType) -> None:
        ui.label(kind.summary).classes("font-medium").mark(f"type-summary-{key}")
        for label, text in (
            ("Good for", kind.good_for),
            ("What happens", kind.how),
            ("You tell Avispria", kind.you_tell),
            ("Afterwards", kind.after),
        ):
            with ui.row().classes("gap-2 no-wrap items-baseline"):
                ui.label(f"{label}:").classes("text-sm font-bold")
                ui.label(text).classes("text-sm")

    def _type_changed(self, event: events.ValueChangeEventArguments) -> None:
        kind = SCAN_TYPES.get(str(event.value))
        if kind is None:
            return
        self._apply_preset(kind)
        ui.notify(f"Settings set to what suits: {kind.title}", type="info")

    def _apply_preset(self, kind: ScanType) -> None:
        """Set the fields to what ``kind`` recommends (the person can change them afterwards)."""
        host: Any = self
        if kind.is_area:
            host.target_kind.set_value("resolution")
            host.target.set_value(kind.gsd_cm)
            host.front.set_value(kind.front_percent)
            host.side.set_value(kind.side_percent)
            host.crosshatch.set_value(kind.crosshatch)
            if kind.tilt_deg:
                host.tilt.set_value(kind.tilt_deg)
        else:
            host.obj_front.set_value(kind.front_percent)
            host.obj_side.set_value(kind.side_percent)
