#!/usr/bin/env python3
"""
Render the profile README's cards as animated SVGs into cards/.

Layout and motion follow the reference profile design (paper cards, Instrument
Serif, one colour per tile, gaps baked into the SVGs so rows tile exactly),
recast in the site's dark palette. Every card is a standalone SVG shown through
<img>, so it can only use inline CSS, SMIL and fonts embedded as data URIs.

Live numbers come from data/contributions.json (fetch_contributions.py); the
hero embeds assets/hero-art.jpg, cut down by scripts/make_hero_art.py.

    python scripts/render_readme_cards.py
    STATIC=1 python scripts/render_readme_cards.py   # final frame, for screenshots
"""

from __future__ import annotations

import base64
import datetime
import json
import os
import re
import subprocess
import sys
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "contributions.json"
OUT = ROOT / "cards"
FONTS = ROOT / "fonts"
FONT_CACHE = ROOT / ".cache" / "fonts"
HERO_ART = ROOT / "assets" / "hero-art.jpg"

STATIC = bool(os.environ.get("STATIC"))

# ---- brand tokens (therayyanawaz.co.in, dark) -------------------------------
PAPER = "#171717"
PAPER_DEEP = "#262626"
INK = "#fafafa"
INK_SOFT = "#a1a1a1"
MUTED = "#737373"
RULE = "#ffffff1a"
TECH = "#54a2ff"
STUDIO = "#fb2c36"
LEARN = "#ffd236"
W = 880  # full card width, GitHub's README column at 100%

SERIF = "'Instrument Serif', Georgia, serif"
SANS = "'DM Sans', system-ui, -apple-system, sans-serif"
MONO = "'Geist Mono', ui-monospace, SFMono-Regular, Menlo, monospace"

OWNER = "therayyanawaz"
SITE = "https://therayyanawaz.co.in"

FONT_FILES = {
    "serif": ("Instrument Serif", "normal", "400", "InstrumentSerif.woff2"),
    "serif-i": ("Instrument Serif", "italic", "400", "InstrumentSerif-Italic.woff2"),
    "sans": ("DM Sans", "normal", "100 1000", "DMSans.woff2"),
    "mono": ("Geist Mono", "normal", "100 900", "GeistMono.woff2"),
}

SUBSET_TEXT = "".join(chr(c) for c in range(32, 127)) + "\u2013\u2014\u00b7\u2192\u2190\u2197\u2199\u2605\u00b7\u2019\u201c\u201d\u2026"

BASE_CSS = """
@keyframes rise{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:none}}
@keyframes fade{from{opacity:0}to{opacity:1}}
@keyframes grow{from{transform:scaleY(0)}to{transform:scaleY(1)}}
@keyframes pop{0%{opacity:0;transform:scale(.3)}70%{opacity:1;transform:scale(1.15)}100%{opacity:1;transform:none}}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.25}}
@keyframes nudge{0%,100%{transform:none}50%{transform:translateX(4px)}}
@keyframes nudgeup{0%,100%{transform:none}50%{transform:translate(3px,-3px)}}
.r{opacity:0;animation:rise .8s cubic-bezier(.2,.7,.2,1) both;transform-box:fill-box}
.f{opacity:0;animation:fade .9s ease-out both}
.g{transform-box:fill-box;transform-origin:bottom;transform:scaleY(0);animation:grow .8s cubic-bezier(.2,.7,.2,1) both}
.p{opacity:0;transform-box:fill-box;transform-origin:center;animation:pop .4s ease-out both}
.live{animation:pulse 1.6s ease-in-out infinite}
.n{transform-box:fill-box;animation:nudge 1.8s ease-in-out infinite}
.nu{transform-box:fill-box;animation:nudgeup 1.8s ease-in-out infinite}
@keyframes tilein{0%{opacity:0;transform:translateY(90px) scale(.6) rotate(-9deg)}55%{opacity:1;transform:translateY(-10px) scale(1.05) rotate(2deg)}75%{transform:translateY(3px) scale(.98) rotate(-.8deg)}90%{transform:translateY(-1px) scale(1.01) rotate(.2deg)}100%{opacity:1;transform:none}}
@keyframes slidein{from{opacity:0;transform:translateX(-26px)}to{opacity:1;transform:none}}
@keyframes arrowin{0%{opacity:0;transform:translateX(-30px)}60%{opacity:1;transform:translateX(6px)}100%{opacity:1;transform:none}}
@keyframes roll{from{transform:translateY(60px)}to{transform:none}}
@keyframes sheen{0%{transform:translateX(-260px) skewX(-20deg)}22%,100%{transform:translateX(420px) skewX(-20deg)}}
@keyframes ring{0%{opacity:.7;transform:scale(.2)}100%{opacity:0;transform:scale(2.4)}}
.ti{opacity:0;transform-box:fill-box;transform-origin:50% 60%;animation:tilein 1.1s cubic-bezier(.2,.8,.2,1) both}
.sl{opacity:0;transform-box:fill-box;animation:slidein .6s cubic-bezier(.2,.7,.2,1) both}
.ai{opacity:0;transform-box:fill-box;animation:arrowin .7s cubic-bezier(.2,.7,.2,1) both}
.ro{transform-box:fill-box;animation:roll .8s cubic-bezier(.15,.8,.2,1) both}
.sh{animation:sheen 5s ease-in-out infinite}
.rg{opacity:0;transform-box:fill-box;transform-origin:center;animation:ring 1s ease-out both}
@media (prefers-reduced-motion: reduce){.r,.f,.g,.p,.live,.n,.nu,.ti,.sl,.ai,.ro,.rg{animation:none!important;opacity:1!important;transform:none!important}.sh,.rg{display:none}}
"""


