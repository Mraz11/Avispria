# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest

from avispria.adapters.profiles import load_profiles
from avispria.core.geometry import rectangle_polygon
from avispria.core.mission import PhotoMode
from avispria.core.plan_model import PlanRequest
from avispria.core.planner import plan
from avispria.core.safety import SafetyLimits
from avispria.core.scan import ScanRequest, plan_scan
from avispria.core.scan_types import AREA_3D, DEFAULT_TYPE, FLAT, OBJECT_3D, SCAN_TYPES

LITO = load_profiles()["lito-x1"]


def test_there_are_three_kinds_and_every_one_is_described_in_full() -> None:
    assert list(SCAN_TYPES) == ["flat", "area_3d", "object_3d"] and DEFAULT_TYPE in SCAN_TYPES
    for key, t in SCAN_TYPES.items():
        assert t.key == key
        for text in (t.title, t.summary, t.good_for, t.how, t.you_tell, t.after):
            assert (text.strip() and text.strip()[-1] in ".)'") or text is t.title, (key, text)
        assert t.after.startswith("Make maps:")


def test_the_two_area_kinds_differ_in_the_way_that_matters() -> None:
    assert FLAT.is_area and AREA_3D.is_area and not OBJECT_3D.is_area
    assert (FLAT.tilt_deg, FLAT.crosshatch) == (0.0, False)  # straight down, one direction
    assert (AREA_3D.tilt_deg, AREA_3D.crosshatch) == (30.0, True)  # tilted, two directions
    assert AREA_3D.gsd_cm >= FLAT.gsd_cm  # tilted pictures are coarser towards their top


def area_plan(kind, crosshatch: bool):  # type: ignore[no-untyped-def]
    aoi = rectangle_polygon(51.4769, -0.0015, 150.0, 150.0, 0.0)
    return plan(
        PlanRequest(
            aoi=aoi,
            camera=LITO.modes["12mp"],
            drone_max_speed_ms=LITO.max_speed_ms,
            takeoff_lon=aoi.centroid.x,
            takeoff_lat=aoi.centroid.y,
            target_gsd_m=kind.gsd_cm / 100.0,
            front_overlap=kind.front_percent / 100.0,
            side_overlap=kind.side_percent / 100.0,
            gimbal_pitch_deg=-(90.0 - kind.tilt_deg),
            crosshatch=crosshatch,
            photo_mode=PhotoMode.WAYPOINT,
            flat_terrain=True,
            limits=SafetyLimits(max_flight_time_s=20 * 60.0),
            name="t",
        )
    )


@pytest.mark.parametrize("kind", [FLAT, AREA_3D], ids=lambda t: t.key)
def test_the_recommended_settings_of_an_area_kind_make_a_valid_plan(kind) -> None:  # type: ignore[no-untyped-def]
    result = area_plan(kind, kind.crosshatch)
    assert not [i for i in result.issues if i.level == "error"]
    assert (result.summary.oblique is not None) == (kind.tilt_deg > 0)
    one_way = area_plan(kind, False)
    ratio = result.summary.strips / one_way.summary.strips
    assert (ratio > 1.8) == kind.crosshatch  # lines in two directions, or in one


def test_the_object_kind_makes_a_valid_plan_with_a_tree_sized_object() -> None:
    result = plan_scan(
        ScanRequest(
            centre_lon=-0.0015,
            centre_lat=51.4769,
            camera=LITO.modes["12mp"],
            drone_max_speed_ms=LITO.max_speed_ms,
            object_height_m=15.0,
            object_radius_m=5.0,
        )
    )
    assert not [i for i in result.issues if i.level == "error"] and result.summary.photos > 50
