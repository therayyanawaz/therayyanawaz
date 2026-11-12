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
PORTRAIT = ROOT / "assets" / "portrait.jpg"

STATIC = os.environ.get("STATIC", "").strip().lower() in {"1", "true", "yes"}
USER = os.environ.get("GH_PROFILE_USER", "therayyanawaz")
SITE = os.environ.get("GH_PROFILE_SITE", "https://therayyanawaz.co.in")

# Palette and type lifted from therayyanawaz.co.in
BG = "#0a0a0a"
CARD = "#171717"
LINE = "#ffffff1a"
INK = "#fafafa"
MUTED = "#a1a1a1"
DIM = "#737373"
BRAND = "#54a2ff"
BRAND_DEEP = "#1447e6"
RED = "#fb2c36"
AMBER = "#ffd236"

LANG_COLORS = {
    "TypeScript": "#3178c6",
    "JavaScript": "#f1e05a",
    "Python": "#3572a5",
    "Markdown": "#8b949e",
    "Shell": "#89e051",
    "HTML": "#e34c26",
    "CSS": "#563d7c",
    "Go": "#00add8",
    "Rust": "#dea584",
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
.a{animation:up .9s cubic-bezier(.22,1,.36,1) backwards}
.al{animation:from-left .9s cubic-bezier(.22,1,.36,1) backwards}
.af{animation:fade 1.1s ease backwards}
.ag{animation:grow 1.1s cubic-bezier(.22,1,.36,1) backwards}
.lift{animation:lift 1s cubic-bezier(.16,1.14,.32,1) backwards;transform-box:fill-box;transform-origin:center}
.bar{transform-box:fill-box;transform-origin:center bottom}
.dot{animation:pulse 2.4s ease-in-out infinite}
.motion{display:inline}
.still{display:none}
@keyframes up{from{opacity:0;transform:translateY(12px)}}
@keyframes from-left{from{opacity:0;transform:translateX(-14px)}}
@keyframes fade{from{opacity:0}}
@keyframes grow{from{transform:scaleY(0)}}
@keyframes lift{from{opacity:0;transform:translateY(26px) rotate(-2.5deg)}}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
@media (prefers-reduced-motion:reduce){
  *{animation:none!important}
  .motion{display:none!important}
  .still{display:inline!important}
}
"""

if STATIC:
    BASE_CSS += ".a,.al,.af,.ag,.lift,.bar,.dot{animation:none!important}.motion{display:none!important}.still{display:inline!important}"


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
    shell = (
        f'<rect width="{width}" height="{height}" rx="18" fill="{CARD}"/>\n'
        f'<rect x=".5" y=".5" width="{width - 1}" height="{height - 1}" rx="17.5" fill="none" stroke="{LINE}"/>\n'
        f'<rect width="{width}" height="{height}" rx="18" fill="url(#glow)"/>'
        if card
        else ""
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{esc(title)}">
<title>{esc(title)}</title>
<defs>
<linearGradient id="glow" x1="0" y1="0" x2="0" y2="1">
<stop offset="0" stop-color="{BRAND}" stop-opacity=".08"/>
<stop offset=".7" stop-color="{BRAND}" stop-opacity="0"/>
</linearGradient>
{defs}
</defs>
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

PORTRAIT_BOX = (626, 34, 210, 232)


def portrait_panel():
    """Optional portrait: a surface-finished duotone, embedded so the SVG stays one file."""
    if not PORTRAIT.exists():
        return "", ""
    px, py, pw, ph = PORTRAIT_BOX
    b64 = base64.b64encode(PORTRAIT.read_bytes()).decode("ascii")
    defs = (
        f'<clipPath id="portraitClip"><rect x="{px}" y="{py}" width="{pw}" height="{ph}" rx="14"/></clipPath>'
        '<pattern id="scan" width="4" height="4" patternUnits="userSpaceOnUse">'
        f'<rect width="4" height="2" fill="{BG}" opacity=".14"/></pattern>'
        '<linearGradient id="portraitFade" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{BRAND}" stop-opacity=".14"/>'
        f'<stop offset=".5" stop-color="{BRAND}" stop-opacity="0"/>'
        f'<stop offset="1" stop-color="{CARD}" stop-opacity=".62"/></linearGradient>'
    )
    body = f"""
<g clip-path="url(#portraitClip)">
  <image class="develop" href="data:image/jpeg;base64,{b64}" x="{px}" y="{py}" width="{pw}" height="{ph}"
         preserveAspectRatio="xMidYMid slice" style="animation-delay:.4s"/>
  <rect x="{px}" y="{py}" width="{pw}" height="{ph}" fill="url(#portraitFade)"/>
  <rect x="{px}" y="{py}" width="{pw}" height="{ph}" fill="url(#scan)"/>
</g>
<rect x="{px}" y="{py}" width="{pw}" height="{ph}" rx="14" fill="none" stroke="{LINE}"/>
"""
    return body, defs


def hero(stats):
    w, h = 880, 300
    portrait, portrait_defs = portrait_panel()

    shine = (
        ""
        if STATIC
        else '<g mask="url(#nawazMask)" class="motion"><rect x="40" y="130" width="430" height="68" fill="url(#shineGrad)"/></g>'
    )

    defs = (
        portrait_defs
        + f'<linearGradient id="shineGrad" x1="0" y1="0" x2="1" y2="0" gradientTransform="translate(-1 0)">'
        f'<stop offset="0" stop-color="#ffffff" stop-opacity="0"/>'
        f'<stop offset=".5" stop-color="#ffffff" stop-opacity=".85"/>'
        f'<stop offset="1" stop-color="#ffffff" stop-opacity="0"/>'
        + (
            ""
            if STATIC
            else f'<animate attributeName="gradientTransform" begin="1.6s" dur="6.5s" repeatCount="indefinite" '
            f'values="translate(-1 0);translate(2.2 0);translate(2.2 0)" calcMode="spline" '
            f'keySplines=".4 0 .6 1;0 0 1 1" keyTimes="0;.45;1"/>'
        )
        + f"</linearGradient>"
        f'<mask id="nawazMask"><text x="40" y="184" font-size="54" font-family="Instrument Serif" '
        f'font-style="italic" fill="#ffffff">Nawaz</text></mask>'
    )

    body = f"""
<g class="af" style="animation-delay:.05s">
  <rect x="40" y="49" width="8" height="8" rx="2" fill="{BRAND}"/>
  <text x="58" y="57" font-size="9.5" fill="{DIM}" letter-spacing="2.4" class="mono">BACKEND ENGINEER \u00b7 SECURITY AUTOMATION</text>
</g>
<text x="40" y="134" font-size="54" fill="{INK}" letter-spacing="-.6" class="serif a" style="animation-delay:.16s">Md Rayyan</text>
<text x="40" y="188" font-size="54" fill="{BRAND}" letter-spacing="-.6" font-style="italic" class="serif a" style="animation-delay:.3s">Nawaz</text>
{shine}
<g class="a" style="animation-delay:.5s">
  <text x="40" y="224" font-size="15.5" fill="{MUTED}">I build secure, scalable backends and</text>
  <text x="40" y="246" font-size="15.5" fill="{MUTED}">the tooling that keeps them safe.</text>
</g>
<g class="af" style="animation-delay:.82s">
  <text x="40" y="280" font-size="10.5" fill="{MUTED}" letter-spacing=".6" class="mono">therayyanawaz.co.in</text>
  <text x="196" y="280" font-size="11" fill="{BRAND}" class="mono">\u2197</text>
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
<rect width="280" height="160" rx="18" fill="{bg}"/>
<g class="lift" style="animation-delay:{delay}s">
  <text x="24" y="36" font-size="8.5" fill="{soft}" letter-spacing="2.6" class="mono">{esc(label)}</text>
  {arrow_path(234, 28, 16, fg, 1.5)}
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
        color = BRAND if is_peak else "#e9e9e9"
        delay = 0.28 + i * 0.05
        bars.append(
            f'<rect class="ag bar" style="animation-delay:{delay:.2f}s;transform-origin:center bottom" '
            f'x="{x:.1f}" y="{y:.1f}" width="{bar_w}" height="{bar_h:.1f}" rx="3" fill="{color}"/>'
            f'<text x="{x + bar_w / 2:.1f}" y="266" font-size="8.5" fill="{DIM}" text-anchor="middle" '
            f'letter-spacing="1" class="mono a" style="animation-delay:{delay + 0.25:.2f}s">{m["label"]}</text>'
        )
        if is_peak:
            bars.append(
                f'<text x="{x + bar_w / 2:.1f}" y="{y - 9:.1f}" font-size="9" fill="{BRAND}" '
                f'text-anchor="middle" class="mono a" style="animation-delay:{delay + 0.45:.2f}s">{fmt(m["count"])}</text>'
            )

    busiest = stats["busiest_day"]
    busiest_label = f"{busiest.strftime('%b')} {busiest.day}" if busiest else "\u2014"

    def stat(y, value, label):
        return (
            f'<text x="620" y="{y}" font-size="30" fill="{INK}" letter-spacing="-.4" class="serif">{esc(value)}</text>'
            f'<text x="620" y="{y + 20}" font-size="8" fill="{DIM}" letter-spacing="2" class="mono">{label}</text>'
        )

    body = f"""
<text x="40" y="48" font-size="9" fill="{DIM}" letter-spacing="2.4" class="mono af" style="animation-delay:.02s">THE LAST 12 MONTHS ON GITHUB</text>
<text x="40" y="104" font-size="40" fill="{INK}" letter-spacing="-.5" class="serif a" style="animation-delay:.1s" xml:space="preserve">{fmt(stats["total"])}<tspan font-style="italic" fill="{BRAND}"> contributions</tspan></text>
{''.join(bars)}
<g class="af" style="animation-delay:.6s">
  <line x1="600" y1="66" x2="600" y2="252" stroke="{LINE}"/>
  <line x1="620" y1="126" x2="840" y2="126" stroke="{LINE}"/>
  <line x1="620" y1="196" x2="840" y2="196" stroke="{LINE}"/>
</g>
<g class="a" style="animation-delay:.75s">
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
    w, h = 880, 128
    name = repo.get("name", "")
    desc = truncate(repo.get("description") or "Open source project", 108)
    language = repo.get("language") or ""
    stars = int(repo.get("stars") or 0)
    accent = LANG_COLORS.get(language, BRAND)
    meta = f'<circle cx="44" cy="100" r="3.5" fill="{accent}"/>'
    meta += f'<text x="56" y="103.5" font-size="10.5" fill="{MUTED}">{esc(language or "Code")}</text>'
    if stars:
        star_x = 40 + 24 + len(language or "Code") * 6.6
        meta += (
            f'<path d="M{star_x + 5} 96.5 l1.9 3.9 4.3.6-3.1 3 .7 4.3-3.8-2-3.8 2 .7-4.3-3.1-3 4.3-.6z" fill="{DIM}"/>'
            f'<text x="{star_x + 16}" y="103.5" font-size="10.5" fill="{MUTED}">{fmt(stars)}</text>'
        )
    body = f"""
<g class="al" style="animation-delay:{delay}s">
  <text x="40" y="42" font-size="8.5" fill="{accent}" letter-spacing="2.4" class="mono">{index:02d}</text>
  <text x="70" y="45" font-size="24" fill="{INK}" letter-spacing="-.3" class="serif">{esc(name)}</text>
  <text x="40" y="72" font-size="12.5" fill="{MUTED}">{esc(desc)}</text>
  {meta}
  <text x="840" y="42" font-size="8" fill="{DIM}" letter-spacing="2" text-anchor="end" class="mono">OPEN SOURCE</text>
</g>
<g class="af" style="animation-delay:{delay + 0.2:.2f}s">
  <circle cx="806" cy="82" r="17" fill="none" stroke="{LINE}"/>
  <path d="M799 82 h14 m-5 -5 l5 5 l-5 5" fill="none" stroke="{accent}" stroke-width="1.5"
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

    palette = ["#262626", blend(CARD, BRAND, 0.3), blend(CARD, BRAND, 0.55), blend(CARD, BRAND, 0.8), BRAND]

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
        cells.append(f'<g class="af" style="animation-delay:{delay:.2f}s">{"".join(col)}</g>')

    # Month labels under the first column of each month
    labels = []
    seen = set()
    for wi, week in enumerate(weeks):
        for day in week:
            if day.day <= 7 and day <= end and (day.year, day.month) not in seen:
                seen.add((day.year, day.month))
                if x0 + wi * step < 764:
                    labels.append(
                        f'<text x="{x0 + wi * step}" y="205" font-size="8.5" fill="{DIM}" letter-spacing="1.2" '
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
<text x="40" y="56" font-size="26" fill="{INK}" letter-spacing="-.3" class="serif af" style="animation-delay:.02s">Every day, <tspan font-style="italic" fill="{BRAND}">in blue</tspan></text>
<g class="af" style="animation-delay:.1s">
  <text x="840" y="54" font-size="8.5" fill="{DIM}" letter-spacing="2" text-anchor="end" class="mono">REFRESHED DAILY</text>
  <text x="840" y="70" font-size="8" fill="{DIM}" letter-spacing="1.6" text-anchor="end" class="mono">{esc(span)}</text>
</g>
{''.join(labels)}
{''.join(cells)}
<g class="af" style="animation-delay:1.35s">
  <text x="706" y="226" font-size="8" fill="{DIM}" letter-spacing="1.6" text-anchor="end" class="mono">LESS</text>
  {legend}
  <text x="800" y="226" font-size="8" fill="{DIM}" letter-spacing="1.6" class="mono">MORE</text>
</g>
"""
    return svg(w, h, "Contribution graph in the site's blue", body, faces=("dm", "serif", "mono"))


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
            BRAND_DEEP, "#ffffff", "#cfe0ff", 0.55,
        ),
        "tile-security.svg": tile(
            "SECURITY", "Security", " tooling", ["Scanners and CI checks that", "keep supply chains honest."],
            RED, "#ffffff", "#ffe0e2", 0.67,
        ),
        "tile-automation.svg": tile(
            "AUTOMATION", "Runs", " itself", ["GitHub Actions, CLIs and", "repeatable workflows."],
            AMBER, "#171717", "#5c4a08", 0.79,
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