def subset_font(filename: str) -> bytes:
    src = FONTS / filename
    FONT_CACHE.mkdir(parents=True, exist_ok=True)
    out = FONT_CACHE / (src.stem + "-subset.woff")
    if not out.exists():
        subprocess.run(
            [
                sys.executable, "-m", "fontTools.subset", str(src),
                f"--text={SUBSET_TEXT}", f"--output-file={out}",
                "--flavor=woff", "--layout-features=kern,liga",
                "--no-hinting", "--desubroutinize", "--drop-tables+=DSIG",
            ],
            check=True, capture_output=True,
        )
    return out.read_bytes()


def font_face(keys):
    out = []
    for k in keys:
        fam, style, weight, fn = FONT_FILES[k]
        b64 = base64.b64encode(subset_font(fn)).decode()
        out.append(
            f"@font-face{{font-family:'{fam}';font-style:{style};font-weight:{weight};"
            f"src:url(data:font/woff;base64,{b64}) format('woff')}}"
        )
    return "".join(out)


GAP = 12          # gap between cards, baked into the SVGs (GitHub's own spacing is uneven)
BOTTOM = 12       # bottom padding per row, matching GAP
COL = W / 3       # each card in a row of three is exactly a third of the column


def svg(w, h, body, fonts, label, extra_css="", left=0, right=0, bottom=BOTTOM):
    """Card of w x h drawn at x=left inside a transparent canvas, padded so rows tile exactly."""
    if left:
        body = f'<g transform="translate({left:.3f} 0)">{body}</g>'
    w, h = w + left + right, h + bottom
    css = font_face(fonts) + BASE_CSS + extra_css
    if STATIC:  # preview: show every animation at its end state
        css += ".r,.f,.g,.p,.live,.n,.nu,.ti,.sl,.ai,.ro,.rg{animation:none!important;opacity:1!important;transform:none!important}.sh,.rg{display:none}"
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.3f}" height="{h}" viewBox="0 0 {w:.3f} {h}" '
        f'role="img" aria-label="{escape(label)}"><title>{escape(label)}</title>'
        f"<style>{css}</style>{body}</svg>"
    )


def write(name, content):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(content, encoding="utf-8")
    print(f"wrote cards/{name} ({len(content) // 1024} KB)")


def d(s):
    return f'style="animation-delay:{s:.2f}s"'


def wrap(text, n):
    lines, line = [], ""
    for word in text.split():
        if line and len(line) + 1 + len(word) > n:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    return lines + [line] if line else lines


def text_lines(x, y, lines, lh, attrs):
    return "".join(
        f'<text x="{x}" y="{y + i * lh}" {attrs}>{escape(l)}</text>' for i, l in enumerate(lines)
    )


