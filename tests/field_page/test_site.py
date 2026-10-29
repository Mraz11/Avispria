# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The phone field page: it must stay offline-capable, private and in step with the planner."""

import importlib.util
import json
import re
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "field-page"
TESTS = Path(__file__).resolve().parent
OWN_REPO = "https://github.com/Mraz11/Avispria"


def load_generator():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location(
        "field_page_gen", ROOT / "scripts" / "field_page.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.scripts: list[dict[str, str | None]] = []
        self.links: list[dict[str, str | None]] = []
        self.anchors: list[str] = []
        self.metas: list[dict[str, str | None]] = []
        self.attrs: list[tuple[str, str]] = []
        self.inline_script = False
        self._in_script = False
        self.stack: list[str] = []
        self.errors: list[str] = []

    VOID = frozenset({"meta", "link", "br", "img", "input", "hr", "path"})

    def handle_starttag(self, tag, attrs):  # type: ignore[no-untyped-def]
        a = dict(attrs)
        self.attrs += [(tag, k) for k in a]
        if tag == "script":
            self.scripts.append(a)
            self._in_script = "src" not in a
        elif tag == "link":
            self.links.append(a)
        elif tag == "a":
            self.anchors.append(a.get("href") or "")
        elif tag == "meta":
            self.metas.append(a)
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):  # type: ignore[no-untyped-def]
        if tag == "script":
            self._in_script = False
        if tag in self.VOID:
            return
        if not self.stack or self.stack[-1] != tag:
            self.errors.append(f"unexpected </{tag}> (open: {self.stack[-3:]})")
        else:
            self.stack.pop()

    def handle_data(self, data):  # type: ignore[no-untyped-def]
        if self._in_script and data.strip():
            self.inline_script = True


def page() -> Page:
    parsed = Page()
    parsed.feed((SITE / "index.html").read_text(encoding="utf-8"))
    return parsed


def shipped() -> list[Path]:
    return [p for p in SITE.rglob("*") if p.is_file()]


def test_generated_files_are_current() -> None:
    gen = load_generator()
    stale = {
        path.relative_to(ROOT).as_posix(): reason
        for path, text in gen.expected_files().items()
        if (reason := gen.stale_reason(path, text)) is not None
    }
    assert stale == {}, f"run `python scripts/field_page.py` (out of date: {stale})"


def test_golden_values_are_compared_by_value_not_by_text() -> None:
    gen = load_generator()
    base = json.dumps({"a": [1, 2.5, {"x": 3.0}], "name": "lito", "ok": True})

    def differences(**changes: object) -> list[str]:
        edited = json.loads(base)
        edited.update(changes)
        return gen.golden_differences(base, json.dumps(edited))

    assert gen.golden_differences(base, base) == []
    assert (
        differences(a=[1, 2.5 * (1 + 1e-9), {"x": 3.0 * (1 - 1e-10)}]) == []
    )  # another system's last digits
    real_change = differences(a=[1, 2.5 * (1 + 1e-3), {"x": 3.0}])  # a real change
    assert len(real_change) == 1 and real_change[0].startswith("$.a[1]: 2.5 != 2.502")
    assert differences(a=[2, 2.5, {"x": 3.0}]) == ["$.a[0]: 1 != 2"]  # counts must match exactly
    assert differences(name="mini") == ["$.name: 'lito' != 'mini'"]
    assert differences(a=[1, 2.5]) == ["$.a: 3 items != 2 items"]
    assert gen.golden_differences(base, json.dumps({"a": [], "ok": True})) != []  # missing key
    assert gen.golden_differences(base, base.replace("true", "false")) == ["$.ok: True != False"]


def test_the_offline_list_is_every_file_the_page_ships() -> None:
    text = (SITE / "sw.js").read_text(encoding="utf-8")
    listed = json.loads(re.search(r"const ASSETS = (\[.*?\]);", text, re.S).group(1))  # type: ignore[union-attr]
    on_disk = sorted(
        p.relative_to(SITE).as_posix() for p in shipped() if p.name not in {"sw.js", "package.json"}
    )
    assert listed[0] == "./" and sorted(listed[1:]) == on_disk
    assert re.search(r'const BUILD = "[0-9a-f]{12}";', text)


def test_the_page_is_well_formed_and_loads_only_its_own_files() -> None:
    p = page()
    assert p.errors == [] and p.stack == []
    assert [s.get("src") for s in p.scripts] == ["js/app.js"] and p.scripts[0].get(
        "type"
    ) == "module"
    assert not p.inline_script
    bad_attrs = [(t, k) for t, k in p.attrs if k == "style" or k.startswith("on")]
    assert bad_attrs == []  # no inline styles or handlers: the content policy forbids them
    for tag in (*p.links, *p.scripts):
        target = tag.get("href") or tag.get("src")
        assert target and "://" not in target and (SITE / target).is_file(), target
    external = [a for a in p.anchors if "://" in a]
    assert (
        external == []
    )  # the page's own links are in-page tabs; the GitHub link is added by app.js
    assert any(
        m.get("name") == "viewport" and "width=device-width" in (m.get("content") or "")
        for m in p.metas
    )


