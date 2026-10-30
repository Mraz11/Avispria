# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The look of the interface: logo, light and dark mode, and the colours of buttons and charts."""

import re
from collections import deque
from pathlib import Path

import numpy as np
import pytest
from nicegui import ui
from nicegui.testing import User
from PIL import Image

from avispria.app.ui import theme, theme_state
from avispria.app.ui.layout import ASSETS
from avispria.app.ui.theme import DARK, LIGHT
from avispria.app.ui.theme_state import ThemeState
from uihelpers import eventually, set_text

pytestmark = [pytest.mark.anyio, pytest.mark.nicegui_main_file("tests/ui/ui_main.py")]
ROOT = Path(__file__).resolve().parents[2]


def prop(user: User, marker: str, name: str) -> object:
    return next(iter(user.find(marker=marker).elements)).props.get(name)


async def test_every_screen_shows_the_logo_in_both_variants(user: User, fake_computer) -> None:
    fake_computer()
    for page in ("/", "/check", "/plan", "/process"):
        await user.open(page)
        light = next(iter(user.find(marker="logo-light").elements))
        dark = next(iter(user.find(marker="logo-dark").elements))
        assert (
            'src="/assets/logo.png"' in str(light.props)
            or light.props.get("src") == "/assets/logo.png"
        ), page
        assert dark.props.get("src") == "/assets/logo-dark.png", page
        assert light.props.get("alt") == "Avispria logo", page  # a screen reader says what it is


async def test_the_start_screen_welcomes_with_the_logo(user: User, fake_computer) -> None:
    fake_computer()
    await user.open("/")
    await user.should_see("Welcome to Avispria")
    assert len(user.find(marker="logo-light").elements) == 2  # the header and the welcome card


async def test_the_theme_button_switches_between_light_and_dark(user: User) -> None:
    await user.open("/check")
    assert prop(user, "theme-toggle", "icon") == "dark_mode"  # offers dark while light
    user.find(marker="theme-toggle").click()
    await eventually(lambda: prop(user, "theme-toggle", "icon") == "light_mode")
    user.find(marker="theme-toggle").click()
    await eventually(lambda: prop(user, "theme-toggle", "icon") == "dark_mode")


async def test_charts_are_redrawn_in_the_colours_of_the_chosen_mode(
    user: User, photo_folder: Path
) -> None:
    await user.open("/check")
    set_text(user, "photos-input", str(photo_folder))
    user.find(marker="run").click()
    await user.should_see(kind=ui.echart)
    chart = next(iter(user.find(kind=ui.echart).elements))
    assert chart.options["visualMap"]["inRange"]["color"] == list(LIGHT.ramp)
    assert chart.options["xAxis"]["axisLabel"]["color"] == LIGHT.muted
    user.find(marker="theme-toggle").click()
    await eventually(lambda: chart.options["visualMap"]["inRange"]["color"] == list(DARK.ramp))
    assert (
        chart.options["xAxis"]["axisLabel"]["color"] == DARK.muted
    )  # axis text stays readable on the dark card
    assert DARK.ramp[-1] == "#39FF14"  # plenty of overlap shows as Neon Green in dark mode


async def test_secondary_actions_are_terra_cotta_and_main_actions_stay_green(
    user: User, photo_folder: Path
) -> None:
    await user.open("/check")
    set_text(user, "photos-input", str(photo_folder))
    user.find(marker="run").click()
    await user.should_see("Make maps from these photos")
    next_step = next(iter(user.find("Make maps from these photos").elements))
    assert next_step.props.get("color") == "secondary"  # Terra Cotta fill
    check = next(iter(user.find(marker="run").elements))
    assert check.props.get("color", "primary") == "primary"  # Leaf Green / Emerald fill


# ------------------------------------------------------------ the theme controller on its own
class FakeDark:
    value = False


