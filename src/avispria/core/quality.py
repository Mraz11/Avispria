# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Plain-language summary of the engine's own reconstruction statistics.

Input is the parsed ``odm_report/stats.json`` written by ODX. Every field is optional:
older or partial runs must never crash the summary. The thresholds are rules of
thumb for consumer-drone surveys, not guarantees.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from avispria.core.safety import Issue

REPROJECTION_WARN_PX = 1.5  # rule of thumb: under ~1 px is good
GSD_RATIO_WARN = (0.75, 1.33)  # estimate and measurement agree within about 25%


@dataclass(frozen=True)
class ReconstructionSummary:
    photos_total: int | None = None
    photos_placed: int | None = None
    components: int | None = None
    sparse_points: int | None = None
    reprojection_px: float | None = None
    gps_error_m: float | None = None
    points: int | None = None
    area_m2: float | None = None
    gsd_cm_measured: float | None = None
    gsd_cm_estimated: float | None = None
    issues: list[Issue] = field(default_factory=list)

    @property
    def points_per_m2(self) -> float | None:
        if not self.points or not self.area_m2:
            return None
        return self.points / self.area_m2

    @property
    def gsd_ratio(self) -> float | None:
        """Measured / estimated ground resolution (below 1: the engine saw finer detail)."""
        if not self.gsd_cm_measured or not self.gsd_cm_estimated:
            return None
        return self.gsd_cm_measured / self.gsd_cm_estimated


def _section(stats: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = stats.get(key)
    return value if isinstance(value, Mapping) else {}


def _number(section: Mapping[str, object], key: str) -> float | None:
    value = section.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _count(section: Mapping[str, object], key: str) -> int | None:
    value = _number(section, key)
    return None if value is None else int(value)


def _dense_points(stats: Mapping[str, object]) -> int | None:
    pc = _section(_section(stats, "point_cloud_statistics"), "stats")
    rows = pc.get("statistic")
    if isinstance(rows, list) and rows and isinstance(rows[0], Mapping):
        return _count(rows[0], "count")
    return None


def summarize_reconstruction(
    stats: Mapping[str, object], gsd_estimated_cm: float | None
) -> ReconstructionSummary:
    """Key numbers from ODX's statistics, with warnings for results needing attention."""
    rec = _section(stats, "reconstruction_statistics")
    summary = ReconstructionSummary(
        photos_total=_count(rec, "initial_shots_count"),
        photos_placed=_count(rec, "reconstructed_shots_count"),
        components=_count(rec, "components"),
        sparse_points=_count(rec, "reconstructed_points_count"),
        reprojection_px=_number(rec, "reprojection_error_pixels"),
        gps_error_m=_number(_section(stats, "gps_errors"), "average_error"),
        points=_dense_points(stats),
        area_m2=_number(_section(stats, "processing_statistics"), "area"),
        gsd_cm_measured=_number(_section(stats, "odm_processing_statistics"), "average_gsd"),
        gsd_cm_estimated=gsd_estimated_cm,
    )
    issues: list[Issue] = []
    placed, total = summary.photos_placed, summary.photos_total
    if placed is not None and total is not None and placed < total:
        issues.append(
            Issue(
                "warning",
                "RQ001",
                f"only {placed} of {total} photos could be placed in the 3D model; the others "
                "were not used (check them for blur and for overlap with their neighbours)",
            )
        )
    if summary.components is not None and summary.components > 1:
        issues.append(
            Issue(
                "warning",
                "RQ002",
                f"the photos formed {summary.components} separate models that may not line up "
                "with each other; more overlap between flight lines usually fixes this",
            )
        )
    if summary.reprojection_px is not None and summary.reprojection_px > REPROJECTION_WARN_PX:
        issues.append(
            Issue(
                "warning",
                "RQ003",
                f"reprojection error is {summary.reprojection_px:.1f} px (under about 1 px is "
                "good): the 3D geometry fits the photos poorly; look for blur or moving objects",
            )
        )
    ratio = summary.gsd_ratio
    if ratio is not None and not GSD_RATIO_WARN[0] <= ratio <= GSD_RATIO_WARN[1]:
        issues.append(
            Issue(
                "warning",
                "RQ004",
                f"the engine measured {summary.gsd_cm_measured:.2f} cm/px but the photo metadata "
                f"suggested {summary.gsd_cm_estimated:.2f}: the camera profile or the flat-ground "
                "assumption may be off",
            )
        )
    return ReconstructionSummary(**{**summary.__dict__, "issues": issues})
