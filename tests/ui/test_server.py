# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Start the real server (not a simulation) and use it the way a browser would."""

import os
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import psutil
import pytest

from avispria.app.ui.app import HOST, find_free_port

START = "from avispria.app.cli import app; app()"


@pytest.fixture
def server(tmp_path: Path) -> Iterator[tuple[int, subprocess.Popen[bytes]]]:
    port = find_free_port(18080)
    # NiceGUI switches into its own test mode when it sees pytest's variable: a real user's
    # environment never has it, so the program under test must not inherit it
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTEST_", "NICEGUI_"))}
    proc = subprocess.Popen(
        [sys.executable, "-c", START, "ui", "--port", str(port), "--no-browser"],
        cwd=tmp_path,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                pytest.fail(f"the server stopped at start-up (exit code {proc.returncode})")
            try:
                if httpx.get(f"http://{HOST}:{port}/", timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.3)
        else:
            pytest.fail("the server did not start in time")
        yield port, proc
    finally:
        proc.terminate()
        try:
            proc.wait(15)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_the_real_server_serves_every_screen(server: tuple[int, subprocess.Popen[bytes]]) -> None:
    port, _ = server
    for path in ("/", "/check", "/plan", "/process"):
        reply = httpx.get(f"http://{HOST}:{port}{path}", timeout=10)
        assert reply.status_code == 200 and "Avispria" in reply.text, path
    assert httpx.get(f"http://{HOST}:{port}/no-such-screen", timeout=10).status_code == 404


def test_the_real_server_listens_on_this_computer_only(
    server: tuple[int, subprocess.Popen[bytes]],
) -> None:
    port, proc = server
    listening = [
        c.laddr
        for c in psutil.Process(proc.pid).net_connections(kind="inet")
        if c.status == psutil.CONN_LISTEN and c.laddr.port == port
    ]
    assert listening, "the server is not listening"
    assert {addr.ip for addr in listening} == {
        HOST
    }  # never 0.0.0.0: not reachable from the network
