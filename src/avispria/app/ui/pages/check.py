# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Check my photos: is this set of photos likely to make a good map?"""

from __future__ import annotations

from pathlib import Path

from nicegui import ui

from avispria.adapters.photos import photo_subfolders
from avispria.app.capture_workflow import report_csv, run_qa
from avispria.app.ui.charts import photo_map
from avispria.app.ui.inputs import parse_latlon_text, parse_number
from avispria.app.ui.jobs import JobResult, run_job
from avispria.app.ui.layout import frame
from avispria.app.ui.state import STATE
from avispria.app.ui.views import explain_issues, qa_tiles, qa_verdict
from avispria.app.ui.widgets import PathField, echart, issue_cards, tile_row, verdict_banner
from avispria.core.capture import CaptureReport


def _problem(box: ui.column, text: str) -> None:
    with box:
        ui.label(text).classes("av-problem-text font-medium")


def _show_photos_table(report: CaptureReport) -> None:
    columns = [
        {"name": "name", "label": "Photo", "field": "name", "align": "left"},
        {"name": "gsd", "label": "Resolution (cm/px)", "field": "gsd"},
        {"name": "front", "label": "Front overlap", "field": "front"},
        {"name": "side", "label": "Side overlap", "field": "side"},
    ]
    pct = lambda v: "-" if v is None else f"{v * 100:.0f}%"  # noqa: E731
    rows = [
        {
            "name": p.name,
            "gsd": f"{p.gsd_m * 100:.2f}",
            "front": pct(p.front_overlap),
            "side": pct(p.side_overlap),
        }
        for p in report.photos
    ]
    with ui.expansion("All photos", icon="table_rows").classes("w-full border rounded-lg"):
        ui.table(columns=columns, rows=rows, row_key="name").classes("w-full")


def _show_report(
    box: ui.column,
    folder: Path,
    outcome: JobResult,
    skipped: list[tuple[str, str]],
    report: CaptureReport,
) -> None:
    with box:
        verdict_banner(qa_verdict(report))
        tile_row(qa_tiles(report))
        if skipped:
            with ui.expansion(f"{len(skipped)} file(s) could not be read", icon="report").classes(
                "w-full border rounded-lg"
            ):
                for name, reason in skipped:
                    ui.label(f"{name}: {reason}").classes("text-sm")
        if report.photos:
            ui.label("Where the photos were taken").classes("text-lg font-bold")
            ui.label(
                "Each dot is a photo. Its colour shows how much it overlaps its nearest "
                "neighbour: red means thin overlap, green means plenty."
            ).classes("text-sm av-muted")
            echart(lambda palette: photo_map(report, palette))
        if report.issues:
            ui.label("Things to look at").classes("text-lg font-bold")
            issue_cards(explain_issues(report.issues))
        if report.photos:
            _show_photos_table(report)
        with ui.row().classes("gap-3"):
            ui.button(
                "Make maps from these photos",
                icon="map",
                color="secondary",
                on_click=lambda: ui.navigate.to("/process"),
            ).props("no-caps")
            ui.button(
                "Save details as a spreadsheet (CSV)",
                icon="download",
                on_click=lambda: ui.download.content(
                    report_csv(report).encode("utf-8"), f"{folder.name}_photo_check.csv"
                ),
            ).props("outline no-caps")


async def check_page() -> None:
    with frame("Check my photos"):
        ui.label(
            "Choose the folder with your drone photos. Avispria reads where and how each "
            "photo was taken (it does not look at the pictures themselves) and tells you "
            "whether they should make a good map."
        ).classes("text-base")
        folder = PathField(
            "Photo folder",
            value=STATE.photo_folder,
            hint="Use the original files from the drone or its memory card, not edited copies.",
            marker="photos",
        )
        subfolders = ui.switch("Include photos in subfolders (for a whole memory card)")
        with ui.expansion("Use the terrain (optional, for hilly sites)", icon="terrain").classes(
            "w-full border rounded-lg"
        ):
            ui.label(
                "With an elevation model Avispria measures the height above the real ground "
                "instead of assuming it is flat, which makes resolution and overlap right "
                "over hills. If it is the surface model WebODM made from these same photos "
                "(odm_dem/dsm.tif) you can leave the takeoff point empty."
            ).classes("text-sm av-muted")
            dem = PathField(
                "Elevation model (GeoTIFF)",
                directory=False,
                suffixes=(".tif", ".tiff"),
                marker="dem",
            )
            takeoff = (
                ui.input("Takeoff point: latitude, longitude", placeholder="23.8290, 90.4170")
                .props("outlined dense")
                .classes("w-full")
                .mark("takeoff-input")
            )
            ui.label(
                "Drones other than DJI usually record only a height above sea level, not the "
                "height above the ground. On a flat site, type the height of the ground above sea "
                "level here (in metres) and Avispria works out each photo's height above the "
                "ground from it. For sites with hills use an elevation model instead."
            ).classes("text-sm av-muted")
            ground_elev = (
                ui.input("Height of the ground above sea level (m), flat sites")
                .props("outlined dense")
                .classes("w-80")
                .mark("ground-input")
            )
        button = ui.button("Check photos", icon="fact_check").props("no-caps size=lg").mark("run")
        results = ui.column().classes("w-full gap-4")

    async def run() -> None:
        results.clear()
        text = folder.value
        if not text:
            ui.notify("Choose the photo folder first.", type="warning")
            return
        path = Path(text).expanduser()
        if not path.is_dir():
            _problem(results, f"That folder does not exist: {path}")
            return
        dem_path, takeoff_lonlat = None, None
        if dem.value:
            dem_path = Path(dem.value).expanduser()
            if not dem_path.is_file():
                _problem(results, f"That elevation model file does not exist: {dem_path}")
                return
        if takeoff.value.strip():
            if dem_path is None:
                _problem(results, "A takeoff point is only used together with an elevation model.")
                return
            try:
                lat, lon = parse_latlon_text(takeoff.value)
            except ValueError as exc:
                _problem(results, str(exc))
                return
            takeoff_lonlat = (lon, lat)
        ground_m = None
        if (ground_elev.value or "").strip():
            ground_m = parse_number(ground_elev.value)
            if ground_m is None:
                _problem(results, "The ground height should be a number of metres above sea level.")
                return
        button.disable()
        with results:
            ui.spinner(size="lg")
            ui.label("Checking your photos...")
        outcome = await run_job(
            run_qa,
            path,
            None,
            recursive=subfolders.value,
            dem_path=dem_path,
            takeoff=takeoff_lonlat,
            ground_elevation_m=ground_m,
        )
        button.enable()
        results.clear()
        STATE.photo_folder = str(path)
        if not outcome.ok or outcome.value is None:
            _problem(results, outcome.error or "The check did not finish.")
            return
        report, skipped, _ground = outcome.value
        if report.stats["photos_total"] == 0 and not skipped:
            _no_photos(results, path, folder, subfolders)
            return
        _show_report(results, path, outcome, skipped, report)

    button.on_click(run)


def _no_photos(box: ui.column, path: Path, folder: PathField, subfolders: ui.switch) -> None:
    with box:
        ui.label(f"No photos directly in {path}").classes("font-medium av-caution-text")
        found = [] if subfolders.value else photo_subfolders(path)
        if not found:
            ui.label("No JPEG or DNG photos were found there.").classes("text-sm")
            return
        ui.label("Photos were found in these subfolders. Click one to use it:").classes("text-sm")
        for sub, count in found:
            ui.button(
                f"{sub}  ({count} photos)",
                icon="folder",
                on_click=lambda s=sub: folder.set(str(path / s)),
            ).props("flat no-caps")
