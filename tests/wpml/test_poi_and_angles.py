# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Point-of-interest headings, per-waypoint camera angles and photos at waypoints.

The fixtures in tests/fixtures/dji_fly_poi are two REAL missions made in DJI Fly on a Lito X1
(their coordinates moved to Greenwich, nothing else changed): ``angles_6wp`` has camera tilts
of -90, -60, -30 and 0 degrees and photos at waypoints 2, 4 and 5; ``poi_5wp`` has five
waypoints facing one point of interest (Gimbal Tilt "POI 1" in the app), a photo at each.
"""

import re
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

from avispria.core.mission import Mission, PhotoMode, Takeoff, Waypoint
from avispria.core.wpml.lint import LintLimits, lint_kmz
from avispria.core.wpml.reader import read_mission
from avispria.core.wpml.template import DummyTemplate
from avispria.core.wpml.writer import write_kmz

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
ANGLES = (FIXTURES / "dji_fly_poi" / "angles_6wp.kmz").read_bytes()
POI = (FIXTURES / "dji_fly_poi" / "poi_5wp.kmz").read_bytes()
DUMMY = (FIXTURES / "dji_fly_dummy" / "lito_x1_5wp.kmz").read_bytes()
NOW = 1_793_200_000_000


def wp(i: int, pitch: float = -90.0, *, photo: bool = False, poi=None) -> Waypoint:  # type: ignore[no-untyped-def]
    return Waypoint(
        lon=-0.0015 + i * 0.0002,
        lat=51.4769,
        height_m=50.0,
        speed_ms=3.0,
        gimbal_pitch_deg=pitch,
        take_photo=photo,
        surface_clearance_m=None,
        height_above_ground_m=None,
        poi=poi,
    )


def mission(waypoints: list[Waypoint]) -> Mission:
    return Mission(
        "m",
        tuple(waypoints),
        Takeoff(-0.0015, 51.4769, None, "flat"),
        PhotoMode.WAYPOINT,
        None,
        3.0,
        60.0,
    )


def test_the_real_angles_mission_reads_the_way_the_phone_showed_it() -> None:
    m = read_mission(ANGLES)
    assert [w.heading_mode for w in m.waypoints] == ["towardPOI"] * 2 + ["followWayline"] * 4
    # DJI Fly keeps the tilt in actions, not in the waypoint's own field (which stays 0)
    assert [w.gimbal_pitch_deg for w in m.waypoints] == [None, None, -90.0, -60.0, -30.0, 0.0]
    photos = [w.index for w in m.waypoints if any(a.func == "takePhoto" for a in w.actions)]
    assert photos == [2, 4, 5]
    assert m.waypoints[0].poi is not None and m.waypoints[2].poi is None


def test_the_real_poi_mission_faces_one_point_and_stores_no_tilt() -> None:
    m = read_mission(POI)
    assert [w.heading_mode for w in m.waypoints] == ["towardPOI"] * 5
    assert len({w.poi for w in m.waypoints}) == 1  # one point of interest for all of them
    lon, lat, height = m.waypoints[0].poi  # type: ignore[misc]
    assert height == 50.0 and abs(lon) < 0.01 and 51.4 < lat < 51.5
    assert [w.gimbal_pitch_deg for w in m.waypoints] == [None] * 5  # the app aims the camera itself
    assert [[a.func for a in w.actions] for w in m.waypoints] == [["takePhoto"]] * 5
    assert [a.action_id for w in m.waypoints for a in w.actions] == [1, 2, 3, 4, 5]


def test_each_camera_angle_arrives_on_the_waypoint_it_is_meant_for() -> None:
    """The tilt of waypoint k is stored on waypoint k-1 (over the leg [k-1, k]).

    Writing waypoint i's tilt on its own leg [i, i+1] shifted every angle by one waypoint; it
    went unnoticed while all missions used a single angle.
    """
    pitches = [-90.0, -90.0, -60.0, -30.0, 0.0, 20.0]
    out = write_kmz(
        DummyTemplate.from_kmz(DUMMY),
        mission([wp(i, p) for i, p in enumerate(pitches)]),
        now_ms=NOW,
    )
    assert [w.gimbal_pitch_deg for w in read_mission(out).waypoints] == pitches


def test_camera_and_photo_actions_have_the_structure_dji_fly_writes() -> None:
    pitches = [-90.0, -90.0, -90.0, -60.0, -30.0, 0.0]
    photos = {2, 4, 5}
    out = write_kmz(
        DummyTemplate.from_kmz(DUMMY),
        mission([wp(i, p, photo=i in photos) for i, p in enumerate(pitches)]),
        now_ms=NOW,
    )
    ours, real = read_mission(out), read_mission(ANGLES)

    def shape(m, func):  # type: ignore[no-untyped-def]
        return [
            (w.index, a.start, a.end, a.trigger, a.params.get("gimbalPitchRotateAngle"))
            for w in m.waypoints
            for a in w.actions
            if a.func == func
        ]

    # the turns that DJI Fly recorded for waypoints 1 to 4 are exactly the ones we write there
    assert [s for s in shape(ours, "gimbalEvenlyRotate") if 1 <= s[0] <= 4] == shape(
        real, "gimbalEvenlyRotate"
    )
    assert shape(ours, "takePhoto") == [(i, i, i, "reachPoint", None) for i in sorted(photos)]
    assert shape(real, "takePhoto") == [(i, i, i, "reachPoint", None) for i in sorted(photos)]


def test_a_point_of_interest_is_written_the_way_dji_fly_writes_it() -> None:
    poi = (-0.0010, 51.4775, 50.0)
    waypoints = [wp(i, -45.0, photo=True, poi=poi) for i in range(4)]
    out = write_kmz(DummyTemplate.from_kmz(DUMMY), mission(waypoints), now_ms=NOW)
    text = zipfile.ZipFile(__import__("io").BytesIO(out)).read("wpmz/waylines.wpml").decode()
    assert text.count("<wpml:waypointHeadingMode>towardPOI</wpml:waypointHeadingMode>") == 4
    assert (
        "<wpml:waypointPoiPoint>51.477500,-0.001000,50.000000</wpml:waypointPoiPoint>" in text
    )  # lat,lon,height
    assert not re.search(r"followWayline", text.split("<Folder>")[1])
    back = read_mission(out)
    assert all(w.poi == pytest.approx(poi) for w in back.waypoints)
    assert [i for i in lint_kmz(out, LintLimits()) if i.level == "error"] == []


def test_a_mission_written_on_a_sample_that_has_points_of_interest_does_not_inherit_them() -> None:
    out = write_kmz(DummyTemplate.from_kmz(ANGLES), mission([wp(i) for i in range(4)]), now_ms=NOW)
    back = read_mission(out)
    assert {w.heading_mode for w in back.waypoints} == {"followWayline"}
    assert all(w.poi is None for w in back.waypoints)


@pytest.mark.parametrize(
    ("pitch", "ok"), [(40.0, True), (-90.0, True), (41.0, False), (-90.5, False)]
)
def test_the_camera_angles_are_the_lito_x1s_own_limits(pitch: float, ok: bool) -> None:
    waypoints = [wp(0), wp(1, pitch)]
    if ok:
        write_kmz(DummyTemplate.from_kmz(DUMMY), mission(waypoints), now_ms=NOW)
    else:
        with pytest.raises(ValueError, match="gimbal pitch out of range"):
            write_kmz(DummyTemplate.from_kmz(DUMMY), mission(waypoints), now_ms=NOW)


def test_the_survey_the_phone_already_opened_is_written_exactly_as_before() -> None:
    """A constant camera angle gives the same actions as before the off-by-one fix."""
    out = write_kmz(
        DummyTemplate.from_kmz(DUMMY), mission([wp(i, -90.0) for i in range(5)]), now_ms=NOW
    )
    back = read_mission(out)
    funcs = [(w.index, a.func, a.start, a.end) for w in back.waypoints for a in w.actions]
    assert funcs == [(0, "gimbalRotate", 0, 0), (0, "gimbalEvenlyRotate", 0, 1)] + [
        (i, "gimbalEvenlyRotate", i, i + 1) for i in range(1, 4)
    ]


@pytest.mark.parametrize(
    ("pitch", "flagged"), [(30.0, False), (-90.0, False), (45.0, True), (-95.0, True)]
)
def test_the_linter_uses_the_same_camera_limits(pitch: float, flagged: bool) -> None:
    import io

    waypoints = [wp(0), wp(1, -90.0), wp(2, -90.0)]
    out = write_kmz(DummyTemplate.from_kmz(DUMMY), mission(waypoints), now_ms=NOW)
    # a tilt the writer would refuse can still turn up in a file made elsewhere: edit it in
    with zipfile.ZipFile(io.BytesIO(out)) as z:
        parts = {n: z.read(n) for n in z.namelist()}
    text = (
        parts["wpmz/waylines.wpml"]
        .decode()
        .replace(
            "<wpml:gimbalPitchRotateAngle>-90</wpml:gimbalPitchRotateAngle>",
            f"<wpml:gimbalPitchRotateAngle>{pitch:g}</wpml:gimbalPitchRotateAngle>",
        )
    )
    parts["wpmz/waylines.wpml"] = text.encode()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        for name, data in parts.items():
            z.writestr(name, data)
    codes = {i.code for i in lint_kmz(buffer.getvalue(), LintLimits())}
    assert ("WPML013" in codes) == flagged


CUSTOM = (FIXTURES / "dji_fly_poi" / "custom_3wp.kmz").read_bytes()


def raw_headings(data: bytes) -> list[tuple[str, str, str]]:
    text = zipfile.ZipFile(__import__("io").BytesIO(data)).read("wpmz/waylines.wpml").decode()
    return re.findall(
        r"<wpml:waypointHeadingMode>(\w+)</wpml:waypointHeadingMode>\s*"
        r"<wpml:waypointHeadingAngle>(-?[\d.]+)</wpml:waypointHeadingAngle>.*?"
        r"<wpml:waypointHeadingAngleEnable>(\d)</wpml:waypointHeadingAngleEnable>",
        text,
        flags=re.S,
    )


def test_the_real_custom_mission_shows_how_dji_fly_stores_heading_hover_zoom_and_speed() -> None:
    m = read_mission(CUSTOM)
    # "Custom 90 / 180" is the mode smoothTransition plus the angle; the last one follows the course
    assert [(w.heading_mode, w.heading_angle_deg) for w in m.waypoints] == [
        ("smoothTransition", 90.0),
        ("smoothTransition", 180.0),
        ("followWayline", None),
    ]
    assert [w.hover_s for w in m.waypoints] == [3.0, None, None]
    assert [w.zoom_factor for w in m.waypoints] == [2.0, None, None]
    assert [w.speed_ms for w in m.waypoints] == [2.5, 1.0, 2.5]  # waypoint 2 has its own speed
    assert [w.gimbal_pitch_deg for w in m.waypoints] == [0.0, 0.0, 20.0]  # tilting up is possible
    # DJI Fly groups actions by kind: arrival actions share group 1, tilt turns are 2, zoom is 4
    assert [(a.group_id, a.func) for a in m.waypoints[0].actions] == [
        (1, "gimbalRotate"),
        (1, "hover"),
        (4, "zoom"),
        (2, "gimbalEvenlyRotate"),
    ]
    assert [(a.group_id, a.func) for a in m.waypoints[2].actions] == [(1, "takePhoto")]


def test_a_custom_heading_a_hover_and_a_photo_are_written_the_way_dji_fly_writes_them() -> None:
    waypoints = [
        replace(wp(0, 0.0), heading_deg=90.0, hover_s=3.0),
        replace(wp(1, 0.0), heading_deg=180.0, speed_ms=1.0),
        wp(2, 20.0, photo=True),
    ]
    out = write_kmz(DummyTemplate.from_kmz(DUMMY), mission(waypoints), now_ms=NOW)
    ours, real = read_mission(out), read_mission(CUSTOM)
    assert (
        raw_headings(out)
        == raw_headings(CUSTOM)
        == [
            ("smoothTransition", "90", "1"),
            ("smoothTransition", "180", "0"),
            ("followWayline", "0", "1"),
        ]
    )
    assert [(w.heading_angle_deg, w.hover_s, w.speed_ms) for w in ours.waypoints] == [
        (90.0, 3.0, 3.0),
        (180.0, None, 1.0),
        (None, None, 3.0),
    ]
    kinds = lambda m, i: [(a.group_id, a.func) for a in m.waypoints[i].actions if a.func != "zoom"]  # noqa: E731
    assert [kinds(ours, i) for i in range(3)] == [kinds(real, i) for i in range(3)]
    ids = [a.action_id for w in ours.waypoints for a in w.actions]
    assert ids == sorted(set(ids))  # unique and increasing in file order
    assert [i for i in lint_kmz(out, LintLimits()) if i.level == "error"] == []


def test_a_photo_at_a_waypoint_carries_the_same_parameters_as_dji_flys_own() -> None:
    out = write_kmz(DummyTemplate.from_kmz(DUMMY), mission([wp(0), wp(1, photo=True)]), now_ms=NOW)
    ours = [a for w in read_mission(out).waypoints for a in w.actions if a.func == "takePhoto"]
    real = [a for w in read_mission(POI).waypoints for a in w.actions if a.func == "takePhoto"]
    assert (
        dict(ours[0].params)
        == dict(real[0].params)
        == {
            "payloadPositionIndex": "0",
            "useGlobalPayloadLensIndex": "0",
        }
    )  # the first sample had no photo, so the default had been a guess


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"heading_deg": 181.0}, "heading must be between"),
        ({"heading_deg": -181.0}, "heading must be between"),
        ({"hover_s": -1.0}, "invalid hover time"),
        ({"hover_s": float("nan")}, "invalid hover time"),
        ({"heading_deg": 10.0, "poi": (0.0, 51.0, 10.0)}, "cannot both face a point"),
    ],
)
def test_headings_and_hovers_that_make_no_sense_are_refused(change: dict, message: str) -> None:  # type: ignore[type-arg]
    waypoints = [replace(wp(0), **change), wp(1)]
    with pytest.raises(ValueError, match=message):
        write_kmz(DummyTemplate.from_kmz(DUMMY), mission(waypoints), now_ms=NOW)
