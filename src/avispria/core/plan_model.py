# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""What a survey plan is asked to do (request) and what it comes out as (result)."""

from __future__ import annotations

from dataclasses import dataclass, field

from shapely.geometry import Polygon

from avispria.core.camera import CameraProfile
from avispria.core.mission import Mission, PhotoMode
from avispria.core.predict import PlanPrediction
from avispria.core.profile import TerrainOptions
from avispria.core.safety import Issue, SafetyLimits
from avispria.core.speed import SpeedSolution
from avispria.core.terrain import Dem


@dataclass(frozen=True)
class PlanRequest:
    aoi: Polygon
    camera: CameraProfile
    drone_max_speed_ms: float
    takeoff_lon: float
    takeoff_lat: float
    target_gsd_m: float | None = None
    agl_m: float | None = None
    front_overlap: float = 0.8
    side_overlap: float = 0.7
    heading_deg: float | None = None
    crosshatch: bool = False
    gimbal_pitch_deg: float = -90.0
    photo_mode: PhotoMode = PhotoMode.WAYPOINT
    dem: Dem | None = None
    flat_terrain: bool = False
    takeoff_elevation_m: float | None = None
    terrain: TerrainOptions = field(default_factory=TerrainOptions)
    shutter_s: float = 1 / 1000
    wind_ms: float = 0.0
    overrun_m: float | None = None
    limits: SafetyLimits = field(default_factory=SafetyLimits)
    photo_overhead_s: float = 1.0
    climb_rate_ms: float = 3.0
    surface_height_m: float = 0.0  # trees or buildings standing this high above the ground model
    calibrate_height: bool = True  # tune the flight height and spacing to the real surface
    name: str = "avispria"


@dataclass(frozen=True)
class PlanSummary:
    agl_m: float
    gsd_m: float
    photo_spacing_m: float
    line_spacing_m: float
    heading_deg: float
    strips: int
    speed: SpeedSolution
    photo_interval_s: float | None
    terrain_source: str
    takeoff_elevation_m: float | None
    takeoff_elevation_source: str
    flight_reference_m: float = 0.0  # height the route is built around (after calibration)
    spacing_height_m: float = 0.0  # height the photo and line spacing are computed for
    calibration_steps: int = 1  # planning passes it took
    prediction: PlanPrediction | None = None  # what the plan will achieve over the real surface


@dataclass(frozen=True)
class PlanResult:
    missions: tuple[Mission, ...]
    summary: PlanSummary
    issues: tuple[Issue, ...]

    @property
    def ok(self) -> bool:
        return not any(i.level == "error" for i in self.issues)
