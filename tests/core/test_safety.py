# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from avispria.core.mission import Mission, PhotoMode, Takeoff, Waypoint, haversine_m
from avispria.core.safety import SafetyLimits, check_mission

TAKEOFF = Takeoff(lon=90.4, lat=23.8, elevation_m=10.0, elevation_source="test")


def _wp(lon: float, lat: float, h: float, **kw: float) -> Waypoint:
    defaults: dict[str, float | bool | None] = {
        "speed_ms": 5.0,
        "gimbal_pitch_deg": -90.0,
        "take_photo": True,
        "surface_clearance_m": 50.0,
        "height_above_ground_m": h,
    }
    defaults.update(kw)
    return Waypoint(lon=lon, lat=lat, height_m=h, **defaults)  # type: ignore[arg-type]


def _mission(wps: list[Waypoint], **kw: object) -> Mission:
    base: dict[str, object] = {
        "name": "t",
        "waypoints": tuple(wps),
        "takeoff": TAKEOFF,
        "photo_mode": PhotoMode.WAYPOINT,
        "photo_interval_s": None,
        "speed_ms": 5.0,
        "estimated_duration_s": 300.0,
    }
    base.update(kw)
    return Mission(**base)  # type: ignore[arg-type]


def _codes(issues: list) -> set[str]:  # type: ignore[type-arg]
    return {i.code for i in issues}


def test_haversine_known_distance() -> None:
    # 0.001 deg latitude is ~111.2 m
    assert abs(haversine_m(90.4, 23.8, 90.4, 23.801) - 111.2) < 0.5


def test_clean_mission_passes() -> None:
    m = _mission([_wp(90.4, 23.8, 60.0), _wp(90.401, 23.8, 60.0)])
    assert check_mission(m, SafetyLimits()) == []


def test_each_limit_is_reported() -> None:
    far = _wp(90.41, 23.8, 60.0)  # ~1 km east
    tall = _wp(90.4, 23.8, 150.0)
    low = _wp(90.4, 23.8001, 60.0, surface_clearance_m=5.0)
    m = _mission([tall, low, far], estimated_duration_s=4000.0, speed_ms=20.0)
    codes = _codes(check_mission(m, SafetyLimits(max_waypoints=2)))
    assert {"SAF001", "SAF002", "SAF003", "SAF004", "SAF005", "SAF006", "SAF007"} <= codes


def test_flat_terrain_is_a_warning_not_error() -> None:
    wps = [_wp(90.4, 23.8, 60.0, surface_clearance_m=None, height_above_ground_m=None)] * 2
    m = _mission(wps, takeoff=Takeoff(90.4, 23.8, None, "none"))
    issues = check_mission(m, SafetyLimits())
    assert [(i.level, i.code) for i in issues] == [("warning", "SAF008")]


def test_interval_shorter_than_camera_is_error() -> None:
    m = _mission(
        [_wp(90.4, 23.8, 60.0), _wp(90.401, 23.8, 60.0)],
        photo_mode=PhotoMode.INTERVAL,
        photo_interval_s=1.0,
    )
    issues = check_mission(m, SafetyLimits(), camera_min_interval_s=2.0)
    assert "SAF009" in _codes(issues)
