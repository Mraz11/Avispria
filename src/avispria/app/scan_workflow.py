# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Plan an object scan and write its missions (the counterpart of ``run_plan`` for surveys)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from avispria import __version__
from avispria.adapters.profiles import DroneProfile
from avispria.app.workflow import PlanBlockedError
from avispria.core.safety import Issue
from avispria.core.scan import ScanPlan, ScanRequest, plan_scan
from avispria.core.wpml.lint import LintLimits, lint_kmz
from avispria.core.wpml.sheet import plan_hash, spot_check_csv
from avispria.core.wpml.template import DummyTemplate
from avispria.core.wpml.writer import write_kmz


@dataclass(frozen=True)
class ScanOutputs:
    plan: ScanPlan
    kmz_paths: list[Path]
    sheet_paths: list[Path]
    report_path: Path
    warnings: list[Issue]


def run_scan(
    request: ScanRequest,
    template_path: Path,
    profile: DroneProfile,
    out_dir: Path,
    now_ms: int,
) -> ScanOutputs:
    """Plan, write and lint the missions. Writes nothing if any rule is broken."""
    limits = request.limits
    if limits.max_waypoints > profile.waypoint_limit:
        limits = replace(limits, max_waypoints=profile.waypoint_limit)
    request = replace(request, limits=limits, drone_max_speed_ms=profile.max_speed_ms)
    plan = plan_scan(request)
    errors = [i for i in plan.issues if i.level == "error"]
    if errors:
        raise PlanBlockedError(errors)
    template = DummyTemplate.from_kmz(template_path.read_bytes())
    lint_limits = LintLimits(max_waypoints=limits.max_waypoints, max_speed_ms=profile.max_speed_ms)
    blobs: list[tuple[str, bytes]] = []
    for mission in plan.missions:
        kmz = write_kmz(template, mission, now_ms=now_ms, straight_lines=True)
        lint_errors = [i for i in lint_kmz(kmz, lint_limits) if i.level == "error"]
        if lint_errors:
            raise PlanBlockedError(lint_errors)
        blobs.append((mission.name, kmz))
    out_dir.mkdir(parents=True, exist_ok=True)
    kmz_paths, sheet_paths = [], []
    for name, kmz in blobs:
        (out_dir / f"{name}.kmz").write_bytes(kmz)
        (out_dir / f"{name}_spotcheck.csv").write_text(spot_check_csv(kmz), encoding="utf-8")
        kmz_paths.append(out_dir / f"{name}.kmz")
        sheet_paths.append(out_dir / f"{name}_spotcheck.csv")
    options = {k: str(v) for k, v in asdict(request).items() if k not in ("camera", "limits")}
    report = {
        "tool": {"name": "avispria", "version": __version__},
        "kind": "object scan",
        "created_ms": now_ms,
        "drone": profile.key,
        "options": options,
        "limits": asdict(limits),
        "summary": asdict(plan.summary),
        "missions": [
            {
                "name": m.name,
                "file": p.name,
                "plan_hash": plan_hash(p.read_bytes()),
                "waypoints": len(m.waypoints),
                "photos": m.photo_count,
                "estimated_duration_min": round(m.estimated_duration_s / 60, 1),
                "max_height_m": round(max(w.height_m for w in m.waypoints), 1),
            }
            for m, p in zip(plan.missions, kmz_paths, strict=True)
        ],
        "issues": [asdict(i) for i in plan.issues],
    }
    report_path = out_dir / "scan_report.json"
    report_path.write_text(json.dumps(report, indent=1), encoding="utf-8")
    warnings = [i for i in plan.issues if i.level == "warning"]
    return ScanOutputs(plan, kmz_paths, sheet_paths, report_path, warnings)
