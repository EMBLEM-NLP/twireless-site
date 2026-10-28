#!/usr/bin/env python3
"""Build a client's website questionnaire kit from one data file.

The data file (twireless.questionnaire.json) is the single source of truth: every question, its help
text, its options, where a choice jumps to, and which part of the website each answer unlocks.
From it this script makes:

  assets/header.png                  the branded banner (1600 x 400) for the top of the form
  create_<slug>_form.gs              a Google Apps Script that builds the whole Google Form
  <slug>-questionnaire-preview.pdf   what the client will see, for a quick read on a phone
  (the .html it is printed from is kept next to it)
  assets/share.png                   the 1200 x 630 picture that shows when the web app's link is shared
  docs/questionnaire/index.html      the same questions as a web app: one self-contained page with a progress
                                     bar, one section per screen, saved answers and a send screen

  python3 ops/questionnaire/build_questionnaire.py check      validate the data file
  python3 ops/questionnaire/build_questionnaire.py banner     also makes assets/share.png
  python3 ops/questionnaire/build_questionnaire.py script     also dry-runs the script in Node
  python3 ops/questionnaire/build_questionnaire.py preview
  python3 ops/questionnaire/build_questionnaire.py app        needs only the Python standard library
  python3 ops/questionnaire/build_questionnaire.py all

For another client: copy the data file, change "client" and the questions, run `all`.
Needs Python 3.10+, Pillow, and Playwright for Python with Chromium; Node 18+ for the dry run.
"""
from __future__ import annotations

import argparse
import base64
import html
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
FONT = REPO / "designs/design-2/assets/fonts/atkinson-hyperlegible-next-latin-wght-normal.woff2"
DIGITS = REPO / "designs/design-2/assets/fonts/public-sans-digits-wght-normal.woff2"
LOGO = REPO / "src/assets/img/t-wireless-logo-960.png"

BLUE = "#00549a"
BLUE_DEEP = "#003c6e"
RED = "#e53245"
INK = "#1d2b3a"
MUTED = "#53657a"
LINE = "#d3dde8"
TINT = "#e6eef7"

TYPES = {"text", "paragraph", "choice", "checkbox", "grid"}
# Words only the web app, the banner and the share picture read. All optional; each has a default.
FORM_APP_KEYS = ("done", "partial", "summary", "answers_title", "banner_title", "share_title", "preview")


# ---------------------------------------------------------------------------------------------
# data


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate(spec: dict) -> list[str]:
    """Return a list of problems; an empty list means the data is sound."""
    bad: list[str] = []
    parts = {p["id"] for p in spec["parts"]}
    words = spec["form"].get("app", {})
    for key in words:
        if key not in FORM_APP_KEYS:
            bad.append(f"form: unknown app setting {key}")
    for key in ("done", "partial", "summary", "answers_title", "banner_title", "share_title"):
        if key in words and not str(words[key]).strip():
            bad.append(f"form.app.{key} is empty")
    if "preview" in words:
        link = words["preview"]
        host = urlparse(link.get("url", "")) if isinstance(link, dict) else None
        if host is None or set(link) - {"label", "url"} or not link.get("label", "").strip():
            bad.append("form.app.preview is { label, url }")
        elif host.scheme != "https" or not host.netloc:
            bad.append("form.app.preview.url must be an https address")
    sections = spec["sections"]
    sec_ids = [s["id"] for s in sections]
    if len(sec_ids) != len(set(sec_ids)):
        bad.append("duplicate section ids")
    seen: set[str] = set()
    for i, s in enumerate(sections):
        if s["part"] not in parts:
            bad.append(f"section {s['id']}: unknown part {s['part']}")
        if not s.get("title"):
            bad.append(f"section {s['id']}: no title")
        for key in s.get("app", {}):
            if key != "description":
                bad.append(f"section {s['id']}: unknown app setting {key}")
        if s.get("gate") and (i == 0 or len(s["questions"]) != 1):
            bad.append(f"section {s['id']}: a gate is one question and never the first section")
        for q in s["questions"]:
            qid = q["id"]
            if qid in seen:
                bad.append(f"duplicate question id {qid}")
            seen.add(qid)
            if q["type"] not in TYPES:
                bad.append(f"{qid}: unknown type {q['type']}")
            if not q.get("title"):
                bad.append(f"{qid}: no title")
            if len(q.get("title", "")) > 300:
                bad.append(f"{qid}: title longer than 300 characters")
            if len(q.get("help", "")) > 1200:
                bad.append(f"{qid}: help longer than 1200 characters")
            if "required" not in q:
                bad.append(f"{qid}: required is not set")
            if q["type"] in ("choice", "checkbox"):
                opts = q.get("options") or []
                if len(opts) != len(set(opts)):
                    bad.append(f"{qid}: duplicate options")
                if len(opts) + (1 if q.get("other") else 0) < 2:
                    bad.append(f"{qid}: fewer than two ways to answer")
                if any(not o.strip() for o in opts):
                    bad.append(f"{qid}: an empty option")
            if q["type"] == "grid":
                if not q.get("rows") or not q.get("cols"):
                    bad.append(f"{qid}: a grid needs rows and cols")
                if len(q["rows"]) != len(set(q["rows"])) or len(q["cols"]) != len(set(q["cols"])):
                    bad.append(f"{qid}: duplicate grid rows or columns")
            app = q.get("app") or {}
            for key in app:
                if key not in ("exclusive", "autocomplete", "inputmode"):
                    bad.append(f"{qid}: unknown app setting {key}")
            for label in app.get("exclusive", []):
                if q["type"] != "checkbox" or label not in q.get("options", []):
                    bad.append(f"{qid}: exclusive option that does not exist: {label}")
            if ("autocomplete" in app or "inputmode" in app) and q["type"] != "text":
                bad.append(f"{qid}: autocomplete and inputmode are for text questions")
            for label, target in (q.get("goto") or {}).items():
                if q["type"] != "choice":
                    bad.append(f"{qid}: only a choice question can jump")
                if label not in q["options"]:
                    bad.append(f"{qid}: jump from an option that does not exist: {label}")
                if not (target.startswith("@") or target in sec_ids):
                    bad.append(f"{qid}: jump to a section that does not exist: {target}")
                elif target in sec_ids and sec_ids.index(target) <= i:
                    bad.append(f"{qid}: jumps backwards to {target}")
                if target.startswith("@") and target not in ("@submit", "@next"):
                    bad.append(f"{qid}: unknown jump {target}")
                if q.get("other"):
                    bad.append(f"{qid}: Google Forms can't combine an Other option with a jump")
    return bad


