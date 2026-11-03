# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A 3D plan (tilted camera, lines in two directions) must really cover the area.

Every planned photo's footprint is cast onto flat ground with independent ray code
(tests/raycast.py) and the photos that see each point of the area are counted, the way capture QA
counts real photos.
"""

import math
from dataclasses import replace

import numpy as np
import pytest
import shapely
from shapely.geometry import Polygon

from avispria.adapters.profiles import load_profiles
from avispria.core.camera import OBLIQUE_MIN_DEG, gsd_m, oblique_view
from avispria.core.errors import PlanningError
from avispria.core.geometry import LocalFrame, rectangle_polygon
from avispria.core.mission import PhotoMode
from avispria.core.plan_model import PlanRequest, PlanResult
from avispria.core.planner import plan
from avispria.core.predict import planned_photos
from avispria.core.safety import SafetyLimits
from raycast import footprint

LITO = load_profiles()["lito-x1"]
CAM = LITO.modes["12mp"]
LAT, LON = 51.4769, -0.0015


def request(pitch: float = -90.0, **changes: object) -> PlanRequest:
    aoi = rectangle_polygon(LAT, LON, 120.0, 120.0, 0.0)
    base = PlanRequest(
        aoi=aoi,
        camera=CAM,
        drone_max_speed_ms=LITO.max_speed_ms,
        takeoff_lon=aoi.centroid.x,
        takeoff_lat=aoi.centroid.y,
        target_gsd_m=0.025,
        front_overlap=0.8,
        side_overlap=0.7,
        photo_mode=PhotoMode.WAYPOINT,
        flat_terrain=True,
        gimbal_pitch_deg=pitch,
        limits=SafetyLimits(max_flight_time_s=40 * 60.0, max_waypoints=400),
        name="t",
    )
    return replace(base, **changes)  # type: ignore[arg-type]


def coverage(
    result: PlanResult, req: PlanRequest
) -> tuple[np.ndarray, list[Polygon], list[tuple[float, float, float]]]:
    """For a grid of points inside the area: how many photos see each. Plus the footprints."""
    frame = LocalFrame.for_polygon(req.aoi)
    area = frame.polygon_to_local(req.aoi)
    tilt = 90.0 + req.gimbal_pitch_deg
    x0, y0, x1, y1 = area.bounds  # the planner's frame is in absolute metres, not around zero
    xs, ys = np.meshgrid(np.arange(x0 + 1.0, x1, 2.5), np.arange(y0 + 1.0, y1, 2.5))
    inside = shapely.contains_xy(area, xs.ravel(), ys.ravel())
    px, py = xs.ravel()[inside], ys.ravel()[inside]
    counts = np.zeros(len(px), dtype=int)
    prints: list[Polygon] = []
    meta: list[tuple[float, float, float]] = []
    for mission in result.missions:
        for photo in planned_photos(mission):
            (x,), (y,) = frame.to_local([photo.lon], [photo.lat])
            poly = footprint(CAM, photo.height_rel_m, tilt, float(x), float(y), photo.course_deg)
            counts += shapely.contains_xy(poly, px, py).astype(int)
            prints.append(poly)
            meta.append((float(x), float(y), photo.course_deg))
    return counts, prints, meta


def test_a_3d_plan_sees_every_point_of_the_area_from_many_photos() -> None:
    req = request(pitch=-60.0, crosshatch=True)
    result = plan(req)
    counts, _, _ = coverage(result, req)
    assert (counts >= 3).mean() >= 0.99, (
        f"only {(counts >= 3).mean():.1%} of the area is seen by 3 photos"
    )
    assert (counts >= 5).mean() >= 0.95
    assert np.median(counts) >= 8  # two crossing sets of lines, each overlapping 80% and 70%
    assert counts.min() >= 1


def test_the_tilt_is_in_the_plan_and_in_every_waypoint() -> None:
    result = plan(request(pitch=-60.0, crosshatch=True))
    assert result.summary.tilt_deg == pytest.approx(30.0) and result.summary.oblique is not None
    assert {w.gimbal_pitch_deg for m in result.missions for w in m.waypoints} == {-60.0}
    assert result.summary.prediction is None  # the prediction is for straight-down photos only
    assert plan(request()).summary.oblique is None and plan(request()).summary.tilt_deg == 0.0


def test_consecutive_photos_along_a_line_overlap_as_asked() -> None:
    """Along the track the overlap is 80% of the picture's LENGTH; as an area it is a little less,
    because the wide far end of one picture is not in the next one's narrow near end."""
    req = request(pitch=-60.0, crosshatch=False)
    result = plan(req)
    _, prints, meta = coverage(result, req)
    shares = []
    for k in range(len(prints) - 1):
        (xa, ya, ca), (xb, yb, cb) = meta[k], meta[k + 1]
        if abs(ca - cb) < 1.0 and math.hypot(xa - xb, ya - yb) < 30.0:  # the same line
            shares.append(prints[k].intersection(prints[k + 1]).area / prints[k].area)
    assert len(shares) >= 20
    assert min(shares) >= 0.75 and max(shares) < 0.80  # about 77.7%
    view = result.summary.oblique
    assert view is not None
    assert 1.0 - result.summary.photo_spacing_m / view.along_m == pytest.approx(0.80, abs=1e-9)


