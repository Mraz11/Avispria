# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest

from avispria.core.feasibility import JobSpec, SystemSpec, assess, ram_needed_gb

GOOD_PC = SystemSpec(
    "Windows 11", 8, ram_total_gb=32.0, ram_available_gb=24.0, swap_total_gb=8.0, disk_free_gb=400.0
)
SMALL_PC = SystemSpec(
    "Windows 10", 4, ram_total_gb=8.0, ram_available_gb=5.0, swap_total_gb=4.0, disk_free_gb=60.0
)


def test_ram_table_matches_opendronemap_docs() -> None:
    assert ram_needed_gb(40) == pytest.approx(4.0)
    assert ram_needed_gb(250) == pytest.approx(16.0)
    assert ram_needed_gb(1500) == pytest.approx(64.0)
    assert ram_needed_gb(10) == pytest.approx(4.0)  # never below the 4 GB minimum
    assert ram_needed_gb(145) == pytest.approx(10.0)  # linear between 40 and 250
    assert ram_needed_gb(10_000) > 256.0  # extrapolates linearly beyond the table


def test_small_job_on_good_pc_is_ok() -> None:
    a = assess(GOOD_PC, JobSpec(photos=200, native_mp=48.8, input_gb=12.0))
    assert a.verdict == "ok"
    assert a.processing_mp == pytest.approx(12.2)  # downscaled for processing by default
    assert a.options == []


def test_too_big_job_offers_working_alternatives() -> None:
    a = assess(SMALL_PC, JobSpec(photos=600, native_mp=48.8, input_gb=36.0))
    assert a.verdict == "not-possible"
    kinds = [o.kind for o in a.options]
    assert {"lower-resolution", "split"} <= set(kinds)
    split = next(o for o in a.options if o.kind == "split")
    assert split.fits and split.ram_gb <= SMALL_PC.ram_total_gb
    # 600 photos do not fit in 8 GB even at 3 MP: the option is shown, honestly marked
    lower = next(o for o in a.options if o.kind == "lower-resolution")
    assert not lower.fits and "3 MP" in lower.description


def test_lower_resolution_fits_when_it_can() -> None:
    a = assess(SMALL_PC, JobSpec(photos=150, native_mp=48.8, input_gb=9.0))
    lower = next(o for o in a.options if o.kind == "lower-resolution")
    assert lower.fits and lower.ram_gb <= SMALL_PC.ram_total_gb * 0.85


def test_swap_makes_it_possible_but_slow() -> None:
    pc = SystemSpec(
        "Linux", 4, ram_total_gb=12.0, ram_available_gb=10.0, swap_total_gb=8.0, disk_free_gb=200.0
    )
    a = assess(pc, JobSpec(photos=250, native_mp=12.2, input_gb=1.5))  # needs 16 GB
    assert a.verdict == "slow"
    assert any("virtual memory" in r for r in a.reasons)


def test_disk_shortage_is_reported() -> None:
    pc = SystemSpec("Windows 11", 8, 32.0, 24.0, 8.0, disk_free_gb=10.0)
    a = assess(pc, JobSpec(photos=100, native_mp=12.2, input_gb=0.8))
    assert a.verdict == "not-possible"
    assert any("disk" in r for r in a.reasons)
    assert any(o.kind == "free-disk" for o in a.options)


def test_full_resolution_needs_more_memory() -> None:
    job = JobSpec(photos=200, native_mp=48.8, input_gb=12.0)
    default = assess(GOOD_PC, job)
    full = assess(GOOD_PC, job, processing_mp=48.8)
    assert full.ram_gb > default.ram_gb


def test_no_useless_options_at_the_memory_floor() -> None:
    tiny = SystemSpec(
        "Linux", 1, ram_total_gb=3.9, ram_available_gb=3.6, swap_total_gb=0.0, disk_free_gb=100.0
    )
    a = assess(tiny, JobSpec(photos=4, native_mp=48.8, input_gb=0.24))
    assert a.verdict == "not-possible"
    kinds = [o.kind for o in a.options]
    assert "lower-resolution" not in kinds and "split" not in kinds
    swap = next(o for o in a.options if o.kind == "more-swap")
    assert swap.fits and swap.slow
    assert "3.9 GB" in " ".join(a.reasons)


def test_gb_formatting() -> None:
    from avispria.core.feasibility import gb

    assert gb(3.94) == "3.9"
    assert gb(12.4) == "12"