def test_the_controller_remembers_and_announces_a_change(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[str] = []
    monkeypatch.setattr(theme_state.ui, "run_javascript", lambda js: sent.append(js))
    state = ThemeState(FakeDark())  # type: ignore[arg-type]
    seen: list[str] = []
    state.on_change(lambda p: seen.append(p.name))
    assert state.palette is LIGHT and not state.dark
    state.toggle()
    assert state.dark and state.palette is DARK and state.dark_mode.value is True
    assert seen == ["dark"]
    assert "localStorage.setItem('avispria.theme', 'dark')" in sent[0] and "data-theme" in sent[0]
    state.set_dark(True)  # nothing changed: nobody is told again
    assert seen == ["dark"]


def test_a_choice_made_in_the_browser_is_followed_but_not_saved_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[str] = []
    monkeypatch.setattr(theme_state.ui, "run_javascript", lambda js: sent.append(js))
    state = ThemeState(FakeDark())  # type: ignore[arg-type]
    state.from_browser("dark")
    assert state.dark and sent == []  # the browser already knows its own setting
    state.from_browser("light")
    state.from_browser("anything else")  # unknown values mean light
    assert not state.dark


def test_a_listener_that_returns_false_is_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(theme_state.ui, "run_javascript", lambda js: None)
    state = ThemeState(FakeDark())  # type: ignore[arg-type]
    calls: list[int] = []
    state.on_change(lambda p: (calls.append(1), False)[1])  # a chart that was deleted
    state.toggle()
    state.toggle()
    assert calls == [1]


# ------------------------------------------------------------------------- the logo files
def logo(name: str) -> np.ndarray:
    with Image.open(ASSETS / name) as image:
        return np.asarray(image.convert("RGBA")).astype(int)


def enclosed_openings(mask: np.ndarray) -> int:
    """How many regions outside ``mask`` its shape completely encloses (like the hole of a ring)."""
    h, w = mask.shape
    seen = mask.copy()
    count = 0
    for sy, sx in zip(*np.nonzero(~mask), strict=True):
        if seen[sy, sx]:
            continue
        queue, touches_edge = deque([(sy, sx)]), False
        seen[sy, sx] = True
        while queue:
            y, x = queue.popleft()
            touches_edge |= y in (0, h - 1) or x in (0, w - 1)
            for yy, xx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                if 0 <= yy < h and 0 <= xx < w and not seen[yy, xx]:
                    seen[yy, xx] = True
                    queue.append((yy, xx))
        count += not touches_edge
    return count


def navy(pixels: np.ndarray) -> np.ndarray:
    r, g, b, a = (pixels[..., i] for i in range(4))
    return (b > r + 18) & (0.2126 * r + 0.7152 * g + 0.0722 * b < 120) & (a > 200)


def test_the_logo_is_transparent_and_the_dark_variant_has_no_navy_left() -> None:
    light, dark = logo("logo.png"), logo("logo-dark.png")
    assert (
        light.shape == dark.shape and light[0, 0, 3] == 0 and light[-1, -1, 3] == 0
    )  # transparent corners
    solid = light[..., 3] > 200
    assert 0.25 < solid.mean() < 0.75  # a real cut-out, not an empty picture or a full square
    assert navy(light).sum() > 0.1 * solid.sum()  # the original has the navy X
    assert navy(dark).sum() == 0  # ... which is light in the dark variant
    # the green and terracotta parts are untouched (each file has its own 256-colour palette,
    # so the same colour may be rounded a few steps differently)
    kept = ~navy(light) & solid
    differences = np.abs(light[kept][:, :3] - dark[kept][:, :3]).max(axis=1)
    assert (
        np.percentile(differences, 99.5) <= 12
    )  # a few soft edge pixels may be classed differently


def test_the_logo_is_small_enough_to_load_on_every_visit() -> None:
    for name in ("logo.png", "logo-dark.png", "favicon.png"):
        assert (ASSETS / name).stat().st_size < 40_000, name
    with Image.open(ASSETS / "favicon.png") as icon:
        assert icon.size == (64, 64)


def test_the_original_picture_and_the_script_that_makes_the_files_are_kept() -> None:
    assert (ROOT / "branding" / "logo-source.jpg").stat().st_size > 10_000
    assert (ROOT / "branding" / "logo.png").is_file() and (
        ROOT / "branding" / "logo-dark.png"
    ).is_file()
    assert "def cut_out" in (ROOT / "scripts" / "make_branding.py").read_text(encoding="utf-8")


def test_the_stylesheet_uses_variables_and_hard_codes_no_colour() -> None:
    css = (ASSETS / "avispria.css").read_text(encoding="utf-8")
    code = "\n".join(line for line in css.splitlines() if not line.strip().startswith("/*"))
    assert theme.tokens_css(quasar=True).count("--primary") >= 2
    assert re.findall(r"#[0-9a-fA-F]{3,8}\b", code) == [], "a colour is hard-coded"
    for variable in (
        "--bg",
        "--surface",
        "--text",
        "--primary",
        "--secondary",
        "--highlight",
        "--border-strong",
    ):
        assert f"var({variable}" in css, variable


def test_the_logo_shows_a_drone_with_four_rotors_not_a_windmill() -> None:
    """A windmill is one hub with blades; a drone seen from above is a body with four separate
    rotors. Count the enclosed openings of the navy shape: four rotors and the camera hole."""
    for name in ("logo.png", "logo-dark.png"):
        pixels = logo(name)
        r, g, b, a = (pixels[..., i] for i in range(4))
        if name == "logo.png":
            shape = navy(pixels)
        else:  # the dark variant has the same shape, drawn light
            shape = (r > 200) & (g > 200) & (b > 200) & (a > 200)
        assert enclosed_openings(shape) == 5, name
