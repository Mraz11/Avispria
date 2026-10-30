# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import json
import socket
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import ClassVar

import pytest

from avispria.adapters import system_probe
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


@pytest.fixture
def no_discovery(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests must not depend on whatever happens to run on the developer's machine."""
    from avispria.adapters import system_probe

    monkeypatch.setattr(system_probe, "discover_local_services", lambda: [])


def test_engines_found_and_missing(fake_node: str, no_discovery: None) -> None:
    dead = f"http://127.0.0.1:{_free_port()}/"
    found = probe_engines(webodm_url=fake_node + "/", node_url=fake_node + "/info", timeout=2)
    assert [e.reachable for e in found] == [True, True]
    assert "odx 3.6.2" in found[1].detail
    missing = probe_engines(webodm_url=dead, node_url=dead + "info", timeout=0.5)
    assert [e.reachable for e in missing] == [False, False]
    assert missing[0].detail == "not running"


def test_timeouts_and_refusals_both_mean_not_running() -> None:
    import urllib.error

    from avispria.adapters.system_probe import _reason

    assert _reason(urllib.error.URLError(ConnectionRefusedError())) == "not running"
    assert _reason(urllib.error.URLError(TimeoutError("timed out"))) == "not running"  # Windows
    assert _reason(TimeoutError("timed out")) == "not running"
    assert _reason(urllib.error.URLError("unknown host")) == "unknown host"


class _FakeConn:
    def __init__(self, port: int, status: str = "LISTEN") -> None:
        self.laddr = ("127.0.0.1", port)
        self.status = status


class _FakeProc:
    def __init__(self, pid: int, name: str, exe: str, ports: list[int]) -> None:
        self.info = {"pid": pid, "name": name, "exe": exe}
        self._ports = ports

    def net_connections(self, kind: str = "inet") -> list[_FakeConn]:
        return [_FakeConn(p) for p in self._ports] + [_FakeConn(9, "ESTABLISHED")]


def test_discovers_webodm_ports_from_running_processes(
    monkeypatch: pytest.MonkeyPatch, fake_node: str
) -> None:
    from avispria.adapters import system_probe

    port = int(fake_node.rsplit(":", 1)[1])
    procs = [
        _FakeProc(11, "webodm.exe", r"C:\WebODM\webodm.exe", [port]),
        _FakeProc(12, "chrome.exe", r"C:\Program Files\Chrome\chrome.exe", [9222]),
    ]
    monkeypatch.setattr(system_probe.psutil, "process_iter", lambda attrs=None: iter(procs))
    found = system_probe.discover_local_services()
    assert found == [("webodm.exe", 11, "127.0.0.1", port)]
    engines = system_probe.probe_engines(
        webodm_url="http://127.0.0.1:1/", node_url="http://127.0.0.1:1/info", timeout=1
    )
    discovered = [e for e in engines if e.reachable]
    assert discovered and discovered[0].url.endswith(f":{port}/info")
    assert "odx 3.6.2" in discovered[0].detail


def test_ipv6_loopback_is_probed_with_brackets() -> None:
    from avispria.adapters.system_probe import _local_host

    assert _local_host("::1") == "[::1]"
    assert _local_host("0.0.0.0") == "127.0.0.1"
    assert _local_host("192.168.1.5") == "192.168.1.5"


@pytest.fixture
def redis_like() -> Iterator[int]:
    """A TCP service that answers HTTP with a Redis-style error line."""
    import socketserver

    class Handler(socketserver.BaseRequestHandler):
        def handle(self) -> None:
            self.request.recv(1024)
            self.request.sendall(b"-ERR wrong number of arguments for 'get' command\r\n")

    server = socketserver.TCPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield int(server.server_address[1])
    server.shutdown()
    server.server_close()


def test_non_http_services_never_crash_the_probe(
    monkeypatch: pytest.MonkeyPatch, redis_like: int
) -> None:
    from avispria.adapters import system_probe

    procs = [
        _FakeProc(21, "redis-server.exe", r"C:\WebODM\redis\redis-server.exe", [6379]),
        _FakeProc(22, "webodm.exe", r"C:\WebODM\webodm.exe", [redis_like]),
    ]
    monkeypatch.setattr(system_probe.psutil, "process_iter", lambda attrs=None: iter(procs))
    found = system_probe.discover_local_services()
    assert [f[0] for f in found] == ["webodm.exe"]  # internal Redis skipped by name
    engines = system_probe.probe_engines(
        webodm_url="http://127.0.0.1:1/", node_url="http://127.0.0.1:1/info", timeout=1
    )
    assert not any(e.reachable for e in engines)  # odd reply handled, nothing crashed


class _FakeWebOdm(BaseHTTPRequestHandler):
    nodes: ClassVar[list[dict[str, object]]] = [
        {
            "id": 1,
            "label": "node-odx-1",
            "hostname": "localhost",
            "port": 3000,
            "online": True,
            "engine": "odx",
            "engine_version": "3.6.2",
        }
    ]
    require_login = False

    def do_GET(self) -> None:
        if self.path.startswith("/api/processingnodes/"):
            if self.require_login:
                self.send_response(403)
                self.end_headers()
                self.wfile.write(b'{"detail":"Authentication credentials were not provided."}')
                return
            body = json.dumps(self.nodes).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"<html>WebODM</html>")

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture
def fake_webodm() -> Iterator[tuple[str, type[_FakeWebOdm]]]:
    handler = type("H", (_FakeWebOdm,), {})
    server = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/", handler
    server.shutdown()
    server.server_close()


