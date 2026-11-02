# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import shutil
import sys
import zipfile
from pathlib import Path

import pytest

from avispria.adapters.adb import Adb, AdbNotFound
from avispria.app.phone_workflow import WAYPOINT_DIR, SendError, kmz_path
from avispria.app.ui.phone_job import (
    SendRequest,
    check_phone,
    check_requests,
    connect_phone,
    pair_phone,
    send_all,
    use_as_sample,
)

FAKE = Path(__file__).resolve().parents[1] / "fakes" / "fake_adb.py"
SAMPLE = Path(__file__).resolve().parents[1] / "fixtures" / "dji_fly_dummy" / "lito_x1_5wp.kmz"
A, B = "59B88CA7-CDF1-4396-8DAE-180AC23D1645", "F6C1AB6D-E118-4CA5-87DE-F90EF97069E6"


@pytest.fixture
def phone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "phone"
    base = root / WAYPOINT_DIR.lstrip("/")
    for guid in (A, B):
        (base / guid).mkdir(parents=True)
        (base / guid / f"{guid}.kmz").write_bytes(SAMPLE.read_bytes())
    monkeypatch.setenv("FAKE_ADB_ROOT", str(root))
    monkeypatch.setattr(
        Adb, "find", classmethod(lambda cls, explicit=None: Adb([sys.executable, str(FAKE)]))
    )
    return root


def plans(tmp_path: Path, n: int) -> list[Path]:
    out = []
    for i in range(n):
        path = tmp_path / f"survey_{i + 1:02d}.kmz"
        with zipfile.ZipFile(SAMPLE) as src, zipfile.ZipFile(path, "w") as dst:
            for item in src.infolist():
                data = src.read(item.filename)
                dst.writestr(
                    item.filename,
                    data + f"\n<!-- {i} -->\n".encode() if item.filename.endswith("wpml") else data,
                )
        out.append(path)
    return out


def test_a_connected_phone_shows_its_missions(phone: Path) -> None:
    status = check_phone()
    assert status.problem is None and status.serial == "f2e66f48" and status.model == "Redmi K90"
    assert {s.guid for s in status.slots} == {A, B} and status.adb and not status.adb_missing


def test_every_way_the_connection_can_be_wrong_is_a_message_not_a_crash(
    phone: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_ADB_STATE", "unauthorized")
    assert (
        "Allow" in (check_phone().problem or "")
        and check_phone().devices[0].state == "unauthorized"
    )
    monkeypatch.setenv("FAKE_ADB_STATE", "none")
    assert "No phone is connected" in (check_phone().problem or "")
    monkeypatch.setenv("FAKE_ADB_STATE", "device")
    shutil.rmtree(phone / WAYPOINT_DIR.lstrip("/"))
    assert "Open DJI Fly once" in (check_phone().problem or "")
    (phone / WAYPOINT_DIR.lstrip("/")).mkdir(
        parents=True
    )  # the folder exists but DJI Fly has no mission
    empty = check_phone()
    assert (
        "placeholder mission" in (empty.problem or "")
        and empty.serial == "f2e66f48"
        and empty.slots == []
    )

    def missing(cls, explicit=None):  # type: ignore[no-untyped-def]
        raise AdbNotFound("adb was not found.")

    monkeypatch.setattr(Adb, "find", classmethod(missing))
    gone = check_phone()
    assert gone.adb_missing and "adb was not found" in (gone.problem or "") and gone.serial is None


def test_requests_that_cannot_be_right_are_refused_before_anything_is_written(
    phone: Path, tmp_path: Path
) -> None:
    slots = check_phone().slots
    one, two = plans(tmp_path, 2)
    check_requests([SendRequest(one, A), SendRequest(two, B)], slots)  # fine
    for bad, message in (
        ([], "Choose a mission file"),
        ([SendRequest(one, "")], "Choose the slot"),
        ([SendRequest(one, A), SendRequest(two, A)], "chosen twice"),
        ([SendRequest(one, "AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA")], "not on the phone any more"),
        ([SendRequest(tmp_path / "missing.kmz", A)], "was not found"),
    ):
        with pytest.raises(SendError, match=message):
            check_requests(bad, slots)


def test_a_whole_plan_goes_to_its_slots_with_backups(phone: Path, tmp_path: Path) -> None:
    one, two = plans(tmp_path, 2)
    out = send_all(
        "", "f2e66f48", [SendRequest(one, A), SendRequest(two, B)], tmp_path / "b", close_app=True
    )
    assert [o.error for o in out] == [None, None]
    assert (phone / kmz_path(A).lstrip("/")).read_bytes() == one.read_bytes()
    assert (phone / kmz_path(B).lstrip("/")).read_bytes() == two.read_bytes()
    assert len(list((tmp_path / "b").glob("*_original.kmz"))) == 2
    assert [o.result.closed_app for o in out if o.result] == [
        True,
        False,
    ]  # closed once, before the first


def test_the_first_failure_stops_the_rest_and_leaves_earlier_missions_sent(
    phone: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    one, _two, three = plans(tmp_path, 3)
    original_b = (phone / kmz_path(B).lstrip("/")).read_bytes()
    out = send_all(
        "",
        "f2e66f48",
        [SendRequest(one, A), SendRequest(tmp_path / "gone.kmz", B), SendRequest(three, A)],
        tmp_path / "b",
    )
    assert (
        out[0].error is None
        and out[1].error
        and "could not be read" in out[1].error
        and len(out) == 2
    )
    assert (
        phone / kmz_path(A).lstrip("/")
    ).read_bytes() == one.read_bytes()  # the first one stays sent
    assert (
        phone / kmz_path(B).lstrip("/")
    ).read_bytes() == original_b  # the failed one is as it was


def test_a_mission_is_copied_out_as_the_sample(phone: Path, tmp_path: Path) -> None:
    path = use_as_sample("", "f2e66f48", A, tmp_path / "samples")
    assert path == tmp_path / "samples" / f"{A}.kmz" and path.read_bytes() == SAMPLE.read_bytes()


def test_wireless_pairing_goes_through(phone: Path) -> None:
    assert "Successfully paired" in pair_phone("", " 192.168.1.5:37123 ", " 123456 ")
    assert "connected to 192.168.1.5:41000" in connect_phone("", "192.168.1.5:41000")


def test_a_mission_avispria_cannot_read_is_never_a_slot(phone: Path, tmp_path: Path) -> None:
    junk = A.replace("59B88CA7", "AAAAAAAA")
    base = phone / WAYPOINT_DIR.lstrip("/") / junk
    base.mkdir(parents=True)
    (base / f"{junk}.kmz").write_bytes(
        b"not a waypoint mission"
    )  # e.g. a point-of-interest mission
    slots = check_phone().slots
    assert next(s for s in slots if s.guid == junk).waypoints == 0
    (plan,) = plans(tmp_path, 1)
    with pytest.raises(SendError, match="cannot read mission AAAAAAAA"):
        check_requests([SendRequest(plan, junk)], slots)
    check_requests([SendRequest(plan, A)], slots)  # a readable one is still fine
