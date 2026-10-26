#!/usr/bin/env python3
"""WEB-DESIGN-RSI-2.0: measure a website's design, score a review, gate a promotion, and keep
several designs of the same site honest and distinct.

A web counterpart to PDF-BRIEF-DESIGN-RSI-1.0 in the EMBLEM RSI test suite. Same loop: build a
candidate, measure it, fix measured failures, review it with evidence, evaluate, then compare
against the incumbent. Promotion needs a passing measured layer, complete review evidence, every
score gate, a minimum gain and no dimension regressing beyond the allowed amount. Scores are
reviewer observations, not visitor-behaviour measurements. A producer review guides iteration;
release needs an independent reviewer and an approved contract.

2.0 adds, for contracts that ask for them (1.0 contracts and runs keep working unchanged):
  imagery       every photo shown is in the design's licence manifest, under an allowed licence,
                served as AVIF/WebP with a JPEG fallback, sharp but not oversized, within a byte
                budget, lazy below the fold and prioritised when it is the hero; the imagery audit
                (rsi/imagery.py) passes and the build carries the current manifest
  logos         required logos are visible on each page, unaltered (file hashes), big enough, on a
                clean white plate, never on a photo of someone who can be recognised; the home page
                shows the composite photo that carries them
  distinctness  the design's first screens, palette and headline typeface differ enough from the
                other designs of the same site (sibling runs)
  accuracy      the review's accuracy questions come from the contract

  measure   Serve the built site locally, run Lighthouse (mobile) and Playwright checks at three
            viewports, scroll each page so lazy images load, save hashed screenshots as evidence.
  template  Write an unreviewed review skeleton bound to a measured run's evidence.
  evaluate  Score a completed review against its measured run.
  compare   Promotion gate: incumbent (measured+review) versus candidate (measured+review).
  distinct  How different two measured runs look (first screens, palette, typefaces).

Exit: 0 pass/promoted, 3 completed but gates not passing, 2 blocked.
Needs: Python 3.10+, Playwright for Python with Chromium, Node with Lighthouse; for 2.0 imagery
also Pillow, numpy and OpenCV (rsi/imagery.py).
"""
from __future__ import annotations

import argparse
import functools
import hashlib
import http.server
import io
import json
import math
import os
import re
import shutil
import socketserver
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

SERIES_V1 = "WEB-DESIGN-RSI-1.0"
SERIES = "WEB-DESIGN-RSI-2.0"
CONTRACT_SCHEMAS = {SERIES_V1: "web.design.contract.v1", SERIES: "web.design.contract.v2"}
MEASURED_SCHEMAS = {SERIES_V1: "web.design.measured.v1", SERIES: "web.design.measured.v2"}
SCHEMA_VERSION = "2.0.0"
REPO = Path(__file__).resolve().parent.parent
PAGE_ROLE_DIMENSIONS = ("purpose_clarity", "hierarchy", "consistency", "legibility", "information_gain")
ACCURACY_GATES = ("content_matches_sources", "no_fabricated_offers_or_reviews", "unverified_flagged_for_owner")
IMAGERY_DIMENSIONS = ("imagery_quality", "logo_integration")


class DesignError(Exception):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_tree(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(x for x in root.rglob("*") if x.is_file()):
        h.update(str(p.relative_to(root)).encode())
        h.update(b"\0")
        h.update(sha256_file(p).encode())
    return h.hexdigest()


def _load(path: Path) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise DesignError(f"Cannot read {path}: {exc}")


def _repo_path(value: str) -> Path:
    p = Path(value)
    return p if p.is_absolute() else REPO / p


def accuracy_gates(contract: dict) -> tuple:
    return tuple(contract.get("accuracy_gates") or ACCURACY_GATES)


def validate_contract(c: dict) -> dict:
    series = c.get("measurement_series")
    if series not in CONTRACT_SCHEMAS or c.get("schema") != CONTRACT_SCHEMAS[series]:
        raise DesignError("Not a WEB-DESIGN-RSI-1.0 or 2.0 contract")
    w = c.get("weights") or {}
    if not w or abs(sum(float(v) for v in w.values()) - 100) > 1e-6:
        raise DesignError("Contract weights must sum to 100")
    for d in c.get("critical_dimensions", []):
        if d not in w:
            raise DesignError(f"Critical dimension {d} has no weight")
    if not c.get("pages"):
        raise DesignError("Contract lists no pages")
    if series == SERIES_V1 and any(k in c for k in ("imagery", "logos", "distinctness", "accuracy_gates")):
        raise DesignError("imagery, logos, distinctness and accuracy_gates need a 2.0 contract")
    gates = c.get("accuracy_gates")
    if gates is not None and (not isinstance(gates, list) or not gates or not all(isinstance(g, str) for g in gates)):
        raise DesignError("accuracy_gates must be a non-empty list of names")
    for key in ("imagery", "logos", "distinctness"):
        if key in c and not isinstance(c[key], dict):
            raise DesignError(f"{key} must be an object")
    return c


# ---------------------------------------------------------------- measuring

class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def _serve(root: Path):
    handler = functools.partial(_Quiet, directory=str(root))
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


def _lighthouse(url: str, lighthouse: str, chrome: str | None) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "lh.json"
        env = dict(os.environ)
        if chrome:
            env["CHROME_PATH"] = chrome
        cmd = [lighthouse, url, "--output=json", f"--output-path={out}", "--quiet",
               "--only-categories=performance,accessibility,best-practices,seo",
               "--chrome-flags=--headless=new --no-sandbox --disable-dev-shm-usage"]
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=300)
        if proc.returncode != 0 or not out.exists():
            raise DesignError(f"Lighthouse failed on {url}: {proc.stderr[-400:]}")
        r = json.loads(out.read_text())
    a = r["audits"]
    items = a.get("network-requests", {}).get("details", {}).get("items", [])
    origin = url.split("/")[2]
    hosts = sorted({i["url"].split("/")[2] for i in items if "://" in i.get("url", "")} - {origin})
    return {
        "scores": {k: round(v["score"] * 100) for k, v in r["categories"].items()},
        "lcp_ms": round(a["largest-contentful-paint"]["numericValue"]),
        "cls": round(a["cumulative-layout-shift"]["numericValue"], 4),
        "tbt_ms": round(a["total-blocking-time"]["numericValue"]),
        "requests": len(items),
        "transfer_kib": round(sum(i.get("transferSize", 0) for i in items) / 1024),
        "outside_domains": hosts,
        "lighthouse_version": r.get("lighthouseVersion"),
    }


