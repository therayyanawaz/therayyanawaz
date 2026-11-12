#!/usr/bin/env python3
"""
Optional: turn a portrait photo into the ASCII art the hero card prints in.

    python scripts/make_portrait.py path/to/photo.jpg

Writes assets/portrait.txt: 185 columns x 96 rows, the grid the hero prints
(7.2px mono stretched to 800 units, one row every 18ms). The photo is cropped to
head and shoulders and pushed high-key, so paper stays blank and the subject's
dark areas become the densest characters.
Delete the file and the hero lays out without a portrait.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "portrait.txt"
COLS, ROWS = 185, 96
RAMP = "@%#*+=-:. "  # dense ink -> paper


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("usage: python scripts/make_portrait.py <photo>")
    image = Image.open(sys.argv[1]).convert("L")
    width, height = image.size
    image = image.crop(
        (int(width * 0.29), int(height * 0.07), int(width * 0.73), int(height * 0.565))
    )
    image = ImageOps.autocontrast(image, cutoff=1)

    # High-key curve: lift the mids so skin and background read as paper.
    image = image.point(lambda v: int(min(1.0, max(0.0, (v / 255 - 0.08) / 0.70) ** 0.62) * 255))

    # A little paper on each side keeps the head from touching the edge.
    canvas = Image.new("L", (int(image.width * 1.12), image.height), 255)
    canvas.paste(image, (int(image.width * 0.06), 0))
    image = canvas.resize((COLS, ROWS), Image.LANCZOS)
    pixels = image.load()

    rows = []
    for y in range(ROWS):
        line = ""
        for x in range(COLS):
            value = pixels[x, y] / 255
            ink = max(0.0, min(1.0, (0.82 - value) / 0.66))
            line += RAMP[min(len(RAMP) - 1, int((1 - ink) * (len(RAMP) - 1) + 0.5))]
        rows.append(line)  # trailing spaces matter: the card stretches the row to fit

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({COLS}x{ROWS})")


if __name__ == "__main__":
    main()
