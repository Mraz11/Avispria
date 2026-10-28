# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""`avispria doctor`: can this computer process these photos, and what if not?"""

from __future__ import annotations

import statistics
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from avispria.adapters.photos import photo_files, scan_photos
from avispria.adapters.system_probe import (
    EngineStatus,
    docker_available,
    probe_engines,
    probe_system,
)
from avispria.core.feasibility import Assessment, JobSpec, SystemSpec, assess

GB = 1024**3


@dataclass(frozen=True)
class DoctorReport:
    system: SystemSpec
    engines: list[EngineStatus]
    docker: bool
    job: JobSpec | None
    assessment: Assessment | None
    unreadable: int


def job_from_folder(folder: Path, *, recursive: bool = False) -> tuple[JobSpec | None, int]:
    """Photo count, typical megapixels and total size; also the unreadable-file count."""
    records, skipped = scan_photos(folder, recursive=recursive)
    sizes = [r.width_px * r.height_px for r in records if r.width_px and r.height_px]
    if not records or not sizes:
        return None, len(skipped)
    total = sum(p.stat().st_size for p in photo_files(folder, recursive=recursive))
    job = JobSpec(
        photos=len(records), native_mp=statistics.median(sizes) / 1e6, input_gb=total / GB
    )
    return job, len(skipped)


def run_doctor(
    workdir: Path,
    folder: Path | None = None,
    *,
    recursive: bool = False,
    processing_mp: float | None = None,
    webodm_url: str | None = None,
    system_probe: Callable[[Path], SystemSpec] | None = None,
    engine_probe: Callable[[], list[EngineStatus]] | None = None,
) -> DoctorReport:
    system = (system_probe or probe_system)(workdir)
    job, unreadable = (None, 0) if folder is None else job_from_folder(folder, recursive=recursive)
    assessment = None if job is None else assess(system, job, processing_mp)
    if engine_probe is not None:
        engines = engine_probe()
    elif webodm_url:
        base = webodm_url.rstrip("/")
        engines = probe_engines(webodm_url=base + "/", node_url=base + "/info")
    else:
        engines = probe_engines()
    return DoctorReport(system, engines, docker_available(), job, assessment, unreadable)
