# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from avispria.app.ui.plan_job import FormError, PlanForm, build_inputs, execute_plan
from avispria.core.geometry import LocalFrame
from avispria.core.wpml.lint import LintLimits, lint_kmz


def test_a_form_with_numbers_becomes_flyable_missions(plan_form: PlanForm, tmp_path: Path) -> None:
    result = execute_plan(plan_form, now_ms=1_793_200_000_000)
    assert result.outputs is not None and not result.blocked
    out = Path(plan_form.out_dir)
    assert (out / "survey_area.geojson").is_file()  # the rectangle is kept with the plan
    kmz = sorted(out.glob("*.kmz"))
    assert kmz and all(lint_kmz(p.read_bytes(), LintLimits(max_speed_ms=12.0)) == [] for p in kmz)
    assert (out / "plan_report.json").is_file()
    # the area really is the 80 x 120 m rectangle that was asked for
    assert result.aoi is not None
    local = LocalFrame.for_polygon(result.aoi).polygon_to_local(result.aoi)
    assert local.area == pytest.approx(80.0 * 120.0, rel=0.003)
    assert result.takeoff == pytest.approx((90.4125, 23.8103), abs=1e-6)  # centre by default
    assert result.photos and result.outputs.result.summary.prediction is not None


def test_the_takeoff_point_can_be_set_and_the_target_can_be_a_height(plan_form: PlanForm) -> None:
    options = build_inputs(
        replace(plan_form, takeoff="23.8095, 90.4120", target_kind="height", target_value=55.0)
    ).options
    assert (options.takeoff_lat, options.takeoff_lon) == (23.8095, 90.4120)
    assert options.agl_m == 55.0 and options.target_gsd_m is None
    default = build_inputs(plan_form).options
    assert default.target_gsd_m == pytest.approx(0.02) and default.agl_m is None
    assert default.front_overlap == pytest.approx(0.8) and default.side_overlap == pytest.approx(
        0.7
    )


def test_an_area_file_can_be_used_instead(plan_form: PlanForm, tmp_path: Path) -> None:
    ring = [
        [90.4120, 23.8100],
        [90.4130, 23.8100],
        [90.4130, 23.8108],
        [90.4120, 23.8108],
        [90.4120, 23.8100],
    ]
    area = tmp_path / "area.geojson"
    area.write_text(json.dumps({"type": "Polygon", "coordinates": [ring]}))
    result = execute_plan(replace(plan_form, area_mode="file", aoi_file=str(area)))
    assert result.outputs is not None and result.aoi is not None
    assert result.aoi.centroid.x == pytest.approx(90.4125, abs=1e-4)


def test_a_plan_over_an_elevation_model_is_terrain_aware(
    plan_form: PlanForm, tmp_path: Path
) -> None:
    surface = tmp_path / "dem.tif"
    n, cell = 300, 1 / 3600
    xs = 90.40 + (np.arange(n) + 0.5) * cell
    data = np.tile(20.0 + 400.0 * (xs - 90.40), (n, 1)).astype("float32")  # gentle slope
    with rasterio.open(
        surface,
        "w",
        driver="GTiff",
        height=n,
        width=n,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(90.40, 23.82, cell, cell),
    ) as dst:
        dst.write(data, 1)
    result = execute_plan(
        replace(plan_form, terrain="model", dem_file=str(surface), surface_height_m=10.0)
    )
    assert result.outputs is not None
    prediction = result.outputs.result.summary.prediction
    assert prediction is not None and prediction.terrain_aware


def test_a_blocked_plan_comes_back_with_its_reasons_and_writes_no_missions(
    plan_form: PlanForm,
) -> None:
    result = execute_plan(replace(plan_form, max_distance_m=10.0, takeoff="23.8120, 90.4125"))
    assert result.outputs is None and {i.code for i in result.blocked} == {"SAF004"}
    assert list(Path(plan_form.out_dir).glob("*.kmz")) == []


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"aircraft": "nope"}, "Unknown aircraft"),
        ({"camera_mode": "99mp"}, "no camera mode"),
        ({"template": ""}, "Choose the DJI Fly sample mission file"),
        ({"template": "/nowhere/x.kmz"}, "was not found"),
        ({"out_dir": " "}, "Choose the folder where the plan"),
        ({"target_value": 0.0}, "more than zero"),
        ({"front_percent": 99.0}, "front overlap must be between"),
        ({"side_percent": 5.0}, "side overlap must be between"),
        ({"centre": ""}, "Centre of the area: Enter latitude"),
        ({"centre": "95, 10"}, "Centre of the area: Latitude"),
        ({"width_m": 0.0}, "Survey area: size must be"),
        ({"length_m": 50_000.0}, "Survey area: size must be"),
        ({"takeoff": "far away"}, "Takeoff point: Enter latitude"),
        ({"terrain": "model", "dem_file": ""}, "Choose the elevation model"),
        ({"terrain": "model", "dem_file": "/nowhere/d.tif"}, "elevation model was not found"),
        ({"heading_text": "north"}, "direction must be a number"),
        ({"shutter": "fast"}, "like 1/1000"),
        ({"area_mode": "file", "aoi_file": ""}, "Choose the survey area file"),
        ({"area_mode": "file", "aoi_file": "/nowhere/a.geojson"}, "was not found"),
    ],
)
def test_form_mistakes_say_what_to_change(
    plan_form: PlanForm, change: dict[str, object], message: str
) -> None:
    with pytest.raises(FormError, match=message):
        build_inputs(replace(plan_form, **change))  # type: ignore[arg-type]


def test_the_template_must_be_a_kmz_and_the_area_file_valid(
    plan_form: PlanForm, tmp_path: Path
) -> None:
    wrong = tmp_path / "mission.zip"
    wrong.write_bytes(b"x")
    with pytest.raises(FormError, match=r"should be a \.kmz file"):
        build_inputs(replace(plan_form, template=str(wrong)))
    bad = tmp_path / "bad.geojson"
    bad.write_text("{not json")
    with pytest.raises(FormError, match="could not be used"):
        build_inputs(replace(plan_form, area_mode="file", aoi_file=str(bad)))
