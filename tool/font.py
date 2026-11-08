#!/usr/bin/env python3
"""Render Mirage SVG text as JetBrains Mono outlines for GitHub's image proxy.

Fonts are cached locally; only the resulting SVG outlines are published.
"""

from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET

import httpx
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]
FONT_TAG = ROOT / ".font.tag"
NERD_FONT_TAG = ROOT / ".nerd-font.tag"
FONT_CACHE = Path.home() / ".cache" / "wafkse-profile" / "font"
FONT_SOURCE = "https://raw.githubusercontent.com/JetBrains/JetBrainsMono"
NERD_FONT_SOURCE = "https://raw.githubusercontent.com/ryanoasis/nerd-fonts"
FONT_STYLE = {"regular": "Regular", "semibold": "SemiBold"}
SVG_NS = "http://www.w3.org/2000/svg"
SVG_TEXT = f"{{{SVG_NS}}}text"
SVG_GROUP = f"{{{SVG_NS}}}g"
SVG_PATH = f"{{{SVG_NS}}}path"


def load_font(style: str, tag: str) -> TTFont:
    name = f"JetBrainsMono-{FONT_STYLE[style]}.ttf"
    target = FONT_CACHE / tag / name

    if not target.is_file():
        url = f"{FONT_SOURCE}/{tag}/fonts/ttf/{name}"
        response = httpx.get(url, timeout=30, follow_redirects=True)
        response.raise_for_status()

        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        temporary.write_bytes(response.content)
        temporary.replace(target)

    return TTFont(target, recalcBBoxes=False, recalcTimestamp=False)



def load_nerd_font(tag: str) -> TTFont:
    name = "SymbolsNerdFontMono-Regular.ttf"
    target = FONT_CACHE / "nerd-fonts" / tag / name

    if not target.is_file():
        url = (
            f"{NERD_FONT_SOURCE}/{tag}/patched-fonts/"
            f"NerdFontsSymbolsOnly/{name}"
        )
        response = httpx.get(url, timeout=30, follow_redirects=True)
        response.raise_for_status()

        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        temporary.write_bytes(response.content)
        temporary.replace(target)

    return TTFont(target, recalcBBoxes=False, recalcTimestamp=False)


def text_outline(text: str, font: TTFont) -> tuple[str, int]:
    glyph_set = font.getGlyphSet()
    cmap = font.getBestCmap()
    advance = font["hmtx"].metrics
    pen = SVGPathPen(glyph_set)
    offset = 0

    for char in text:
        name = cmap.get(ord(char))
        if name is None:
            raise ValueError(f"JetBrains Mono has no glyph for {char!r}")

        glyph_set[name].draw(TransformPen(pen, (1, 0, 0, 1, offset, 0)))
        offset += advance[name][0]

    return pen.getCommands(), offset


def outline_svg(source: bytes, regular: TTFont, semibold: TTFont, symbols: TTFont | None = None) -> bytes:
    ET.register_namespace("", SVG_NS)
    root = ET.fromstring(source)

    for parent in root.iter():
        for child in list(parent):
            if child.tag != SVG_TEXT:
                continue

            label = "".join(child.itertext())
            if child.get("font-family") == "Symbols Nerd Font Mono":
                if symbols is None:
                    raise ValueError("Nerd Font glyph requested without a symbols font")
                font = symbols
            else:
                font = semibold if int(child.get("font-weight", "400")) >= 600 else regular
            commands, advance = text_outline(label, font)
            scale = float(child.get("font-size", "16")) / font["head"].unitsPerEm
            x, y = float(child.get("x", "0")), float(child.get("y", "0"))
            anchor = child.get("text-anchor", "start")

            if anchor == "end":
                offset = -advance
            elif anchor == "middle":
                offset = -advance / 2
            else:
                offset = 0

            group = ET.Element(SVG_GROUP, {
                "transform": f"translate({x:g} {y:g}) scale({scale:.8g} {-scale:.8g})",
                "fill": child.get("fill", "#000"),
            })

            if commands:
                ET.SubElement(group, SVG_PATH, {
                    "d": commands,
                    "transform": f"translate({offset:g} 0)",
                })

            index = list(parent).index(child)
            parent.remove(child)
            parent.insert(index, group)

    return ET.tostring(root, encoding="utf-8", xml_declaration=False)


def main() -> None:
    tag = FONT_TAG.read_text(encoding="utf-8").strip()
    if not tag.startswith("v") or not tag[1:].replace(".", "").isdigit():
        raise ValueError("Invalid JetBrains Mono release tag")

    nerd_tag = NERD_FONT_TAG.read_text(encoding="utf-8").strip()
    if not nerd_tag.startswith("v") or not nerd_tag[1:].replace(".", "").isdigit():
        raise ValueError("Invalid Nerd Fonts release tag")

    regular = load_font("regular", tag)
    semibold = load_font("semibold", tag)
    symbols = load_nerd_font(nerd_tag)

    for target in sorted((ROOT / "assets").glob("*.svg")):
        source = target.read_bytes()
        result = outline_svg(source, regular, semibold, symbols)

        if result != source:
            target.write_bytes(result)


if __name__ == "__main__":
    main()
