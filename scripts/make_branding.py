# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Make every logo file from the original picture (``branding/logo-source.jpg``).

The original has a pale background. This cuts the logo out (with clean, halo-free edges),
redraws its navy X as a drone seen from above (a body, four arms and four separate rotors: the
original X reads as a windmill), makes a dark-mode variant (the navy parts become light, so the
drone shows on a dark page) and writes the sizes the screens, the browser tab and the phone's home
screen need. The tree and the mountains are left exactly as designed.

Run ``python scripts/make_branding.py`` to recreate the files. Needs numpy and Pillow.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "branding" / "logo-source.jpg"
BEIGE = "#FDF8F5"
APP_ASSETS = ROOT / "src" / "avispria" / "app" / "ui" / "assets"
PHONE = ROOT / "field-page"


def _box(arr: np.ndarray, r: int, axis: int) -> np.ndarray:
    pad = [(0, 0)] * arr.ndim
    pad[axis] = (r + 1, r)
    c = np.cumsum(np.pad(arr, pad, mode="edge"), axis=axis, dtype=np.float64)
    n = arr.shape[axis]
    hi = np.take(c, range(2 * r + 1, 2 * r + 1 + n), axis=axis)
    lo = np.take(c, range(0, n), axis=axis)
    return ((hi - lo) / (2 * r + 1)).astype(np.float32)


def _blur(arr: np.ndarray, sigma: float) -> np.ndarray:
    """Smooth a 2-D float array (three box blurs approximate a Gaussian)."""
    r = max(1, round(sigma * 0.9))
    out = arr.astype(np.float32)
    for _ in range(3):
        out = _box(_box(out, r, 0), r, 1)
    return out


