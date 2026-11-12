#!/usr/bin/env python3
"""
Render the GitHub profile README as a stack of animated SVG cards.

Every card is a self-contained SVG: fonts are subset with pyftsubset and
embedded as base64 WOFF data URIs, and all motion is CSS keyframes or SMIL.
GitHub shows these files through <img>, so nothing here depends on scripts,
external stylesheets or network requests.

Contribution data comes from data/contributions.json, which the scheduled
Action refreshes before calling this script.

Usage:
    python scripts/render_readme_cards.py
    STATIC=1 python scripts/render_readme_cards.py   # final frame, for screenshots
"""

from __future__ import annotations

import base64
import calendar
import json
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path
from xml.sax.saxutils import escape as esc

ROOT = Path(__file__).resolve().parent.parent
CARDS = ROOT / "cards"
FONT_DIR = ROOT / "fonts"
FONT_CACHE = ROOT / ".cache" / "fonts"
DATA = ROOT / "data" / "contributions.json"
PORTRAIT = ROOT / "assets" / "portrait.txt"

STATIC = os.environ.get("STATIC", "").strip().lower() in {"1", "true", "yes"}
USER = os.environ.get("GH_PROFILE_USER", "therayyanawaz")
SITE = os.environ.get("GH_PROFILE_SITE", "https://therayyanawaz.co.in")

# Tokens taken from the reference design
CARD = "#f3f3f1"
INK = "#111111"
BODY = "#3a3a3c"
MUTED = "#6e6e73"
DIM = "#8e8e93"
LINE = "#00000014"
BRAND = "#2f55ff"
TILE_BLUE = "#2447f5"
TILE_RED = "#f4432c"
TILE_YELLOW = "#ffc61a"

LANG_COLORS = {
    "TypeScript": "#3178c6",
    "JavaScript": "#b8a400",
    "Python": "#3572a5",
    "Markdown": "#6e6e73",
    "Shell": "#4d8a2f",
    "HTML": "#e34c26",
    "CSS": "#563d7c",
    "Go": "#0087a8",
    "Rust": "#a35a32",
}

SUBSET_TEXT = "".join(chr(c) for c in range(32, 127)) + "\u2013\u2014\u00b7\u2192\u2190\u2197\u2022\u2019\u201c\u201d\u2026"

# ---------------------------------------------------------------------------
# Fonts
# ---------------------------------------------------------------------------


def subset_font(src: Path) -> bytes:
    """Subset one font with pyftsubset and return the WOFF bytes."""
    FONT_CACHE.mkdir(parents=True, exist_ok=True)
    out = FONT_CACHE / f"{src.stem}-subset.woff"
    if not out.exists():
        subprocess.run(
            [
                sys.executable,
                "-m",
                "fontTools.subset",
                str(src),
                f"--text={SUBSET_TEXT}",
                f"--output-file={out}",
                "--flavor=woff",
                "--layout-features=kern,liga",
                "--no-hinting",
                "--desubroutinize",
                "--drop-tables+=DSIG",
            ],
            check=True,
            capture_output=True,
        )
    return out.read_bytes()


def font_face(family: str, filename: str, style: str = "normal", weight: str = "400") -> str:
    src = FONT_DIR / filename
    try:
        data = subset_font(src)
    except Exception as exc:  # fontTools missing: fall back to the full face
        print(f"  ! pyftsubset failed for {filename} ({exc}); embedding the full font", file=sys.stderr)
        data = src.read_bytes()
    fmt = "woff2" if data[:4] == b"wOF2" else "woff"
    b64 = base64.b64encode(data).decode("ascii")
    return (
        f"@font-face{{font-family:'{family}';font-style:{style};font-weight:{weight};"
        f"src:url(data:font/{fmt};base64,{b64}) format('{fmt}')}}"
    )


FONT_FACES = {
    "dm": font_face("DM Sans", "DMSans.woff2", weight="100 1000"),
    "serif": font_face("Instrument Serif", "InstrumentSerif.woff2"),
    "serif-italic": font_face("Instrument Serif", "InstrumentSerif-Italic.woff2", style="italic"),
    "mono": font_face("Geist Mono", "GeistMono.woff2", weight="100 900"),
}