_PAGE_PROBE = """() => {
  const vis = el => { const s = getComputedStyle(el); const r = el.getBoundingClientRect();
    return s.visibility !== 'hidden' && s.display !== 'none' && r.width > 0 && r.height > 0; };
  const sizes = new Set(); let minPx = 1e9;
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const t = walker.currentNode; const el = t.parentElement;
    if (!el || !t.textContent.trim() || !vis(el) || el.closest('svg,.visually-hidden,.sprite')) continue;
    const px = parseFloat(getComputedStyle(el).fontSize); sizes.add(Math.round(px)); minPx = Math.min(minPx, px);
  }
  const h = [...document.querySelectorAll('h1,h2,h3,h4,h5,h6')].map(x => Number(x.tagName[1]));
  let skipped = 0; for (let i = 1; i < h.length; i++) if (h[i] - h[i - 1] > 1) skipped++;
  const h1 = document.querySelector('h1');
  const bodyPx = parseFloat(getComputedStyle(document.body).fontSize);
  return {
    overflow_px: document.documentElement.scrollWidth - window.innerWidth,
    h1_count: document.querySelectorAll('h1').length,
    heading_skips: skipped,
    type_sizes: [...sizes].sort((a, b) => a - b),
    min_text_px: minPx === 1e9 ? null : Math.round(minPx * 10) / 10,
    hero_ratio: h1 ? Math.round(parseFloat(getComputedStyle(h1).fontSize) / bodyPx * 100) / 100 : null,
    imgs_without_alt: [...document.images].filter(i => !i.hasAttribute('alt')).length,
    text: document.body.innerText,
    height: document.documentElement.scrollHeight,
  };
}"""

_SCROLL = """async () => {
  for (let y = 0; y < document.documentElement.scrollHeight; y += Math.max(300, innerHeight * 0.6)) {
    window.scrollTo(0, y); await new Promise(r => setTimeout(r, 120));
  }
  const pending = [...document.images].filter(i => !i.complete);
  await Promise.race([
    Promise.all(pending.map(i => new Promise(r => { i.addEventListener('load', r, {once: true}); i.addEventListener('error', r, {once: true}); }))),
    new Promise(r => setTimeout(r, 8000)),
  ]);
  window.scrollTo(0, 0); await new Promise(r => setTimeout(r, 150));
}"""

# Every image with where it sits, how it is served and, for logos, what is behind it.
_IMAGE_PROBE = """() => {
  const sizes = {};
  for (const e of performance.getEntriesByType('resource')) sizes[e.name] = e.encodedBodySize || e.transferSize || 0;
  const box = el => { const r = el.getBoundingClientRect(); return {x: r.left + scrollX, y: r.top + scrollY, w: r.width, h: r.height}; };
  const shown = el => { const s = getComputedStyle(el); const r = el.getBoundingClientRect();
    return s.visibility !== 'hidden' && s.display !== 'none' && s.opacity !== '0' && r.width > 0 && r.height > 0; };
  const behind = el => {
    for (let n = el.parentElement; n; n = n.parentElement) {
      const c = getComputedStyle(n).backgroundColor.match(/[\\d.]+/g);
      if (c && (c.length < 4 || Number(c[3]) > 0.9)) return c.slice(0, 3).map(Number);
    }
    return [255, 255, 255];
  };
  return {
    dpr: window.devicePixelRatio, vh: innerHeight, vw: innerWidth,
    images: [...document.images].map(img => {
      const pic = img.parentElement && img.parentElement.tagName === 'PICTURE' ? img.parentElement : null;
      const cs = getComputedStyle(img);
      return {
        src: img.currentSrc || img.src, fallback: img.getAttribute('src'), nw: img.naturalWidth, nh: img.naturalHeight,
        box: box(img), shown: shown(img), loading: img.getAttribute('loading'), fetchpriority: img.getAttribute('fetchpriority'),
        alt: img.getAttribute('alt'), has_wh: img.hasAttribute('width') && img.hasAttribute('height'),
        srcset: (img.getAttribute('srcset') || '').split(',').filter(s => s.trim()).length,
        sources: pic ? [...pic.querySelectorAll('source')].map(s => ({type: s.type, n: (s.getAttribute('srcset') || '').split(',').filter(x => x.trim()).length})) : [],
        fit: cs.objectFit, behind: behind(img), bytes: sizes[img.currentSrc || img.src] || null,
      };
    }),
  };
}"""

_SIGNATURE_PROBE = """() => {
  const fam = el => el ? getComputedStyle(el).fontFamily.split(',')[0].replace(/["']/g, '').trim() : null;
  return { h1: fam(document.querySelector('h1')), body: fam(document.body) };
}"""


def _logo_id(path: str) -> str | None:
    m = re.search(r"/assets/img/brands/([a-z0-9-]+)\.(?:svg|png|webp)$", path)
    if m:
        return m.group(1)
    return "t-wireless" if re.search(r"/assets/img/t-wireless-logo-\d+\.(?:png|webp)$", path) else None


def _manifest_index(manifest: dict) -> dict:
    """File name -> (photo id, entry) for every rendered photo and card."""
    idx = {}
    for pid, e in manifest.get("photos", {}).items():
        for crop in e["crops"].values():
            for files in crop["files"].values():
                for f in files:
                    idx[f["file"]] = (pid, e)
    for cid, e in manifest.get("cards", {}).items():
        for files in e["files"].values():
            for f in files:
                idx[f["file"]] = (cid, e)
    return idx


@functools.lru_cache(maxsize=256)
def _file_size_px(path: str) -> tuple | None:
    """Pixel width and height of an image file (SVG: its width/height or viewBox)."""
    p = Path(path)
    if not p.is_file():
        return None
    if p.suffix == ".svg":
        head = p.read_text(encoding="utf-8", errors="ignore")[:2000]
        vb = re.search(r'viewBox="[\d.\s-]*?([\d.]+)\s+([\d.]+)"', head)
        if vb:
            return float(vb.group(1)), float(vb.group(2))
        w, h = re.search(r'width="([\d.]+)', head), re.search(r'height="([\d.]+)', head)
        return (float(w.group(1)), float(h.group(1))) if w and h else None
    from PIL import Image
    with Image.open(p) as im:
        return im.size


