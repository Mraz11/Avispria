# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest

from avispria.adapters.system_probe import EngineStatus
from avispria.app import doctor as doctor_module
from avispria.app.ui import state
from avispria.core.feasibility import SystemSpec


@pytest.fixture(autouse=True)
def fresh_state() -> None:
    state.reset()


@pytest.fixture
def fake_computer(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """A computer with the given memory and (optionally) a running WebODM."""

    def install(ram: float = 16.0, webodm: bool = True, disk: float = 200.0) -> None:
        spec = SystemSpec("Windows 11", 12, ram, ram * 0.5, 4.0, disk)
        engines = [
            EngineStatus("WebODM", "http://127.0.0.1:29800/", webodm, "HTTP 200"),
            EngineStatus("Processing node", "http://127.0.0.1:29301/info", webodm, "ok"),
        ]
        monkeypatch.setattr(doctor_module, "probe_system", lambda workdir: spec)
        monkeypatch.setattr(doctor_module, "probe_engines", lambda: engines)
        monkeypatch.setattr(doctor_module, "running_engine_programs", lambda: [])

    return install


@pytest.fixture
def photo_folder(tmp_path):  # type: ignore[no-untyped-def]
    """Twelve small DJI-like photos in a 2 x 6 block, ~83% front and ~80% side overlap."""
    from photobuild import make_dji_jpeg

    folder = tmp_path / "flight"
    folder.mkdir()
    for i in range(12):
        make_dji_jpeg(
            folder / f"DJI_{i:04d}.JPG",
            size=(800, 600),
            lat=22.2820 + (i % 6) * 0.0001,
            lon=91.7790 + (i // 6) * 0.0002,
            altitude=60.0,
        )
    return folder


TEMPLATE = "tests/fixtures/dji_fly_dummy/lito_x1_5wp.kmz"


@pytest.fixture
def plan_form(tmp_path):  # type: ignore[no-untyped-def]
    """A valid Plan a flight form: an 80 x 120 m area near Dhaka, flat ground, Lito X1."""
    from pathlib import Path

    from avispria.app.ui.plan_job import PlanForm

    template = Path(__file__).resolve().parents[2] / TEMPLATE
    return PlanForm(
        centre="23.8103, 90.4125",
        width_m=80.0,
        length_m=120.0,
        template=str(template),
        out_dir=str(tmp_path / "plan"),
        target_value=2.0,
    )


@pytest.fixture
def machine(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """Make the processing screen see a computer of the given size and a fake engine."""
    from avispria.adapters import system_probe
    from avispria.app import process_workflow

    def install(port: int, ram: float = 16.0, swap: float = 4.0) -> None:
        pc = SystemSpec("Windows 11", 12, ram, ram * 0.5, swap, 200.0)
        node = system_probe.LocalNode(f"http://127.0.0.1:{port}", "t", 99, None)
        monkeypatch.setattr(process_workflow.system_probe, "find_local_node", lambda: node)
        monkeypatch.setattr(process_workflow.system_probe, "probe_system", lambda path: pc)
        monkeypatch.setattr(process_workflow, "DEFAULT_POLL_S", 0.05)
        monkeypatch.setattr(doctor_module, "probe_system", lambda workdir: pc)
        engines = [EngineStatus("WebODM", "http://127.0.0.1:29800/", True, "HTTP 200")]
        monkeypatch.setattr(doctor_module, "probe_engines", lambda: engines)
        monkeypatch.setattr(doctor_module, "running_engine_programs", lambda: [])

    return install


@pytest.fixture
def autel_folder(tmp_path):  # type: ignore[no-untyped-def]
    """Twelve photos as an Autel records them: position and height above SEA LEVEL only."""
    from photobuild import make_exif_only_jpeg

    folder = tmp_path / "autel"
    folder.mkdir()
    for i in range(12):
        make_exif_only_jpeg(
            folder / f"MAX_{i:04d}.JPG",
            size=(800, 600),
            lat=47.6435 + (i % 6) * 0.00008,
            lon=16.4763 + (i // 6) * 0.00016,
            altitude_asl=513.1,
        )
    return folder
