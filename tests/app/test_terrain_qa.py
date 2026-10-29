# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Terrain-aware capture QA against real data: the Brighton Beach flight (DJI Phantom 3)
and the surface model the processing engine (ODX 3.8.4) made from those same photos."""

import json
import statistics
from datetime import datetime
from pathlib import Path

import pytest

from avispria.app.capture_workflow import camera_from_record, terrain_gsd_cm, terrain_heights
from avispria.core.capture import analyse_capture
from avispria.core.photo import PhotoRecord

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
DSM = FIXTURES / "odx" / "brighton_dsm_1m.tif"
ODX_MEASURED_GSD_CM = 1.59  # odm_processing_statistics.average_gsd of that run


def brighton() -> list[PhotoRecord]:
    rows = json.loads((FIXTURES / "photos" / "brighton_beach.json").read_text())["photos"]
    return [
        PhotoRecord(
            name=r["file"],
            time=datetime.fromisoformat(r["time"]),
            lat=r["lat"],
            lon=r["lon"],
            relative_altitude_m=r["relative_altitude_m"],
            gimbal_pitch_deg=r["gimbal_pitch_deg"],
            gimbal_yaw_deg=r["gimbal_yaw_deg"],
            speed_ms=r["speed_ms"],
            exposure_s=r["exposure_s"],
            iso=r["iso"],
            focal_mm=r["focal_mm"],
            focal_35mm=r["focal_35mm"],
            width_px=r["width_px"],
            height_px=r["height_px"],
            model=r["model"],
            product=r["product"],
            shutter=r["shutter"],
            absolute_altitude_m=r["absolute_altitude_m"],
        )
        for r in rows
    ]


def test_terrain_explains_most_of_the_flat_ground_gsd_error() -> None:
    photos = brighton()
    camera = camera_from_record(photos[0])
    flat = analyse_capture(photos, lambda r: camera)
    ground = terrain_heights(photos, DSM, takeoff=None)
    aware = analyse_capture(photos, lambda r: camera, agl_m=ground.agl_m)

    assert ground.mode == "absolute" and ground.issues == [] and ground.fallback == []
    assert aware.stats["terrain_aware"] == 1.0 and aware.stats["terrain_photos"] == 18
    # the ground is several metres above the takeoff point: the drone was ~35.6 m above it
    assert aware.stats["altitude_m_median"] == pytest.approx(35.6, abs=0.6)
    flat_gsd, aware_gsd = flat.stats["gsd_cm_median"], aware.stats["gsd_cm_median"]
    assert flat_gsd == pytest.approx(1.89, abs=0.01)
    assert aware_gsd == pytest.approx(1.68, abs=0.03)
    # against the engine's own measurement: flat ground is >15% off, terrain-aware <8%
    assert abs(flat_gsd - ODX_MEASURED_GSD_CM) / ODX_MEASURED_GSD_CM > 0.15
    assert abs(aware_gsd - ODX_MEASURED_GSD_CM) / ODX_MEASURED_GSD_CM < 0.08
    # the rest (~6%) is the camera-size convention for this 16:9-cropped camera, not terrain


def test_terrain_gsd_helper_matches_the_full_analysis() -> None:
    value = terrain_gsd_cm(brighton(), DSM)
    assert value is not None and value == pytest.approx(1.68, abs=0.03)


def test_takeoff_mode_reproduces_absolute_mode_at_the_implied_takeoff_elevation() -> None:
    """Both modes must agree: put the takeoff on a spot whose elevation equals the one the
    photos imply (absolute altitude minus altitude above takeoff = 158.5 m)."""
    import numpy as np
    import rasterio
    from pyproj import Transformer

    photos = brighton()
    implied = statistics.median(p.absolute_altitude_m - p.relative_altitude_m for p in photos)
    assert implied == pytest.approx(158.51, abs=0.01)
    with rasterio.open(DSM) as src:
        z = src.read(1, masked=True)
        row, col = np.unravel_index(np.argmin(np.abs(z - implied)), z.shape)
        x, y = src.xy(row, col)
        spot_z = float(z[row, col])
        lon, lat = Transformer.from_crs(src.crs, "EPSG:4326", always_xy=True).transform(x, y)
    assert abs(spot_z - implied) < 0.1  # a cell at that elevation exists on the model

    absolute = terrain_heights(photos, DSM, takeoff=None)
    by_takeoff = terrain_heights(photos, DSM, takeoff=(lon, lat))
    assert by_takeoff.mode == "takeoff" and by_takeoff.fallback == []
    diffs = [abs(absolute.agl_m[k] - by_takeoff.agl_m[k]) for k in absolute.agl_m]
    assert max(diffs) < 0.25  # the 1 m model and the cell choice allow a few decimetres
    # and a wrong takeoff elevation shifts every height by exactly that difference
    assert statistics.median(by_takeoff.agl_m.values()) == pytest.approx(
        statistics.median(absolute.agl_m.values()), abs=0.25
    )
