# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""What the Plan a flight screen shows once a plan exists (or was blocked)."""

from __future__ import annotations

from pathlib import Path

from nicegui import ui

from avispria.app.ui.charts import route_map
from avispria.app.ui.files import open_in_file_manager
from avispria.app.ui.plan_job import PlanJobResult
from avispria.app.ui.views import Verdict, explain_issues
from avispria.app.ui.views_results import plan_tiles, plan_verdict
from avispria.app.ui.widgets import echart, issue_cards, tile_row, verdict_banner

HOW_TO_FLY = (
    "Open DJI Fly, choose Waypoint Flight, add two points and save the mission. This creates "
    "a mission folder on your phone.",
    "Connect the phone to the computer and open that mission's folder: "
    "Android/data/dji.go.v5/files/waypoint/<long ID>/",
    "Copy one of the .kmz files shown above into it, renamed to the long ID, replacing the "
    "file that is there (keep a backup of the original).",
    "Reopen DJI Fly, open the mission and compare the number of waypoints and the heights with "
    "the spot-check sheet (a .csv next to each .kmz) before you take off.",
)


def show_plan(box: ui.column, result: PlanJobResult, out_dir: Path) -> None:
    with box:
        if result.outputs is None:
            verdict_banner(
                Verdict("problem", "This plan cannot be flown as asked", "Nothing was saved.")
            )
            ui.label("Why").classes("text-lg font-bold")
            issue_cards(explain_issues(result.blocked))
            return
        outputs = result.outputs
        plan = outputs.result
        verdict_banner(plan_verdict(outputs.warnings))
        if plan.summary.photo_interval_s is not None:
            with ui.card().classes("w-full bg-blue-50"):
                ui.label(
                    f"In DJI Fly, set the camera to timed shot every "
                    f"{plan.summary.photo_interval_s:.1f} seconds (or shorter) before you start."
                ).classes("font-medium")
        tile_row(plan_tiles(plan))
        ui.label("The route").classes("text-lg font-bold")
        ui.label(
            "The dashed line is your survey area; each coloured line is one mission (one "
            "battery). The route goes a little beyond the area so the turns happen outside it."
        ).classes("text-sm text-gray-600")
        if result.aoi is not None:
            echart(route_map(plan, result.aoi, result.takeoff, result.photos))
        ui.label("Missions").classes("text-lg font-bold")
        columns = [
            {"name": "file", "label": "File", "field": "file", "align": "left"},
            {"name": "waypoints", "label": "Waypoints", "field": "waypoints"},
            {"name": "minutes", "label": "Flying time", "field": "minutes"},
            {"name": "height", "label": "Highest point above takeoff", "field": "height"},
        ]
        rows = [
            {
                "file": path.name,
                "waypoints": len(m.waypoints),
                "minutes": f"about {m.estimated_duration_s / 60:.0f} min",
                "height": f"{max(w.height_m for w in m.waypoints):.0f} m",
            }
            for m, path in zip(plan.missions, outputs.kmz_paths, strict=True)
        ]
        ui.table(columns=columns, rows=rows, row_key="file").classes("w-full")
        if outputs.warnings:
            ui.label("Notes about this plan").classes("text-lg font-bold")
            issue_cards(explain_issues(outputs.warnings))
        with ui.expansion(
            "How do I get these missions onto my drone?", icon="phone_android"
        ).classes("w-full border rounded-lg"):
            for n, step in enumerate(HOW_TO_FLY, start=1):
                ui.label(f"{n}. {step}").classes("text-sm")
        ui.label(f"Saved in {out_dir}").classes("text-sm text-gray-600 break-all")
        ui.button(
            "Open the folder", icon="folder_open", on_click=lambda: open_in_file_manager(out_dir)
        ).props("outline no-caps")
