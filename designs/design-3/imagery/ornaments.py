#!/usr/bin/env python3
"""Design 3 ("Lamplight"): the engine-turned ornaments, drawn here rather than taken from anyone.

Guilloché is the pattern on banknotes and watch dials: many fine lines, each a sine wave a little
out of step with the last, so that together they weave. Every file below is generated from a
formula (nothing is traced or downloaded), so there is no licence to carry: it's ours to ship.

  weave.svg      a 48 px tile that repeats in both directions: the mat around the home photograph,
                 the band above the footer, the ground behind the 404 and thank-you pages
  seal-lines.svg a round engine-turned dial for the hallmark seal on the home photograph (the seal's
                 ring of text is set in the page, so it stays real text)

    python3 designs/design-3/imagery/ornaments.py        rewrites designs/design-3/assets/img/ornaments/
"""
import math
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "assets" / "img" / "ornaments"
CHAMPAGNE = "#dcbd88"


def fmt(v):
    s = f"{v:.1f}"
    return s[:-2] if s.endswith(".0") else s


def polyline(points, close=False):
    """A path with relative moves, which keeps the file small."""
    x0, y0 = points[0]
    d = [f"M{fmt(x0)} {fmt(y0)}"]
    px, py = round(x0, 1), round(y0, 1)
    parts = []
    for x, y in points[1:]:
        qx, qy = round(x, 1), round(y, 1)
        parts.append(f"{fmt(qx - px)} {fmt(qy - py)}")
        px, py = qx, qy
    d.append("l" + " ".join(parts).replace(" -", "-"))
    if close:
        d.append("z")
    return "".join(d)


def weave_tile(size=48, lines=8, amp=15.0, stroke=0.8):
    """Lines y = c + A sin(2 pi x / size + phase), phase stepping by 2 pi / lines, so the tile repeats."""
    paths = []
    step = size / lines
    for i in range(-3, lines + 3):
        c = i * step
        phase = i * 2 * math.pi / lines * 3
        pts = [(x, c + amp * math.sin(2 * math.pi * x / size + phase)) for x in [k * size / 48 for k in range(49)]]
        paths.append(polyline(pts))
    body = "".join(f'<path d="{d}"/>' for d in paths)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 {size} {size}" '
            f'fill="none" stroke="{CHAMPAGNE}" stroke-width="{stroke}" stroke-linecap="round">{body}</svg>\n')


def ring(cx, cy, base, amp, lobes, phase, steps=144):
    pts = []
    for k in range(steps + 1):
        t = 2 * math.pi * k / steps
        r = base + amp * math.sin(lobes * t + phase)
        pts.append((cx + r * math.cos(t), cy + r * math.sin(t)))
    return polyline(pts, close=True)


def seal_lines(size=240, stroke=0.6):
    c = size / 2
    layers = []
    for rings, base, amp, lobes in ((14, size * 0.30, size * 0.05, 12), (10, size * 0.19, size * 0.04, 8)):
        for i in range(rings):
            layers.append(ring(c, c, base, amp, lobes, i * 2 * math.pi / rings, steps=84))
    for r in (size * 0.335, size * 0.12):
        layers.append(ring(c, c, r, 0, 1, 0, steps=48))
    body = "".join(f'<path d="{d}"/>' for d in layers)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 {size} {size}" '
            f'fill="none" stroke="{CHAMPAGNE}" stroke-width="{stroke}" stroke-linejoin="round">{body}</svg>\n')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    files = {"weave.svg": weave_tile(), "seal-lines.svg": seal_lines()}
    for name, svg in files.items():
        (OUT / name).write_text(svg, encoding="utf-8")
        print(f"{name}: {len(svg) / 1024:.0f} KiB")


if __name__ == "__main__":
    main()
