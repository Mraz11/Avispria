# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import sys
import zipfile
from datetime import datetime
from pathlib import Path

import pytest

from avispria.adapters.adb import Adb, AdbError
from avispria.app.phone_workflow import (
    NEW_SUFFIX,
    WAYPOINT_DIR,
    SendError,
    kmz_path,
    list_slots,
    pull_mission,
    ready_device,
    send_mission,
    sha256_of,
)

FAKE = Path(__file__).resolve().parents[1] / "fakes" / "fake_adb.py"
SAMPLE = Path(__file__).resolve().parents[1] / "fixtures" / "dji_fly_dummy" / "lito_x1_5wp.kmz"
SERIAL = "f2e66f48"
SLOT = "59B88CA7-CDF1-4396-8DAE-180AC23D1645"
OTHER = "F6C1AB6D-E118-4CA5-87DE-F90EF97069E6"
WHEN = datetime(2026, 10, 30, 18, 5, 0)


def plan_b(tmp_path: Path) -> Path:
    """A second valid mission file: the sample with a harmless XML comment, so its bytes differ."""
    out = tmp_path / "plan_b.kmz"
    with zipfile.ZipFile(SAMPLE) as src, zipfile.ZipFile(out, "w") as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename.endswith("waylines.wpml"):
                data = data.rstrip() + b"\n<!-- plan b -->\n"
            dst.writestr(item.filename, data)
    return out


@pytest.fixture
def phone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A phone with two DJI Fly missions (one with a map picture) and DJI's other folders."""
    root = tmp_path / "phone"
    base = root / WAYPOINT_DIR.lstrip("/")
    (base / SLOT).mkdir(parents=True)
    (base / SLOT / f"{SLOT}.kmz").write_bytes(SAMPLE.read_bytes())
    (base / OTHER).mkdir()
    (base / OTHER / f"{OTHER}.kmz").write_bytes(b"not a kmz at all")  # unreadable, still listed
    (base / "map_preview" / SLOT).mkdir(parents=True)
    (base / "map_preview" / SLOT / f"{SLOT}.jpg").write_bytes(b"\xff\xd8 a small map picture")
    (base / "capability").mkdir()
    monkeypatch.setenv("FAKE_ADB_ROOT", str(root))
    monkeypatch.setenv("FAKE_ADB_LOG", str(tmp_path / "adb.log"))
    return root


@pytest.fixture
def adb() -> Adb:
    return Adb([sys.executable, str(FAKE)])


def remote(phone: Path, guid: str = SLOT) -> Path:
    return phone / kmz_path(guid).lstrip("/")


def leftovers(phone: Path) -> list[str]:
    return [
        p.name for p in (phone / WAYPOINT_DIR.lstrip("/")).rglob("*") if p.name.endswith(NEW_SUFFIX)
    ]


def test_the_missions_on_the_phone_are_listed_with_what_dji_fly_keeps(
    phone: Path, adb: Adb, tmp_path: Path
) -> None:
    slots = list_slots(adb, SERIAL, tmp_path / "backups")
    assert {s.guid for s in slots} == {SLOT, OTHER}  # capability and map_preview are not missions
    good = next(s for s in slots if s.guid == SLOT)
    assert good.waypoints == 5 and good.short == "59B88CA7"
    assert good.created is not None and good.created.year == 2026  # from the file's own createTime
    assert good.preview is not None and good.preview.startswith(b"\xff\xd8")
    broken = next(s for s in slots if s.guid == OTHER)
    assert broken.waypoints == 0 and broken.preview is None and broken.created is None
    assert slots[0].guid == SLOT  # the one with a date comes before the one without


def test_a_phone_without_dji_flys_folder_gets_a_helpful_message(
    phone: Path, adb: Adb, tmp_path: Path
) -> None:
    import shutil

    shutil.rmtree(phone / WAYPOINT_DIR.lstrip("/"))
    with pytest.raises(AdbError, match="Open DJI Fly once"):
        list_slots(adb, SERIAL, tmp_path / "backups")


def test_a_mission_can_be_copied_out_to_use_as_the_sample(
    phone: Path, adb: Adb, tmp_path: Path
) -> None:
    out = pull_mission(adb, SERIAL, SLOT, tmp_path / "sample")
    assert out.name == f"{SLOT}.kmz" and out.read_bytes() == SAMPLE.read_bytes()
    with pytest.raises(SendError, match="Not a DJI Fly mission id"):
        pull_mission(adb, SERIAL, "../../etc/passwd", tmp_path)


def test_sending_replaces_the_mission_keeps_the_original_and_leaves_nothing_behind(
    phone: Path, adb: Adb, tmp_path: Path
) -> None:
    plan, backups = plan_b(tmp_path), tmp_path / "backups"
    original = remote(phone).read_bytes()
    result = send_mission(adb, SERIAL, plan, SLOT, backups, close_app=True, now=WHEN)
    assert remote(phone).read_bytes() == plan.read_bytes()  # the phone now has the plan
    assert result.backup.read_bytes() == original  # and we still have exactly what was there
    assert result.backup.name == f"{SLOT}_20261030-180500_original.kmz"
    assert result.sha256 == sha256_of(plan) and result.closed_app
    assert leftovers(phone) == []  # no temporary file
    assert "am force-stop dji.go.v5" in (tmp_path / "adb.log").read_text()
    again = next(s for s in list_slots(adb, SERIAL, backups) if s.guid == SLOT)
    assert again.last_sent == "plan_b.kmz at 2026-10-30 18:05"  # the list remembers what went where


