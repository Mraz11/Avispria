# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""File-level workflows used by the CLI (and later the UI)."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from avispria.adapters.dem_file import load_dem_window
from avispria.adapters.profiles import DroneProfile
from avispria.core.geometry import load_aoi
from avispria.core.mission import PhotoMode
from avispria.core.planner import PlanRequest, PlanResult, TerrainOptions, plan
from avispria.core.safety import Issue, SafetyLimits
from avispria.core.version import __version__
from avispria.core.wpml.lint import LintLimits, lint_kmz
from avispria.core.wpml.sheet import plan_hash, spot_check_csv
from avispria.core.wpml.template import DummyTemplate
from avispria.core.wpml.writer import write_kmz

GUID = re.compile(r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$")


class PlanBlockedError(RuntimeError):
    """The plan has errors; nothing was written."""

    def __init__(self, issues: list[Issue]) -> None:
        super().__init__("; ".join(f"{i.code}: {i.message}" for i in issues))
        self.issues = issues


@dataclass(frozen=True)
class PlanOptions:
    takeoff_lat: float
    takeoff_lon: float
    mode: str = "12mp"
    target_gsd_m: float | None = None
    agl_m: float | None = None
    front_overlap: float = 0.8
    side_overlap: float = 0.7
    heading_deg: float | None = None
    crosshatch: bool = False
    photo_mode: PhotoMode = PhotoMode.INTERVAL
    dem_path: Path | None = None
    flat_terrain: bool = False
    takeoff_elevation_m: float | None = None
    shutter_s: float = 1 / 1000
    wind_ms: float = 0.0
    limits: SafetyLimits = field(default_factory=SafetyLimits)
    terrain: TerrainOptions = field(default_factory=TerrainOptions)
    straight_lines: bool = True
    name: str = "avispria"


@dataclass(frozen=True)
class PlanOutputs:
    result: PlanResult
    kmz_paths: list[Path]
    sheet_paths: list[Path]
    report_path: Path
    warnings: list[Issue]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _extra_warnings(
    template: DummyTemplate, profile: DroneProfile, opts: PlanOptions
) -> list[Issue]:
    out: list[Issue] = []
    if opts.photo_mode is PhotoMode.WAYPOINT and not template.has_photo_action:
        out.append(
            Issue(
                "warning",
                "AVI001",
                "the dummy mission has no Take Photo action, so the photo action encoding is "
                "unverified for this aircraft; prefer interval mode until a probe flight "
                "confirms it",
            )
        )
    if template.drone_enum != profile.drone_enum:
        out.append(
            Issue(
                "warning",
                "AVI002",
                f"dummy droneEnumValue {template.drone_enum} differs from profile "
                f"{profile.drone_enum}; the dummy's value is used",
            )
        )
    if not profile.verified:
        out.append(
            Issue(
                "warning",
                "AVI003",
                f"camera profile for {profile.name} is not verified; "
                "confirm it from an original photo",
            )
        )
    return out


def run_plan(
    aoi_path: Path,
    template_path: Path,
    profile: DroneProfile,
    opts: PlanOptions,
    out_dir: Path,
    now_ms: int,
) -> PlanOutputs:
    """Plan, write and lint missions. Writes nothing if any error is found."""
    if opts.mode not in profile.modes:
        raise ValueError(
            f"{profile.key} has no camera mode {opts.mode!r}; choose {sorted(profile.modes)}"
        )
    aoi = load_aoi(json.loads(aoi_path.read_text("utf-8")))
    template = DummyTemplate.from_kmz(template_path.read_bytes())
    dem = None
    if opts.dem_path is not None:
        lons = [*aoi.exterior.xy[0], opts.takeoff_lon]
        lats = [*aoi.exterior.xy[1], opts.takeoff_lat]
        dem = load_dem_window(opts.dem_path, (min(lons), min(lats), max(lons), max(lats)))
    limits = opts.limits
    if limits.max_waypoints > profile.waypoint_limit:
        limits = SafetyLimits(**{**asdict(limits), "max_waypoints": profile.waypoint_limit})
    result = plan(
        PlanRequest(
            aoi=aoi,
            camera=profile.modes[opts.mode],
            drone_max_speed_ms=profile.max_speed_ms,
            takeoff_lon=opts.takeoff_lon,
            takeoff_lat=opts.takeoff_lat,
            target_gsd_m=opts.target_gsd_m,
            agl_m=opts.agl_m,
            front_overlap=opts.front_overlap,
            side_overlap=opts.side_overlap,
            heading_deg=opts.heading_deg,
            crosshatch=opts.crosshatch,
            photo_mode=opts.photo_mode,
            dem=dem,
            flat_terrain=opts.flat_terrain,
            takeoff_elevation_m=opts.takeoff_elevation_m,
            terrain=opts.terrain,
            shutter_s=opts.shutter_s,
            wind_ms=opts.wind_ms,
            limits=limits,
            name=opts.name,
        )
    )
    warnings = [i for i in result.issues if i.level == "warning"]
    warnings += _extra_warnings(template, profile, opts)
    errors = [i for i in result.issues if i.level == "error"]
    if errors:
        raise PlanBlockedError(errors)

    lint_limits = LintLimits(max_waypoints=limits.max_waypoints, max_speed_ms=profile.max_speed_ms)
    blobs: list[tuple[str, bytes]] = []
    for mission in result.missions:
        kmz = write_kmz(template, mission, now_ms=now_ms, straight_lines=opts.straight_lines)
        lint_errors = [i for i in lint_kmz(kmz, lint_limits) if i.level == "error"]
        if lint_errors:
            raise PlanBlockedError(lint_errors)
        blobs.append((mission.name, kmz))

    out_dir.mkdir(parents=True, exist_ok=True)
    kmz_paths, sheet_paths = [], []
    for name, kmz in blobs:
        kmz_path = out_dir / f"{name}.kmz"
        kmz_path.write_bytes(kmz)
        sheet_path = out_dir / f"{name}_spotcheck.csv"
        sheet_path.write_text(spot_check_csv(kmz), encoding="utf-8")
        kmz_paths.append(kmz_path)
        sheet_paths.append(sheet_path)

    report = {
        "tool": {"name": "avispria", "version": __version__},
        "created_ms": now_ms,
        "inputs": {
            "aoi": {"path": aoi_path.name, "sha256": _sha256(aoi_path)},
            "template": {"path": template_path.name, "sha256": _sha256(template_path)},
            "dem": None
            if opts.dem_path is None
            else {"path": opts.dem_path.name, "sha256": _sha256(opts.dem_path)},
            "drone": profile.key,
            "camera_mode": opts.mode,
            "options": {
                k: str(v) for k, v in asdict(opts).items() if k not in ("limits", "terrain")
            },
            "limits": asdict(limits),
            "terrain": asdict(opts.terrain),
        },
        "summary": dict(asdict(result.summary).items()),
        "missions": [
            {
                "name": m.name,
                "file": p.name,
                "plan_hash": plan_hash(p.read_bytes()),
                "waypoints": len(m.waypoints),
                "photos": m.photo_count,
                "photo_interval_s": m.photo_interval_s,
                "estimated_duration_min": round(m.estimated_duration_s / 60, 1),
                "max_height_m": round(max(w.height_m for w in m.waypoints), 1),
            }
            for m, p in zip(result.missions, kmz_paths, strict=True)
        ],
        "warnings": [asdict(i) for i in warnings],
    }
    report_path = out_dir / "plan_report.json"
    report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return PlanOutputs(result, kmz_paths, sheet_paths, report_path, warnings)


def prepare_copy(kmz_path: Path, slot_guid: str, out_dir: Path) -> Path:
    """Lay out ``<GUID>/<GUID>.kmz`` ready to copy over a DJI Fly dummy mission."""
    if not GUID.match(slot_guid):
        raise ValueError(f"{slot_guid!r} is not a DJI Fly mission id (a GUID)")
    data = kmz_path.read_bytes()
    errors = [i for i in lint_kmz(data, LintLimits()) if i.level == "error"]
    if errors:
        raise PlanBlockedError(errors)
    target = out_dir / slot_guid / f"{slot_guid}.kmz"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return target
