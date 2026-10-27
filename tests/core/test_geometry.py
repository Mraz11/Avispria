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