def test_the_content_policy_allows_nothing_beyond_the_site_itself() -> None:
    csp = next(
        m["content"] for m in page().metas if m.get("http-equiv") == "Content-Security-Policy"
    )
    assert csp is not None
    directives = dict(d.strip().split(" ", 1) for d in csp.split(";") if d.strip())
    assert directives["default-src"] == "'self'" and directives["script-src"] == "'self'"
    assert directives["connect-src"] == "'self'" and directives["form-action"] == "'none'"
    assert "unsafe" not in csp and "http" not in csp


def test_no_file_mentions_an_outside_address_except_the_project_page() -> None:
    allowed = {OWN_REPO, "http://www.w3.org/2000/svg"}  # the second is an SVG namespace label
    for path in shipped():
        if path.suffix in {".png"}:
            continue
        text = path.read_text(encoding="utf-8")
        found = set(re.findall(r"https?://[^\s\"'<>)]+", text))
        assert found <= allowed, f"{path.name}: {found - allowed}"


def test_scripts_never_build_html_from_text_or_run_text_as_code() -> None:
    forbidden = re.compile(
        "|".join(
            [
                r"innerHTML",
                r"outerHTML",
                r"insertAdjacentHTML",
                r"document\.write",
                r"\beval\(",
                r"new Function",
                r"setTimeout\(\s*[\"']",
            ]
        )
    )
    for path in (SITE / "js").glob("*.js"):
        assert not forbidden.search(path.read_text(encoding="utf-8")), path.name
    sw = (SITE / "sw.js").read_text(encoding="utf-8")
    assert "location.origin" in sw  # only same-site requests are ever answered or cached


def test_manifest_is_installable() -> None:
    m = json.loads((SITE / "manifest.webmanifest").read_text(encoding="utf-8"))
    assert m["display"] == "standalone" and m["start_url"] == "./" and m["scope"] == "./"
    assert m["name"] and m["short_name"] and re.fullmatch(r"#[0-9a-f]{6}", m["theme_color"])
    purposes = {i["purpose"] for i in m["icons"]}
    assert {"any", "maskable"} <= purposes
    for icon in m["icons"]:
        with Image.open(SITE / icon["src"]) as img:
            assert f"{img.width}x{img.height}" == icon["sizes"] and img.format == "PNG"
    assert {i["sizes"] for i in m["icons"]} >= {"192x192", "512x512"}  # what Android requires


def test_icons_are_drawn_for_their_purpose() -> None:
    with Image.open(SITE / "icons" / "icon-512.png") as img:
        assert img.convert("RGBA").getpixel((0, 0))[3] == 0  # rounded: transparent corner
    with Image.open(SITE / "icons" / "icon-maskable-512.png") as img:
        assert img.convert("RGBA").getpixel((0, 0))[3] == 255  # full bleed: the phone crops it
    with Image.open(SITE / "icons" / "apple-touch-icon.png") as img:
        assert img.size == (180, 180) and img.mode == "RGB"  # iPhones want an opaque square


def test_module_package_file_only_serves_node() -> None:
    package = json.loads((SITE / "package.json").read_text(encoding="utf-8"))
    assert package == {"type": "module", "private": True}


def test_golden_values_cover_the_planner_cases() -> None:
    golden = json.loads((TESTS / "golden.json").read_text(encoding="utf-8"))
    assert {"camera", "height", "speed", "survey", "canopy"} <= set(golden)
    assert len(golden["survey"]) >= 5 and any(len(c["missions"]) > 1 for c in golden["survey"])


@pytest.mark.skipif(
    shutil.which("node") is None, reason="Node.js is not installed (GitHub's runners have it)"
)
def test_the_javascript_calculators_agree_with_the_planner() -> None:
    files = sorted(str(p) for p in TESTS.glob("*.test.mjs"))
    assert len(files) >= 2
    result = subprocess.run(
        ["node", "--test", *files], capture_output=True, text=True, check=False, timeout=120
    )
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-1500:]


@pytest.mark.skipif(
    shutil.which("node") is None, reason="Node.js is not installed (GitHub's runners have it)"
)
@pytest.mark.parametrize(
    "script", sorted((SITE).rglob("*.js")), ids=lambda p: p.relative_to(SITE).as_posix()
)
def test_every_script_of_the_page_parses(script: Path) -> None:
    """A syntax error would stop the whole page, and nothing else imports app.js to notice."""
    result = subprocess.run(
        ["node", "--check", str(script)], capture_output=True, text=True, check=False, timeout=60
    )
    assert result.returncode == 0, result.stderr[-800:]
