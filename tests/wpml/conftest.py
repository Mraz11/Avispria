# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path

import pytest
from shapely.geometry import box

from avispria.core.camera import CameraProfile
from avispria.core.mission import Mission, PhotoMode
from avispria.core.planner import PlanRequest, plan

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "dji_fly_dummy" / "lito_x1_5wp.kmz"
CAM = CameraProfile("test-12mp", 8.97, 6.72, 6.72, 4032, 3024, min_interval_s=2.0, readout_s=0.03)


@pytest.fixture
def dummy_bytes() -> bytes:
    return FIXTURE.read_bytes()


def _plan(mode: PhotoMode) -> Mission:
    req = PlanRequest(
        aoi=box(-0.0030, 51.4760, -0.0010, 51.4772),
        camera=CAM,
        drone_max_speed_ms=12.0,
        takeoff_lon=-0.0020,
        takeoff_lat=51.4766,
        agl_m=50.0,
        flat_terrain=True,
        photo_mode=mode,
    )
    return plan(req).missions[0]


@pytest.fixture
def interval_mission() -> Mission:
    return _plan(PhotoMode.INTERVAL)


@pytest.fixture
def photo_mission() -> Mission:
    return _plan(PhotoMode.WAYPOINT)
