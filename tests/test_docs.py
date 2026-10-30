# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The README must stay true: every command it names exists, every command is named, links work."""

import re
from pathlib import Path

from typer.main import get_command

from avispria.app.cli import app

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text(encoding="utf-8")


def test_every_command_of_the_program_is_in_the_readme() -> None:
    commands = set(get_command(app).commands)  # type: ignore[attr-defined]
    assert {"plan", "qa", "process", "doctor", "ui", "engine"} <= commands
    missing = [
        name
        for name in sorted(commands)
        if f"`{name}`" not in README and f"avispria {name}" not in README
    ]
    assert missing == [], f"add these commands to the README: {missing}"


def test_every_avispria_command_shown_in_the_readme_exists() -> None:
    commands = set(get_command(app).commands)  # type: ignore[attr-defined]
    shown = set(re.findall(r"uv run avispria ([a-z][a-z-]*)", README))
    assert shown and shown <= commands, (
        f"the README shows commands that do not exist: {shown - commands}"
    )
    for row in re.findall(r"^\| ((?:`[a-z-]+`(?:, )?)+) \|", README, re.M):
        assert set(re.findall(r"`([a-z-]+)`", row)) <= commands, row


def test_the_install_steps_are_real_and_cover_every_system() -> None:
    assert "<you>" not in README and "<your" not in README  # no placeholder addresses
    for text in (
        "git clone https://github.com/Mraz11/Avispria.git",
        "uv sync --locked",
        "winget install --id Git.Git -e",
        "irm https://astral.sh/uv/install.ps1 | iex",
        "curl -LsSf https://astral.sh/uv/install.sh | sh",
        "Start-Avispria.bat",
        "./start-avispria.sh",
        "Start-Avispria.command",
        "### Windows",
        "### macOS",
        "### Linux",
    ):
        assert text in README, text
    for name in ("Start-Avispria.bat", "start-avispria.sh", "Start-Avispria.command"):
        assert (ROOT / name).is_file(), name  # the launchers the steps name exist


def test_links_to_files_in_the_repository_work() -> None:
    links = re.findall(r"\]\(([^)#]+)\)", README) + re.findall(r'src="([^"]+)"', README)
    local = [link for link in links if "://" not in link]
    assert local, "the README links to nothing"
    for link in local:
        assert (ROOT / link).exists(), f"broken link in the README: {link}"


def test_the_readme_points_to_the_real_logo_and_it_exists() -> None:
    assert 'src="branding/logo.png"' in README and (ROOT / "branding" / "logo.png").is_file()
