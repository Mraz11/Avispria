# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import io
import re
import zipfile

import pytest

from avispria.core.mission import Mission
from avispria.core.wpml.lint import LintLimits, lint_kmz
from avispria.core.wpml.template import DummyTemplate
from avispria.core.wpml.writer import write_kmz


def _mutate(kmz: bytes, name: str, fn) -> bytes:  # type: ignore[no-untyped-def]
    src = zipfile.ZipFile(io.BytesIO(kmz))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as out:
        for info in src.infolist():
            data = src.read(info.filename)
            if info.filename.endswith(name):
                data = fn(data.decode()).encode()
            out.writestr(info.filename, data)
    return buf.getvalue()


@pytest.fixture
def good(dummy_bytes: bytes, interval_mission: Mission) -> bytes:
    return write_kmz(DummyTemplate.from_kmz(dummy_bytes), interval_mission, now_ms=1)


def _codes(kmz: bytes, **limits: float) -> set[str]:
    return {i.code for i in lint_kmz(kmz, LintLimits(**limits))}  # type: ignore[arg-type]


def test_written_mission_is_clean(good: bytes) -> None:
    assert lint_kmz(good, LintLimits()) == []


def test_real_dji_fly_dummy_is_clean(dummy_bytes: bytes) -> None:
    assert [i for i in lint_kmz(dummy_bytes, LintLimits()) if i.level == "error"] == []


def test_garbage_is_reported_not_raised() -> None:
    assert _codes(b"nope") == {"WPML001"}


@pytest.mark.parametrize(
    ("name", "pattern", "replacement", "code"),
    [
        ("waylines.wpml", r"uav\.com/wpmz/1\.0\.2", "dji.com/wpmz/1.0.6", "WPML002"),
        ("waylines.wpml", "relativeToStartPoint", "WGS84", "WPML004"),
        ("waylines.wpml", r"<wpml:index>1</wpml:index>", "<wpml:index>7</wpml:index>", "WPML006"),
        ("waylines.wpml", r"-0\.00\d+,51", "-200.0,51", "WPML007"),
        ("waylines.wpml", r"<wpml:executeHeight>[^<]+<", "<wpml:executeHeight>nan<", "WPML008"),
        ("waylines.wpml", r"<wpml:waypointSpeed>[^<]+<", "<wpml:waypointSpeed>0<", "WPML009"),
        (
            "waylines.wpml",
            r"<wpml:actionGroupEndIndex>1<",
            "<wpml:actionGroupEndIndex>999<",
            "WPML014",
        ),
        ("waylines.wpml", r"<wpml:actionId>3<", "<wpml:actionId>1<", "WPML015"),
        ("waylines.wpml", "goHome", "noAction", "WPML016"),
    ],
)
def test_each_fault_is_detected(
    good: bytes, name: str, pattern: str, replacement: str, code: str
) -> None:
    bad = _mutate(good, name, lambda s: re.sub(pattern, replacement, s, count=1))
    assert code in _codes(bad)


def test_waypoint_cap(good: bytes) -> None:
    assert "WPML010" in _codes(good, max_waypoints=3)


def test_duplicate_waypoints(good: bytes) -> None:
    def dup(s: str) -> str:
        coords = re.findall(r"<coordinates>\s*([^<]+?)\s*</coordinates>", s)
        return s.replace(coords[1], coords[0], 1)

    assert "WPML011" in _codes(_mutate(good, "waylines.wpml", dup))


def test_non_dji_fly_namespace_warns(good: bytes) -> None:
    both = _mutate(good, "waylines.wpml", lambda s: s.replace("uav.com", "example.org"))
    both = _mutate(both, "template.kml", lambda s: s.replace("uav.com", "example.org"))
    issues = lint_kmz(both, LintLimits())
    assert ("warning", "WPML003") in {(i.level, i.code) for i in issues}
