# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""`avispria process`: photo folder -> checked -> engine -> results + provenance."""

from __future__ import annotations

import re
import shutil
import statistics
import threading
import time
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol

from avispria.adapters import system_probe
from avispria.adapters.engine import (
    EngineInfo,
    TaskOutcome,
    connect,
    describe,
    download_results,
    submit,
    wait,
)
from avispria.adapters.photos import photo_files, scan_photos
from avispria.adapters.resize import resize_photo
from avispria.app.capture_workflow import camera_chooser
from avispria.app.process_record import write_provenance
from avispria.app.result_quality import read_stats, report_quality, summarize_result
from avispria.core.capture import analyse_capture
from avispria.core.feasibility import Assessment, JobSpec, SystemSpec, assess, gb
from avispria.core.processing import (
    DEFAULT_RESIZE_MP,
    MIN_PHOTOS,
    PRESETS,
    PresetName,
    build_options,
    effective_gsd_cm,
)
from avispria.core.quality import ReconstructionSummary
from avispria.core.safety import Issue

GB = 1024**3
UPLOAD_DIR = ".avispria-upload"
DEFAULT_POLL_S = 3.0
GENERIC_FOLDER = re.compile(r"^(images?|photos?|pictures?|imgs?|dcim|\d{3}media)$", re.IGNORECASE)


def task_name(folder: Path) -> str:
    """Folder name, or its parent's when the folder has a generic name like 'images'."""
    path = folder.resolve()
    for part in (path, *path.parents):
        if part.name and not GENERIC_FOLDER.match(part.name):
            return part.name
    return "avispria"


class Reporter(Protocol):
    def step(self, title: str) -> None: ...
    def info(self, text: str) -> None: ...
    def warn(self, text: str) -> None: ...
    def upload(self, percent: float) -> None: ...
    def progress(self, percent: float, status: str) -> None: ...


class ProcessBlockedError(RuntimeError):
    """Processing was not started; ``assessment`` holds alternatives if it is a capacity issue."""

    def __init__(self, reason: str, assessment: Assessment | None = None) -> None:
        super().__init__(reason)
        self.assessment = assessment


@dataclass(frozen=True)
class ProcessRequest:
    folder: Path
    out_dir: Path
    preset: PresetName = "standard"
    recursive: bool = False
    resize_mp: float | None = DEFAULT_RESIZE_MP
    force: bool = False
    url: str | None = None
    token: str | None = None
    name: str | None = None
    poll_s: float | None = None  # None: DEFAULT_POLL_S
    cancel: threading.Event | None = None  # set it to stop a running job


@dataclass(frozen=True)
class ProcessOutcome:
    completed: bool
    task: TaskOutcome
    zip_path: Path | None
    results_dir: Path | None
    provenance_path: Path


def _extract(zip_path: Path, dest: Path) -> list[Path]:
    dest.mkdir(parents=True, exist_ok=True)
    root = dest.resolve()
    out: list[Path] = []
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            target = (dest / member.filename).resolve()
            if not target.is_relative_to(root):
                raise ProcessBlockedError(f"unsafe path in results archive: {member.filename}")
            if member.is_dir():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            out.append(target)
    return out


def _engine(
    req: ProcessRequest, rep: Reporter, find_node: Callable[[], object]
) -> tuple[object, EngineInfo]:
    url, token = req.url, req.token
    if url is None:
        local = find_node()
        if local is None:
            raise ProcessBlockedError("no processing engine is running; start WebODM and try again")
        url, token = local.url, token or local.token  # type: ignore[attr-defined]
        rep.info(f"using WebODM's local engine at {url} (token read from the running engine)")
    node = connect(url, token)
    info = describe(node)
    rep.info(f"{info.engine} {info.engine_version}, {info.cpu_cores or '?'} cores")
    if info.queue:
        rep.warn(f"the engine already has {info.queue} task(s); this one will wait its turn")
    return node, info


