# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import threading
from pathlib import Path

import pytest

from avispria.adapters import system_probe
from avispria.app import process_workflow
from avispria.app.ui.process_job import (
    ProcessForm,
    ProcessFormError,
    build_request,
    check_computer,
    default_output,
    execute_process,
)
from avispria.app.ui.views import option_lines
from avispria.core.feasibility import SystemSpec
from fakes.nodeodx import fake_engine
from photobuild import make_dji_jpeg

BIG = SystemSpec("Windows 11", 12, 16.0, 8.0, 15.0, 200.0)
TINY = SystemSpec("Windows 11", 2, 2.0, 1.0, 0.0, 200.0)


def photos(tmp_path: Path, n: int = 6) -> Path:
    folder = tmp_path / "survey" / "images"
    folder.mkdir(parents=True)
    for i in range(n):
        make_dji_jpeg(
            folder / f"DJI_{i:04d}.JPG",
            size=(800, 600),
            lat=22.2820 + (i % 3) * 0.0001,
            lon=91.7790 + (i // 3) * 0.0002,
        )
    return folder


class Quiet:
    def step(self, title: str) -> None: ...
    def info(self, text: str) -> None: ...
    def warn(self, text: str) -> None: ...
    def upload(self, percent: float) -> None: ...
    def progress(self, percent: float, status: str) -> None: ...


def test_the_default_output_folder_is_next_to_the_photos_and_named_after_the_survey(
    tmp_path: Path,
) -> None:
    folder = photos(tmp_path)  # .../survey/images
    assert default_output(str(folder)) == str(tmp_path / "survey" / "survey_avispria")
    assert default_output("") == "" and default_output("   ") == ""


def test_a_valid_form_becomes_a_request(tmp_path: Path) -> None:
    folder = photos(tmp_path)
    stop = threading.Event()
    request = build_request(ProcessForm(str(folder), preset="fast", recursive=True), stop)
    assert request.folder == folder and request.preset == "fast" and request.recursive
    assert request.out_dir == tmp_path / "survey" / "survey_avispria"
    assert request.resize_mp == pytest.approx(12.2) and request.cancel is stop
    assert build_request(ProcessForm(str(folder), photo_size="full")).resize_mp is None
    assert build_request(ProcessForm(str(folder), photo_size="6")).resize_mp == 6.0


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"folder": ""}, "Choose the folder with your photos"),
        ({"folder": "/nowhere/photos"}, "does not exist"),
        ({"preset": "ultra"}, "quality levels"),
        ({"photo_size": "huge"}, "photo sizes"),
    ],
)
def test_form_mistakes_say_what_to_change(
    tmp_path: Path, change: dict[str, str], message: str
) -> None:
    form = ProcessForm(folder=str(photos(tmp_path)))
    values = {**form.__dict__, **change}
    with pytest.raises(ProcessFormError, match=message):
        build_request(ProcessForm(**values))


def test_results_cannot_go_inside_the_photo_folder_or_onto_a_file(tmp_path: Path) -> None:
    folder = photos(tmp_path)
    with pytest.raises(ProcessFormError, match="outside the photo folder"):
        build_request(ProcessForm(str(folder), out_dir=str(folder / "results")))
    with pytest.raises(ProcessFormError, match="outside the photo folder"):
        build_request(ProcessForm(str(folder), out_dir=str(folder)))
    a_file = tmp_path / "notes.txt"
    a_file.write_text("x")
    with pytest.raises(ProcessFormError, match="a file, not a folder"):
        build_request(ProcessForm(str(folder), out_dir=str(a_file)))


def patch_machine(monkeypatch: pytest.MonkeyPatch, port: int, pc: SystemSpec = BIG) -> None:
    local = system_probe.LocalNode(f"http://127.0.0.1:{port}", "t", 99, None)
    monkeypatch.setattr(process_workflow.system_probe, "find_local_node", lambda: local)
    monkeypatch.setattr(process_workflow.system_probe, "probe_system", lambda path: pc)
    monkeypatch.setattr(process_workflow, "DEFAULT_POLL_S", 0.05)


def test_the_computer_check_uses_the_chosen_photo_size(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from avispria.app import doctor as doctor_module

    folder = photos(tmp_path)
    monkeypatch.setattr(doctor_module, "probe_system", lambda workdir: BIG)
    monkeypatch.setattr(doctor_module, "probe_engines", lambda: [])
    normal = check_computer(ProcessForm(str(folder)))
    assert normal.assessment is not None and normal.assessment.verdict == "ok"
    assert normal.assessment.processing_mp <= 12.2
    with_full = check_computer(ProcessForm(str(folder), photo_size="full"))
    assert with_full.assessment is not None and with_full.job is not None
    assert with_full.assessment.processing_mp == pytest.approx(with_full.job.native_mp)


def test_a_job_runs_and_comes_back_with_its_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = photos(tmp_path)
    with fake_engine("t") as (port, state):
        patch_machine(monkeypatch, port)
        result = execute_process(ProcessForm(str(folder), preset="fast"), Quiet())
    assert result.blocked is None and result.outcome is not None and result.outcome.completed
    assert result.provenance is not None and result.provenance["status"] == "COMPLETED"
    assert state.uploads == 6 and (tmp_path / "survey" / "survey_avispria" / "results").is_dir()


def test_a_job_that_does_not_fit_comes_back_blocked_with_alternatives(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = photos(tmp_path)
    with fake_engine("t") as (port, state):
        patch_machine(monkeypatch, port, pc=TINY)
        result = execute_process(ProcessForm(str(folder)), Quiet())
    assert result.outcome is None and result.blocked and "cannot process" in result.blocked
    assert result.assessment is not None and state.uploads == 0
    lines = option_lines(result.assessment)
    assert lines and any(
        "other computer" in line.lower() or "computer with at least" in line for line in lines
    )
    assert all(line.endswith(")") for line in lines)
    # ... and the same job can be forced
    with fake_engine("t") as (port, state):
        patch_machine(monkeypatch, port, pc=TINY)
        forced = execute_process(ProcessForm(str(folder), force=True), Quiet())
    assert forced.outcome is not None and state.uploads == 6
