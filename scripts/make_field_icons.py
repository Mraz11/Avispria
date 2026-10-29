# SPDX-FileCopyrightText: 2026 Avispria contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Draw the field page's icons (a drone seen from above) with Pillow.

Run ``python scripts/make_field_icons.py`` to recreate field-page/icons/*.png.
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

GREEN, WHITE = (46, 125, 50, 255), (255, 255, 255, 255)
OUT = Path(__file__).resolve().parents[1] / "field-page" / "icons"


def drone(size: int, *, rounded: bool, glyph: float) -> Image.Image:
    """A quadcopter from above on a green square; ``glyph`` is its share of the width."""
    s = size * 4  # draw large, then shrink: smooth edges
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if rounded:
        d.rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * 0.22), fill=GREEN)
    else:
        d.rectangle([0, 0, s, s], fill=GREEN)
    c, reach, radius, line = s / 2, s * glyph * 0.36, s * glyph * 0.21, max(4, int(s * 0.034))
    for sx in (-1, 1):
        for sy in (-1, 1):
            x, y = c + sx * reach, c + sy * reach
            gap = math.hypot(reach, reach)  # centre to rotor centre
            ex, ey = c + sx * reach * (1 - radius / gap), c + sy * reach * (1 - radius / gap)
            d.line([(c, c), (ex, ey)], fill=WHITE, width=line)  # the arm stops at the ring
            d.ellipse([x - radius, y - radius, x + radius, y + radius], outline=WHITE, width=line)
    body = s * glyph * 0.12
    d.ellipse([c - body, c - body, c + body, c + body], fill=WHITE)
    lens = body * 0.45
    d.ellipse([c - lens, c - lens, c + lens, c + lens], fill=GREEN)
    return img.resize((size, size), Image.Resampling.LANCZOS)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    drone(192, rounded=True, glyph=0.74).save(OUT / "icon-192.png", optimize=True)
    drone(512, rounded=True, glyph=0.74).save(OUT / "icon-512.png", optimize=True)
    # maskable: full bleed, glyph inside the safe zone (the phone may crop to a circle)
    drone(512, rounded=False, glyph=0.52).save(OUT / "icon-maskable-512.png", optimize=True)
    # iPhones round the corners themselves and want an opaque square
    drone(180, rounded=False, glyph=0.66).convert("RGB").save(
        OUT / "apple-touch-icon.png", optimize=True
    )


if __name__ == "__main__":
    main()