# ---- 1 · hero -----------------------------------------------------------------
def hero():
    h = 420
    art = base64.b64encode(HERO_ART.read_bytes()).decode()
    body = f"""
<defs>
  <linearGradient id="shine" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="600" y2="0">
    <stop offset="0" stop-color="{INK}"/><stop offset=".42" stop-color="{INK}"/>
    <stop offset=".5" stop-color="{TECH}"/><stop offset=".58" stop-color="{INK}"/>
    <stop offset="1" stop-color="{INK}"/>
    <animateTransform attributeName="gradientTransform" type="translate" values="-600 0;600 0;600 0"
      keyTimes="0;.45;1" dur="7s" begin="1.6s" repeatCount="indefinite"/>
  </linearGradient>
</defs>
<rect width="{W}" height="{h}" rx="14" fill="{PAPER}"/>
<g class="f" {d(0)}>
  <rect class="live" x="48" y="49" width="8" height="8" rx="2" fill="{TECH}"/>
  <text x="66" y="57" font-family="{MONO}" font-size="12" letter-spacing="1" fill="{MUTED}">BACKEND ENGINEER · SECURITY AUTOMATION</text>
</g>
<text class="r" {d(0.15)} x="44" y="190" font-family="{SERIF}" font-size="96" letter-spacing="-2" fill="{INK}">Md Rayyan</text>
<text class="r" {d(0.3)} x="44" y="290" font-family="{SERIF}" font-style="italic" font-size="96" letter-spacing="-2" fill="url(#shine)">Nawaz</text>
<g class="r" {d(0.55)}>
  {text_lines(48, 338, ["I build secure, scalable backends,", "and the tooling that keeps them safe."], 27, f'font-family="{SANS}" font-size="18" fill="{INK_SOFT}"')}
</g>
<g class="f" {d(0.8)}>
  <text x="48" y="396" font-family="{MONO}" font-size="13" fill="{INK}">therayyanawaz.co.in</text>
  <text class="nu" x="236" y="396" font-family="{MONO}" font-size="13" fill="{TECH}">&#8599;</text>
</g>
<image class="f" style="animation-delay:.2s" x="520" y="46" width="330" height="352"
  preserveAspectRatio="xMidYMid meet" href="data:image/jpeg;base64,{art}"/>
"""
    write("hero.svg", svg(W, h, body, ["serif", "serif-i", "sans", "mono"],
                          f"Md Rayyan Nawaz. Backend engineer and security automation builder. I build secure, scalable backends, and the tooling that keeps them safe."))


# ---- 2 · world tiles ----------------------------------------------------------
TILE_W, TILE_H = 880 / 3 - 8, 210  # 285.33: two 12px gaps across the row


def count_up(num, word, x, y, attrs, begin, dur=1.1, frames=18):
    """Number counts up from 0 with SMIL <set> frames (works inside <img>), easing out."""
    m = re.match(r"([\d.]+)(.*)", num)
    tail = f' <tspan font-style="italic">{escape(word)}</tspan>'
    if not m:
        return f'<text x="{x}" y="{y}" {attrs}>{escape(num)}{tail}</text>'
    val, suf = float(m.group(1)), m.group(2)
    dec = len(m.group(1).split(".")[1]) if "." in m.group(1) else 0
    if STATIC:
        return f'<text x="{x}" y="{y}" {attrs}>{escape(num)}{tail}</text>'
    out = []
    for i in range(frames + 1):
        e = 1 - (1 - i / frames) ** 3
        txt = num if i == frames else f"{val * e:.{dec}f}{suf}"
        on = begin + dur * i / frames
        off = "" if i == frames else f'<set attributeName="opacity" to="0" begin="{begin + dur * (i + 1) / frames:.3f}s"/>'
        out.append(f'<text x="{x}" y="{y}" {attrs} opacity="0">{escape(txt)}{tail}'
                   f'<set attributeName="opacity" to="1" begin="{on:.3f}s"/>{off}</text>')
    return "".join(out)


