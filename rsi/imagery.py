#!/usr/bin/env python3
"""WEB-DESIGN-RSI-2.0 imagery layer: source, licence, render and audit the photos a design uses.

  fetch   Download each photo's original from an allowed host and record (or check) its SHA-256.
  render  Grade each photo, put the logo screen onto phones that carry one, crop to the design's
          shapes and encode AVIF, WebP and JPEG at several widths; render HTML cards (the social
          preview image); write photos.json, the manifest the build and the measure step read.
  sheet   Contact sheet of the rendered crops with author and licence, for review evidence.
  audit   Licences, hosts, credits and hashes, and every file in the photo folder accounted for.

Layout for a design folder (designs/design-2/ for example):
  imagery/sources.json      what each photo is, where it came from, its licence and its crops
  imagery/originals/        downloaded originals; not committed, `fetch` restores and checks them
  imagery/screens/*.html    what a phone screen in a photo shows (logos included)
  imagery/cards/*.html      composed images (HTML rendered to a picture); design 2 has none, its link
                            preview is a plain crop of the hero photo ("formats": ["jpg"] on that crop)
  assets/img/photos/        rendered files plus photos.json, shipped with the site

Exit: 0 pass, 3 audit failures, 2 blocked.
Needs: Python 3.10+, Pillow with AVIF and WebP, numpy and OpenCV (screen composites),
Playwright for Python with Chromium (screens and cards).
"""
from __future__ import annotations

import argparse
import datetime
import functools
import hashlib
import http.server
import io
import json
import math
import socketserver
import sys
import threading
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image, ImageCms, ImageDraw, ImageEnhance, ImageFont, ImageOps

SERIES = "WEB-DESIGN-RSI-2.0"
SOURCES_SCHEMA = "web.design.imagery.sources.v1"
MANIFEST_SCHEMA = "web.design.imagery.manifest.v1"
REPO = Path(__file__).resolve().parent.parent
FORMATS = ("avif", "webp", "jpg")
PREMIUM_HOSTS = {"plus.unsplash.com"}  # Unsplash+ is a paid licence, never free to use
# Who can be seen in a photo. Logos may only sit on photos where nobody can be recognised, so no
# one appears to endorse the store (a condition of the Pexels and Unsplash licences).
PEOPLE = ("none", "no faces", "identifiable")
LOGO_SAFE_PEOPLE = ("none", "no faces")
FACE_MODEL = Path(__file__).resolve().parent / "models" / "face_detection_yunet_2023mar.onnx"
FACE_SCORE = 0.8


class ImageryError(Exception):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def load_sources(design: Path) -> dict:
    path = design / "imagery" / "sources.json"
    try:
        src = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ImageryError(f"Cannot read {path}: {exc}")
    if src.get("schema") != SOURCES_SCHEMA:
        raise ImageryError(f"{path} is not a {SOURCES_SCHEMA} file")
    ids = [p["id"] for p in src.get("photos", [])] + [c["id"] for c in src.get("cards", [])]
    if len(ids) != len(set(ids)):
        raise ImageryError("photo and card ids must be unique")
    return src


