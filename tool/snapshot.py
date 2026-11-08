#!/usr/bin/env python3
"""Gather public GitHub contributions and Atom writing for the Mirage profile."""

from __future__ import annotations
import argparse
import json
import math
import os
from pathlib import Path
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
USER = "wafkse"
FEED = "https://wafkse.dev/atom.xml"
QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        weeks {
          contributionDays { date contributionCount }
        }
      }
    }
  }
}
"""


def contribution_signal(weeks: list[dict]) -> dict[str, str]:
    """52 weekly values, square-root-scaled, in SVG coordinate space."""
    if not weeks:
        raise ValueError("Empty GitHub contribution calendar")
    weeks = weeks[-52:]
    counts = [sum(int(day["contributionCount"]) for day in week["contributionDays"])
              for week in weeks]
    dates = [day["date"] for week in weeks for day in week["contributionDays"]]
    if not dates or min(counts) < 0:
        raise ValueError("Invalid GitHub contribution data")

    peak = max(1, max(counts))
    baseline = 147
    points = [
        (316 + round(691 * i / max(1, len(counts) - 1)),
         baseline - round(80 * math.sqrt(count / peak)))
        for i, count in enumerate(counts)
    ]
    return {
        "total_label": f"{sum(counts):,}",
        "range_label": f"{min(dates)} / {max(dates)}",
        "points": " ".join(f"{x},{y}" for x, y in points),
        "area": (f"M{points[0][0]} {baseline} "
                 + " ".join(f"L{x} {y}" for x, y in points)
                 + f" L{points[-1][0]} {baseline} Z"),
    }


def fetch_contributions(token: str) -> list[dict]:
    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": USER}}).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.github+json",
            "User-Agent": "wafkse-profile",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        payload = json.load(response)
    if payload.get("errors"):
        raise RuntimeError(f"GitHub GraphQL error: {payload['errors']}")
    try:
        return payload["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    except (KeyError, TypeError) as error:
        raise RuntimeError("GitHub response lacks contribution weeks") from error


def markdown_escape(text: str) -> str:
    return re.sub(r"([\\\[\]<>])", r"\\\1", text)


def recent_writing(atom_xml: bytes, limit: int = 2) -> str:
    """Only same-origin HTTPS links are permitted in generated Markdown."""
    root = ET.fromstring(atom_xml)
    ns = "{http://www.w3.org/2005/Atom}"
    entries: list[str] = []
    for entry in root.findall(f"{ns}entry"):
        title_node = entry.find(f"{ns}title")
        if title_node is None:
            continue
        title = " ".join("".join(title_node.itertext()).split())[:120]
        if not title:
            continue
        href = next(
            (link.get("href") for link in entry.findall(f"{ns}link")
             if link.get("rel", "alternate") == "alternate"), None
        )
        if not href:
            continue
        address = urllib.parse.urlsplit(href)
        if (address.scheme != "https" or address.netloc != "wafkse.dev"
                or not re.fullmatch(r"/[A-Za-z0-9_/-]*", address.path)
                or address.query or address.fragment):
            continue
        entries.append(f"- [{markdown_escape(title)}]({href})")
        if len(entries) >= limit:
            break
    return "**Recent writing**\n\n" + "\n".join(entries) + "\n" if entries else ""


def toml_document(section: str, values: dict[str, str]) -> str:
    result = [f"[default.{section}]"]
    for key, value in values.items():
        if not re.fullmatch(r"[a-z_]+", key) or not isinstance(value, str):
            raise ValueError("Invalid generated data")
        result.append(f"{key} = {json.dumps(value, ensure_ascii=True)}")
    return "\n".join(result) + "\n"


def write_if_changed(path: Path, content: str) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return False
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(content, encoding="utf-8")
    temp.replace(path)
    return True


def fetch_atom() -> bytes:
    request = urllib.request.Request(
        FEED, headers={"User-Agent": "wafkse-profile"}
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return response.read(2_000_000)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--signal", type=Path, default=ROOT / "config/signal.toml")
    parser.add_argument("--writing", type=Path, default=ROOT / "config/writing.toml")
    args = parser.parse_args()
    token = os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")
    if not token:
        parser.error("Set GH_TOKEN or GITHUB_TOKEN before refreshing")
    signal = contribution_signal(fetch_contributions(token))
    write_if_changed(args.signal, toml_document("signal", signal))
    try:
        writing = recent_writing(fetch_atom())
    except (OSError, ValueError, ET.ParseError) as error:
        print(f"Atom unavailable; keeping last snapshot: {error}", file=sys.stderr)
    else:
        write_if_changed(args.writing, toml_document("writing", {"markdown": writing}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
