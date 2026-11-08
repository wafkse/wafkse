"""Offline tests for stable SVG text outlines."""

from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tool"))

from font import outline_svg, text_outline


class Glyph:
    def draw(self, pen):
        pen.moveTo((0, 0))
        pen.lineTo((400, 0))
        pen.lineTo((400, 500))
        pen.closePath()


class Font:
    def __init__(self):
        self._head = type("Head", (), {"unitsPerEm": 1000})()
        self._hmtx = type("Hmtx", (), {"metrics": {"a": (600, 0)}})()

    def getGlyphSet(self):
        return {"a": Glyph()}

    def getBestCmap(self):
        return {ord("a"): "a"}

    def __getitem__(self, key):
        return {"head": self._head, "hmtx": self._hmtx}[key]


class SvgFontTest(unittest.TestCase):
    def test_outline_preserves_position_and_alignment(self):
        source = b'<svg xmlns="http://www.w3.org/2000/svg"><title>test</title><text x="100" y="40" font-size="20" text-anchor="end" fill="#fff">aa</text></svg>'
        result = outline_svg(source, Font(), Font())

        root = ET.fromstring(result)
        path = root.find(".//{http://www.w3.org/2000/svg}path")

        self.assertIsNotNone(path)
        self.assertEqual(path.get("transform"), "translate(-1200 0)")
        self.assertIn(b"<title>test</title>", result)
        self.assertNotIn(b"<text ", result)
        self.assertIn(b'fill="#fff"', result)

    def test_nerd_font_glyph_is_selected_by_family(self):
        class Symbols(Font):
            def getBestCmap(self):
                return {0xE7A8: "a"}

        source = (
            '<svg xmlns="http://www.w3.org/2000/svg">'
            '<text x="100" y="40" font-size="48" '
            'font-family="Symbols Nerd Font Mono">&#xE7A8;</text>'
            '</svg>'
        ).encode("utf-8")

        with self.assertRaises(ValueError):
            outline_svg(source, Font(), Font())

        result = outline_svg(source, Font(), Font(), Symbols())
        root = ET.fromstring(result)
        group = root.find(".//{http://www.w3.org/2000/svg}g")
        path = root.find(".//{http://www.w3.org/2000/svg}path")

        self.assertIsNotNone(group)
        self.assertIsNotNone(path)
        # The fake icon occupies x=0..400 but advances by 600 units.
        # Its horizontal center is 200, not the advance midpoint (300).
        self.assertEqual(group.get("transform"), "translate(100 40) scale(0.048 -0.048)")
        self.assertEqual(path.get("transform"), "translate(-200 -250)")
        self.assertNotIn(b"<text ", result)


    def test_text_middle_anchor_uses_advance_not_ink_bounds(self):
        source = (
            b'<svg xmlns="http://www.w3.org/2000/svg">'
            b'<text x="100" y="40" font-size="20" '
            b'text-anchor="middle">aa</text></svg>'
        )
        result = outline_svg(source, Font(), Font())
        root = ET.fromstring(result)
        path = root.find(".//{http://www.w3.org/2000/svg}path")

        self.assertIsNotNone(path)
        self.assertEqual(path.get("transform"), "translate(-600 0)")

    def test_missing_glyph_is_rejected(self):
        with self.assertRaises(ValueError):
            text_outline("b", Font())


if __name__ == "__main__":
    unittest.main()
