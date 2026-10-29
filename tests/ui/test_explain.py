# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import re
from pathlib import Path

from avispria.app.ui.explain import EXPLANATIONS, explain

SRC = Path(__file__).resolve().parents[2] / "src" / "avispria"
CODE = re.compile(r'"((?:QA|SAF|RQ|PL|AVI|WPML)\d{3})"')


def emitted_codes() -> set[str]:
    codes: set[str] = set()
    for path in SRC.rglob("*.py"):
        if path.name == "explain.py":
            continue
        codes |= set(CODE.findall(path.read_text(encoding="utf-8")))
    return codes


def test_every_code_the_tool_can_emit_is_explained() -> None:
    codes = emitted_codes()
    assert len(codes) >= 45  # the scan really found them
    assert codes - set(EXPLANATIONS) == set(), "add an explanation for the new code(s)"


def test_no_explanation_is_empty_or_orphaned() -> None:
    for code, e in EXPLANATIONS.items():
        assert e.title and e.meaning and e.action, code
        assert e.title[0].isupper() and e.meaning.endswith(".") and e.action.endswith("."), code
    assert set(EXPLANATIONS) - emitted_codes() == set(), "an explanation for a code nothing emits"


def test_unknown_code_gets_a_neutral_explanation() -> None:
    e = explain("XYZ999")
    assert e.title == "Notice" and e.meaning == "" and e.action == ""
