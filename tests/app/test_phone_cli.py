# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import sys
import zipfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from avispria.adapters.adb import Adb, AdbNotFound
from avispria.app.cli import app
from avispria.app.phone_workflow import WAYPOINT_DIR, kmz_path

runner = CliRunner()
FAKE = Path(__file__).resolve().parents[1] / "fakes" / "fake_adb.py"
SAMPLE = Path(__file__).resolve().parents[1] / "fixtures" / "dji_fly_dummy" / "lito_x1_5wp.kmz"
SLOT = "59B88CA7-CDF1-4396-8DAE-180AC23D1645"


@pytest.fixture
def phone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "phone"
    base = root / WAYPOINT_DIR.lstrip("/")
    (base / SLOT).mkdir(parents=True)
    (base / SLOT / f"{SLOT}.kmz").write_bytes(SAMPLE.read_bytes())
    monkeypatch.setenv("FAKE_ADB_ROOT", str(root))
    monkeypatch.setattr(
        Adb, "find", classmethod(lambda cls, explicit=None: Adb([sys.executable, str(FAKE)]))
    )
    return root


def plan(tmp_path: Path) -> Path:
    out = tmp_path / "plan.kmz"
    with zipfile.ZipFile(SAMPLE) as src, zipfile.ZipFile(out, "w") as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            dst.writestr(
                item.filename,
                data + b"\n<!-- my plan -->\n" if item.filename.endswith("wpml") else data,
            )
    return out


def test_status_shows_the_phone_and_how_it_is_connected(
    phone: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = runner.invoke(app, ["phone", "status"]).output
    assert "f2e66f48" in out and "Redmi K90" in out and "(USB)" in out
    monkeypatch.setenv("FAKE_ADB_SERIAL", "192.168.1.5:41000")
    assert "(Wi-Fi)" in runner.invoke(app, ["phone", "status"]).output
    monkeypatch.setenv("FAKE_ADB_STATE", "none")
    assert "none connected" in runner.invoke(app, ["phone", "status"]).output
    monkeypatch.setenv("FAKE_ADB_STATE", "unauthorized")
    assert "tap Allow" in runner.invoke(app, ["phone", "status"]).output.replace("\n", " ")


def test_no_adb_gives_instructions_and_a_failing_exit_code(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(cls, explicit=None):  # type: ignore[no-untyped-def]
        raise AdbNotFound("adb was not found. Download 'SDK Platform-Tools'.")

    monkeypatch.setattr(Adb, "find", classmethod(missing))
    for args in (
        ["phone", "status"],
        ["phone", "slots"],
        ["phone", "pair", "1.2.3.4:5555", "123456"],
    ):
        result = runner.invoke(app, args)
        assert result.exit_code == 1 and "Platform-Tools" in result.output, args


def test_slots_lists_the_missions(phone: Path) -> None:
    out = runner.invoke(app, ["phone", "slots"]).output
    assert SLOT in out and "5 waypoints" in out and "1 mission(s)" in out


def test_pull_copies_a_mission_and_refuses_a_made_up_id(phone: Path, tmp_path: Path) -> None:
    ok = runner.invoke(app, ["phone", "pull", SLOT, "--out", str(tmp_path / "sample")])
    assert (
        ok.exit_code == 0
        and (tmp_path / "sample" / f"{SLOT}.kmz").read_bytes() == SAMPLE.read_bytes()
    )
    bad = runner.invoke(app, ["phone", "pull", "../../etc/passwd", "--out", str(tmp_path)])
    assert bad.exit_code == 1 and "Not a DJI Fly mission id" in bad.output


def test_send_asks_first_and_declining_changes_nothing(phone: Path, tmp_path: Path) -> None:
    original = (phone / kmz_path(SLOT).lstrip("/")).read_bytes()
    result = runner.invoke(
        app,
        ["phone", "send", str(plan(tmp_path)), "--slot", SLOT, "--backup-dir", str(tmp_path / "b")],
        input="n\n",
    )
    assert result.exit_code == 1 and "This replaces mission 59B88CA7 (5 waypoints)" in result.output
    assert (phone / kmz_path(SLOT).lstrip("/")).read_bytes() == original
    assert not (tmp_path / "b").exists()  # not even a backup: nothing was started


def test_send_replaces_the_mission_after_confirmation_and_says_what_to_do_next(
    phone: Path, tmp_path: Path
) -> None:
    original = (phone / kmz_path(SLOT).lstrip("/")).read_bytes()
    mine = plan(tmp_path)
    result = runner.invoke(
        app,
        ["phone", "send", str(mine), "--slot", SLOT, "--backup-dir", str(tmp_path / "b")],
        input="y\n",
    )
    assert result.exit_code == 0, result.output
    assert (phone / kmz_path(SLOT).lstrip("/")).read_bytes() == mine.read_bytes()
    assert next((tmp_path / "b").glob("*_original.kmz")).read_bytes() == original
    assert "close DJI Fly completely" in result.output
    assert (
        "last sent by Avispria: plan.kmz"
        in runner.invoke(app, ["phone", "slots", "--backup-dir", str(tmp_path / "b")]).output
    )


def test_closing_dji_fly_is_announced_with_a_warning(phone: Path, tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "phone",
            "send",
            str(plan(tmp_path)),
            "--slot",
            SLOT,
            "--backup-dir",
            str(tmp_path / "b"),
            "--close-app",
            "--yes",
        ],
    )
    assert result.exit_code == 0 and "no flight is in progress" in result.output


def test_sending_to_a_mission_that_is_not_there_is_refused(phone: Path, tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "phone",
            "send",
            str(plan(tmp_path)),
            "--slot",
            "AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA",
            "--yes",
            "--backup-dir",
            str(tmp_path / "b"),
        ],
    )
    assert result.exit_code == 1 and "There is no mission" in result.output


def test_wireless_pairing_and_connecting(phone: Path) -> None:
    ok = runner.invoke(app, ["phone", "pair", "192.168.1.5:37123", "123456"])
    assert ok.exit_code == 0 and "Successfully paired" in ok.output and "phone connect" in ok.output
    assert runner.invoke(app, ["phone", "pair", "192.168.1.5:37123", "000000"]).exit_code == 1
    assert (
        "connected to 192.168.1.5:41000"
        in runner.invoke(app, ["phone", "connect", "192.168.1.5:41000"]).output
    )
