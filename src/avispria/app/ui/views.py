# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""What the screens show, as plain data: verdicts, tiles and explained warnings.

Everything here is a pure function of results the tool already produces, so it is tested
without a browser. The screens only draw these objects.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from avispria.app.doctor import DoctorReport
from avispria.app.ui.explain import explain
from avispria.core.capture import CaptureReport
from avispria.core.feasibility import Assessment, gb, ram_needed_gb
from avispria.core.safety import Issue

Level = Literal["good", "caution", "problem"]


@dataclass(frozen=True)
class Verdict:
    level: Level
    headline: str
    detail: str = ""


@dataclass(frozen=True)
class Tile:
    label: str
    value: str
    hint: str = ""


@dataclass(frozen=True)
class StatusRow:
    label: str
    value: str
    level: Level
    hint: str = ""


@dataclass(frozen=True)
class ExplainedIssue:
    code: str
    level: Literal["error", "warning"]
    title: str
    detail: str  # the technical message (first occurrence)
    meaning: str
    action: str
    count: int = 1  # how many times it occurred (e.g. once per mission)


def pct(value: float | None) -> str:
    return "-" if value is None else f"{value * 100:.0f}%"


def explain_issues(issues: Sequence[Issue]) -> list[ExplainedIssue]:
    """One entry per code, errors first, each with its plain-language explanation."""
    groups: dict[str, list[Issue]] = {}
    for issue in issues:
        groups.setdefault(issue.code, []).append(issue)
    out = []
    for code, items in groups.items():
        e = explain(code)
        level: Literal["error", "warning"] = (
            "error" if any(i.level == "error" for i in items) else "warning"
        )
        out.append(
            ExplainedIssue(code, level, e.title, items[0].message, e.meaning, e.action, len(items))
        )
    out.sort(key=lambda item: item.level != "error")
    return out


# ---------------------------------------------------------------- start screen
def photos_that_fit(ram_gb: float) -> int:
    """How many 12 MP photos fit in ``ram_gb`` of memory (OpenDroneMap's own table)."""
    low, high = 0, 20_000
    while low < high:
        mid = (low + high + 1) // 2
        if ram_needed_gb(mid) <= ram_gb:
            low = mid
        else:
            high = mid - 1
    return low


def system_rows(report: DoctorReport) -> list[StatusRow]:
    s = report.system
    comfortable = photos_that_fit(s.ram_total_gb * 0.85)
    with_virtual = photos_that_fit(s.ram_total_gb * 0.85 + s.swap_total_gb)
    memory_level: Level = (
        "good" if s.ram_total_gb >= 8 else "caution" if s.ram_total_gb >= 4 else "problem"
    )
    disk_level: Level = (
        "good" if s.disk_free_gb >= 50 else "caution" if s.disk_free_gb >= 20 else "problem"
    )
    rows = [
        StatusRow("Computer", f"{s.os_name}, {s.cpu_logical} processor threads", "good"),
        StatusRow(
            "Memory",
            f"{gb(s.ram_total_gb)} GB ({gb(s.ram_available_gb)} GB free right now)",
            memory_level,
            f"Comfortable for about {comfortable} photos at 12 MP, up to about {with_virtual} "
            "using virtual memory (slower).",
        ),
        StatusRow(
            "Free disk space",
            f"{gb(s.disk_free_gb)} GB",
            disk_level,
            "A job needs roughly 8 times the size of its photos.",
        ),
    ]
    running = next((e for e in report.engines if e.name == "WebODM" and e.reachable), None)
    node = next((e for e in report.engines if e.name == "Processing node" and e.reachable), None)
    if running is not None or node is not None:
        rows.append(StatusRow("Map-making engine", "WebODM is running", "good"))
    else:
        rows.append(
            StatusRow(
                "Map-making engine",
                "Not found",
                "caution",
                "To make maps, install WebODM (free, webodm.org/download) and start it. "
                "Checking photos and planning flights work without it.",
            )
        )
    return rows


def option_lines(assessment: Assessment) -> list[str]:
    """The alternatives for a job that does not fit, one sentence each."""
    lines = []
    for o in assessment.options:
        need = "" if o.ram_gb is None else f", about {gb(o.ram_gb)} GB"
        mark = ("works, but slow" if o.slow else "works") if o.fits else "not enough on its own"
        lines.append(f"{o.description} ({mark}{need})")
    return lines


def feasibility_verdict(assessment: Assessment) -> Verdict:
    reasons = " ".join(assessment.reasons)
    if assessment.verdict == "ok":
        return Verdict("good", "This computer can process these photos", reasons)
    if assessment.verdict == "slow":
        return Verdict("caution", "Possible, but slow", reasons)
    return Verdict("problem", "Not possible on this computer as it is", reasons)


# ----------------------------------------------------------------- photo check
def qa_verdict(report: CaptureReport) -> Verdict:
    errors = [i for i in report.issues if i.level == "error"]
    used = int(report.stats.get("photos_used", 0))
    if errors or used < 3:
        first = errors[0] if errors else None
        e = explain(first.code if first else "QA009")
        return Verdict("problem", e.title, first.message if first else e.meaning)
    codes = {i.code for i in report.issues}
    if codes:
        n = len(codes)
        return Verdict(
            "caution",
            "Usable, with things to look at",
            f"{n} point{'s' if n != 1 else ''} below. None of them stops you from processing.",
        )
    return Verdict(
        "good",
        "Looks good for processing",
        "Based on the photos' position and camera data; sharpness itself is not checked.",
    )


def qa_tiles(report: CaptureReport) -> list[Tile]:
    s = report.stats
    if "gsd_cm_median" not in s:
        return [
            Tile("Photos", f"{int(s.get('photos_used', 0))} of {int(s.get('photos_total', 0))}")
        ]
    tiles = [
        Tile(
            "Photos checked",
            f"{int(s['photos_used'])} of {int(s['photos_total'])}",
            "the others have no position or do not look straight down"
            if s["photos_used"] < s["photos_total"]
            else "all of them",
        ),
        Tile(
            "Height",
            f"{s['altitude_m_median']:.0f} m",
            "above the surface (terrain used)"
            if s.get("terrain_aware")
            else "above the takeoff point (flat ground assumed)",
        ),
        Tile(
            "Ground resolution",
            f"{s['gsd_cm_median']:.2f} cm/px",
            "size of one pixel on the ground",
        ),
    ]
    overlaps = []
    for label, key in (("front", "front_overlap"), ("side", "side_overlap")):
        if f"{key}_median" in s:
            overlaps.append((label, s[f"{key}_median"], s[f"{key}_p10"]))
    if overlaps:
        tiles.append(
            Tile(
                "Overlap",
                ", ".join(f"{label} {pct(m)}" for label, m, _ in overlaps),
                "typical; low end " + " / ".join(pct(p) for _, _, p in overlaps),
            )
        )
    tiles.append(
        Tile(
            "Area coverage",
            f"{s['area_pct_min_views']:.0f}% seen by 3+ photos",
            f"{s['area_pct_good_views']:.0f}% by 5+ photos (5 or more is best for 3D)",
        )
    )
    if "interval_s_median" in s:
        tiles.append(
            Tile("Photo interval", f"{s['interval_s_median']:.1f} s", "typical time between photos")
        )
    return tiles
