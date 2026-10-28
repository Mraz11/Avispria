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
