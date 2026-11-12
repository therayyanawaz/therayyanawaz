#!/usr/bin/env python3
"""
Generate the abstract image the hero prints in, as ASCII rows.

    python scripts/make_abstract.py

Writes assets/abstract.txt: 185 columns x 96 rows of a three-armed spiral drawn
procedurally. No photo is involved, so the hero stays a single self-contained SVG.
"""

from __future__ import annotations

import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "abstract.txt"
COLS, ROWS = 185, 96


def ink(x: float, y: float) -> bool:
    """True where a spiral arm runs, at a point in [-1, 1]^2."""
    radius = math.hypot(x, y) / 0.97
    if radius > 1.0:
        return False
    theta = math.atan2(y, x)
    arms = math.sin(3.0 * theta + 8.2 * radius)
    width = 0.40 + 0.12 * radius
    return abs(arms) < width


def main() -> None:
    rows = []
    for row in range(ROWS):
        y = ((row + 0.5) / ROWS) * 2 - 1
        line = ""
        for col in range(COLS):
            x = ((col + 0.5) / COLS) * 2 - 1
            line += "#" if ink(x, y) else " "
        rows.append(line)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({COLS}x{ROWS})")


if __name__ == "__main__":
    main()
