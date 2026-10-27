#!/usr/bin/env python3
"""Design 3 ("Lamplight"): slim the two typefaces for the web.

The originals (Noto Serif Display and Jost, both under the SIL Open Font License, from the
fontsource packages) are kept in imagery/font-sources/. This script writes the files the site
loads into assets/fonts/:

  * Noto Serif Display is only ever set at weight 400, so each style is pinned to that one weight
    (a static font is a fraction of the size of a variable one);
  * Jost keeps a narrowed weight axis, 400 to 500, which covers every weight the stylesheet asks for;
  * both are cut down to the characters the site can show: Basic Latin, the Latin-1 letters, curly
    quotes, dashes, the bullet, the ellipsis, the minus sign and a few symbols. A character outside
    that set (an unusual name on the credits page) falls back to the system serif for that letter.

    python3 designs/design-3/imagery/fonts.py

Needs fontTools and brotli (pip install fonttools brotli).
"""
import io
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

HERE = Path(__file__).resolve().parent
SRC = HERE / "font-sources"
OUT = HERE.parent / "assets" / "fonts"

UNICODES = (
    list(range(0x20, 0x7F))            # Basic Latin
    + list(range(0xA0, 0x100))         # Latin-1 Supplement
    + [0x131, 0x152, 0x153]            # dotless i, OE ligatures
    + list(range(0x2010, 0x2016))      # hyphens and dashes
    + list(range(0x2018, 0x201F))      # curly quotes
    + [0x2022, 0x2026, 0x2032, 0x2033, 0x20AC, 0x2122, 0x2212]
)

JOBS = [
    # source file, output file, axis limits
    ("noto-serif-display-latin-wght-normal.woff2", "noto-serif-display-latin-wght-normal.woff2", {"wght": 400}),
    ("noto-serif-display-latin-wght-italic.woff2", "noto-serif-display-latin-wght-italic.woff2", {"wght": 400}),
    ("jost-latin-wght-normal.woff2", "jost-latin-wght-normal.woff2", {"wght": (400, 500)}),
]


def slim(src: Path, dst: Path, limits: dict) -> None:
    font = TTFont(src)
    font = instancer.instantiateVariableFont(font, limits)
    buf = io.BytesIO()  # save and reload, so the font tables are in a state the subsetter accepts
    font.flavor = None
    font.save(buf)
    buf.seek(0)
    font = TTFont(buf)
    opts = subset.Options()
    opts.flavor = "woff2"
    opts.layout_features = ["kern", "liga", "calt", "ccmp", "locl", "mark", "mkmk", "case", "tnum", "lnum"]
    opts.hinting = False
    opts.glyph_names = False
    opts.notdef_outline = True
    opts.name_IDs = [1, 2, 3, 4, 6]
    opts.drop_tables += ["DSIG"]
    sub = subset.Subsetter(opts)
    sub.populate(unicodes=UNICODES)
    sub.subset(font)
    dst.parent.mkdir(parents=True, exist_ok=True)
    font.flavor = "woff2"
    font.save(dst)


def main():
    for name, out_name, limits in JOBS:
        src, dst = SRC / name, OUT / out_name
        before = src.stat().st_size
        slim(src, dst, limits)
        print(f"{out_name}: {before / 1024:.1f} KiB -> {dst.stat().st_size / 1024:.1f} KiB")


if __name__ == "__main__":
    main()
