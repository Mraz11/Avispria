# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Resize JPEG photos for processing while keeping EXIF (incl. GPS) and DJI XMP."""

from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image

from avispria.core.processing import plan_resize

JPEG_SUFFIXES = {".jpg", ".jpeg"}
TAG_EXIF_IFD = 0x8769
TAG_PIXEL_X = 40962
TAG_PIXEL_Y = 40963


def resize_photo(
    src: Path, dst: Path, max_mp: float | None, quality: int = 95
) -> tuple[int, int, bool]:
    """Write ``src`` to ``dst``, downscaled to at most ``max_mp`` megapixels.

    Returns (width, height, resized). Non-JPEG files (e.g. DNG) and photos that are
    already small enough are copied unchanged.
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.suffix.lower() not in JPEG_SUFFIXES:
        shutil.copy2(src, dst)
        return 0, 0, False
    with Image.open(src) as img:
        width, height = img.size
        target = plan_resize(width, height, max_mp)
        if target is None:
            shutil.copy2(src, dst)
            return width, height, False
        exif = img.getexif()
        exif_ifd = exif.get_ifd(TAG_EXIF_IFD)
        if exif_ifd:
            exif_ifd[TAG_PIXEL_X], exif_ifd[TAG_PIXEL_Y] = target
        xmp = img.info.get("xmp")
        small = img.convert("RGB").resize(target, Image.Resampling.LANCZOS)
        extra: dict[str, object] = {"exif": exif, "quality": quality, "subsampling": 0}
        if xmp:
            extra["xmp"] = xmp
        small.save(dst, "JPEG", **extra)
    shutil.copystat(src, dst)
    return target[0], target[1], True
