# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Build tiny little-endian TIFF/JPEG files with chosen EXIF/XMP for tests."""

from __future__ import annotations

import struct

Entry = tuple[int, int, object]  # (tag, type, value); type 2=ASCII 3=SHORT 4=LONG 5=RATIONAL
IFD_POINTER = 0xFFFF  # pseudo-type: value is the name of another IFD


def _encode(typ: int, value: object) -> tuple[bytes, int]:
    if typ == 1:  # BYTE (raw bytes, e.g. XMP packet in tag 700)
        raw = bytes(value)  # type: ignore[call-overload]
        return raw, len(raw)
    if typ == 2:
        raw = str(value).encode() + b"\0"
        return raw, len(raw)
    vals = value if isinstance(value, list | tuple) else [value]
    if typ == 3:
        return b"".join(struct.pack("<H", int(v)) for v in vals), len(vals)
    if typ == 4:
        return b"".join(struct.pack("<I", int(v)) for v in vals), len(vals)
    if typ == 5:
        return b"".join(struct.pack("<II", n, d) for n, d in vals), len(vals)
    if typ == 12:
        return b"".join(struct.pack("<d", float(v)) for v in vals), len(vals)
    raise ValueError(typ)


def build_tiff(ifds: dict[str, list[Entry]], order: list[str]) -> bytes:
    """``order[0]`` is IFD0. Entries with type IFD_POINTER reference another IFD by name."""
    offsets: dict[str, int] = {}
    pos = 8
    for name in order:
        offsets[name] = pos
        pos += 2 + 12 * len(ifds[name]) + 4
    data_start = pos
    data_area = bytearray()
    blobs = bytearray()
    for name in order:
        entries = sorted(ifds[name], key=lambda e: e[0])
        blobs += struct.pack("<H", len(entries))
        for tag, typ, value in entries:
            if typ == IFD_POINTER:
                blobs += struct.pack("<HHII", tag, 4, 1, offsets[str(value)])
                continue
            raw, count = _encode(typ, value)
            if len(raw) <= 4:
                blobs += struct.pack("<HHI", tag, typ, count) + raw.ljust(4, b"\0")
            else:
                blobs += struct.pack("<HHII", tag, typ, count, data_start + len(data_area))
                data_area += raw + (b"\0" if len(raw) % 2 else b"")
        blobs += struct.pack("<I", 0)
    return b"II*\0" + struct.pack("<I", 8) + bytes(blobs) + bytes(data_area)


def dji_xmp(**values: str) -> bytes:
    attrs = " ".join(f'drone-dji:{k}="{v}"' for k, v in values.items())
    return (
        '<x:xmpmeta xmlns:x="adobe:ns:meta/">'
        '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
        f'<rdf:Description xmlns:drone-dji="http://www.dji.com/drone-dji/1.0/" '
        'xmlns:xmp="http://ns.adobe.com/xap/1.0/" '
        f'xmp:CreateDate="2026-10-24T12:04:56+06:00" {attrs}/>'
        "</rdf:RDF></x:xmpmeta>"
    ).encode()


def jpeg_with(tiff: bytes, xmp: bytes) -> bytes:
    exif_seg = b"Exif\0\0" + tiff
    xmp_seg = b"http://ns.adobe.com/xap/1.0/\0" + xmp
    app1 = b"\xff\xe1" + struct.pack(">H", len(exif_seg) + 2) + exif_seg
    app1x = b"\xff\xe1" + struct.pack(">H", len(xmp_seg) + 2) + xmp_seg
    return b"\xff\xd8" + app1 + app1x + b"\xff\xd9"