def test_dji_fly_is_only_closed_when_asked(phone: Path, adb: Adb, tmp_path: Path) -> None:
    send_mission(adb, SERIAL, plan_b(tmp_path), SLOT, tmp_path / "b")
    assert "force-stop" not in (tmp_path / "adb.log").read_text()


def test_other_missions_are_never_touched(phone: Path, adb: Adb, tmp_path: Path) -> None:
    before = remote(phone, OTHER).read_bytes()
    send_mission(adb, SERIAL, plan_b(tmp_path), SLOT, tmp_path / "b")
    assert remote(phone, OTHER).read_bytes() == before
    log = (tmp_path / "adb.log").read_text()
    assert OTHER not in log.split("push")[-1] and " rm " not in f" {log} ".replace(
        "rm -f", ""
    ).replace("shell rm", "x")
    deletes = [line for line in log.splitlines() if "rm" in line.split()]
    assert all(line.endswith(NEW_SUFFIX) for line in deletes)  # only ever a temporary file


@pytest.mark.parametrize(
    "bad", ["lower-case-id", "../../etc/passwd", f"{SLOT}/../x", f"{SLOT}; reboot", ""]
)
def test_a_slot_id_that_is_not_a_dji_fly_mission_id_is_refused(
    phone: Path, adb: Adb, tmp_path: Path, bad: str
) -> None:
    with pytest.raises(SendError, match="Not a DJI Fly mission id"):
        send_mission(adb, SERIAL, plan_b(tmp_path), bad, tmp_path / "b")


def test_a_file_dji_fly_cannot_read_is_never_sent(phone: Path, adb: Adb, tmp_path: Path) -> None:
    junk = tmp_path / "junk.kmz"
    junk.write_bytes(b"this is not a mission")
    original = remote(phone).read_bytes()
    with pytest.raises(SendError, match="has problems, so it was not sent"):
        send_mission(adb, SERIAL, junk, SLOT, tmp_path / "b")
    assert (
        remote(phone).read_bytes() == original and not (tmp_path / "b").exists()
    )  # nothing happened at all
    with pytest.raises(SendError, match="could not be read"):
        send_mission(adb, SERIAL, tmp_path / "missing.kmz", SLOT, tmp_path / "b")


def test_a_slot_that_disappeared_is_reported_before_anything_is_written(
    phone: Path, adb: Adb, tmp_path: Path
) -> None:
    with pytest.raises(SendError, match="not on the phone any more"):
        send_mission(
            adb, SERIAL, plan_b(tmp_path), "AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA", tmp_path / "b"
        )


def test_a_refused_write_changes_nothing(
    phone: Path, adb: Adb, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = remote(phone).read_bytes()
    monkeypatch.setenv("FAKE_ADB_FAIL", "push")
    with pytest.raises(SendError, match="nothing was changed"):
        send_mission(adb, SERIAL, plan_b(tmp_path), SLOT, tmp_path / "b")
    assert remote(phone).read_bytes() == original and leftovers(phone) == []


def test_a_file_that_arrives_damaged_is_detected_and_never_swapped_in(
    phone: Path, adb: Adb, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = remote(phone).read_bytes()
    monkeypatch.setenv("FAKE_ADB_CORRUPT", "push")
    with pytest.raises(SendError, match="arrived damaged"):
        send_mission(adb, SERIAL, plan_b(tmp_path), SLOT, tmp_path / "b")
    assert remote(phone).read_bytes() == original and leftovers(phone) == []


def test_a_swap_that_leaves_a_damaged_file_is_undone_from_the_backup(
    phone: Path, adb: Adb, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = remote(phone).read_bytes()
    monkeypatch.setenv(
        "FAKE_ADB_CORRUPT", "mv"
    )  # the phone damages the file as it is moved into place
    with pytest.raises(SendError, match="original mission was put back"):
        send_mission(adb, SERIAL, plan_b(tmp_path), SLOT, tmp_path / "b")
    assert remote(phone).read_bytes() == original  # exactly as it was
    assert leftovers(phone) == []


def test_when_even_the_restore_fails_the_message_says_where_the_original_is(
    phone: Path, adb: Adb, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = remote(phone).read_bytes()
    monkeypatch.setenv("FAKE_ADB_FAIL", "mv")  # the swap itself is refused, so is the restore
    with pytest.raises(SendError, match="Your original is safe on this computer") as info:
        send_mission(adb, SERIAL, plan_b(tmp_path), SLOT, tmp_path / "b")
    assert str(tmp_path / "b") in str(info.value)
    assert remote(phone).read_bytes() == original  # the real file was never replaced


def devices_with(monkeypatch: pytest.MonkeyPatch, state: str) -> None:
    monkeypatch.setenv("FAKE_ADB_STATE", state)


def test_choosing_the_phone(phone: Path, adb: Adb, monkeypatch: pytest.MonkeyPatch) -> None:
    assert ready_device(adb).serial == SERIAL and ready_device(adb, SERIAL).model == "Redmi K90"
    with pytest.raises(AdbError, match="is not connected"):
        ready_device(adb, "someone-else")
    devices_with(monkeypatch, "unauthorized")
    with pytest.raises(AdbError, match="Allow"):
        ready_device(adb)
    devices_with(monkeypatch, "offline")
    with pytest.raises(AdbError, match="offline"):
        ready_device(adb)
    devices_with(monkeypatch, "none")
    with pytest.raises(AdbError, match="No phone is connected"):
        ready_device(adb)
