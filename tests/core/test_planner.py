# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import numpy as np
import pytest
from shapely.geometry import Point, box

from avispria.core.camera import CameraProfile
from avispria.core.mission import PhotoMode
from avispria.core.planner import PlanningError, PlanRequest, TerrainOptions, plan
from avispria.core.safety import SafetyLimits
from avispria.core.terrain import Dem

CAM = CameraProfile(
    "mini4pro-12mp", 8.97, 6.72, 6.72, 4032, 3024, min_interval_s=2.0, readout_s=0.03
)
AOI = box(90.400, 23.800, 90.403, 23.8027)  # ~300 m x 300 m
TAKEOFF = (90.4015, 23.80135)  # centre of the AOI
ARCSEC = 1 / 3600


def hill_dem(peak: float = 40.0) -> Dem:
    lon0, lat0 = 90.395, 23.808
    lons = lon0 + (np.arange(50) + 0.5) * ARCSEC
    lats = lat0 - (np.arange(50) + 0.5) * ARCSEC
    glon, glat = np.meshgrid(lons, lats)
    r2 = ((glon - 90.4015) / 0.0006) ** 2 + ((glat - 23.8013) / 0.0006) ** 2
    data = 10.0 + peak * np.exp(-r2)
    return Dem(data, (ARCSEC, 0.0, lon0, 0.0, -ARCSEC, lat0), "EPSG:4326")


def request(**kw: object) -> PlanRequest:
    base: dict[str, object] = {
        "aoi": AOI,
        "camera": CAM,
        "drone_max_speed_ms": 12.0,
        "takeoff_lon": TAKEOFF[0],
        "takeoff_lat": TAKEOFF[1],
        "agl_m": 60.0,
        "front_overlap": 0.75,
        "side_overlap": 0.7,
        "shutter_s": 1 / 2000,
        "limits": SafetyLimits(max_waypoints=500),
    }
    base.update(kw)
    return PlanRequest(**base)  # type: ignore[arg-type]


def test_requires_terrain_or_explicit_flat() -> None:
    with pytest.raises(PlanningError, match="terrain"):
        plan(request())


def test_requires_exactly_one_of_gsd_and_agl() -> None:
    with pytest.raises(PlanningError):
        plan(request(flat_terrain=True, target_gsd_m=0.02))
    with pytest.raises(PlanningError):
        plan(request(flat_terrain=True, agl_m=None))


def test_flat_plan_is_constant_height_with_warning() -> None:
    res = plan(request(flat_terrain=True))
    heights = {w.height_m for m in res.missions for w in m.waypoints}
    assert heights == {60.0}
    assert "SAF008" in {i.code for i in res.issues}
    assert res.ok  # a warning does not block export
    photos = sum(m.photo_count for m in res.missions)
    assert photos > 20
    buffered = AOI.buffer(0.001)
    assert all(buffered.contains(Point(w.lon, w.lat)) for m in res.missions for w in m.waypoints)


def test_terrain_plan_keeps_clearance_and_climbs_over_hill() -> None:
    res = plan(request(dem=hill_dem(), takeoff_elevation_m=10.0))
    assert res.ok, res.issues
    wps = [w for m in res.missions for w in m.waypoints]
    assert (
        min(w.surface_clearance_m for w in wps if w.surface_clearance_m is not None) >= 60.0 - 1e-6
    )
    assert max(w.height_m for w in wps) > 60.0 + 25.0  # rises over the 40 m hill
    assert res.summary.terrain_source.startswith("DEM")


def test_takeoff_elevation_defaults_to_conservative_dem_minimum() -> None:
    res = plan(request(dem=hill_dem(), takeoff_lon=90.3995, takeoff_lat=23.7995))
    assert res.summary.takeoff_elevation_m == pytest.approx(10.0, abs=0.5)
    assert "minimum" in res.summary.takeoff_elevation_source


def test_dem_gap_is_an_error() -> None:
    dem = hill_dem()
    holes = dem.data.copy()
    holes[20:30, 20:30] = np.nan
    with pytest.raises(PlanningError, match="no data"):
        plan(
            request(
                dem=Dem(holes, dem.transform, dem.crs),
                terrain=TerrainOptions(dilation_radius_m=0.0),
            )
        )


def test_interval_mode_uses_few_waypoints_and_sets_interval() -> None:
    wp_mode = plan(request(flat_terrain=True))
    iv_mode = plan(request(flat_terrain=True, photo_mode=PhotoMode.INTERVAL))
    n_wp = sum(len(m.waypoints) for m in wp_mode.missions)
    n_iv = sum(len(m.waypoints) for m in iv_mode.missions)
    assert n_iv < n_wp
    m = iv_mode.missions[0]
    assert m.photo_count == 0
    assert m.photo_interval_s is not None
    assert m.photo_interval_s >= CAM.min_interval_s - 1e-9


def test_crosshatch_doubles_strips() -> None:
    single = plan(request(flat_terrain=True, photo_mode=PhotoMode.INTERVAL))
    double = plan(request(flat_terrain=True, photo_mode=PhotoMode.INTERVAL, crosshatch=True))
    assert double.summary.strips == pytest.approx(2 * single.summary.strips, abs=1)


def test_splits_into_sorties_under_waypoint_limit() -> None:
    res = plan(request(flat_terrain=True, limits=SafetyLimits(max_waypoints=40)))
    assert len(res.missions) > 1
    assert all(len(m.waypoints) <= 40 for m in res.missions)
    assert res.ok
    whole = plan(request(flat_terrain=True))
    assert sum(m.photo_count for m in res.missions) == sum(m.photo_count for m in whole.missions)
    assert [m.name for m in res.missions][:2] == ["avispria_01", "avispria_02"]


def test_bad_gimbal_pitch_rejected() -> None:
    with pytest.raises(PlanningError):
        plan(request(flat_terrain=True, gimbal_pitch_deg=10.0))


def test_strip_ends_stop_and_mid_points_pass() -> None:
    res = plan(request(flat_terrain=True))
    m = res.missions[0]
    assert m.waypoints[0].stop and m.waypoints[-1].stop
    stops = sum(w.stop for w in m.waypoints)
    assert stops == 2 * res.summary.strips
    assert any(not w.stop for w in m.waypoints)
