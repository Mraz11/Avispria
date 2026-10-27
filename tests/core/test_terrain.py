# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import numpy as np
import pytest

from avispria.core.terrain import Dem, filter_extreme, window_radius_px

# 4 x 5 grid, 10 m pixels, top-left corner at (1000, 2000)
DATA = np.arange(20, dtype=float).reshape(4, 5)
DEM = Dem(DATA, (10.0, 0.0, 1000.0, 0.0, -10.0, 2000.0), "EPSG:32646")


def test_sample_pixel_centres_exactly() -> None:
    xs = np.array([1005.0, 1045.0, 1005.0])
    ys = np.array([1995.0, 1995.0, 1965.0])
    assert np.allclose(DEM.sample(xs, ys), [0.0, 4.0, 15.0])


def test_sample_bilinear_midpoint() -> None:
    assert DEM.sample(np.array([1010.0]), np.array([1990.0]))[0] == pytest.approx(3.0)


def test_sample_outside_is_nan() -> None:
    out = DEM.sample(np.array([900.0, 1003.0]), np.array([1995.0, 1999.0]))
    assert np.isnan(out[0])
    assert out[1] == pytest.approx(0.0)  # inside the outer half pixel: clamped


def test_nodata_neighbour_propagates_nan() -> None:
    data = DATA.copy()
    data[0, 1] = np.nan
    dem = Dem(data, DEM.transform, DEM.crs)
    assert np.isnan(dem.sample(np.array([1010.0]), np.array([1995.0]))[0])


def test_rotated_transform_rejected() -> None:
    with pytest.raises(ValueError):
        Dem(DATA, (10.0, 1.0, 1000.0, 0.0, -10.0, 2000.0), "EPSG:32646")


def test_max_and_min_filters() -> None:
    data = np.zeros((5, 5))
    data[2, 2] = 10.0
    data[0, 0] = np.nan
    dem = Dem(data, DEM.transform, DEM.crs)
    hi = filter_extreme(dem, 1, 1, "max")
    lo = filter_extreme(dem, 1, 1, "min")
    assert hi.data[1:4, 1:4].min() == 10.0
    assert hi.data[4, 4] == 0.0
    assert lo.data[2, 2] == 0.0
    assert not np.isnan(hi.data[0, 0])  # nan ignored when neighbours exist


def test_window_radius_geographic_and_projected() -> None:
    projected = window_radius_px(DEM, radius_m=25.0, lat=23.8)
    assert projected == (3, 3)
    geo = Dem(DATA, (1 / 3600, 0.0, 90.0, 0.0, -1 / 3600, 24.0), "EPSG:4326")
    rx, ry = window_radius_px(geo, radius_m=60.0, lat=23.8)
    assert ry == 2  # 1 arcsec ~ 30.9 m north-south
    assert rx == 3  # ~28.3 m east-west at 23.8 N
