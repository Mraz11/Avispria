# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read this computer's resources and look for a local photogrammetry engine."""

from __future__ import annotations

import http.client
import json
import os
import platform
import shutil
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import psutil

from avispria.core.feasibility import SystemSpec

GB = 1024**3
WEBODM_URL = "http://localhost:8000/"
NODEODX_URL = "http://localhost:3000/info"
# programs that belong to a local photogrammetry stack (matched case-insensitively
# against the process name and executable path)
ENGINE_MARKERS = ("webodm", "nodeodx", "nodeodm", "clusterodx", "odx")
# WebODM bundles internal services that do not speak HTTP; never probe them
NON_HTTP_SERVICES = ("redis", "postgres", "pg_ctl", "celery", "nginx-cache")
# anything a non-HTTP or half-broken service can throw at an HTTP probe
PROBE_ERRORS = (urllib.error.URLError, http.client.HTTPException, OSError, ValueError)


@dataclass(frozen=True)
class EngineStatus:
    name: str
    url: str
    reachable: bool
    detail: str
    needs_token: bool = False


def _os_name() -> str:
    name, release = platform.system(), platform.release()
    if name == "Windows":
        return f"Windows {release}"
    if name == "Darwin":
        return f"macOS {platform.mac_ver()[0] or release}"
    return f"{name} {release}"


def probe_system(workdir: Path) -> SystemSpec:
    """Resources relevant to processing, with free disk measured at ``workdir``."""
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    target = workdir if workdir.exists() else workdir.anchor or Path.cwd()
    return SystemSpec(
        os_name=_os_name(),
        cpu_logical=os.cpu_count() or 1,
        ram_total_gb=mem.total / GB,
        ram_available_gb=mem.available / GB,
        swap_total_gb=swap.total / GB,
        disk_free_gb=shutil.disk_usage(target).free / GB,
    )


