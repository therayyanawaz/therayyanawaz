#!/usr/bin/env python3
"""
Optional: turn a portrait photo into the duotone the hero card prints in.

    python scripts/make_portrait.py path/to/photo.jpg

Writes assets/portrait.jpg (~20 KB, cropped to head and shoulders, greyscale and
tinted to the site's blue). The hero embeds it as a data URI, so the SVG stays a
single file. Delete it and the hero lays out without a portrait.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageEnhance, ImageOps

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "portrait.jpg"

SHADOW = (10, 16, 24)
MID = (38, 92, 140)
LIGHT = (206, 232, 255)


def duotone(gray: Image.Image) -> Image.Image:
    stops = [(0.0, SHADOW), (0.55, MID), (1.0, LIGHT)]

    def lut(channel: int) -> list[int]:
        table = []
        for i in range(256):
            t = i / 255
            for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
                if t <= p1:
                    f = (t - p0) / (p1 - p0)
                    table.append(round(c0[channel] + (c1[channel] - c0[channel]) * f))
                    break
            else:
                table.append(LIGHT[channel])
        return table

    return Image.merge("RGB", [gray.point(lut(c)) for c in range(3)])


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("usage: python scripts/make_portrait.py <photo>")
    image = Image.open(sys.argv[1]).convert("L")
    width, height = image.size
    image = image.crop((int(width * 0.28), int(height * 0.06), int(width * 0.72), int(height * 0.55)))
    image = ImageOps.fit(image, (420, 464), Image.LANCZOS)
    image = ImageOps.autocontrast(image, cutoff=1)
    image = ImageEnhance.Contrast(image).enhance(1.08)
    image = duotone(image)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUT, "JPEG", quality=84, optimize=True, progressive=True)
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
