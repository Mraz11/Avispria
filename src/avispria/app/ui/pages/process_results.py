# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""What the Make maps screen shows: the computer check, and the result of a job."""

from __future__ import annotations

from pathlib import Path

from nicegui import ui

from avispria.app.doctor import DoctorReport
from avispria.app.ui.files import open_in_file_manager
from avispria.app.ui.process_job import ProcessJobResult
from avispria.app.ui.views import (
    Tile,
    Verdict,
    explain_issues,
    feasibility_verdict,
    option_lines,
    system_rows,
)
from avispria.app.ui.views_results import key_outputs, process_tiles, process_verdict
from avispria.app.ui.widgets import issue_cards, status_rows, tile_row, verdict_banner
from avispria.core.feasibility import Assessment, gb
from avispria.core.safety import Issue


def show_options(assessment: Assessment) -> None:
    lines = option_lines(assessment)
    if not lines:
        return
    ui.label("What you can do").classes("text-lg font-bold")
    for line in lines:
        ui.label(f"- {line}").classes("text-sm")


def show_feasibility(box: ui.column, report: DoctorReport) -> None:
    with box:
        a, job = report.assessment, report.job
        if a is None or job is None:
            ui.label("No photos could be read in that folder.").classes(
                "av-caution-text font-medium"
            )
            status_rows(system_rows(report))
            return
        verdict_banner(feasibility_verdict(a))
        tile_row(
            [
                Tile(
                    "Photos", f"{job.photos}", f"{job.native_mp:.1f} MP each, {job.input_gb:.2f} GB"
                ),
                Tile(
                    "The job needs",
                    f"about {gb(a.ram_gb)} GB of memory",
                    f"and {gb(a.disk_gb)} GB of free disk",
                ),
                Tile("Photos are processed at", f"{a.processing_mp:.1f} MP"),
            ]
        )
        show_options(a)
        ui.label("Your computer").classes("text-lg font-bold")
        status_rows(system_rows(report))


def _issues_from(provenance: dict) -> list[Issue]:  # type: ignore[type-arg]
    found = (provenance.get("reconstruction") or {}).get("issues") or []
    return [Issue("warning", str(i.get("code", "")), str(i.get("message", ""))) for i in found]


def show_result(box: ui.column, result: ProcessJobResult, out_dir: Path) -> None:
    with box:
        if result.provenance is None or result.outcome is None:
            verdict_banner(
                Verdict("problem", "Not started", result.blocked or "The job did not start.")
            )
            if result.assessment is not None:
                show_options(result.assessment)
                ui.label(
                    "You can choose a smaller photo size above, or tick 'Start even if this "
                    "computer looks too small' to try anyway."
                ).classes("text-sm av-muted")
            return
        provenance = result.provenance
        verdict_banner(process_verdict(provenance))
        tile_row(process_tiles(provenance))
        issues = _issues_from(provenance)
        if issues:
            ui.label("Things to look at").classes("text-lg font-bold")
            issue_cards(explain_issues(issues))
        log = provenance.get("log_tail") or []
        if log and provenance.get("status") not in ("COMPLETED", "CANCELED"):
            with ui.expansion("What the engine said (last lines)", icon="terminal").classes(
                "w-full border rounded-lg"
            ):
                for line in log[-15:]:
                    ui.label(str(line)).classes("text-xs font-mono break-all")
        if result.outcome.completed:
            ui.label("Your results").classes("text-lg font-bold")
            for label, path in key_outputs(provenance, out_dir):
                with ui.row().classes("items-center gap-2 no-wrap"):
                    ui.icon("insert_drive_file").classes("av-muted")
                    with ui.column().classes("gap-0"):
                        ui.label(label).classes("font-medium")
                        ui.label(str(path)).classes("text-xs av-muted break-all")
            if result.outcome.zip_path is not None:
                ui.label(
                    "To look at everything in WebODM: choose Import and select "
                    f"{result.outcome.zip_path}"
                ).classes("text-sm av-muted break-all")
        ui.label(f"Saved in {out_dir}").classes("text-sm av-muted break-all")
        with ui.row().classes("gap-3"):
            ui.button(
                "Open the results folder",
                icon="folder_open",
                color="secondary",
                on_click=lambda: open_in_file_manager(out_dir),
            ).props("no-caps")
            ui.label("A record of exactly what was done is in avispria_provenance.json.").classes(
                "text-sm av-muted"
            )
