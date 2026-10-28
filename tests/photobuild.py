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
        GimbalPitchDegree="-90.0",
        GimbalYawDegree="0.0",
        ShutterType="Electronic",
    )
    img.save(path, "JPEG", exif=exif, xmp=xmp, quality=90)
    return path