def _imagery_checks(page_file: str, role: str, probe: dict, contract: dict, manifest: dict, add, site: Path) -> dict:
    """Photos and logos on one page (phone viewport). Returns a summary for measured.json."""
    im_cfg, logo_cfg = contract.get("imagery") or {}, contract.get("logos") or {}
    idx = _manifest_index(manifest)
    files = {}
    for e in list(manifest.get("photos", {}).values()):
        for crop in e["crops"].values():
            for fs in crop["files"].values():
                for f in fs:
                    files[f["file"]] = (f["w"], f["h"])
    for img in probe["images"]:
        name = unquote(urlparse(img["src"]).path).rsplit("/", 1)[-1]
        size = files.get(name) or _file_size_px(str(site / unquote(urlparse(img["src"]).path).lstrip("/")))
        if size and img["nw"]:  # loaded: use the file's real pixels
            img["nw"], img["nh"] = size
    dpr, vh = probe["dpr"], probe["vh"]
    photos, logos, unknown = [], [], []
    for img in probe["images"]:
        path = unquote(urlparse(img["src"]).path)
        if "/assets/img/photos/" in path:
            name = path.rsplit("/", 1)[-1]
            hit = idx.get(name)
            img["photo_id"], img["entry"] = (hit if hit else (None, None))
            if not hit:
                unknown.append(name)
            photos.append(img)
        elif _logo_id(path):
            img["logo_id"] = _logo_id(path)
            logos.append(img)
    shown = [p for p in photos if p["shown"]]
    summary = {"photos": sorted({p["photo_id"] for p in shown if p["photo_id"]}), "photo_count": len(shown),
               "logos": sorted({lg["logo_id"] for lg in logos if lg["shown"]}), "unknown_photo_files": unknown}
    if im_cfg:
        allowed = set(im_cfg.get("allowed_licenses", []))
        need = im_cfg.get("min_photos", {}).get(role, 0)
        add("photos_min", page_file, "phone", len(summary["photos"]) >= need, len(summary["photos"]), need)
        add("photo_in_manifest", page_file, "phone", not unknown, unknown, "every photo listed in photos.json")
        bad_licence = sorted({p["photo_id"] for p in photos if p["entry"] and p["entry"].get("source", {}).get("license") not in allowed
                              and p["entry"].get("kind") != "card"})
        add("photo_licence_allowed", page_file, "phone", not bad_licence, bad_licence, sorted(allowed))
        formats = tuple(im_cfg.get("formats", ["avif", "webp"]))
        fallback = im_cfg.get("fallback", "jpg")
        modern = [p["src"].rsplit("/", 1)[-1] for p in shown if not p["src"].lower().endswith(tuple("." + f for f in formats))]
        add("photo_modern_format", page_file, "phone", not modern, modern, list(formats))
        no_fb = [p["fallback"] for p in photos if not str(p["fallback"]).lower().endswith("." + fallback)
                 or {s["type"] for s in p["sources"]} < {f"image/{f}" for f in formats}]
        add("photo_fallback", page_file, "phone", not no_fb, no_fb, f"{fallback} fallback plus {', '.join(formats)} sources")
        thin = [p["fallback"] for p in photos if p["srcset"] < im_cfg.get("min_srcset", 2)
                or any(s["n"] < im_cfg.get("min_srcset", 2) for s in p["sources"])]
        add("photo_responsive", page_file, "phone", not thin, thin, f">= {im_cfg.get('min_srcset', 2)} widths per format")
        no_wh = [p["fallback"] for p in photos if not p["has_wh"]]
        add("photo_dimensions", page_file, "phone", not no_wh, no_wh, "width and height attributes")
        blurry, heavy_px = [], []
        for p in shown:
            need_px = p["box"]["w"] * dpr
            if p["fit"] == "cover" and p["nw"] and p["nh"] and p["box"]["h"]:
                # a cover crop needs enough pixels along whichever side it fills
                need_px = max(need_px, p["box"]["h"] * dpr * p["nw"] / p["nh"])
            if p["nw"] < im_cfg.get("min_sharpness", 0.85) * need_px:
                blurry.append(f'{p["src"].rsplit("/", 1)[-1]} {p["nw"]}px for {round(need_px)}px')
            if p["nw"] > im_cfg.get("max_oversize", 2.2) * need_px:
                heavy_px.append(f'{p["src"].rsplit("/", 1)[-1]} {p["nw"]}px for {round(need_px)}px')
        add("photo_sharpness", page_file, "phone", not blurry, blurry, f">= {im_cfg.get('min_sharpness', 0.85)} x shown size")
        add("photo_not_oversized", page_file, "phone", not heavy_px, heavy_px, f"<= {im_cfg.get('max_oversize', 2.2)} x shown size")
        max_kib = im_cfg.get("max_photo_kib", 200)
        big = [f'{p["src"].rsplit("/", 1)[-1]} {round(p["bytes"] / 1024)} KiB' for p in shown if p["bytes"] and p["bytes"] > max_kib * 1024]
        add("photo_bytes", page_file, "phone", not big, big, f"<= {max_kib} KiB each")
        total = round(sum(p["bytes"] or 0 for p in shown) / 1024)
        add("page_photo_kib", page_file, "phone", total <= im_cfg.get("max_page_image_kib", 900), total, im_cfg.get("max_page_image_kib", 900))
        summary["photo_kib"] = total
        eager_low = [p["fallback"] for p in photos if p["box"]["y"] >= vh and p["loading"] != "lazy"]
        add("lazy_below_fold", page_file, "phone", not eager_low, eager_low, "photos below the first screen load lazily")
        above = [p for p in shown if p["box"]["y"] < vh]
        if above:
            def seen_area(p):
                return p["box"]["w"] * max(0, min(p["box"]["h"], vh - p["box"]["y"]))
            lead = max(above, key=seen_area)
            if seen_area(lead) >= 0.15 * probe["vw"] * vh:
                add("lead_photo_priority", page_file, "phone", lead["fetchpriority"] == "high" and lead["loading"] != "lazy",
                    {"photo": lead["src"].rsplit("/", 1)[-1], "fetchpriority": lead["fetchpriority"], "loading": lead["loading"]},
                    "the biggest photo on the first screen loads eagerly with fetchpriority=high")
        no_alt = [p["fallback"] for p in photos if p["alt"] is None]
        add("photo_alt", page_file, "phone", not no_alt, no_alt, "alt attribute on every photo")
    if logo_cfg:
        need = set(logo_cfg.get("required", {}).get(role, []))
        seen = {lg["logo_id"] for lg in logos if lg["shown"]}
        add("logos_required", page_file, "phone", need <= seen, sorted(seen), sorted(need))
        small, dirty, warped, on_people = [], [], [], []
        safe = set((contract.get("imagery") or {}).get("logo_safe_people", ["none", "no faces"]))
        for lg in (x for x in logos if x["shown"]):
            bw, bh = lg["box"]["w"], lg["box"]["h"]
            na = lg["nw"] / lg["nh"] if lg["nw"] and lg["nh"] else bw / bh
            if lg["fit"] in ("contain", "scale-down"):
                dw, dh = (bh * na, bh) if bw / bh > na else (bw, bw / na)
            else:
                dw, dh = bw, bh
                if abs((bw / bh) / na - 1) > 0.02:
                    warped.append(f'{lg["logo_id"]} drawn {round(bw)}x{round(bh)}')
            if dh < logo_cfg.get("min_px", 16):
                small.append(f'{lg["logo_id"]} {round(dh)}px tall')
            if lg["logo_id"] != "t-wireless" and min(lg["behind"]) < logo_cfg.get("plate_min_rgb", 245):
                dirty.append(f'{lg["logo_id"]} on rgb{tuple(lg["behind"])}')
            cx, cy = lg["box"]["x"] + bw / 2, lg["box"]["y"] + bh / 2
            for p in shown:
                b = p["box"]
                if b["x"] <= cx <= b["x"] + b["w"] and b["y"] <= cy <= b["y"] + b["h"]:
                    people = (p["entry"] or {}).get("people")
                    if p["entry"] and p["entry"].get("kind") != "card" and people not in safe:
                        on_people.append(f'{lg["logo_id"]} on {p["photo_id"]} ({people})')
        add("logo_min_size", page_file, "phone", not small, small, f">= {logo_cfg.get('min_px', 16)}px drawn height")
        add("logo_clean_plate", page_file, "phone", not dirty, dirty, f"white plate (rgb >= {logo_cfg.get('plate_min_rgb', 245)})")
        add("logo_not_distorted", page_file, "phone", not warped, warped, "original proportions")
        add("logo_not_on_identifiable_people", page_file, "phone", not on_people, on_people, "logos only on photos where nobody can be recognised")
        want = set(logo_cfg.get("composite_required", {}).get(role, []))
        if want:
            found = [p["photo_id"] for p in shown if p["entry"] and p["entry"].get("kind") == "composite"
                     and want <= set(p["entry"].get("logos", []))]
            add("logo_composite", page_file, "phone", bool(found), found, f"a composite photo carrying {sorted(want)}")
    return summary