def _drop_specks(alpha: np.ndarray, minimum: int = 150) -> np.ndarray:
    """Keep only the real pieces of the logo: JPEG noise leaves tiny stray dots."""
    h, w = alpha.shape
    solid = alpha > 0.5
    seen = np.zeros_like(solid)
    keep = np.zeros_like(solid)
    for y0, x0 in zip(*np.nonzero(solid), strict=True):
        if seen[y0, x0]:
            continue
        stack, piece = [(y0, x0)], []
        seen[y0, x0] = True
        while stack:
            y, x = stack.pop()
            piece.append((y, x))
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    yy, xx = y + dy, x + dx
                    if 0 <= yy < h and 0 <= xx < w and solid[yy, xx] and not seen[yy, xx]:
                        seen[yy, xx] = True
                        stack.append((yy, xx))
        if len(piece) >= minimum:
            for y, x in piece:
                keep[y, x] = True
    near = (
        np.asarray(Image.fromarray((keep * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(9)))
        > 0
    )
    return np.where(near, alpha, 0.0)


def cut_out(source: Image.Image) -> Image.Image:
    """The logo on a transparent background, cropped to its edges."""
    a = np.asarray(source.convert("RGB")).astype(np.float32)
    plain = ((a.min(axis=2) > 222) & ((a.max(axis=2) - a.min(axis=2)) < 22)).astype(np.float32)
    background = np.stack(
        [_blur(a[..., c] * plain, 40) / np.maximum(_blur(plain, 40), 1e-4) for c in range(3)],
        axis=-1,
    )
    distance = np.linalg.norm(a - background, axis=2)
    solid = (distance > 80).astype(np.float32)
    near_solid = _blur(solid, 4)
    colour = np.stack(
        [_blur(a[..., c] * solid, 4) / np.maximum(near_solid, 1e-4) for c in range(3)], axis=-1
    )
    colour = np.where(near_solid[..., None] > 0.02, colour, a)
    span = colour - background
    alpha = np.clip(
        ((a - background) * span).sum(axis=2) / np.maximum((span * span).sum(axis=2), 1.0), 0, 1
    )
    alpha[distance < 9] = 0.0
    rgb = np.where(
        (alpha < 0.97)[..., None], colour, a
    )  # edge pixels take the clean colour: no halo
    alpha = _drop_specks(alpha)
    rgba = np.dstack([np.clip(rgb, 0, 255), alpha * 255]).astype(np.uint8)
    image = Image.fromarray(rgba, "RGBA")
    return image.crop(image.getchannel("A").point(lambda v: 255 if v > 6 else 0).getbbox())


def _navy_mask(arr: np.ndarray, minimum_alpha: int) -> np.ndarray:
    r, g, b, a = (arr[..., i] for i in range(4))
    return (b > r + 18) & (0.2126 * r + 0.7152 * g + 0.0722 * b < 120) & (a > minimum_alpha)


def redraw_x_as_drone(logo: Image.Image) -> Image.Image:
    """Replace the navy X by a drone seen from above, the same size and in the same colour.

    The hub and the reach of the old X are measured from the picture, and the drone is drawn in
    proportion to them: four open rotors on thin arms around a small body with a camera hole.
    """
    arr = np.asarray(logo).astype(int)
    solid = _navy_mask(arr, 200)
    ys, xs = np.nonzero(solid)
    hub = (xs.mean(), ys.mean())
    # how far the old X reaches from its hub: the nearer side each way, so nothing is cut off
    dx = min(hub[0] - xs.min(), xs.max() - hub[0])
    dy = min(hub[1] - ys.min(), ys.max() - hub[1])
    reach = math.hypot(dx, dy)
    colour = (*(int(np.median(arr[..., c][solid])) for c in range(3)), 255)
    # erase the old X (a little beyond its edges, to remove the soft border too)
    wide = _navy_mask(arr, 60)
    grown = (
        np.asarray(Image.fromarray((wide * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(7)))
        > 0
    )
    erased = arr.copy()
    erased[grown, 3] = 0
    base = Image.fromarray(erased.astype(np.uint8), "RGBA")

    ss = 4  # draw large, then shrink: smooth edges
    layer = Image.new("RGBA", (logo.width * ss, logo.height * ss), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    arm, body, hole = 0.074 * reach, 0.147 * reach, 0.054 * reach
    ring, ring_width = 0.196 * reach, 0.059 * reach
    for sx in (-1, 1):
        for sy in (-1, 1):
            # each rotor's outer edge touches the old X's outline but never crosses it
            cx, cy = hub[0] + sx * (dx - ring), hub[1] + sy * (dy - ring)
            gap = math.hypot(cx - hub[0], cy - hub[1])
            along = (gap - (ring - ring_width)) / gap  # the arm stops where the rotor ring begins
            draw.line(
                [
                    (hub[0] * ss, hub[1] * ss),
                    ((hub[0] + (cx - hub[0]) * along) * ss, (hub[1] + (cy - hub[1]) * along) * ss),
                ],
                fill=colour,
                width=round(arm * ss),
            )
            draw.ellipse(
                [(cx - ring) * ss, (cy - ring) * ss, (cx + ring) * ss, (cy + ring) * ss],
                outline=colour,
                width=round(ring_width * ss),
            )
    draw.ellipse(
        [(hub[0] - body) * ss, (hub[1] - body) * ss, (hub[0] + body) * ss, (hub[1] + body) * ss],
        fill=colour,
    )
    draw.ellipse(
        [(hub[0] - hole) * ss, (hub[1] - hole) * ss, (hub[0] + hole) * ss, (hub[1] + hole) * ss],
        fill=(0, 0, 0, 0),
    )
    base.alpha_composite(layer.resize(logo.size, Image.Resampling.LANCZOS))
    return base


def dark_variant(logo: Image.Image) -> Image.Image:
    """The same logo with the navy parts light, for dark backgrounds (green and terracotta stay)."""
    arr = np.asarray(logo).astype(np.float32)
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    navy = (b > r + 18) & (lum < 120)
    tone = np.clip(0.93 + (lum - 40.0) / 500.0, 0.92, 1.0)[..., None]
    arr[..., :3] = np.where(navy[..., None], np.array([234.0, 241.0, 250.0]) * tone, arr[..., :3])
    return Image.fromarray(arr.astype(np.uint8), "RGBA")


def fit(logo: Image.Image, width: int) -> Image.Image:
    return logo.resize((width, round(logo.height * width / logo.width)), Image.Resampling.LANCZOS)


def badge(logo: Image.Image, size: int, *, rounded: bool, share: float) -> Image.Image:
    """The logo centred on a warm-beige square; ``share`` is the logo's share of the width."""
    s = size * 4
    canvas = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    if rounded:
        draw.rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * 0.22), fill=BEIGE)
    else:
        draw.rectangle([0, 0, s, s], fill=BEIGE)
    mark = fit(logo, round(s * share))
    mark.thumbnail((round(s * share), round(s * share)), Image.Resampling.LANCZOS)
    canvas.alpha_composite(mark, ((s - mark.width) // 2, (s - mark.height) // 2))
    return canvas.resize((size, size), Image.Resampling.LANCZOS)


def save_small(image: Image.Image, path: Path) -> None:
    """Save with 256 colours: looks the same, a sixth of the size (it loads on every visit)."""
    if image.mode == "RGB":
        image = image.convert("RGBA")
    image.quantize(colors=256, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE).save(
        path, optimize=True
    )


def main() -> None:
    logo = redraw_x_as_drone(cut_out(Image.open(SOURCE)))
    dark = dark_variant(logo)
    logo.save(ROOT / "branding" / "logo.png", optimize=True)  # the full-quality masters
    dark.save(ROOT / "branding" / "logo-dark.png", optimize=True)
    for folder in (APP_ASSETS, PHONE / "img"):
        folder.mkdir(parents=True, exist_ok=True)
        save_small(fit(logo, 320), folder / "logo.png")
        save_small(fit(dark, 320), folder / "logo-dark.png")
    save_small(badge(logo, 64, rounded=True, share=0.72), APP_ASSETS / "favicon.png")
    icons = PHONE / "icons"
    icons.mkdir(parents=True, exist_ok=True)
    save_small(badge(logo, 64, rounded=True, share=0.72), icons / "favicon.png")
    save_small(badge(logo, 192, rounded=True, share=0.72), icons / "icon-192.png")
    save_small(badge(logo, 512, rounded=True, share=0.72), icons / "icon-512.png")
    # maskable: full bleed, the logo inside the safe zone (a phone may crop it to a circle)
    save_small(badge(logo, 512, rounded=False, share=0.56), icons / "icon-maskable-512.png")
    # iPhones round the corners themselves and want an opaque square
    badge(logo, 180, rounded=False, share=0.66).convert("RGB").save(
        icons / "apple-touch-icon.png", optimize=True
    )


if __name__ == "__main__":
    main()
