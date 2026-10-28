# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path

import pytest
from PIL import Image

from avispria.adapters.photos import read_photo
from avispria.adapters.resize import resize_photo
from photobuild import make_dji_jpeg


def test_48mp_becomes_12mp_with_metadata_kept(tmp_path: Path) -> None:
    src = make_dji_jpeg(tmp_path / "DJI_0001.JPG")
    dst = tmp_path / "out" / "DJI_0001.JPG"
    assert resize_photo(src, dst, 12.2) == (4032, 3024, True)
    r = read_photo(dst)
    assert (r.width_px, r.height_px) == (4032, 3024)  # EXIF dimensions updated
    assert r.lat == pytest.approx(22.2823982) and r.relative_altitude_m == pytest.approx(60.0)
    assert r.gimbal_pitch_deg == pytest.approx(-90.0) and r.shutter == "Electronic"
    assert r.focal_mm == pytest.approx(6.72) and r.focal_35mm == 24 and r.model == "FC9589"
    with Image.open(dst) as img:
        assert img.getexif().get_ifd(0x8825)[2] == (22.0, 16.0, 56.6)  # EXIF GPS kept


def test_small_photos_and_dng_are_copied_unchanged(tmp_path: Path) -> None:
    small = make_dji_jpeg(tmp_path / "small.JPG", (4032, 3024))
    out = tmp_path / "o" / "small.JPG"
    assert resize_photo(small, out, 12.2) == (4032, 3024, False)
    assert out.read_bytes() == small.read_bytes()
    dng = tmp_path / "raw.DNG"
    dng.write_bytes(b"II*\0 fake raw")
    assert resize_photo(dng, tmp_path / "o" / "raw.DNG", 12.2)[2] is False
    assert (tmp_path / "o" / "raw.DNG").read_bytes() == dng.read_bytes()