def save_sources(design: Path, src: dict) -> None:
    (design / "imagery" / "sources.json").write_text(json.dumps(src, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- fetch

def fetch(design: Path, refresh: bool = False) -> list[str]:
    src = load_sources(design)
    allowed = set(src.get("allowed_hosts", []))
    notes, changed = [], False
    for p in src["photos"]:
        host = urlparse(p["download_url"]).netloc
        if host in PREMIUM_HOSTS or host not in allowed:
            raise ImageryError(f"{p['id']}: {host} is not an allowed host")
        dest = design / "imagery" / p["original"]
        if dest.exists() and not refresh:
            data = dest.read_bytes()
        else:
            req = urllib.request.Request(p["download_url"], headers={"User-Agent": "Mozilla/5.0 (EMBLEM-NLP imagery fetch)"})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
        digest = sha256_bytes(data)
        if not p.get("original_sha256"):
            p["original_sha256"] = digest
            p["original_size"] = list(Image.open(io.BytesIO(data)).size)
            changed = True
            notes.append(f"{p['id']}: recorded {digest[:12]}")
        elif p["original_sha256"] != digest:
            raise ImageryError(f"{p['id']}: original differs from the recorded hash; the provider may have replaced it")
        else:
            notes.append(f"{p['id']}: ok")
    if changed:
        save_sources(design, src)
    return notes


# ---------------------------------------------------------------- local server for HTML layers

class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class _Renderer:
    """Renders HTML (screens and cards) from the repository over HTTP, so fonts load as they do on the site."""

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        handler = functools.partial(_Quiet, directory=str(REPO))
        self.httpd = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
        self.httpd.daemon_threads = True
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.pw = sync_playwright().start()
        self.browser = self.pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        return self

    def shot(self, html: Path, width: int, height: int, scale: float = 2.0) -> Image.Image:
        page = self.browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=scale)
        rel = Path(html).resolve().relative_to(REPO).as_posix()
        page.goto(f"{self.base}/{rel}", wait_until="networkidle")
        page.evaluate("document.fonts.ready.then(() => true)")
        bad = page.evaluate("[...document.images].filter(i => !(i.complete && i.naturalWidth)).map(i => i.src)")
        if bad:
            raise ImageryError(f"{html}: images did not load: {bad}")
        png = page.screenshot(full_page=False)
        page.close()
        return Image.open(io.BytesIO(png)).convert("RGB")

    def __exit__(self, *exc):
        self.browser.close()
        self.pw.stop()
        self.httpd.shutdown()


# ---------------------------------------------------------------- image work

def to_srgb(im: Image.Image) -> Image.Image:
    im = ImageOps.exif_transpose(im)
    icc = im.info.get("icc_profile")
    if icc:
        try:
            src = ImageCms.ImageCmsProfile(io.BytesIO(icc))
            im = ImageCms.profileToProfile(im, src, ImageCms.createProfile("sRGB"), outputMode="RGB")
        except ImageCms.PyCMSError:
            pass
    return im.convert("RGB")


def _grain(shape, spread, rng, cv2, np, sigma=0.9):
    """Grain like the photographs' own: luminance noise of the photo's grain size (about 0.9 px),
    the same in all three channels with a trace of independent colour. `spread` is the standard
    deviation of the residual against a 1.5 px blur, which is how the grain is measured."""
    h, w = shape[:2]
    n = cv2.GaussianBlur(rng.normal(0, 1, (h, w)).astype(np.float32), (0, 0), sigma)
    n /= float(n.std()) + 1e-6
    r = float((n - cv2.GaussianBlur(n, (0, 0), 1.5)).std()) + 1e-6
    c = cv2.GaussianBlur(rng.normal(0, 1, (h, w, 3)).astype(np.float32), (0, 0), sigma)
    c /= float(c.std()) + 1e-6
    return (n[..., None] * 0.97 + c * 0.1) * (spread / r)


def _grain_spread(img, around, cv2, np):
    """The spread of the photo's grain in the pixels flagged by `around`, measured robustly (the
    median absolute deviation of the luminance residual, so an edge in the ring does not inflate it)."""
    lum = img.mean(2)
    res = lum - cv2.GaussianBlur(lum, (0, 0), 1.5)
    v = res[around]
    if v.size < 20:
        return 1.0
    return float(np.clip(1.4826 * np.median(np.abs(v - np.median(v))), 0.3, 6.0))


def _texture(f, mask, forbid, cv2, np):
    """The photo's own fine texture (weave, grain, noise) for a filled gap: the detail of a clean
    patch of the same surface beside the mark, found by looking at every position around it that
    does not touch the mark or anything in `forbid`, and taking the one with the least going on.
    Returns an image-sized float array of that detail (zero outside the gap's bounding box), or
    None when there is no clean patch to take it from."""
    h, w = mask.shape
    ys, xs = np.nonzero(mask)
    y0, y1, x0, x1 = int(ys.min()), int(ys.max()) + 1, int(xs.min()), int(xs.max()) + 1
    bh, bw = y1 - y0, x1 - x0
    low = cv2.GaussianBlur(f, (0, 0), 4)
    detail = f - low
    forb = cv2.dilate(((mask > 0) | (forbid > 0)).astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
    step = max(6, min(bw, bh) // 8)
    best, best_score = None, None
    for dy in range(-(bh + 40), bh + 41, step):
        for dx in range(-(bw + 40), bw + 41, step):
            sy, sx = y0 + dy, x0 + dx
            if sy < 0 or sx < 0 or sy + bh > h or sx + bw > w or forb[sy:sy + bh, sx:sx + bw].any():
                continue
            patch = detail[sy:sy + bh, sx:sx + bw]
            score = float(np.abs(patch).mean()) + 0.5 * float(np.abs(np.diff(low[sy:sy + bh, sx:sx + bw].mean(2), axis=1)).mean())
            if best_score is None or score < best_score:
                best, best_score = (sy, sx), score
    if best is None:
        return None
    sy, sx = best
    out = np.zeros_like(f)
    out[y0:y1, x0:x1] = detail[sy:sy + bh, sx:sx + bw]
    return out


def _harmonic(img, unknown, scale, cv2, np):
    """Fill the `unknown` pixels of a float image with the smooth (Laplace) continuation of the
    known ones around them. It is worked out coarse to fine, on grids `scale` times (and 2 and 4
    times) coarser than the image, so a large gap converges, then scaled back up."""
    h, w = unknown.shape
    s0 = max(1, int(scale))
    u = None
    for s, iters in ((s0 * 4, 600), (s0 * 2, 500), (s0, 500)):
        gh, gw = max(3, h // s), max(3, w // s)
        small = cv2.resize(img, (gw, gh), interpolation=cv2.INTER_AREA)
        # A coarse cell is unknown when any part of it is, so no known value is polluted by a mark.
        unk = cv2.resize(unknown.astype(np.uint8) * 255, (gw, gh), interpolation=cv2.INTER_AREA) > 0
        known = ~unk
        if not known.any():
            return img
        if u is None:
            cur = small.copy()
            cur[unk] = small[known].mean(0)
        else:
            cur = np.where(unk[..., None], cv2.resize(u, (gw, gh), interpolation=cv2.INTER_LINEAR), small)
        for _ in range(iters):
            p = np.pad(cur, ((1, 1), (1, 1), (0, 0)), mode="edge")
            avg = (p[:-2, 1:-1] + p[2:, 1:-1] + p[1:-1, :-2] + p[1:-1, 2:]) / 4
            new = np.where(unk[..., None], avg, cur)
            done = float(np.abs(new - cur).max()) < 0.005
            cur = new
            if done:
                break
        u = cur
    return cv2.resize(u, (w, h), interpolation=cv2.INTER_CUBIC)


def _erase_marks(out, fix, cv2, np):
    """Erase printed marks (letters, a small logo) from a smooth surface.

    Only the pixels that differ from their surroundings the way printing does are filled, and only
    inside the fix's box or polygon, so skin, shadows and edges next to the mark are left alone.
    The surface is estimated by a morphological closing (dark marks) or opening (light marks) with
    a window larger than the strokes (a number, or [width, height] for a flat window that follows a
    band's rows); with "surface": "median" a median of that window is used instead, which follows a
    tone that changes across the box. Pixels that sit `delta` to `max_delta` levels away from it,
    and are no more colourful than `sat` (0-255), are the mark. The mark is grown by `grow` pixels
    to take its soft edge, filled from what surrounds it, and given the surface's own grain.
    `keep` lists polygons (a finger, an edge) that are never touched, widened by `keep_margin`;
    `protect_sat` (0-255) also leaves alone every pixel more colourful than that (skin beside a
    white case), so the fill cannot dull an edge. For a faint, soft ghost that has no crisp strokes
    to threshold, "whole": true erases the whole polygon, and "method": "laplace" fills it by
    smoothly continuing the tone of the pixels around it (`scale` sets the working grid), which
    follows a gradient the way a flat fill cannot. A fill is smoother than the photo, so it is
    given the photo's grain back: noise like it by default (scaled by "grain", 1.0 unless the
    ring around the mark is busier than the surface itself, which a soft, out-of-focus surface
    beside a hard edge can make it), or with "texture": "copy" the real fine detail of a clean
    patch of the same surface beside the mark (for a woven fabric).
    """
    h, w = out.shape[:2]
    if "poly" in fix:
        pts = np.array(fix["poly"], np.int32)
        x0, y0 = pts.min(0)
        x1, y1 = pts.max(0)
    else:
        x0, y0, x1, y1 = fix["box"]
        pts = np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], np.int32)
    win = fix.get("window", 61)
    kw, kh = (int(win[0]) | 1, int(win[1]) | 1) if isinstance(win, (list, tuple)) else (int(win) | 1, int(win) | 1)
    k = max(kw, kh)
    grow = int(fix.get("grow", 3))
    radius = int(fix.get("radius", 4))
    pad = k + grow + radius + 8
    if fix.get("texture") == "copy":  # room to look for a clean patch beside the mark
        pad = max(pad, int(max(x1 - x0, y1 - y0)) * 2 + 60)
    X0, Y0, X1, Y1 = max(0, int(x0) - pad), max(0, int(y0) - pad), min(w, int(x1) + pad), min(h, int(y1) + pad)
    roi = out[Y0:Y1, X0:X1].copy()
    lum = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY).astype(np.int16)
    sat = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)[..., 1]
    light = fix.get("mark", "dark") == "light"
    se = cv2.getStructuringElement(cv2.MORPH_RECT if isinstance(win, (list, tuple)) else cv2.MORPH_ELLIPSE, (kw, kh))
    median = fix.get("surface") == "median"  # for a tone that changes across the box: a median follows it, an envelope lifts it
    if median:
        surface = cv2.medianBlur(lum.astype(np.uint8), k).astype(np.int16)
    else:
        surface = cv2.morphologyEx(lum.astype(np.uint8), cv2.MORPH_OPEN if light else cv2.MORPH_CLOSE, se).astype(np.int16)
    diff = (lum - surface) if light else (surface - lum)
    region = np.zeros(lum.shape, np.uint8)
    cv2.fillPoly(region, [(pts - np.array([X0, Y0])).astype(np.int32)], 255)
    mark = (diff >= fix.get("delta", 12)) & (diff <= fix.get("max_delta", 255)) & (sat <= fix.get("sat", 255))
    mask = (mark & (region > 0)).astype(np.uint8) * 255
    if fix.get("whole"):
        mask = region.copy()
    if grow and not fix.get("whole"):
        mask = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * grow + 1, 2 * grow + 1)))
    mask[region == 0] = 0
    protect = None
    if "protect_sat" in fix:  # colourful pixels (skin) beside a neutral surface are never touched
        protect = (sat > int(fix["protect_sat"])).astype(np.uint8) * 255
        protect = cv2.dilate(protect, np.ones((3, 3), np.uint8))
        mask[protect > 0] = 0
    keep_mask = None
    if fix.get("keep"):  # polygons that must stay as they are: a finger, an edge that touches the mark
        keep = np.zeros(lum.shape, np.uint8)
        for poly in fix["keep"]:
            cv2.fillPoly(keep, [(np.array(poly, np.int32) - np.array([X0, Y0])).astype(np.int32)], 255)
        m = int(fix.get("keep_margin", 0))
        if m:
            keep = cv2.dilate(keep, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * m + 1, 2 * m + 1)))
        mask[keep > 0] = 0
        keep_mask = keep
    if not mask.any():
        raise ImageryError(f"retouch found nothing to erase: {fix.get('why', '')}")
    method = fix.get("method", "surface")
    if method == "inpaint":
        filled = cv2.inpaint(roi, mask, radius, cv2.INPAINT_TELEA).astype(np.float32)
    elif method == "laplace":
        unknown = (mask > 0) | (protect > 0 if protect is not None else False)
        if keep_mask is not None:
            unknown |= keep_mask > 0
        filled = _harmonic(roi.astype(np.float32), unknown, int(fix.get("scale", 6)), cv2, np)
    else:
        # Fill with the surface itself, channel by channel, so a neighbouring finger or edge cannot
        # bleed its colour into the gap the way inpainting lets it.
        op = cv2.MORPH_OPEN if light else cv2.MORPH_CLOSE
        if median:
            surf = cv2.merge([cv2.medianBlur(roi[..., c], k) for c in range(3)]).astype(np.float32)
        else:
            surf = cv2.merge([cv2.morphologyEx(roi[..., c], op, se) for c in range(3)]).astype(np.float32)
        filled = cv2.GaussianBlur(surf, (0, 0), sigmaX=max(1.0, kw / 20), sigmaY=max(1.0, kh / 20))
    # An envelope sits a little below (or above) the surface's mean tone, so shift the fill to the
    # tone of the untouched pixels around the mark; then add their grain back, as a fill is smoother.
    f = roi.astype(np.float32)
    ring = cv2.dilate(mask, np.ones((25, 25), np.uint8)) > 0
    ring &= mask == 0
    if keep_mask is not None:
        ring &= keep_mask == 0
    if protect is not None:
        ring &= protect == 0
    if ring.any() and method == "surface":
        filled = filled + np.median(f[ring] - filled[ring], axis=0)
    rng = np.random.default_rng(11)
    tex = None
    if fix.get("texture") == "copy":
        forbid = np.zeros(mask.shape, np.uint8)
        if keep_mask is not None:
            forbid |= keep_mask
        if protect is not None:
            forbid |= protect
        tex = _texture(f, mask, forbid, cv2, np)
    if tex is not None:
        filled = filled + tex
    else:
        sd = (_grain_spread(f, ring, cv2, np) if ring.any() else 1.0) * float(fix.get("grain", 1.0))
        filled = filled + _grain(filled.shape, sd, rng, cv2, np)
    soft = cv2.GaussianBlur(mask.astype(np.float32) / 255.0, (0, 0), float(fix.get("feather", 1.5)))[..., None]
    soft = np.maximum(soft, (mask > 0)[..., None].astype(np.float32))
    if protect is not None:
        soft[protect > 0] = 0
    if keep_mask is not None:
        soft[keep_mask > 0] = 0
    filled = np.clip(f * (1 - soft) + filled * soft, 0, 255).astype(np.uint8)
    out[Y0:Y1, X0:X1] = filled
    return out


