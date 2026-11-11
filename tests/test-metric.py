"""Offline coverage of the GitHub API -> typed TOML -> Mirage boundary."""

from __future__ import annotations

from datetime import date
from pathlib import Path
import sys
import unittest

import httpx
import tomlkit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tool"))

from metric import (
    CommitAuthor, CommitBody, CommitRecord, GitHubClient,
    MetricRecord, RepositoryRecord, collect_metric, normalize_hour,
    serialize_metric,
)


class MetricTest(unittest.TestCase):
    def test_hour_has_square_grid_coordinate(self):
        target_commit = [
            CommitRecord(commit=CommitBody(author=CommitAuthor(date="2026-11-02T00:00:00Z"))),
            CommitRecord(commit=CommitBody(author=CommitAuthor(date="2026-11-08T23:00:00Z"))),
        ]
        target_hour = normalize_hour(target_commit)

        self.assertEqual(len(target_hour), 7)
        self.assertTrue(all(len(target_day) == 24 for target_day in target_hour))
        self.assertEqual(target_hour[0][0], 4)
        self.assertEqual(target_hour[6][23], 4)

    def test_serialization_round_trip(self):
        target_metric = MetricRecord(
            as_of=date(2026, 11, 8),
            since=date(2026, 8, 10),
            commit_count=2,
            repository_count=1,
            hour=[[0] * 24 for _ in range(7)],
        )

        target_document = tomlkit.parse(serialize_metric(target_metric))
        content = target_document["default"]["metric"].unwrap()
        self.assertEqual(content["commit-count"], 2)
        self.assertEqual(content["repository-count"], 1)
        self.assertEqual(content["as-of"], "2026-11-08")
        self.assertNotIn("commit_count", content)
        restored = MetricRecord.model_validate(content)

        self.assertEqual(restored, target_metric)

    def test_repository_discovery_uses_default_branch(self):
        target_request = []

        def respond(request: httpx.Request):
            target_request.append(str(request.url))
            path = request.url.path

            if path == "/users/wafkse/repos":
                return httpx.Response(200, json=[
                    {"name": "example", "default_branch": "development", "fork": False, "archived": False, "private": False},
                    {"name": "forked", "default_branch": "main", "fork": True, "archived": False, "private": False},
                ])

            if path == "/repos/wafkse/example/commits":
                return httpx.Response(200, json=[
                    {"commit": {"author": {"date": "2026-11-08T10:00:00Z"}}},
                ])

            return httpx.Response(404)

        with httpx.Client(
            transport=httpx.MockTransport(respond),
            base_url="https://api.github.com",
        ) as target_http:
            target_metric = collect_metric(GitHubClient(target_http), date(2026, 11, 8))

        self.assertEqual(target_metric.repository_count, 1)
        self.assertEqual(target_metric.commit_count, 1)
        self.assertTrue(any("sha=development" in url for url in target_request))
        self.assertFalse(any(url.endswith("/languages") for url in target_request))


if __name__ == "__main__":
    unittest.main()
