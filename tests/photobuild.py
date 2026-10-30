# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Build small DJI-like JPEG photos (EXIF + DJI XMP) for tests."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from tiffbuild import dji_xmp


def make_dji_jpeg(
    path: Path,
    size: tuple[int, int] = (8064, 6048),
    lat: float = 22.2823982,
    lon: float = 91.7798470,
    altitude: float = 60.0,
    absolute_altitude: float | None = None,
) -> Path:
    img = Image.new("RGB", size, (80, 130, 60))
    exif = Image.Exif()
    exif[0x010F], exif[0x0110] = "DJI", "FC9589"
    exif_ifd = exif.get_ifd(0x8769)
    exif_ifd[0x920A] = 6.72  # FocalLength
    exif_ifd[0xA405] = 24  # FocalLengthIn35mmFormat
    exif_ifd[0x9003] = "2026:10:24 12:04:56"
    exif_ifd[40962], exif_ifd[40963] = size
    exif[0x8825] = {1: "N", 2: (22.0, 16.0, 56.6), 3: "E", 4: (91.0, 46.0, 47.5)}
    xmp = dji_xmp(
        GpsLatitude=f"{lat:+.7f}",
        GpsLongitude=f"{lon:+.7f}",
        RelativeAltitude=f"{altitude:+.1f}",
        **({} if absolute_altitude is None else {"AbsoluteAltitude": f"{absolute_altitude:+.3f}"}),
        GimbalPitchDegree="-90.0",
        GimbalYawDegree="0.0",
        ShutterType="Electronic",
    )
    img.save(path, "JPEG", exif=exif, xmp=xmp, quality=90)
    return path


def _dms(value: float) -> tuple[float, float, float]:
    value = abs(value)
    degrees = int(value)
    minutes = int((value - degrees) * 60)
    return float(degrees), float(minutes), round(((value - degrees) * 60 - minutes) * 60, 6)


def make_exif_only_jpeg(
    path: Path,
    size: tuple[int, int] = (5472, 3648),
    lat: float = 47.6435,
    lon: float = 16.4763,
    altitude_asl: float = 513.1,
    model: str = "XT705",
) -> Path:
    """A photo like the Autel EVO II Pro RTK's: position and height above SEA LEVEL in the EXIF,
    no height above takeoff, no camera angle, no DJI fields; text padded with NUL characters."""
    img = Image.new("RGB", size, (80, 130, 60))
    exif = Image.Exif()
    exif[0x010F], exif[0x0110] = "Autel Robotics" + "\0" * 8, model + "\0" * 10
    exif_ifd = exif.get_ifd(0x8769)
    exif_ifd[0x920A] = 10.57  # FocalLength
    exif_ifd[0xA405] = 29  # FocalLengthIn35mmFormat
    exif_ifd[0x9003] = "2022:05:25 12:20:09"
    exif_ifd[40962], exif_ifd[40963] = size  # ExifImageWidth / ExifImageHeight
    exif[0x8825] = {
        1: "N" if lat >= 0 else "S",
        2: _dms(lat),
        3: "E" if lon >= 0 else "W",
        4: _dms(lon),
        5: 0,  # above sea level
        6: altitude_asl,
    }
    img.save(path, "JPEG", exif=exif, quality=90)
    return path
