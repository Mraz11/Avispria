# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Run every quality gate in order and stop at the first failure.

Used by `make check`, by CI, and directly:  uv run python scripts/check.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable

# What GitHub's runners set. The tests run with these everywhere, so a test that only
# passes on a developer's PC (e.g. one that breaks when a library forces coloured output
# on GitHub Actions) fails here first instead of after pushing.
CI_ENV = {"GITHUB_ACTIONS": "true", "CI": "true", "PYTHONUTF8": "1"}

STEPS: list[tuple[str, list[str], dict[str, str]]] = [
    ("ruff format --check", [PY, "-m", "ruff", "format", "--check", "."], {}),
    ("ruff check", [PY, "-m", "ruff", "check", "."], {}),
    ("mypy (core, strict)", [PY, "-m", "mypy", "src/avispria/core"], {}),
    ("file length (<= 400 lines)", [PY, "scripts/check_file_length.py", "--root", "src"], {}),
    ("pytest + coverage", [PY, "-m", "pytest"], CI_ENV),
]


def _normalised(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def check_context_files() -> int:
    context = ROOT / "PROJECT_CONTEXT.md"
    claude = ROOT / "CLAUDE.md"
    if _normalised(context) != _normalised(claude):
        print("FAIL: CLAUDE.md and PROJECT_CONTEXT.md differ.")
        print("Edit PROJECT_CONTEXT.md, then copy it over CLAUDE.md.")
        return 1
    return 0


def run_step(name: str, cmd: list[str], env: dict[str, str] | None = None) -> int:
    print(f"\n==> {name}", flush=True)
    return subprocess.run(cmd, cwd=ROOT, check=False, env={**os.environ, **(env or {})}).returncode


def main() -> int:
    print("==> context files identical", flush=True)
    if check_context_files() != 0:
        return 1
    for name, cmd, env in STEPS:
        code = run_step(name, cmd, env)
        if code != 0:
            print(f"\nFAILED: {name} (exit code {code})")
            return code
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
