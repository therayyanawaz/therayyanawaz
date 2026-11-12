#!/usr/bin/env python3
"""
Refresh data/contributions.json from GitHub.

Scrapes the public contribution calendar for the last year and reads the
featured repositories from the REST API. Run by the scheduled Action before
scripts/render_readme_cards.py; works locally with or without a token.

    GITHUB_TOKEN=... python scripts/fetch_contributions.py
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "contributions.json"
USER = os.environ.get("GH_PROFILE_USER", "therayyanawaz")
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""

FEATURED = ["Crawl-Job", "VulnScanner", "reciprocity", "AWSMnotes"]

# One short line per card, written to match the site rather than the terse repo field.
BLURBS = {
    "Crawl-Job": "TypeScript job crawler with API, RSS, HTTP and Playwright sources, dedupe and Postgres storage.",
    "VulnScanner": "Local-first vulnerability toolkit: NVD, KEV and EPSS sync, lockfile scans and CI policy gates.",
    "reciprocity": "Browser userscript that finds the Instagram accounts that don't follow you back.",
    "AWSMnotes": "Community security-testing notes: pentest methods, attack vectors and practical research.",
}

HEADERS = {
    "User-Agent": f"{USER}-profile-cards",
    "Accept": "text/html,application/xhtml+xml",
}
if TOKEN:
    HEADERS["Authorization"] = f"Bearer {TOKEN}"


def get(url: str, accept: str = "application/json") -> bytes:
    headers = dict(HEADERS)
    headers["Accept"] = accept
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def contributions(user: str) -> list[dict]:
    html = get(f"https://github.com/users/{user}/contributions", "text/html").decode("utf-8", "replace")

    # Counts live in <tool-tip for="contribution-day-component-x-y">N contributions on ...</tool-tip>
    tips = {}
    for tag, body in re.findall(r"<tool-tip\b[^>]*\bfor=\"([^\"]+)\"[^>]*>(.*?)</tool-tip>", html, re.S):
        match = re.search(r"(\d+|No) contributions?", body)
        tips[tag] = 0 if not match or match.group(1) == "No" else int(match.group(1))

    days = {}
    for tag in re.findall(r"<td\b[^>]*>", html):
        if "ContributionCalendar-day" not in tag:
            continue
        attrs = dict(re.findall(r'([\w-]+)="([^"]*)"', tag))
        day = attrs.get("data-date")
        if not day:
            continue
        days[day] = tips.get(attrs.get("id", ""), 0)

    if not days:
        sys.exit("could not parse the contribution calendar; GitHub may have changed its markup")
    return [{"date": day, "count": days[day]} for day in sorted(days)]


def repo(name: str, user: str) -> dict:
    raw = json.loads(get(f"https://api.github.com/repos/{user}/{name}"))
    return {
        "name": raw.get("name", name),
        "description": BLURBS.get(name) or raw.get("description") or "",
        "language": raw.get("language") or "",
        "stars": raw.get("stargazers_count", 0),
        "topics": raw.get("topics") or [],
        "url": raw.get("html_url", f"https://github.com/{user}/{name}"),
    }


def main() -> None:
    print(f"reading contributions for {USER}")
    days = contributions(USER)
    total = sum(d["count"] for d in days)
    print(f"  {len(days)} days, {total} contributions")

    repos = []
    for name in FEATURED:
        try:
            repos.append(repo(name, USER))
            print(f"  repo {name}: ok")
        except Exception as exc:  # keep the last good cards rendering
            print(f"  ! repo {name}: {exc}", file=sys.stderr)

    previous = {}
    if OUT.exists():
        try:
            previous = json.loads(OUT.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            previous = {}
    if not repos:
        repos = previous.get("repos", [])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "username": USER,
                "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                "total": total,
                "days": days,
                "repos": repos,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
