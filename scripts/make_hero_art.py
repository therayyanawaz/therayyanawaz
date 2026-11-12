#!/usr/bin/env python3
"""
Turn assets/hero.png into the small JPEG embedded in the hero card.

An SVG shown through <img> can only carry embedded data, so the artwork is
cropped to its sticker, scaled to the hero's art slot and re-encoded small.
The background is painted to the card colour so the JPEG edges disappear.

    python scripts/make_hero_art.py      # writes assets/hero-art.jpg
"""
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "assets" / "hero.png"
OUT = ROOT / "assets" / "hero-art.jpg"

CARD = (23, 23, 23)      # #171717, the hero card fill
BOX = (330, 352)         # the art slot inside the 880x432 card
QUALITY = 86


def main():
    im = Image.open(SRC).convert("RGB")

    # trim the flat background: anything within 26 levels of the corner pixel
    bg = Image.new("RGB", im.size, im.getpixel((0, 0)))
    diff = ImageChops.difference(im, bg).convert("L").point(lambda v: 255 if v > 26 else 0)
    bbox = diff.getbbox()
    if bbox:
        pad = 12
        im = im.crop(
            (
                max(0, bbox[0] - pad),
                max(0, bbox[1] - pad),
                min(im.width, bbox[2] + pad),
                min(im.height, bbox[3] + pad),
            )
        )

    scale = min(BOX[0] / im.width, BOX[1] / im.height)
    art = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)

    canvas = Image.new("RGB", art.size, CARD)
    canvas.paste(art, (0, 0))
    canvas.save(OUT, "JPEG", quality=QUALITY, optimize=True, progressive=True)
    print(f"wrote {OUT.relative_to(ROOT)} {canvas.size[0]}x{canvas.size[1]} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
