# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import math
from dataclasses import replace
from itertools import pairwise

import pytest

from avispria.adapters.profiles import load_profiles
from avispria.core.camera import footprint_m
from avispria.core.errors import PlanningError
from avispria.core.geometry import LocalFrame, utm_crs_for
from avispria.core.mission import Waypoint, haversine_m
from avispria.core.safety import SafetyLimits
from avispria.core.scan import ScanPlan, ScanRequest, plan_scan

LITO = load_profiles()["lito-x1"]
LON, LAT = -0.0015, 51.4769


def tree(**changes: object) -> ScanRequest:
    base = ScanRequest(
        centre_lon=LON,
        centre_lat=LAT,
        camera=LITO.modes["12mp"],
        drone_max_speed_ms=LITO.max_speed_ms,
        object_height_m=25.0,
        object_radius_m=6.0,
        standoff_m=14.0,
    )
    return replace(base, **changes)  # type: ignore[arg-type]


def ring_waypoints(plan: ScanPlan) -> list[Waypoint]:
    return [w for m in plan.missions for w in m.waypoints if w.poi is not None]


def cap_waypoints(plan: ScanPlan) -> list[Waypoint]:
    return [w for m in plan.missions for w in m.waypoints if w.poi is None]


def local_xy(plan: ScanPlan, w: Waypoint) -> tuple[float, float]:
    frame = LocalFrame(utm_crs_for(LON, LAT))
    cx, cy = frame.to_local([LON], [LAT])
    x, y = frame.to_local([w.lon], [w.lat])
    return float(x[0] - cx[0]), float(y[0] - cy[0])


def test_every_ring_waypoint_is_on_a_circle_around_the_axis() -> None:
    plan = plan_scan(tree())
    for w in ring_waypoints(plan):
        # 6 m radius + 14 m. Exact in metres on the map grid; haversine assumes a round Earth,
        # which is about 0.3% short of true metres at this latitude
        assert math.hypot(*local_xy(plan, w)) == pytest.approx(20.0, abs=0.001)
        assert haversine_m(LON, LAT, w.lon, w.lat) == pytest.approx(20.0, rel=0.006)


def test_each_photo_looks_at_the_height_on_the_object_the_plan_says() -> None:
    """From the camera, along its tilt, the line of sight meets the surface at the centre height."""
    plan = plan_scan(tree())
    rings = plan.summary.rings
    by_height = {round(r.height_m, 1): r for r in rings}
    for w in ring_waypoints(plan):
        ring = by_height[round(w.height_above_ground_m or 0.0, 1)]
        meets = w.height_above_ground_m + math.tan(math.radians(w.gimbal_pitch_deg)) * (20.0 - 6.0)
        assert meets == pytest.approx(ring.centre_height_m, abs=0.1)


def test_the_rings_cover_the_object_from_base_to_top_with_the_promised_overlap() -> None:
    req = tree(side_overlap=0.70)
    plan = plan_scan(req)
    _, along = footprint_m(
        req.camera, req.standoff_m
    )  # the picture's vertical reach on the surface
    centres = [r.centre_height_m for r in plan.summary.rings]
    assert centres[0] - along / 2 <= req.base_height_m + 1e-6  # the first picture reaches the foot
    assert centres[-1] + along / 2 >= req.object_height_m - 1e-6  # the last reaches the top
    gaps = [b - a for a, b in pairwise(centres)]
    assert (
        max(gaps) <= along * (1 - req.side_overlap) + 1e-6
    )  # neighbours overlap at least as promised


def test_more_overlap_between_rings_means_more_rings() -> None:
    few = plan_scan(tree(side_overlap=0.5)).summary.rings
    many = plan_scan(tree(side_overlap=0.9)).summary.rings
    assert len(many) > len(few) >= 1


@pytest.mark.parametrize("max_step", [5.0, 10.0, 20.0])
def test_neighbouring_photos_around_a_ring_are_never_further_apart_than_the_largest_angle(
    max_step: float,
) -> None:
    plan = plan_scan(tree(max_step_deg=max_step, top_cap=False))
    waypoints = ring_waypoints(plan)
    heights = sorted({round(w.height_above_ground_m or 0, 1) for w in waypoints})
    for h in heights:
        ring = [w for w in waypoints if round(w.height_above_ground_m or 0, 1) == h]
        angles = sorted(math.degrees(math.atan2(*local_xy(plan, w))) % 360 for w in ring)
        gaps = [b - a for a, b in pairwise(angles)] + [360 - angles[-1] + angles[0]]
        assert max(gaps) <= max_step + 0.01


