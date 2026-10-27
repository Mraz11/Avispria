# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Smoke tests: the package imports and the CLI responds."""

from typer.testing import CliRunner

import avispria
from avispria.app.cli import app
from avispria.core.version import __version__ as core_version

runner = CliRunner()


def test_package_imports_and_has_expected_version() -> None:
    # Update this literal deliberately when cutting a release.
    assert avispria.__version__ == "0.0.1"


def test_package_version_comes_from_core_module() -> None:
    assert avispria.__version__ == core_version


def test_cli_version_command_prints_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert avispria.__version__ in result.output


def test_cli_plan_is_a_placeholder_that_exits_with_code_2() -> None:
    result = runner.invoke(app, ["plan"])
    assert result.exit_code == 2
    assert "not implemented" in result.output
