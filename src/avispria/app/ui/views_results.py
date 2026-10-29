# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""What the flight-plan and processing screens show: verdicts, tiles and result files."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from avispria.app.ui.views import Tile, Verdict, pct
from avispria.core.plan_model import PlanResult
from avispria.core.safety import Issue

SERIOUS_PLAN_CODES = {"PL001", "PL002", "SAF003", "SAF008", "QA006", "QA010", "QA014"}


# ------------------------------------------------------------------- flight plan
def plan_verdict(warnings: Sequence[Issue]) -> Verdict:
    if not warnings:
        return Verdict("good", "Plan ready", "All checks passed.")
    serious = [i for i in warnings if i.code in SERIOUS_PLAN_CODES]
    n = len({i.code for i in warnings})
    if serious:
        return Verdict(
            "caution",
            "Plan ready, but please read the notes",
            f"{n} note{'s' if n != 1 else ''} below; some affect the quality or safety of "
            "the flight.",
        )
    return Verdict("good", "Plan ready", f"{n} note{'s' if n != 1 else ''} to read below.")


def plan_tiles(result: PlanResult) -> list[Tile]:
    s, p = result.summary, result.summary.prediction
    minutes = sum(m.estimated_duration_s for m in result.missions) / 60.0
    photos = sum(m.photo_count for m in result.missions)
    tiles = [
        Tile(
            "You asked for",
            f"{s.gsd_m * 100:.2f} cm/px",
            f"flying {s.agl_m:.0f} m above the surface",
        )
    ]
    if p is not None:
        tiles += [
            Tile(
                "You will get",
                f"{p.gsd_cm_median:.2f} cm/px",
                f"typical; coarsest tenth {p.gsd_cm_p90:.2f} cm/px",
            ),
            Tile(
                "Height above the surface",
                f"{p.height_median_m:.0f} m",
                f"from {p.height_min_m:.0f} to {p.height_max_m:.0f} m along the route",
            ),
            Tile(
                "Overlap",
                f"front {pct(p.front_overlap_median)}, side {pct(p.side_overlap_median)}",
                f"typical; low end {pct(p.front_overlap_p10)} / {pct(p.side_overlap_p10)}",
            ),
            Tile(
                "Area coverage",
                f"{p.area_pct_min_views:.0f}% seen by 3+ photos",
                f"{p.area_pct_good_views:.0f}% by 5+ photos",
            ),
        ]
    n = len(result.missions)
    tiles.append(
        Tile(
            "Flight",
            f"{n} mission{'s' if n != 1 else ''}, about {minutes:.0f} min",
            f"{photos} photos" if photos else f"timed shot every {s.photo_interval_s or 0:.1f} s",
        )
    )
    tiles.append(Tile("Speed", f"{s.speed.speed_ms:.1f} m/s", f"limited by {s.speed.binding}"))
    return tiles


# ------------------------------------------------------------ processed results
OUTPUT_LABELS = (
    ("odm_orthophoto.tif", "Orthophoto (the map)"),
    ("dsm.tif", "Surface model (heights including trees and buildings)"),
    ("dtm.tif", "Terrain model (ground heights)"),
    ("odm_georeferenced_model.laz", "Point cloud"),
    ("odm_textured_model_geo.glb", "3D model"),
    ("report.pdf", "Quality report from the engine"),
)


def process_verdict(provenance: Mapping[str, Any]) -> Verdict:
    status = str(provenance.get("status", ""))
    if status == "COMPLETED":
        rec = provenance.get("reconstruction") or {}
        issues = rec.get("issues") or []
        if issues:
            return Verdict(
                "caution", "Maps are ready, with notes", f"{len(issues)} point(s) below."
            )
        return Verdict("good", "Maps are ready", "No problems found in the 3D reconstruction.")
    if status == "CANCELED":
        return Verdict("caution", "Stopped", "Processing was cancelled; nothing was downloaded.")
    return Verdict("problem", "Processing did not finish", str(provenance.get("error") or status))


def process_tiles(provenance: Mapping[str, Any]) -> list[Tile]:
    rec = provenance.get("reconstruction") or {}
    task = provenance.get("task") or {}
    tiles: list[Tile] = []
    if task.get("processing_s"):
        tiles.append(Tile("Processing time", f"{task['processing_s'] / 60:.1f} min"))
    if rec.get("photos_total"):
        tiles.append(Tile("Photos used", f"{rec['photos_placed']} of {rec['photos_total']}"))
    if rec.get("reprojection_px") is not None:
        tiles.append(
            Tile("Fit of the 3D model", f"{rec['reprojection_px']:.2f} px", "under 1 px is good")
        )
    if rec.get("gps_error_m") is not None:
        tiles.append(Tile("Agreement with photo GPS", f"{rec['gps_error_m']:.2f} m"))
    if rec.get("points"):
        density = rec.get("points_per_m2")
        tiles.append(
            Tile(
                "Point cloud",
                f"{rec['points'] / 1e6:.2f} million points",
                f"about {density:.0f} per m2" if density else "",
            )
        )
    if rec.get("area_m2"):
        tiles.append(Tile("Area covered", f"{rec['area_m2'] / 1e4:.2f} ha"))
    if rec.get("gsd_cm_measured"):
        tiles.append(
            Tile(
                "Ground resolution", f"{rec['gsd_cm_measured']:.2f} cm/px", "measured by the engine"
            )
        )
    return tiles


def key_outputs(provenance: Mapping[str, Any], out_dir: Path) -> list[tuple[str, Path]]:
    """The main result files, with plain labels."""
    files = [str(o["file"]) for o in provenance.get("outputs", [])]
    found = []
    for suffix, label in OUTPUT_LABELS:
        match = next((f for f in files if f.endswith(suffix)), None)
        if match is not None:
            found.append((label, out_dir / match))
    return found