def tile(name, label, color, on, num, word, blurb, delay, pos):
    lines = wrap(blurb, 34)
    blurb_svg = "".join(
        f'<text class="r" {d(delay + 0.75 + i * 0.1)} x="24" y="{150 + i * 20}" font-family="{SANS}" '
        f'font-size="14" fill="{on}" opacity=".92">{escape(l)}</text>'
        for i, l in enumerate(lines)
    )
    body = f"""
<defs>
  <clipPath id="card"><rect width="{TILE_W}" height="{TILE_H}" rx="14"/></clipPath>
  <clipPath id="slot"><rect x="0" y="62" width="{TILE_W}" height="62"/></clipPath>
  <linearGradient id="gl" x1="0" x2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/>
    <stop offset=".5" stop-color="#fff" stop-opacity=".35"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>
</defs>
<g class="ti" {d(delay)}>
  <g clip-path="url(#card)">
    <rect width="{TILE_W}" height="{TILE_H}" fill="{color}"/>
    <circle class="rg" {d(delay + 0.5)} cx="{TILE_W - 40}" cy="{TILE_H - 40}" r="60" fill="none" stroke="{on}" stroke-opacity=".5" stroke-width="2"/>
    <rect class="sh" style="animation-delay:{delay + 1.4:.2f}s" x="0" y="-20" width="90" height="{TILE_H + 40}" fill="url(#gl)" transform="translate(-260 0)"/>
  </g>
  <text class="sl" {d(delay + 0.35)} x="24" y="38" font-family="{MONO}" font-size="12" letter-spacing="1.2" fill="{on}">{label}</text>
  <g class="ai" {d(delay + 0.5)}><text class="n" style="animation-delay:{delay + 1.3:.2f}s" x="248" y="39" font-family="{MONO}" font-size="16" fill="{on}">&#8594;</text></g>
  <g clip-path="url(#slot)"><g class="ro" {d(delay + 0.45)}>
    {count_up(num, word, 22, 112, f'font-family="{SERIF}" font-size="44" fill="{on}"', delay + 0.45)}
  </g></g>
  {blurb_svg}
</g>
"""
    write(f"{name}.svg", svg(TILE_W, TILE_H, body, ["serif", "serif-i", "sans", "mono"],
                             f"{label}: {num} {word}. {blurb}", left=4 * pos, right=8 - 4 * pos))


# ---- 3 · activity (monthly bars) ------------------------------------------------
def activity(data):
    h = 340
    monthly = data["monthly"][-12:]
    best = max(monthly[:-1] or monthly, key=lambda m: m["total"])
    top = best["total"]
    x0, x1, base, maxh, gap = 40, 600, 292, 140, 10
    bw = (x1 - x0 - gap * (len(monthly) - 1)) / len(monthly)
    bars = []
    for i, m in enumerate(monthly):
        partial = i == len(monthly) - 1
        is_best = m is best
        bh = max(4, round(m["total"] / top * maxh))
        x = x0 + i * (bw + gap)
        fill = TECH if is_best else ("#3a3a3a" if partial else "#e9e9e9")
        label = datetime.date.fromisoformat(m["month"] + "-01").strftime("%b")
        bars.append(
            f'<rect class="g" style="animation-delay:{2.2 + i * 0.07:.2f}s" x="{x:.1f}" y="{base - bh}" '
            f'width="{bw:.1f}" height="{bh}" rx="4" fill="{fill}"><title>{label}: {m["total"]:,}</title></rect>'
            f'<text class="f" style="animation-delay:{2.2 + i * 0.07:.2f}s" x="{x + bw / 2:.1f}" y="{base + 22}" '
            f'text-anchor="middle" font-family="{MONO}" font-size="11" fill="{MUTED}">{label}</text>'
        )
        if is_best:
            bars.append(
                f'<text class="p" style="animation-delay:3.2s" x="{x + bw / 2:.1f}" y="{base - bh - 10}" '
                f'text-anchor="middle" font-family="{MONO}" font-size="11" fill="{TECH}">{m["total"]:,}</text>'
            )
    cs = data["current_streak"]["length"]
    ls = data["longest_streak"]["length"]
    streak_note = "current streak, and the longest" if cs >= ls else f"current streak, longest {ls}"
    total_days = len(data["days"])
    stats = [
        (f'{cs} <tspan font-style="italic">days</tspan>', streak_note),
        (f'{data["active_days"]}<tspan fill="#737373"> / {total_days}</tspan>', "days with a commit"),
        (f'{data["best_day"]["count"]}', "on the busiest day"),
    ]
    side = []
    for i, (big, small) in enumerate(stats):
        y = 104 + i * 92
        side.append(
            f'<g class="r" {d(2.6 + i * 0.15)}>'
            f'<text x="650" y="{y}" font-family="{SERIF}" font-size="40" fill="{INK}">{big}</text>'
            f'<text x="650" y="{y + 24}" font-family="{SANS}" font-size="13" fill="{MUTED}">{small}</text></g>'
        )
        if i < 2:
            side.append(f'<rect class="f" {d(2.6)} x="650" y="{y + 44}" width="190" height="1" fill="{RULE}"/>')
    body = f"""
<rect width="{W}" height="{h}" rx="14" fill="{PAPER}"/>
<text class="f" {d(1.9)} x="40" y="58" font-family="{MONO}" font-size="12" letter-spacing="1" fill="{MUTED}">THE LAST 12 MONTHS ON GITHUB</text>
<text class="r" {d(2.0)} x="38" y="114" font-family="{SERIF}" font-size="52" fill="{INK}">{data["total_contributions"]:,} <tspan font-style="italic">contributions</tspan></text>
{''.join(bars)}
{''.join(partial for partial in side)}
"""
    write("activity.svg", svg(W, h, body, ["serif", "serif-i", "sans", "mono"],
                              f'{data["total_contributions"]:,} contributions in the last year, {cs}-day streak'))


