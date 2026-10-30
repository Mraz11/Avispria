# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import json
import math
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from avispria.core.camera import CameraProfile, footprint_m, gsd_m
from avispria.core.capture import QaThresholds, analyse_capture
from avispria.core.photo import PhotoRecord

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "photos" / "lito_x1_manual_2x2.json"
CAM = CameraProfile("fc9589-48mp", 9.692, 7.269, 6.72, 8064, 6048, 5.0, 0.03)
T0 = datetime(2026, 10, 24, 12, 0, 0)


def real_2x2() -> list[PhotoRecord]:
    out = []
    for p in json.loads(FIXTURE.read_text())["photos"]:
        vx, vy, _ = p["flight_speed_ms"]
        out.append(
            PhotoRecord(
                name=p["file"],
                time=datetime.strptime(p["create_date"], "%Y:%m:%d %H:%M:%S"),
                lat=p["lat"],
                lon=p["lon"],
                relative_altitude_m=p["relative_altitude_m"],
                gimbal_pitch_deg=p["gimbal_pitch_deg"],
                gimbal_yaw_deg=p["gimbal_yaw_deg"],
                speed_ms=math.hypot(vx, vy),
                exposure_s=p["exposure_s"],
                iso=p["iso"],
                focal_mm=p["focal_mm"],
                focal_35mm=p["focal_35mm"],
                width_px=p["width_px"],
                height_px=p["height_px"],
                model=p["model"],
                product=p["product"],
                shutter=p["shutter"],
            )
        )
    return out


def grid(rows: int, cols: int, dx: float, dy: float, alt: float = 60.0) -> list[PhotoRecord]:
    """Lawnmower photos: rows run north, columns step east (metres near Greenwich)."""
    out = []
    lat0, lon0 = 51.4769, -0.0015
    m_lat, m_lon = 111_320.0, 111_320.0 * math.cos(math.radians(lat0))
    k = 0
    for c in range(cols):
        for r in range(rows) if c % 2 == 0 else reversed(range(rows)):
            out.append(
                PhotoRecord(
                    f"P{k:03d}.JPG",
                    T0 + timedelta(seconds=2 * k),
                    lat0 + r * dy / m_lat,
                    lon0 + c * dx / m_lon,
                    alt,
                    -90.0,
                    0.0,
                    5.0,
                    1 / 2000,
                    100,
                    6.72,
                    24,
                    8064,
                    6048,
                    "FC9589",
                    "Lito X1",
                    "Electronic",
                )
            )
            k += 1
    return out


def codes(report) -> set[str]:  # type: ignore[no-untyped-def]
    return {i.code for i in report.issues}


def test_real_manual_capture_overlaps() -> None:
    rep = analyse_capture(real_2x2(), lambda r: CAM)
    assert rep.stats["photos_used"] == 4
    assert rep.stats["gsd_cm_median"] == pytest.approx(3.57, abs=0.02)
    by = {p.name: p for p in rep.photos}
    # 0043 is ~173 m west of 0042 with a 287.7 m wide footprint -> ~37% overlap
    assert by["DJI_20261024120528_0043_D.DNG"].overlap_prev == pytest.approx(0.36, abs=0.03)
    # 0044 is ~43 m south of 0043 with a 215.8 m tall footprint -> ~78% overlap
    assert by["DJI_20261024120558_0044_D.DNG"].overlap_prev == pytest.approx(0.78, abs=0.03)
    # every photo has a north-south neighbour with >60% overlap ...
    assert "QA010" not in codes(rep)
    # ... but the east-west spacing leaves much of the area seen by too few photos
    assert rep.stats["area_pct_min_views"] == pytest.approx(76, abs=5)
    assert rep.stats["area_pct_good_views"] == 0.0
    assert "QA006" in codes(rep)


def test_good_grid_has_no_issues() -> None:
    w, h = footprint_m(CAM, 60.0)
    photos = grid(rows=8, cols=6, dx=w * 0.3, dy=h * 0.2)  # 70% side, 80% front overlap
    rep = analyse_capture(photos, lambda r: CAM)
    assert rep.issues == [], rep.issues
    assert rep.stats["area_pct_good_views"] > 95.0
    assert rep.stats["interval_s_median"] == pytest.approx(2.0)


def test_detects_oblique_blur_altitude_and_gaps() -> None:
    photos = grid(rows=6, cols=3, dx=20.0, dy=10.0)
    photos[2] = replace(photos[2], gimbal_pitch_deg=-60.0)
    photos[3] = replace(photos[3], speed_ms=12.0, exposure_s=1 / 100)
    photos[4] = replace(photos[4], relative_altitude_m=90.0)
    later = [replace(p, time=p.time + timedelta(seconds=60)) for p in photos[8:]]  # type: ignore[operator]
    rep = analyse_capture(photos[:8] + later, lambda r: CAM)
    assert {"QA001", "QA002", "QA003", "QA005"} <= codes(rep)


