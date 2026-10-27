# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Safe KMZ (zip) and XML handling: size limits, no path tricks, no entity expansion."""

from __future__ import annotations

import io
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass

from lxml import etree

MAX_ENTRIES = 32
MAX_ENTRY_BYTES = 5 * 1024 * 1024
MAX_TOTAL_BYTES = 20 * 1024 * 1024
TEMPLATE_SUFFIX = "template.kml"
WAYLINES_SUFFIX = "waylines.wpml"


class KmzError(ValueError):
    """The KMZ file is unreadable, unsafe or not a DJI waypoint mission."""


@dataclass(frozen=True)
class KmzEntry:
    name: str
    data: bytes
    date_time: tuple[int, int, int, int, int, int]


def _check_name(name: str) -> None:
    parts = name.replace("\\", "/").split("/")
    if name.startswith(("/", "\\")) or ".." in parts or ":" in name or "\\" in name:
        raise KmzError(f"unsafe entry name in KMZ: {name!r}")


def read_entries(data: bytes) -> tuple[KmzEntry, ...]:
    """All entries of a KMZ, in archive order, after safety checks."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise KmzError("not a valid KMZ (zip) file") from exc
    infos = archive.infolist()
    if len(infos) > MAX_ENTRIES:
        raise KmzError(f"KMZ has too many entries ({len(infos)})")
    entries: list[KmzEntry] = []
    total = 0
    for info in infos:
        _check_name(info.filename)
        if info.is_dir():
            continue
        if info.file_size > MAX_ENTRY_BYTES:
            raise KmzError(f"entry {info.filename!r} is too large ({info.file_size} bytes)")
        with archive.open(info) as handle:
            content = handle.read(MAX_ENTRY_BYTES + 1)
        if len(content) > MAX_ENTRY_BYTES:
            raise KmzError(f"entry {info.filename!r} is too large")
        total += len(content)
        if total > MAX_TOTAL_BYTES:
            raise KmzError("KMZ content is too large")
        entries.append(KmzEntry(info.filename, content, info.date_time))
    return tuple(entries)


def find_entry(entries: Sequence[KmzEntry], suffix: str) -> KmzEntry:
    """The single entry whose name ends with ``suffix`` (case-insensitive)."""
    matches = [e for e in entries if e.name.lower().endswith(suffix)]
    if len(matches) != 1:
        raise KmzError(f"KMZ must contain exactly one {suffix} (found {len(matches)})")
    return matches[0]


def parse_xml(data: bytes, label: str) -> etree._Element:
    """Parse XML without DTDs, entities or network access."""
    if b"<!DOCTYPE" in data.upper():
        raise KmzError(f"{label}: DOCTYPE declarations are not allowed")
    parser = etree.XMLParser(
        resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False
    )
    try:
        return etree.fromstring(data, parser)
    except etree.XMLSyntaxError as exc:
        raise KmzError(f"{label}: malformed XML ({exc})") from exc


def serialize_xml(root: etree._Element) -> bytes:
    """Serialize like DJI Fly: double-quoted declaration, two-space indentation."""
    for node in root.iter():
        if node.text is not None and not node.text.strip():
            node.text = None
        if node.tail is not None and not node.tail.strip():
            node.tail = None
    etree.indent(root, space="  ")
    body = etree.tostring(root, encoding="UTF-8", xml_declaration=False)
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + body + b"\n"


def write_entries(entries: Sequence[KmzEntry]) -> bytes:
    """Deterministic deflated zip with the given names and timestamps."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        for entry in entries:
            info = zipfile.ZipInfo(entry.name, date_time=entry.date_time)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, entry.data)
    return buf.getvalue()
