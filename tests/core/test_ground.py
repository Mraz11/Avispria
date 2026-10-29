# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import math
from datetime import datetime

import numpy as np
import pytest
from pyproj import Transformer

from avispria.core.ground import heights_above_ground
from avispria.core.photo import PhotoRecord
from avispria.core.terrain import Dem

LON0, LAT0 = -0.0100, 51.4900
CELL = 1 / 3600
M_LON = 111_320.0 * math.cos(math.radians(51.48))
SLOPE = 0.05  # metres of elevation per metre eastwards
REF_LON = -0.0050  # elevation 100 m here
TAKEOFF = (REF_LON, 51.4780)


def elevation(lon: np.ndarray) -> np.ndarray:
    return 100.0 + SLOPE * (lon - REF_LON) * M_LON


def geographic_dem(offset: float = 0.0, n: int = 200) -> Dem:
    lons = LON0 + (np.arange(n) + 0.5) * CELL
    data = np.tile(elevation(lons) + offset, (n, 1))
    return Dem(data, (CELL, 0.0, LON0, 0.0, -CELL, LAT0), "EPSG:4326")


def utm_dem(cell: float = 10.0, n: int = 400) -> Dem:
    fwd = Transformer.from_crs("EPSG:4326", "EPSG:32630", always_xy=True)
    back = Transformer.from_crs("EPSG:32630", "EPSG:4326", always_xy=True)
    x0, y0 = fwd.transform(LON0, LAT0)
    xs = x0 + (np.arange(n) + 0.5) * cell
    ys = y0 - (np.arange(n) + 0.5) * cell
    gx, gy = np.meshgrid(xs, ys)
    glon, _ = back.transform(gx, gy)
    return Dem(elevation(np.asarray(glon)), (cell, 0.0, x0, 0.0, -cell, y0), "EPSG:32630")


def photo(
    name: str, east_m: float, rel: float = 50.0, absolute: float | None = None
) -> PhotoRecord:
    lon = REF_LON + east_m / M_LON
    return PhotoRecord(
        name,
        datetime(2026, 1, 1),
        51.4780,
        lon,
        rel,
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
        absolute_altitude_m=absolute,
    )


PHOTOS = [photo(f"P{i}", east) for i, east in enumerate([-60, 0, 60, 120])]


def test_takeoff_mode_uses_only_height_differences() -> None:
    g = heights_above_ground(PHOTOS, geographic_dem(), takeoff=TAKEOFF)
    assert g.mode == "takeoff" and g.issues == [] and g.fallback == []
    # takeoff at east 0 (z=100): a photo 60 m east sits on ground 3 m higher -> 47 m above it
    for p, east in zip(PHOTOS, [-60, 0, 60, 120], strict=True):
        assert g.agl_m[p.name] == pytest.approx(50.0 - SLOPE * east, abs=0.05)
    assert g.takeoff_elevation_m == pytest.approx(100.0, abs=0.05)


def test_takeoff_mode_ignores_a_constant_datum_offset() -> None:
    plain = heights_above_ground(PHOTOS, geographic_dem(), takeoff=TAKEOFF)
    shifted = heights_above_ground(PHOTOS, geographic_dem(offset=80.0), takeoff=TAKEOFF)
    assert shifted.agl_m == pytest.approx(plain.agl_m, abs=1e-6)


def test_absolute_mode_when_the_model_shares_the_photos_height_reference() -> None:
    photos = [
        photo(p.name, e, absolute=150.0) for p, e in zip(PHOTOS, [-60, 0, 60, 120], strict=True)
    ]
    g = heights_above_ground(photos, geographic_dem())  # takeoff elevation 100 + 50 m flight height
    assert g.mode == "absolute" and g.issues == []
    assert g.agl_m["P2"] == pytest.approx(50.0 - SLOPE * 60, abs=0.05)


def test_projected_model_gives_the_same_answer() -> None:
    geo = heights_above_ground(PHOTOS, geographic_dem(), takeoff=TAKEOFF)
    utm = heights_above_ground(PHOTOS, utm_dem(), takeoff=TAKEOFF)
    assert utm.agl_m == pytest.approx(geo.agl_m, abs=0.05)


def test_mismatched_height_reference_is_detected_and_ignored() -> None:
    photos = [
        photo(p.name, e, absolute=150.0) for p, e in zip(PHOTOS, [-60, 0, 60, 120], strict=True)
    ]
    g = heights_above_ground(
        photos, geographic_dem(offset=80.0)
    )  # model 80 m higher than the photos
    assert g.mode == "ignored" and g.agl_m == {}
    assert [i.code for i in g.issues] == ["QA011"]
    assert "--takeoff" in g.issues[0].message


def test_photos_without_absolute_altitude_cannot_use_absolute_mode() -> None:
    g = heights_above_ground(PHOTOS, geographic_dem())  # no takeoff and no absolute altitudes
    assert g.mode == "ignored" and [i.code for i in g.issues] == ["QA011"]


def test_takeoff_outside_the_model_is_an_error() -> None:
    g = heights_above_ground(PHOTOS, geographic_dem(), takeoff=(5.0, 40.0))
    assert g.mode == "ignored" and [(i.level, i.code) for i in g.issues] == [("error", "QA012")]


def test_photos_off_the_map_fall_back_to_relative_altitude() -> None:
    far = PhotoRecord(
        "FAR.JPG",
        datetime(2026, 1, 1),
        40.0,
        5.0,
        50.0,
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
    g = heights_above_ground([*PHOTOS, far], geographic_dem(), takeoff=TAKEOFF)
    assert g.fallback == ["FAR.JPG"] and "FAR.JPG" not in g.agl_m
    assert len(g.agl_m) == 4 and [i.code for i in g.issues] == ["QA013"]


def test_photo_below_the_surface_is_not_trusted() -> None:
    low = photo("LOW.JPG", 300.0, rel=5.0)  # ground 15 m above takeoff -> negative height
    g = heights_above_ground([*PHOTOS, low], geographic_dem(), takeoff=TAKEOFF)
    assert "LOW.JPG" in g.fallback