# ---- 4 · repo cards -----------------------------------------------------------
REPO_W, REPO_H = 880 / 3 - 8, 176


def repo_card(i, name, desc, lang, color, stars):
    delay = 4.6 + i * 0.12
    meta = f"{lang}  \u00b7  \u2605 {stars}" if stars else f"{lang}  \u00b7  open source"
    body = f"""
<rect width="{REPO_W}" height="{REPO_H}" rx="14" fill="{PAPER}"/>
<g class="r" {d(delay)}>
  <rect x="24" y="30" width="8" height="8" rx="2" fill="{color}"/>
  <text x="40" y="39" font-family="{SANS}" font-weight="600" font-size="18" fill="{INK}">{escape(name)}</text>
  {text_lines(24, 72, wrap(desc, 34), 21, f'font-family="{SANS}" font-size="14" fill="{INK_SOFT}"')}
  <text x="24" y="{REPO_H - 24}" font-family="{MONO}" font-size="12" fill="{MUTED}">{escape(meta)}</text>
</g>
"""
    write(f"repo-{name}.svg", svg(REPO_W, REPO_H, body, ["sans", "mono"], f"{name}: {desc}",
                                  left=4 * i, right=8 - 4 * i))


def section_title(text, italic, theme):
    fg = "#fafafa" if theme == "dark" else "#111111"
    body = (
        f'<text class="r" {d(4.4)} x="2" y="46" font-family="{SERIF}" font-size="34" fill="{fg}">{escape(text)} '
        f'<tspan font-style="italic">{escape(italic)}</tspan></text>'
    )
    write(f"title-coding-{theme}.svg", svg(W, 64, body, ["serif", "serif-i"], f"{text} {italic}", bottom=0))


# ---- 5 · blue contribution graph -----------------------------------------------
BLUE = ["#2a2a2a", "#1d4472", "#2762a6", "#3487de", TECH, "#a8d4ff"]


def level_for(c):
    return 0 if c == 0 else 1 if c <= 5 else 2 if c <= 15 else 3 if c <= 30 else 4 if c <= 50 else 5