def _fill_rows(out, fix, cv2, np):
    """Fill a box row by row, from the pixels just left and right of it (or column by column, from
    the pixels above and below, with "axis": "cols"). For a band or rim whose tone changes across
    it but not along it, this continues the tone exactly, where a four-sided blend leaves a flat
    patch. Grain from the surroundings is added back."""
    x0, y0, x1, y1 = fix["box"]
    band = int(fix.get("band", 8))
    f = out.astype(np.float32)
    rng = np.random.default_rng(11)
    if fix.get("axis", "rows") == "rows":
        a = cv2.GaussianBlur(f[y0:y1, x0 - band:x0].mean(1, keepdims=True), (0, 0), sigmaX=0.1, sigmaY=float(fix.get("smooth", 1.5)))
        b = cv2.GaussianBlur(f[y0:y1, x1:x1 + band].mean(1, keepdims=True), (0, 0), sigmaX=0.1, sigmaY=float(fix.get("smooth", 1.5)))
        if "cap" in fix:  # a highlight at the far end must not streak across the whole patch
            b = np.minimum(b, a + float(fix["cap"]))
        t = ((np.arange(x1 - x0) + 0.5) / (x1 - x0))[None, :, None]
        patch = (1 - t) * a + t * b
        ring = np.concatenate([f[y0:y1, x0 - band:x0].reshape(-1, 3), f[y0:y1, x1:x1 + band].reshape(-1, 3)])
    else:
        a = cv2.GaussianBlur(f[y0 - band:y0, x0:x1].mean(0, keepdims=True), (0, 0), sigmaX=float(fix.get("smooth", 1.5)), sigmaY=0.1)
        b = cv2.GaussianBlur(f[y1:y1 + band, x0:x1].mean(0, keepdims=True), (0, 0), sigmaX=float(fix.get("smooth", 1.5)), sigmaY=0.1)
        t = ((np.arange(y1 - y0) + 0.5) / (y1 - y0))[:, None, None]
        patch = (1 - t) * a + t * b
        ring = np.concatenate([f[y0 - band:y0, x0:x1].reshape(-1, 3), f[y1:y1 + band, x0:x1].reshape(-1, 3)])
    sd = 1.0
    if ring.size:
        near = f[y0:y1, x0 - band:x0] if fix.get("axis", "rows") == "rows" else f[y0 - band:y0, x0:x1]
        nl = near.mean(2)
        nres = nl - cv2.GaussianBlur(nl, (0, 0), 1.5)
        sd = float(np.clip(1.4826 * np.median(np.abs(nres - np.median(nres))), 0.3, 6.0))
    patch = patch + _grain(patch.shape, sd, rng, cv2, np)
    # Fade the patch in over `feather` pixels at every side so no edge shows.
    fe = int(fix.get("feather", 0))
    if fe:
        hh, ww = y1 - y0, x1 - x0
        wy = np.clip(np.minimum(np.arange(hh) + 1, hh - np.arange(hh)) / fe, 0, 1)[:, None, None]
        wx = np.clip(np.minimum(np.arange(ww) + 1, ww - np.arange(ww)) / fe, 0, 1)[None, :, None]
        w = np.minimum(wy, wx) if fix.get("fade_all", True) else (wx if fix.get("axis", "rows") == "rows" else wy)
        patch = out[y0:y1, x0:x1].astype(np.float32) * (1 - w) + patch * w
    out[y0:y1, x0:x1] = np.clip(patch, 0, 255).astype(np.uint8)
    return out


