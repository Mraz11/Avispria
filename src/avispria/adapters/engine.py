# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Talk to a NodeODX processing engine through PyODX (the WebODM project's client)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode, urlparse

from pyodx import Node, Task
from pyodx import exceptions as odx_errors
from pyodx.types import TaskStatus

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


@dataclass(frozen=True)
class TaskOutcome:
    uuid: str
    completed: bool
    status: str
    error: str
    processing_s: float
    log_tail: list[str]


def submit(
    node: Node,
    files: list[Path],
    options: dict[str, object],
    name: str,
    on_upload: Callable[[float], None] | None = None,
) -> Task:
    """Create a task and upload ``files``; ``on_upload`` gets 0-100 percentages."""
    try:
        return node.create_task(
            [str(f) for f in files],
            options,
            name=name,
            progress_callback=on_upload,
            parallel_uploads=4,
        )
    except (odx_errors.GenericError, OSError) as exc:
        raise _friendly(exc, node) from exc


def wait(
    task: Task,
    on_status: Callable[[float, str], None] | None = None,
    interval: float = 3.0,
) -> TaskOutcome:
    """Block until the task ends; ``on_status`` gets (progress %, status name)."""

    def report(info: object) -> None:
        if on_status is not None:
            status = getattr(info, "status", None)
            on_status(float(getattr(info, "progress", 0) or 0), getattr(status, "name", "?"))

    try:
        task.wait_for_completion(status_callback=report, interval=interval)
    except odx_errors.TaskFailedError:
        pass
    except (odx_errors.GenericError, OSError) as exc:
        raise _friendly(exc, task.node) from exc
    info = task.info()
    completed = info.status == TaskStatus.COMPLETED
    tail: list[str] = []
    if not completed:
        try:
            tail = [str(line) for line in task.output(-40)]
        except (odx_errors.GenericError, OSError):
            tail = []
    return TaskOutcome(
        uuid=task.uuid,
        completed=completed,
        status=info.status.name,
        error=str(info.last_error or ""),
        processing_s=max(0.0, float(info.processing_time or 0) / 1000.0),
        log_tail=tail,
    )


def download_results(task: Task, destination: Path) -> Path:
    """Download all outputs as one zip (the archive WebODM's Import button accepts)."""
    destination.mkdir(parents=True, exist_ok=True)
    try:
        return Path(task.download_zip(str(destination)))
    except (odx_errors.GenericError, OSError) as exc:
        raise _friendly(exc, task.node) from exc
