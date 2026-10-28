# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest

from avispria.adapters.engine import EngineError, connect, describe
from avispria.adapters.system_probe import parse_node_cmdline
from fakes.nodeodx import fake_nodeodx


def test_parse_node_cmdline_from_webodm() -> None:
    args = [
        "nodeodx",
        "--odx_path",
        r"H:\WebODM\resources\app\apps\ODX",
        "--token",
        "abc",
        "--port",
        "29301",
    ]
    parsed = parse_node_cmdline(args)
    assert parsed == (29301, "abc", r"H:\WebODM\resources\app\apps\ODX")
    assert parse_node_cmdline(["nodeodx.exe", "--port=3001", "--token=xyz"]) == (3001, "xyz", None)
    assert parse_node_cmdline(["nodeodx.exe"]) == (3000, None, None)  # NodeODX default port


def test_connect_with_token_and_describe() -> None:
    with fake_nodeodx("s3cret") as port:
        node = connect(f"http://127.0.0.1:{port}", token="s3cret")
        info = describe(node)
    assert (info.engine, info.engine_version, info.api_version) == ("odx", "3.6.2", "2.4.0")
    assert info.cpu_cores == 12 and info.total_memory_gb == pytest.approx(15.83, abs=0.01)
    assert {"dsm", "fast-orthophoto", "pc-quality"} <= info.options


def test_wrong_token_is_a_clear_error() -> None:
    with fake_nodeodx("s3cret") as port, pytest.raises(EngineError, match="token"):
        describe(connect(f"http://127.0.0.1:{port}", token="wrong"))


def test_unreachable_engine_is_a_clear_error() -> None:
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        free = s.getsockname()[1]
    with pytest.raises(EngineError, match="cannot reach"):
        describe(connect(f"http://127.0.0.1:{free}", token=None, timeout=2))


def _photos(tmp_path, n=6):  # type: ignore[no-untyped-def]
    files = []
    for i in range(n):
        f = tmp_path / f"DJI_{i:04d}.JPG"
        f.write_bytes(b"\xff\xd8 fake jpeg " + bytes([i]))
        files.append(f)
    return files


def test_full_task_lifecycle(tmp_path) -> None:  # type: ignore[no-untyped-def]
    import zipfile

    from avispria.adapters.engine import download_results, submit, wait
    from fakes.nodeodx import fake_engine

    uploads: list[float] = []
    statuses: list[tuple[float, str]] = []
    with fake_engine("s3cret") as (port, state):
        node = connect(f"http://127.0.0.1:{port}", token="s3cret")
        task = submit(
            node, _photos(tmp_path), {"dsm": True, "pc-quality": "medium"}, "test", uploads.append
        )
        outcome = wait(task, lambda p, s: statuses.append((p, s)), interval=0.05)
        zip_path = download_results(task, tmp_path / "out")
    assert state.uploads == 6
    assert {o["name"]: o["value"] for o in state.options} == {"dsm": True, "pc-quality": "medium"}
    assert uploads and uploads[-1] == pytest.approx(100.0)
    assert statuses[0][1] == "RUNNING" and statuses[-1][1] == "COMPLETED"
    assert outcome.completed and outcome.processing_s == pytest.approx(61.0)
    assert "odm_orthophoto/odm_orthophoto.tif" in zipfile.ZipFile(zip_path).namelist()


def test_failed_task_returns_error_and_log(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from avispria.adapters.engine import submit, wait
    from fakes.nodeodx import fake_engine

    with fake_engine("s3cret", outcome="fail") as (port, _):
        node = connect(f"http://127.0.0.1:{port}", token="s3cret")
        outcome = wait(submit(node, _photos(tmp_path), {}, "t"), interval=0.05)
    assert not outcome.completed and outcome.status == "FAILED"
    assert "exited with code 1" in outcome.error
    assert any("not enough memory" in line for line in outcome.log_tail)
