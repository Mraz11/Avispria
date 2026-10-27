# HANDOFF - 2026-10-26 - session #1 (restarted as Avispria)
## Done this session
- Project renamed CanopyPlan -> Avispria; scaffold regenerated from scratch
  with bootstrap_avispria.ps1 (kept outside the repo, not committed).
- Beyond spec: scripts/check.py (single gate), tests/test_tools.py,
  .gitattributes (LF), .python-version, docs/LICENSING.md.
- Claude self-tested the scaffold in a Linux sandbox (see master handoff 2.3).
## Current state (command proof)
- UNVERIFIED on the founder's machine until pasted:
  uv run python scripts/check.py  (expected last line: "All checks passed.")
- UNVERIFIED: CI green on ubuntu / windows / macos.
## Open problems / suspicions
- Name checks pending: PyPI, GitHub search, trademark databases.
  Risks: "Avis" brand proximity; "avispa" = wasp in Spanish.
  Pronunciation not yet decided.
- rasterio capped <1.5 (1.5 macOS wheels need macOS 15+). Revisit after CI.
- setup-uv pinned to @v10.0.1; if the tag fails to resolve try @v10.0.0.
- pre-commit-hooks pinned to v6.0.0 (tested 2026-10-26).
- LICENSE downloaded from gnu.org; AGPL is provisional until ADR-0002.
- CITATION.cff has REPLACE_ME placeholders (name, GitHub handle).
## Next single task (ready-to-paste)
Session 2: ADRs 0001-0003 (prompt in AVISPRIA_MASTER_HANDOFF.md, Section 12).
## Decisions made
- Name: Avispria. No formal ADRs yet (Session 2).
## Do-not-touch notes
- tests/golden/* stays empty. CLAUDE.md must equal PROJECT_CONTEXT.md.
