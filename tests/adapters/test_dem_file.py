# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path

import numpy as np
import pytest
import rasterio
from pyproj import Transformer
from rasterio.transform import from_origin

from avispria.adapters.dem_file import load_dem_window

X0, Y0 = 699_000.0, 5_706_000.0  # UTM 30N, near Greenwich


def make_surface(path: Path, n: int = 2400, cell: float = 0.05) -> tuple[float, float]:
    """A tilted plane z = 100 + 0.1 * (x - X0), with a no-data hole; returns centre lon/lat."""
    xs = X0 + (np.arange(n) + 0.5) * cell
    data = np.tile((100.0 + 0.1 * (xs - X0)).astype("float32"), (n, 1))
    data[:200, :200] = -9999.0  # no-data corner
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=n,
        width=n,
        count=1,
        dtype="float32",
        crs="EPSG:32630",
        transform=from_origin(X0, Y0, cell, cell),
        nodata=-9999.0,
        compress="deflate",
    ) as dst:
        dst.write(data, 1)
    lon, lat = Transformer.from_crs("EPSG:32630", "EPSG:4326", always_xy=True).transform(
        X0 + n * cell / 2, Y0 - n * cell / 2
    )
    return lon, lat


def test_large_models_are_read_at_reduced_size(tmp_path: Path) -> None:
    path = tmp_path / "dsm.tif"
    lon, lat = make_surface(path)
    bounds = (lon - 1e-4, lat - 1e-4, lon + 1e-4, lat + 1e-4)
    full = load_dem_window(path, bounds)
    small = load_dem_window(path, bounds, max_side_px=300)
    assert full.data.shape == (2400, 2400) and max(small.data.shape) <= 300
    assert small.transform[0] == pytest.approx(0.05 * 2400 / small.data.shape[1], rel=1e-6)
    # the elevation under the centre is the same at both sizes (plane z = 100 + 0.1 * dx)
    x_c, y_c = X0 + 60.0, Y0 - 60.0
    expected = 100.0 + 0.1 * 60.0
    assert full.sample([x_c], [y_c])[0] == pytest.approx(expected, abs=0.01)
    assert small.sample([x_c], [y_c])[0] == pytest.approx(expected, abs=0.05)


def test_no_data_stays_empty_after_reduction(tmp_path: Path) -> None:
    path = tmp_path / "dsm.tif"
    lon, lat = make_surface(path)
    small = load_dem_window(path, (lon - 1e-4, lat - 1e-4, lon + 1e-4, lat + 1e-4), max_side_px=300)
    assert np.isnan(small.sample([X0 + 2.0], [Y0 - 2.0])[0])  # inside the no-data corner
    assert np.isfinite(small.sample([X0 + 60.0], [Y0 - 60.0])[0])
    assert not (small.data < -1000).any()  # no-data never leaks in as a number
