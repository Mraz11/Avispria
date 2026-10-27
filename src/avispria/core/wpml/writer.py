# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Write a planned mission into the user's DJI Fly dummy KMZ.

Only waypoint placemarks, their actions, speeds and the update time change; the
namespace, aircraft enum, safety actions and every unknown field are kept as
DJI Fly wrote them. Placemarks are cloned from the dummy's first waypoint.
"""

from __future__ import annotations

import copy
import math

from lxml import etree

from avispria.core.mission import Mission, Waypoint
from avispria.core.wpml.kmz import KmzEntry, parse_xml, serialize_xml, write_entries
from avispria.core.wpml.reader import KML_NS
from avispria.core.wpml.template import REQUIRED_HEIGHT_MODE, DummyTemplate

TURN_STOP = "toPointAndStopWithContinuityCurvature"  # observed in DJI Fly dummies
TURN_PASS = "toPointAndPassWithContinuityCurvature"  # observed in DJI Fly dummies

GROUP_GIMBAL = 1  # DJI Fly: gimbalRotate at the first waypoint
GROUP_EVENLY = 2  # DJI Fly: gimbalEvenlyRotate on every segment (id reused)
GROUP_PHOTO = 3

_ROTATE_DEFAULTS = (
    ("gimbalHeadingYawBase", "aircraft"),
    ("gimbalRotateMode", "absoluteAngle"),
    ("gimbalPitchRotateEnable", "1"),
    ("gimbalPitchRotateAngle", "0"),
    ("gimbalRollRotateEnable", "0"),
    ("gimbalRollRotateAngle", "0"),
    ("gimbalYawRotateEnable", "0"),
    ("gimbalYawRotateAngle", "0"),
    ("gimbalRotateTimeEnable", "0"),
    ("gimbalRotateTime", "0"),
    ("payloadPositionIndex", "0"),
)
_EVENLY_DEFAULTS = (
    ("gimbalPitchRotateAngle", "0"),
    ("gimbalRollRotateAngle", "0"),
    ("payloadPositionIndex", "0"),
)
_PHOTO_DEFAULTS = (("payloadPositionIndex", "0"),)


def _num(value: float) -> str:
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


class _Builder:
    def __init__(self, ns: str) -> None:
        self.ns = ns
        self.w = f"{{{ns}}}"
        self.k = f"{{{KML_NS}}}"
        self.next_action_id = 1

    def el(self, tag: str, text: str | None = None) -> etree._Element:
        node = etree.Element(self.w + tag)
        node.text = text
        return node

    def set(self, node: etree._Element, path: str, text: str) -> None:
        target = node.find("/".join(self.w + p for p in path.split("/")))
        if target is not None:
            target.text = text

    def params(self, defaults: tuple[tuple[str, str], ...], **overrides: str) -> etree._Element:
        node = self.el("actionActuatorFuncParam")
        for name, value in defaults:
            node.append(self.el(name, overrides.get(name, value)))
        return node

    def group(
        self, group_id: int, start: int, end: int, func: str, params: etree._Element
    ) -> etree._Element:
        g = self.el("actionGroup")
        for tag, text in (
            ("actionGroupId", str(group_id)),
            ("actionGroupStartIndex", str(start)),
            ("actionGroupEndIndex", str(end)),
            ("actionGroupMode", "parallel"),
        ):
            g.append(self.el(tag, text))
        trigger = self.el("actionTrigger")
        trigger.append(self.el("actionTriggerType", "reachPoint"))
        g.append(trigger)
        action = self.el("action")
        action.append(self.el("actionId", str(self.next_action_id)))
        action.append(self.el("actionActuatorFunc", func))
        action.append(params)
        g.append(action)
        self.next_action_id += 1
        return g


def _check(mission: Mission) -> None:
    wps = mission.waypoints
    if len(wps) < 2:
        raise ValueError("a DJI Fly mission needs at least two waypoints")
    for i, w in enumerate(wps):
        values = (w.lon, w.lat, w.height_m, w.speed_ms, w.gimbal_pitch_deg)
        if not all(math.isfinite(v) for v in values):
            raise ValueError(f"waypoint {i} has a non-finite value")
        if not (-180 <= w.lon <= 180 and -90 <= w.lat <= 90):
            raise ValueError(f"waypoint {i} has invalid coordinates")
        if w.speed_ms <= 0:
            raise ValueError(f"waypoint {i} has a non-positive speed")
        if not -90 <= w.gimbal_pitch_deg <= 0:
            raise ValueError(f"waypoint {i} gimbal pitch out of range")


def _placemark(
    b: _Builder,
    proto: etree._Element,
    i: int,
    wp: Waypoint,
    n: int,
    straight: bool,
    photo_params: bytes | None,
) -> etree._Element:
    pm = copy.deepcopy(proto)
    for group in pm.findall(b.w + "actionGroup"):
        pm.remove(group)
    coords = pm.find(f"{b.k}Point/{b.k}coordinates")
    if coords is None:
        raise ValueError("dummy placemark has no coordinates element")
    coords.text = f"\n            {wp.lon:.13f},{wp.lat:.13f}\n          "
    ends = i in (0, n - 1)
    b.set(pm, "index", str(i))
    b.set(pm, "executeHeight", _num(wp.height_m))
    b.set(pm, "waypointSpeed", _num(wp.speed_ms))
    b.set(pm, "waypointHeadingParam/waypointHeadingAngleEnable", "1" if ends else "0")
    b.set(pm, "waypointTurnParam/waypointTurnMode", TURN_STOP if ends or wp.stop else TURN_PASS)
    b.set(pm, "useStraightLine", "1" if straight else "0")
    b.set(pm, "waypointGimbalHeadingParam/waypointGimbalPitchAngle", _num(wp.gimbal_pitch_deg))

    pitch = _num(wp.gimbal_pitch_deg)
    groups = []
    if i == 0:
        params = b.params(_ROTATE_DEFAULTS, gimbalPitchRotateAngle=pitch)
        groups.append(b.group(GROUP_GIMBAL, 0, 0, "gimbalRotate", params))
    if i < n - 1:
        params = b.params(_EVENLY_DEFAULTS, gimbalPitchRotateAngle=pitch)
        groups.append(b.group(GROUP_EVENLY, i, i + 1, "gimbalEvenlyRotate", params))
    if wp.take_photo:
        params = etree.fromstring(photo_params) if photo_params else b.params(_PHOTO_DEFAULTS)
        groups.append(b.group(GROUP_PHOTO, i, i, "takePhoto", params))
    anchor = pm.find(b.w + "waypointGimbalHeadingParam")
    for g in groups:
        if anchor is not None:
            anchor.addprevious(g)
        else:
            pm.append(g)
    return pm


def _update_config(b: _Builder, root: etree._Element, speed: str) -> None:
    cfg = root.find(f"{b.k}Document/{b.w}missionConfig")
    if cfg is not None:
        b.set(cfg, "globalTransitionalSpeed", speed)


def write_kmz(
    template: DummyTemplate, mission: Mission, *, now_ms: int, straight_lines: bool = True
) -> bytes:
    """Return KMZ bytes for ``mission`` built on the user's DJI Fly dummy."""
    _check(mission)
    b = _Builder(template.namespace)
    speed = _num(mission.speed_ms)

    w_root = parse_xml(template.entry(template.waylines_name).data, "waylines.wpml")
    folder = w_root.find(f"{b.k}Document/{b.k}Folder")
    if folder is None:
        raise ValueError("dummy waylines.wpml has no Folder")
    placemarks = folder.findall(b.k + "Placemark")
    proto = copy.deepcopy(placemarks[0])
    for pm in placemarks:
        folder.remove(pm)
    n = len(mission.waypoints)
    for i, wp in enumerate(mission.waypoints):
        folder.append(_placemark(b, proto, i, wp, n, straight_lines, template.photo_params_xml))
    b.set(folder, "executeHeightMode", REQUIRED_HEIGHT_MODE)
    b.set(folder, "autoFlightSpeed", speed)
    _update_config(b, w_root, speed)

    t_root = parse_xml(template.entry(template.template_name).data, "template.kml")
    doc = t_root.find(b.k + "Document")
    if doc is not None:
        b.set(doc, "updateTime", str(now_ms))
    _update_config(b, t_root, speed)

    replaced = {
        template.waylines_name: serialize_xml(w_root),
        template.template_name: serialize_xml(t_root),
    }
    return write_entries(
        [KmzEntry(e.name, replaced.get(e.name, e.data), e.date_time) for e in template.entries]
    )