def test_the_tilt_goes_from_looking_up_at_the_bottom_to_looking_down_at_the_top() -> None:
    rings = plan_scan(tree(look_up_deg=10.0, look_down_deg=20.0)).summary.rings
    pitches = [r.pitch_deg for r in rings]
    assert pitches[0] == pytest.approx(10.0) and pitches[-1] == pytest.approx(-20.0)
    assert pitches == sorted(pitches, reverse=True)


def test_every_photo_is_taken_standing_still_facing_the_object() -> None:
    plan = plan_scan(tree(hover_s=1.5))
    for w in ring_waypoints(plan):
        assert w.take_photo and w.stop and w.hover_s == 1.5
        assert w.poi == pytest.approx(
            (LON, LAT, 12.5)
        )  # the middle of the object: one point of interest
        assert -90.0 <= w.gimbal_pitch_deg <= 40.0
    caps = cap_waypoints(plan)
    assert caps and all(
        w.gimbal_pitch_deg == -90.0 and w.heading_deg == 0.0 and w.stop for w in caps
    )


def test_the_top_cap_is_a_grid_of_straight_down_photos_above_the_object() -> None:
    plan = plan_scan(tree(top_clearance_m=8.0))
    caps = cap_waypoints(plan)
    assert plan.summary.cap_photos == len(caps) > 4
    assert {round(w.height_above_ground_m or 0, 1) for w in caps} == {33.0}  # 25 m top + 8 m
    xs = [local_xy(plan, w) for w in caps]
    assert max(math.hypot(x, y) for x, y in xs) <= 6.0 + 4.0  # over the crown, not beyond it
    assert min(math.hypot(x, y) for x, y in xs) < 3.0  # one near the middle
    assert plan_scan(tree(top_cap=False)).summary.cap_photos == 0


def test_the_route_is_a_spiral_with_no_two_consecutive_waypoints_in_the_same_place() -> None:
    plan = plan_scan(tree())
    for m in plan.missions:
        for a, b in pairwise(m.waypoints):
            assert haversine_m(a.lon, a.lat, b.lon, b.lat) >= 1.0  # the linter's own rule is 0.5 m


def bearing(x: float, y: float) -> float:
    return math.degrees(math.atan2(x, y)) % 360.0


def test_the_first_waypoint_faces_the_takeoff_point_which_defaults_to_south_of_the_object() -> None:
    plan = plan_scan(tree())
    t = plan.missions[0].takeoff
    assert haversine_m(t.lon, t.lat, LON, LAT) == pytest.approx(20.0 + 15.0, rel=0.01)
    x, y = local_xy(plan, plan.missions[0].waypoints[0])
    assert bearing(x, y) == pytest.approx(
        180.0, abs=0.01
    )  # due south on the grid: nearest the takeoff
    north = plan_scan(tree(takeoff_lon=LON, takeoff_lat=LAT + 0.0004))
    tx, ty = local_xy(north, Waypoint(LON, LAT + 0.0004, 0, 1, 0, False, None, None))
    x, y = local_xy(north, north.missions[0].waypoints[0])
    assert bearing(x, y) == pytest.approx(bearing(tx, ty), abs=0.01)  # towards wherever takeoff is
    assert abs(bearing(x, y) - 180.0) > 150.0  # i.e. on the north side, not the south


def test_missions_stay_within_the_waypoint_limit_and_keep_whole_rings_together() -> None:
    plan = plan_scan(tree(limits=SafetyLimits(max_waypoints=40)))
    sizes = [len(m.waypoints) for m in plan.missions]
    assert max(sizes) <= 40 and sum(sizes) == plan.summary.photos
    ring = plan.summary.rings[0].photos
    assert all(s % ring == 0 or s == plan.summary.cap_photos for s in sizes[:-1]) or ring > 20
    default = plan_scan(tree())
    assert all(len(m.waypoints) <= 99 for m in default.missions)
    assert sum(len(m.waypoints) for m in default.missions) == default.summary.photos


