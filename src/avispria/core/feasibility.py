# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Will this computer manage this photogrammetry job? If not, what would work?

Memory needs follow OpenDroneMap's published table ("Minimum RAM needed for N
images", docs.opendronemap.org/installation). The table does not state image
size; we assume typical ~12 MP drone photos and scale by processing megapixels,
which is an estimate. Disk needs are a conservative rule of thumb.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field
from typing import Literal

# (images, GB of RAM or RAM + swap) from the OpenDroneMap documentation
ODM_RAM_TABLE: tuple[tuple[int, float], ...] = (
    (40, 4.0),
    (250, 16.0),
    (500, 32.0),
    (1500, 64.0),
    (2500, 128.0),
    (3500, 192.0),
    (5000, 256.0),
)
REFERENCE_MP = 12.2  # assumed image size behind the ODM table (4032 x 3024)
DEFAULT_PROCESSING_MP = 12.2  # Avispria downscales larger photos unless asked not to
RAM_USABLE_FRACTION = 0.85  # leave room for the operating system
DISK_FACTOR = 8.0  # project folders grow to several times the input size
DISK_MARGIN_GB = 5.0
DISK_MIN_GB = 20.0  # OpenDroneMap minimum
SPLIT_OVERLAP = 1.1  # submodels share ~10% of images
LOWER_RESOLUTIONS_MP = (8.0, 6.0, 4.0, 3.0)

Verdict = Literal["ok", "slow", "not-possible"]


@dataclass(frozen=True)
class SystemSpec:
    os_name: str
    cpu_logical: int
    ram_total_gb: float
    ram_available_gb: float
    swap_total_gb: float
    disk_free_gb: float


@dataclass(frozen=True)
class JobSpec:
    photos: int
    native_mp: float
    input_gb: float


@dataclass(frozen=True)
class Option:
    kind: str
    description: str
    ram_gb: float | None  # memory the option needs (None if memory is not the point)
    fits: bool  # would this alone make the job possible on this computer?
    slow: bool = False


def gb(value: float) -> str:
    """Human-friendly GB: one decimal below 10 GB so 3.9 never reads as 4."""
    return f"{value:.1f}" if value < 10 else f"{value:.0f}"


@dataclass(frozen=True)
class Assessment:
    verdict: Verdict
    ram_gb: float
    disk_gb: float
    processing_mp: float
    effective_images: float
    reasons: list[str] = field(default_factory=list)
    options: list[Option] = field(default_factory=list)


def ram_needed_gb(images: float) -> float:
    """RAM (or RAM + swap) for ``images`` reference-size photos, per the ODM table."""
    table = ODM_RAM_TABLE
    if images <= table[0][0]:
        return table[0][1]
    for (n0, g0), (n1, g1) in itertools.pairwise(table):
        if images <= n1:
            return g0 + (images - n0) * (g1 - g0) / (n1 - n0)
    (n0, g0), (n1, g1) = table[-2], table[-1]
    return g1 + (images - n1) * (g1 - g0) / (n1 - n0)


def _ram_for(photos: float, mp: float) -> float:
    return ram_needed_gb(photos * mp / REFERENCE_MP)


def assess(system: SystemSpec, job: JobSpec, processing_mp: float | None = None) -> Assessment:
    """Verdict plus, when the job does not fit comfortably, ranked alternatives."""
    if job.photos <= 0 or job.native_mp <= 0:
        raise ValueError("a job needs at least one photo with a known size")
    mp = min(job.native_mp, DEFAULT_PROCESSING_MP) if processing_mp is None else processing_mp
    mp = min(mp, job.native_mp)
    effective = job.photos * mp / REFERENCE_MP
    ram = ram_needed_gb(effective)
    disk = max(DISK_MIN_GB, job.input_gb * DISK_FACTOR + DISK_MARGIN_GB)
    usable = system.ram_total_gb * RAM_USABLE_FRACTION
    reasons: list[str] = []
    options: list[Option] = []

    disk_ok = system.disk_free_gb >= disk
    if not disk_ok:
        reasons.append(
            f"needs about {gb(disk)} GB of free disk, only {gb(system.disk_free_gb)} GB free"
        )
        options.append(
            Option(
                "free-disk",
                f"Free up space or choose a drive with at least {gb(disk)} GB free",
                None,
                True,
            )
        )
    if ram <= usable:
        verdict: Verdict = "ok"
        if system.ram_available_gb < ram:
            reasons.append(
                f"close other programs: {gb(system.ram_available_gb)} GB is free right now, "
                f"about {gb(ram)} GB is needed"
            )
    elif ram <= usable + system.swap_total_gb:
        verdict = "slow"
        reasons.append(
            f"needs about {gb(ram)} GB; it will use virtual memory (disk), which is much slower"
        )
    else:
        verdict = "not-possible"
        reasons.append(
            f"needs about {gb(ram)} GB of memory; this PC has {gb(system.ram_total_gb)} GB "
            f"(+ {gb(system.swap_total_gb)} GB virtual memory)"
        )
    if not disk_ok:
        verdict = "not-possible"

    if ram > usable:
        options += _memory_options(job, mp, ram, usable)
    return Assessment(verdict, ram, disk, mp, effective, reasons, options)


def _memory_options(job: JobSpec, mp: float, ram: float, usable: float) -> list[Option]:
    """Alternatives that actually reduce the memory need (or add memory)."""
    out: list[Option] = []
    lower = [m for m in LOWER_RESOLUTIONS_MP if m < mp and _ram_for(job.photos, m) < ram]
    if lower:
        fitting = [m for m in lower if _ram_for(job.photos, m) <= usable]
        m = fitting[0] if fitting else lower[-1]
        need = _ram_for(job.photos, m)
        out.append(
            Option(
                "lower-resolution",
                f"Process at {m:g} MP instead of {mp:g} MP (slightly less detail)",
                need,
                need <= usable,
            )
        )
    for parts in range(2, 41):
        need = _ram_for(math.ceil(job.photos / parts * SPLIT_OVERLAP), mp)
        if need >= ram:
            break  # already at the minimum: splitting cannot help
        if need <= usable:
            out.append(
                Option(
                    "split",
                    f"Split into {parts} overlapping parts processed one after another, "
                    "then merged into one map",
                    need,
                    True,
                )
            )
            break
    out.append(
        Option(
            "more-swap",
            f"Increase virtual memory so memory + virtual memory reaches {math.ceil(ram)} GB",
            ram,
            True,
            slow=True,
        )
    )
    out.append(
        Option(
            "other-computer",
            f"Process on a computer with at least {math.ceil(ram / RAM_USABLE_FRACTION)} GB RAM",
            ram,
            True,
        )
    )
    return out
