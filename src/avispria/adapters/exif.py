# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Minimal, dependency-free EXIF reader for JPEG and TIFF-based raw files (DNG).

Only the handful of tags capture QA needs are decoded. Offsets are bounds-checked
so a corrupt file raises ExifError instead of crashing or reading garbage.
"""

from __future__ import annotations

import struct
from collections.abc import Callable
from dataclasses import dataclass

TAG_NEW_SUBFILE_TYPE = 254
TAG_IMAGE_WIDTH = 256
TAG_IMAGE_LENGTH = 257
TAG_MAKE = 271
TAG_MODEL = 272
TAG_SUB_IFDS = 330
TAG_EXIF_IFD = 34665
TAG_GPS_IFD = 34853
TAG_EXPOSURE_TIME = 33434
TAG_ISO = 34855
TAG_DATETIME_ORIGINAL = 36867
TAG_FOCAL_LENGTH = 37386
TAG_PIXEL_X = 40962
TAG_PIXEL_Y = 40963
TAG_FOCAL_35MM = 41989

_TYPE_SIZES = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1, 9: 4, 10: 8, 11: 4, 12: 8}
MAX_IFD_ENTRIES = 1000


class ExifError(ValueError):
    """The file has no readable EXIF block."""


@dataclass(frozen=True)
class ExifInfo:
    make: str | None = None
    model: str | None = None
    width_px: int | None = None
    height_px: int | None = None
    exposure_s: float | None = None
    iso: int | None = None
    focal_mm: float | None = None
    focal_35mm: int | None = None
    datetime_original: str | None = None
    gps_lat: float | None = None  # decimal degrees, from the standard EXIF GPS block
    gps_lon: float | None = None
    gps_alt_m: float | None = None  # above sea level (older DJI firmware, other drones)


Read = Callable[[int, int], bytes]


class _Tiff:
    def __init__(self, read: Read, size: int) -> None:
        self.read, self.size = read, size
        head = read(0, 8)
        if head[:2] == b"II":
            self.e = "<"
        elif head[:2] == b"MM":
            self.e = ">"
        else:
            raise ExifError("not a TIFF/EXIF structure")
        if struct.unpack(self.e + "H", head[2:4])[0] != 42:
            raise ExifError("bad TIFF magic number")
        self.ifd0 = struct.unpack(self.e + "I", head[4:8])[0]

    def _get(self, offset: int, n: int) -> bytes:
        if offset < 0 or n < 0 or offset + n > self.size:
            raise ExifError("EXIF offset outside the file")
        return self.read(offset, n)

    def ifd(self, offset: int) -> dict[int, tuple[int, int, bytes]]:
        """Map tag -> (type, count, raw value bytes)."""
        (count,) = struct.unpack(self.e + "H", self._get(offset, 2))
        if count > MAX_IFD_ENTRIES:
            raise ExifError("implausible IFD size")
        table = self._get(offset + 2, 12 * count)
        out: dict[int, tuple[int, int, bytes]] = {}
        for i in range(count):
            tag, typ, n = struct.unpack(self.e + "HHI", table[12 * i : 12 * i + 8])
            size = _TYPE_SIZES.get(typ)
            if size is None:
                continue
            total = size * n
            field = table[12 * i + 8 : 12 * i + 12]
            if total <= 4:
                raw = field[:total]
            else:
                if total > 1_000_000:
                    continue  # large arrays (maker notes, tiles) are not needed
                raw = self._get(struct.unpack(self.e + "I", field)[0], total)
            out[tag] = (typ, n, raw)
        return out

    def ints(self, entry: tuple[int, int, bytes] | None) -> list[int]:
        if entry is None:
            return []
        typ, n, raw = entry
        fmt = {1: "B", 3: "H", 4: "I"}.get(typ)
        return list(struct.unpack(self.e + fmt * n, raw)) if fmt else []

    def rational(self, entry: tuple[int, int, bytes] | None) -> float | None:
        """First value of any numeric type as a float (EXIF writers differ: DJI uses
        RATIONAL, other software FLOAT/DOUBLE or integers)."""
        if entry is None or entry[1] < 1:
            return None
        typ, _, raw = entry
        if typ in (5, 10):
            num, den = struct.unpack(self.e + ("II" if typ == 5 else "ii"), raw[:8])
            return num / den if den else None
        fmt = {3: "H", 4: "I", 9: "i", 11: "f", 12: "d"}.get(typ)
        if fmt is None:
            return None
        (value,) = struct.unpack(self.e + fmt, raw[: struct.calcsize(fmt)])
        return float(value)

    def rationals(self, entry: tuple[int, int, bytes] | None) -> list[float]:
        """All values of a RATIONAL array (e.g. GPS degrees, minutes, seconds)."""
        if entry is None or entry[0] != 5:
            return []
        _, n, raw = entry
        out = []
        for i in range(n):
            num, den = struct.unpack(self.e + "II", raw[8 * i : 8 * i + 8])
            out.append(num / den if den else 0.0)
        return out

    @staticmethod
    def text(entry: tuple[int, int, bytes] | None) -> str | None:
        if entry is None or entry[0] != 2:
            return None
        return entry[2].split(b"\0", 1)[0].decode("ascii", "replace").strip() or None


def _first(values: list[int]) -> int | None:
    return values[0] if values else None


def _gps(t: _Tiff, ifd0: dict[int, tuple[int, int, bytes]]) -> tuple[float | None, ...]:
    if TAG_GPS_IFD not in ifd0:
        return None, None, None
    gps = t.ifd(t.ints(ifd0[TAG_GPS_IFD])[0])

    def degrees(value_tag: int, ref_tag: int, negative: str) -> float | None:
        dms = t.rationals(gps.get(value_tag))
        if len(dms) != 3:
            return None
        value = dms[0] + dms[1] / 60 + dms[2] / 3600
        return -value if (t.text(gps.get(ref_tag)) or "").upper() == negative else value

    altitude = t.rational(gps.get(6))
    if altitude is not None and _first(t.ints(gps.get(5))) == 1:  # below sea level
        altitude = -altitude
    return degrees(2, 1, "S"), degrees(4, 3, "W"), altitude


def _parse(t: _Tiff) -> ExifInfo:
    ifd0 = t.ifd(t.ifd0)
    exif = t.ifd(t.ints(ifd0[TAG_EXIF_IFD])[0]) if TAG_EXIF_IFD in ifd0 else {}
    gps_lat, gps_lon, gps_alt = _gps(t, ifd0)
    width = _first(t.ints(exif.get(TAG_PIXEL_X)))
    height = _first(t.ints(exif.get(TAG_PIXEL_Y)))
    # DNG: the full-resolution image lives in a SubIFD with NewSubfileType 0
    for offset in t.ints(ifd0.get(TAG_SUB_IFDS)):
        sub = t.ifd(offset)
        if _first(t.ints(sub.get(TAG_NEW_SUBFILE_TYPE))) == 0:
            width = _first(t.ints(sub.get(TAG_IMAGE_WIDTH))) or width
            height = _first(t.ints(sub.get(TAG_IMAGE_LENGTH))) or height
            break
    if width is None and _first(t.ints(ifd0.get(TAG_NEW_SUBFILE_TYPE))) in (None, 0):
        width = _first(t.ints(ifd0.get(TAG_IMAGE_WIDTH)))
        height = _first(t.ints(ifd0.get(TAG_IMAGE_LENGTH)))
    return ExifInfo(
        make=t.text(ifd0.get(TAG_MAKE)),
        model=t.text(ifd0.get(TAG_MODEL)),
        width_px=width,
        height_px=height,
        exposure_s=t.rational(exif.get(TAG_EXPOSURE_TIME)),
        iso=_first(t.ints(exif.get(TAG_ISO))),
        focal_mm=t.rational(exif.get(TAG_FOCAL_LENGTH)),
        focal_35mm=_first(t.ints(exif.get(TAG_FOCAL_35MM))),
        datetime_original=t.text(exif.get(TAG_DATETIME_ORIGINAL)),
        gps_lat=gps_lat,
        gps_lon=gps_lon,
        gps_alt_m=gps_alt,
    )


def _jpeg_tiff(data: bytes) -> bytes:
    pos = 2
    while pos + 4 <= len(data):
        if data[pos] != 0xFF:
            break
        marker = data[pos + 1]
        if marker in (0xD9, 0xDA):  # end of image / start of scan
            break
        (length,) = struct.unpack(">H", data[pos + 2 : pos + 4])
        segment = data[pos + 4 : pos + 2 + length]
        if marker == 0xE1 and segment.startswith(b"Exif\0\0"):
            return segment[6:]
        pos += 2 + length
    raise ExifError("JPEG has no EXIF block")


def read_exif(data: bytes, read: Read | None = None, size: int | None = None) -> ExifInfo:
    """Parse EXIF from JPEG bytes, or from a TIFF/DNG given its head bytes.

    For large TIFF/DNG files pass ``read(offset, n)`` and ``size`` so only the
    needed parts are read from disk.
    """
    if data[:2] == b"\xff\xd8":
        tiff = _jpeg_tiff(data)
        return _parse(_Tiff(lambda o, n: tiff[o : o + n], len(tiff)))
    if data[:2] in (b"II", b"MM"):
        if read is None:
            return _parse(_Tiff(lambda o, n: data[o : o + n], len(data)))
        return _parse(_Tiff(read, size if size is not None else len(data)))
    raise ExifError("not a JPEG or TIFF/DNG file")