def _get(url: str, timeout: float) -> tuple[int, bytes]:
    request = urllib.request.Request(url, headers={"User-Agent": "avispria-doctor"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status, response.read(64 * 1024)


def _local_host(ip: str) -> str:
    if ip in ("", "0.0.0.0", "::", "127.0.0.1"):
        return "127.0.0.1"
    return f"[{ip}]" if ":" in ip else ip


def discover_local_services() -> list[tuple[str, int, str, int]]:
    """(process name, pid, host, port) for running WebODM/NodeODX-like programs.

    Lets `doctor` find the native WebODM app whatever port it chose, instead of
    assuming the Docker default. Processes we may not inspect are skipped.
    """
    found: set[tuple[str, int, str, int]] = set()
    for proc in psutil.process_iter(attrs=["pid", "name", "exe"]):
        info = proc.info
        label = f"{info.get('name') or ''} {info.get('exe') or ''}".lower()
        if not any(marker in label for marker in ENGINE_MARKERS):
            continue
        if any(skip in label for skip in NON_HTTP_SERVICES):
            continue
        try:
            conns = proc.net_connections(kind="inet")
        except (psutil.Error, OSError):
            continue
        for conn in conns:
            if getattr(conn, "status", "") == "LISTEN" and conn.laddr:
                host = _local_host(str(conn.laddr[0]))
                found.add(
                    (str(info.get("name") or "?"), int(info["pid"]), host, int(conn.laddr[1]))
                )
    return sorted(found, key=lambda item: (item[3], item[1]))


DEFAULT_NODE_PORT = 3000  # NodeODX default when no --port is given


@dataclass(frozen=True)
class LocalNode:
    url: str
    token: str | None  # held in memory only; never printed or stored
    pid: int
    odx_path: str | None


DOCKER_NODE_URL = "http://localhost:3000"  # NodeODX's standard address (WebODM's Docker setup)


def find_default_node(url: str = DOCKER_NODE_URL, timeout: float = 1.5) -> LocalNode | None:
    """NodeODX answering at its standard address, if it needs no token.

    WebODM's Docker setup, the usual one on Linux and macOS, runs the engine in a container, so
    there is no ``nodeodx`` program to find; it listens on port 3000 without a token.
    """
    try:
        status = _probe_node(url.rstrip("/") + "/info", timeout)
    except PROBE_ERRORS:
        return None
    if not status.reachable or status.needs_token:
        return None
    return LocalNode(url, None, 0, None)


def find_engine() -> LocalNode | None:
    """The engine WebODM runs here: the Windows app's own program, else the standard address."""
    return find_local_node() or find_default_node()


def parse_node_cmdline(args: list[str]) -> tuple[int, str | None, str | None]:
    """(port, token, odx_path) from a NodeODX command line (`--x v` or `--x=v`)."""
    values: dict[str, str] = {}
    i = 0
    while i < len(args):
        arg = args[i]
        if arg.startswith("--"):
            key, sep, value = arg[2:].partition("=")
            if not sep and i + 1 < len(args) and not args[i + 1].startswith("--"):
                value = args[i + 1]
                i += 1
            values[key] = value
        i += 1
    try:
        port = int(values.get("port", DEFAULT_NODE_PORT))
    except ValueError:
        port = DEFAULT_NODE_PORT
    return port, values.get("token") or None, values.get("odx_path") or None


def find_local_node() -> LocalNode | None:
    """The NodeODX engine running on this computer (e.g. started by WebODM), if any.

    The token is read from the engine's own command line, which WebODM sets when it
    starts the engine. It is kept in memory for this run only.
    """
    for proc in psutil.process_iter(attrs=["pid", "name"]):
        name = str(proc.info.get("name") or "").lower()
        if not name.startswith("nodeodx"):
            continue
        try:
            cmdline = proc.cmdline()
        except (psutil.Error, OSError):
            continue
        port, token, odx_path = parse_node_cmdline(cmdline[1:])
        return LocalNode(f"http://127.0.0.1:{port}", token, int(proc.info["pid"]), odx_path)
    return None


def _probe_node(url: str, timeout: float) -> EngineStatus:
    status, body = _get(url, timeout)
    info = json.loads(body.decode("utf-8", "replace"))
    if isinstance(info, dict) and "token" in str(info.get("error", "")).lower():
        # NodeODX started by WebODM is protected by an access token
        return EngineStatus("Processing node", url, True, "needs its access token", True)
    if not isinstance(info, dict) or "taskQueueCount" not in info:
        raise ValueError("not a processing node")
    engine = f"{info.get('engine', 'engine')} {info.get('engineVersion', '')}".strip()
    detail = f"{engine}, {info.get('taskQueueCount', 0)} task(s) queued"
    return EngineStatus("Processing node", url, status == 200, detail)


def probe_engines(
    webodm_url: str = WEBODM_URL, node_url: str = NODEODX_URL, timeout: float = 1.5
) -> list[EngineStatus]:
    """WebODM (web app) and processing nodes answering locally.

    Checks the usual addresses first, then every port opened by a running
    WebODM/NodeODX program (the native Windows app may use its own port).
    """
    out: list[EngineStatus] = []
    try:
        status, _ = _get(webodm_url, timeout)
        out.append(EngineStatus("WebODM", webodm_url, status < 500, f"HTTP {status}"))
    except PROBE_ERRORS as exc:
        out.append(EngineStatus("WebODM", webodm_url, False, _reason(exc)))
    try:
        out.append(_probe_node(node_url, timeout))
    except PROBE_ERRORS as exc:
        out.append(EngineStatus("Processing node", node_url, False, _reason(exc)))
    known = {webodm_url, node_url}
    for name, _pid, host, port in discover_local_services():
        base = f"http://{host}:{port}"
        try:
            node = _probe_node(base + "/info", timeout)
            if node.url not in known:
                out.insert(0, node)
            continue
        except PROBE_ERRORS:
            pass
        try:
            status, _ = _get(base + "/", timeout)
        except PROBE_ERRORS:
            continue
        if status < 500 and base + "/" not in known:
            out.insert(0, EngineStatus("WebODM", base + "/", True, f"{name}, HTTP {status}"))
    return out


@dataclass(frozen=True)
class WebOdmApi:
    status: int | None
    needs_login: bool
    nodes: list[dict[str, object]]
    error: str | None


def probe_webodm_api(base_url: str, timeout: float = 2.0) -> WebOdmApi:
    """Ask WebODM for its processing nodes (tells us whether the API needs a login)."""
    url = base_url.rstrip("/") + "/api/processingnodes/"
    request = urllib.request.Request(url, headers={"User-Agent": "avispria-doctor"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read(256 * 1024).decode("utf-8", "replace"))
            nodes = [n for n in data if isinstance(n, dict)] if isinstance(data, list) else []
            return WebOdmApi(response.status, False, nodes, None)
    except urllib.error.HTTPError as exc:
        return WebOdmApi(exc.code, exc.code in (401, 403), [], None)
    except PROBE_ERRORS as exc:
        return WebOdmApi(None, False, [], _reason(exc))


def probe_node(base_url: str, token: str | None = None, timeout: float = 2.0) -> EngineStatus:
    """Status of a NodeODX/NodeODM node at ``base_url``, optionally with its token."""
    url = base_url.rstrip("/") + "/info"
    if token:
        url += "?" + urllib.parse.urlencode({"token": token})
    return _probe_node(url, timeout)


def classify_service(host: str, port: int, timeout: float = 1.5) -> str:
    """Plain description of what answers on host:port."""
    base = f"http://{host}:{port}"
    try:
        node = _probe_node(base + "/info", timeout)
        return f"processing node ({node.detail})"  # includes "needs its access token"
    except PROBE_ERRORS:
        pass
    try:
        status, _ = _get(base + "/", timeout)
        return f"web page (HTTP {status})"
    except urllib.error.HTTPError as exc:
        return f"web page (HTTP {exc.code})"
    except (http.client.HTTPException, ValueError):
        return "not a web service"
    except PROBE_ERRORS as exc:
        reason = _reason(exc)
        return "no answer" if reason == "not running" else "not a web service"


def _reason(exc: Exception) -> str:
    """Plain-language reason a local engine did not answer.

    Linux/macOS refuse a closed local port at once; Windows retries for about two
    seconds, so a short probe times out instead. For a local engine both mean the
    same thing: nothing is running there.
    """
    reason = getattr(exc, "reason", exc)
    if isinstance(reason, ConnectionRefusedError | TimeoutError):
        return "not running"
    return str(reason)


def docker_available() -> bool:
    return shutil.which("docker") is not None
