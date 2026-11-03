# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A tilted camera's picture, checked against plain ray casting (no formulas shared with it)."""

import math

import pytest

from avispria.adapters.profiles import load_profiles
from avispria.core.camera import (
    MAX_RAY_DEG,
    CameraProfile,
    altitude_for_gsd,
    altitude_for_oblique_gsd,
    footprint_m,
    gsd_m,
    oblique_view,
)
from raycast import ground_point

PROFILE = load_profiles()["lito-x1"]
CAMERAS = [PROFILE.modes["12mp"], PROFILE.modes["48mp"]]


@pytest.mark.parametrize("cam", CAMERAS, ids=lambda c: c.name)
@pytest.mark.parametrize("tilt", [0.0, 10.0, 25.0, 30.0, 40.0])
@pytest.mark.parametrize("h", [40.0, 90.0])
def test_the_footprint_matches_casting_the_rays(cam: CameraProfile, tilt: float, h: float) -> None:
    view = oblique_view(cam, h, tilt)
    half_w, half_h = cam.image_width_px / 2.0, cam.image_height_px / 2.0
    near = [ground_point(cam, h, tilt, x, -half_h) for x in (-half_w, 0.0, half_w)]
    mid = [ground_point(cam, h, tilt, x, 0.0) for x in (-half_w, half_w)]
    far = [ground_point(cam, h, tilt, x, half_h) for x in (-half_w, 0.0, half_w)]
    assert view.near_ahead_m == pytest.approx(near[1][1], rel=1e-9, abs=1e-9)
    assert view.far_ahead_m == pytest.approx(far[1][1], rel=1e-9)
    assert view.along_m == pytest.approx(far[1][1] - near[1][1], rel=1e-9)
    assert view.across_near_m == pytest.approx(near[2][0] - near[0][0], rel=1e-9)
    assert view.across_centre_m == pytest.approx(mid[1][0] - mid[0][0], rel=1e-9)
    assert view.across_far_m == pytest.approx(far[2][0] - far[0][0], rel=1e-9)
    assert view.gsd_centre_m == pytest.approx(view.across_centre_m / cam.image_width_px, rel=1e-9)


@pytest.mark.parametrize("tilt", [0.0, 20.0, 35.0])
def test_the_motion_blur_pixel_size_along_the_track_matches_casting_the_rays(tilt: float) -> None:
    cam, h = CAMERAS[0], 60.0
    half_h = cam.image_height_px / 2.0
    # the ground covered by one pixel step at the near edge, in the direction of flight
    step = (
        ground_point(cam, h, tilt, 0.0, -half_h + 0.5)[1]
        - ground_point(cam, h, tilt, 0.0, -half_h - 0.5)[1]
    )
    assert oblique_view(cam, h, tilt).gsd_along_near_m == pytest.approx(abs(step), rel=2e-4)


def test_straight_down_is_the_old_straight_down_geometry() -> None:
    cam, h = CAMERAS[0], 70.0
    view = oblique_view(cam, h, 0.0)
    across, along = footprint_m(cam, h)
    assert view.across_centre_m == pytest.approx(across, rel=1e-9)
    assert view.along_m == pytest.approx(along, rel=1e-9)
    assert view.gsd_centre_m == pytest.approx(gsd_m(cam, h), rel=1e-9)
    assert view.near_ahead_m == pytest.approx(-view.far_ahead_m)  # symmetrical under the aircraft


def test_a_tilted_picture_is_wider_and_coarser_towards_the_top() -> None:
    view = oblique_view(CAMERAS[0], 60.0, 30.0)
    assert view.across_near_m < view.across_centre_m < view.across_far_m
    assert view.gsd_near_m < view.gsd_centre_m < view.gsd_far_m
    assert view.near_ahead_m < view.far_ahead_m
    assert view.along_m > footprint_m(CAMERAS[0], 60.0)[1]  # it reaches further along the ground


@pytest.mark.parametrize("tilt", [0.0, 15.0, 30.0, 45.0])
def test_the_height_for_a_resolution_gives_that_resolution_at_the_centre(tilt: float) -> None:
    cam = CAMERAS[0]
    h = altitude_for_oblique_gsd(cam, 0.02, tilt)
    assert oblique_view(cam, h, tilt).gsd_centre_m == pytest.approx(0.02, rel=1e-9)
    assert altitude_for_oblique_gsd(cam, 0.02, 0.0) == pytest.approx(altitude_for_gsd(cam, 0.02))
    assert (
        h <= altitude_for_gsd(cam, 0.02) + 1e-9
    )  # a longer slant needs a lower flight for the same detail


def test_a_tilt_that_would_look_near_the_horizon_is_refused_with_the_largest_allowed() -> None:
    cam = CAMERAS[0]
    half = math.degrees(math.atan(cam.image_height_px / 2 / cam.focal_px))
    largest = MAX_RAY_DEG - half
    oblique_view(cam, 50.0, largest - 0.01)  # just allowed
    with pytest.raises(ValueError, match=f"use at most {largest:.0f} degrees"):
        oblique_view(cam, 50.0, largest + 0.5)


@pytest.mark.parametrize("tilt", [-1.0, 90.0, 120.0, float("nan"), float("inf")])
def test_nonsense_tilts_are_refused(tilt: float) -> None:
    with pytest.raises(ValueError, match="tilt"):
        oblique_view(CAMERAS[0], 50.0, tilt)
    with pytest.raises(ValueError, match="height"):
        oblique_view(CAMERAS[0], -5.0, 10.0)
    with pytest.raises(ValueError, match="GSD"):
        altitude_for_oblique_gsd(CAMERAS[0], 0.0, 10.0)