def retouch(im: Image.Image, fixes: list) -> Image.Image:
    """Fill listed boxes from their surroundings (OpenCV inpainting): small third-party logos on
    parts or signs that a photo happens to show. Each fix records why.

    A fix is a box or a polygon plus `fill`: "smooth" (the default: blend the box from its edges),
    "inpaint" (OpenCV inpainting over the whole box), "rows" (continue each row from its two ends,
    for a band; see _fill_rows) or "marks" (only the printed pixels inside the box or polygon are
    erased; see _erase_marks)."""
    if not fixes:
        return im
    import cv2
    import numpy as np
    arr = cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2BGR)
    out = arr.copy()
    rng = np.random.default_rng(11)
    for fix in fixes:
        if fix.get("fill") == "marks":
            out = _erase_marks(out, fix, cv2, np)
            continue
        x0, y0, x1, y1 = fix["box"]
        if fix.get("fill") == "rows":
            out = _fill_rows(out, fix, cv2, np)
            continue
        if fix.get("fill", "smooth") == "inpaint":
            mask = np.zeros(arr.shape[:2], np.uint8)
            mask[y0:y1, x0:x1] = 255
            out = cv2.inpaint(out, mask, fix.get("radius", 15), cv2.INPAINT_TELEA)
            continue
        # Smooth fill: blend the box from its four edges (a Coons patch), each edge averaged over a
        # band and blurred along its length, then add grain that matches the surroundings.
        band = fix.get("band", 8)
        f = out.astype(np.float32)
        top = cv2.GaussianBlur(f[y0 - band:y0, x0:x1].mean(0, keepdims=True), (0, 0), sigmaX=6, sigmaY=0.1)[0]
        bot = cv2.GaussianBlur(f[y1:y1 + band, x0:x1].mean(0, keepdims=True), (0, 0), sigmaX=6, sigmaY=0.1)[0]
        lef = cv2.GaussianBlur(f[y0:y1, x0 - band:x0].mean(1, keepdims=True), (0, 0), sigmaX=0.1, sigmaY=6)[:, 0]
        rig = cv2.GaussianBlur(f[y0:y1, x1:x1 + band].mean(1, keepdims=True), (0, 0), sigmaX=0.1, sigmaY=6)[:, 0]
        h, w = y1 - y0, x1 - x0
        u = ((np.arange(w) + 1) / (w + 1))[None, :, None]
        v = ((np.arange(h) + 1) / (h + 1))[:, None, None]
        c00, c10 = f[y0 - 1, x0 - 1], f[y0 - 1, x1]
        c01, c11 = f[y1, x0 - 1], f[y1, x1]
        patch = ((1 - v) * top[None] + v * bot[None] + (1 - u) * lef[:, None] + u * rig[:, None]
                 - ((1 - u) * (1 - v) * c00 + u * (1 - v) * c10 + (1 - u) * v * c01 + u * v * c11))
        above = f[y0 - band:y0, x0:x1].mean(2)
        ares = above - cv2.GaussianBlur(above, (0, 0), 1.5)
        sd = float(np.clip(1.4826 * np.median(np.abs(ares - np.median(ares))), 0.3, 6.0)) if above.size else 1.0
        patch += _grain(patch.shape, sd, rng, cv2, np)
        out[y0:y1, x0:x1] = np.clip(patch, 0, 255).astype(np.uint8)
    return Image.fromarray(cv2.cvtColor(out, cv2.COLOR_BGR2RGB))


