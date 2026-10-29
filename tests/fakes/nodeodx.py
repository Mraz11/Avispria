# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A small fake NodeODX server for tests (token-protected like WebODM's engine)."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler
from pathlib import Path
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


def _flat_dsm(elevation: float) -> bytes:
    """A small WGS 84 GeoTIFF of constant elevation around the process-test photos."""
    import numpy as np
    from rasterio.io import MemoryFile
    from rasterio.transform import from_origin

    with MemoryFile() as mem:
        with mem.open(
            driver="GTiff",
            height=100,
            width=100,
            count=1,
            dtype="float32",
            crs="EPSG:4326",
            transform=from_origin(91.77, 22.29, 0.0004, 0.0004),
            nodata=-9999.0,
        ) as dst:
            dst.write(np.full((100, 100), elevation, "float32"), 1)
        return mem.read()


class FakeState:
    """What the fake engine received and how the task should end."""

    def __init__(
        self, token: str, outcome: str = "complete", dsm_elevation: float | None = None
    ) -> None:
        self.token = token
        self.dsm_elevation = dsm_elevation
        self.outcome = outcome  # "complete" or "fail"
        self.options: list[dict[str, object]] = []
        self.uploads = 0
        self.polls = 0
        self.cancelled = False
        self.uuid = "4f1c-test-task"


def results_zip(dsm_elevation: float | None = None) -> bytes:
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("odm_orthophoto/odm_orthophoto.tif", b"fake orthophoto")
        if dsm_elevation is None:
            z.writestr("odm_dem/dsm.tif", b"fake dsm")  # not a raster: must not break processing
        z.writestr("odm_georeferencing/odm_georeferenced_model.laz", b"fake laz")
        z.writestr("log.json", b"{}")
        fixture = (
            Path(__file__).resolve().parents[1]
            / "fixtures"
            / "odx"
            / "stats_brighton_standard.json"
        )
        z.writestr("odm_report/stats.json", fixture.read_bytes())
        if dsm_elevation is not None:
            z.writestr("odm_dem/dsm.tif", _flat_dsm(dsm_elevation))
    return buf.getvalue()


def _handler(state: FakeState) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def _send(self, payload: object, raw: bytes | None = None) -> None:
            body = raw if raw is not None else json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/zip" if raw else "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _authorised(self) -> bool:
            query = parse_qs(urlparse(self.path).query)
            if query.get("token", [""])[0] != state.token:
                self._send({"error": "Invalid authentication token: token does not match."})
                return False
            return True

        def do_GET(self) -> None:
            if not self._authorised():
                return
            path = urlparse(self.path).path
            if path == "/info":
                self._send(INFO)
            elif path == "/options":
                self._send(OPTIONS)
            elif path == f"/task/{state.uuid}/info":
                state.polls += 1
                done = state.polls >= 2 and state.outcome != "hang"
                code = 20 if not done else (40 if state.outcome == "complete" else 30)
                if state.cancelled:
                    done, code = True, 50
                status: dict[str, object] = {"code": code}
                if done and state.outcome == "fail":
                    status["errorMessage"] = "Process exited with code 1"
                self._send(
                    {
                        "uuid": state.uuid,
                        "name": "test",
                        "dateCreated": 1_793_200_000_000,
                        "processingTime": 61_000 if done else 30_000,
                        "status": status,
                        "options": state.options,
                        "imagesCount": state.uploads,
                        "progress": 100 if done else 40,
                    }
                )
            elif path == f"/task/{state.uuid}/output":
                self._send(
                    [
                        "[INFO] running sfm",
                        "[ERROR] not enough memory" if state.outcome == "fail" else "[INFO] done",
                    ]
                )
            elif path == f"/task/{state.uuid}/download/all.zip":
                self._send(None, raw=results_zip(state.dsm_elevation))
            else:
                self._send({"error": "not found"})

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            if not self._authorised():
                return
            path = urlparse(self.path).path
            if path == "/task/new/init":
                marker = body.find(b'name="options"')
                if marker >= 0:
                    start = body.find(b"\r\n\r\n", marker) + 4
                    end = body.find(b"\r\n--", start)
                    state.options = json.loads(body[start:end].decode())
                self._send({"uuid": state.uuid})
            elif path == f"/task/new/upload/{state.uuid}":
                state.uploads += body.count(b'name="images"')
                self._send({"success": True})
            elif path == f"/task/new/commit/{state.uuid}":
                self._send({"uuid": state.uuid})
            elif path == "/task/cancel":
                state.cancelled = True
                self._send({"success": True})
            else:
                self._send({"error": "not found"})

        def log_message(self, *args: object) -> None:
            pass

    return Handler


@contextmanager
def fake_nodeodx(token: str = "s3cret", outcome: str = "complete") -> Iterator[int]:
    with fake_engine(token, outcome) as (port, _state):
        yield port


@contextmanager
def fake_engine(
    token: str = "s3cret", outcome: str = "complete", dsm_elevation: float | None = None
) -> Iterator[tuple[int, FakeState]]:
    from http.server import ThreadingHTTPServer

    state = FakeState(token, outcome, dsm_elevation)
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield int(server.server_port), state
    finally:
        server.shutdown()
        server.server_close()
