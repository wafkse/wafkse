"""Pure, network-free tests for generated profile data."""

from pathlib import Path
import sys
import tomllib
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tool"))
from snapshot import contribution_signal, markdown_escape, recent_writing, toml_document


class SnapshotTests(unittest.TestCase):
    def test_signal(self):
        signal = contribution_signal([
            {"contributionDays": [{"date": "2026-11-01", "contributionCount": 0}]},
            {"contributionDays": [{"date": "2026-11-08", "contributionCount": 9}]},
        ])
        self.assertEqual(signal["total_label"], "9")
        self.assertEqual(signal["points"], "316,147 1007,67")
        self.assertTrue(signal["area"].endswith("L1007 147 Z"))

    def test_zeros(self):
        signal = contribution_signal(
            [{"contributionDays": [{"date": "2026-11-08", "contributionCount": 0}]}]
        )
        self.assertEqual(signal["points"], "316,147")
        self.assertEqual(signal["total_label"], "0")

    def test_empty(self):
        with self.assertRaises(ValueError):
            contribution_signal([])

    def test_atom_origin_filter(self):
        atom = b"""<feed xmlns="http://www.w3.org/2005/Atom">
          <entry><title>Rust [notes]</title>
            <link rel="alternate" href="https://wafkse.dev/blog/rust/"/></entry>
          <entry><title>Unsafe link</title>
            <link rel="alternate" href="https://evil.example/blog/"/></entry>
        </feed>"""
        writing = recent_writing(atom)
        self.assertIn("Rust \\[notes\\]", writing)
        self.assertNotIn("evil.example", writing)

    def test_toml_round_trip(self):
        text = toml_document("writing", {"markdown": "**Latest**\n\n- [A](https://wafkse.dev/)"})
        self.assertIn("**Latest**", tomllib.loads(text)["default"]["writing"]["markdown"])

    def test_escape(self):
        self.assertEqual(markdown_escape(r"a[b]\c"), r"a\[b\]\\c")


if __name__ == "__main__":
    unittest.main()
