# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read this computer's resources and look for a local photogrammetry engine."""

from __future__ import annotations

import json
import os
import platform
import shutil
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import psutil

from avispria.core.feasibility import SystemSpec

GB = 1024**3
WEBODM_URL = "http://localhost:8000/"
NODEODX_URL = "http://localhost:3000/info"


@dataclass(frozen=True)
class EngineStatus:
    name: str
    url: str
    reachable: bool
    detail: str


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


def probe_engines(
    webodm_url: str = WEBODM_URL, node_url: str = NODEODX_URL, timeout: float = 1.5
) -> list[EngineStatus]:
    """Is WebODM (web app) or a NodeODX/NodeODM processing node answering locally?"""
    out: list[EngineStatus] = []
    try:
        status, _ = _get(webodm_url, timeout)
        out.append(EngineStatus("WebODM", webodm_url, status < 500, f"HTTP {status}"))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        out.append(EngineStatus("WebODM", webodm_url, False, _reason(exc)))
    try:
        status, body = _get(node_url, timeout)
        info = json.loads(body.decode("utf-8", "replace"))
        engine = f"{info.get('engine', 'engine')} {info.get('engineVersion', '')}".strip()
        detail = f"{engine}, {info.get('taskQueueCount', 0)} task(s) queued"
        out.append(EngineStatus("Processing node", node_url, status == 200, detail))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        out.append(EngineStatus("Processing node", node_url, False, _reason(exc)))
    return out


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
