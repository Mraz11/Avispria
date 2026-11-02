# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import hashlib
import sys
from pathlib import Path

import pytest

from avispria.adapters import adb as adb_module
from avispria.adapters.adb import Adb, AdbError, AdbNotFound, Device

FAKE = Path(__file__).resolve().parents[1] / "fakes" / "fake_adb.py"
WAYPOINT = "/sdcard/Android/data/dji.go.v5/files/waypoint"


@pytest.fixture
def phone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty fake phone; returns its file system root."""
    root = tmp_path / "phone"
    (root / WAYPOINT.lstrip("/") / "59B88CA7-CDF1-4396-8DAE-180AC23D1645").mkdir(parents=True)
    monkeypatch.setenv("FAKE_ADB_ROOT", str(root))
    monkeypatch.setenv("FAKE_ADB_LOG", str(tmp_path / "adb.log"))
    return root


@pytest.fixture
def adb() -> Adb:
    return Adb([sys.executable, str(FAKE)], timeout=30)


def test_the_phone_is_found_with_its_model_and_state(phone: Path, adb: Adb) -> None:
    assert adb.devices() == [Device("f2e66f48", "device", "Redmi K90")]
    assert adb.devices()[0].ready and not adb.devices()[0].wireless


@pytest.mark.parametrize(
    ("state", "ready"),
    [("device", True), ("unauthorized", False), ("offline", False), ("none", False)],
)
def test_every_connection_state_is_reported(
    phone: Path, adb: Adb, monkeypatch, state: str, ready: bool
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("FAKE_ADB_STATE", state)
    found = adb.devices()
    assert (state == "none" and found == []) or (
        found and found[0].state == state and found[0].ready == ready
    )


def test_a_phone_that_has_not_allowed_the_computer_gets_instructions(
    phone: Path, adb: Adb, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("FAKE_ADB_STATE", "unauthorized")
    with pytest.raises(AdbError, match=r"tap\s+Allow"):
        adb.ls("f2e66f48", WAYPOINT)
    monkeypatch.setenv("FAKE_ADB_STATE", "none")
    with pytest.raises(AdbError, match="No phone is connected"):
        adb.ls("f2e66f48", WAYPOINT)
    monkeypatch.setenv("FAKE_ADB_STATE", "offline")
    with pytest.raises(AdbError, match="offline"):
        adb.ls("f2e66f48", WAYPOINT)


def test_listing_copying_and_checking_files(phone: Path, adb: Adb, tmp_path: Path) -> None:
    assert adb.ls("f2e66f48", WAYPOINT) == ["59B88CA7-CDF1-4396-8DAE-180AC23D1645"]
    source = tmp_path / "mission.kmz"
    source.write_bytes(b"PK mission bytes")
    remote = (
        f"{WAYPOINT}/59B88CA7-CDF1-4396-8DAE-180AC23D1645/59B88CA7-CDF1-4396-8DAE-180AC23D1645.kmz"
    )
    adb.push("f2e66f48", source, remote)
    assert adb.exists("f2e66f48", remote) and not adb.exists("f2e66f48", remote + ".nope")
    assert adb.sha256("f2e66f48", remote) == hashlib.sha256(b"PK mission bytes").hexdigest()
    back = adb.pull("f2e66f48", remote, tmp_path / "copy" / "back.kmz")
    assert back.read_bytes() == b"PK mission bytes"
    adb.move("f2e66f48", remote, remote + ".old")
    assert not adb.exists("f2e66f48", remote) and adb.exists("f2e66f48", remote + ".old")
    adb.remove("f2e66f48", remote + ".old")
    assert not adb.exists("f2e66f48", remote + ".old")


def test_a_missing_file_is_a_clear_error_and_says_it_is_missing(phone: Path, adb: Adb) -> None:
    with pytest.raises(AdbError, match="not on the phone") as info:
        adb.ls("f2e66f48", WAYPOINT + "/nothing-here")
    assert info.value.missing is True


@pytest.mark.parametrize(
    "path",
    [
        "/etc/passwd",
        "/sdcard/../data/x",
        "/sdcard/a b",
        "/sdcard/x;rm -rf /",
        "/sdcard/$(id)",
        "relative/path",
        "",
    ],
)
def test_unusual_paths_never_reach_the_phone(
    phone: Path, adb: Adb, tmp_path: Path, path: str
) -> None:
    with pytest.raises(AdbError, match="Refusing an unusual path"):
        adb.ls("f2e66f48", path)
    with pytest.raises(AdbError, match="Refusing an unusual path"):
        adb.remove("f2e66f48", path)
    log = (tmp_path / "adb.log").read_text() if (tmp_path / "adb.log").exists() else ""
    assert "passwd" not in log and "rm -f" not in log  # nothing was even attempted


@pytest.mark.parametrize("serial", ["x y", "a;b", "$(id)", "", "x" * 81])
def test_odd_serial_numbers_are_refused(phone: Path, adb: Adb, serial: str) -> None:
    with pytest.raises(AdbError, match="valid phone serial"):
        adb.run("devices", serial=serial)


def test_a_failing_transfer_is_an_error_not_a_silent_success(
    phone: Path, adb: Adb, tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    source = tmp_path / "m.kmz"
    source.write_bytes(b"x")
    monkeypatch.setenv("FAKE_ADB_FAIL", "push")
    with pytest.raises(AdbError, match="refused access"):
        adb.push("f2e66f48", source, f"{WAYPOINT}/new.kmz")
    with pytest.raises(AdbError, match="was not found"):
        adb.push("f2e66f48", tmp_path / "missing.kmz", f"{WAYPOINT}/new.kmz")


def test_wireless_pairing_and_connecting(phone: Path, adb: Adb) -> None:
    assert "Successfully paired" in adb.pair("192.168.1.5:37123", "123456")
    assert "connected to 192.168.1.5:41000" in adb.connect("192.168.1.5:41000")
    with pytest.raises(AdbError, match="Pairing failed"):
        adb.pair("192.168.1.5:37123", "000000")
    for bad in ("192.168.1.5", "host;rm:123", "http://x:1"):
        with pytest.raises(AdbError, match="address shown on the phone"):
            adb.connect(bad)
    with pytest.raises(AdbError, match="6-digit"):
        adb.pair("192.168.1.5:37123", "12ab56")
    assert Device("192.168.1.5:41000", "device").wireless


def test_closing_an_app_only_accepts_real_package_names(
    phone: Path, adb: Adb, tmp_path: Path
) -> None:
    adb.close_app("f2e66f48", "dji.go.v5")
    assert "am force-stop dji.go.v5" in (tmp_path / "adb.log").read_text()
    with pytest.raises(AdbError, match="Not a valid app name"):
        adb.close_app("f2e66f48", "dji.go.v5; reboot")


def test_finding_the_adb_program(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    exe = tmp_path / ("adb.exe" if sys.platform == "win32" else "adb")
    exe.write_bytes(b"")
    assert Adb.find(str(exe)).command == [str(exe)]  # a file
    assert Adb.find(str(tmp_path)).command == [str(exe)]  # or the folder it is in
    with pytest.raises(AdbNotFound, match="was not found at"):
        Adb.find(str(tmp_path / "nowhere"))
    monkeypatch.setattr(adb_module.shutil, "which", lambda name: None)
    monkeypatch.setattr(adb_module, "candidate_locations", lambda: [])
    with pytest.raises(AdbNotFound, match="platform-tools"):  # tells where to get it
        Adb.find()
    with pytest.raises(AdbNotFound):
        Adb(["/no/such/adb-program"]).devices()