def _palette(png: Path, colors: int = 6) -> list:
    from PIL import Image
    im = Image.open(png).convert("RGB")
    im.thumbnail((160, 160))
    q = im.quantize(colors=colors, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()[: colors * 3]
    counts = sorted(q.getcolors(), reverse=True)
    total = sum(c for c, _ in counts)
    return [[*pal[i * 3:i * 3 + 3], round(c / total, 4)] for c, i in counts]


def _lab(rgb):
    def lin(c):
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(float(v)) for v in rgb)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883
    f = [t ** (1 / 3) if t > 216 / 24389 else (24389 / 27 * t + 16) / 116 for t in (x, y, z)]
    return 116 * f[1] - 16, 500 * (f[0] - f[1]), 200 * (f[1] - f[2])


def palette_distance(a: list, b: list) -> float:
    """Average colour distance (CIE76) between two weighted palettes, both ways."""
    la = [(_lab(c[:3]), c[3]) for c in a]
    lb = [(_lab(c[:3]), c[3]) for c in b]

    def one_way(x, y):
        return sum(w * min(math.dist(p, q) for q, _ in y) for p, w in x) / sum(w for _, w in x)
    return round((one_way(la, lb) + one_way(lb, la)) / 2, 2)


def visual_similarity(a: Path, b: Path, width: int = 96) -> float:
    """Structural similarity (SSIM, 7x7 windows) of two first-screen screenshots, scaled to the same size."""
    import numpy as np
    from PIL import Image
    ia, ib = Image.open(a).convert("L"), Image.open(b).convert("L")
    h = round(width * ia.height / ia.width)
    x = np.asarray(ia.resize((width, h), Image.LANCZOS), dtype=np.float64)
    y = np.asarray(ib.resize((width, h), Image.LANCZOS), dtype=np.float64)

    def box(m, k=7):
        p = np.pad(m, ((k // 2 + 1, k // 2), (k // 2 + 1, k // 2)), mode="edge").cumsum(0).cumsum(1)
        return (p[k:, k:] - p[:-k, k:] - p[k:, :-k] + p[:-k, :-k]) / (k * k)
    mx, my = box(x), box(y)
    vx, vy, cxy = box(x * x) - mx ** 2, box(y * y) - my ** 2, box(x * y) - mx * my
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    s = ((2 * mx * my + c1) * (2 * cxy + c2)) / ((mx ** 2 + my ** 2 + c1) * (vx + vy + c2))
    return round(float(s.mean()), 4)


def capture_signature(site: Path, out_dir: Path, chrome: str | None, prefix: str = "signature") -> dict:
    """First screens of the home page (phone and desktop), their palettes, and the typefaces in use."""
    from playwright.sync_api import sync_playwright
    out_dir.mkdir(parents=True, exist_ok=True)
    httpd, base = _serve(site)
    sig = {"shots": {}, "palette": {}, "fonts": {}}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"], executable_path=chrome or None)
            for vp, (w, h, scale, mobile) in {"phone": (390, 844, 2, True), "desktop": (1440, 900, 1, False)}.items():
                ctx = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=scale, is_mobile=mobile,
                                          has_touch=mobile, locale="en-CA", timezone_id="America/Toronto")
                pg = ctx.new_page()
                pg.goto(f"{base}/index.html", wait_until="networkidle")
                pg.wait_for_timeout(1500)
                pg.add_style_tag(content=".demo-banner{display:none!important}")
                shot = out_dir / f"{prefix}-home-{vp}.png"
                pg.screenshot(path=str(shot))
                sig["shots"][vp] = shot.name
                sig["palette"][vp] = _palette(shot)
                if vp == "desktop":
                    sig["fonts"] = pg.evaluate(_SIGNATURE_PROBE)
                ctx.close()
            browser.close()
    finally:
        httpd.shutdown()
    return sig


def compare_signatures(a: dict, a_dir: Path, b: dict, b_dir: Path) -> dict:
    sims = {vp: visual_similarity(a_dir / a["shots"][vp], b_dir / b["shots"][vp]) for vp in ("phone", "desktop")}
    dists = {vp: palette_distance(a["palette"][vp], b["palette"][vp]) for vp in ("phone", "desktop")}
    return {"visual_similarity": round(sum(sims.values()) / 2, 4), "visual_similarity_by_viewport": sims,
            "palette_distance": round(sum(dists.values()) / 2, 2), "palette_distance_by_viewport": dists,
            "headline_fonts": [a["fonts"].get("h1"), b["fonts"].get("h1")],
            "body_fonts": [a["fonts"].get("body"), b["fonts"].get("body")],
            "same_headline_font": a["fonts"].get("h1") == b["fonts"].get("h1"),
            "same_body_font": a["fonts"].get("body") == b["fonts"].get("body")}


def _run_site(run_dir: Path) -> Path:
    m = _load(run_dir / "measured.json")
    site = Path(m.get("site", "site"))
    return site if site.is_absolute() else run_dir / site


def measure(site: Path, contract_path: Path, out_dir: Path, lighthouse: str, chrome: str | None) -> dict:
    from playwright.sync_api import sync_playwright

    contract = validate_contract(_load(contract_path))
    series = contract["measurement_series"]
    v2 = series == SERIES
    cfg = contract["measure"]
    site = Path(site).resolve()
    if not site.is_dir():
        raise DesignError(f"Site folder not found: {site}")
    out_dir = Path(out_dir)
    if out_dir.exists() and any(out_dir.iterdir()):
        raise DesignError(f"Refusing to overwrite {out_dir}")
    (out_dir / "evidence").mkdir(parents=True, exist_ok=True)

    checks, evidence, pages = [], [], {}

    def add(cid, page, viewport, ok, measured, threshold):
        checks.append({"id": cid, "page": page, "viewport": viewport, "pass": bool(ok),
                       "measured": measured, "threshold": threshold})

    def keep(path: Path, page, role, viewport):
        evidence.append({"page": page, "role": role, "viewport": viewport,
                         "path": f"evidence/{path.name}", "sha256": sha256_file(path)})

    manifest, imagery_summary = {}, {}
    if v2 and contract.get("imagery"):
        mpath = site / contract["imagery"].get("manifest", "assets/img/photos/photos.json")
        if not mpath.is_file():
            raise DesignError(f"Photo manifest not found in the build: {mpath}")
        manifest = _load(mpath)
    hide = ",".join(cfg.get("hide_in_screenshots", [".actionbar"]))
    present_roles = []
    httpd, base = _serve(site)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"],
                                        executable_path=chrome or None)
            for page_file, role in contract["pages"].items():
                exists = (site / page_file).is_file()
                add("page_present", page_file, None, exists, exists, True)
                if not exists:
                    continue
                present_roles.append(role)
                url = f"{base}/{page_file}"
                lh = _lighthouse(url, lighthouse, chrome)
                page_rec = {"role": role, "lighthouse": lh, "viewports": {}}
                for cat, minimum in cfg["lighthouse_min"].items():
                    add(f"lighthouse_{cat}", page_file, "lighthouse_mobile", lh["scores"].get(cat, 0) >= minimum,
                        lh["scores"].get(cat), minimum)
                add("cls", page_file, "lighthouse_mobile", lh["cls"] <= cfg["max_cls"], lh["cls"], cfg["max_cls"])
                add("lcp", page_file, "lighthouse_mobile", lh["lcp_ms"] <= cfg["max_lcp_ms"], lh["lcp_ms"], cfg["max_lcp_ms"])
                add("transfer", page_file, "lighthouse_mobile", lh["transfer_kib"] <= cfg["max_transfer_kib"],
                    lh["transfer_kib"], cfg["max_transfer_kib"])
                add("outside_domains", page_file, "lighthouse_mobile",
                    len(lh["outside_domains"]) <= cfg["max_outside_domains"], lh["outside_domains"], cfg["max_outside_domains"])
                for vp, (w, h) in cfg["viewports"].items():
                    phone = vp != "desktop"
                    ctx = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=2 if phone else 1,
                                              is_mobile=phone, has_touch=phone, locale="en-CA",
                                              timezone_id="America/Toronto")
                    pg = ctx.new_page()
                    pg.goto(url, wait_until="networkidle")
                    pg.wait_for_timeout(2500)
                    if v2 and vp == "phone":
                        shot = out_dir / "evidence" / f"{page_file.replace('.html', '')}-phone-top.png"
                        pg.screenshot(path=str(shot))  # the first screen as a visitor sees it
                        keep(shot, page_file, role, "phone_top")
                    pg.evaluate(_SCROLL)  # load lazy images before probing and full-page screenshots
                    pg.wait_for_load_state("networkidle")
                    probe = pg.evaluate(_PAGE_PROBE)
                    text = probe.pop("text")
                    page_rec["viewports"][vp] = probe
                    add("no_horizontal_overflow", page_file, vp, probe["overflow_px"] <= 0, probe["overflow_px"], 0)
                    if vp == "phone":
                        add("h1_exactly", page_file, vp, probe["h1_count"] == cfg["h1_exactly"], probe["h1_count"], cfg["h1_exactly"])
                        add("heading_order", page_file, vp, probe["heading_skips"] == 0, probe["heading_skips"], 0)
                        add("type_scale_discipline", page_file, vp, len(probe["type_sizes"]) <= cfg["max_type_sizes"],
                            len(probe["type_sizes"]), cfg["max_type_sizes"])
                        add("min_text_size", page_file, vp, (probe["min_text_px"] or 0) >= cfg["min_text_px"],
                            probe["min_text_px"], cfg["min_text_px"])
                        add("hero_hierarchy_ratio", page_file, vp, (probe["hero_ratio"] or 0) >= cfg["min_hero_hierarchy_ratio"],
                            probe["hero_ratio"], cfg["min_hero_hierarchy_ratio"])
                        add("image_alt", page_file, vp, probe["imgs_without_alt"] == 0, probe["imgs_without_alt"], 0)
                        for rx in cfg["required_text"].get(role, []):
                            add("required_text", page_file, vp, re.search(rx, text) is not None, rx, "present")
                        if v2 and (contract.get("imagery") or contract.get("logos")):
                            imagery_summary[page_file] = _imagery_checks(page_file, role, pg.evaluate(_IMAGE_PROBE),
                                                                         contract, manifest, add, site)
                    if vp in ("phone", "desktop"):
                        if phone and hide:
                            pg.add_style_tag(content=f"{hide}{{display:none!important}}")
                        shot = out_dir / "evidence" / f"{page_file.replace('.html', '')}-{vp}.png"
                        pg.screenshot(path=str(shot), full_page=True)
                        keep(shot, page_file, role, vp)
                    ctx.close()
                pages[page_file] = page_rec
            browser.close()
    finally:
        httpd.shutdown()

    extra = {}
    if v2 and contract.get("imagery", {}).get("sources"):
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import imagery  # the imagery layer that sits beside this file
        src_path = _repo_path(contract["imagery"]["sources"])
        design_dir = src_path.parent.parent
        result = imagery.audit(design_dir)
        add("imagery_audit", None, None, result["pass"], result["errors"], "licences, hosts, credits, hashes, faces")
        built = site / contract["imagery"].get("manifest", "assets/img/photos/photos.json")
        current = design_dir / "assets" / "img" / "photos" / "photos.json"
        add("manifest_current", None, None, current.is_file() and sha256_file(built) == sha256_file(current),
            "build carries the design's current photos.json", "same file")
        shutil.copy(src_path, out_dir / "imagery-sources.json")
        sheet = imagery.sheet(design_dir, out_dir / "evidence" / "imagery-sheet.png")
        keep(sheet, None, None, "imagery_sheet")
        extra["imagery_audit"] = {k: result[k] for k in ("pass", "errors", "warnings", "photos", "cards", "files", "bytes")}
        extra["imagery_sources_sha256"] = sha256_file(out_dir / "imagery-sources.json")
    if v2 and contract.get("logos", {}).get("files"):
        changed = [f for f, digest in contract["logos"]["files"].items()
                   if not (site / f).is_file() or sha256_file(site / f) != digest]
        add("logo_files_unaltered", None, None, not changed, changed, "approved logo files, byte for byte")
    if v2:
        sig = capture_signature(site, out_dir / "evidence", chrome)
        for vp, name in sig["shots"].items():
            keep(out_dir / "evidence" / name, "index.html", "home", f"signature_{vp}")
        extra["signature"] = sig
        dcfg = contract.get("distinctness") or {}
        extra["distinctness"] = {}
        for sib in dcfg.get("siblings", []):
            sib_dir = _repo_path(sib["run"])
            with tempfile.TemporaryDirectory() as tmp:
                sib_sig = capture_signature(_run_site(sib_dir), Path(tmp), chrome, prefix=sib["design_id"])
                cmp = compare_signatures(sig, out_dir / "evidence", sib_sig, Path(tmp))
            cmp["run"] = sib["run"]
            extra["distinctness"][sib["design_id"]] = cmp
            add("distinct_visual", None, sib["design_id"], cmp["visual_similarity"] <= dcfg.get("max_visual_similarity", 0.55),
                cmp["visual_similarity"], f"<= {dcfg.get('max_visual_similarity', 0.55)}")
            add("distinct_palette", None, sib["design_id"], cmp["palette_distance"] >= dcfg.get("min_palette_distance", 12),
                cmp["palette_distance"], f">= {dcfg.get('min_palette_distance', 12)}")
            if dcfg.get("require_different_headline_font", True):
                add("distinct_headline_font", None, sib["design_id"], not cmp["same_headline_font"],
                    cmp["headline_fonts"], "different headline typeface")

    blockers = [f"missing required page role: {r}" for r in contract.get("required_page_roles", [])
                if r not in present_roles]
    failed = [c for c in checks if not c["pass"]]
    # Keep a copy of the measured build inside the run so evaluate can re-hash it anywhere.
    shutil.copytree(site, out_dir / "site")
    data = {
        "schema": MEASURED_SCHEMAS[series], "schema_version": SCHEMA_VERSION, "measurement_series": series,
        "target_id": contract["target_id"], "design_id": contract.get("design_id"),
        "site": "site", "site_source": str(site), "site_sha256": sha256_tree(site),
        "page_roles": {k: v for k, v in contract["pages"].items() if (site / k).is_file()},
        "checks_total": len(checks), "checks_failed": len(failed), "failed_checks": failed,
        "declaration_blockers": blockers, "measured_pass": not failed and not blockers,
        "pages": pages, "imagery": imagery_summary, **extra, "evidence": evidence, "checks": checks,
    }
    (out_dir / "measured.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return data


# ---------------------------------------------------------------- reviewing

def review_template(measured: dict, contract: dict, reviewer_id: str, role: str) -> dict:
    ev = measured["evidence"]

    def for_page(page):
        return [{"path": e["path"], "sha256": e["sha256"]} for e in ev if e["page"] == page]
    home = next((p for p, r in measured["page_roles"].items() if r == "home"), None)
    sheet = [{"path": e["path"], "sha256": e["sha256"]} for e in ev if e["viewport"] == "imagery_sheet"]

    def dim_evidence(d):
        base = for_page(home) if home else []
        return base + sheet if d in IMAGERY_DIMENSIONS else base
    return {
        "schema": "web.design.review.v1", "measurement_series": contract["measurement_series"], "target_id": measured["target_id"],
        "candidate_sha256": measured["site_sha256"], "reviewer_id": reviewer_id, "reviewer_role": role,
        "ratings": {d: {"score": None, "status": "unreviewed", "rationale": "", "evidence": dim_evidence(d)}
                    for d in contract["weights"]},
        "page_roles": [{"id": f"role-{r}", "role": r, "page": p,
                        "ratings": {d: None for d in PAGE_ROLE_DIMENSIONS}, "evidence": for_page(p)}
                       for p, r in measured["page_roles"].items()],
        "accuracy_gate": {g: None for g in accuracy_gates(contract)},
        "notes": "Rate 0-5 per dimension with a rationale and the screenshots that support it.",
    }


def _score5(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 5:
        raise DesignError(f"{label}: score must be a number from 0 to 5")
    return float(value)


def _evidence_ok(items: Any, base: Path) -> tuple[bool, list[str]]:
    if not isinstance(items, list) or not items:
        return False, ["evidence missing"]
    errs = []
    for it in items:
        path = base / str((it or {}).get("path", ""))
        if not path.is_file():
            errs.append(f"evidence file missing: {it}")
        elif sha256_file(path) != (it or {}).get("sha256"):
            errs.append(f"evidence hash mismatch: {path.name}")
    return not errs, errs


def validate_review(review: dict, contract: dict, measured: dict, base: Path) -> list[str]:
    b = []
    if review.get("schema") != "web.design.review.v1": b.append("unsupported review schema")
    if review.get("target_id") != contract.get("target_id"): b.append("target_id mismatch")
    if review.get("candidate_sha256") != measured.get("site_sha256"): b.append("review is bound to a different site build")
    if not review.get("reviewer_id"): b.append("reviewer_id missing")
    if review.get("reviewer_role") not in {"producer_diagnostic", "independent_reviewer"}: b.append("invalid reviewer_role")
    ratings = review.get("ratings") or {}
    for d in contract["weights"]:
        r = ratings.get(d)
        if not isinstance(r, dict): b.append(f"{d}: missing review"); continue
        try: _score5(r.get("score"), d)
        except DesignError as exc: b.append(str(exc)); continue
        if r.get("status") != "reviewed": b.append(f"{d}: status must be reviewed")
        if not str(r.get("rationale", "")).strip(): b.append(f"{d}: rationale required")
        ok, errs = _evidence_ok(r.get("evidence"), base)
        if not ok: b.extend(f"{d}: {e}" for e in errs)
    for g in accuracy_gates(contract):
        if (review.get("accuracy_gate") or {}).get(g) is not True: b.append(f"accuracy gate failed/unknown: {g}")
    seen = []
    for i, e in enumerate(review.get("page_roles") or []):
        seen.append(e.get("role"))
        if measured["page_roles"].get(e.get("page")) != e.get("role"):
            b.append(f"page_roles[{i}] page/role does not match the measured run")
        for d in PAGE_ROLE_DIMENSIONS:
            try: _score5((e.get("ratings") or {}).get(d), f"page_roles[{i}].{d}")
            except DesignError as exc: b.append(str(exc))
        ok, errs = _evidence_ok(e.get("evidence"), base)
        if not ok: b.extend(f"page_roles[{i}]: {x}" for x in errs)
    for req in contract.get("required_page_roles", []):
        if req not in seen: b.append(f"missing required page-role review: {req}")
    return b


def evaluate(contract_path: Path, measured_path: Path, review_path: Path) -> dict:
    contract = validate_contract(_load(contract_path))
    series = contract["measurement_series"]
    measured = _load(measured_path)
    if (measured.get("schema") != MEASURED_SCHEMAS[series] or measured.get("target_id") != contract["target_id"]
            or measured.get("measurement_series", SERIES_V1) != series):
        raise DesignError("Not a measured run for this contract")
    site_blockers = []
    site = Path(measured.get("site", ""))
    if not site.is_absolute():
        site = Path(measured_path).parent / site  # runs carry their own copy of the measured build
    if not site.is_dir(): site_blockers.append("measured site no longer available")
    elif sha256_tree(site) != measured["site_sha256"]: site_blockers.append("site has changed since measurement")
    review = _load(review_path)
    blockers = site_blockers + validate_review(review, contract, measured, Path(review_path).parent)
    weights = contract["weights"]
    dim = {}
    for d in weights:
        r = (review.get("ratings") or {}).get(d)
        try: dim[d] = round(_score5(r.get("score"), d) * 20, 3) if isinstance(r, dict) else None
        except DesignError: dim[d] = None
    overall = round(sum(dim[d] * weights[d] / 100 for d in weights), 3) if all(v is not None for v in dim.values()) else None
    roles = []
    for e in review.get("page_roles") or []:
        try: vals = [_score5((e.get("ratings") or {}).get(d), d) * 20 for d in PAGE_ROLE_DIMENSIONS]
        except DesignError: vals = []
        roles.append({"role": e.get("role"), "page": e.get("page"), "score": round(sum(vals) / len(vals), 3) if vals else None})
    independent = review.get("reviewer_role") == "independent_reviewer" and review.get("reviewer_id") != contract["producer_id"]
    gates_list = accuracy_gates(contract)
    g = {
        "measured_layer": bool(measured.get("measured_pass")) and not site_blockers,
        "evidence_complete": not blockers,
        "overall": overall is not None and overall >= contract["min_overall_score"],
        "critical_dimensions": all(dim.get(d) is not None and dim[d] >= contract["min_dimension_score"]
                                   for d in contract["critical_dimensions"]),
        "page_roles": bool(roles) and all(x["score"] is not None and x["score"] >= contract["min_page_role_score"] for x in roles),
        "accuracy": all((review.get("accuracy_gate") or {}).get(k) is True for k in gates_list),
    }
    diagnostic_pass = all(g.values())
    release_blockers = []
    if not independent: release_blockers.append("Independent reviewer evidence not supplied.")
    if contract.get("approved_for_production") is not True: release_blockers.append("Design contract is not approved_for_production.")
    if not diagnostic_pass: release_blockers.append("Design diagnostic gates are not all passing.")
    weakest = min(((v, k) for k, v in dim.items() if v is not None), default=(None, None))
    return {
        "schema": "web.design.result.v1", "measurement_series": series, "target_id": contract["target_id"],
        "candidate_sha256": measured["site_sha256"], "reviewer_id": review.get("reviewer_id"),
        "reviewer_role": review.get("reviewer_role"), "independent_review": independent,
        "measured_checks_failed": measured.get("checks_failed"), "measured_failed_checks": measured.get("failed_checks"),
        "declaration_blockers": measured.get("declaration_blockers"),
        "dimension_scores": dim, "overall_score": overall, "page_role_scores": roles,
        "weakest_dimension": weakest[1], "weakest_dimension_score": weakest[0], "gates": g,
        "diagnostic_pass": diagnostic_pass,
        "release_eligible": bool(diagnostic_pass and independent and contract.get("approved_for_production") is True),
        "blockers": blockers, "release_blockers": release_blockers,
        "score_note": "Review-derived design score plus Lighthouse and Playwright measurements; not a visitor-behaviour measurement.",
    }


def compare(contract_path: Path, incumbent: tuple[Path, Path], candidate: tuple[Path, Path]) -> dict:
    contract = validate_contract(_load(contract_path))
    inc = evaluate(contract_path, *incumbent)
    cand = evaluate(contract_path, *candidate)
    if inc["candidate_sha256"] == cand["candidate_sha256"]:
        raise DesignError("Incumbent and candidate are the same build; a self-comparison is not a promotion")
    max_reg = float(contract["max_dimension_regression"])
    regressions = {d: round(inc["dimension_scores"][d] - cand["dimension_scores"][d], 3)
                   for d in contract["weights"]
                   if inc["dimension_scores"].get(d) is not None and cand["dimension_scores"].get(d) is not None
                   and inc["dimension_scores"][d] - cand["dimension_scores"][d] > max_reg}
    gain = None
    if inc["overall_score"] is not None and cand["overall_score"] is not None:
        gain = round(cand["overall_score"] - inc["overall_score"], 3)
    promoted = bool(cand["diagnostic_pass"] and gain is not None and gain >= contract["min_promotion_gain"] and not regressions)
    status = ("PROMOTED" if cand["release_eligible"] else "DIAGNOSTIC_PROMOTED_RELEASE_BLOCKED") if promoted else "NOT_PROMOTED"
    return {"schema": "web.design.promotion.v1", "measurement_series": contract["measurement_series"], "target_id": cand["target_id"],
            "incumbent_sha256": inc["candidate_sha256"], "candidate_sha256": cand["candidate_sha256"],
            "incumbent_score": inc["overall_score"], "candidate_score": cand["overall_score"], "gain": gain,
            "measured_failures_incumbent": inc["measured_checks_failed"],
            "measured_failures_candidate": cand["measured_checks_failed"],
            "dimension_regressions": regressions, "promoted": promoted, "status": status,
            "candidate_release_eligible": cand["release_eligible"],
            "candidate_release_blockers": cand["release_blockers"], "incumbent": inc, "candidate": cand}


def distinct(run_a: Path, run_b: Path, chrome: str | None) -> dict:
    """First screens, palettes and typefaces of two measured runs, side by side."""
    with tempfile.TemporaryDirectory() as tmp:
        ta, tb = Path(tmp) / "a", Path(tmp) / "b"
        sa = capture_signature(_run_site(Path(run_a)), ta, chrome, "a")
        sb = capture_signature(_run_site(Path(run_b)), tb, chrome, "b")
        result = compare_signatures(sa, ta, sb, tb)
    return {"schema": "web.design.distinct.v1", "measurement_series": SERIES, "a": str(run_a), "b": str(run_b), **result}


def _write(path: Path, data: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("measure")
    m.add_argument("--site", type=Path, required=True, help="Built site folder, for example dist/")
    m.add_argument("--contract", type=Path, required=True)
    m.add_argument("--out", type=Path, required=True, help="New folder for measured.json and evidence")
    m.add_argument("--lighthouse", default=os.environ.get("LIGHTHOUSE_BIN", "lighthouse"))
    m.add_argument("--chrome", default=os.environ.get("CHROME_PATH"))
    t = sub.add_parser("template")
    t.add_argument("--measured", type=Path, required=True)
    t.add_argument("--contract", type=Path, required=True)
    t.add_argument("--reviewer-id", default="")
    t.add_argument("--reviewer-role", default="producer_diagnostic", choices=["producer_diagnostic", "independent_reviewer"])
    t.add_argument("--out", type=Path, required=True)
    e = sub.add_parser("evaluate")
    e.add_argument("--contract", type=Path, required=True)
    e.add_argument("--measured", type=Path, required=True)
    e.add_argument("--review", type=Path, required=True)
    e.add_argument("--out", type=Path, required=True)
    c = sub.add_parser("compare")
    c.add_argument("--contract", type=Path, required=True)
    c.add_argument("--incumbent-measured", type=Path, required=True)
    c.add_argument("--incumbent-review", type=Path, required=True)
    c.add_argument("--measured", type=Path, required=True)
    c.add_argument("--review", type=Path, required=True)
    c.add_argument("--out", type=Path, required=True)
    d = sub.add_parser("distinct")
    d.add_argument("--run-a", type=Path, required=True, help="A measured run folder, for example rsi/runs/design-1/v6-candidate")
    d.add_argument("--run-b", type=Path, required=True)
    d.add_argument("--chrome", default=os.environ.get("CHROME_PATH"))
    d.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "measure":
            d = measure(a.site, a.contract, a.out, a.lighthouse, a.chrome)
            print(json.dumps({k: d[k] for k in ("target_id", "site_sha256", "checks_total", "checks_failed",
                                                "measured_pass", "declaration_blockers")}, indent=2))
            for f in d["failed_checks"]:
                print(f"  FAIL {f['id']} {f['page'] or ''} {f['viewport'] or ''}: measured {f['measured']}, needs {f['threshold']}")
            return 0 if d["measured_pass"] else 3
        if a.cmd == "template":
            if a.out.exists():
                raise DesignError(f"Refusing to overwrite {a.out}")
            contract = validate_contract(_load(a.contract))
            _write(a.out, review_template(_load(a.measured), contract, a.reviewer_id, a.reviewer_role))
            print(f"Wrote unreviewed template {a.out}")
            return 0
        if a.cmd == "distinct":
            d = distinct(a.run_a, a.run_b, a.chrome)
            if a.out:
                _write(a.out, d)
            print(json.dumps(d, indent=2))
            return 0
        if a.cmd == "evaluate":
            d = evaluate(a.contract, a.measured, a.review)
            ok = d["diagnostic_pass"]
        else:
            d = compare(a.contract, (a.incumbent_measured, a.incumbent_review), (a.measured, a.review))
            ok = d["promoted"]
        _write(a.out, d)
        print(json.dumps({k: v for k, v in d.items() if k not in ("incumbent", "candidate")}, indent=2))
        return 0 if ok else 3
    except DesignError as exc:
        print(json.dumps({"schema": "web.design.error.v1", "status": "BLOCKED", "error": str(exc)}, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
