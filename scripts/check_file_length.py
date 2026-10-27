# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fail if any .py file under the given root exceeds the hard line limit."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SOFT_LIMIT = 300
HARD_LIMIT = 400


def count_lines(path: Path) -> int:
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for _ in handle)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("src"))
    args = parser.parse_args(argv)

    if not args.root.is_dir():
        print(f"error: root directory not found: {args.root}")
        return 2

    failures: list[tuple[Path, int]] = []
    warnings: list[tuple[Path, int]] = []
    for path in sorted(args.root.rglob("*.py")):
        lines = count_lines(path)
        if lines > HARD_LIMIT:
            failures.append((path, lines))
        elif lines > SOFT_LIMIT:
            warnings.append((path, lines))

    for path, lines in warnings:
        print(f"warning: {path} has {lines} lines (soft limit {SOFT_LIMIT})")
    for path, lines in failures:
        print(f"FAIL: {path} has {lines} lines (hard limit {HARD_LIMIT})")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
