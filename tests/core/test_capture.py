# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import json
import math
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from avispria.core.camera import CameraProfile, footprint_m
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
