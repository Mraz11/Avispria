# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import numpy as np
import pytest
from shapely.geometry import Polygon

from avispria.core.geometry import AoiError, LocalFrame, load_aoi, utm_crs_for

SQUARE = {
    "type": "Polygon",
    "coordinates": [
        [[90.40, 23.80], [90.41, 23.80], [90.41, 23.81], [90.40, 23.81], [90.40, 23.80]]
    ],
}


def test_load_polygon_feature_and_collection() -> None:
    poly = load_aoi(SQUARE)
    assert isinstance(poly, Polygon)
    feature = {"type": "Feature", "properties": {}, "geometry": SQUARE}
    assert load_aoi(feature).equals(poly)
    fc = {"type": "FeatureCollection", "features": [feature]}
    assert load_aoi(fc).equals(poly)


@pytest.mark.parametrize(
    "bad",
    [
        {"type": "Point", "coordinates": [90.0, 23.0]},
        {"type": "FeatureCollection", "features": []},
        {"type": "Polygon", "coordinates": [[[200, 0], [201, 0], [201, 1], [200, 0]]]},
        {"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]]},
    ],
)
def test_load_rejects_bad_aoi(bad: dict[str, object]) -> None:
    with pytest.raises(AoiError):
        load_aoi(bad)


def test_utm_zone_selection() -> None:
    assert utm_crs_for(90.4, 23.8) == "EPSG:32646"
    assert utm_crs_for(-58.4, -34.6) == "EPSG:32721"


def test_local_frame_round_trip() -> None:
    frame = LocalFrame.for_polygon(load_aoi(SQUARE))
    lons = np.array([90.40, 90.405, 90.41])
    lats = np.array([23.80, 23.805, 23.81])
    xs, ys = frame.to_local(lons, lats)
    back_lon, back_lat = frame.to_lonlat(xs, ys)
    assert np.allclose(back_lon, lons, atol=1e-9)
    assert np.allclose(back_lat, lats, atol=1e-9)


def test_local_polygon_area_is_metric() -> None:
    poly = load_aoi(SQUARE)
    frame = LocalFrame.for_polygon(poly)
    local = frame.polygon_to_local(poly)
    # 0.01 deg x 0.01 deg at 23.8 N is roughly 1019 m x 1107 m
    assert 1.0e6 < local.area < 1.2e6


def test_rectangle_from_numbers_has_the_requested_size_and_centre() -> None:
    from avispria.core.geometry import LocalFrame, rectangle_polygon

    rect = rectangle_polygon(lat=23.8103, lon=90.4125, width_m=200.0, length_m=300.0)
    frame = LocalFrame.for_polygon(rect)
    local = frame.polygon_to_local(rect)
    assert local.area == pytest.approx(200.0 * 300.0, rel=0.002)
    centre = rect.centroid
    assert (centre.y, centre.x) == pytest.approx((23.8103, 90.4125), abs=1e-6)
    minx, miny, maxx, maxy = local.bounds
    assert (maxx - minx) == pytest.approx(200.0, abs=0.5)  # heading 0: long side runs north
    assert (maxy - miny) == pytest.approx(300.0, abs=0.5)


def test_rectangle_heading_turns_the_long_side() -> None:
    from avispria.core.geometry import LocalFrame, rectangle_polygon

    east_west = rectangle_polygon(23.8103, 90.4125, width_m=100.0, length_m=400.0, heading_deg=90.0)
    local = LocalFrame.for_polygon(east_west).polygon_to_local(east_west)
    minx, miny, maxx, maxy = local.bounds
    assert (maxx - minx) == pytest.approx(400.0, abs=0.5)
    assert (maxy - miny) == pytest.approx(100.0, abs=0.5)
    diagonal = rectangle_polygon(23.8103, 90.4125, 100.0, 400.0, heading_deg=45.0)
    assert LocalFrame.for_polygon(diagonal).polygon_to_local(diagonal).area == pytest.approx(
        100.0 * 400.0, rel=0.002
    )


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"lat": 95.0, "lon": 0.0, "width_m": 10.0, "length_m": 10.0}, "latitude"),
        ({"lat": 0.0, "lon": 200.0, "width_m": 10.0, "length_m": 10.0}, "longitude"),
        ({"lat": 0.0, "lon": 0.0, "width_m": 0.0, "length_m": 10.0}, "size"),
        ({"lat": 0.0, "lon": 0.0, "width_m": 10.0, "length_m": 20000.0}, "size"),
    ],
)
def test_rectangle_rejects_nonsense(kwargs: dict[str, float], match: str) -> None:
    from avispria.core.geometry import AoiError, rectangle_polygon

    with pytest.raises(AoiError, match=match):
        rectangle_polygon(**kwargs)
