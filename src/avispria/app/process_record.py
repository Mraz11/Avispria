# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The provenance record of a processing run: what was done, with what, and what came out."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

from avispria.adapters.engine import EngineInfo, TaskOutcome
from avispria.core.capture import CaptureReport
from avispria.core.feasibility import Assessment, SystemSpec
from avispria.core.processing import ProcessingOptions
from avispria.core.quality import ReconstructionSummary
from avispria.core.safety import Issue
from avispria.core.version import __version__


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_provenance(
    *,
    out_dir: Path,
    started: float,
    name: str,
    preset: str,
    resize_mp: float | None,
    outcome: TaskOutcome,
    info: EngineInfo,
    opts: ProcessingOptions,
    system: SystemSpec,
    assessment: Assessment,
    reconstruction: ReconstructionSummary | None,
    qa: CaptureReport,
    qa_issues: Sequence[Issue],
    files: Sequence[Path],
    outputs: Sequence[Path],
) -> Path:
    """Write ``avispria_provenance.json`` (checksums of every input and output; no secrets)."""
    record = {
        "tool": {"name": "avispria", "version": __version__},
        "started": started,
        "finished": time.time(),
        "status": outcome.status,
        "error": outcome.error,
        "log_tail": outcome.log_tail,
        "engine": asdict(info) | {"options": sorted(info.options)},
        "task": {"uuid": outcome.uuid, "processing_s": outcome.processing_s, "name": name},
        "preset": preset,
        "options_sent": opts.options,
        "options_dropped": opts.dropped,
        "resize_mp": resize_mp,
        "system": asdict(system),
        "assessment": {"verdict": assessment.verdict, "ram_gb": assessment.ram_gb},
        "reconstruction": None
        if reconstruction is None
        else asdict(reconstruction)
        | {"points_per_m2": reconstruction.points_per_m2, "gsd_ratio": reconstruction.gsd_ratio},
        "capture_qa": {
            "advisory": True,
            "stats": qa.stats,
            "issues": [asdict(i) for i in qa_issues],
        },
        "inputs": [
            {"file": f.name, "bytes": f.stat().st_size, "sha256": sha256_of(f)} for f in files
        ],
        "outputs": [
            {
                "file": p.relative_to(out_dir).as_posix(),
                "bytes": p.stat().st_size,
                "sha256": sha256_of(p),
            }
            for p in outputs
        ],
    }
    path = out_dir / "avispria_provenance.json"
    path.write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
    return path