def tone(im: Image.Image, spec: dict) -> Image.Image:
    """Map the photo's tones onto a three-colour palette (shadows, mid-tones, highlights) and blend the
    result with the original by `strength`. For a photo whose colours fight the rest of a design (a blue
    dusk sky, a green lawn) this pulls it towards the design's own warmth without turning it into a duotone."""
    import numpy as np
    strength = min(max(float(spec.get("strength", 0.5)), 0.0), 1.0)
    dark = np.array(spec.get("dark", [20, 8, 12]), np.float32)
    mid = np.array(spec.get("mid", [120, 60, 52]), np.float32)
    light = np.array(spec.get("light", [240, 214, 170]), np.float32)
    g = np.asarray(ImageOps.grayscale(im), np.float32)[..., None] / 255.0
    mapped = np.where(g < 0.5, dark + (mid - dark) * np.clip(g / 0.5, 0, 1),
                      mid + (light - mid) * np.clip((g - 0.5) / 0.5, 0, 1))
    base = np.asarray(im.convert("RGB"), np.float32)
    return Image.fromarray(np.clip(base * (1 - strength) + mapped * strength, 0, 255).astype(np.uint8))


def grade(im: Image.Image, g: dict) -> Image.Image:
    if g.get("saturation", 1) != 1:
        im = ImageEnhance.Color(im).enhance(g["saturation"])
    if g.get("contrast", 1) != 1:
        im = ImageEnhance.Contrast(im).enhance(g["contrast"])
    if g.get("brightness", 1) != 1:
        im = ImageEnhance.Brightness(im).enhance(g["brightness"])
    if g.get("tone"):
        im = tone(im, g["tone"])
    return im


def find_screen(rgb: Image.Image):
    """Find a blank (white) phone screen: returns its four corners (TL, TR, BR, BL) and a mask.

    The screen's corners are rounded, so each edge is fitted as a line away from the corners and
    the corners are where those lines meet; the mask keeps the real rounded outline.
    """
    import cv2
    import numpy as np

    bgr = cv2.cvtColor(np.asarray(rgb), cv2.COLOR_RGB2BGR)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    mask = ((hsv[..., 2] > 200) & (hsv[..., 1] < 30)).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask)
    h_img, w_img = mask.shape
    # A screen sits inside the frame; a light background touches its edges.
    inside = [k for k in range(1, n)
              if stats[k, cv2.CC_STAT_LEFT] > 0 and stats[k, cv2.CC_STAT_TOP] > 0
              and stats[k, cv2.CC_STAT_LEFT] + stats[k, cv2.CC_STAT_WIDTH] < w_img
              and stats[k, cv2.CC_STAT_TOP] + stats[k, cv2.CC_STAT_HEIGHT] < h_img]
    if not inside:
        raise ImageryError("no blank screen found")
    i = max(inside, key=lambda k: stats[k, cv2.CC_STAT_AREA])
    comp = (lab == i).astype(np.uint8) * 255
    contours, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    c = max(contours, key=cv2.contourArea)
    filled = comp  # keeps whatever is in front of the screen (a thumb, a camera cutout) in front
    hull = cv2.convexHull(c)
    approx = cv2.approxPolyDP(hull, 0.02 * cv2.arcLength(hull, True), True).reshape(-1, 2).astype(np.float64)
    if len(approx) != 4:
        raise ImageryError(f"screen outline has {len(approx)} corners, expected 4")
    s, d = approx.sum(1), approx[:, 1] - approx[:, 0]
    corners = np.array([approx[s.argmin()], approx[d.argmin()], approx[s.argmax()], approx[d.argmax()]])
    pts = c.reshape(-1, 2).astype(np.float64)
    tol = max(2.0, 0.0012 * math.hypot(*comp.shape))
    rng = np.random.default_rng(7)
    lines = []
    for k in range(4):
        a, b = corners[k], corners[(k + 1) % 4]
        L = np.linalg.norm(b - a)
        u = (b - a) / L
        rel = pts - a
        t = rel @ u
        dist = np.abs(rel @ np.array([-u[1], u[0]]))
        cand = pts[(t > 0.04 * L) & (t < 0.96 * L) & (dist < 0.08 * L + 8)]
        if len(cand) < 20:
            raise ImageryError("not enough of a screen edge is visible")
        # RANSAC: the edge is the line with the most contour points on it; a thumb or a rounded
        # corner bends away from it and is left out.
        best = None
        for _ in range(400):
            p1, p2 = cand[rng.choice(len(cand), 2, replace=False)]
            v = p2 - p1
            n = np.linalg.norm(v)
            if n < 0.1 * L:
                continue
            normal = np.array([-v[1], v[0]]) / n
            inl = np.abs((cand - p1) @ normal) < tol
            if best is None or inl.sum() > best.sum():
                best = inl
        vx, vy, x0, y0 = cv2.fitLine(cand[best].astype(np.float32), cv2.DIST_L2, 0, 0.01, 0.01).ravel()
        lines.append((np.array([x0, y0]), np.array([vx, vy])))
    quad = []
    for k in range(4):
        (p1, d1), (p2, d2) = lines[k - 1], lines[k]
        t = np.linalg.solve(np.array([d1, -d2]).T, p2 - p1)
        quad.append(p1 + t[0] * d1)
    return np.array(quad, dtype=np.float32), filled


