#!/usr/bin/env python3
"""Collect public GitHub metrics into a typed Mirage TOML candidate."""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta, timezone
from math import ceil, log1p
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from pydantic import BaseModel, ConfigDict, field_validator
import tomlkit

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TARGET_PATH = PROJECT_ROOT / "config" / "metric.toml"

PROFILE_PATH = PROJECT_ROOT / "config" / "profile.toml"
GITHUB_OWNER = os.getenv("GITHUB_REPOSITORY_OWNER") or str(
    tomlkit.parse(PROFILE_PATH.read_text(encoding="utf-8"))["default"]["profile"]["username"]
)
GITHUB_API_URL = os.getenv("GITHUB_API_URL", "https://api.github.com")
ACTIVITY_PERIOD = timedelta(days=90)

PAGE_SIZE = 100
PAGE_LIMIT = 30
HOUR_COUNT = 24
DAY_COUNT = 7
LANGUAGE_LIMIT = 6


class RepositoryRecord(BaseModel):
    name: str
    default_branch: str
    fork: bool = False
    archived: bool = False
    private: bool = False


class CommitAuthor(BaseModel):
    date: datetime


class CommitBody(BaseModel):
    author: CommitAuthor


class CommitRecord(BaseModel):
    commit: CommitBody


class LanguageRecord(BaseModel):
    name: str
    share: str
    x: int
    width: int
    legend_x: int
    color_index: int


class MetricRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    as_of: date
    since: date
    commit_count: int
    repository_count: int
    hour: list[list[int]]
    language: list[LanguageRecord]

    @field_validator("hour")
    @classmethod
    def validate_hour(cls, target_hour: list[list[int]]) -> list[list[int]]:
        if len(target_hour) != DAY_COUNT:
            raise ValueError("Expected seven weekdays")

        if any(len(target_day) != HOUR_COUNT for target_day in target_hour):
            raise ValueError("Expected 24 UTC hours per weekday")

        if any(not 0 <= level <= 4 for target_day in target_hour for level in target_day):
            raise ValueError("Activity level out of range")

        return target_hour


class GitHubClient:
    def __init__(self, target_client: httpx.Client, owner: str = GITHUB_OWNER):
        self._client = target_client
        self._owner = owner

    def fetch(self, target_path: str, target_query: dict[str, str | int] | None = None) -> Any:
        target_response = self._client.get(target_path, params=target_query)
        target_response.raise_for_status()
        return target_response.json()

    def fetch_page(self, target_path: str, target_query: dict[str, str | int] | None = None):
        for page_index in range(1, PAGE_LIMIT + 1):
            page_query = {**(target_query or {}), "per_page": PAGE_SIZE, "page": page_index}
            page_value = self.fetch(target_path, page_query)

            if not isinstance(page_value, list):
                raise ValueError(f"Expected paginated list from {target_path}")

            yield from page_value

            if len(page_value) < PAGE_SIZE:
                return

        raise RuntimeError(f"Pagination limit exceeded for {target_path}")

    def repository(self) -> list[RepositoryRecord]:
        owner = quote(self._owner, safe="")
        target_repository = [
            RepositoryRecord.model_validate(value)
            for value in self.fetch_page(f"/users/{owner}/repos", {"type": "owner"})
        ]

        return sorted(
            (
                value for value in target_repository
                if not (value.private or value.archived or value.fork)
                and value.name != self._owner
            ),
            key=lambda value: value.name,
        )

    def language(self, target_repository: RepositoryRecord) -> dict[str, int]:
        owner = quote(self._owner, safe="")
        repository = quote(target_repository.name, safe="")
        target_data = self.fetch(f"/repos/{owner}/{repository}/languages")

        if not isinstance(target_data, dict):
            raise ValueError("Expected GitHub language byte counts")

        return {str(key): int(value) for key, value in target_data.items()}

    def commit(self, target_repository: RepositoryRecord, since: date, until: date) -> list[CommitRecord]:
        owner = quote(self._owner, safe="")
        repository = quote(target_repository.name, safe="")
        target_query = {
            "author": self._owner,
            "sha": target_repository.default_branch,
            "since": since.isoformat() + "T00:00:00Z",
            "until": until.isoformat() + "T23:59:59Z",
        }

        return [
            CommitRecord.model_validate(value)
            for value in self.fetch_page(f"/repos/{owner}/{repository}/commits", target_query)
        ]


