# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import json
import socket
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from avispria.adapters.system_probe import probe_engines, probe_system


class _FakeNode(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = json.dumps({"engine": "odx", "engineVersion": "3.6.2", "taskQueueCount": 1}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture
def fake_node() -> Iterator[str]:
    server = HTTPServer(("127.0.0.1", 0), _FakeNode)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def test_probe_system_reads_real_resources(tmp_path: Path) -> None:
    spec = probe_system(tmp_path)
    assert spec.ram_total_gb > 0.5 and spec.cpu_logical >= 1
    assert spec.disk_free_gb > 0 and spec.ram_available_gb <= spec.ram_total_gb
    assert spec.os_name


def test_engines_found_and_missing(fake_node: str) -> None:
    dead = f"http://127.0.0.1:{_free_port()}/"
    found = probe_engines(webodm_url=fake_node + "/", node_url=fake_node + "/info", timeout=2)
    assert [e.reachable for e in found] == [True, True]
    assert "odx 3.6.2" in found[1].detail
    missing = probe_engines(webodm_url=dead, node_url=dead + "info", timeout=0.5)
    assert [e.reachable for e in missing] == [False, False]
    assert missing[0].detail == "not running"
