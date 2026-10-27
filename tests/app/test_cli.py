# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import json
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from typer.testing import CliRunner

from avispria.app.cli import app
from avispria.core.wpml.lint import LintLimits, lint_kmz

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "dji_fly_dummy"
DUMMY = FIXTURES / "lito_x1_5wp.kmz"
GUID = "37924189-3F0F-4792-AA10-D50082167E9C"
runner = CliRunner()


@pytest.fixture
def aoi(tmp_path: Path) -> Path:
    ring = [[-0.0030, 51.4760], [-0.0010, 51.4760], [-0.0010, 51.4772], [-0.0030, 51.4772]]
    path = tmp_path / "aoi.geojson"
    path.write_text(json.dumps({"type": "Polygon", "coordinates": [[*ring, ring[0]]]}))
    return path


@pytest.fixture
def dem(tmp_path: Path) -> Path:
    arcsec = 1 / 3600
    lon0, lat0, n = -0.02, 51.49, 120
    lons = lon0 + (np.arange(n) + 0.5) * arcsec
    lats = lat0 - (np.arange(n) + 0.5) * arcsec
    glon, glat = np.meshgrid(lons, lats)
    data = 20.0 + 30.0 * np.exp(
        -(((glon + 0.002) / 0.0006) ** 2 + ((glat - 51.4766) / 0.0004) ** 2)
    )
    path = tmp_path / "dem.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=n,
        width=n,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(lon0, lat0, arcsec, arcsec),
        nodata=-9999.0,
    ) as dst:
        dst.write(data.astype("float32"), 1)
    return path


def _plan(aoi: Path, out: Path, *extra: str) -> object:
    args = [
        "plan",
        str(aoi),
        "--template",
        str(DUMMY),
        "--takeoff",
        "51.4766,-0.0020",
        "--out",
        str(out),
        "--agl",
        "50",
        *extra,
    ]
    return runner.invoke(app, args)


def test_plan_flat_writes_lint_clean_files(aoi: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    result = _plan(aoi, out, "--flat")
    assert result.exit_code == 0, result.output
    assert "Set DJI Fly timed shot" in result.output
    kmz = sorted(out.glob("*.kmz"))
    assert kmz and all(lint_kmz(p.read_bytes(), LintLimits(max_speed_ms=12.0)) == [] for p in kmz)
    assert sorted(out.glob("*_spotcheck.csv"))
    report = json.loads((out / "plan_report.json").read_text())
    assert report["missions"][0]["plan_hash"]
    assert {w["code"] for w in report["warnings"]} >= {"SAF008", "AVI003"}


def test_plan_with_geotiff_dem_follows_terrain(aoi: Path, dem: Path, tmp_path: Path) -> None:
    result = _plan(aoi, tmp_path / "out", "--dem", str(dem))
    assert result.exit_code == 0, result.output
    assert "terrain: DEM" in result.output
    assert "DEM minimum within 45 m" in result.output


def test_plan_requires_terrain_choice(aoi: Path, tmp_path: Path) -> None:
    result = _plan(aoi, tmp_path / "out")
    assert result.exit_code == 1
    assert "terrain data required" in result.output


def test_blocked_plan_writes_nothing(aoi: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    result = _plan(aoi, out, "--flat", "--max-distance", "20")
    assert result.exit_code == 1
    assert "Plan blocked" in result.output and "SAF004" in result.output
    assert not out.exists()


def test_photo_waypoint_mode_warns_about_unverified_encoding(aoi: Path, tmp_path: Path) -> None:
    result = _plan(aoi, tmp_path / "out", "--flat", "--photo-mode", "waypoint")
    assert result.exit_code == 0, result.output
    assert "AVI001" in result.output


def test_inspect_lint_and_sheet(tmp_path: Path) -> None:
    inspected = runner.invoke(app, ["inspect", str(DUMMY)])
    assert inspected.exit_code == 0 and "drone enum    68 / 0" in inspected.output
    assert runner.invoke(app, ["lint", str(DUMMY)]).exit_code == 0
    garbage = tmp_path / "bad.kmz"
    garbage.write_bytes(b"nope")
    assert runner.invoke(app, ["lint", str(garbage)]).exit_code == 1
    sheet = runner.invoke(app, ["sheet", str(DUMMY)])
    assert sheet.exit_code == 0 and sheet.output.count("\n") == 7


def test_prepare_copy_layout(tmp_path: Path) -> None:
    ok = runner.invoke(app, ["prepare-copy", str(DUMMY), "--slot", GUID, "--out", str(tmp_path)])
    assert ok.exit_code == 0, ok.output
    assert (tmp_path / GUID / f"{GUID}.kmz").read_bytes() == DUMMY.read_bytes()
    bad = runner.invoke(
        app, ["prepare-copy", str(DUMMY), "--slot", "not-a-guid", "--out", str(tmp_path)]
    )
    assert bad.exit_code == 1


def test_drones_lists_lito_x1() -> None:
    result = runner.invoke(app, ["drones"])
    assert result.exit_code == 0 and "lito-x1" in result.output


def test_dem_that_misses_the_area_is_rejected(aoi: Path, tmp_path: Path) -> None:
    far = tmp_path / "far.tif"
    with rasterio.open(
        far,
        "w",
        driver="GTiff",
        height=10,
        width=10,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(10.0, 10.0, 0.001, 0.001),
    ) as dst:
        dst.write(np.zeros((10, 10), "float32"), 1)
    result = _plan(aoi, tmp_path / "out", "--dem", str(far))
    assert result.exit_code == 1
    assert "does not cover" in result.output
