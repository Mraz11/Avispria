# Avispria - Project Context (keep <=200 lines)

## What this is
Avispria (avis = Latin "bird", plus the osprey): open-source
(AGPL-3.0-or-later, provisional until ADR-0002), offline-first desktop toolkit
for planning DJI Fly waypoint photogrammetry missions for consumer RGB drones
(Mini 4 Pro first), checking capture quality, and orchestrating local
processing via NodeODX. Users: forestry/environmental researchers, often
offline and low-budget.
Tagline: "Canopy structure and change, seen from above."
RGB-only honesty rule: never imply multispectral capability, a "hidden
spectrum", or plant-health diagnosis. Colour indices are proxies and need
field validation.

## Team
- Founder/PM (human): decides, runs commands, flies, reviews, merges.
- Claude (lead dev): writes tests first, then code, then docs.
- Founder works in Windows PowerShell: give PowerShell commands (not bash)
  unless told otherwise.

## Stack (pinned in uv.lock - never upgrade casually)
Python 3.12 · uv · Shapely 2 · pyproj · rasterio (<1.5, see HANDOFF) · lxml ·
Typer · NiceGUI · sqlite3 (stdlib) · pytest · hypothesis · ruff · mypy ·
pre-commit
Processing: NodeODX over HTTP via pyodx (separate AGPL process).

## Commands
- Setup:      uv sync --locked   then   uv run pre-commit install
- All checks: uv run python scripts/check.py   (same gate as `make check` and CI)
  = context files identical, ruff format --check, ruff check,
    mypy src/avispria/core, file length <=400, pytest + coverage >=85%
- Tests only: uv run pytest
- Format:     uv run ruff format .   then   uv run ruff check --fix .
- CLI:        uv run avispria --help
- UI:         not implemented yet (Phase 1)

## Architecture rules
- src/avispria/core = PURE functions. No I/O, no network, no UI, no globals.
- adapters/ = all I/O behind small interfaces, each with a fake for tests.
- app/ = thin CLI + NiceGUI; no business logic.
- Max 300 lines/module (soft), 400 (CI hard fail); 50 lines/function.
- Units: metres, seconds, degrees; WGS84 in/out, UTM internally (pyproj).
- Every .py file starts with the two SPDX header lines (see docs/LICENSING.md).
- ASCII only inside .py files.

## Domain gotchas
- DJI Fly has NO official KMZ import for consumer drones. We patch the
  user's own dummy mission KMZ (template.kml + waylines.wpml in a zip).
- Founder's aircraft: DJI Lito X1 + RC-N3 + Redmi K90 (Android). Verified from
  their DJI Fly files: droneEnumValue 68 (same as Mini 4 Pro), namespace
  uav.com/wpmz/1.0.2, waypoint speed 0.1-12 m/s, gimbal pitch -90..+40.
  DJI Fly 1.21.16. Camera FC9589 (6.72 mm, 24 mm-equiv, 8064x6048, electronic shutter).
  Fixtures: tests/fixtures/dji_fly_dummy/ (keep byte-exact; coords shifted).
- Founder copies DJI Fly files on the phone with FV File Explorer.
- takePhoto action encoding is NOT yet seen in a DJI Fly file: default to
  interval (timed-shot) mode until a dummy with a photo action is captured.
- Fly namespace differs from Pilot 2 namespace; never mix.
- Copernicus GLO-30 is a DSM (includes canopy), 2011-2015 vintage.
- DJI RC 2 is MTP-only; ADB works on some controllers/phones.
- OSM standard tiles must never be prefetched; use local PMTiles.
- Never generate anything that bypasses geofencing or altitude limits.

## Workflow rules
1. One task per session. Restate task + acceptance criteria first.
2. Write failing test(s) before code. Show expected red.
3. Diffs <=300 lines. Output full files or unified diffs with paths.
4. No new dependency without asking; justify in one ADR line.
5. Never edit tests/golden/* unless the task says so.
6. Never claim success without the founder's pasted green check output.
7. If unsure an API exists in our pinned version, ask for help() output.
8. After 3 failed fix attempts: stop, summarise, propose revert.
9. End every session by rewriting HANDOFF.md (<=40 lines).
10. CLAUDE.md and PROJECT_CONTEXT.md must stay identical: edit
    PROJECT_CONTEXT.md, then copy it over CLAUDE.md (check.py enforces this).

## Commits
Conventional Commits: feat|fix|test|docs|chore|refactor(scope): summary

## Pointers
- Decisions: docs/adr/   Specs: docs/specs/   Field protocol: docs/field/
- Current state: HANDOFF.md
