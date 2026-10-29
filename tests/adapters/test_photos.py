# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from avispria.adapters.exif import ExifError, read_exif
from avispria.adapters.photos import read_photo, scan_photos
from avispria.adapters.xmp import read_xmp
from tiffbuild import IFD_POINTER, build_tiff, dji_xmp, jpeg_with

XMP = dji_xmp(
    GpsLatitude="+22.282398204",
    GpsLongitude="+91.779846956",
    RelativeAltitude="+199.300",
    AbsoluteAltitude="+272.097",
    GimbalPitchDegree="-90.00",
    GimbalYawDegree="+4.50",
    FlightXSpeed="0.0",
    FlightYSpeed="0.1",
    FlightZSpeed="0.0",
    ProductName="Lito X1",
    ShutterType="Electronic",
)
EXIF_IFD = [
    (33434, 5, [(1, 1600)]),  # ExposureTime
    (34855, 3, 130),  # ISO
    (36867, 2, "2026:10:24 12:04:56"),  # DateTimeOriginal
    (37386, 5, [(672, 100)]),  # FocalLength
    (41989, 3, 24),  # FocalLengthIn35mmFormat
]


def dng_bytes() -> bytes:
    ifds = {
        "ifd0": [
            (254, 4, 1),  # reduced-resolution thumbnail
            (256, 4, 160),
            (257, 4, 120),
            (271, 2, "DJI"),
            (272, 2, "FC9589"),
            (330, IFD_POINTER, "sub"),
            (34665, IFD_POINTER, "exif"),
            (700, 1, XMP),
        ],
        "exif": EXIF_IFD,
        "sub": [(254, 4, 0), (256, 4, 8064), (257, 4, 6048)],
    }
    return build_tiff(ifds, ["ifd0", "exif", "sub"])


def jpeg_bytes() -> bytes:
    ifds = {
        "ifd0": [(271, 2, "DJI"), (272, 2, "FC9589"), (34665, IFD_POINTER, "exif")],
        "exif": [*EXIF_IFD, (40962, 4, 4032), (40963, 4, 3024)],
    }
    return jpeg_with(build_tiff(ifds, ["ifd0", "exif"]), XMP)


def test_exif_from_dng_uses_full_resolution_subifd() -> None:
    e = read_exif(dng_bytes())
    assert (e.make, e.model) == ("DJI", "FC9589")
    assert (e.width_px, e.height_px) == (8064, 6048)
    assert e.exposure_s == pytest.approx(1 / 1600)
    assert e.focal_mm == pytest.approx(6.72)
    assert e.focal_35mm == 24 and e.iso == 130
    assert e.datetime_original == "2026:10:24 12:04:56"


def test_exif_from_jpeg() -> None:
    e = read_exif(jpeg_bytes())
    assert (e.width_px, e.height_px) == (4032, 3024)
    assert e.model == "FC9589"


def test_exif_rejects_garbage() -> None:
    with pytest.raises(ExifError):
        read_exif(b"not an image at all")


def test_xmp_values() -> None:
    x = read_xmp(dng_bytes())
    assert x["GpsLatitude"] == "+22.282398204"
    assert x["CreateDate"] == "2026-10-24T12:04:56+06:00"
    assert read_xmp(b"no xmp here") == {}


@pytest.mark.parametrize("make", [dng_bytes, jpeg_bytes])
def test_read_photo_record(tmp_path: Path, make) -> None:  # type: ignore[no-untyped-def]
    suffix = ".DNG" if make is dng_bytes else ".JPG"
    path = tmp_path / f"DJI_0001{suffix}"
    path.write_bytes(make())
    r = read_photo(path)
    assert r.lat == pytest.approx(22.282398204) and r.lon == pytest.approx(91.779846956)
    assert r.relative_altitude_m == pytest.approx(199.3)
    assert r.absolute_altitude_m == pytest.approx(272.097)
    assert r.gimbal_pitch_deg == pytest.approx(-90.0)
    assert r.speed_ms == pytest.approx(0.1)
    assert r.time == datetime(2026, 10, 24, 12, 4, 56, tzinfo=timezone(timedelta(hours=6)))
    assert r.product == "Lito X1" and r.model == "FC9589"


def test_scan_sorts_by_time_and_skips_non_photos(tmp_path: Path) -> None:
    (tmp_path / "b.JPG").write_bytes(jpeg_bytes())
    (tmp_path / "a.DNG").write_bytes(dng_bytes())
    (tmp_path / "notes.txt").write_text("hello")
    (tmp_path / "broken.JPG").write_bytes(b"\xff\xd8 broken")
    photos, skipped = scan_photos(tmp_path)
    assert [p.name for p in photos] == ["a.DNG", "b.JPG"]  # same time: name order
    assert [s[0] for s in skipped] == ["broken.JPG"]


