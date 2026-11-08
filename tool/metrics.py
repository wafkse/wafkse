#!/usr/bin/env python3
"""Generate GitHub activity/source metrics as a Mirage TOML candidate.

Observations are from authored commits on the configured default branches and
tracked source-file extensions. This is not GitHub's contribution count.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "config/metrics.toml"
USER = "wafkse"
REPOSITORIES = {
    "nekor": "development",
    "mirage": "development",
    "catalejo": "development",
    "tokel": "development",
    "desenredo": "development",
    "fack": "trunk",
    "aldebaran": "development",
    "dotfiles": "development",
}
EXTENSIONS = {
    "rs": "Rust", "c": "C", "h": "C",
    "cc": "C++", "cpp": "C++", "cxx": "C++", "hpp": "C++",
    "py": "Python", "ts": "Web", "tsx": "Web", "js": "Web",
    "jsx": "Web", "css": "Web", "scss": "Web",
    "luau": "Lua", "lua": "Lua", "sh": "Shell", "bash": "Shell",
}
TONES = {
    "Rust": "peach", "C": "teal", "C++": "yellow", "Python": "blue",
    "Web": "lavender", "Lua": "mauve", "Shell": "green", "Other": "muted",
}


def fetch_json(path: str) -> object:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    request = urllib.request.Request(
        "https://api.github.com" + path,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "wafkse-profile",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def read_commits(repository: str, since: str) -> list[dict]:
    commits: list[dict] = []
    for page in range(1, 16):
        query = urllib.parse.urlencode({
            "author": USER, "since": since + "T00:00:00Z",
            "per_page": 100, "page": page,
        })
        result = fetch_json(f"/repos/{USER}/{repository}/commits?{query}")
        if not isinstance(result, list):
            raise RuntimeError(f"Unexpected commits response for {repository}")
        commits.extend(result)
        if len(result) < 100:
            return commits
    raise RuntimeError(f"Pagination cap exceeded for {repository}")


def source_bytes(tree: dict) -> dict[str, int]:
    if tree.get("truncated"):
        raise RuntimeError("GitHub returned a truncated repository tree")
    result: dict[str, int] = {}
    for item in tree["tree"]:
        if item.get("type") != "blob" or not isinstance(item.get("size"), int):
            continue
        name = item["path"].rsplit("/", 1)[-1]
        language = EXTENSIONS.get(name.rsplit(".", 1)[-1].lower())
        if language:
            result[language] = result.get(language, 0) + item["size"]
    return result


def commit_bins(commits: list[dict]) -> list[int]:
    bins = [0] * (7 * 24)
    for item in commits:
        raw = item["commit"]["author"]["date"]
        instant = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        weekday = instant.weekday()  # Monday first, timezone aware UTC
        bins[weekday * 24 + instant.hour] += 1
    return bins


def calculate(hours: list[int], source: dict[str, int], as_of: str, since: str) -> dict:
    if len(hours) != 168 or any(n < 0 for n in hours):
        raise ValueError("Expected 168 nonnegative hour bins")
    peak = max(1, *hours)
    cells = [{
        "x": 174 + (i % 24) * 30,
        "y": 66 + (i // 24) * 25,
        "active": count > 0,
        "opacity": f"{min(1.0, 0.26 + 0.74 * math.log1p(count) / math.log1p(peak)):.2f}"
        if count else "0.20",
    } for i, count in enumerate(hours)]

    sorted_source = sorted(
        [(name, amount) for name, amount in source.items() if amount > 0],
        key=lambda item: (-item[1], item[0]),
    )
    if not sorted_source:
        raise ValueError("No source files found")
    if len(sorted_source) > 6:
        other = sum(amount for _, amount in sorted_source[5:])
        sorted_source = sorted_source[:5] + [("Other", other)]

    total_bytes = sum(source.values())
    x_offset = 0
    segments = []
    for index, (name, amount) in enumerate(sorted_source):
        width = (900 - x_offset if index == len(sorted_source) - 1
                 else round(900 * amount / total_bytes))
        segments.append({
            "name": name,
            "percent": f"{100 * amount / total_bytes:.1f}%",
            "x": 30 + x_offset,
            "width": width,
            "legend_x": 30 + index * 154,
            "tone": TONES.get(name, "muted"),
        })
        x_offset += width
    return {
        "as_of": as_of, "since": since, "commit_count": sum(hours),
        "repo_count": len(REPOSITORIES), "cells": cells, "languages": segments,
    }


def write_toml(metrics: dict) -> str:
    lines = [
        "[default.metrics]",
        "as_of = " + json.dumps(metrics["as_of"]),
        "since = " + json.dumps(metrics["since"]),
        "commit_count = " + str(metrics["commit_count"]),
        "repo_count = " + str(metrics["repo_count"]),
        "cells = [",
    ]
    for cell in metrics["cells"]:
        lines.append(
            "  { x = %d, y = %d, active = %s, opacity = %s },"
            % (cell["x"], cell["y"], str(cell["active"]).lower(),
               json.dumps(cell["opacity"]))
        )
    lines += ["]", "languages = ["]
    for part in metrics["languages"]:
        lines.append(
            "  { name = %s, percent = %s, x = %d, width = %d, legend_x = %d, tone = %s },"
            % (json.dumps(part["name"]), json.dumps(part["percent"]),
               part["x"], part["width"], part["legend_x"],
               json.dumps(part["tone"]))
        )
    return "\n".join(lines + ["]", ""])


def main() -> None:
    today = datetime.now(timezone.utc).date()
    since = today - timedelta(days=90)
    bins = [0] * 168
    source: dict[str, int] = {}
    for repository, branch in REPOSITORIES.items():
        tree = fetch_json(
            f"/repos/{USER}/{repository}/git/trees/{branch}?recursive=1"
        )
        for name, amount in source_bytes(tree).items():
            source[name] = source.get(name, 0) + amount
        for index, count in enumerate(commit_bins(read_commits(repository, since.isoformat()))):
            bins[index] += count

    output = write_toml(calculate(bins, source, today.isoformat(), since.isoformat()))
    if not DESTINATION.exists() or DESTINATION.read_text(encoding="utf-8") != output:
        temporary = DESTINATION.with_suffix(".toml.tmp")
        temporary.write_text(output, encoding="utf-8")
        temporary.replace(DESTINATION)


if __name__ == "__main__":
    main()