def test_missing_metadata_and_too_few_photos() -> None:
    p = grid(rows=2, cols=1, dx=10, dy=10)
    p[1] = replace(p[1], lat=None)
    rep = analyse_capture(p, lambda r: CAM)
    assert {"QA007", "QA009"} <= codes(rep)
    assert rep.stats["photos_used"] == 1


def test_thresholds_are_configurable() -> None:
    strict = analyse_capture(real_2x2(), lambda r: CAM, QaThresholds(min_neighbour_overlap=0.9))
    assert "QA010" in codes(strict)
    lenient = analyse_capture(real_2x2(), lambda r: CAM, QaThresholds(good_views=4, min_views=2))
    assert lenient.stats["area_pct_min_views"] == pytest.approx(100.0)


def test_height_above_ground_drives_gsd_and_footprints() -> None:
    w, h = footprint_m(CAM, 60.0)
    photos = grid(rows=4, cols=3, dx=w * 0.3, dy=h * 0.2)
    flat = analyse_capture(photos, lambda r: CAM)
    aware = analyse_capture(photos, lambda r: CAM, agl_m={p.name: 40.0 for p in photos})
    assert flat.stats["terrain_aware"] == 0.0 and aware.stats["terrain_aware"] == 1.0
    assert aware.stats["gsd_cm_median"] == pytest.approx(
        flat.stats["gsd_cm_median"] * 40 / 60, rel=1e-3
    )
    assert aware.stats["altitude_m_median"] == pytest.approx(40.0)
    # same spacing, smaller footprints: less overlap
    assert aware.stats["overlap_prev_median"] < flat.stats["overlap_prev_median"]


def test_altitude_spread_is_judged_on_height_above_ground() -> None:
    photos = grid(rows=4, cols=3, dx=20.0, dy=10.0)
    varying_rel = [replace(p, relative_altitude_m=60.0 + 4 * (i % 3)) for i, p in enumerate(photos)]
    assert "QA003" in codes(analyse_capture(varying_rel, lambda r: CAM))  # flat view: mixed
    steady_agl = {p.name: 50.0 for p in varying_rel}  # terrain-following flight
    assert "QA003" not in codes(analyse_capture(varying_rel, lambda r: CAM, agl_m=steady_agl))
    constant_rel = grid(rows=4, cols=3, dx=20.0, dy=10.0)
    uneven = {p.name: 40.0 + 6 * (i % 3) for i, p in enumerate(constant_rel)}  # hilly ground
    assert "QA003" in codes(analyse_capture(constant_rel, lambda r: CAM, agl_m=uneven))


def test_front_and_side_overlap_are_measured_separately() -> None:
    w, h = footprint_m(CAM, 60.0)
    photos = grid(rows=8, cols=6, dx=w * 0.3, dy=h * 0.2)  # 70% side, 80% front
    rep = analyse_capture(photos, lambda r: CAM)
    assert rep.stats["front_overlap_median"] == pytest.approx(0.80, abs=0.02)
    assert rep.stats["side_overlap_median"] == pytest.approx(0.70, abs=0.02)
    assert rep.stats["side_overlap_p10"] == pytest.approx(0.70, abs=0.02)
    assert all(p.front_overlap is not None and p.side_overlap is not None for p in rep.photos)


def test_a_single_strip_has_no_side_overlap_and_a_gap_between_strips_is_flagged() -> None:
    w, h = footprint_m(CAM, 60.0)
    one_strip = analyse_capture(grid(rows=8, cols=1, dx=0.0, dy=h * 0.2), lambda r: CAM)
    assert "side_overlap_median" not in one_strip.stats
    assert one_strip.stats["front_overlap_median"] == pytest.approx(0.80, abs=0.02)
    # strips spaced so that side overlap is only ~30%: front overlap alone cannot hide that
    gappy = analyse_capture(grid(rows=8, cols=4, dx=w * 0.7, dy=h * 0.2), lambda r: CAM)
    assert gappy.stats["side_overlap_median"] == pytest.approx(0.30, abs=0.02)
    assert "QA014" in codes(gappy) and "QA014" not in codes(
        analyse_capture(grid(rows=8, cols=4, dx=w * 0.3, dy=h * 0.2), lambda r: CAM)
    )


