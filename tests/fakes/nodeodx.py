# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A small fake NodeODX server for tests (token-protected like WebODM's engine)."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

INFO = {
    "version": "2.4.0",
    "taskQueueCount": 0,
    "totalMemory": 17_000_000_000,
    "availableMemory": 6_000_000_000,
    "cpuCores": 12,
    "maxImages": None,
    "maxParallelTasks": 2,
    "engine": "odx",
    "engineVersion": "3.6.2",
    "odmVersion": "3.6.2",
}
OPTIONS = [
    {"name": "dsm", "type": "bool", "value": "false", "domain": "bool", "help": "Build a DSM"},
    {"name": "fast-orthophoto", "type": "bool", "value": "false", "domain": "bool", "help": ""},
    {
        "name": "pc-quality",
        "type": "enum",
        "value": "medium",
        "domain": ["ultra", "high", "medium", "low", "lowest"],
        "help": "",
    },
    {
        "name": "feature-quality",
        "type": "enum",
        "value": "high",
        "domain": ["ultra", "high", "medium", "low", "lowest"],
        "help": "",
    },
    {
        "name": "orthophoto-resolution",
        "type": "float",
        "value": "5",
        "domain": "float > 0",
        "help": "",
    },
    {"name": "rolling-shutter", "type": "bool", "value": "false", "domain": "bool", "help": ""},
]


def _handler(token: str) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def _send(self, payload: object) -> None:
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            url = urlparse(self.path)
            if parse_qs(url.query).get("token", [""])[0] != token:
                self._send({"error": "Invalid authentication token: token does not match."})
                return
            if url.path == "/info":
                self._send(INFO)
            elif url.path == "/options":
                self._send(OPTIONS)
            else:
                self._send({"error": "not found"})

        def log_message(self, *args: object) -> None:
            pass

    return Handler


@contextmanager
def fake_nodeodx(token: str = "s3cret") -> Iterator[int]:
    server = HTTPServer(("127.0.0.1", 0), _handler(token))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield int(server.server_port)
    finally:
        server.shutdown()
        server.server_close()