def test_webodm_api_lists_processing_nodes(fake_webodm: tuple[str, type[_FakeWebOdm]]) -> None:
    from avispria.adapters.system_probe import probe_webodm_api

    url, _ = fake_webodm
    api = probe_webodm_api(url, timeout=2)
    assert api.status == 200 and not api.needs_login
    assert api.nodes[0]["label"] == "node-odx-1" and api.nodes[0]["online"] is True


def test_webodm_api_reports_login_required(fake_webodm: tuple[str, type[_FakeWebOdm]]) -> None:
    from avispria.adapters.system_probe import probe_webodm_api

    url, handler = fake_webodm
    handler.require_login = True
    api = probe_webodm_api(url, timeout=2)
    assert api.needs_login and api.nodes == []


def test_classify_services(fake_node: str, redis_like: int) -> None:
    from avispria.adapters.system_probe import classify_service

    node_port = int(fake_node.rsplit(":", 1)[1])
    assert classify_service("127.0.0.1", node_port, timeout=2).startswith("processing node")
    assert classify_service("127.0.0.1", redis_like, timeout=2) == "not a web service"
    assert classify_service("127.0.0.1", _free_port(), timeout=0.5) == "no answer"


class _TokenNode(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = (
            b'{"engine":"odx","engineVersion":"3.6.2","taskQueueCount":0}'
            if "token=secret" in self.path
            else b'{"error":"Invalid authentication token"}'
        )
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture
def token_node() -> Iterator[int]:
    server = HTTPServer(("127.0.0.1", 0), _TokenNode)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield int(server.server_port)
    server.shutdown()
    server.server_close()


def test_token_protected_node_is_recognised(token_node: int) -> None:
    from avispria.adapters.system_probe import classify_service, probe_node

    assert classify_service("127.0.0.1", token_node, timeout=2) == (
        "processing node (needs its access token)"
    )
    locked = probe_node(f"http://127.0.0.1:{token_node}", timeout=2)
    assert locked.reachable and locked.needs_token
    unlocked = probe_node(f"http://127.0.0.1:{token_node}", token="secret", timeout=2)
    assert not unlocked.needs_token and "odx 3.6.2" in unlocked.detail


def test_the_standard_address_is_tried_when_there_is_no_nodeodx_program(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """WebODM's Docker setup (the usual one on Linux and macOS) has no nodeodx program to find."""
    from fakes.nodeodx import fake_engine

    with fake_engine(None) as (port, _):  # an engine that needs no token, as the Docker one
        found = system_probe.find_default_node(f"http://127.0.0.1:{port}")
    assert found is not None and found.url == f"http://127.0.0.1:{port}"
    assert found.token is None and found.pid == 0 and found.odx_path is None


def test_nothing_at_the_standard_address_means_no_engine() -> None:
    assert (
        system_probe.find_default_node("http://127.0.0.1:9", timeout=0.3) is None
    )  # nothing listens


def test_an_engine_that_needs_a_token_is_not_used_without_one() -> None:
    from fakes.nodeodx import fake_engine

    with fake_engine("s3cret") as (port, _):
        assert system_probe.find_default_node(f"http://127.0.0.1:{port}") is None


def test_find_engine_prefers_the_running_program_and_falls_back_to_the_standard_address(
    monkeypatch,  # type: ignore[no-untyped-def]
) -> None:
    program = system_probe.LocalNode("http://127.0.0.1:29301", "tok", 42, None)
    standard = system_probe.LocalNode("http://localhost:3000", None, 0, None)
    monkeypatch.setattr(system_probe, "find_default_node", lambda *a, **k: standard)
    monkeypatch.setattr(system_probe, "find_local_node", lambda: program)
    assert system_probe.find_engine() is program  # the Windows app's own engine first
    monkeypatch.setattr(system_probe, "find_local_node", lambda: None)
    assert system_probe.find_engine() is standard
    monkeypatch.setattr(system_probe, "find_default_node", lambda *a, **k: None)
    assert system_probe.find_engine() is None
