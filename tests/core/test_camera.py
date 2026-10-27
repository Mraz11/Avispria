# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from avispria.core.camera import (
    CameraProfile,
    altitude_for_gsd,
    footprint_m,
    gsd_m,
    oblique_gsd_m,
    sensor_size_from_exif,
    spacing_m,
)

CAM = CameraProfile(
    name="test",
    sensor_width_mm=9.0,
    sensor_height_mm=6.75,
    focal_mm=6.75,
    image_width_px=4000,
    image_height_px=3000,
    min_interval_s=2.0,
    readout_s=0.03,
)


def test_gsd_hand_calculation() -> None:
    # 100 m * 9 mm / (6.75 mm * 4000 px) = 0.0333... m/px
    assert gsd_m(CAM, 100.0) == pytest.approx(100 * 9.0 / (6.75 * 4000))


def test_altitude_for_gsd_inverts_gsd() -> None:
    assert gsd_m(CAM, altitude_for_gsd(CAM, 0.025)) == pytest.approx(0.025)


def test_footprint_landscape_across_is_image_width() -> None:
    across, along = footprint_m(CAM, 100.0)
    assert across == pytest.approx(gsd_m(CAM, 100.0) * 4000)
    assert along == pytest.approx(gsd_m(CAM, 100.0) * 3000)


def test_spacing_from_overlap() -> None:
    sp = spacing_m(CAM, 100.0, front_overlap=0.8, side_overlap=0.7)
    across, along = footprint_m(CAM, 100.0)
    assert sp.photo_m == pytest.approx(along * 0.2)
    assert sp.line_m == pytest.approx(across * 0.3)


@pytest.mark.parametrize("bad", [-0.1, 1.0, 1.5])
def test_spacing_rejects_bad_overlap(bad: float) -> None:
    with pytest.raises(ValueError):
        spacing_m(CAM, 100.0, front_overlap=bad, side_overlap=0.7)


def test_oblique_equals_nadir_at_zero_tilt() -> None:
    along, across = oblique_gsd_m(CAM, 100.0, tilt_deg=0.0)
    assert along == pytest.approx(gsd_m(CAM, 100.0))
    assert across == pytest.approx(gsd_m(CAM, 100.0))


@given(st.floats(min_value=1.0, max_value=60.0))
def test_oblique_gsd_grows_with_tilt(tilt: float) -> None:
    along, across = oblique_gsd_m(CAM, 100.0, tilt_deg=tilt)
    assert along > gsd_m(CAM, 100.0)
    assert across > gsd_m(CAM, 100.0)


def test_sensor_from_exif_matches_35mm_diagonal() -> None:
    w, h = sensor_size_from_exif(6.72, 24.0, 8064, 6048)
    diag_35 = math.hypot(36.0, 24.0)
    assert math.hypot(w, h) == pytest.approx(diag_35 * 6.72 / 24.0)
    assert w / h == pytest.approx(8064 / 6048)


@pytest.mark.parametrize(
    "field",
    ["sensor_width_mm", "focal_mm", "image_width_px", "min_interval_s"],
)
def test_profile_rejects_non_positive(field: str) -> None:
    kwargs = {
        "name": "x",
        "sensor_width_mm": 9.0,
        "sensor_height_mm": 6.75,
        "focal_mm": 6.75,
        "image_width_px": 4000,
        "image_height_px": 3000,
        "min_interval_s": 2.0,
        "readout_s": 0.03,
    }
    kwargs[field] = 0
    with pytest.raises(ValueError):
        CameraProfile(**kwargs)  # type: ignore[arg-type]