def screen_size(quad) -> tuple[float, float]:
    import numpy as np
    w = (np.linalg.norm(quad[1] - quad[0]) + np.linalg.norm(quad[2] - quad[3])) / 2
    h = (np.linalg.norm(quad[3] - quad[0]) + np.linalg.norm(quad[2] - quad[1])) / 2
    return float(w), float(h)


def put_on_screen(photo: Image.Image, ui: Image.Image, quad, mask) -> Image.Image:
    """Warp the screen image onto the phone, keep the real rounded corners and the photo's light."""
    import cv2
    import numpy as np

    W, H = photo.size
    uw, uh = ui.size
    m = cv2.getPerspectiveTransform(np.float32([[0, 0], [uw, 0], [uw, uh], [0, uh]]), quad)
    ui_arr = np.asarray(ui.convert("RGB")).astype(np.float32)
    warped = cv2.warpPerspective(ui_arr, m, (W, H), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REPLICATE)
    warped = cv2.GaussianBlur(warped, (0, 0), 0.6)
    base = np.asarray(photo).astype(np.float32)
    # The blank screen's own shading (light falloff) carries over, normalised so white stays near white.
    lum = cv2.cvtColor(base.astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32)
    inside = mask > 0
    shade = cv2.GaussianBlur(np.where(inside, lum, 0), (0, 0), 40) / (cv2.GaussianBlur(inside.astype(np.float32), (0, 0), 40) + 1e-6)
    ref = np.percentile(lum[inside], 95)
    shade = np.clip(shade / ref, 0.88, 1.0)[..., None]
    alpha = cv2.GaussianBlur(cv2.dilate(mask, np.ones((3, 3), np.uint8)).astype(np.float32) / 255, (0, 0), 1.0)[..., None]
    out = base * (1 - alpha) + (warped * shade) * alpha
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))


def crop_box(size, aspect: float, focus, zoom: float = 1.0):
    W, H = size
    if W / H > aspect:
        ch = H / zoom
        cw = ch * aspect
    else:
        cw = W / zoom
        ch = cw / aspect
    cx, cy = focus[0] * W, focus[1] * H
    left = min(max(cx - cw / 2, 0), W - cw)
    top = min(max(cy - ch / 2, 0), H - ch)
    return round(left), round(top), round(left + cw), round(top + ch)


def parse_aspect(name: str) -> float:
    a, b = name.split("x")
    return float(a) / float(b)


def encode(im: Image.Image, fmt: str, settings: dict) -> bytes:
    buf = io.BytesIO()
    q = settings.get(fmt, {}).get("quality")
    if fmt == "avif":
        im.save(buf, "AVIF", quality=q or 52, speed=settings.get("avif", {}).get("speed", 6))
    elif fmt == "webp":
        im.save(buf, "WEBP", quality=q or 76, method=6)
    elif fmt == "jpg":
        im.save(buf, "JPEG", quality=q or 80, optimize=True, progressive=True, subsampling=2)
    elif fmt == "png":
        im.save(buf, "PNG", optimize=True)
    else:
        raise ImageryError(f"unknown format {fmt}")
    return buf.getvalue()


def credit_of(p: dict, licenses: dict) -> dict:
    lic = licenses.get(p["license"], {})
    return {"provider": p["provider"], "provider_id": p.get("provider_id"), "page_url": p["page_url"],
            "author": p["author"], "author_url": p.get("author_url"), "license": p["license"],
            "license_url": lic.get("url"), "retrieved": p.get("retrieved")}


# ---------------------------------------------------------------- render

