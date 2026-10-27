# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import json
from pathlib import Path

import pytest

from avispria.adapters.profiles import load_profiles

CAP = Path(__file__).resolve().parents[1] / "fixtures" / "dji_fly_dummy" / "lito_x1_capability"


def test_lito_x1_speed_matches_dji_fly_capability() -> None:
    cap = json.loads((CAP / "SPEEDCapability.json").read_text())
    assert load_profiles()["lito-x1"].max_speed_ms == pytest.approx(cap["max"])


def test_gimbal_nadir_is_within_dji_fly_capability() -> None:
    cap = json.loads((CAP / "GIMBAL_PITCHCapability.json").read_text())
    assert cap["min"] <= -90.0 <= cap["max"]


def test_profiles_have_both_camera_modes() -> None:
    profiles = load_profiles()
    for key in ("lito-x1", "mini-4-pro"):
        assert set(profiles[key].modes) == {"12mp", "48mp"}
        assert profiles[key].drone_enum == 68


def test_user_override_file(tmp_path: Path) -> None:
    override = tmp_path / "mine.toml"
    override.write_text(
        '[lito-x1]\nname = "Mine"\nmax_speed_ms = 8.0\ndrone_enum = 68\nwaypoint_limit = 50\n'
        "[lito-x1.modes.12mp]\nsensor_width_mm = 9.0\nsensor_height_mm = 6.75\nfocal_mm = 6.7\n"
        "image_width_px = 4032\nimage_height_px = 3024\nmin_interval_s = 2.5\nreadout_s = 0.03\n"
    )
    p = load_profiles(override)["lito-x1"]
    assert (p.name, p.max_speed_ms, p.waypoint_limit) == ("Mine", 8.0, 50)
