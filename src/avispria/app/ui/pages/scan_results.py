# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""What Plan a flight shows after planning 'a 3D model of one object' (or when it was blocked)."""

from __future__ import annotations

from pathlib import Path

from nicegui import ui

from avispria.app.ui.pages.plan_results import missions_section
from avispria.app.ui.scan_job import ScanJobResult
from avispria.app.ui.views import Tile, Verdict, explain_issues
from avispria.app.ui.views_results import plan_verdict
from avispria.app.ui.widgets import issue_cards, tile_row, verdict_banner
from avispria.core.scan import ScanPlan


def scan_tiles(plan: ScanPlan, object_height_m: float, object_radius_m: float) -> list[Tile]:
    s = plan.summary
    minutes = sum(m.estimated_duration_s for m in plan.missions) / 60.0
    n = len(plan.missions)
    return [
        Tile(
            "The object",
            f"{object_height_m:g} m tall, radius {object_radius_m:g} m",
            f"rings {s.ring_radius_m:g} m from its axis",
        ),
        Tile(
            "Photos",
            f"{s.photos} photos in {len(s.rings)} rings",
            f"and {s.cap_photos} straight down over the top" if s.cap_photos else "no top cap",
        ),
        Tile(
            "Resolution",
            f"{s.gsd_cm_best:.2f} to {s.gsd_cm_worst:.2f} cm/px",
            "on the object, at the centre of a picture",
        ),
        Tile(
            "Flight",
            f"{n} mission{'s' if n != 1 else ''}, about {minutes:.0f} min",
            "a ring is never split between two missions unless it is too big for one"
            if n > 1
            else "one battery",
        ),
    ]


def ring_rows(plan: ScanPlan) -> list[dict[str, str]]:
    return [
        {
            "ring": str(k),
            "height": f"{r.height_m:.1f} m",
            "tilt": f"{r.pitch_deg:+.0f} degrees",
            "looks_at": f"{r.centre_height_m:.1f} m up the object",
            "photos": str(r.photos),
            "gsd": f"{r.gsd_cm:.2f} cm/px",
        }
        for k, r in enumerate(plan.summary.rings, start=1)
    ]


def show_scan(box: ui.column, result: ScanJobResult, out_dir: Path) -> None:
    with box:
        if result.outputs is None or result.request is None:
            verdict_banner(
                Verdict("problem", "This plan cannot be flown as asked", "Nothing was saved.")
            )
            ui.label("Why").classes("text-lg font-bold")
            issue_cards(explain_issues(result.blocked))
            return
        outputs, request = result.outputs, result.request
        verdict_banner(plan_verdict(outputs.warnings))
        with ui.card().classes("w-full av-note-info").mark("scan-photo-note"):
            ui.label(
                "At every photo point the drone stops, waits a moment and takes one photo facing "
                "the object. The camera needs no setting."
            ).classes("font-medium")
        tile_row(scan_tiles(outputs.plan, request.object_height_m, request.object_radius_m))
        ui.label("The rings").classes("text-lg font-bold")
        ui.label(
            "Camera height is above the ground at the object. The camera tilts up at the bottom "
            "and down at the top so it keeps looking at the object."
        ).classes("text-sm av-muted")
        columns = [
            {"name": "ring", "label": "Ring", "field": "ring", "align": "left"},
            {"name": "height", "label": "Camera height", "field": "height"},
            {"name": "tilt", "label": "Camera tilt", "field": "tilt"},
            {"name": "looks_at", "label": "Looks at", "field": "looks_at"},
            {"name": "photos", "label": "Photos", "field": "photos"},
            {"name": "gsd", "label": "Resolution", "field": "gsd"},
        ]
        ui.table(columns=columns, rows=ring_rows(outputs.plan), row_key="ring").classes(
            "w-full"
        ).mark("scan-rings")
        missions_section(outputs.plan.missions, outputs.kmz_paths, outputs.warnings, out_dir)
