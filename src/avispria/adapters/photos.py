# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read survey photo metadata (JPEG or DNG) from disk without loading pixels."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from pathlib import Path

from avispria.adapters.exif import ExifError, read_exif
from avispria.adapters.xmp import read_xmp
from avispria.core.photo import PhotoRecord

PHOTO_SUFFIXES = {".jpg", ".jpeg", ".dng"}
HEAD_BYTES = 512 * 1024  # EXIF and DJI XMP sit near the start of JPEG and DNG files


def _num(values: dict[str, str], key: str) -> float | None:
    raw = values.get(key)
    if raw is None or raw == "":
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _time(xmp: dict[str, str], exif_time: str | None) -> datetime | None:
    raw = xmp.get("CreateDate")
    if raw:
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            pass
    if exif_time:
        try:
            return datetime.strptime(exif_time, "%Y:%m:%d %H:%M:%S")
        except ValueError:
            return None
    return None


def read_photo(path: Path) -> PhotoRecord:
    """Metadata of one photo. Raises ExifError if the file has no readable EXIF."""
    size = path.stat().st_size
    with path.open("rb") as handle:
        head = handle.read(HEAD_BYTES)

        def read(offset: int, n: int) -> bytes:
            handle.seek(offset)
            return handle.read(n)

        is_tiff = head[:2] in (b"II", b"MM")
        exif = read_exif(head, read=read if is_tiff else None, size=size if is_tiff else None)
    xmp = read_xmp(head)
    vx, vy = _num(xmp, "FlightXSpeed"), _num(xmp, "FlightYSpeed")
    return PhotoRecord(
        name=path.name,
        time=_time(xmp, exif.datetime_original),
        lat=_num(xmp, "GpsLatitude"),
        lon=_num(xmp, "GpsLongitude"),
        relative_altitude_m=_num(xmp, "RelativeAltitude"),
        gimbal_pitch_deg=_num(xmp, "GimbalPitchDegree"),
        gimbal_yaw_deg=_num(xmp, "GimbalYawDegree"),
        speed_ms=None if vx is None or vy is None else math.hypot(vx, vy),
        exposure_s=exif.exposure_s,
        iso=exif.iso,
        focal_mm=exif.focal_mm,
        focal_35mm=exif.focal_35mm,
        width_px=exif.width_px,
        height_px=exif.height_px,
        model=exif.model or xmp.get("Model"),
        product=xmp.get("ProductName"),
        shutter=xmp.get("ShutterType"),
    )


def _sort_key(r: PhotoRecord) -> tuple[float, str]:
    if r.time is None:
        return (math.inf, r.name)
    t = r.time if r.time.tzinfo else r.time.replace(tzinfo=UTC)
    return (t.timestamp(), r.name)


def scan_photos(folder: Path) -> tuple[list[PhotoRecord], list[tuple[str, str]]]:
    """All photos in ``folder`` in capture order, plus (file, reason) for unreadable ones."""
    records: list[PhotoRecord] = []
    skipped: list[tuple[str, str]] = []
    for path in sorted(folder.iterdir()):
        if not path.is_file() or path.suffix.lower() not in PHOTO_SUFFIXES:
            continue
        try:
            records.append(read_photo(path))
        except (ExifError, OSError) as exc:
            skipped.append((path.name, str(exc)))
    return sorted(records, key=_sort_key), skipped