BASE_CSS = """
text{font-family:'DM Sans',system-ui,-apple-system,'Segoe UI',sans-serif}
.serif{font-family:'Instrument Serif',Georgia,'Times New Roman',serif}
.mono{font-family:'Geist Mono',ui-monospace,SFMono-Regular,Menlo,monospace}
.r{animation:up .9s cubic-bezier(.22,1,.36,1) backwards}
.l{animation:from-left .9s cubic-bezier(.22,1,.36,1) backwards}
.f{animation:fade 1.1s ease backwards}
.g{animation:grow 1.1s cubic-bezier(.22,1,.36,1) backwards}
.lift{animation:lift 1s cubic-bezier(.16,1.14,.32,1) backwards;transform-box:fill-box;transform-origin:center}
.bar{transform-box:fill-box;transform-origin:center bottom}
.live{animation:pulse 2.4s ease-in-out infinite}
.motion{display:inline}
.still{display:none}
@keyframes up{from{opacity:0;transform:translateY(14px)}}
@keyframes from-left{from{opacity:0;transform:translateX(-14px)}}
@keyframes fade{from{opacity:0}}
@keyframes grow{from{transform:scaleY(0)}}
@keyframes lift{from{opacity:0;transform:translateY(26px) rotate(-2.5deg)}}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.35}}
@media (prefers-reduced-motion:reduce){
  *{animation:none!important}
  .motion{display:none!important}
  .still{display:inline!important}
}
"""

