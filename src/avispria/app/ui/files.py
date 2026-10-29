# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Looking at folders and files on this computer, for the folder browser and result links.

The interface runs on the user's own computer, so it can list the real file system itself:
a web page cannot reveal real paths, but this program can.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Entry:
    name: str
    path: Path
    is_dir: bool


def list_entries(
    folder: Path, *, directories_only: bool = False, suffixes: Sequence[str] | None = None
) -> list[Entry]:
    """Folders first, then files, each alphabetically; hidden entries skipped.

    ``suffixes`` (e.g. ``(".kmz",)``) limits the files shown; unreadable folders give [].
    """
    wanted = tuple(s.lower() for s in suffixes) if suffixes else None
    try:
        children = list(folder.iterdir())
    except OSError:
        return []
    entries = []
    for child in children:
        if child.name.startswith((".", "$")):
            continue
        try:
            is_dir = child.is_dir()
        except OSError:
            continue
        if is_dir:
            entries.append(Entry(child.name, child, True))
        elif not directories_only and (wanted is None or child.suffix.lower() in wanted):
            entries.append(Entry(child.name, child, False))
    return sorted(entries, key=lambda e: (not e.is_dir, e.name.lower()))


def start_folder(preferred: str | Path | None) -> Path:
    """``preferred`` (or its nearest existing parent), else the home folder."""
    if preferred:
        path = Path(str(preferred)).expanduser()
        for candidate in (path, *path.parents):
            if candidate.is_dir():
                return candidate
    return Path.home()


def windows_drives() -> list[Path]:
    """Drive roots present on Windows (C:\\, D:\\, ...); empty elsewhere."""
    if sys.platform != "win32":
        return []
    return [
        Path(f"{letter}:\\")
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        if Path(f"{letter}:\\").exists()
    ]


def open_in_file_manager(path: Path) -> bool:
    """Show ``path`` (a file's folder) in the system file manager; False if that failed."""
    target = path if path.is_dir() else path.parent
    try:
        if sys.platform == "win32":
            os.startfile(target)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", str(target)], check=False)
        else:
            subprocess.run(["xdg-open", str(target)], check=False)
    except OSError:
        return False
    return True
