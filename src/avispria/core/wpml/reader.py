# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read a DJI WPML KMZ into plain data (used by the linter, sheets and tests)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

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
    gimbal_pitch_deg: float | None  # the tilt this waypoint is reached with (see arrival_tilts)
    actions: tuple[KmzAction, ...]
    heading_mode: str = ""  # followWayline, towardPOI, ...
    poi: tuple[float, float, float] | None = None  # (lon, lat, height m) when facing a point
    heading_angle_deg: float | None = None  # a custom (fixed) heading, as typed in the app
    hover_s: float | None = None  # waiting time at the waypoint
    zoom_factor: float | None = None  # a zoom action (1-4x), read only


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


def arrival_tilts(waypoints: Sequence[KmzWaypoint]) -> list[float | None]:
    """The camera tilt (degrees, -90 = straight down) each waypoint is reached with.

    DJI Fly does not use the waypoint's own gimbal field (it stays 0). It stores the tilt of
    waypoint ``k`` as an action declared on waypoint ``k - 1`` that turns the camera evenly over
    the leg ``[k - 1, k]`` (``gimbalEvenlyRotate``), or as a ``gimbalRotate`` at waypoint ``k``
    itself (the first waypoint). A waypoint with no such action has no stored tilt: ``None``
    (for a waypoint facing a point of interest DJI Fly aims the camera by itself).
    """
    tilts: list[float | None] = [None] * len(waypoints)
    for w in waypoints:
        for a in w.actions:
            angle = a.params.get("gimbalPitchRotateAngle")
            if angle is None:
                continue
            sets_tilt = a.func == "gimbalEvenlyRotate" or (
                a.func == "gimbalRotate" and a.start == a.end
            )
            if sets_tilt and 0 <= a.end < len(tilts):
                tilts[a.end] = float(angle)
    return tilts


def _custom_heading(doc: _Doc, pm: etree._Element) -> float | None:
    """The angle of a custom heading (DJI Fly stores it as smoothTransition + an angle)."""
    mode = doc.text(pm, "wpml:waypointHeadingParam/wpml:waypointHeadingMode", "")
    if mode not in ("smoothTransition", "fixed"):
        return None
    return doc.number(pm, "wpml:waypointHeadingParam/wpml:waypointHeadingAngle", "0")


def _action_number(doc: _Doc, pm: etree._Element, func: str, param: str) -> float | None:
    for group in pm.findall(f"{{{doc.ns}}}actionGroup"):
        for action in group.findall(f"{{{doc.ns}}}action"):
            if doc.text(action, "wpml:actionActuatorFunc", "") == func:
                value = doc.text(action, f"wpml:actionActuatorFuncParam/wpml:{param}", "")
                try:
                    return float(value)
                except ValueError:
                    return None
    return None


def _zoom(doc: _Doc, pm: etree._Element) -> float | None:
    for group in pm.findall(f"{{{doc.ns}}}actionGroup"):
        for action in group.findall(f"{{{doc.ns}}}action"):
            if doc.text(action, "wpml:actionActuatorFunc", "") == "zoom":
                use = doc.text(action, "wpml:actionActuatorFuncParam/wpml:isUseFocalFactor", "0")
                if use == "1":
                    return _action_number(doc, pm, "zoom", "focalFactor")
    return None


def _poi(doc: _Doc, pm: etree._Element) -> tuple[float, float, float] | None:
    raw = doc.text(pm, "wpml:waypointHeadingParam/wpml:waypointPoiPoint", "")
    try:
        lat, lon, height = (float(v) for v in raw.split(","))
    except ValueError:
        return None
    return None if lat == 0.0 and lon == 0.0 else (lon, lat, height)


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
        heading_angle_deg=_custom_heading(doc, pm),
        hover_s=_action_number(doc, pm, "hover", "hoverTime"),
        zoom_factor=_zoom(doc, pm),
        heading_mode=doc.text(pm, "wpml:waypointHeadingParam/wpml:waypointHeadingMode", ""),
        poi=_poi(doc, pm)
        if doc.text(pm, "wpml:waypointHeadingParam/wpml:waypointHeadingMode", "") == "towardPOI"
        else None,
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
        waypoints=_with_tilts(
            tuple(_waypoint(doc, pm) for pm in folder.findall(f"{{{KML_NS}}}Placemark"))
        ),
    )


def _with_tilts(waypoints: tuple[KmzWaypoint, ...]) -> tuple[KmzWaypoint, ...]:
    tilts = arrival_tilts(waypoints)
    return tuple(replace(w, gimbal_pitch_deg=t) for w, t in zip(waypoints, tilts, strict=True))
