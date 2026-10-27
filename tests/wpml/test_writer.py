# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import io
import zipfile

import pytest

from avispria.core.mission import Mission
from avispria.core.wpml.reader import read_mission
from avispria.core.wpml.template import DummyTemplate
from avispria.core.wpml.writer import write_kmz

NOW = 1_793_200_000_000


def test_round_trip_preserves_mission(dummy_bytes: bytes, interval_mission: Mission) -> None:
    out = write_kmz(DummyTemplate.from_kmz(dummy_bytes), interval_mission, now_ms=NOW)
    back = read_mission(out)
    assert back.namespace == "http://www.uav.com/wpmz/1.0.2"
    assert (back.drone_enum, back.drone_sub_enum) == (68, 0)
    assert back.height_mode == "relativeToStartPoint"
    assert len(back.waypoints) == len(interval_mission.waypoints)
    for got, want in zip(back.waypoints, interval_mission.waypoints, strict=True):
        assert got.lon == pytest.approx(want.lon, abs=1e-9)
        assert got.lat == pytest.approx(want.lat, abs=1e-9)
        assert got.height_m == pytest.approx(want.height_m, abs=0.05)
        assert got.speed_ms == pytest.approx(want.speed_ms, abs=0.05)
        assert got.gimbal_pitch_deg == pytest.approx(-90.0)
        assert got.straight_line
        stop = got.turn_mode == "toPointAndStopWithContinuityCurvature"
        assert stop == (want.stop or got.index in (0, len(back.waypoints) - 1))
    assert back.auto_speed_ms == pytest.approx(interval_mission.speed_ms, abs=0.05)


def test_gimbal_is_pointed_down_on_every_segment(
    dummy_bytes: bytes, interval_mission: Mission
) -> None:
    back = read_mission(
        write_kmz(DummyTemplate.from_kmz(dummy_bytes), interval_mission, now_ms=NOW)
    )
    actions = [a for w in back.waypoints for a in w.actions]
    first = [a for a in actions if a.func == "gimbalRotate"]
    assert len(first) == 1 and first[0].params["gimbalPitchRotateAngle"] == "-90"
    evenly = [a for a in actions if a.func == "gimbalEvenlyRotate"]
    assert len(evenly) == len(back.waypoints) - 1
    assert all(a.params["gimbalPitchRotateAngle"] == "-90" for a in evenly)
    assert all(a.end == a.start + 1 for a in evenly)
    ids = [a.action_id for a in actions]
    assert ids == sorted(set(ids))  # unique and increasing, like DJI Fly writes them


def test_photo_mode_adds_one_photo_per_photo_waypoint(
    dummy_bytes: bytes, photo_mission: Mission
) -> None:
    back = read_mission(write_kmz(DummyTemplate.from_kmz(dummy_bytes), photo_mission, now_ms=NOW))
    photos = [w.index for w in back.waypoints for a in w.actions if a.func == "takePhoto"]
    expected = [i for i, w in enumerate(photo_mission.waypoints) if w.take_photo]
    assert photos == expected


def test_zip_layout_matches_dji_fly(dummy_bytes: bytes, interval_mission: Mission) -> None:
    out = write_kmz(DummyTemplate.from_kmz(dummy_bytes), interval_mission, now_ms=NOW)
    original = zipfile.ZipFile(io.BytesIO(dummy_bytes)).infolist()
    written = zipfile.ZipFile(io.BytesIO(out)).infolist()
    assert [i.filename for i in written] == [i.filename for i in original]
    assert [i.date_time for i in written] == [i.date_time for i in original]
    assert all(i.compress_type == zipfile.ZIP_DEFLATED for i in written)


def test_template_kml_only_gets_new_update_time(
    dummy_bytes: bytes, interval_mission: Mission
) -> None:
    out = write_kmz(DummyTemplate.from_kmz(dummy_bytes), interval_mission, now_ms=NOW)
    before = zipfile.ZipFile(io.BytesIO(dummy_bytes)).read("wpmz/template.kml").decode()
    after = zipfile.ZipFile(io.BytesIO(out)).read("wpmz/template.kml").decode()
    assert after.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert f"<wpml:updateTime>{NOW}</wpml:updateTime>" in after
    assert "<wpml:createTime>1793096017977</wpml:createTime>" in after
    assert before.count("droneEnumValue") == after.count("droneEnumValue")


def test_output_is_deterministic(dummy_bytes: bytes, interval_mission: Mission) -> None:
    t = DummyTemplate.from_kmz(dummy_bytes)
    assert write_kmz(t, interval_mission, now_ms=NOW) == write_kmz(t, interval_mission, now_ms=NOW)


def test_rejects_single_waypoint(dummy_bytes: bytes, interval_mission: Mission) -> None:
    from dataclasses import replace

    tiny = replace(interval_mission, waypoints=interval_mission.waypoints[:1])
    with pytest.raises(ValueError, match="at least two"):
        write_kmz(DummyTemplate.from_kmz(dummy_bytes), tiny, now_ms=NOW)