if STATIC:
    BASE_CSS += ".r,.l,.f,.g,.lift,.bar,.live{animation:none!important}.motion{display:none!important}.still{display:inline!important}"


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def blend(color_a: str, color_b: str, t: float) -> str:
    a = [int(color_a[i : i + 2], 16) for i in (1, 3, 5)]
    b = [int(color_b[i : i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def fmt(n: int) -> str:
    return f"{n:,}"


def truncate(text: str, limit: int) -> str:
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0]
    return (cut or text[: limit - 1]) + "\u2026"


def svg(
    width: int,
    height: int,
    title: str,
    body: str,
    defs: str = "",
    faces=("dm", "serif", "serif-italic", "mono"),
    card: bool = True,
) -> str:
    """Wrap a card body in an SVG document with the shared style block."""
    font_css = "".join(FONT_FACES[face] for face in faces)
    shell = f'<rect width="{width}" height="{height}" rx="14" fill="{CARD}"/>' if card else ""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{esc(title)}">
<title>{esc(title)}</title>
<defs>{defs}</defs>
<style>{font_css}{BASE_CSS}</style>
{shell}
{body}
</svg>
"""


def text(x, y, value, size=12, fill=MUTED, cls="", extra="", anchor="start"):
    attrs = f'x="{x}" y="{y}" font-size="{size}" fill="{fill}"'
    if cls:
        attrs += f' class="{cls}"'
    if anchor != "start":
        attrs += f' text-anchor="{anchor}"'
    if extra:
        attrs += f" {extra}"
    return f'<text {attrs}>{esc(value)}</text>'


def arrow_path(x1: int, y: int, length: int, color: str, width: float = 1.6) -> str:
    return (
        f'<path d="M{x1} {y} h{length} m-7 -6 l7 6 l-7 6" fill="none" stroke="{color}" '
        f'stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round"/>'
    )


# ---------------------------------------------------------------------------
# Contribution statistics
# ---------------------------------------------------------------------------


def load_stats():
    if not DATA.exists():
        sys.exit(f"missing {DATA}; run scripts/fetch_contributions.py first")
    raw = json.loads(DATA.read_text(encoding="utf-8"))
    days = sorted((date.fromisoformat(d["date"]), int(d["count"])) for d in raw["days"])
    counts = dict(days)
    total = sum(counts.values())
    active = sum(1 for c in counts.values() if c > 0)

    best = 0
    run = 0
    for _, c in days:
        run = run + 1 if c > 0 else 0
        best = max(best, run)

    # Walk back from the newest day. A zero today should not wipe out the streak
    # before the calendar refreshes, so allow one empty day of grace.
    end = len(days) - 1
    if end >= 0 and days[end][1] == 0:
        end -= 1
    current = 0
    while end >= 0 and days[end][1] > 0:
        current += 1
        end -= 1

    busiest_day, busiest_count = max(days, key=lambda d: (d[1], d[0])) if days else (None, 0)

    month_sums: dict[tuple[int, int], int] = {}
    for day, c in days:
        month_sums[(day.year, day.month)] = month_sums.get((day.year, day.month), 0) + c
    last = days[-1][0] if days else date.today()
    months = []
    y, m = last.year, last.month
    for _ in range(12):
        months.append({"year": y, "month": m, "label": calendar.month_abbr[m], "count": month_sums.get((y, m), 0)})
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    months.reverse()

    peak = max(counts.values()) if counts else 0
    levels = {}
    for day, count in counts.items():
        levels[day] = 0 if count <= 0 or not peak else 1 + min(3, int(((count / peak) ** 0.55) * 3.999))

    return {
        "ordered": days,
        "total": total,
        "active": active,
        "current": current,
        "best": best,
        "busiest_day": busiest_day,
        "busiest_count": busiest_count,
        "months": months,
        "levels": levels,
        "repos": raw.get("repos", []),
        "updated": raw.get("generated_at", ""),
    }


# ---------------------------------------------------------------------------
# Hero
# ---------------------------------------------------------------------------

PORTRAIT_ORIGIN = (520, 46)
PORTRAIT_SCALE = 0.41


def read_portrait():
    if not PORTRAIT.exists():
        return []
    return [line for line in PORTRAIT.read_text(encoding="utf-8").splitlines()]


def hero(stats):
    w, h = 880, 420
    rows = read_portrait()

    portrait = ""
    if rows:
        ox, oy = PORTRAIT_ORIGIN
        lines = []
        for i, row in enumerate(rows):
            delay = 0.25 + i * 0.018
            lines.append(
                f'<text class="f" style="animation-delay:{delay:.3f}s;animation-duration:.35s" xml:space="preserve" '
                f'x="20" y="{43.2 + i * 8.3:.1f}" font-size="7.2" fill="{INK}" '
                f'textLength="800" lengthAdjust="spacing">{esc(row)}</text>'
            )
        portrait = (
            f'<g transform="translate({ox} {oy}) scale({PORTRAIT_SCALE}) translate(-20 -37)">'
            f'{"".join(lines)}</g>'
        )

    shine = (
        ""
        if STATIC
        else '<g mask="url(#nawazMask)" class="motion"><rect x="40" y="210" width="520" height="100" fill="url(#shine)"/></g>'
    )

    defs = (
        '<linearGradient id="shine" x1="0" y1="0" x2="1" y2="0" gradientTransform="translate(-1 0)">'
        '<stop offset="0" stop-color="#2f55ff" stop-opacity="0"/>'
        '<stop offset=".5" stop-color="#2f55ff" stop-opacity="1"/>'
        '<stop offset="1" stop-color="#2f55ff" stop-opacity="0"/>'
        + (
            ""
            if STATIC
            else '<animate attributeName="gradientTransform" values="translate(-1 0);translate(3 0);translate(3 0)" '
            'keyTimes="0;.45;1" dur="7s" begin="1.6s" repeatCount="indefinite"/>'
        )
        + "</linearGradient>"
        f'<mask id="nawazMask"><text x="44" y="290" font-size="92" font-family="Instrument Serif" '
        f'font-style="italic" letter-spacing="-2" fill="#ffffff">Nawaz</text></mask>'
    )

    body = f"""
<g class="f" style="animation-delay:0s">
  <rect class="live" x="48" y="49" width="8" height="8" rx="2" fill="{BRAND}"/>
  <text x="66" y="57" font-size="12" letter-spacing="1" fill="{MUTED}" class="mono">BACKEND ENGINEER \u00b7 SECURITY AUTOMATION</text>
</g>
<text class="serif r" style="animation-delay:.15s" x="44" y="190" font-size="92" letter-spacing="-2" fill="{INK}">Md Rayyan</text>
<text class="serif r" style="animation-delay:.30s" x="44" y="290" font-size="92" letter-spacing="-2" font-style="italic" fill="{INK}">Nawaz</text>
{shine}
<g class="r" style="animation-delay:.55s">
  <text x="48" y="338" font-size="18" fill="{BODY}">I build secure, scalable backends,</text>
  <text x="48" y="365" font-size="18" fill="{BODY}">and the tooling that keeps them safe.</text>
</g>
<g class="f" style="animation-delay:.80s">
  <text x="48" y="396" font-size="13" fill="{INK}" class="mono">therayyanawaz.co.in</text>
  <text x="236" y="396" font-size="13" fill="{BRAND}" class="mono">\u2197</text>
</g>
{portrait}
"""
    return svg(w, h, "Md Rayyan Nawaz \u2014 backend engineer and security automation builder", body, defs)


# ---------------------------------------------------------------------------
# Three tiles
# ---------------------------------------------------------------------------


def tile(label, headline, italic, sub, bg, fg, soft, delay):
    w, h = 280, 160
    body = f"""
<rect width="280" height="160" rx="14" fill="{bg}"/>
<g class="lift" style="animation-delay:{delay}s">
  <text x="24" y="36" font-size="8.5" fill="{soft}" letter-spacing="2.6" class="mono">{esc(label)}</text>
  <path d="M238 28 h12 m-5 -4 l5 4 l-5 4" fill="none" stroke="{fg}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
  <text x="24" y="94" font-size="27" fill="{fg}" letter-spacing="-.3" class="serif" xml:space="preserve">{esc(headline)}<tspan font-style="italic">{esc(italic)}</tspan></text>
  <text x="24" y="122" font-size="11" fill="{soft}">{esc(sub[0])}</text>
  <text x="24" y="138" font-size="11" fill="{soft}">{esc(sub[1])}</text>
</g>
"""
    return svg(w, h, f"{label} \u2014 {headline}{italic}", body, card=False)


# ---------------------------------------------------------------------------
# Monthly activity chart
# ---------------------------------------------------------------------------


def activity(stats):
    w, h = 880, 300
    months = stats["months"]
    peak = max((m["count"] for m in months), default=0) or 1
    area_x, area_w = 40, 512
    base_y, max_h = 246, 100
    slot = area_w / 12
    bar_w = 26
    bars = []
    for i, m in enumerate(months):
        bar_h = max(3.0, (m["count"] / peak) * max_h)
        x = area_x + i * slot + (slot - bar_w) / 2
        y = base_y - bar_h
        is_peak = m["count"] == peak
        color = BRAND if is_peak else INK
        delay = 0.28 + i * 0.05
        bars.append(
            f'<rect class="g bar" style="animation-delay:{delay:.2f}s;transform-origin:center bottom" '
            f'x="{x:.1f}" y="{y:.1f}" width="{bar_w}" height="{bar_h:.1f}" rx="2" fill="{color}"/>'
            f'<text x="{x + bar_w / 2:.1f}" y="266" font-size="8.5" fill="{MUTED}" text-anchor="middle" '
            f'letter-spacing="1" class="mono f" style="animation-delay:{delay + 0.25:.2f}s">{m["label"]}</text>'
        )
        if is_peak:
            bars.append(
                f'<text x="{x + bar_w / 2:.1f}" y="{y - 9:.1f}" font-size="9" fill="{BRAND}" '
                f'text-anchor="middle" class="mono f" style="animation-delay:{delay + 0.45:.2f}s">{fmt(m["count"])}</text>'
            )

    busiest = stats["busiest_day"]
    busiest_label = f"{busiest.strftime('%b')} {busiest.day}" if busiest else "\u2014"

    def stat(y, value, label):
        return (
            f'<text x="620" y="{y}" font-size="30" fill="{INK}" letter-spacing="-.4" class="serif">{esc(value)}</text>'
            f'<text x="620" y="{y + 20}" font-size="8" fill="{MUTED}" letter-spacing="2" class="mono">{label}</text>'
        )

    body = f"""
<text x="40" y="48" font-size="9" fill="{MUTED}" letter-spacing="2.4" class="mono f" style="animation-delay:.02s">THE LAST 12 MONTHS ON GITHUB</text>
<text x="40" y="104" font-size="40" fill="{INK}" letter-spacing="-.5" class="serif r" style="animation-delay:.1s" xml:space="preserve">{fmt(stats["total"])}<tspan font-style="italic" fill="{BRAND}"> contributions</tspan></text>
{''.join(bars)}
<g class="f" style="animation-delay:.6s">
  <line x1="600" y1="66" x2="600" y2="252" stroke="{LINE}"/>
  <line x1="620" y1="126" x2="840" y2="126" stroke="{LINE}"/>
  <line x1="620" y1="196" x2="840" y2="196" stroke="{LINE}"/>
</g>
<g class="r" style="animation-delay:.75s">
  {stat(100, f"{stats['current']} days", "CURRENT STREAK")}
  {stat(170, f"{stats['active']} / 365", "DAYS WITH A COMMIT")}
  {stat(240, fmt(stats["busiest_count"]), f"BUSIEST DAY \u00b7 {busiest_label.upper()}")}
</g>
"""
    return svg(w, h, "Monthly contributions with current streak, active days and busiest day", body, faces=("dm", "serif", "mono"))


# ---------------------------------------------------------------------------
# Repo cards
# ---------------------------------------------------------------------------


def repo_card(repo, index, delay):
    w, h = 880, 124
    name = repo.get("name", "")
    desc = truncate(repo.get("description") or "Open source project", 108)
    language = repo.get("language") or ""
    stars = int(repo.get("stars") or 0)
    accent = LANG_COLORS.get(language, BRAND)
    meta = f'<circle cx="44" cy="98" r="3.5" fill="{accent}"/>'
    meta += f'<text x="56" y="101.5" font-size="10.5" fill="{BODY}">{esc(language or "Code")}</text>'
    if stars:
        star_x = 40 + 24 + len(language or "Code") * 6.6
        meta += (
            f'<path d="M{star_x + 5} 94.5 l1.9 3.9 4.3.6-3.1 3 .7 4.3-3.8-2-3.8 2 .7-4.3-3.1-3 4.3-.6z" fill="{DIM}"/>'
            f'<text x="{star_x + 16}" y="101.5" font-size="10.5" fill="{BODY}">{fmt(stars)}</text>'
        )
    body = f"""
<g class="l" style="animation-delay:{delay}s">
  <text x="40" y="41" font-size="8.5" fill="{BRAND}" letter-spacing="2.4" class="mono">{index:02d}</text>
  <text x="70" y="44" font-size="24" fill="{INK}" letter-spacing="-.3" class="serif">{esc(name)}</text>
  <text x="40" y="70" font-size="12.5" fill="{BODY}">{esc(desc)}</text>
  {meta}
  <text x="840" y="41" font-size="8" fill="{MUTED}" letter-spacing="2" text-anchor="end" class="mono">OPEN SOURCE</text>
</g>
<g class="f" style="animation-delay:{delay + 0.2:.2f}s">
  <circle cx="806" cy="78" r="17" fill="none" stroke="{LINE}"/>
  <path d="M799 78 h14 m-5 -5 l5 5 l-5 5" fill="none" stroke="{BRAND}" stroke-width="1.5"
        stroke-linecap="round" stroke-linejoin="round"/>
</g>
"""
    return svg(w, h, f"{name} \u2014 {desc}", body, faces=("dm", "serif", "mono"))


# ---------------------------------------------------------------------------
# Contribution graph
# ---------------------------------------------------------------------------


def graph(stats):
    w, h = 880, 250
    days = stats["ordered"]
    if not days:
        days = [(date.today(), 0)]
    levels = stats["levels"]

    start = days[0][0]
    start -= timedelta(days=(start.weekday() + 1) % 7)  # back to Sunday
    end = days[-1][0]
    weeks = []
    cursor = start
    while cursor <= end:
        weeks.append([cursor + timedelta(days=i) for i in range(7)])
        cursor += timedelta(days=7)
    weeks = weeks[-53:]

    palette = ["#e6e4df", "#c3cdff", "#8fa2ff", "#5a76ff", BRAND]

    step = 14
    x0, y0 = 40, 86
    cells = []
    for wi, week in enumerate(weeks):
        delay = 1.4 + wi * 0.012
        col = []
        for di, day in enumerate(week):
            if day > end:
                continue
            col.append(
                f'<rect x="{x0 + wi * step}" y="{y0 + di * step}" width="10" height="10" rx="2.5" '
                f'fill="{palette[levels.get(day, 0)]}"/>'
            )
        cells.append(f'<g class="f" style="animation-delay:{delay:.2f}s">{"".join(col)}</g>')

    labels = []
    seen = set()
    for wi, week in enumerate(weeks):
        for day in week:
            if day.day <= 7 and day <= end and (day.year, day.month) not in seen:
                seen.add((day.year, day.month))
                if x0 + wi * step < 764:
                    labels.append(
                        f'<text x="{x0 + wi * step}" y="205" font-size="8.5" fill="{MUTED}" letter-spacing="1.2" '
                        f'class="mono">{calendar.month_abbr[day.month]}</text>'
                    )
                break

    legend_x = 716
    legend = "".join(
        f'<rect x="{legend_x + i * 15}" y="218" width="10" height="10" rx="2.5" fill="{color}"/>'
        for i, color in enumerate(palette)
    )

    first = days[0][0]
    span = f"{first.strftime('%b %Y')} \u2014 {end.strftime('%b %Y')}".upper()
    body = f"""
<text x="40" y="56" font-size="26" fill="{INK}" letter-spacing="-.3" class="serif f" style="animation-delay:.02s" xml:space="preserve">Every day, <tspan font-style="italic" fill="{BRAND}">in blue</tspan></text>
<g class="f" style="animation-delay:.1s">
  <text x="840" y="54" font-size="8.5" fill="{MUTED}" letter-spacing="2" text-anchor="end" class="mono">REFRESHED DAILY</text>
  <text x="840" y="70" font-size="8" fill="{MUTED}" letter-spacing="1.6" text-anchor="end" class="mono">{esc(span)}</text>
</g>
{''.join(labels)}
{''.join(cells)}
<g class="f" style="animation-delay:1.35s">
  <text x="706" y="226" font-size="8" fill="{MUTED}" letter-spacing="1.6" text-anchor="end" class="mono">LESS</text>
  {legend}
  <text x="800" y="226" font-size="8" fill="{MUTED}" letter-spacing="1.6" class="mono">MORE</text>
</g>
"""
    return svg(w, h, "Contribution graph in blue", body, faces=("dm", "serif", "mono"))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    stats = load_stats()
    CARDS.mkdir(parents=True, exist_ok=True)

    files = {
        "hero.svg": hero(stats),
        "tile-backend.svg": tile(
            "BACKEND", "Backend", " systems", ["Node.js, TypeScript and Python", "services, APIs and data pipelines."],
            TILE_BLUE, "#ffffff", "#dbe2ff", 0.55,
        ),
        "tile-security.svg": tile(
            "SECURITY", "Security", " tooling", ["Scanners and CI checks that", "keep supply chains honest."],
            TILE_RED, "#ffffff", "#ffe3de", 0.67,
        ),
        "tile-automation.svg": tile(
            "AUTOMATION", "Runs", " itself", ["GitHub Actions, CLIs and", "repeatable workflows."],
            TILE_YELLOW, "#171717", "#5c4a08", 0.79,
        ),
        "activity.svg": activity(stats),
        "graph.svg": graph(stats),
    }

    for i, repo in enumerate(stats["repos"]):
        slug = "".join(ch if ch.isalnum() else "-" for ch in repo["name"].lower()).strip("-")
        files[f"repo-{slug}.svg"] = repo_card(repo, i + 1, 1.15 + i * 0.15)

    for name, content in files.items():
        (CARDS / name).write_text(content, encoding="utf-8")

    total_kb = sum(len(c.encode("utf-8")) for c in files.values()) / 1024
    mode = "static final frames" if STATIC else "animated"
    print(f"rendered {len(files)} cards into cards/ ({total_kb:.0f} KB, {mode})")
    for name in files:
        print(f"  cards/{name}")


if __name__ == "__main__":
    main()