def test_coverage_can_be_measured_over_a_given_area() -> None:
    from shapely.geometry import box

    w, h = footprint_m(CAM, 60.0)
    rows, cols, dx, dy = 6, 4, w * 0.3, h * 0.2
    photos = grid(rows, cols, dx, dy)
    lon0, lat0 = -0.0015, 51.4769
    m_lat, m_lon = 111_320.0, 111_320.0 * math.cos(math.radians(lat0))
    east, north = (cols - 1) * dx / m_lon, (rows - 1) * dy / m_lat
    hull = analyse_capture(photos, lambda r: CAM).stats["area_pct_good_views"]
    inside = box(lon0 + east * 0.3, lat0 + north * 0.3, lon0 + east * 0.7, lat0 + north * 0.7)
    wide = box(lon0 - 3 * east, lat0 - 3 * north, lon0 + 4 * east, lat0 + 4 * north)
    assert analyse_capture(photos, lambda r: CAM, region=inside).stats["area_pct_good_views"] == (
        pytest.approx(100.0, abs=1.0)
    )
    # an area much larger than the surveyed block is mostly seen by nobody
    assert (
        analyse_capture(photos, lambda r: CAM, region=wide).stats["area_pct_good_views"] < hull - 30
    )


def test_neighbour_search_matches_brute_force() -> None:
    import random

    from shapely.geometry import Polygon  # noqa: F401  (documenting what is compared)

    from avispria.core.footprints import footprints_for, local_frame

    rng = random.Random(7)
    photos = [
        replace(
            p,
            lon=p.lon + rng.uniform(-3e-4, 3e-4),  # type: ignore[operator]
            lat=p.lat + rng.uniform(-3e-4, 3e-4),  # type: ignore[operator]
            gimbal_yaw_deg=rng.uniform(0, 360),
        )
        for p in grid(rows=5, cols=5, dx=30.0, dy=20.0)
    ]
    rep = analyse_capture(photos, lambda r: CAM)
    fps = footprints_for(photos, lambda r: CAM, {}, local_frame(photos))
    polys = [f.polygon() for f in fps]
    for i, row in enumerate(rep.photos):
        best = max(
            (polys[i].intersection(polys[j]).area / polys[i].area, -j)
            for j in range(len(polys))
            if j != i
        )
        assert row.best_overlap == pytest.approx(best[0], abs=1e-12)
        assert row.best_neighbour == photos[-best[1]].name


def sea_level_only(photos: list, altitude: float = 513.0) -> list:  # type: ignore[type-arg]
    """Photos as an Autel records them: a height above sea level, none above takeoff."""
    return [
        replace(
            p,
            relative_altitude_m=None,
            absolute_altitude_m=altitude + 0.2 * i,
            gimbal_pitch_deg=None,
        )
        for i, p in enumerate(photos)
    ]


def test_photos_with_only_a_sea_level_height_are_used_once_the_height_above_ground_is_known() -> (
    None
):
    w, h = footprint_m(CAM, 60.0)
    photos = sea_level_only(grid(rows=6, cols=3, dx=w * 0.3, dy=h * 0.2))
    heights = {p.name: 60.0 for p in photos}  # e.g. the GPS height minus the ground height
    rep = analyse_capture(photos, lambda r: CAM, agl_m=heights)
    assert (
        rep.stats["photos_used"] == 18 and "QA015" not in codes(rep) and "QA007" not in codes(rep)
    )
    assert rep.stats["gsd_cm_median"] == pytest.approx(gsd_m(CAM, 60.0) * 100, abs=0.001)
    assert rep.stats["front_overlap_median"] == pytest.approx(0.80, abs=0.02)


def test_no_height_above_the_ground_gets_its_own_accurate_message() -> None:
    w, h = footprint_m(CAM, 60.0)
    photos = sea_level_only(grid(rows=6, cols=3, dx=w * 0.3, dy=h * 0.2))
    rep = analyse_capture(photos, lambda r: CAM)
    assert "QA015" in codes(rep) and "QA007" not in codes(
        rep
    )  # the position is there; the height is not
    message = next(i.message for i in rep.issues if i.code == "QA015")
    assert "above sea level" in message and "513-516" in message  # what they do have
    assert rep.stats["photos_used"] == 0 and "QA009" in codes(rep)


def test_a_missing_position_is_still_reported_as_a_missing_position() -> None:
    w, h = footprint_m(CAM, 60.0)
    photos = grid(rows=6, cols=3, dx=w * 0.3, dy=h * 0.2)
    photos[0] = replace(photos[0], lat=None, lon=None)
    rep = analyse_capture(photos, lambda r: CAM)
    assert "QA007" in codes(rep) and "QA015" not in codes(rep)
    assert rep.stats["photos_used"] == 17


def test_an_unrecorded_camera_angle_is_said_aloud_not_silently_assumed() -> None:
    w, h = footprint_m(CAM, 60.0)
    photos = grid(rows=6, cols=3, dx=w * 0.3, dy=h * 0.2)
    assert "QA016" not in codes(analyse_capture(photos, lambda r: CAM))  # DJI photos record it
    unknown = [replace(p, gimbal_pitch_deg=None) for p in photos]
    rep = analyse_capture(unknown, lambda r: CAM)
    assert "QA016" in codes(rep) and rep.stats["photos_used"] == 18  # used, assuming straight down
    assert "straight down" in next(i.message for i in rep.issues if i.code == "QA016")
