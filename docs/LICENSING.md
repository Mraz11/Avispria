# Licensing policy

- Project license: **AGPL-3.0-or-later** (provisional until ADR-0002 is accepted).
- Full license text: the `LICENSE` file (canonical text from
  https://www.gnu.org/licenses/agpl-3.0.txt).

## SPDX header policy
Every source file in `src/`, `tests/` and `scripts/` starts with:

    # SPDX-FileCopyrightText: <year> Avispria contributors
    # SPDX-License-Identifier: AGPL-3.0-or-later

## Third-party code
- Do not paste code from other projects without recording its license and
  origin in the commit message (and, later, in docs/THIRD_PARTY.md).
- Never copy GPL/AGPL code into the project if ADR-0002 selects a permissive
  license. Patterns and file formats are fine to learn from; code is not.
- NodeODX/ODX run as separate processes reached over HTTP (keep that boundary).
- Record each DEM and basemap source's license in the provenance bundle.