def test_the_resolution_asked_for_is_what_the_centre_of_the_picture_gets() -> None:
    result = plan(request(pitch=-60.0, crosshatch=True))
    s = result.summary
    assert s.gsd_m == pytest.approx(0.025, rel=1e-9)
    assert oblique_view(CAM, s.agl_m, 30.0).gsd_centre_m == pytest.approx(0.025, rel=1e-9)
    assert s.agl_m < plan(request()).summary.agl_m  # a longer slant: lower for the same detail


def test_a_tilted_plan_has_different_spacing_and_overrun_from_a_flat_one() -> None:
    tilted, flat = plan(request(pitch=-60.0)), plan(request())
    view = tilted.summary.oblique
    assert view is not None
    assert tilted.summary.photo_spacing_m == pytest.approx(view.along_m * 0.2, rel=1e-9)
    assert tilted.summary.line_spacing_m == pytest.approx(view.across_centre_m * 0.3, rel=1e-9)
    assert flat.summary.photo_spacing_m == pytest.approx(
        gsd_m(CAM, flat.summary.agl_m) * CAM.image_height_px * 0.2, rel=1e-9
    )


def test_crossing_lines_double_the_lines_and_the_photos() -> None:
    one = plan(request(pitch=-60.0, crosshatch=False))
    two = plan(request(pitch=-60.0, crosshatch=True))
    photos = lambda r: sum(m.photo_count for m in r.missions)  # noqa: E731
    assert two.summary.strips > one.summary.strips * 1.8
    assert photos(two) > photos(one) * 1.7


def test_the_lines_start_early_enough_for_a_forward_looking_camera() -> None:
    """A flat-map line starts one photo spacing before the area; a tilted one needs more."""
    flat = plan(request())
    tilted = plan(request(pitch=-60.0))
    area = LocalFrame.for_polygon(request().aoi)

    def margin(result: PlanResult) -> float:
        wps = result.missions[0].waypoints
        xs, ys = area.to_local([w.lon for w in wps[:2]], [w.lat for w in wps[:2]])
        return float(math.hypot(xs[1] - xs[0], ys[1] - ys[0]))

    view = tilted.summary.oblique
    assert view is not None
    assert margin(tilted) >= 2 * tilted.summary.photo_spacing_m + max(view.near_ahead_m, 0.0) - 1e-6
    assert margin(flat) == pytest.approx(
        flat.summary.photo_spacing_m, rel=1e-6
    )  # flat plans unchanged


def test_a_tilt_that_is_too_steep_is_refused_in_plain_words() -> None:
    with pytest.raises(PlanningError, match="too steep"):
        plan(request(pitch=-30.0))  # 60 degrees from straight down


def test_less_than_one_degree_of_tilt_is_a_flat_plan() -> None:
    assert OBLIQUE_MIN_DEG == 1.0
    almost = plan(request(pitch=-89.5))
    assert almost.summary.oblique is None and almost.summary.tilt_deg == 0.0


@pytest.mark.parametrize(
    ("width", "length", "angle", "pitch"),
    [(200.0, 70.0, 30.0, -70.0), (90.0, 160.0, 0.0, -55.0), (150.0, 150.0, 75.0, -65.0)],
)
def test_other_shapes_and_tilts_are_covered_too(
    width: float, length: float, angle: float, pitch: float
) -> None:
    aoi = rectangle_polygon(LAT, LON, width, length, angle)
    req = request(
        pitch=pitch,
        crosshatch=True,
        aoi=aoi,
        takeoff_lon=aoi.centroid.x,
        takeoff_lat=aoi.centroid.y,
    )
    counts, _, _ = coverage(plan(req), req)
    assert len(counts) > 200
    assert (counts >= 3).mean() >= 0.99, f"{width} x {length} at {angle} degrees, pitch {pitch}"
    assert counts.min() >= 1
