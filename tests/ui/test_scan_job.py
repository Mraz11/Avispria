# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import json
from dataclasses import replace
from pathlib import Path

import pytest

from avispria.app.ui.plan_job import FormError, PlanForm
from avispria.app.ui.scan_job import build_scan, execute_scan
from avispria.core.errors import PlanningError
from avispria.core.wpml.reader import read_mission


@pytest.fixture
def scan_form(plan_form: PlanForm) -> PlanForm:
    """A valid form for a 3D model of one object (sample mission and folder: the fixture's)."""
    return replace(
        plan_form,
        scan_type="object_3d",
        object_centre="12.3456, 98.7654",
        object_height_m=25.0,
        object_radius_m=6.0,
        standoff_m=14.0,
        takeoff="",
    )


def test_an_object_scan_is_planned_written_and_reported(scan_form: PlanForm) -> None:
    result = execute_scan(scan_form, now_ms=1_793_200_000_000)
    assert result.blocked == [] and result.outputs is not None
    out = Path(scan_form.out_dir)
    assert sorted(p.name for p in out.glob("*.kmz")) == [p.name for p in result.outputs.kmz_paths]
    report = json.loads((out / "scan_report.json").read_text())
    assert report["kind"] == "object scan" and report["summary"]["photos"] == 176
    assert result.centre == pytest.approx((98.7654, 12.3456))
    assert result.takeoff is not None  # worked out: outside the ring, on the south side
    waypoints = [
        w for p in result.outputs.kmz_paths for w in read_mission(p.read_bytes()).waypoints
    ]
    assert len(waypoints) == 176 and all(
        any(a.func == "takePhoto" for a in w.actions) for w in waypoints
    )


def test_the_form_values_reach_the_plan(scan_form: PlanForm) -> None:
    request, _profile, template, out_dir = build_scan(
        replace(
            scan_form,
            standoff_m=18.0,
            look_up_deg=5.0,
            look_down_deg=30.0,
            top_cap=False,
            hover_s=2.0,
            scan_speed_ms=2.5,
            ground_offset_m=3.0,
            base_height_m=1.0,
            front_percent=85.0,
            side_percent=75.0,
            battery_minutes=15.0,
            max_height_m=100.0,
            takeoff="12.3446, 98.7654",
        )
    )
    assert (request.standoff_m, request.look_up_deg, request.look_down_deg, request.top_cap) == (
        18.0,
        5.0,
        30.0,
        False,
    )
    assert (request.hover_s, request.speed_ms, request.ground_offset_m, request.base_height_m) == (
        2.0,
        2.5,
        3.0,
        1.0,
    )
    assert (request.front_overlap, request.side_overlap) == (0.85, 0.75)
    assert (
        request.limits.max_flight_time_s == 900.0
        and request.limits.max_height_above_takeoff_m == 100.0
    )
    assert request.takeoff_lat == 12.3446 and request.takeoff_lon == 98.7654
    assert template.suffix == ".kmz" and out_dir == Path(scan_form.out_dir)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"object_centre": ""}, "Position of the object"),
        ({"object_centre": "nowhere"}, "Position of the object"),
        ({"takeoff": "far away"}, "Takeoff point"),
        ({"aircraft": "nope"}, "Unknown aircraft"),
        ({"camera_mode": "999mp"}, "no camera mode"),
        ({"template": "/nowhere/sample.kmz"}, "sample mission file was not found"),
        ({"template": ""}, "sample mission"),
        ({"front_percent": 99.0}, "overlap around a ring"),
        ({"side_percent": 5.0}, "overlap between rings"),
        ({"out_dir": " "}, "Choose the folder"),
    ],
)
def test_mistakes_in_the_form_are_explained_before_anything_is_planned(
    scan_form: PlanForm,
    changes: dict,
    message: str,  # type: ignore[type-arg]
) -> None:
    with pytest.raises(FormError, match=message):
        build_scan(replace(scan_form, **changes))
    assert (
        not list(Path(scan_form.out_dir).glob("*.kmz"))
        if Path(scan_form.out_dir).exists()
        else True
    )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"object_radius_m": 0.0}, "radius"),
        ({"object_height_m": 0.5, "base_height_m": 2.0}, "higher than"),
        ({"look_up_deg": 60.0}, "at most 40"),
        ({"scan_speed_ms": 0.0}, "speed"),
    ],
)
def test_numbers_that_make_no_sense_are_refused_by_the_planner_with_its_reason(
    scan_form: PlanForm,
    changes: dict,
    message: str,  # type: ignore[type-arg]
) -> None:
    with pytest.raises(PlanningError, match=message):
        execute_scan(replace(scan_form, **changes))


def test_a_plan_that_breaks_a_rule_comes_back_with_its_reasons_and_writes_nothing(
    scan_form: PlanForm,
) -> None:
    result = execute_scan(replace(scan_form, standoff_m=3.0))
    assert result.outputs is None and "SC001" in {i.code for i in result.blocked}
    assert not list(Path(scan_form.out_dir).glob("*.kmz"))
