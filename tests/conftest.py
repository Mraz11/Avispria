# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import sys
from pathlib import Path

# make shared test helpers (tiffbuild) importable under importlib import mode
sys.path.insert(0, str(Path(__file__).resolve().parent))
