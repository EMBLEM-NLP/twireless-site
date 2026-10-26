#!/usr/bin/env python3
"""WEB-DESIGN-RSI-1.0: measure a website's design, score a review, or gate a promotion.

A web counterpart to PDF-BRIEF-DESIGN-RSI-1.0 in the EMBLEM RSI test suite. Same loop:
build a candidate, measure it, fix measured failures, review it with evidence, evaluate,
then compare against the incumbent. Promotion needs a passing measured layer, complete
review evidence, every score gate, a minimum gain and no dimension regressing beyond
the allowed amount. Scores are reviewer observations, not visitor-behaviour measurements.
A producer review guides iteration; release needs an independent reviewer and an
approved contract.

  measure   Serve the built site locally, run Lighthouse (mobile) and Playwright checks at
            three viewports, and save hashed full-page screenshots as evidence.
  template  Write an unreviewed review skeleton bound to a measured run's evidence.
  evaluate  Score a completed review against its measured run.
  compare   Promotion gate: incumbent (measured+review) versus candidate (measured+review).

Exit: 0 pass/promoted, 3 completed but gates not passing, 2 blocked.
Needs: Python 3.10+, Playwright for Python with Chromium, Node with Lighthouse.
"""
from __future__ import annotations

import argparse
import functools
import hashlib
import http.server
import json
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

SERIES = "WEB-DESIGN-RSI-1.0"
SCHEMA_VERSION = "1.0.0"
PAGE_ROLE_DIMENSIONS = ("purpose_clarity", "hierarchy", "consistency", "legibility", "information_gain")
ACCURACY_GATES = ("content_matches_sources", "no_fabricated_offers_or_reviews", "unverified_flagged_for_owner")


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


def validate_contract(c: dict) -> dict:
    if c.get("schema") != "web.design.contract.v1" or c.get("measurement_series") != SERIES:
        raise DesignError("Not a WEB-DESIGN-RSI-1.0 contract")
    w = c.get("weights") or {}
    if not w or abs(sum(float(v) for v in w.values()) - 100) > 1e-6:
        raise DesignError("Contract weights must sum to 100")
    for d in c.get("critical_dimensions", []):
        if d not in w:
            raise DesignError(f"Critical dimension {d} has no weight")
    if not c.get("pages"):
        raise DesignError("Contract lists no pages")
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


