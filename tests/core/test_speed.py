# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest

from avispria.core.camera import CameraProfile
from avispria.core.speed import solve_speed

CAM = CameraProfile("t", 9.0, 6.75, 6.75, 4000, 3000, min_interval_s=2.0, readout_s=0.03)


def test_readout_skew_binds_in_bright_light() -> None:
    res = solve_speed(CAM, gsd_m=0.03, shutter_s=1 / 1000, photo_spacing_m=20.0, drone_max_ms=12.0)
    assert res.blur_ms == pytest.approx(15.0)
    assert res.skew_ms == pytest.approx(1.0)
    assert res.speed_ms == pytest.approx(1.0)
    assert res.binding == "rolling-shutter skew"
    assert res.feasible


def test_trigger_interval_binds() -> None:
    res = solve_speed(
        CAM, gsd_m=0.03, shutter_s=1 / 2000, photo_spacing_m=4.0, drone_max_ms=12.0, skew_px=10.0
    )
    assert res.trigger_ms == pytest.approx(2.0)
    assert res.binding == "camera photo interval"


def test_wind_reduces_speed() -> None:
    calm = solve_speed(CAM, 0.03, 1 / 4000, 50.0, 12.0, skew_px=100.0)
    windy = solve_speed(CAM, 0.03, 1 / 4000, 50.0, 12.0, skew_px=100.0, wind_ms=4.0)
    assert windy.speed_ms < calm.speed_ms
    assert windy.binding == "wind headroom"


def test_infeasible_when_below_minimum() -> None:
    res = solve_speed(CAM, 0.005, 1 / 100, 1.0, 12.0, min_speed_ms=1.0)
    assert not res.feasible
    assert res.speed_ms == pytest.approx(1.0)


@pytest.mark.parametrize("kw", [{"shutter_s": 0.0}, {"photo_spacing_m": 0.0}, {"gsd_m": -1.0}])
def test_rejects_bad_inputs(kw: dict[str, float]) -> None:
    args = {"gsd_m": 0.03, "shutter_s": 1 / 1000, "photo_spacing_m": 10.0, "drone_max_ms": 12.0}
    args.update(kw)
    with pytest.raises(ValueError):
        solve_speed(CAM, **args)
