# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Command-line interface. Thin: parsing, printing and exit codes only.

Each submodule registers its commands on the shared Typer ``app``.
"""

from avispria.app.cli import capture, doctor, engine, files, plan  # noqa: F401  (register commands)
from avispria.app.cli._base import app

__all__ = ["app"]
