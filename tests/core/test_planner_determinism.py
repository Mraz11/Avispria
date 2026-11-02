# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A plan must not depend on the last digits of the arithmetic.

GitHub's Ubuntu planned the 200 x 200 m case of the phone page's golden numbers in 6.8819
minutes while every other machine (and this one) said 6.9086: the comparison of two equal sides
of a square was decided by noise. Nudging the inputs by a trillionth must never change a plan.
"""

import random

from avispria.adapters.profiles import load_profiles
from avispria.core.geometry import rectangle_polygon
from avispria.core.mission import PhotoMode
from avispria.core.planner import PlanRequest, plan
from avispria.core.safety import SafetyLimits


def minutes_and_strips(
    width: float, length: float, lat: float, lon: float, angle: float = 0.0
) -> tuple[float, int]:
    lito = load_profiles()["lito-x1"]
    aoi = rectangle_polygon(lat, lon, width, length, angle)
    res = plan(
        PlanRequest(
            aoi=aoi,
            camera=lito.modes["12mp"],
            drone_max_speed_ms=lito.max_speed_ms,
            takeoff_lon=aoi.centroid.x,
            takeoff_lat=aoi.centroid.y,
            agl_m=50.0,
            front_overlap=0.75,
            side_overlap=0.65,
            photo_mode=PhotoMode.INTERVAL,
            flat_terrain=True,
            shutter_s=1 / 1000,
            wind_ms=0.0,
            limits=SafetyLimits(max_flight_time_s=20 * 60.0),
            name="determinism",
        )
    )
    return sum(m.estimated_duration_s for m in res.missions) / 60.0, res.summary.strips


def test_a_square_survey_is_planned_the_same_whatever_the_last_digits_say() -> None:
    rng = random.Random(7)
    seen = set()
    for _ in range(30):
        e = 1e-12
        minutes, strips = minutes_and_strips(
            200.0 * (1 + rng.uniform(-e, e)),
            200.0 * (1 + rng.uniform(-e, e)),
            23.8103 + rng.uniform(-e, e),
            90.4125 + rng.uniform(-e, e),
        )
        seen.add((round(minutes, 6), strips))
    assert len(seen) == 1, f"the plan depends on noise: {sorted(seen)}"


def test_a_rotated_square_and_a_rectangle_are_stable_too() -> None:
    rng = random.Random(11)
    for width, length, angle in ((200.0, 200.0, 30.0), (150.0, 300.0, 0.0), (100.0, 100.0, 90.0)):
        seen = set()
        for _ in range(12):
            e = 1e-12
            seen.add(
                tuple(
                    round(v, 6)
                    for v in minutes_and_strips(
                        width * (1 + rng.uniform(-e, e)),
                        length * (1 + rng.uniform(-e, e)),
                        23.8103,
                        90.4125,
                        angle,
                    )
                )
            )
        assert len(seen) == 1, (
            f"{width} x {length} at {angle} degrees depends on noise: {sorted(seen)}"
        )