def counts(spec: dict) -> dict:
    out: dict = {"sections": len(spec["sections"]), "questions": 0}
    for p in spec["parts"]:
        out[p["id"]] = 0
    for s in spec["sections"]:
        for _ in s["questions"]:
            out["questions"] += 1
            out[s["part"]] += 1
    return out


def coverage(spec: dict) -> dict[str, list[dict]]:
    """tag -> the questions that unlock it, in form order."""
    out: dict[str, list[dict]] = {}
    for s in spec["sections"]:
        for q in s["questions"]:
            for tag in q.get("unlocks", []):
                out.setdefault(tag, []).append({"id": q["id"], "title": q["title"], "section": s["title"], "part": s["part"]})
    return out


def esc(text: str) -> str:
    return html.escape(text, quote=True).replace("\n", "<br>")


def data_uri(path: Path, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def first_minutes(spec: dict) -> str:
    return spec["parts"][0]["minutes"].split(",")[0].strip()


def form_words(spec: dict) -> dict:
    """The optional words that only the web app, the banner and the share picture use, with a default for each.

    summary          one or two sentences for a link preview and the share picture; {minutes} becomes Part 1's time
    answers_title    the first line of the text a person sends back (it is theirs, so it is not the form's title)
    banner_title     the line under the logo on the banner
    share_title      the large line on the share picture
    """
    form = spec["form"]
    given = form.get("app") or {}
    paras = [p for p in form["description"].split("\n\n") if p.strip() and not p.startswith("Prepared by")]
    summary = given.get("summary") or (paras[1] if len(paras) > 1 else form["title"])
    banner = given.get("banner_title", "Website questions")
    return {
        "summary": summary.replace("{minutes}", first_minutes(spec)),
        "answers_title": given.get("answers_title", form["title"]),
        "banner_title": banner,
        "share_title": given.get("share_title", banner),
    }


# ---------------------------------------------------------------------------------------------
# banner


def banner_html(spec: dict) -> str:
    c = spec["client"]
    font = data_uri(FONT, "font/woff2")
    logo = data_uri(LOGO, "image/png")
    return f"""<!doctype html><meta charset="utf-8">
<style>
@font-face {{ font-family: "Atkinson"; src: url("{font}") format("woff2"); font-weight: 200 800; }}
html, body {{ margin: 0; background: #fff; }}
.banner {{ position: relative; width: 1600px; height: 400px; overflow: hidden; background: #fff;
  font-family: "Atkinson", system-ui, sans-serif; color: {BLUE_DEEP}; }}
.logo {{ position: absolute; left: 118px; top: 98px; width: 820px; height: auto; display: block; }}
.what {{ position: absolute; left: 122px; top: 244px; font-size: 44px; font-weight: 700; letter-spacing: 0.004em; }}
.where {{ position: absolute; left: 122px; top: 304px; font-size: 30px; color: {MUTED}; }}
.rule {{ position: absolute; left: 1060px; top: 92px; width: 3px; height: 214px; background: {LINE}; }}
.by {{ position: absolute; left: 1112px; top: 128px; font-size: 30px; color: {MUTED}; }}
.agency {{ position: absolute; left: 1110px; top: 170px; font-size: 62px; font-weight: 800; letter-spacing: 0.012em; }}
.strip {{ position: absolute; left: 0; right: 0; bottom: 0; height: 24px; background: {BLUE}; }}
.strip i {{ position: absolute; left: 0; top: 0; bottom: 0; width: 260px; background: {RED}; }}
</style>
<div class="banner">
  <img class="logo" src="{logo}" alt="">
  <div class="what">{esc(form_words(spec)['banner_title'])}</div>
  <div class="where">{esc(c['address'].replace(', Unit 1', ''))}</div>
  <div class="rule"></div>
  <div class="by">Prepared by</div>
  <div class="agency">{esc(c['agency'])}</div>
  <div class="strip"><i></i></div>
</div>"""


def render_banner(spec: dict, out: Path) -> None:
    from playwright.sync_api import sync_playwright

    out.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 400}, device_scale_factor=1)
        page.set_content(banner_html(spec))
        page.evaluate("document.fonts.ready")
        page.wait_for_timeout(200)
        page.screenshot(path=str(out), clip={"x": 0, "y": 0, "width": 1600, "height": 400})
        browser.close()
    from PIL import Image

    # Flat colours and a few shades for the text edges: a 96-colour palette is a third of the size
    # and looks the same. The script carries this file inside it, so a small file is a short paste.
    im = Image.open(out).convert("RGB")
    im = im.quantize(colors=96, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    im.save(out, optimize=True)
    print(f"banner  {out.relative_to(REPO)}  {out.stat().st_size / 1024:.0f} KiB")


# ---------------------------------------------------------------------------------------------
# Google Apps Script

GS_TEMPLATE = r"""/**
 * __NAME__ website questionnaire: builds the Google Form.
 * Made by ops/questionnaire/build_questionnaire.py from __DATA__.
 * Don't edit this file by hand: change the data file and build again.
 *
 * HOW TO USE (about 3 minutes)
 *  1. Go to https://script.google.com and choose "New project".
 *  2. Delete the sample code, paste this whole file, and press the Save icon.
 *  3. In the function menu at the top, choose "createQuestionnaireForm", then press Run.
 *  4. Google asks for permission. The script only needs to create and edit Google Forms.
 *     It says the app isn't verified because it's your own new script: choose Advanced, then
 *     "Go to" the project, then Allow.
 *  5. When it finishes, open the Execution log at the bottom. It prints the link to edit the
 *     form and the link to send to __CONTACT__.
 *  6. A script can't set the look. In the form, open the palette icon and set the theme colour
 *     to __COLOR__, the background to __BACKGROUND__ and the font to __FONT__. The banner is already
 *     at the top of the first page; you can also use it as the header image.
 *  Each run makes a new form. Delete extra copies from Google Drive.
 */

function createQuestionnaireForm() {
  var spec = SPEC;
  var form = FormApp.create(spec.form.title);
  try {
    form.setDescription(spec.form.description);
    form.setConfirmationMessage(spec.form.confirmation);
    form.setCollectEmail(false);
    form.setShuffleQuestions(false);
    form.setProgressBar(!!spec.form.settings.progress_bar);
    form.setAllowResponseEdits(!!spec.form.settings.allow_edits);
    form.setShowLinkToRespondAgain(!!spec.form.settings.show_respond_again);
    tryOnly_(function () { form.setRequireLogin(false); }, 'sign-in setting');
    tryOnly_(function () { form.setLimitOneResponsePerUser(false); }, 'one-response setting');

    if (BANNER_BASE64) {
      var blob = Utilities.newBlob(Utilities.base64Decode(BANNER_BASE64), 'image/png', 'header.png');
      form.addImageItem()
        .setImage(blob)
        .setAltText(spec.client.name + ' website questions, prepared by ' + spec.client.agency)
        .setAlignment(FormApp.Alignment.CENTER);
    }

    var pages = {};
    var jumps = [];
    spec.sections.forEach(function (section, index) {
      if (index === 0) {
        var header = form.addSectionHeaderItem().setTitle(section.title);
        if (section.description) header.setHelpText(section.description);
      } else {
        var page = form.addPageBreakItem().setTitle(section.title);
        if (section.description) page.setHelpText(section.description);
        pages[section.id] = page;
      }
      section.questions.forEach(function (q) {
        var item = addQuestion_(form, q);
        if (q.goto) jumps.push({ item: item, q: q });
      });
    });

    // Jumps point at pages that come later in the form, so they are set once every page exists.
    jumps.forEach(function (j) { setJumps_(j.item, j.q, pages); });
  } catch (err) {
    Logger.log('Stopped part-way: ' + err);
    Logger.log('Delete the unfinished form "' + spec.form.title + '" from Google Drive, then run again.');
    throw err;
  }

  var editUrl = form.getEditUrl();
  var shareUrl = form.getPublishedUrl();
  Logger.log('Made the form with ' + form.getItems().length + ' items.');
  Logger.log('Edit it: ' + editUrl);
  Logger.log('Send this link to ' + spec.client.contact + ': ' + shareUrl);
  return { edit: editUrl, share: shareUrl };
}

function addQuestion_(form, q) {
  var item;
  if (q.type === 'text') {
    item = form.addTextItem();
  } else if (q.type === 'paragraph') {
    item = form.addParagraphTextItem();
  } else if (q.type === 'choice') {
    item = form.addMultipleChoiceItem();
    item.setChoiceValues(q.options);
    if (q.other) item.showOtherOption(true);
  } else if (q.type === 'checkbox') {
    item = form.addCheckboxItem();
    item.setChoiceValues(q.options);
    if (q.other) item.showOtherOption(true);
    if (q.max_choices) {
      item.setValidation(FormApp.createCheckboxValidation()
        .requireSelectAtMost(q.max_choices)
        .setHelpText('Choose up to ' + q.max_choices + '.')
        .build());
    }
  } else if (q.type === 'grid') {
    item = form.addGridItem();
    item.setRows(q.rows);
    item.setColumns(q.cols);
  } else {
    throw new Error('Unknown question type "' + q.type + '" for ' + q.id);
  }
  item.setTitle(q.title);
  if (q.help) item.setHelpText(q.help);
  item.setRequired(!!q.required);
  return item;
}

function setJumps_(item, q, pages) {
  var choices = q.options.map(function (label) {
    var target = q.goto[label];
    if (!target) return item.createChoice(label);
    if (target === '@submit') return item.createChoice(label, FormApp.PageNavigationType.SUBMIT);
    if (target === '@next') return item.createChoice(label, FormApp.PageNavigationType.CONTINUE);
    if (!pages[target]) throw new Error('No page "' + target + '" for the jump in ' + q.id);
    return item.createChoice(label, pages[target]);
  });
  item.setChoices(choices);
}

function tryOnly_(fn, what) {
  try { fn(); } catch (e) { Logger.log('Left the ' + what + ' as it was: ' + e); }
}

// The banner (a PNG, base64) and the questions. They are data, so they sit at the bottom.
var BANNER_BASE64 = '__BANNER__';

var SPEC = __SPEC__;
"""


def script_spec(spec: dict) -> str:
    """The data the script needs, without the notes that are only for the team."""
    lean_sections = []
    for s in spec["sections"]:
        qs = []
        for q in s["questions"]:
            qs.append({k: v for k, v in q.items() if k not in ("unlocks", "why", "app")})
        lean_sections.append({**{k: v for k, v in s.items() if k not in ("questions", "app")}, "questions": qs})
    lean = {
        "client": {k: spec["client"][k] for k in ("name", "contact", "agency")},
        "form": {k: v for k, v in spec["form"].items() if k != "app"},
        "sections": lean_sections,
    }
    head = json.dumps({k: lean[k] for k in ("client", "form")}, ensure_ascii=False, indent=1)
    head = head[:-2]  # drop the closing brace so the sections can follow
    lines = [json.dumps(s, ensure_ascii=False, separators=(",", ":")) for s in lean_sections]
    return head + ',\n "sections": [\n  ' + ",\n  ".join(lines) + "\n ]\n}"


def build_script(spec: dict, banner: Path, out: Path, data_name: str) -> None:
    theme = spec["form"]["theme"]
    text = (
        GS_TEMPLATE.replace("__NAME__", spec["client"]["name"])
        .replace("__DATA__", data_name)
        .replace("__CONTACT__", spec["client"]["contact"])
        .replace("__COLOR__", theme["color"])
        .replace("__BACKGROUND__", theme["background"])
        .replace("__FONT__", theme["font"])
        .replace("__BANNER__", base64.b64encode(banner.read_bytes()).decode("ascii") if banner.exists() else "")
        .replace("__SPEC__", script_spec(spec))
    )
    out.write_text(text, encoding="utf-8")
    print(f"script  {out.relative_to(REPO)}  {out.stat().st_size / 1024:.0f} KiB")


def dry_run(script: Path, spec: dict) -> bool:
    """Run the script against a stand-in for Google Forms (check_form_script.js)."""
    r = subprocess.run(
        ["node", str(HERE / "check_form_script.js"), str(script), str(HERE / "twireless.questionnaire.json")],
        capture_output=True,
        text=True,
    )
    print(r.stdout.rstrip())
    if r.returncode:
        print(r.stderr.rstrip())
    return r.returncode == 0


# ---------------------------------------------------------------------------------------------
# preview (what the client sees)

PREVIEW_CSS = f"""
@font-face {{ font-family: "Atkinson"; src: url("__FONT__") format("woff2"); font-weight: 200 800; }}
@page {{
  size: Letter; margin: 0.5in 0.6in 0.7in;
  @bottom-left {{ content: "__FOOT__"; font: 8pt "Atkinson", sans-serif; color: {MUTED}; vertical-align: top; padding-top: 0.2in; }}
  @bottom-right {{ content: "Page " counter(page) " of " counter(pages); font: 8pt "Atkinson", sans-serif; color: {MUTED}; vertical-align: top; padding-top: 0.2in; }}
}}
* {{ box-sizing: border-box; }}
html {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; background: {TINT}; }}
body {{ margin: 0; background: {TINT}; color: {INK}; font: 10pt/1.4 "Atkinson", system-ui, sans-serif; }}
.page {{ max-width: 7.3in; margin: 0 auto; }}
.banner {{ display: block; width: 100%; height: auto; border-radius: 10px 10px 0 0; }}
.card {{ background: #fff; border: 1px solid {LINE}; border-radius: 9px; padding: 11px 16px 11px; margin: 0 0 7px; break-inside: avoid; }}
.title-card {{ border-radius: 0 0 10px 10px; border-top: 0; border-bottom: 1px solid {LINE}; margin-bottom: 14px; padding-top: 16px; }}
.title-card h1 {{ margin: 0 0 8px; font-size: 21pt; line-height: 1.15; font-weight: 750; color: {BLUE_DEEP}; }}
.title-card p {{ margin: 0 0 8px; }}
.title-card .req {{ margin: 12px 0 0; color: {RED}; font-size: 9.4pt; }}
.section {{ background: {BLUE}; color: #fff; border-radius: 9px; padding: 9px 16px 10px; margin: 16px 0 7px; break-after: avoid; break-inside: avoid; }}
.section h2 {{ margin: 0; font-size: 13.5pt; line-height: 1.22; font-weight: 700; }}
.section p {{ margin: 4px 0 0; font-size: 9.4pt; opacity: .96; }}
.section.gate {{ background: {BLUE_DEEP}; }}
.q {{ margin: 0 0 4px; font-size: 10.6pt; font-weight: 650; line-height: 1.28; }}
.q .star {{ color: {RED}; margin-left: 3px; }}
.help {{ margin: 0 0 6px; color: {MUTED}; font-size: 9pt; line-height: 1.38; }}
.opts {{ margin: 6px 0 0; padding: 0; list-style: none; }}
.opts.two {{ columns: 2; column-gap: 22px; }}
.opts.two li {{ break-inside: avoid; }}
.opts li {{ position: relative; margin: 0 0 4px; padding-left: 23px; line-height: 1.32; }}
.opts li::before {{ content: ""; position: absolute; left: 1px; top: 2px; width: 12px; height: 12px; border: 2px solid #6d7b8a; background: #fff; }}
.radio li::before {{ border-radius: 50%; }}
.check li::before {{ border-radius: 3px; }}
.fill {{ margin-top: 12px; border-bottom: 1.5px solid #9aa8b6; color: #7a8896; padding-bottom: 2px; font-size: 9.6pt; width: 62%; }}
.fill.long {{ width: 100%; height: 38px; }}
.other {{ display: inline-block; min-width: 150px; border-bottom: 1.5px solid #9aa8b6; margin-left: 6px; }}
.flow {{ margin: 9px 0 0; padding: 6px 9px; background: #f1f6fb; border-left: 3px solid {BLUE}; color: {BLUE_DEEP}; font-size: 8.9pt; line-height: 1.35; }}
table.grid {{ width: 100%; border-collapse: collapse; margin-top: 8px; font-size: 9.2pt; }}
table.grid th {{ font-weight: 600; text-align: center; color: {MUTED}; padding: 0 3px 6px; vertical-align: bottom; line-height: 1.2; }}
table.grid th:first-child {{ text-align: left; }}
table.grid td {{ border-top: 1px solid {LINE}; padding: 6px 3px; text-align: center; vertical-align: middle; }}
table.grid td:first-child {{ text-align: left; padding-right: 10px; line-height: 1.32; }}
table.grid td i {{ display: inline-block; width: 12px; height: 12px; border: 2px solid #6d7b8a; border-radius: 50%; vertical-align: middle; }}
.end {{ margin: 22px 0 0; text-align: center; color: {MUTED}; font-size: 9.2pt; }}
"""


def option_list(q: dict, kind: str) -> str:
    items = "".join(f"<li>{esc(o)}</li>" for o in q["options"])
    if q.get("other"):
        items += '<li>Other: <span class="other"></span></li>'
    many = len(q["options"]) + (1 if q.get("other") else 0) >= 5
    short = max(len(o) for o in q["options"]) <= 40
    return f'<ul class="opts {kind}{" two" if many and short else ""}">{items}</ul>'


def jump_note(q: dict, spec: dict) -> str:
    if not q.get("goto"):
        return ""
    titles = {s["id"]: s["title"] for s in spec["sections"]}
    lines = []
    for label, target in q["goto"].items():
        if target == "@submit":
            lines.append(f"If you choose “{esc(label)}”, the form ends and sends your answers.")
        elif target == "@next":
            lines.append(f"If you choose “{esc(label)}”, you go to the next page.")
        else:
            lines.append(f"If you choose “{esc(label)}”, you skip ahead to “{esc(titles[target])}”.")
    return '<div class="flow">' + "<br>".join(lines) + "</div>"


def question_html(q: dict, spec: dict) -> str:
    star = '<span class="star">*</span>' if q.get("required") else ""
    head = f'<div class="q">{esc(q["title"])}{star}</div>'
    if q.get("help"):
        head += f'<div class="help">{esc(q["help"])}</div>'
    t = q["type"]
    if t == "text":
        body = '<div class="fill">Your answer</div>'
    elif t == "paragraph":
        body = '<div class="fill long">Your answer</div>'
    elif t == "choice":
        body = option_list(q, "radio")
    elif t == "checkbox":
        body = option_list(q, "check")
    else:
        cols = "".join(f"<th>{esc(c)}</th>" for c in q["cols"])
        rows = "".join(
            f"<tr><td>{esc(r)}</td>" + "".join("<td><i></i></td>" for _ in q["cols"]) + "</tr>" for r in q["rows"]
        )
        body = f'<table class="grid"><tr><th></th>{cols}</tr>{rows}</table>'
    return f'<div class="card">{head}{body}{jump_note(q, spec)}</div>'


def foot_text(spec: dict) -> str:
    c = spec["client"]
    return f"Preview of the Google Form for {c['name']}. Prepared by {c['agency']}."


def preview_html(spec: dict, banner: Path) -> str:
    form = spec["form"]
    out = [
        "<!doctype html><meta charset='utf-8'>",
        f"<title>{esc(form['title'])}: preview</title>",
        "<style>" + PREVIEW_CSS.replace("__FONT__", data_uri(FONT, "font/woff2")).replace("__FOOT__", foot_text(spec)) + "</style>",
        '<div class="page">',
    ]
    if banner.exists():
        out.append(f'<img class="banner" src="{data_uri(banner, "image/png")}" alt="">')
    out.append(
        '<div class="card title-card">'
        f"<h1>{esc(form['title'])}</h1>"
        + "".join(f"<p>{esc(par)}</p>" for par in form["description"].split("\n\n"))
        + '<p class="req">* Indicates a required question</p></div>'
    )
    for s in spec["sections"]:
        cls = "section gate" if s.get("gate") else "section"
        desc = f"<p>{esc(s['description'])}</p>" if s.get("description") else ""
        out.append(f'<div class="{cls}"><h2>{esc(s["title"])}</h2>{desc}</div>')
        out.extend(question_html(q, spec) for q in s["questions"])
    out.append(f'<div class="end">End of the form. {esc(form["confirmation"].split(chr(10))[0])}</div></div>')
    return "\n".join(out)


def render_pdf(html_path: Path, pdf_path: Path, spec: dict) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(html_path.as_uri())
        page.evaluate("document.fonts.ready")
        page.pdf(path=str(pdf_path), prefer_css_page_size=True, print_background=True)
        browser.close()
    print(f"preview {pdf_path.relative_to(REPO)}  {pdf_path.stat().st_size / 1024:.0f} KiB")


# ---------------------------------------------------------------------------------------------
# share picture (what shows when the web app's link is sent in a text or WhatsApp message)


def share_html(spec: dict) -> str:
    c = spec["client"]
    words = form_words(spec)
    font = data_uri(FONT, "font/woff2")
    logo = data_uri(LOGO, "image/png")
    return f"""<!doctype html><meta charset="utf-8">
<style>
@font-face {{ font-family: "Atkinson"; src: url("{font}") format("woff2"); font-weight: 200 800; }}
html, body {{ margin: 0; background: #fff; }}
.share {{ position: relative; width: 1200px; height: 630px; overflow: hidden; background: #fff;
  font-family: "Atkinson", system-ui, sans-serif; color: {BLUE_DEEP}; }}
.inner {{ position: absolute; left: 92px; right: 92px; top: 62px; }}
.logo {{ width: 600px; height: auto; display: block; margin-left: -4px; }}
.title {{ margin-top: 40px; font-size: 72px; font-weight: 800; letter-spacing: -0.004em; line-height: 1.06; text-wrap: balance; }}
.sub {{ margin-top: 22px; max-width: 990px; font-size: 36px; line-height: 1.32; color: {MUTED}; text-wrap: balance; }}
.by {{ position: absolute; left: 94px; bottom: 62px; font-size: 30px; color: {MUTED}; }}
.by b {{ color: {BLUE_DEEP}; font-weight: 800; letter-spacing: 0.01em; }}
.strip {{ position: absolute; left: 0; right: 0; bottom: 0; height: 30px; background: {BLUE}; }}
.strip i {{ position: absolute; left: 0; top: 0; bottom: 0; width: 300px; background: {RED}; }}
</style>
<div class="share">
  <div class="inner">
    <img class="logo" src="{logo}" alt="">
    <div class="title">{esc(words['share_title']).replace(c['name'], c['name'].replace(' ', '&nbsp;'))}</div>
    <div class="sub">{esc(words['summary']).replace(c['name'], c['name'].replace(' ', '&nbsp;'))}</div>
  </div>
  <div class="by">Prepared by <b>{esc(c['agency'])}</b></div>
  <div class="strip"><i></i></div>
</div>"""


def render_share(spec: dict, out: Path) -> None:
    from playwright.sync_api import sync_playwright

    out.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1200, "height": 630}, device_scale_factor=1)
        page.set_content(share_html(spec))
        page.evaluate("document.fonts.ready")
        page.wait_for_timeout(200)
        page.screenshot(path=str(out), clip={"x": 0, "y": 0, "width": 1200, "height": 630})
        browser.close()
    from PIL import Image

    im = Image.open(out).convert("RGB")
    im = im.quantize(colors=64, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    im.save(out, optimize=True)
    print(f"share   {out.relative_to(REPO)}  {out.stat().st_size / 1024:.0f} KiB")


# ---------------------------------------------------------------------------------------------
# web app (ops/questionnaire/app/): the same questions as one self-contained page

APP_DIR = HERE / "app"
APP_OUT = REPO / "docs" / "questionnaire" / "index.html"
APP_URL = "https://emblem-nlp.github.io/twireless-site/questionnaire/"
APP_VERSION = 1  # change it when answers saved on people's devices should no longer be used
SHARE = HERE / "assets" / "share.png"
FAVICON = REPO / "src/assets/img/favicon-32.png"
APP_LOGO = REPO / "src/assets/img/t-wireless-logo-480.png"
PART_PREFIX = re.compile(r"^Part \d+ of \d+:\s*")
TEAM_ONLY = ("unlocks", "why", "app")  # notes for us; they never go to the client's device


def app_description(section: dict) -> str:
    """What the web app says under a page's title: the page's description unless the data gives the app its own
    (an empty one shows nothing, for a page the app only shows once its question applies)."""
    own = section.get("app") or {}
    return own["description"] if "description" in own else section.get("description", "")


def app_screens(spec: dict) -> list[dict]:
    """Group the form's pages into the screens of the web app.

    Every page becomes a screen, with two exceptions. A page whose answer can jump past the pages after it
    (Repairs: "No") is shown together with them: they appear once the answer says they apply. A gate page (the two
    "keep going or finish later" pages) is a stop between the parts, and "finish later" goes to the send screen.
    """
    secs = spec["sections"]
    ids = [s["id"] for s in secs]
    out: list[dict] = []
    i = 0
    while i < len(secs):
        s = secs[i]
        if s.get("gate"):
            q = s["questions"][0]
            for label, target in (q.get("goto") or {}).items():
                if target not in ("@submit", "@next") and ids.index(target) != i + 1:
                    raise ValueError(f"{q['id']}: from a gate, '{label}' must end the form or go to the next page")
            out.append({"id": s["id"], "kind": "stop", "part": s["part"], "title": s["title"],
                        "description": app_description(s) or s.get("description", ""),
                        "pages": [s["id"]]})
            i += 1
            continue
        end = i
        for q in s["questions"]:
            for target in (q.get("goto") or {}).values():
                if target == "@next":
                    continue
                if target.startswith("@"):
                    raise ValueError(f"{q['id']}: only a gate page can end the form in the web app")
                end = max(end, ids.index(target) - 1)
        group = secs[i : end + 1]
        for later in group[1:]:
            if later.get("gate") or later["part"] != s["part"] or any(q.get("goto") for q in later["questions"]):
                raise ValueError(f"{later['id']}: a page that a jump can skip must be plain and in the same part")
        out.append({"id": s["id"], "kind": "section", "part": s["part"], "title": PART_PREFIX.sub("", s["title"]),
                    "description": app_description(s), "pages": [g["id"] for g in group]})
        i = end + 1
    return out


def app_model(spec: dict, endpoint: str = "") -> dict:
    """Everything the page needs, without the notes that are only for the team."""
    form = spec["form"]
    paras = [p for p in form["description"].split("\n\n") if p.strip()]
    byline = paras.pop() if paras and paras[-1].startswith("Prepared by") else ""
    words = form.get("app") or {}
    parts = []
    for n, p in enumerate(spec["parts"], 1):
        minutes = p["minutes"].split(",")[0].strip()
        parts.append({"id": p["id"], "n": n, "of": len(spec["parts"]), "title": PART_PREFIX.sub("", p["title"]),
                      "minutes": minutes, "mins": int(re.search(r"\d+", minutes).group()),
                      "optional": "optional" in p["minutes"].lower()})
    pages = []
    for s in spec["sections"]:
        qs = []
        for q in s["questions"]:
            lean = {k: v for k, v in q.items() if k not in TEAM_ONLY}
            lean.update(q.get("app") or {})
            qs.append(lean)
        pages.append({"id": s["id"], "title": s["title"], "description": app_description(s), "questions": qs})
    return {
        "version": APP_VERSION,
        "client": {k: spec["client"][k] for k in ("slug", "name", "agency")},  # the contact's name stays in the data file
        "title": form["title"],
        "answersTitle": form_words(spec)["answers_title"],
        "preview": words.get("preview"),
        "intro": paras,
        "byline": byline,
        "done": words.get("done") or form["confirmation"].split("\n\n")[0],
        "partial": words.get("partial") or "Here is what you have answered so far.",
        "endpoint": endpoint,
        "logo": data_uri(APP_LOGO, "image/png"),
        "parts": parts,
        "screens": app_screens(spec),
        "pages": pages,
    }


def content_security_policy(endpoint: str) -> str:
    """The page makes no requests of its own, so say so. Only a send address, if one is set, may be reached."""
    connect = "'none'"
    if endpoint:
        host = urlparse(endpoint)
        connect = f"{host.scheme}://{host.netloc}"
        if host.netloc == "script.google.com":  # Apps Script answers from a second address
            connect += " https://script.googleusercontent.com"
    return ("default-src 'none'; img-src data:; font-src data:; style-src 'unsafe-inline'; "
            f"script-src 'unsafe-inline'; connect-src {connect}; base-uri 'none'; form-action 'none'")


def build_app(spec: dict, out: Path, url: str = APP_URL, endpoint: str = "") -> None:
    model = app_model(spec, endpoint)
    description = form_words(spec)["summary"]
    share = ""
    if SHARE.exists():
        image = url.rstrip("/") + "/share.png"
        share = (f'<meta property="og:image" content="{esc(image)}">\n<meta name="twitter:card" content="summary_large_image">\n'
                 f'<meta name="twitter:image" content="{esc(image)}">')
        out.parent.mkdir(parents=True, exist_ok=True)
        (out.parent / "share.png").write_bytes(SHARE.read_bytes())
    # JSON inside a script element. "</script" would end it, and "<!--" followed by "<script" would stop the browser from
    # ever finding its end, so no "<" is written as itself ("\u003c" is the same character to JSON.parse). The same goes
    # for ">" and "&", and U+2028/9 are line breaks to a script.
    blob = json.dumps(model, ensure_ascii=False, separators=(",", ":"))
    blob = (blob.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
            .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))
    css = (APP_DIR / "app.css").read_text(encoding="utf-8")
    css = css.replace("%%FONT%%", data_uri(FONT, "font/woff2")).replace("%%DIGITS%%", data_uri(DIGITS, "font/woff2"))
    values = {
        "TITLE": esc(model["title"]), "DESCRIPTION": esc(description), "CSP": esc(content_security_policy(endpoint)),
        "AGENCY": esc(spec["client"]["agency"]), "URL": esc(url),
        "SHARE": share, "FAVICON": data_uri(FAVICON, "image/png"), "CSS": css, "SPEC": blob,
        "JS": (APP_DIR / "app.js").read_text(encoding="utf-8"),
    }
    page = re.sub(r"%%(\w+)%%", lambda m: values[m.group(1)], (APP_DIR / "template.html").read_text(encoding="utf-8"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    shown = out.relative_to(REPO) if REPO in out.resolve().parents else out
    stops = sum(1 for s in model["screens"] if s["kind"] == "stop")
    print(f"app     {shown}  {out.stat().st_size / 1024:.0f} KiB  ({len(model['screens']) - stops} sections, {stops} stops)")


# ---------------------------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=["check", "banner", "script", "preview", "app", "all"])
    ap.add_argument("--data", type=Path, default=HERE / "twireless.questionnaire.json")
    ap.add_argument("--out", type=Path, default=HERE, help="where the .gs, .html and .pdf go")
    ap.add_argument("--app-out", type=Path, default=APP_OUT, help="where the web app's index.html goes")
    ap.add_argument("--url", default=APP_URL, help="the public address of the web app (for link previews)")
    ap.add_argument("--endpoint", default="", help="an address the web app can send the answers to (optional)")
    ns = ap.parse_args()

    spec = load(ns.data)
    problems = validate(spec)
    if problems:
        print("The data file has problems:")
        for p in problems:
            print("  -", p)
        return 3
    n = counts(spec)
    per_part = ", ".join(p["id"] + " " + str(n[p["id"]]) for p in spec["parts"])
    print(f"data    {ns.data.name}: {n['sections']} pages, {n['questions']} questions ({per_part})")
    if ns.step == "check":
        return 0

    slug = spec["client"]["slug"]
    banner = HERE / "assets" / "header.png"
    if ns.step in ("banner", "all"):
        render_banner(spec, banner)
        render_share(spec, SHARE)
    if ns.step in ("script", "all"):
        gs = ns.out / f"create_{slug}_form.gs"
        build_script(spec, banner, gs, ns.data.name)
        if not dry_run(gs, spec):
            return 3
    if ns.step in ("preview", "all"):
        page = ns.out / f"{slug}-questionnaire-preview.html"
        page.write_text(preview_html(spec, banner), encoding="utf-8")
        render_pdf(page, ns.out / f"{slug}-questionnaire-preview.pdf", spec)
    if ns.step in ("app", "all"):
        build_app(spec, ns.app_out, ns.url, ns.endpoint)
    return 0


if __name__ == "__main__":
    sys.exit(main())
