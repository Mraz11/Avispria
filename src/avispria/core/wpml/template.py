# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The user's own DJI Fly dummy mission, used as the template for every export.

Everything DJI Fly expects (namespace, aircraft enum, field set and order,
safety settings) is copied from this file rather than guessed.
"""

from __future__ import annotations

from dataclasses import dataclass

from lxml import etree

from avispria.core.wpml.kmz import (
    TEMPLATE_SUFFIX,
    WAYLINES_SUFFIX,
    KmzEntry,
    KmzError,
    find_entry,
    parse_xml,
    read_entries,
)
from avispria.core.wpml.reader import KML_NS, wpml_namespace

REQUIRED_HEIGHT_MODE = "relativeToStartPoint"


@dataclass(frozen=True, eq=False)
class DummyTemplate:
    entries: tuple[KmzEntry, ...]
    template_name: str
    waylines_name: str
    namespace: str
    drone_enum: int
    drone_sub_enum: int
    placemark_count: int
    photo_params_xml: bytes | None  # takePhoto parameters if the dummy has a photo action

    @property
    def entry_names(self) -> tuple[str, ...]:
        return tuple(e.name for e in self.entries)

    @property
    def has_photo_action(self) -> bool:
        return self.photo_params_xml is not None

    @classmethod
    def from_kmz(cls, data: bytes) -> DummyTemplate:
        entries = read_entries(data)
        t_entry = find_entry(entries, TEMPLATE_SUFFIX)
        w_entry = find_entry(entries, WAYLINES_SUFFIX)
        t_root = parse_xml(t_entry.data, TEMPLATE_SUFFIX)
        w_root = parse_xml(w_entry.data, WAYLINES_SUFFIX)
        ns = wpml_namespace(w_root, WAYLINES_SUFFIX)
        if wpml_namespace(t_root, TEMPLATE_SUFFIX) != ns:
            raise KmzError("template.kml and waylines.wpml use different wpml namespaces")
        w = f"{{{ns}}}"
        k = f"{{{KML_NS}}}"
        folders = w_root.findall(f"{k}Document/{k}Folder")
        if len(folders) != 1:
            raise KmzError("dummy waylines.wpml must contain exactly one Folder")
        placemarks = folders[0].findall(f"{k}Placemark")
        if not placemarks:
            raise KmzError("dummy mission has no waypoints; add at least two in DJI Fly")
        mode = folders[0].findtext(f"{w}executeHeightMode", default="").strip()
        if mode != REQUIRED_HEIGHT_MODE:
            raise KmzError(
                f"dummy mission uses height mode {mode!r}; expected {REQUIRED_HEIGHT_MODE!r}"
            )
        info = w_root.find(f"{k}Document/{w}missionConfig/{w}droneInfo")
        if info is None:
            raise KmzError("dummy mission has no droneInfo")
        try:
            enum = int(info.findtext(f"{w}droneEnumValue", default=""))
            sub = int(info.findtext(f"{w}droneSubEnumValue", default="0"))
        except ValueError as exc:
            raise KmzError("droneEnumValue is not an integer") from exc
        photo = None
        for action in w_root.iter(f"{w}action"):
            if action.findtext(f"{w}actionActuatorFunc", default="").strip() == "takePhoto":
                params = action.find(f"{w}actionActuatorFuncParam")
                if params is not None:
                    photo = etree.tostring(params)
                break
        return cls(
            entries=entries,
            template_name=t_entry.name,
            waylines_name=w_entry.name,
            namespace=ns,
            drone_enum=enum,
            drone_sub_enum=sub,
            placemark_count=len(placemarks),
            photo_params_xml=photo,
        )

    def entry(self, name: str) -> KmzEntry:
        return next(e for e in self.entries if e.name == name)