def render(design: Path, only: list[str] | None = None) -> dict:
    src = load_sources(design)
    out_dir = design / "assets" / "img" / "photos"
    manifest_path = out_dir / "photos.json"
    old = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"photos": {}, "cards": {}}
    manifest = {"schema": MANIFEST_SCHEMA, "measurement_series": SERIES, "design_id": src["design_id"],
                "generated": datetime.date.today().isoformat(), "photos": {}, "cards": {}}
    settings = src.get("encode", {})
    out_dir.mkdir(parents=True, exist_ok=True)
    rendered_files = set()
    with _Renderer() as r:
        for p in src["photos"]:
            if only and p["id"] not in only and p["id"] in old.get("photos", {}):
                kept = dict(old["photos"][p["id"]])
                kept.update({"source": credit_of(p, src.get("licenses", {})), "alt": p["alt"], "people": p.get("people"),
                             "logo_safe": p.get("people") in LOGO_SAFE_PEOPLE, "description": p.get("description")})
                manifest["photos"][p["id"]] = kept
                for c in old["photos"][p["id"]]["crops"].values():
                    rendered_files.update(f["file"] for fs in c["files"].values() for f in fs)
                continue
            orig = design / "imagery" / p["original"]
            if not orig.exists():
                raise ImageryError(f"{p['id']}: original missing; run fetch")
            if p.get("original_sha256") and sha256_file(orig) != p["original_sha256"]:
                raise ImageryError(f"{p['id']}: original does not match its recorded hash")
            im = grade(retouch(to_srgb(Image.open(orig)), p.get("retouch", [])), {**src.get("grade", {}), **p.get("grade", {})})
            entry = {"source": credit_of(p, src.get("licenses", {})), "alt": p["alt"], "people": p.get("people"),
                     "logo_safe": p.get("people") in LOGO_SAFE_PEOPLE,
                     "description": p.get("description"), "retouched": list(dict.fromkeys(f["why"] for f in p.get("retouch", []))),
                     "logos": [], "kind": "photo", "crops": {}}
            if p.get("screen"):
                quad, mask = find_screen(im)
                sw, sh = screen_size(quad)
                css_w = p["screen"].get("css_width", 540)
                css_h = round(css_w * sh / sw)
                ui = r.shot(design / "imagery" / p["screen"]["ui"], css_w, css_h, scale=max(1.0, sw / css_w))
                im = put_on_screen(im, ui, quad, mask)
                entry["kind"] = "composite"
                entry["logos"] = p["screen"].get("logos", [])
                entry["screen_quad"] = [[round(float(x), 1), round(float(y), 1)] for x, y in quad]
            for crop_name, spec in p["crops"].items():
                box = crop_box(im.size, parse_aspect(crop_name), spec.get("focus", [0.5, 0.5]), spec.get("zoom", 1.0))
                cut = im.crop(box)
                fmts = tuple(spec.get("formats", FORMATS))  # a crop used only as a JPEG (the link preview) lists just that
                files = {f: [] for f in fmts}
                widths = [w for w in spec["widths"] if w <= cut.width] or [cut.width]
                for w in widths:
                    h = round(w * cut.height / cut.width)
                    small = cut.resize((w, h), Image.LANCZOS)
                    for fmt in fmts:
                        data = encode(small, fmt, settings)
                        name = f"{p['id']}-{crop_name}-{w}.{fmt}"
                        (out_dir / name).write_bytes(data)
                        rendered_files.add(name)
                        files[fmt].append({"file": name, "w": w, "h": h, "bytes": len(data), "sha256": sha256_bytes(data)})
                entry["crops"][crop_name] = {"aspect": round(parse_aspect(crop_name), 5), "box": list(box), "files": files}
            manifest["photos"][p["id"]] = entry
            print(f"rendered {p['id']} ({entry['kind']}): {', '.join(entry['crops'])}")
        # Cards are composed in HTML from rendered photos, so they come last.
        for c in src.get("cards", []):
            w, h = c["size"]
            img = r.shot(design / "imagery" / c["html"], w, h, scale=1.0)
            files = {}
            for fmt in c.get("formats", ["jpg"]):
                data = encode(img, fmt, settings)
                name = f"{c['id']}.{fmt}"
                (out_dir / name).write_bytes(data)
                rendered_files.add(name)
                files[fmt] = [{"file": name, "w": w, "h": h, "bytes": len(data), "sha256": sha256_bytes(data)}]
            manifest["cards"][c["id"]] = {"kind": "card", "alt": c["alt"], "uses": c.get("uses", []),
                                          "logos": c.get("logos", []), "files": files}
            print(f"rendered card {c['id']}")
    for f in out_dir.iterdir():
        if f.is_file() and f.name != "photos.json" and f.name not in rendered_files:
            f.unlink()  # a crop or width that is no longer specified
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


# ---------------------------------------------------------------- audit

