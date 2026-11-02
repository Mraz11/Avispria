# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import json
from dataclasses import replace
from pathlib import Path

import pytest
from typer.testing import CliRunner

from avispria.adapters.profiles import load_profiles
from avispria.app.cli import app
from avispria.app.scan_workflow import run_scan
from avispria.app.workflow import PlanBlockedError
from avispria.core.scan import ScanRequest, plan_scan
from avispria.core.wpml.lint import LintLimits, lint_kmz
from avispria.core.wpml.reader import read_mission

runner = CliRunner()
DUMMY = Path(__file__).resolve().parents[1] / "fixtures" / "dji_fly_dummy" / "lito_x1_5wp.kmz"
LITO = load_profiles()["lito-x1"]
CENTRE = "12.3456,98.7654"


def request(**changes: object) -> ScanRequest:
    base = ScanRequest(
        centre_lon=98.7654,
        centre_lat=12.3456,
        camera=LITO.modes["12mp"],
        drone_max_speed_ms=LITO.max_speed_ms,
        object_height_m=25.0,
        object_radius_m=6.0,
        standoff_m=14.0,
    )
    return replace(base, **changes)  # type: ignore[arg-type]


def test_the_written_missions_say_what_was_planned(tmp_path: Path) -> None:
    out = run_scan(request(hover_s=1.5), DUMMY, LITO, tmp_path / "scan", now_ms=1_793_200_000_000)
    assert [p.name for p in out.kmz_paths] == ["scan_01.kmz", "scan_02.kmz", "scan_03.kmz"]
    planned = [w for m in out.plan.missions for w in m.waypoints]
    written = [w for p in out.kmz_paths for w in read_mission(p.read_bytes()).waypoints]
    assert len(written) == len(planned) == out.plan.summary.photos
    for got, want in zip(written, planned, strict=True):
        assert got.gimbal_pitch_deg == pytest.approx(
            want.gimbal_pitch_deg
        )  # the tilt DJI Fly will use
        assert got.lon == pytest.approx(want.lon, abs=1e-9) and got.height_m == pytest.approx(
            want.height_m, abs=0.05
        )
        assert any(a.func == "takePhoto" for a in got.actions)  # a photo at every waypoint
        assert got.hover_s == 1.5  # standing still for it
        if want.poi is not None:
            assert got.heading_mode == "towardPOI" and got.poi == pytest.approx(want.poi, abs=1e-5)
        else:
            assert got.heading_mode == "smoothTransition" and got.heading_angle_deg == 0.0
        assert got.turn_mode.startswith("toPointAndStop")  # it stops at each photo
    for p in out.kmz_paths:
        assert [i for i in lint_kmz(p.read_bytes(), LintLimits()) if i.level == "error"] == []


def test_the_report_and_the_spot_check_sheets_are_written(tmp_path: Path) -> None:
    out = run_scan(request(), DUMMY, LITO, tmp_path / "scan", now_ms=1_793_200_000_000)
    report = json.loads(out.report_path.read_text())
    assert report["kind"] == "object scan" and report["drone"] == "lito-x1"
    assert [m["file"] for m in report["missions"]] == ["scan_01.kmz", "scan_02.kmz", "scan_03.kmz"]
    assert (
        report["summary"]["photos"]
        == out.plan.summary.photos
        == sum(m["photos"] for m in report["missions"])
    )
    assert all(
        p.read_text().startswith("waypoint") or "," in p.read_text() for p in out.sheet_paths
    )
    assert len(out.sheet_paths) == 3


def test_a_plan_with_a_rule_broken_writes_nothing(tmp_path: Path) -> None:
    with pytest.raises(PlanBlockedError) as info:
        run_scan(request(standoff_m=3.0), DUMMY, LITO, tmp_path / "scan", now_ms=0)
    assert "SC001" in {i.code for i in info.value.issues}
    assert not (tmp_path / "scan").exists()


def test_the_drones_own_waypoint_limit_is_respected(tmp_path: Path) -> None:
    out = run_scan(request(), DUMMY, replace(LITO, waypoint_limit=40), tmp_path / "scan", now_ms=0)
    assert max(len(m.waypoints) for m in out.plan.missions) <= 40
    assert sum(len(m.waypoints) for m in out.plan.missions) == plan_scan(request()).summary.photos


def test_the_command_plans_and_says_what_it_made(tmp_path: Path) -> None:
    out = tmp_path / "scan"
    result = runner.invoke(
        app,
        [
            "scan",
            CENTRE,
            "--template",
            str(DUMMY),
            "--out",
            str(out),
            "--object-height",
            "25",
            "--object-radius",
            "6",
            "--standoff",
            "14",
        ],
    )
    assert result.exit_code == 0, result.output
    assert (
        "4 rings of 36 photos at 20 m from the axis, and a top cap of 32: 176 photos"
        in result.output
    )
    assert "ring 1: camera 5.1 m up, tilt +10 deg, looking at 7.6 m on the object" in result.output
    assert "scan_01.kmz: 72 waypoints" in result.output and "Saved in" in result.output
    assert sorted(p.name for p in out.iterdir()) == sorted(
        [f"scan_0{n}{s}" for n in (1, 2, 3) for s in (".kmz", "_spotcheck.csv")]
        + ["scan_report.json"]
    )


def test_the_command_refuses_a_plan_that_breaks_a_rule_and_writes_nothing(tmp_path: Path) -> None:
    out = tmp_path / "scan"
    result = runner.invoke(
        app,
        [
            "scan",
            CENTRE,
            "--template",
            str(DUMMY),
            "--out",
            str(out),
            "--object-height",
            "25",
            "--object-radius",
            "6",
            "--standoff",
            "3",
        ],
    )
    assert result.exit_code == 1 and "SC001" in result.output and "Not written" in result.output
    assert not out.exists()


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        (["--object-radius", "0"], "radius"),
        (["--look-up", "50"], "at most 40"),
        (["--front", "0.99"], "front overlap"),
    ],
)
def test_the_command_explains_numbers_that_make_no_sense(
    tmp_path: Path, extra: list[str], message: str
) -> None:
    args = [
        "scan",
        CENTRE,
        "--template",
        str(DUMMY),
        "--out",
        str(tmp_path / "s"),
        "--object-height",
        "25",
        "--object-radius",
        "6",
        *extra,
    ]
    result = runner.invoke(app, args)
    assert result.exit_code == 1 and message in result.output


def test_an_unknown_drone_camera_mode_or_place_is_refused(tmp_path: Path) -> None:
    base = [
        "--template",
        str(DUMMY),
        "--out",
        str(tmp_path / "s"),
        "--object-height",
        "25",
        "--object-radius",
        "6",
    ]
    assert runner.invoke(app, ["scan", CENTRE, *base, "--drone", "nope"]).exit_code == 2
    assert runner.invoke(app, ["scan", CENTRE, *base, "--mode", "999mp"]).exit_code == 2
    assert runner.invoke(app, ["scan", "somewhere", *base]).exit_code != 0


def test_a_takeoff_point_and_a_higher_ground_are_used(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "scan",
            CENTRE,
            "--template",
            str(DUMMY),
            "--out",
            str(tmp_path / "s"),
            "--object-height",
            "25",
            "--object-radius",
            "6",
            "--standoff",
            "14",
            "--takeoff",
            "12.3446,98.7654",
            "--ground-offset",
            "4",
        ],
    )
    assert result.exit_code == 0, result.output
    report = json.loads((tmp_path / "s" / "scan_report.json").read_text())
    assert report["options"]["ground_offset_m"] == "4.0"
    assert report["options"]["takeoff_lat"] == "12.3446"
