# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read a DJI WPML KMZ into plain data (used by the linter, sheets and tests)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from lxml import etree

from avispria.core.wpml.kmz import (
    TEMPLATE_SUFFIX,
    WAYLINES_SUFFIX,
    KmzError,
    find_entry,
    parse_xml,
    read_entries,
)

KML_NS = "http://www.opengis.net/kml/2.2"


@dataclass(frozen=True)
class KmzAction:
    group_id: int
    start: int
    end: int
    trigger: str
    action_id: int
    func: str
    params: Mapping[str, str]


@dataclass(frozen=True)
class KmzWaypoint:
    index: int
    lon: float
    lat: float
    height_m: float
    speed_ms: float
    turn_mode: str
    straight_line: bool
    gimbal_pitch_deg: float | None
    actions: tuple[KmzAction, ...]


@dataclass(frozen=True)
class KmzMission:
    namespace: str
    template_namespace: str
    drone_enum: int
    drone_sub_enum: int
    height_mode: str
    auto_speed_ms: float
    transit_speed_ms: float
    finish_action: str
    rc_lost_action: str
    waypoints: tuple[KmzWaypoint, ...]


def wpml_namespace(root: etree._Element, label: str) -> str:
    ns = root.nsmap.get("wpml")
    if not ns:
        raise KmzError(f"{label}: no wpml namespace declared")
    return ns


class _Doc:
    def __init__(self, root: etree._Element, ns: str, label: str) -> None:
        self.root, self.ns, self.label = root, ns, label

    def find(self, node: etree._Element, path: str) -> etree._Element | None:
        return node.find(path.replace("wpml:", f"{{{self.ns}}}").replace("kml:", f"{{{KML_NS}}}"))

    def text(self, node: etree._Element, path: str, default: str | None = None) -> str:
        el = self.find(node, path)
        if el is None or el.text is None:
            if default is not None:
                return default
            raise KmzError(f"{self.label}: missing {path}")
        return el.text.strip()

    def number(self, node: etree._Element, path: str, default: str | None = None) -> float:
        raw = self.text(node, path, default)
        try:
            return float(raw)
        except ValueError as exc:
            raise KmzError(f"{self.label}: {path} is not a number ({raw!r})") from exc

    def integer(self, node: etree._Element, path: str) -> int:
        raw = self.text(node, path)
        try:
            return int(raw)
        except ValueError as exc:
            raise KmzError(f"{self.label}: {path} is not an integer ({raw!r})") from exc


def _actions(doc: _Doc, pm: etree._Element) -> tuple[KmzAction, ...]:
    out: list[KmzAction] = []
    for group in pm.findall(f"{{{doc.ns}}}actionGroup"):
        trigger = doc.text(group, "wpml:actionTrigger/wpml:actionTriggerType", "")
        for action in group.findall(f"{{{doc.ns}}}action"):
            params_el = doc.find(action, "wpml:actionActuatorFuncParam")
            params = {}
            if params_el is not None:
                params = {etree.QName(c).localname: (c.text or "").strip() for c in params_el}
            out.append(
                KmzAction(
                    group_id=doc.integer(group, "wpml:actionGroupId"),
                    start=doc.integer(group, "wpml:actionGroupStartIndex"),
                    end=doc.integer(group, "wpml:actionGroupEndIndex"),
                    trigger=trigger,
                    action_id=doc.integer(action, "wpml:actionId"),
                    func=doc.text(action, "wpml:actionActuatorFunc"),
                    params=params,
                )
            )
    return tuple(out)


def _waypoint(doc: _Doc, pm: etree._Element) -> KmzWaypoint:
    coords = doc.text(pm, "kml:Point/kml:coordinates").split(",")
    if len(coords) < 2:
        raise KmzError(f"{doc.label}: bad coordinates {coords!r}")
    try:
        lon, lat = float(coords[0]), float(coords[1])
    except ValueError as exc:
        raise KmzError(f"{doc.label}: bad coordinates {coords!r}") from exc
    pitch_el = doc.find(pm, "wpml:waypointGimbalHeadingParam/wpml:waypointGimbalPitchAngle")
    return KmzWaypoint(
        index=doc.integer(pm, "wpml:index"),
        lon=lon,
        lat=lat,
        height_m=doc.number(pm, "wpml:executeHeight"),
        speed_ms=doc.number(pm, "wpml:waypointSpeed"),
        turn_mode=doc.text(pm, "wpml:waypointTurnParam/wpml:waypointTurnMode", ""),
        straight_line=doc.text(pm, "wpml:useStraightLine", "0") == "1",
        gimbal_pitch_deg=None
        if pitch_el is None or pitch_el.text is None
        else float(pitch_el.text),
        actions=_actions(doc, pm),
    )


def read_mission(data: bytes) -> KmzMission:
    """Parse a KMZ mission. Raises KmzError on anything malformed."""
    entries = read_entries(data)
    t_root = parse_xml(find_entry(entries, TEMPLATE_SUFFIX).data, TEMPLATE_SUFFIX)
    w_root = parse_xml(find_entry(entries, WAYLINES_SUFFIX).data, WAYLINES_SUFFIX)
    doc = _Doc(w_root, wpml_namespace(w_root, WAYLINES_SUFFIX), WAYLINES_SUFFIX)
    document = doc.find(w_root, "kml:Document")
    if document is None:
        raise KmzError(f"{WAYLINES_SUFFIX}: missing Document")
    folders = document.findall(f"{{{KML_NS}}}Folder")
    if len(folders) != 1:
        raise KmzError(f"{WAYLINES_SUFFIX}: expected one Folder, found {len(folders)}")
    folder = folders[0]
    cfg = "kml:Document/wpml:missionConfig/"
    return KmzMission(
        namespace=doc.ns,
        template_namespace=wpml_namespace(t_root, TEMPLATE_SUFFIX),
        drone_enum=doc.integer(w_root, cfg + "wpml:droneInfo/wpml:droneEnumValue"),
        drone_sub_enum=doc.integer(w_root, cfg + "wpml:droneInfo/wpml:droneSubEnumValue"),
        height_mode=doc.text(folder, "wpml:executeHeightMode"),
        auto_speed_ms=doc.number(folder, "wpml:autoFlightSpeed"),
        transit_speed_ms=doc.number(w_root, cfg + "wpml:globalTransitionalSpeed"),
        finish_action=doc.text(w_root, cfg + "wpml:finishAction", ""),
        rc_lost_action=doc.text(w_root, cfg + "wpml:executeRCLostAction", ""),
        waypoints=tuple(_waypoint(doc, pm) for pm in folder.findall(f"{{{KML_NS}}}Placemark")),
    )
