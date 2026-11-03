# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest

from avispria.core.mission import Waypoint
from avispria.core.route import clock, leg_lengths_m, route_length_m, route_seconds

LAT, LON = 51.4769, -0.0015
METRE = 1 / 111_320.0  # degrees of latitude in a metre


def wp(north_m: float, speed: float = 6.0) -> Waypoint:
    return Waypoint(
        lon=LON,
        lat=LAT + north_m * METRE,
        height_m=50.0,
        speed_ms=speed,
        gimbal_pitch_deg=-90.0,
        take_photo=False,
        surface_clearance_m=None,
        height_above_ground_m=None,
    )


def test_a_route_is_the_sum_of_its_legs() -> None:
    wps = [wp(0), wp(10), wp(40), wp(40)]
    assert leg_lengths_m(wps) == pytest.approx([10.0, 30.0, 0.0], abs=0.05)
    assert route_length_m(wps) == pytest.approx(40.0, abs=0.05)


def test_no_leg_for_fewer_than_two_waypoints() -> None:
    assert leg_lengths_m([]) == [] and leg_lengths_m([wp(0)]) == []
    assert route_length_m([wp(0)]) == 0.0 and route_seconds([wp(0)], 6.0) == 0.0


def test_each_leg_is_flown_at_the_speed_of_the_waypoint_it_starts_from() -> None:
    wps = [wp(0, 5.0), wp(10, 10.0), wp(30, 99.0)]  # 10 m at 5 m/s, then 20 m at 10 m/s
    assert route_seconds(wps) == pytest.approx(2.0 + 2.0, abs=0.01)


def test_a_waypoint_without_a_speed_uses_the_default_and_with_none_at_all_there_is_no_time() -> (
    None
):
    wps = [wp(0, 0.0), wp(60, 0.0)]
    assert route_seconds(wps, 6.0) == pytest.approx(10.0, abs=0.05)
    assert route_seconds(wps) == 0.0


def test_a_flight_time_is_written_the_way_dji_fly_writes_it() -> None:
    assert [clock(s) for s in (0, 9.4, 69, 94.4, 600, 3599.6)] == [
        "0:00",
        "0:09",
        "1:09",
        "1:34",
        "10:00",
        "60:00",
    ]
