# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Extract simple key/value pairs from an XMP packet (DJI drone-dji, xmp, tiff)."""

from __future__ import annotations

import re

_PACKET = re.compile(rb"<x:xmpmeta.*?</x:xmpmeta>", re.S)
_ATTR = re.compile(r'\b([A-Za-z][\w.-]*):([A-Za-z]\w*)="([^"]*)"')
_ELEM = re.compile(r"<([A-Za-z][\w.-]*):([A-Za-z]\w*)>([^<]*)</\1:\2>")
_PREFIXES = {"drone-dji", "xmp", "tiff", "exif", "crs", "dc"}


def read_xmp(data: bytes) -> dict[str, str]:
    """Local names -> values for the first XMP packet in ``data`` (first match wins)."""
    match = _PACKET.search(data)
    if match is None:
        return {}
    text = match.group(0).decode("utf-8", "replace")
    out: dict[str, str] = {}
    for pattern in (_ATTR, _ELEM):
        for prefix, name, value in pattern.findall(text):
            if prefix in _PREFIXES and name not in out:
                out[name] = value.strip()
    return out
