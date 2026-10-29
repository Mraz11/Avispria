# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import sys
from pathlib import Path

import pytest

# make shared test helpers (tiffbuild) importable under importlib import mode
sys.path.insert(0, str(Path(__file__).resolve().parent))


@pytest.fixture(autouse=True)
def plain_cli_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make command-line output identical wherever the tests run.

    Typer forces colour whenever GITHUB_ACTIONS is set (GitHub's runners), and the colour
    codes split the text the tests look for (e.g. an option name inside an error box).
    Tests must not depend on the environment they run in, so colour is switched off.
    """
    from typer import rich_utils

    monkeypatch.setattr(rich_utils, "FORCE_TERMINAL", None)
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    monkeypatch.setenv("NO_COLOR", "1")
