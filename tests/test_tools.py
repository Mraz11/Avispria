# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for the repository tooling scripts."""

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_file_length.py"


def _run(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_short_files_pass(tmp_path: Path) -> None:
    (tmp_path / "ok.py").write_text("x = 1\n" * 10, encoding="utf-8")
    assert _run(tmp_path).returncode == 0


def test_file_at_hard_limit_passes(tmp_path: Path) -> None:
    (tmp_path / "edge.py").write_text("x = 1\n" * 400, encoding="utf-8")
    assert _run(tmp_path).returncode == 0


def test_file_over_hard_limit_fails_and_is_named(tmp_path: Path) -> None:
    (tmp_path / "big.py").write_text("x = 1\n" * 401, encoding="utf-8")
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "big.py" in result.stdout


def test_missing_root_is_an_error(tmp_path: Path) -> None:
    assert _run(tmp_path / "does_not_exist").returncode == 2
