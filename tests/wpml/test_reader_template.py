# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import io
import zipfile

import pytest

from avispria.core.wpml.kmz import KmzError, read_entries
from avispria.core.wpml.reader import read_mission
from avispria.core.wpml.template import DummyTemplate


def _zip(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in entries.items():
            z.writestr(name, data)
    return buf.getvalue()


def test_reads_real_lito_x1_dummy(dummy_bytes: bytes) -> None:
    m = read_mission(dummy_bytes)
    assert m.namespace == "http://www.uav.com/wpmz/1.0.2"
    assert (m.drone_enum, m.drone_sub_enum) == (68, 0)
    assert m.height_mode == "relativeToStartPoint"
    assert [w.index for w in m.waypoints] == [0, 1, 2, 3, 4]
    assert all(w.height_m == 50.0 for w in m.waypoints)
    assert m.waypoints[0].turn_mode == "toPointAndStopWithContinuityCurvature"
    assert m.waypoints[1].turn_mode == "toPointAndPassWithContinuityCurvature"
    assert m.waypoints[0].lon == pytest.approx(-0.0015)
    funcs = [a.func for w in m.waypoints for a in w.actions]
    assert funcs.count("gimbalRotate") == 1
    assert funcs.count("gimbalEvenlyRotate") == 4


def test_template_extracts_bootstrap_facts(dummy_bytes: bytes) -> None:
    t = DummyTemplate.from_kmz(dummy_bytes)
    assert t.namespace == "http://www.uav.com/wpmz/1.0.2"
    assert t.drone_enum == 68
    assert t.entry_names == ("wpmz/template.kml", "wpmz/waylines.wpml")
    assert not t.has_photo_action


def test_missing_waylines_is_rejected(dummy_bytes: bytes) -> None:
    z = zipfile.ZipFile(io.BytesIO(dummy_bytes))
    only_template = _zip({"wpmz/template.kml": z.read("wpmz/template.kml")})
    with pytest.raises(KmzError, match=r"waylines\.wpml"):
        DummyTemplate.from_kmz(only_template)


def test_not_a_zip_is_rejected() -> None:
    with pytest.raises(KmzError):
        read_entries(b"definitely not a zip")


def test_oversized_entry_is_rejected() -> None:
    bomb = _zip({"wpmz/waylines.wpml": b" " * (6 * 1024 * 1024)})
    with pytest.raises(KmzError, match="too large"):
        read_entries(bomb)


def test_path_traversal_entry_is_rejected() -> None:
    with pytest.raises(KmzError, match="unsafe"):
        read_entries(_zip({"../evil.kml": b"<kml/>"}))


def test_xml_entities_are_not_expanded(dummy_bytes: bytes) -> None:
    z = zipfile.ZipFile(io.BytesIO(dummy_bytes))
    waylines = z.read("wpmz/waylines.wpml").decode()
    evil = waylines.replace(
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<?xml version="1.0" encoding="UTF-8"?><!DOCTYPE kml [<!ENTITY x SYSTEM "file:///etc/passwd">]>',
    )
    data = _zip(
        {"wpmz/template.kml": z.read("wpmz/template.kml"), "wpmz/waylines.wpml": evil.encode()}
    )
    with pytest.raises(KmzError, match="DOCTYPE"):
        read_mission(data)
