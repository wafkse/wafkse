from pathlib import Path
import sys
import tomllib
import unittest
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tool"))
from metrics import calculate, commit_bins, source_bytes, write_toml


class MetricsTests(unittest.TestCase):
    def test_weekday_hour_in_utc(self):
        bins = commit_bins([
            {"commit": {"author": {"date": "2026-11-08T23:12:10Z"}}},
            {"commit": {"author": {"date": "2026-11-02T00:01:00Z"}}},
        ])
        self.assertEqual(len(bins), 168)
        self.assertEqual(bins[6 * 24 + 23], 1)
        self.assertEqual(bins[0], 1)

    def test_file_extension_filter(self):
        tree = {"truncated": False, "tree": [
            {"path": "src/lib.rs", "size": 100, "type": "blob"},
            {"path": "README.md", "size": 900, "type": "blob"},
            {"path": "native/core.c", "size": 11, "type": "blob"},
        ]}
        self.assertEqual(source_bytes(tree), {"Rust": 100, "C": 11})

    def test_truncated_tree_rejected(self):
        with self.assertRaises(RuntimeError):
            source_bytes({"truncated": True, "tree": []})

    def test_profile_metrics_round_trip(self):
        hours = [0] * 168
        hours[0] = 3
        hours[25] = 2
        metrics = calculate(hours, {"Rust": 90, "C": 10}, "2026-11-08", "2026-08-10")
        output = tomllib.loads(write_toml(metrics))["default"]["metrics"]
        self.assertEqual(output["commit_count"], 5)
        self.assertEqual(len(output["cells"]), 168)
        self.assertEqual(output["languages"][0]["percent"], "90.0%")
        self.assertEqual(sum(x["width"] for x in output["languages"]), 900)


if __name__ == "__main__":
    unittest.main()
