# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Planning over relief: the plan must achieve what it was asked for over the real surface."""

import numpy as np
import pytest
from shapely.geometry import box

from avispria.core.camera import CameraProfile, gsd_m
from avispria.core.mission import PhotoMode
from avispria.core.planner import PlanningError, PlanRequest, PlanResult, plan
from avispria.core.safety import SafetyLimits
from avispria.core.terrain import Dem

CAM = CameraProfile(
    "mini4pro-12mp", 8.97, 6.72, 6.72, 4032, 3024, min_interval_s=2.0, readout_s=0.03
)
AOI = box(90.400, 23.800, 90.403, 23.8027)  # ~300 m x 300 m
TAKEOFF = (90.4015, 23.80135)
ARCSEC = 1 / 3600
TARGET_GSD_CM = 2.0


def hill(peak: float) -> Dem:
    lon0, lat0 = 90.395, 23.808
    lons = lon0 + (np.arange(50) + 0.5) * ARCSEC
    lats = lat0 - (np.arange(50) + 0.5) * ARCSEC
    glon, glat = np.meshgrid(lons, lats)
    r2 = ((glon - 90.4015) / 0.0006) ** 2 + ((glat - 23.8013) / 0.0006) ** 2
    return Dem(10.0 + peak * np.exp(-r2), (ARCSEC, 0.0, lon0, 0.0, -ARCSEC, lat0), "EPSG:4326")


def make_plan(**kw: object) -> PlanResult:
    base: dict[str, object] = {
        "aoi": AOI,
        "camera": CAM,
        "drone_max_speed_ms": 12.0,
        "takeoff_lon": TAKEOFF[0],
        "takeoff_lat": TAKEOFF[1],
        "target_gsd_m": TARGET_GSD_CM / 100,
        "photo_mode": PhotoMode.WAYPOINT,
        "front_overlap": 0.8,
        "side_overlap": 0.7,
        "takeoff_elevation_m": 10.0,
        "limits": SafetyLimits(max_waypoints=500),
    }
    base.update(kw)
    return plan(PlanRequest(**base))  # type: ignore[arg-type]


def codes(result: PlanResult) -> set[str]:
    return {i.code for i in result.issues}


def clearances(result: PlanResult) -> list[float]:
    return [
        w.surface_clearance_m
        for m in result.missions
        for w in m.waypoints
        if w.surface_clearance_m is not None
    ]


def test_calibrated_plan_meets_the_requested_resolution_and_overlap() -> None:
    res = make_plan(dem=hill(40.0))
    p = res.summary.prediction
    assert p is not None and p.terrain_aware and p.not_assessed == 0
    assert p.gsd_cm_median == pytest.approx(TARGET_GSD_CM, rel=0.04)
    # the lowest tenth of the photos still reach (about) the requested overlap
    assert p.front_overlap_p10 is not None and p.front_overlap_p10 >= 0.80 - 0.03
    assert p.side_overlap_p10 is not None and p.side_overlap_p10 >= 0.70 - 0.03
    assert p.area_pct_min_views == pytest.approx(100.0, abs=1.0)
    assert "PL001" not in codes(res) and "PL002" not in codes(res)
    # the route is built lower than the requested height: the safety layers lift it back up
    assert res.summary.flight_reference_m < res.summary.agl_m - 10.0
    assert 2 <= res.summary.calibration_steps <= 4


def test_without_calibration_the_plan_misses_the_resolution_and_says_so() -> None:
    res = make_plan(dem=hill(40.0), calibrate_height=False)
    p = res.summary.prediction
    assert p is not None and res.summary.calibration_steps == 1
    assert p.gsd_cm_median > TARGET_GSD_CM * 1.25  # what the plan used to hide
    assert {"PL001", "PL002"} <= codes(res)
    assert res.summary.gsd_m == pytest.approx(gsd_m(CAM, res.summary.agl_m))  # the request itself


