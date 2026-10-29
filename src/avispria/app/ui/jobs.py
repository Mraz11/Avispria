# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Running long jobs without freezing the screen, and turning errors into plain sentences."""

from __future__ import annotations

import logging
import queue
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from avispria.adapters.engine import EngineError
from avispria.app.process_workflow import ProcessBlockedError
from avispria.app.workflow import PlanBlockedError
from avispria.core.errors import PlanningError
from avispria.core.geometry import AoiError
from avispria.core.wpml.kmz import KmzError

LOG = logging.getLogger("avispria.ui")
KNOWN = (
    PlanningError,
    AoiError,
    KmzError,
    EngineError,
    PlanBlockedError,
    ProcessBlockedError,
    ValueError,
)


@dataclass(frozen=True)
class JobEvent:
    kind: Literal["step", "info", "warn", "upload", "progress"]
    text: str = ""
    percent: float = 0.0


class QueueReporter:
    """Receives progress from a job running in another thread; the screen reads it later.

    It has the same methods as the command line's reporter, but instead of printing it
    queues events, which is the safe way to pass information between threads.
    """

    def __init__(self) -> None:
        self._events: queue.SimpleQueue[JobEvent] = queue.SimpleQueue()

    def step(self, title: str) -> None:
        self._events.put(JobEvent("step", title))

    def info(self, text: str) -> None:
        self._events.put(JobEvent("info", text))

    def warn(self, text: str) -> None:
        self._events.put(JobEvent("warn", text))

    def upload(self, percent: float) -> None:
        self._events.put(JobEvent("upload", percent=percent))

    def progress(self, percent: float, status: str) -> None:
        self._events.put(JobEvent("progress", status.lower(), percent))

    def drain(self) -> list[JobEvent]:
        out = []
        while True:
            try:
                out.append(self._events.get_nowait())
            except queue.Empty:
                return out


def friendly_error(exc: BaseException) -> str:
    """A sentence a non-expert can act on."""
    if isinstance(exc, KNOWN):
        return str(exc)
    if isinstance(exc, FileNotFoundError):
        return f"A file or folder was not found: {exc.filename or exc}"
    if isinstance(exc, PermissionError):
        return f"Avispria is not allowed to read or write: {exc.filename or exc}"
    if isinstance(exc, OSError):
        return f"A file could not be read or written: {exc}"
    return f"Something unexpected went wrong ({type(exc).__name__}): {exc}"


@dataclass(frozen=True)
class JobResult[T]:
    value: T | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


async def run_job[T](fn: Callable[..., T], *args: Any, **kwargs: Any) -> JobResult[T]:
    """Run ``fn`` in a background thread; errors come back as a message, never as a crash."""
    from nicegui import run

    try:
        return JobResult(value=await run.io_bound(fn, *args, **kwargs))
    except Exception as exc:
        if not isinstance(exc, (*KNOWN, OSError)):
            LOG.error("unexpected failure in a background job", exc_info=exc)
        return JobResult(error=friendly_error(exc))
