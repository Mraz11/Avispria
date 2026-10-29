# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read and present the engine's reconstruction statistics after a processing run."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from avispria.app.capture_workflow import terrain_gsd_cm
from avispria.core.photo import PhotoRecord
from avispria.core.processing import effective_gsd_cm
from avispria.core.quality import ReconstructionSummary, summarize_reconstruction

MAX_STATS_BYTES = 20 * 1024 * 1024


def read_stats(results_dir: Path) -> dict[str, object] | None:
    """The engine's statistics file, or None if absent or unreadable (never fatal)."""
    path = results_dir / "odm_report" / "stats.json"
    try:
        if not path.is_file() or path.stat().st_size > MAX_STATS_BYTES:
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def summarize_result(
    stats: Mapping[str, object],
    records: Sequence[PhotoRecord],
    results_dir: Path,
    flat_gsd_cm: float | None,
    native_mp: float,
    processing_mp: float,
) -> ReconstructionSummary:
    """The engine's statistics set against Avispria's estimate of the ground resolution.

    ``flat_gsd_cm`` is the flat-ground estimate for the photos as uploaded. When the
    engine made a surface model, the estimate is redone with the terrain under each
    photo (resized to match the upload) and the flat figure is kept for contrast.
    """
    dsm = results_dir / "odm_dem" / "dsm.tif"
    terrain = terrain_gsd_cm(records, dsm) if dsm.is_file() else None
    if terrain is None:
        return summarize_reconstruction(stats, flat_gsd_cm)
    with_terrain = effective_gsd_cm(terrain, native_mp=native_mp, processing_mp=processing_mp)
    return summarize_reconstruction(stats, with_terrain, flat_gsd_cm)


def report_quality(
    summary: ReconstructionSummary, info: Callable[[str], None], warn: Callable[[str], None]
) -> None:
    """Print the key numbers in plain language, then any warnings."""
    rows: list[tuple[str, str]] = []
    if summary.photos_placed is not None and summary.photos_total is not None:
        placed = f"{summary.photos_placed} of {summary.photos_total}"
        rows.append(("photos placed in the 3D model", placed))
    if summary.reprojection_px is not None:
        rows.append(
            ("reprojection error", f"{summary.reprojection_px:.2f} px (under 1 px is good)")
        )
    if summary.gps_error_m is not None:
        rows.append(("agreement with photo GPS", f"{summary.gps_error_m:.2f} m on average"))
    if summary.points:
        density = ""
        if summary.points_per_m2 is not None:
            density = f" (about {summary.points_per_m2:.0f} per m2)"
        rows.append(("point cloud", f"{summary.points / 1e6:.2f} million points{density}"))
    if summary.area_m2:
        rows.append(("area covered", f"{summary.area_m2 / 1e4:.2f} ha"))
    if summary.gsd_cm_measured:
        estimate = ""
        if summary.gsd_cm_estimated is not None and summary.gsd_cm_flat is not None:
            estimate = (
                f" (estimated {summary.gsd_cm_estimated:.2f} using the terrain, "
                f"{summary.gsd_cm_flat:.2f} on flat ground)"
            )
        elif summary.gsd_cm_estimated is not None:
            estimate = f" (estimated {summary.gsd_cm_estimated:.2f})"
        rows.append(
            ("ground resolution", f"{summary.gsd_cm_measured:.2f} cm/px measured{estimate}")
        )
    width = max((len(key) for key, _ in rows), default=0)
    for key, value in rows:
        info(f"{key.ljust(width)}   {value}")
    for issue in summary.issues:
        warn(f"{issue.code}: {issue.message}")
    if rows and not summary.issues:
        info("no problems found in the reconstruction")