def count_faces(path: Path) -> int:
    """Faces YuNet finds in an image (scaled to 960 px on the long side)."""
    import os
    os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")
    import cv2
    img = cv2.imread(str(path))
    h, w = img.shape[:2]
    scale = 960 / max(h, w)
    if scale < 1:
        img = cv2.resize(img, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
    h, w = img.shape[:2]
    det = cv2.FaceDetectorYN.create(str(FACE_MODEL), "", (w, h), FACE_SCORE, 0.3, 50)
    _, faces = det.detect(img)
    return 0 if faces is None else len(faces)


def audit(design: Path, require_originals: bool = False) -> dict:
    src = load_sources(design)
    errors, warnings = [], []
    licenses = src.get("licenses", {})
    allowed = set(src.get("allowed_hosts", []))
    for p in src["photos"]:
        pid = p["id"]
        for key in ("provider", "page_url", "download_url", "author", "license", "alt", "retrieved", "people"):
            if not p.get(key):
                errors.append(f"{pid}: {key} missing")
        if p.get("license") not in licenses:
            errors.append(f"{pid}: licence {p.get('license')!r} is not one this design allows")
        elif not licenses[p["license"]].get("commercial"):
            errors.append(f"{pid}: licence does not allow commercial use")
        host = urlparse(p.get("download_url", "")).netloc
        if host in PREMIUM_HOSTS:
            errors.append(f"{pid}: {host} is a paid licence")
        elif host not in allowed:
            errors.append(f"{pid}: {host} is not an allowed host")
        if not str(p.get("page_url", "")).startswith("https://"):
            errors.append(f"{pid}: page_url must be an https link to the photo's page")
        for fix in p.get("retouch", []):
            if not fix.get("why") or not (len(fix.get("box", [])) == 4 or (len(fix.get("poly", [])) >= 3 and fix.get("fill") == "marks")):
                errors.append(f"{pid}: each retouch needs a box (or, for fill 'marks', a polygon) and a reason")
        if p.get("people") not in PEOPLE:
            errors.append(f"{pid}: people must be one of {', '.join(PEOPLE)}")
        if p.get("screen") and p.get("people") not in LOGO_SAFE_PEOPLE:
            errors.append(f"{pid}: logos are put on this photo's screen, but someone in it can be recognised")
        orig = design / "imagery" / p.get("original", "")
        if not p.get("original_sha256"):
            errors.append(f"{pid}: original_sha256 not recorded; run fetch")
        elif orig.is_file():
            if sha256_file(orig) != p["original_sha256"]:
                errors.append(f"{pid}: original does not match its recorded hash")
        elif require_originals:
            errors.append(f"{pid}: original missing")
        else:
            warnings.append(f"{pid}: original not present here (fetch restores it)")
    out_dir = design / "assets" / "img" / "photos"
    manifest_path = out_dir / "photos.json"
    files_total = bytes_total = 0
    if not manifest_path.exists():
        errors.append("photos.json missing; run render")
    else:
        m = json.loads(manifest_path.read_text())
        listed = {}
        for pid, e in m.get("photos", {}).items():
            if pid not in {p["id"] for p in src["photos"]}:
                errors.append(f"photos.json lists {pid}, which has no source")
            for crop in e["crops"].values():
                for fs in crop["files"].values():
                    for f in fs:
                        listed[f["file"]] = f
        for cid, e in m.get("cards", {}).items():
            for fs in e["files"].values():
                for f in fs:
                    listed[f["file"]] = f
            for used in e.get("uses", []):
                if used not in m.get("photos", {}):
                    errors.append(f"card {cid} uses {used}, which is not rendered")
        for p in src["photos"]:
            e = m.get("photos", {}).get(p["id"])
            if e and (e.get("people") != p.get("people") or e.get("alt") != p.get("alt")
                      or (e.get("source") or {}).get("license") != p.get("license")
                      or (e.get("source") or {}).get("page_url") != p.get("page_url")):
                errors.append(f"{p['id']}: photos.json is out of date with sources.json; run render")
        for p in src["photos"]:
            if p["id"] not in m.get("photos", {}):
                errors.append(f"{p['id']}: not rendered; run render")
            elif p.get("people") in LOGO_SAFE_PEOPLE and FACE_MODEL.is_file():
                # A photo said to show nobody recognisable must not show a face in any crop.
                for crop_name, crop in m["photos"][p["id"]]["crops"].items():
                    biggest = max(crop["files"]["jpg"], key=lambda f: f["w"])
                    path = out_dir / biggest["file"]
                    if path.is_file():
                        n = count_faces(path)
                        if n:
                            errors.append(f"{p['id']} {crop_name}: marked '{p['people']}' but {n} face(s) found")
            elif p.get("people") in LOGO_SAFE_PEOPLE:
                warnings.append(f"{p['id']}: face model missing, faces not checked")
        for name, f in listed.items():
            path = out_dir / name
            if not path.is_file():
                errors.append(f"{name}: listed but missing")
            elif sha256_file(path) != f["sha256"]:
                errors.append(f"{name}: changed since render")
            else:
                files_total += 1
                bytes_total += path.stat().st_size
        for path in out_dir.iterdir():
            if path.is_file() and path.name != "photos.json" and path.name not in listed:
                errors.append(f"{path.name}: in the photo folder but not in photos.json (unknown source)")
    return {"schema": "web.design.imagery.audit.v1", "measurement_series": SERIES, "design_id": src["design_id"],
            "pass": not errors, "errors": errors, "warnings": warnings, "photos": len(src["photos"]),
            "cards": len(src.get("cards", [])), "files": files_total, "bytes": bytes_total}


# ---------------------------------------------------------------- sheet

def sheet(design: Path, out: Path, cell: int = 300) -> Path:
    src = load_sources(design)
    m = json.loads((design / "assets" / "img" / "photos" / "photos.json").read_text())
    try:
        bold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 15)
        reg = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 13)
    except OSError:
        bold = reg = ImageFont.load_default()
    tiles = []
    for p in src["photos"]:
        e = m["photos"][p["id"]]
        for crop_name, crop in e["crops"].items():
            biggest = max(crop["files"]["jpg"], key=lambda f: f["w"])
            im = Image.open(design / "assets" / "img" / "photos" / biggest["file"]).convert("RGB")
            im.thumbnail((cell, cell))
            tiles.append((im, f"{p['id']} {crop_name}", f"{p['author']}, {p['provider']}", p["license"]
                          + (f"; logos: {', '.join(e['logos'])}" if e["logos"] else "")))
    cols = 4
    rows = (len(tiles) + cols - 1) // cols
    th = cell + 62
    img = Image.new("RGB", (cols * (cell + 16) + 16, rows * th + 16), "white")
    d = ImageDraw.Draw(img)
    for n, (im, a, b, c) in enumerate(tiles):
        x, y = 16 + (n % cols) * (cell + 16), 16 + (n // cols) * th
        img.paste(im, (x + (cell - im.width) // 2, y + (cell - im.height) // 2))
        d.text((x, y + cell + 4), a, fill="black", font=bold)
        d.text((x, y + cell + 23), b, fill=(60, 60, 60), font=reg)
        d.text((x, y + cell + 40), c, fill=(60, 60, 60), font=reg)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("fetch", "render", "sheet", "audit"):
        s = sub.add_parser(name)
        s.add_argument("--design", type=Path, required=True, help="Design folder, for example designs/design-2")
        if name == "fetch":
            s.add_argument("--refresh", action="store_true", help="Download again even if the original is here")
        if name == "render":
            s.add_argument("--only", nargs="*", help="Re-render these photo ids; keep the rest as they are")
        if name == "sheet":
            s.add_argument("--out", type=Path, required=True)
        if name == "audit":
            s.add_argument("--require-originals", action="store_true")
            s.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    try:
        design = a.design.resolve()
        if a.cmd == "fetch":
            for line in fetch(design, a.refresh):
                print(line)
            return 0
        if a.cmd == "render":
            m = render(design, a.only)
            print(f"photos.json: {len(m['photos'])} photos, {len(m['cards'])} cards")
            res = audit(design)
        elif a.cmd == "sheet":
            print(sheet(design, a.out))
            return 0
        else:
            res = audit(design, a.require_originals)
            if a.out:
                a.out.write_text(json.dumps(res, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({k: v for k, v in res.items() if k != "warnings"}, indent=2))
        return 0 if res["pass"] else 3
    except ImageryError as exc:
        print(json.dumps({"schema": "web.design.imagery.error.v1", "status": "BLOCKED", "error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