REAL = os.environ.get("AVISPRIA_REAL_PHOTOS")


@pytest.mark.skipif(not REAL, reason="set AVISPRIA_REAL_PHOTOS to a folder of DJI photos")
def test_real_photos_parse() -> None:
    photos, skipped = scan_photos(Path(str(REAL)))
    assert photos and not skipped
    assert all(p.lat is not None and p.relative_altitude_m is not None for p in photos)


def test_recursive_scan_and_subfolder_hints(tmp_path: Path) -> None:
    from avispria.adapters.photos import photo_subfolders

    (tmp_path / "card" / "DCIM" / "100MEDIA").mkdir(parents=True)
    (tmp_path / "card" / "DCIM" / "101MEDIA").mkdir(parents=True)
    (tmp_path / "card" / "DCIM" / "100MEDIA" / "a.JPG").write_bytes(jpeg_bytes())
    (tmp_path / "card" / "DCIM" / "100MEDIA" / "b.JPG").write_bytes(jpeg_bytes())
    (tmp_path / "card" / "DCIM" / "101MEDIA" / "c.DNG").write_bytes(dng_bytes())
    card = tmp_path / "card"
    assert scan_photos(card)[0] == []
    hints = photo_subfolders(card)
    assert hints == [("DCIM/100MEDIA", 2), ("DCIM/101MEDIA", 1)]
    photos, _ = scan_photos(card, recursive=True)
    assert sorted(p.name for p in photos) == [
        "DCIM/100MEDIA/a.JPG",
        "DCIM/100MEDIA/b.JPG",
        "DCIM/101MEDIA/c.DNG",
    ]


def test_exif_numeric_types_from_other_software() -> None:
    """Some writers store focal length as DOUBLE or SHORT instead of RATIONAL."""
    for focal_entry in [(37386, 12, 6.72), (37386, 3, 7)]:
        ifds = {
            "ifd0": [(271, 2, "X"), (34665, IFD_POINTER, "exif")],
            "exif": [focal_entry, (40962, 4, 100), (40963, 4, 100)],
        }
        e = read_exif(build_tiff(ifds, ["ifd0", "exif"]))
        assert e.focal_mm == pytest.approx(float(focal_entry[2]))


def test_exif_gps_fallback_for_older_dji_firmware(tmp_path: Path) -> None:
    """Phantom 3 era photos: DJI XMP has altitude and gimbal but GPS only in EXIF."""
    gps_ifd = [
        (1, 2, "N"),
        (2, 5, [(46, 1), (50, 1), (3339, 100)]),
        (3, 2, "W"),
        (4, 5, [(91, 1), (59, 1), (4042, 100)]),
        (6, 5, [(19831, 100)]),
    ]
    xmp = dji_xmp(RelativeAltitude="+39.80", GimbalPitchDegree="-89.90", GimbalYawDegree="+45.00")
    ifds = {
        "ifd0": [
            (271, 2, "DJI"),
            (272, 2, "FC300S"),
            (34665, IFD_POINTER, "exif"),
            (34853, IFD_POINTER, "gps"),
        ],
        "exif": [(37386, 5, [(36, 10)]), (41989, 3, 20), (40962, 4, 4000), (40963, 4, 2250)],
        "gps": gps_ifd,
    }
    e = read_exif(jpeg_with(build_tiff(ifds, ["ifd0", "exif", "gps"]), xmp))
    assert e.gps_lat == pytest.approx(46 + 50 / 60 + 33.39 / 3600)
    assert e.gps_lon == pytest.approx(-(91 + 59 / 60 + 40.42 / 3600))
    assert e.gps_alt_m == pytest.approx(198.31)
    path = tmp_path / "DJI_0018.JPG"
    path.write_bytes(jpeg_with(build_tiff(ifds, ["ifd0", "exif", "gps"]), xmp))
    r = read_photo(path)
    assert r.lat == pytest.approx(46.842608, abs=1e-6) and r.lon == pytest.approx(
        -91.994561, abs=1e-6
    )
    assert r.relative_altitude_m == pytest.approx(39.8)
    assert r.absolute_altitude_m == pytest.approx(198.31)  # from the EXIF GPS altitude


def test_xmp_position_wins_over_exif() -> None:
    e = read_exif(jpeg_bytes())
    assert e.gps_lat is None  # the synthetic photo has no EXIF GPS block


def test_date_only_xmp_falls_back_to_exif_time() -> None:
    from avispria.adapters.photos import _time

    assert _time({"CreateDate": "2016-06-23"}, "2016:06:23 16:31:59") == datetime(
        2016, 6, 23, 16, 31, 59
    )
    with_tz = _time({"CreateDate": "2026-10-24T12:04:56+06:00"}, "2026:10:24 12:04:56")
    assert with_tz is not None and with_tz.utcoffset() == timedelta(hours=6)
