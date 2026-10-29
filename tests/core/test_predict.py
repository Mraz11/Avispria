# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import math

import numpy as np
import pytest

from avispria.core.mission import Mission, PhotoMode, Takeoff, Waypoint
from avispria.core.predict import heights_above_surface, planned_photos
from avispria.core.terrain import Dem

LON0, LAT0 = -3.0100, 51.4900  # near the central meridian of UTM zone 30: grid north = true north
M_LAT = 111_320.0
M_LON = 111_320.0 * math.cos(math.radians(51.49))


def wp(east_m: float, north_m: float, height: float, photo: bool = False) -> Waypoint:
    return Waypoint(
        lon=LON0 + east_m / M_LON,
        lat=LAT0 + north_m / M_LAT,
        height_m=height,
        speed_ms=5.0,
        gimbal_pitch_deg=-90.0,
        take_photo=photo,
        surface_clearance_m=None,
        height_above_ground_m=None,
        stop=False,
    )


def mission(waypoints: list[Waypoint], mode: PhotoMode, interval: float | None = None) -> Mission:
    return Mission(
        "m", tuple(waypoints), Takeoff(LON0, LAT0, 100.0, "test"), mode, interval, 5.0, 100.0
    )


def test_waypoint_mode_photos_are_the_photo_waypoints_with_their_course() -> None:
    north = mission(
        [wp(0, 0, 50), wp(0, 50, 50, True), wp(0, 100, 50, True), wp(0, 150, 50)],
        PhotoMode.WAYPOINT,
    )
    photos = planned_photos(north)
    assert len(photos) == 2 and [round(p.height_rel_m) for p in photos] == [50, 50]
    assert all(abs(p.course_deg % 360) < 0.5 for p in photos)  # flying north
    east = mission(
        [wp(0, 0, 50), wp(40, 0, 50, True), wp(80, 0, 50, True), wp(120, 0, 50)], PhotoMode.WAYPOINT
    )
    assert all(p.course_deg == pytest.approx(90.0, abs=0.5) for p in planned_photos(east))
    last = mission(
        [wp(0, 0, 50), wp(0, 60, 50, True)], PhotoMode.WAYPOINT
    )  # photo at the final waypoint
    assert planned_photos(last)[0].course_deg == pytest.approx(0.0, abs=0.5)


def test_interval_mode_samples_the_route_at_speed_times_interval() -> None:
    m = mission([wp(0, 0, 50), wp(105, 0, 60)], PhotoMode.INTERVAL, interval=2.0)  # 10 m apart
    photos = planned_photos(m)
    assert len(photos) == 11  # at 0, 10, ..., 100 m of a 105 m route
    assert photos[0].height_rel_m == pytest.approx(50.0, abs=0.01)
    assert photos[5].height_rel_m == pytest.approx(50.0 + 10.0 * 50 / 105, abs=0.1)  # along the leg
    assert photos[-1].height_rel_m == pytest.approx(50.0 + 10.0 * 100 / 105, abs=0.1)
    east = (photos[3].lon - photos[0].lon) * M_LON
    assert east == pytest.approx(30.0, abs=0.2) and photos[3].course_deg == pytest.approx(
        90.0, abs=0.5
    )


def test_interval_photos_continue_through_turns() -> None:
    """Timed shot runs for the whole route, including the turn between flight lines."""
    m = mission(
        [wp(0, 0, 50), wp(0, 62, 50), wp(22, 62, 50), wp(22, 0, 50)],
        PhotoMode.INTERVAL,
        interval=2.0,
    )
    photos = planned_photos(m)
    assert len(photos) == 15  # ~146 m of route every 10 m
    courses = {round(p.course_deg) % 360 for p in photos}
    assert {0, 90, 180} <= courses  # north, the turn east, then south


def sloping_dem(n: int = 100) -> Dem:
    cell = 1 / 3600
    west = LON0 - 0.005  # the model starts west of the first photo
    lons = west + (np.arange(n) + 0.5) * cell
    row = 100.0 + 0.05 * (lons - LON0) * M_LON  # rises 5 m per 100 m eastwards
    return Dem(np.tile(row, (n, 1)), (cell, 0.0, west, 0.0, -cell, LAT0 + 0.01), "EPSG:4326")


def test_heights_above_the_actual_surface() -> None:
    m = mission([wp(0, 0, 50), wp(105, 0, 50)], PhotoMode.INTERVAL, interval=4.0)  # 20 m apart
    photos = planned_photos(m)
    h = heights_above_surface(photos, takeoff_elevation_m=100.0, dem=sloping_dem())
    # flying level 50 m above takeoff while the ground rises 0.05 m per metre eastwards
    expected = [50.0 - 0.05 * east for east in (0, 20, 40, 60, 80, 100)]
    assert h == pytest.approx(expected, abs=0.1)


def test_surface_height_allowance_lowers_the_height_above_the_surface() -> None:
    photos = planned_photos(
        mission([wp(0, 0, 50), wp(40, 0, 50)], PhotoMode.INTERVAL, interval=4.0)
    )
    plain = heights_above_surface(photos, 100.0, sloping_dem())
    trees = heights_above_surface(photos, 100.0, sloping_dem(), surface_offset_m=25.0)
    assert trees == pytest.approx(plain - 25.0, abs=1e-9)


def test_photos_off_the_model_have_no_height() -> None:
    photos = planned_photos(
        mission([wp(0, 0, 50), wp(40, 0, 50)], PhotoMode.INTERVAL, interval=4.0)
    )
    far = heights_above_surface(photos, 100.0, sloping_dem(n=2))  # a model one cell wide
    assert np.isnan(far).any()