def test_calibration_never_flies_below_the_clearance_limit() -> None:
    res = make_plan(target_gsd_m=0.007, dem=hill(40.0))  # a resolution that needs very low flight
    assert min(clearances(res)) >= 20.0 - 1e-6  # SafetyLimits.min_surface_clearance_m
    assert res.summary.flight_reference_m == pytest.approx(
        10.0, abs=1e-6
    )  # 20 m minus the 10 m margin
    p = res.summary.prediction
    assert p is not None and "PL001" in codes(res)  # the target cannot be reached, and it is said
    assert p.gsd_cm_median > 0.7 * 1.15


def test_large_relief_is_reported_even_when_the_typical_resolution_is_met() -> None:
    res = make_plan(dem=hill(80.0))
    p = res.summary.prediction
    assert p is not None and p.gsd_cm_median == pytest.approx(TARGET_GSD_CM, rel=0.05)
    assert "PL002" in codes(res) and p.gsd_cm_p90 > TARGET_GSD_CM * 1.3
    assert min(clearances(res)) >= 20.0 - 1e-6


def test_flat_plan_prediction_agrees_with_the_request() -> None:
    res = make_plan(flat_terrain=True, takeoff_elevation_m=None)
    p = res.summary.prediction
    assert p is not None and not p.terrain_aware and res.summary.calibration_steps == 1
    assert p.gsd_cm_median == pytest.approx(TARGET_GSD_CM, rel=0.01)
    assert p.height_min_m == pytest.approx(p.height_max_m, abs=1e-6)
    assert p.front_overlap_median == pytest.approx(0.80, abs=0.03)
    assert p.side_overlap_median == pytest.approx(0.70, abs=0.03)
    assert p.area_pct_min_views >= 99.0  # the whole survey area, edges included


def test_trees_on_flat_ground_lift_the_route_so_the_canopy_gets_the_requested_height() -> None:
    bare = make_plan(flat_terrain=True, takeoff_elevation_m=None)
    forest = make_plan(flat_terrain=True, takeoff_elevation_m=None, surface_height_m=25.0)
    h_bare = {w.height_m for m in bare.missions for w in m.waypoints}
    h_forest = {w.height_m for m in forest.missions for w in m.waypoints}
    assert min(h_forest) == pytest.approx(min(h_bare) + 25.0)
    assert max(h_forest) == pytest.approx(max(h_bare) + 25.0)
    p = forest.summary.prediction
    assert p is not None and p.height_median_m == pytest.approx(bare.summary.agl_m, abs=0.1)
    assert p.gsd_cm_median == pytest.approx(TARGET_GSD_CM, rel=0.01)


def test_trees_over_a_ground_model_raise_the_route_by_their_height() -> None:
    bare = make_plan(dem=hill(40.0))
    forest = make_plan(dem=hill(40.0), surface_height_m=25.0)
    top = lambda r: max(w.height_m for m in r.missions for w in m.waypoints)  # noqa: E731
    assert top(forest) - top(bare) == pytest.approx(25.0, abs=4.0)
    p = forest.summary.prediction
    assert p is not None and p.gsd_cm_median == pytest.approx(TARGET_GSD_CM, rel=0.04)
    assert min(clearances(forest)) >= 20.0 - 1e-6  # measured to the canopy top


def test_interval_mode_is_predicted_along_the_whole_route() -> None:
    res = make_plan(dem=hill(40.0), photo_mode=PhotoMode.INTERVAL)
    p = res.summary.prediction
    assert p is not None and res.summary.photo_interval_s is not None
    assert p.gsd_cm_median == pytest.approx(TARGET_GSD_CM, rel=0.06)
    assert p.front_overlap_p10 is not None and p.front_overlap_p10 >= 0.80 - 0.04


def test_oblique_plans_have_no_prediction() -> None:
    res = make_plan(flat_terrain=True, takeoff_elevation_m=None, gimbal_pitch_deg=-60.0)
    assert res.summary.prediction is None and res.missions


def test_negative_surface_height_is_rejected() -> None:
    with pytest.raises(PlanningError, match="surface_height_m"):
        make_plan(flat_terrain=True, takeoff_elevation_m=None, surface_height_m=-1.0)