def test_a_short_battery_makes_more_missions() -> None:
    one = plan_scan(tree(limits=SafetyLimits(max_flight_time_s=20 * 60)))
    short = plan_scan(tree(limits=SafetyLimits(max_flight_time_s=3 * 60)))
    assert len(short.missions) > len(one.missions)
    assert all(m.estimated_duration_s <= 3 * 60 + 1 for m in short.missions[:-1])


def test_a_ground_that_is_higher_than_the_takeoff_point_raises_every_height() -> None:
    flat = plan_scan(tree())
    higher = plan_scan(tree(ground_offset_m=6.0))
    for a, b in zip(ring_waypoints(flat), ring_waypoints(higher), strict=True):
        assert b.height_m == pytest.approx(a.height_m + 6.0)
        assert b.height_above_ground_m == pytest.approx(
            a.height_above_ground_m
        )  # the object is unchanged
    assert higher.summary.rings[0].height_m == pytest.approx(flat.summary.rings[0].height_m)


def test_an_object_shorter_than_one_picture_gets_a_single_ring() -> None:
    plan = plan_scan(tree(object_height_m=6.0, object_radius_m=1.0, standoff_m=14.0))
    assert len(plan.summary.rings) == 1
    assert plan.summary.rings[0].centre_height_m == pytest.approx(3.0)


def codes(plan: ScanPlan) -> set[str]:
    return {i.code for i in plan.issues}


def test_too_close_is_refused_and_close_is_a_warning() -> None:
    assert "SC001" in codes(plan_scan(tree(standoff_m=3.0)))
    near = plan_scan(tree(standoff_m=7.0))
    assert "SC002" in codes(near) and "SC001" not in codes(near)
    assert {i.level for i in near.issues if i.code == "SC002"} == {"warning"}
    assert not {"SC001", "SC002"} & codes(plan_scan(tree(standoff_m=14.0)))


def test_a_ring_that_would_touch_the_ground_is_refused() -> None:
    plan = plan_scan(tree(standoff_m=20.0, look_up_deg=40.0))  # looking steeply up from the ground
    assert "SC003" in codes(plan)


def test_the_usual_safety_rules_apply_to_scans_too() -> None:
    tall = plan_scan(tree(object_height_m=150.0))
    assert "SAF001" in codes(tall)  # higher than 120 m above takeoff
    far = plan_scan(tree(takeoff_lon=LON + 0.01, takeoff_lat=LAT))
    assert "SAF004" in codes(far)  # more than 500 m from takeoff
    assert [i.code for i in plan_scan(tree()).issues].count(
        "SAF008"
    ) <= 1  # said once, not per mission


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"object_radius_m": 0.0}, "radius"),
        ({"object_height_m": 0.0}, "higher than"),
        ({"base_height_m": -1.0}, "below the ground"),
        ({"standoff_m": 0.0}, "distance from the object"),
        ({"front_overlap": 0.99}, "front overlap"),
        ({"side_overlap": -0.1}, "side overlap"),
        ({"max_step_deg": 0.5}, "largest angle"),
        ({"max_step_deg": 45.0}, "largest angle"),
        ({"speed_ms": 0.0}, "speed"),
        ({"speed_ms": 99.0}, "speed"),
        ({"hover_s": -1.0}, "hover"),
        ({"look_up_deg": 41.0}, "at most 40"),
        ({"look_down_deg": 91.0}, "at most 90"),
        ({"top_clearance_m": 1.0}, "at least 3 m"),
        ({"object_height_m": float("nan")}, "real number"),
    ],
)
def test_requests_that_make_no_sense_are_refused_with_the_reason(
    changes: dict, message: str
) -> None:  # type: ignore[type-arg]
    with pytest.raises(PlanningError, match=message):
        plan_scan(tree(**changes))


def test_the_plan_is_the_same_every_time() -> None:
    a, b = plan_scan(tree()), plan_scan(tree())
    assert [(w.lon, w.lat, w.height_m) for m in a.missions for w in m.waypoints] == [
        (w.lon, w.lat, w.height_m) for m in b.missions for w in m.waypoints
    ]
