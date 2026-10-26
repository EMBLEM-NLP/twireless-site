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
  imagery/cards/*.html      composed images such as the social preview
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


def retouch(im: Image.Image, fixes: list) -> Image.Image:
    """Fill listed boxes from their surroundings (OpenCV inpainting): small third-party logos on
    parts or signs that a photo happens to show. Each fix records why."""
    if not fixes:
        return im
    import cv2
    import numpy as np
    arr = cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2BGR)
    out = arr.copy()
    rng = np.random.default_rng(11)
    for fix in fixes:
        x0, y0, x1, y1 = fix["box"]
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
        ring = np.concatenate([f[y0 - band:y0, x0:x1].reshape(-1, 3), f[y1:y1 + band, x0:x1].reshape(-1, 3)])
        grain = cv2.GaussianBlur(f[y0 - band:y0, x0:x1], (0, 0), 2)
        sd = float(np.clip((f[y0 - band:y0, x0:x1] - grain).std(), 0.5, 6.0)) if ring.size else 1.0
        patch += rng.normal(0, sd, patch.shape).astype(np.float32)
        out[y0:y1, x0:x1] = np.clip(patch, 0, 255).astype(np.uint8)
    return Image.fromarray(cv2.cvtColor(out, cv2.COLOR_BGR2RGB))


def grade(im: Image.Image, g: dict) -> Image.Image:
    if g.get("saturation", 1) != 1:
        im = ImageEnhance.Color(im).enhance(g["saturation"])
    if g.get("contrast", 1) != 1:
        im = ImageEnhance.Contrast(im).enhance(g["contrast"])
    if g.get("brightness", 1) != 1:
        im = ImageEnhance.Brightness(im).enhance(g["brightness"])
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
                     "description": p.get("description"), "retouched": [f["why"] for f in p.get("retouch", [])],
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
                files = {f: [] for f in FORMATS}
                widths = [w for w in spec["widths"] if w <= cut.width] or [cut.width]
                for w in widths:
                    h = round(w * cut.height / cut.width)
                    small = cut.resize((w, h), Image.LANCZOS)
                    for fmt in FORMATS:
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
            if not fix.get("why") or len(fix.get("box", [])) != 4:
                errors.append(f"{pid}: each retouch needs a box and a reason")
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
