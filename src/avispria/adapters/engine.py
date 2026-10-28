# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Talk to a NodeODX processing engine through PyODX (the WebODM project's client)."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode, urlparse

from pyodx import Node
from pyodx import exceptions as odx_errors

GB = 1024**3


class EngineError(RuntimeError):
    """The engine cannot be reached or refused the request; message is user-facing."""


@dataclass(frozen=True)
class EngineInfo:
    engine: str
    engine_version: str
    api_version: str
    cpu_cores: int | None
    total_memory_gb: float | None
    available_memory_gb: float | None
    queue: int
    max_images: int | None
    options: frozenset[str]


def connect(base_url: str, token: str | None, timeout: float = 30) -> Node:
    """A PyODX Node for ``base_url`` (http://host:port), authenticated with ``token``."""
    parsed = urlparse(base_url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise EngineError(f"not an engine address: {base_url!r} (expected http://host:port)")
    query = "?" + urlencode({"token": token}) if token else ""
    return Node.from_url(f"{parsed.scheme}://{parsed.netloc}{query}", timeout=int(max(1, timeout)))


def _friendly(exc: Exception, node: Node) -> EngineError:
    where = f"{node.host}:{node.port}"
    if isinstance(exc, odx_errors.NodeConnectionError):
        return EngineError(f"cannot reach the processing engine at {where}; is WebODM running?")
    text = str(exc)
    if "token" in text.lower():
        return EngineError(f"the engine at {where} rejected the access token")
    return EngineError(f"the engine at {where} answered with an error: {text}")


def describe(node: Node) -> EngineInfo:
    """Engine identity, resources, queue and the option names it accepts."""
    try:
        info = node.info()
        options = node.options()
    except (odx_errors.GenericError, OSError) as exc:
        raise _friendly(exc, node) from exc
    total = getattr(info, "total_memory", None)
    available = getattr(info, "available_memory", None)
    return EngineInfo(
        engine=str(getattr(info, "engine", "") or "unknown"),
        engine_version=str(getattr(info, "engine_version", "") or getattr(info, "odm_version", "")),
        api_version=str(getattr(info, "version", "")),
        cpu_cores=getattr(info, "cpu_cores", None),
        total_memory_gb=None if total is None else total / GB,
        available_memory_gb=None if available is None else available / GB,
        queue=int(getattr(info, "task_queue_count", 0) or 0),
        max_images=getattr(info, "max_images", None),
        options=frozenset(o.name for o in options),
    )
