# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from avispria.adapters import system_probe
from avispria.app import process_workflow
from avispria.app.cli import app
from avispria.core.feasibility import SystemSpec
from fakes.nodeodx import fake_engine
from photobuild import make_dji_jpeg

runner = CliRunner()
BIG_PC = SystemSpec("Windows 11", 12, 16.0, 8.0, 15.0, 200.0)
TINY_PC = SystemSpec("Windows 11", 2, 2.0, 1.0, 0.0, 200.0)


def photo_folder(tmp_path: Path, n: int = 6) -> Path:
    folder = tmp_path / "flight"
    folder.mkdir()
    for i in range(n):
        make_dji_jpeg(
            folder / f"DJI_{i:04d}.JPG",
            size=(800, 600),
            lat=22.2820 + (i % 3) * 0.0001,
            lon=91.7790 + (i // 3) * 0.0002,
        )
    return folder


def _patch(monkeypatch: pytest.MonkeyPatch, port: int, token: str, pc: SystemSpec = BIG_PC) -> None:
    local = system_probe.LocalNode(f"http://127.0.0.1:{port}", token, 99, None)
    monkeypatch.setattr(process_workflow.system_probe, "find_local_node", lambda: local)
    monkeypatch.setattr(process_workflow.system_probe, "probe_system", lambda path: pc)
    monkeypatch.setattr(process_workflow, "DEFAULT_POLL_S", 0.05)


def _run(folder: Path, out: Path, *extra: str) -> object:
    from avispria.app.cli import process as process_cli

    process_cli.DEFAULT_RESIZE_MP = 0.12  # small test photos: still exercise resizing
    return runner.invoke(app, ["process", str(folder), "--out", str(out), *extra])


def test_process_end_to_end(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    folder, out = photo_folder(tmp_path), tmp_path / "out"
    with fake_engine("hidden-token-123") as (port, state):
        _patch(monkeypatch, port, "hidden-token-123")
        result = _run(folder, out)
    assert result.exit_code == 0, result.output
    assert "hidden-token-123" not in result.output
    assert state.uploads == 6
    sent = {o["name"]: o["value"] for o in state.options}
    assert sent == {
        "dsm": True,
        "pc-quality": "medium",
        "feature-quality": "high",
        "rolling-shutter": True,
    }
    assert "left out: auto-boundary" in result.output  # fake engine lacks it
    assert "resized 6 of 6 photos" in result.output
    assert (out / "results" / "odm_orthophoto" / "odm_orthophoto.tif").exists()
    assert (out / "flight_all.zip").exists() and not (out / ".avispria-upload").exists()
    prov = json.loads((out / "avispria_provenance.json").read_text())
    assert prov["status"] == "COMPLETED" and prov["engine"]["engine_version"] == "3.6.2"
    assert len(prov["inputs"]) == 6 and all(len(i["sha256"]) == 64 for i in prov["inputs"])
    assert any(o["file"].endswith("odm_orthophoto.tif") for o in prov["outputs"])
    assert "hidden-token-123" not in (out / "avispria_provenance.json").read_text()


def test_process_reports_engine_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    folder, out = photo_folder(tmp_path), tmp_path / "out"
    with fake_engine("t", outcome="fail") as (port, _):
        _patch(monkeypatch, port, "t")
        result = _run(folder, out, "--preset", "fast")
    assert result.exit_code == 1
    assert "Processing failed: Process exited with code 1" in result.output
    assert "not enough memory" in result.output
    assert json.loads((out / "avispria_provenance.json").read_text())["status"] == "FAILED"


def test_process_blocked_on_small_computer(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    folder, out = photo_folder(tmp_path), tmp_path / "out"
    with fake_engine("t") as (port, state):
        _patch(monkeypatch, port, "t", pc=TINY_PC)
        result = _run(folder, out)
    assert result.exit_code == 1
    assert "Not started: this computer cannot process" in result.output
    assert "What you can do:" in result.output and state.uploads == 0


def test_process_needs_five_photos(tmp_path: Path) -> None:
    result = _run(photo_folder(tmp_path, n=3), tmp_path / "out")
    assert result.exit_code == 1 and "at least 5 are needed" in result.output


def test_unknown_preset(tmp_path: Path) -> None:
    result = _run(photo_folder(tmp_path), tmp_path / "out", "--preset", "maximum")
    assert result.exit_code == 2 and "unknown preset" in result.output


def test_task_name_skips_generic_folders(tmp_path: Path) -> None:
    from avispria.app.process_workflow import task_name

    (tmp_path / "brighton" / "images").mkdir(parents=True)
    (tmp_path / "site1" / "DCIM" / "100MEDIA").mkdir(parents=True)
    assert task_name(tmp_path / "brighton" / "images") == "brighton"
    assert task_name(tmp_path / "site1" / "DCIM" / "100MEDIA") == "site1"
    assert task_name(tmp_path / "brighton") == "brighton"


def test_qa_that_cannot_assess_is_only_a_warning(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    folder = tmp_path / "plain" / "images"
    folder.mkdir(parents=True)
    from PIL import Image

    for i in range(6):  # photos without any position metadata
        Image.new("RGB", (400, 300)).save(folder / f"IMG_{i}.JPG", "JPEG")
    out = tmp_path / "out"
    with fake_engine("t") as (port, _):
        _patch(monkeypatch, port, "t")
        result = _run(folder, out)
    assert result.exit_code == 0, result.output
    prov = json.loads((out / "avispria_provenance.json").read_text())
    assert prov["capture_qa"]["advisory"] is True
    assert {i["level"] for i in prov["capture_qa"]["issues"]} == {"warning"}
    assert (out / "plain_all.zip").exists()
