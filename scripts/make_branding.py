# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Make every logo file from the original picture (``branding/logo-source.jpg``).

The original has a pale background. This cuts the logo out (with clean, halo-free edges),
makes a dark-mode variant (the navy parts become light, so the X shows on a dark page) and
writes the sizes the screens, the browser tab and the phone's home screen need.

Run ``python scripts/make_branding.py`` to recreate the files. Needs numpy and Pillow.
"""

from __future__ import annotations

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
    logo = cut_out(Image.open(SOURCE))
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
