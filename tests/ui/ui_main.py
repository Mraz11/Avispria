# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Main file the simulated user opens: the real screens, run without a browser."""

from nicegui import ui

from avispria.app.ui.app import register_pages

register_pages()
ui.run(host="127.0.0.1", reload=False, show=False)
