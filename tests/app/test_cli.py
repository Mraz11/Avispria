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
    codes = {w["code"] for w in report["warnings"]}
    assert "SAF008" in codes and "AVI003" not in codes  # Lito X1 profile is verified


def test_unverified_profile_is_flagged(aoi: Path, tmp_path: Path) -> None:
    result = _plan(aoi, tmp_path / "out", "--flat", "--drone", "mini-4-pro")
    assert result.exit_code == 0, result.output
    assert "AVI003" in result.output


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


def _photo_folder(tmp_path: Path, n: int = 12) -> Path:
    from tiffbuild import IFD_POINTER, build_tiff, dji_xmp, jpeg_with

    folder = tmp_path / "photos"
    folder.mkdir()
    for k in range(n):
        xmp = dji_xmp(
            GpsLatitude=f"{51.4769 + (k % 6) * 0.0001:.7f}",
            GpsLongitude=f"{-0.0015 + (k // 6) * 0.0003:.7f}",
            RelativeAltitude="60.0",
            GimbalPitchDegree="-90.0",
            GimbalYawDegree="0.0",
            FlightXSpeed="3.0",
            FlightYSpeed="0.0",
            ProductName="Lito X1",
        )
        ifds = {
            "ifd0": [(271, 2, "DJI"), (272, 2, "FC9589"), (34665, IFD_POINTER, "exif")],
            "exif": [
                (33434, 5, [(1, 2000)]),
                (36867, 2, f"2026:10:24 12:00:{2 * k:02d}"),
                (37386, 5, [(672, 100)]),
                (41989, 3, 24),
                (40962, 4, 4032),
                (40963, 4, 3024),
            ],
        }
        (folder / f"DJI_{k:04d}.JPG").write_bytes(
            jpeg_with(build_tiff(ifds, ["ifd0", "exif"]), xmp)
        )
    return folder


def test_qa_command_reports_and_writes_csv(tmp_path: Path) -> None:
    folder = _photo_folder(tmp_path)
    csv_path = tmp_path / "qa.csv"
    result = runner.invoke(app, ["qa", str(folder), "--drone", "lito-x1", "--csv", str(csv_path)])
    assert result.exit_code == 0, result.output
    assert "photos: 12 found, 12 used" in result.output
    assert csv_path.read_text().count("\n") == 13


def test_qa_without_profile_derives_camera_from_exif(tmp_path: Path) -> None:
    result = runner.invoke(app, ["qa", str(_photo_folder(tmp_path))])
    assert result.exit_code == 0, result.output
    assert "GSD" in result.output


def test_qa_too_few_photos_fails(tmp_path: Path) -> None:
    result = runner.invoke(app, ["qa", str(_photo_folder(tmp_path, n=2))])
    assert result.exit_code == 1 and "QA009" in result.output


def test_camera_from_photo(tmp_path: Path) -> None:
    photo = next(_photo_folder(tmp_path, n=1).iterdir())
    result = runner.invoke(app, ["camera-from-photo", str(photo), "--key", "lito-x1"])
    assert result.exit_code == 0, result.output
    assert "[lito-x1.modes.12mp]" in result.output
    assert "sensor_width_mm = 9.692" in result.output


def test_qa_points_to_subfolders_with_photos(tmp_path: Path) -> None:
    inner = _photo_folder(tmp_path, n=4)
    parent = inner.parent
    result = runner.invoke(app, ["qa", str(parent)])
    assert result.exit_code == 1
    assert "No photos directly in" in result.output
    assert "photos (4 photos)" in result.output
    recursive = runner.invoke(app, ["qa", str(parent), "--recursive"])
    assert recursive.exit_code == 0, recursive.output
    assert "photos: 4 found, 4 used" in recursive.output


def _fake_doctor(monkeypatch: pytest.MonkeyPatch, ram: float, webodm: bool) -> None:
    from avispria.adapters.system_probe import EngineStatus
    from avispria.app import doctor as doctor_module
    from avispria.core.feasibility import SystemSpec

    spec = SystemSpec("Windows 11", 8, ram, ram * 0.6, 4.0, 300.0)
    engines = [
        EngineStatus(
            "WebODM", "http://localhost:8000/", webodm, "HTTP 200" if webodm else "not running"
        ),
        EngineStatus("Processing node", "http://localhost:3000/info", False, "not running"),
    ]
    monkeypatch.setattr(doctor_module, "probe_system", lambda workdir: spec)
    monkeypatch.setattr(doctor_module, "probe_engines", lambda: engines)


def test_doctor_without_photos(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_doctor(monkeypatch, ram=16.0, webodm=False)
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0, result.output
    assert "16.0 GB total" in result.output
    assert "webodm.org/download" in result.output and "--webodm-url" in result.output


def test_doctor_job_fits(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _fake_doctor(monkeypatch, ram=16.0, webodm=True)
    result = runner.invoke(app, ["doctor", str(_photo_folder(tmp_path))])
    assert result.exit_code == 0, result.output
    assert "WebODM     running" in result.output
    assert "This computer can process these photos." in result.output


def test_doctor_job_too_big_lists_options(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from avispria.app import doctor as doctor_module
    from avispria.core.feasibility import JobSpec

    _fake_doctor(monkeypatch, ram=8.0, webodm=True)
    monkeypatch.setattr(
        doctor_module,
        "job_from_folder",
        lambda folder, recursive=False: (JobSpec(900, 48.8, 54.0), 0),
    )
    result = runner.invoke(app, ["doctor", str(tmp_path)])
    assert result.exit_code == 1
    assert "Not possible on this computer as it is." in result.output
    assert "Split into" in result.output and "works" in result.output


def test_doctor_never_crashes_on_engine_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    from avispria.app import doctor as doctor_module

    _fake_doctor(monkeypatch, ram=16.0, webodm=False)

    def boom() -> list[object]:
        raise RuntimeError("unexpected reply")

    monkeypatch.setattr(doctor_module, "probe_engines", boom)
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0, result.output
    assert "not found running" in result.output