def heatmap(data):
    days = data["days"]
    first = datetime.date.fromisoformat(days[0]["date"])
    lead = (first.weekday() + 1) % 7  # sunday = 0
    cell, step, gx, gy = 12, 15, 44, 96
    cells, months, seen = [], [], set()
    for i, day in enumerate(days):
        k = i + lead
        col, row = divmod(k, 7)
        date = datetime.date.fromisoformat(day["date"])
        if date.day <= 7 and (date.year, date.month) not in seen and row == 0:
            seen.add((date.year, date.month))
            months.append((col, date.strftime("%b")))
        c = day["count"]
        delay = 1.0 + col * 0.03 + row * 0.02
        cells.append(
            f'<rect class="p" style="animation-delay:{delay:.2f}s" x="{gx + col * step}" y="{gy + row * step}" '
            f'width="{cell}" height="{cell}" rx="3" fill="{BLUE[level_for(c)]}">'
            f'<title>{day["date"]}: {c} contribution{"s" if c != 1 else ""}</title></rect>'
        )
    ncols = (len(days) + lead + 6) // 7
    right = gx + ncols * step - 3
    labels = "".join(
        f'<text x="{gx + col * step}" y="{gy + 7 * step + 16}" font-family="{MONO}" font-size="11" fill="{MUTED}">{m}</text>'
        for col, m in months if col < ncols - 12
    )
    legend_x = right - len(BLUE) * 14
    legend = "".join(
        f'<rect x="{legend_x + i * 14}" y="{gy + 7 * step + 6}" width="11" height="11" rx="2.5" fill="{c}"/>'
        for i, c in enumerate(BLUE)
    )
    h = gy + 7 * step + 44
    body = f"""
<rect width="{W}" height="{h}" rx="14" fill="{PAPER}"/>
<text class="r" {d(0.8)} x="42" y="62" font-family="{SERIF}" font-size="34" fill="{INK}">Every day, <tspan font-style="italic" fill="{TECH}">in blue</tspan></text>
<text class="f" {d(0.8)} x="{right}" y="60" text-anchor="end" font-family="{MONO}" font-size="12" letter-spacing="1" fill="{MUTED}">REFRESHED DAILY</text>
{''.join(cells)}
<g class="f" {d(2.4)}>{labels}
<text x="{legend_x - 8}" y="{gy + 7 * step + 16}" text-anchor="end" font-family="{MONO}" font-size="11" fill="{MUTED}">less</text>
{legend}
<text x="{legend_x + len(BLUE) * 14 + 2}" y="{gy + 7 * step + 16}" font-family="{MONO}" font-size="11" fill="{MUTED}">more</text></g>
"""
    write("heatmap.svg", svg(W, h, body, ["serif", "serif-i", "mono"],
                             f'Contribution graph: {data["total_contributions"]:,} contributions in the last year'))


# ---- data ---------------------------------------------------------------------


def load_data():
    raw = json.loads(DATA.read_text(encoding="utf-8"))
    days = sorted(({"date": x["date"], "count": int(x["count"])} for x in raw["days"]), key=lambda x: x["date"])
    counts = {x["date"]: x["count"] for x in days}
    total = sum(counts.values())

    best = run = 0
    for x in days:
        run = run + 1 if x["count"] > 0 else 0
        best = max(best, run)

    end = len(days) - 1
    if end >= 0 and days[end]["count"] == 0:
        end -= 1
    current = 0
    while end >= 0 and days[end]["count"] > 0:
        current += 1
        end -= 1

    busiest = max(days, key=lambda x: (x["count"], x["date"]))

    monthly = {}
    for x in days:
        key = x["date"][:7]
        monthly[key] = monthly.get(key, 0) + x["count"]

    return {
        "days": days,
        "total_contributions": total,
        "active_days": sum(1 for c in counts.values() if c > 0),
        "current_streak": {"length": current},
        "longest_streak": {"length": best},
        "best_day": {"date": busiest["date"], "count": busiest["count"]},
        "monthly": [{"month": k, "total": v} for k, v in sorted(monthly.items())],
        "repos": raw.get("repos", []),
    }


REPO_STYLE = {
    "Crawl-Job": ("TypeScript", TECH),
    "VulnScanner": ("Python", STUDIO),
    "reciprocity": ("JavaScript", LEARN),
}


if __name__ == "__main__":
    data = load_data()
    hero()
    tile("build", "BUILD", "#1447e6", "#ffffff", "40", "repos",
         "Backend services, security tools and utilities, built in the open.", 3.1, 0)
    tile("brand", "SECURITY", STUDIO, "#ffffff", "1", "toolkit",
         "VulnScanner syncs NVD, KEV and EPSS, then gates CI on what it finds.", 3.35, 1)
    tile("learn", "AUTOMATION", LEARN, "#111111", "Daily", "runs",
         "GitHub Actions redraw these cards every morning from real data.", 3.6, 2)
    activity(data)
    for i, repo in enumerate(data["repos"][:3]):
        lang, color = REPO_STYLE.get(repo["name"], (repo.get("language") or "Code", TECH))
        repo_card(i, repo["name"], repo["description"], lang, color, repo.get("stars", 0))
    section_title("What I'm", "coding", "dark")
    section_title("What I'm", "coding", "light")
    heatmap(data)