def measure(site: Path, contract_path: Path, out_dir: Path, lighthouse: str, chrome: str | None) -> dict:
    from playwright.sync_api import sync_playwright

    contract = validate_contract(_load(contract_path))
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
                    if vp in ("phone", "desktop"):
                        if phone:
                            pg.add_style_tag(content=".actionbar{display:none!important}")
                        shot = out_dir / "evidence" / f"{page_file.replace('.html', '')}-{vp}.png"
                        pg.screenshot(path=str(shot), full_page=True)
                        evidence.append({"page": page_file, "role": role, "viewport": vp,
                                         "path": f"evidence/{shot.name}", "sha256": sha256_file(shot)})
                    ctx.close()
                pages[page_file] = page_rec
            browser.close()
    finally:
        httpd.shutdown()

    blockers = [f"missing required page role: {r}" for r in contract.get("required_page_roles", [])
                if r not in present_roles]
    failed = [c for c in checks if not c["pass"]]
    # Keep a copy of the measured build inside the run so evaluate can re-hash it anywhere.
    shutil.copytree(site, out_dir / "site")
    data = {
        "schema": "web.design.measured.v1", "schema_version": SCHEMA_VERSION, "measurement_series": SERIES,
        "target_id": contract["target_id"], "site": "site", "site_source": str(site), "site_sha256": sha256_tree(site),
        "page_roles": {k: v for k, v in contract["pages"].items() if (site / k).is_file()},
        "checks_total": len(checks), "checks_failed": len(failed), "failed_checks": failed,
        "declaration_blockers": blockers, "measured_pass": not failed and not blockers,
        "pages": pages, "evidence": evidence, "checks": checks,
    }
    (out_dir / "measured.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return data


# ---------------------------------------------------------------- reviewing

def review_template(measured: dict, reviewer_id: str, role: str, weights: dict) -> dict:
    ev = measured["evidence"]
    def for_page(page):
        return [{"path": e["path"], "sha256": e["sha256"]} for e in ev if e["page"] == page]
    home = next((p for p, r in measured["page_roles"].items() if r == "home"), None)
    return {
        "schema": "web.design.review.v1", "measurement_series": SERIES, "target_id": measured["target_id"],
        "candidate_sha256": measured["site_sha256"], "reviewer_id": reviewer_id, "reviewer_role": role,
        "ratings": {d: {"score": None, "status": "unreviewed", "rationale": "",
                        "evidence": for_page(home) if home else []} for d in weights},
        "page_roles": [{"id": f"role-{r}", "role": r, "page": p,
                        "ratings": {d: None for d in PAGE_ROLE_DIMENSIONS}, "evidence": for_page(p)}
                       for p, r in measured["page_roles"].items()],
        "accuracy_gate": {g: None for g in ACCURACY_GATES},
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
    for g in ACCURACY_GATES:
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
    measured = _load(measured_path)
    if measured.get("schema") != "web.design.measured.v1" or measured.get("target_id") != contract["target_id"]:
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
    g = {
        "measured_layer": bool(measured.get("measured_pass")) and not site_blockers,
        "evidence_complete": not blockers,
        "overall": overall is not None and overall >= contract["min_overall_score"],
        "critical_dimensions": all(dim.get(d) is not None and dim[d] >= contract["min_dimension_score"]
                                   for d in contract["critical_dimensions"]),
        "page_roles": bool(roles) and all(x["score"] is not None and x["score"] >= contract["min_page_role_score"] for x in roles),
        "accuracy": all((review.get("accuracy_gate") or {}).get(k) is True for k in ACCURACY_GATES),
    }
    diagnostic_pass = all(g.values())
    release_blockers = []
    if not independent: release_blockers.append("Independent reviewer evidence not supplied.")
    if contract.get("approved_for_production") is not True: release_blockers.append("Design contract is not approved_for_production.")
    if not diagnostic_pass: release_blockers.append("Design diagnostic gates are not all passing.")
    weakest = min(((v, k) for k, v in dim.items() if v is not None), default=(None, None))
    return {
        "schema": "web.design.result.v1", "measurement_series": SERIES, "target_id": contract["target_id"],
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
    return {"schema": "web.design.promotion.v1", "measurement_series": SERIES, "target_id": cand["target_id"],
            "incumbent_sha256": inc["candidate_sha256"], "candidate_sha256": cand["candidate_sha256"],
            "incumbent_score": inc["overall_score"], "candidate_score": cand["overall_score"], "gain": gain,
            "measured_failures_incumbent": inc["measured_checks_failed"],
            "measured_failures_candidate": cand["measured_checks_failed"],
            "dimension_regressions": regressions, "promoted": promoted, "status": status,
            "candidate_release_eligible": cand["release_eligible"],
            "candidate_release_blockers": cand["release_blockers"], "incumbent": inc, "candidate": cand}


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
    a = ap.parse_args(argv)
    try:
        if a.cmd == "measure":
            d = measure(a.site, a.contract, a.out, a.lighthouse, a.chrome)
            print(json.dumps({k: d[k] for k in ("target_id", "site_sha256", "checks_total", "checks_failed",
                                                "measured_pass", "declaration_blockers")}, indent=2))
            for f in d["failed_checks"]:
                print(f"  FAIL {f['id']} {f['page']} {f['viewport'] or ''}: measured {f['measured']}, needs {f['threshold']}")
            return 0 if d["measured_pass"] else 3
        if a.cmd == "template":
            if a.out.exists():
                raise DesignError(f"Refusing to overwrite {a.out}")
            contract = validate_contract(_load(a.contract))
            _write(a.out, review_template(_load(a.measured), a.reviewer_id, a.reviewer_role, contract["weights"]))
            print(f"Wrote unreviewed template {a.out}")
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