def run_process(
    req: ProcessRequest,
    rep: Reporter,
    *,
    probe: Callable[[Path], SystemSpec] | None = None,
    find_node: Callable[[], object] | None = None,
) -> ProcessOutcome:
    probe = probe or system_probe.probe_system
    find_node = find_node or system_probe.find_local_node
    started = time.time()
    name = req.name or task_name(req.folder)

    rep.step("Photos")
    files = photo_files(req.folder, recursive=req.recursive)
    if len(files) < MIN_PHOTOS:
        raise ProcessBlockedError(f"found {len(files)} photo(s); at least {MIN_PHOTOS} are needed")
    records, skipped = scan_photos(req.folder, recursive=req.recursive)
    sizes = [r.width_px * r.height_px for r in records if r.width_px and r.height_px]
    native_mp = statistics.median(sizes) / 1e6 if sizes else 0.0
    input_gb = sum(f.stat().st_size for f in files) / GB
    rep.info(f"{len(files)} photos, {native_mp:.1f} MP, {input_gb:.2f} GB")
    for file_name, reason in skipped:
        rep.warn(f"{file_name}: unreadable metadata ({reason})")

    rep.step("Capture check")
    notes: list[Issue] = []
    qa = analyse_capture(records, camera_chooser(None, notes))
    if "area_pct_min_views" in qa.stats:
        rep.info(
            f"GSD {qa.stats['gsd_cm_median']:.2f} cm/px, "
            f"{qa.stats['area_pct_min_views']:.0f}% of the area seen by 3+ photos"
        )
    # QA is advisory here: an assessment that could not be made is a warning, not an error
    qa_issues = [replace(i, level="warning") for i in [*qa.issues, *notes]]
    for issue in qa_issues:
        rep.warn(f"{issue.code}: {issue.message}")

    rep.step("Processing engine")
    node, info = _engine(req, rep, find_node)

    rep.step("This computer")
    system = probe(req.out_dir if req.out_dir.exists() else req.out_dir.parent)
    has_raw = any(f.suffix.lower() not in (".jpg", ".jpeg") for f in files)
    processing_mp = (
        native_mp if (req.resize_mp is None or has_raw) else min(native_mp, req.resize_mp)
    )
    if has_raw and req.resize_mp is not None:
        rep.warn(
            "raw (DNG) photos are sent at full size; JPEG photos give more predictable results"
        )
    job = JobSpec(len(files), max(native_mp, 0.1), input_gb)
    assessment = assess(system, job, processing_mp)
    rep.info(f"needs about {gb(assessment.ram_gb)} GB memory, {gb(assessment.disk_gb)} GB disk")
    for reason in assessment.reasons:
        rep.warn(reason)
    if assessment.verdict == "not-possible" and not req.force:
        raise ProcessBlockedError(
            "this computer cannot process these photos as they are", assessment
        )

    gsd = qa.stats.get("gsd_cm_median")
    sent_gsd = (
        None
        if gsd is None
        else effective_gsd_cm(gsd, native_mp=native_mp, processing_mp=processing_mp)
    )
    opts = build_options(
        req.preset,
        info.options,
        electronic_shutter=any(r.shutter == "Electronic" for r in records),
        gsd_cm=sent_gsd,
    )
    rep.info(f"preset '{req.preset}': {PRESETS[req.preset].description}")
    for note in opts.notes:
        rep.info(note)
    if opts.dropped:
        rep.warn(f"not supported by this engine, left out: {', '.join(opts.dropped)}")

    req.out_dir.mkdir(parents=True, exist_ok=True)
    upload_dir = req.out_dir / UPLOAD_DIR
    try:
        to_send = files
        if req.resize_mp is not None:
            rep.step("Preparing photos")
            to_send, resized = [], 0
            for f in files:
                dst = upload_dir / f.relative_to(req.folder).as_posix().replace("/", "__")
                resized += resize_photo(f, dst, req.resize_mp)[2]
                to_send.append(dst)
            rep.info(f"resized {resized} of {len(files)} photos to at most {req.resize_mp:g} MP")

        rep.step("Uploading")
        task = submit(node, to_send, opts.options, name, rep.upload)  # type: ignore[arg-type]
        rep.step("Processing")
        outcome = wait(
            task,
            rep.progress,
            interval=req.poll_s or DEFAULT_POLL_S,
            should_cancel=None if req.cancel is None else req.cancel.is_set,
        )
        zip_path = results_dir = None
        outputs: list[Path] = []
        reconstruction: ReconstructionSummary | None = None
        if outcome.completed:
            rep.step("Downloading results")
            downloaded = download_results(task, req.out_dir)
            zip_path = req.out_dir / f"{name}_all.zip"
            downloaded.replace(zip_path)
            results_dir = req.out_dir / "results"
            outputs = _extract(zip_path, results_dir)
            stats = read_stats(results_dir)
            if stats is not None:
                rep.step("Result quality")
                reconstruction = summarize_result(
                    stats, records, results_dir, sent_gsd, native_mp, processing_mp
                )
                report_quality(reconstruction, rep.info, rep.warn)
    finally:
        shutil.rmtree(upload_dir, ignore_errors=True)

    provenance_path = write_provenance(
        out_dir=req.out_dir,
        started=started,
        name=name,
        preset=req.preset,
        resize_mp=req.resize_mp,
        outcome=outcome,
        info=info,
        opts=opts,
        system=system,
        assessment=assessment,
        reconstruction=reconstruction,
        qa=qa,
        qa_issues=qa_issues,
        files=files,
        outputs=outputs,
    )
    return ProcessOutcome(outcome.completed, outcome, zip_path, results_dir, provenance_path)