def normalize_hour(target_commit: list[CommitRecord]) -> list[list[int]]:
    target_count = [[0 for _ in range(HOUR_COUNT)] for _ in range(DAY_COUNT)]

    for target_record in target_commit:
        target_instant = target_record.commit.author.date.astimezone(timezone.utc)
        target_count[target_instant.weekday()][target_instant.hour] += 1

    maximum_count = max(1, *(value for target_day in target_count for value in target_day))
    denominator = log1p(maximum_count)

    return [
        [
            min(4, max(1, ceil(4 * log1p(value) / denominator))) if value else 0
            for value in target_day
        ]
        for target_day in target_count
    ]


def normalize_language(target_byte: Counter[str]) -> list[LanguageRecord]:
    target_order = sorted(
        [(name, value) for name, value in target_byte.items() if value > 0],
        key=lambda item: (-item[1], item[0]),
    )

    if not target_order:
        raise ValueError("No public repository language data")

    if len(target_order) > LANGUAGE_LIMIT:
        target_order = target_order[:LANGUAGE_LIMIT - 1] + [
            ("Other", sum(value for _, value in target_order[LANGUAGE_LIMIT - 1:]))
        ]

    total_byte = sum(target_byte.values())
    target_offset = 0
    target_language = []

    for target_index, (name, byte_count) in enumerate(target_order):
        if target_index == len(target_order) - 1:
            width = 900 - target_offset
        else:
            width = max(1, round(900 * byte_count / total_byte))

        percentage = 100 * byte_count / total_byte
        target_language.append(
            LanguageRecord(
                name=name,
                share=f"{percentage:.1f}%" if percentage >= 0.05 else "<0.1%",
                x=30 + target_offset,
                width=width,
                legend_x=30 + 154 * target_index,
                color_index=target_index,
            )
        )
        target_offset += width

    return target_language


def collect_metric(target_client: GitHubClient, as_of: date) -> MetricRecord:
    since = as_of - ACTIVITY_PERIOD
    target_repository = target_client.repository()

    if not target_repository:
        raise ValueError("No eligible public repositories")

    target_byte: Counter[str] = Counter()
    target_commit: list[CommitRecord] = []

    for value in target_repository:
        target_byte.update(target_client.language(value))
        target_commit.extend(target_client.commit(value, since, as_of))

    return MetricRecord(
        as_of=as_of,
        since=since,
        commit_count=len(target_commit),
        repository_count=len(target_repository),
        hour=normalize_hour(target_commit),
        language=normalize_language(target_byte),
    )


def serialize_metric(target_metric: MetricRecord) -> str:
    target_document = {
        "default": {
            "metric": target_metric.model_dump(mode="json"),
        },
    }

    return tomlkit.dumps(target_document)


def write_metric(target_content: str, target_path: Path = TARGET_PATH) -> None:
    if target_path.exists() and target_path.read_text(encoding="utf-8") == target_content:
        return

    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_temporary = target_path.with_suffix(".toml.tmp")
    target_temporary.write_text(target_content, encoding="utf-8")
    target_temporary.replace(target_path)


def main() -> None:
    token = os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")
    target_header = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "wafkse-profile/1.0",
    }

    if token:
        target_header["Authorization"] = f"Bearer {token}"

    with httpx.Client(base_url=GITHUB_API_URL, headers=target_header, timeout=30.0) as target_http:
        target_client = GitHubClient(target_http)
        target_metric = collect_metric(target_client, datetime.now(timezone.utc).date())

    write_metric(serialize_metric(target_metric))


if __name__ == "__main__":
    main()
