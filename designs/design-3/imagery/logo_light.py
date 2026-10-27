"""Design 3: a one-colour, light-on-dark version of the T Wireless wordmark.

The store's logo (src/assets/img/t-wireless-logo-960.png) is red letters and a grey phone on a clear
background. Placed on design 3's dark ground it needed a white box, which looked pasted on. This script
re-inks the same artwork in champagne: the letters and the phone's body become champagne with a soft
vertical gradient, and the phone's white screen becomes clear, so the dark page shows through. The
shapes, spacing and proportions are not touched.

Only the store's own mark is treated this way. Bell, Virgin Plus and Lucky Mobile stay exactly as
supplied, on pearl cards. The full-colour logo is still shipped (structured data uses it) and designs
1 and 2 still show it as it is. The store should approve this one-colour version before launch.

Run from the repository root:  python3 designs/design-3/imagery/logo_light.py
"""
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src" / "assets" / "img" / "t-wireless-logo-960.png"
OUT = ROOT / "designs" / "design-3" / "assets" / "img"

TOP, MID, LOW = (242, 223, 182), (222, 192, 140), (192, 154, 100)   # a champagne gold, lighter at the top


def smoothstep(x, a, b):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def reinked(img: Image.Image) -> Image.Image:
    a = np.asarray(img.convert("RGBA"), dtype=np.float32)
    rgb, alpha = a[..., :3], a[..., 3] / 255.0
    lum = rgb.mean(axis=2)
    grey = (np.abs(rgb[..., 0] - rgb[..., 1]) < 26) & (np.abs(rgb[..., 1] - rgb[..., 2]) < 26)
    # Red letters keep their own coverage. Grey pixels (the phone) keep it only where they are dark or
    # mid-grey: the white screen fades to clear, and the wifi mark stays.
    keep = np.where(grey, 1.0 - smoothstep(lum, 150, 236), 1.0)
    out_alpha = alpha * keep
    h = a.shape[0]
    y = np.linspace(0.0, 1.0, h)[:, None]
    top, mid, low = (np.array(c, dtype=np.float32) for c in (TOP, MID, LOW))
    t = np.where(y < 0.5, y / 0.5, (y - 0.5) / 0.5)[..., None]
    colour = np.where((y < 0.5)[..., None], top + (mid - top) * t, mid + (low - mid) * t)
    colour = np.broadcast_to(colour, (h, a.shape[1], 3))
    res = np.dstack([colour, out_alpha * 255.0])
    return Image.fromarray(np.clip(res + 0.5, 0, 255).astype(np.uint8), "RGBA")


def shrink(img: Image.Image, width: int) -> Image.Image:
    """Downscale with premultiplied alpha, so edges do not pick up a halo."""
    a = np.asarray(img, dtype=np.float32)
    pre = np.dstack([a[..., :3] * (a[..., 3:] / 255.0), a[..., 3:]])
    h = round(img.height * width / img.width)
    chans = [Image.fromarray(pre[..., i]).resize((width, h), Image.LANCZOS) for i in range(4)]
    p = np.dstack([np.asarray(c, dtype=np.float32) for c in chans])
    alpha = np.clip(p[..., 3:], 0, 255)
    rgb = np.where(alpha > 0.5, p[..., :3] / np.maximum(alpha / 255.0, 1e-4), 0)
    return Image.fromarray(np.clip(np.dstack([rgb, alpha]) + 0.5, 0, 255).astype(np.uint8), "RGBA")


def main():
    big = reinked(Image.open(SRC))
    OUT.mkdir(parents=True, exist_ok=True)
    for width in (960, 480):
        im = big if width == big.width else shrink(big, width)
        png, webp = OUT / f"t-wireless-logo-light-{width}.png", OUT / f"t-wireless-logo-light-{width}.webp"
        im.save(png, optimize=True)
        im.save(webp, quality=85, alpha_quality=80, method=6)
        print(png.name, im.size, png.stat().st_size, "bytes;", webp.name, webp.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
