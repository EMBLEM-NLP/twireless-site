#!/usr/bin/env python3
"""End-to-end check of the questionnaire web app, in a headless Chromium.

    python3 ops/questionnaire/app/check_app.py                 # build to a temp folder and test that
    python3 ops/questionnaire/app/check_app.py --axe axe.min.js  # also run axe-core (see below)

It builds the app from the data file, serves it on localhost and then does what a person does: taps through
every screen, leaves required answers empty, picks "No" at the gates, closes the page and comes back, presses
Copy, Save and Share, and rotates through phone, tablet and desktop widths. It fails (exit 1) if any check fails.

It checks the page's behaviour in Chromium only. It can't tell how Safari on an iPhone draws the page, how a
screen reader reads it, or what Google's share sheet offers; those need a real phone.

axe-core is optional: pass the path of its axe.min.js (npm i axe-core, then node_modules/axe-core/axe.min.js).
Needs Playwright for Python with Chromium. The data file's own ids are used, so this is written for this client.
"""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import sys
import tempfile
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import build_questionnaire as bq  # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402

OTHER = "__other__"


class Report:
    def __init__(self) -> None:
        self.failed = 0
        self.total = 0

    def check(self, name: str, cond: object, detail: str = "") -> bool:
        self.total += 1
        ok = bool(cond)
        if not ok:
            self.failed += 1
        print(("  ok    " if ok else "  FAIL  ") + name + (f"   [{detail}]" if detail and not ok else ""))
        return ok

    def section(self, title: str) -> None:
        print(f"\n{title}")


R = Report()


# ---------------------------------------------------------------------------------------------
# servers


def poll(page, fn: str, arg=None, timeout: float = 2.0) -> bool:
    """True if a page function returns something truthy within the time; unlike until(), never raises."""
    try:
        until(page, fn, arg, timeout)
        return True
    except TimeoutError:
        return False


def until(page, fn: str, arg=None, timeout: float = 5.0, what: str = "") -> None:
    """Wait until a page function returns something truthy. Polls with evaluate(), because the app's content
    security policy forbids eval and Playwright's wait_for_function needs it once it has to poll."""
    import time
    end = time.time() + timeout
    while True:
        try:
            if page.evaluate(fn, arg):
                return
        except Exception:  # the page is busy navigating
            pass
        if time.time() > end:
            raise TimeoutError(f"gave up waiting for {what or fn}")
        time.sleep(0.05)


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args) -> None:  # noqa: D401
        pass


def serve(directory: Path) -> tuple[http.server.ThreadingHTTPServer, str]:
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(directory)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


class Collector(http.server.BaseHTTPRequestHandler):
    """Stands in for a service that receives the answers (the optional --endpoint)."""

    bodies: list[tuple[str, str]] = []
    status = 200

    def log_message(self, *args) -> None:
        pass

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "content-type")

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        n = int(self.headers.get("content-length", 0))
        Collector.bodies.append((self.headers.get("content-type", ""), self.rfile.read(n).decode("utf-8")))
        self.send_response(Collector.status)
        self._cors()
        self.end_headers()
        self.wfile.write(b"ok")


# ---------------------------------------------------------------------------------------------
# helpers


def untimed(text: str) -> str:
    """The text with its 'Answers sent: <date and time>' line removed. The time is taken when a button is pressed,
    so two copies made a minute apart differ in that line only."""
    return "\n".join(l for l in text.splitlines() if not l.startswith("Answers sent: "))


def sample_answers(spec: dict) -> tuple[dict, dict]:
    """A full set of answers: the first option of every question, every grid row answered."""
    answers: dict = {}
    others: dict = {}
    for s in spec["sections"]:
        for q in s["questions"]:
            t = q["type"]
            if t in ("text", "paragraph"):
                answers[q["id"]] = f"Answer for {q['id']}"
            elif t == "choice":
                answers[q["id"]] = q["options"][0]
            elif t == "checkbox":
                answers[q["id"]] = [q["options"][0]]
            else:
                answers[q["id"]] = {row: q["cols"][0] for row in q["rows"]}
    return answers, others


class Session:
    """One browser context and page, with a log of console errors and requests."""

    def __init__(self, browser, base: str, width: int = 390, height: int = 844, share: bool = False, state: dict | None = None,
                 reduced: bool = False, clipboard: bool = False, path: str = "/index.html") -> None:
        mobile = width < 700
        self.ctx = browser.new_context(
            viewport={"width": width, "height": height}, device_scale_factor=2 if mobile else 1,
            is_mobile=mobile, has_touch=mobile, accept_downloads=True,
            reduced_motion="reduce" if reduced else "no-preference",
            permissions=["clipboard-read", "clipboard-write"] if clipboard else [],
        )
        if share:
            self.ctx.add_init_script("window.__shared = null; navigator.share = function (d) { window.__shared = d; return Promise.resolve(); };")
        if state is not None:
            self.ctx.add_init_script("if (!sessionStorage.getItem('__seeded')) { sessionStorage.setItem('__seeded', '1'); "
                                     f"localStorage.setItem('questionnaire:twireless:v1', {json.dumps(json.dumps(state))}); }}")
        self.page = self.ctx.new_page()
        self.problems: list[str] = []
        self.requests: list[str] = []
        self.page.on("console", lambda m: self.problems.append(f"console {m.type}: {m.text}") if m.type in ("error", "warning") else None)
        self.page.on("pageerror", lambda e: self.problems.append(f"pageerror: {e}"))
        self.page.on("request", lambda r: self.requests.append(r.url))
        self.base = base
        self.page.goto(base + path)
        until(self.page, "() => document.body.dataset.screen", what="the first screen")

    def close(self) -> None:
        self.ctx.close()

    @property
    def screen(self) -> str:
        return self.page.evaluate("document.body.dataset.screen")

    def go(self, sid: str) -> None:
        self.page.evaluate("id => { location.hash = '#/' + id; }", sid)
        until(self.page, "id => document.body.dataset.screen === id", sid, what=f"screen {sid}")

    def wait_screen(self, sid: str) -> None:
        until(self.page, "id => document.body.dataset.screen === id", sid, timeout=4.0, what=f"screen {sid}")

    def next(self) -> None:
        self.page.click("#foot .btn--primary")

    def back(self) -> None:
        self.page.click("#foot .btn--quiet")

    def questions(self) -> list[dict]:
        return self.page.eval_on_selector_all(
            ".q[data-q]",
            "els => els.map(e => ({id: e.dataset.q, type: [...e.classList].find(c => c.startsWith('q--')).slice(3),"
            " required: !!e.querySelector('.q__title .req'), invalid: e.classList.contains('is-invalid')}))")

    def title_of(self, qid: str) -> str:
        t = self.page.inner_text(f'[data-q="{qid}"] .q__title')
        return t.replace("(required)", "").replace("*", "").strip()

    def option(self, qid: str, text: str):
        return self.page.locator(f'[data-q="{qid}"] label.opt').filter(has=self.page.get_by_text(text, exact=True))

    def raw_text(self) -> str:
        self.page.evaluate("document.querySelector('details.raw').open = true")
        return self.page.input_value("details.raw textarea")

    def saved(self) -> dict:
        return json.loads(self.page.evaluate("localStorage.getItem('questionnaire:twireless:v1')") or "{}")


def answer(s: Session, q: dict, record: dict, prefer: dict | None = None) -> None:
    """Answer one question on screen the way a person would, and note what was chosen."""
    qid, t = q["id"], q["type"]
    sel = f'[data-q="{qid}"]'
    prefer = prefer or {}
    if t in ("text", "paragraph"):
        value = prefer.get(qid) or ("2015" if qid == "opened" else f"Typed answer for {qid}")
        s.page.fill(f"#f-{qid}", value)
        record[qid] = value
    elif t == "choice":
        if qid in prefer:
            s.option(qid, prefer[qid]).click()
            record[qid] = prefer[qid]
        else:
            label = s.page.locator(f"{sel} label.opt").first
            record[qid] = label.locator(".opt__text").inner_text()
            label.click()
    elif t == "checkbox":
        label = s.page.locator(f"{sel} label.opt").first
        record[qid] = [label.locator(".opt__text").inner_text()]
        label.click()
    else:
        rows = s.page.locator(f"{sel} .grid__row")
        got = {}
        for i in range(rows.count()):
            row = rows.nth(i)
            got[row.locator(".grid__label").inner_text()] = row.locator(".pill").first.inner_text()
            row.locator(".pill").first.click()
        record[qid] = got


def fill_screen(s: Session, record: dict, titles: dict, prefer: dict | None = None, optional: bool = False) -> None:
    """Answer every required question on the screen (and optional ones too if asked), including ones that appear
    when a gate question is answered."""
    done: set = set()
    while True:
        pending = [q for q in s.questions() if q["id"] not in done and (q["required"] or optional)]
        if not pending:
            return
        q = pending[0]
        titles[q["id"]] = s.title_of(q["id"])
        answer(s, q, record, prefer)
        done.add(q["id"])


def axe_run(s: Session, axe: Path | None, label: str) -> None:
    if not axe:
        return
    # axe reads colours as they are drawn, so let a screen finish fading in first; half-faded text reads as low contrast
    until(s.page, "() => document.getAnimations().every(a => a.playState !== 'running' && a.playState !== 'pending')", what="animations to finish")
    if not s.page.evaluate("typeof axe !== 'undefined'"):
        s.page.add_script_tag(path=str(axe))
    res = s.page.evaluate("axe.run(document, {runOnly: {type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice']}})")
    bad = [f"{v['id']} ({len(v['nodes'])}): {v['nodes'][0]['html'][:90]}" for v in res["violations"]]
    R.check(f"axe: {label}", not bad, "; ".join(bad))


# ---------------------------------------------------------------------------------------------
# scenarios


def scenario_build(spec: dict) -> None:
    R.section("The build")
    model = bq.app_model(spec)
    kinds = [s["kind"] for s in model["screens"]]
    R.check("18 sections and 2 stops", kinds.count("section") == 18 and kinds.count("stop") == 2, str(kinds))
    R.check("every question is on exactly one screen", sorted(q["id"] for p in model["pages"] for q in p["questions"])
            == sorted(q["id"] for s in spec["sections"] for q in s["questions"]))
    R.check("no team notes reach the page", not any(k in json.dumps(model) for k in ('"unlocks"', '"why"', 'check:')))
    for bad, why in (
        ({"sections": [{"id": "a", "part": "p", "title": "A", "questions": [{"id": "q", "type": "choice", "options": ["x", "y"], "goto": {"x": "@submit"}}]}]},
         "a question outside a gate ending the form"),
    ):
        try:
            bq.app_screens({"sections": [dict(bad["sections"][0])] })
            R.check(f"build refuses {why}", False)
        except ValueError:
            R.check(f"build refuses {why}", True)


def scenario_welcome_and_errors(browser, base: str, axe: Path | None) -> None:
    R.section("Welcome, and leaving required answers empty")
    s = Session(browser, base)
    R.check("starts on the welcome screen", s.screen == "welcome")
    R.check("no header or bottom bar on the welcome screen", s.page.is_hidden("#top") and s.page.is_hidden("#foot"))
    R.check("the intro text from the data file shows", "We’re building the new T Wireless website" in s.page.inner_text("main"))
    axe_run(s, axe, "welcome")
    s.page.click("text=Start")
    s.wait_screen("about")
    R.check("Start goes to the first section", s.screen == "about")
    R.check("header says Part 1 of 3 · Section 1 of 7", "Part 1 of 3 · Section 1 of 7" in s.page.inner_text("#top"), s.page.inner_text("#top"))
    R.check("the progress bar starts at 0", s.page.get_attribute(".meter", "aria-valuenow") == "0")
    s.next()
    s.page.wait_for_timeout(150)
    invalid = [q["id"] for q in s.questions() if q["invalid"]]
    R.check("Next with required questions empty stays put and flags them", s.screen == "about" and invalid == ["name", "role"], str(invalid))
    R.check("each flagged question has a message", s.page.locator(".q__error").count() == 2)
    R.check("focus moves to the first problem", s.page.evaluate("document.activeElement && document.activeElement.id") == "f-name")
    R.check("the problem is announced", poll(s.page, "() => document.getElementById('live').textContent.includes('2 questions need an answer')"),
            s.page.inner_text("#live"))
    axe_run(s, axe, "section with errors")
    s.page.fill("#f-name", "Ali")
    R.check("typing clears that question's message", not [q for q in s.questions() if q["id"] == "name" and q["invalid"]])
    s.option("role", "I work at the store").click()
    R.check("choosing clears the other message", s.page.locator(".q__error").count() == 0)
    s.next()
    s.wait_screen("details")
    R.check("Next moves on when the required answers are there", s.screen == "details")
    R.check("the answers are saved on the device", s.saved().get("answers", {}).get("name") == "Ali")
    s.close()


def scenario_other_and_limits(browser, base: str, spec: dict, axe: Path | None) -> None:
    R.section("Other boxes, 'choose up to', and options that exclude the rest")
    s = Session(browser, base, state={"answers": {}, "others": {}, "furthest": 3})
    s.go("details")
    R.check("the Other box is hidden until Other is chosen", s.page.locator('[data-q="postal"] .opt-other input.input').is_hidden())
    s.option("postal", "Other").click()
    R.check("choosing Other shows the box and focuses it", s.page.locator('[data-q="postal"] .opt-other input.input').is_visible()
            and s.page.evaluate("document.activeElement.getAttribute('aria-label')") == "Other: type your answer")
    # fill the rest of the required questions on this screen except the Other text
    for qid in ("phone", "email", "hours", "holidays"):
        s.page.locator(f'[data-q="{qid}"] label.opt').first.click()
    s.next()
    s.page.wait_for_timeout(150)
    R.check("Other with nothing typed is refused", s.screen == "details" and "Please type your answer in the Other box" in s.page.inner_text('[data-q="postal"] .q__error'))
    s.page.fill('[data-q="postal"] .opt-other input.input', "L6X 1A1")
    R.check("typing in the box clears the message", s.page.locator('[data-q="postal"] .q__error').count() == 0)
    R.check("the typed text is what gets saved", s.saved()["others"]["postal"] == "L6X 1A1" and s.saved()["answers"]["postal"] == OTHER)
    s.next()
    s.wait_screen("finding")
    s.back()
    s.wait_screen("details")
    R.check("going back keeps the Other text", s.page.input_value('[data-q="postal"] .opt-other input.input') == "L6X 1A1")
    s.close()

    s = Session(browser, base, state={"answers": {}, "others": {}, "furthest": 20})
    s.go("social")
    s.option("goals", "More calls and walk-ins").click()
    s.option("goals", "More repair customers").click()
    third = s.page.locator('[data-q="goals"] label.opt').filter(has=s.page.get_by_text("More business customers", exact=True)).locator("input")
    R.check("'Choose up to two': the third option is switched off after two", third.is_disabled())
    R.check("the counter says 2 of 2", "2 of 2 chosen" in s.page.inner_text('[data-q="goals"] .q__count'))
    s.option("goals", "More repair customers").click()
    R.check("unchecking one switches the rest back on", third.is_enabled())
    s.page.locator('[data-q="goals"] .opt-other label.opt').click()
    s.page.fill('[data-q="goals"] .opt-other input.input', "Be easy to find")
    R.check("Other counts toward the limit", s.page.locator('[data-q="goals"] label.opt').first.locator("input").is_disabled() is False
            and third.is_disabled())
    s.go("accessibility")
    s.option("access", "A step-free entrance").click()
    s.option("access", "Seating for customers").click()
    s.option("access", "None of these").click()
    checked = s.page.locator('[data-q="access"] input:checked').count()
    R.check("'None of these' clears the other ticks", checked == 1, f"{checked} checked")
    s.option("access", "Seating for customers").click()
    R.check("ticking something else clears 'None of these'", s.page.locator('[data-q="access"] input:checked').count() == 1
            and s.saved()["answers"]["access"] == ["Seating for customers"])
    s.close()


def scenario_gates(browser, base: str, spec: dict) -> None:
    R.section("Skipping questions that don't apply")
    s = Session(browser, base, state={"answers": {}, "others": {}, "furthest": 5})
    s.go("repairs_q")
    R.check("the repair details are hidden until the gate is answered", s.page.locator('[data-page="repairs_detail"]').count() == 0)
    s.next()
    s.page.wait_for_timeout(100)
    R.check("the gate question itself is required", s.screen == "repairs_q" and s.page.locator('.q.is-invalid').count() == 1)
    s.option("repairs", "Yes, in the store").click()
    R.check("answering Yes shows what you repair", s.page.locator('[data-page="repairs_detail"]').count() == 1
            and "What you repair" in s.page.inner_text('[data-page="repairs_detail"] h2'))
    s.page.locator('[data-q="repair_brands"] label.opt').first.click()
    s.page.locator('[data-q="repair_types"] label.opt').first.click()
    s.page.locator('[data-q="repair_quote"] label.opt').first.click()
    s.option("repairs", "No").click()
    R.check("changing to No hides them again", s.page.locator('[data-page="repairs_detail"]').count() == 0)
    s.option("repairs", "Yes, in the store").click()
    R.check("changing back shows them with the earlier answers still there",
            s.page.locator('[data-q="repair_brands"] input:checked').count() == 1)
    s.option("repairs", "No").click()
    s.next()
    s.wait_screen("biz_q")
    R.check("No to repairs goes straight to Business, no questions asked about repairs", s.screen == "biz_q")
    s.option("biz", "No, we focus on individuals and families").click()
    R.check("No to business hides the business details", s.page.locator('[data-page="biz_detail"]').count() == 0)
    s.next()
    s.wait_screen("gate1")
    R.check("then the stop between Part 1 and Part 2", s.screen == "gate1")
    R.check("a stop shows two choices, Back and no Next", s.page.locator(".stop__go .btn").count() == 2 and s.page.locator("#foot .btn--primary").count() == 0)
    text = s.page.inner_text(".stop")
    R.check("the stop explains how to come back in app words, not the Google Form's", "Edit your response" not in text and "saved on this device" in text, text)
    s.page.locator(".stop__go .btn").nth(1).click()
    s.wait_screen("send")
    R.check("'finish later' goes to the send screen", s.screen == "send")
    export = s.raw_text()
    R.check("the send screen says it is partial", "Here’s what you have so far" in s.page.inner_text("h1"))
    R.check("the text says Part 2 and Part 3 were not started", "Part 1 finished. Part 2 not started. Part 3 not started." in export, export[:300])
    R.check("a hidden question is not in the text", "Which brands do you repair?" not in export)
    R.check("the Carry on button is offered", s.page.get_by_role("button", name="Carry on with Part 2").count() == 1)
    s.page.get_by_role("button", name="Carry on with Part 2").click()
    s.wait_screen("works")
    R.check("Carry on goes to Part 2", s.screen == "works")
    s.back()
    s.wait_screen("gate1")
    s.close()


def scenario_everything(browser, base: str, spec: dict, axe: Path | None) -> dict:
    R.section("All three parts, start to finish")
    s = Session(browser, base, clipboard=True)
    record: dict = {}
    titles: dict = {}
    visited: list[str] = []
    model = bq.app_model(spec)
    kinds = {sc["id"]: sc["kind"] for sc in model["screens"]}
    s.page.click("text=Start")
    s.wait_screen("about")
    progress: list[int] = []
    guard = 0
    while s.screen != "send" and guard < 40:
        guard += 1
        sid = s.screen
        visited.append(sid)
        if kinds[sid] == "stop":
            if sid == "gate1":
                axe_run(s, axe, "a stop screen")
            s.page.locator(".stop__go .btn").first.click()
            until(s.page, "id => document.body.dataset.screen !== id", sid, what=f"leaving {sid}")
            continue
        if sid == "services" or sid == "works":
            pass
        fill_screen(s, record, titles, prefer={"repairs": "Yes, in the store", "biz": "Yes, we help businesses and teams"} if False else None)
        progress.append(int(s.page.get_attribute(".meter", "aria-valuenow")))
        if sid == "sells":
            axe_run(s, axe, "a section with a grid")
        s.next()
        until(s.page, "id => document.body.dataset.screen !== id", sid, what=f"leaving {sid}")
    R.check("walked every screen in order", visited == [sc["id"] for sc in model["screens"]], str(visited))
    R.check("ended on the send screen", s.screen == "send")
    R.check("the progress bar only ever goes up while you go forward", progress == sorted(progress), str(progress))
    R.check("the progress bar is nearly full by the end", progress[-1] >= 90, str(progress))
    R.check("the header says all done", "All done" in s.page.inner_text("#top"))
    R.check("the send screen says everything is done", "That’s everything, Ali. Thank you." in s.page.inner_text("h1"))
    R.check("no console errors, no warnings", not s.problems, str(s.problems))
    R.check("the page asked for nothing but itself", all(u.startswith(base) for u in s.requests) and len(s.requests) == 1, str(s.requests))
    axe_run(s, axe, "send screen")

    export = s.raw_text()
    lines = export.splitlines()
    R.check("the text starts with the form's title and a date", lines[0] == spec["form"]["title"] and lines[1].startswith("Answers sent: "), "\n".join(lines[:3]))
    R.check("it says all three parts are finished", "Part 1 finished. Part 2 finished. Part 3 finished." in export)
    missing = [titles[q] for q in titles if titles[q] not in export]
    R.check("every question that was answered is in the text", not missing, str(missing[:3]))
    wrong = []
    for qid, value in record.items():
        values = [value] if isinstance(value, str) else (value if isinstance(value, list)
                                                       else [k + (" — " if k[-1] in ".?!" else ": ") + v for k, v in value.items()])
        for v in values:
            if v not in export:
                wrong.append(f"{qid}: {v}")
    R.check("every answer given is in the text", not wrong, str(wrong[:3]))
    order = [export.find(titles[q]) for q in titles]
    R.check("the questions are in the order of the form", order == sorted(order))
    R.check("nothing says 'Needs an answer' on the review list", s.page.locator(".rq__flag").count() == 0)
    answered = int(export.split("Questions answered: ")[1].split(" of ")[0])
    R.check("the count of answered questions matches", answered == len(titles), f"{answered} vs {len(titles)}")

    # the three send buttons
    s.page.get_by_role("button", name="Copy my answers").click()
    s.page.wait_for_timeout(200)
    clip = s.page.evaluate("navigator.clipboard.readText()")
    R.check("Copy puts exactly that text on the clipboard", untimed(clip) == untimed(export) and clip.startswith(spec["form"]["title"]))
    R.check("and says so", "Copied" in s.page.inner_text(".send__status"))
    with s.page.expect_download() as dl:
        s.page.get_by_role("button", name="Save as a file").click()
    saved_file = Path(dl.value.path()).read_text(encoding="utf-8")
    R.check("Save downloads a file with the same text", untimed(saved_file) == untimed(export) and dl.value.suggested_filename == "twireless-website-answers.txt", dl.value.suggested_filename)
    R.check("no console errors after copying and saving", not s.problems, str(s.problems))
    s.close()
    return {"record": record, "titles": titles, "export": export}


def scenario_share_and_endpoint(browser, base: str, spec: dict) -> None:
    R.section("Share sheet and the optional send address")
    answers, others = sample_answers(spec)
    s = Session(browser, base, share=True, state={"answers": answers, "others": others, "furthest": 20})
    s.go("send")
    R.check("with a share sheet available, Send my answers is the main button",
            s.page.locator(".send__actions .btn--primary").inner_text().strip() == "Send my answers")
    s.page.get_by_role("button", name="Send my answers").click()
    s.page.wait_for_timeout(200)
    shared = s.page.evaluate("window.__shared")
    R.check("it hands the title and the text to the share sheet", shared and shared["title"] == spec["form"]["title"] and "Which best describes you?" in shared["text"])
    R.check("and thanks, without saying it was delivered", "If you sent the message" in s.page.inner_text(".send__status"))
    s.close()

    s = Session(browser, base, share=True, state={"answers": answers, "others": others, "furthest": 20})
    s.page.evaluate("() => { navigator.share = function () { return Promise.reject(new DOMException('cancelled', 'AbortError')); }; }")
    s.go("send")
    s.page.get_by_role("button", name="Send my answers").click()
    s.page.wait_for_timeout(200)
    R.check("cancelling the share sheet says nothing was sent", "Nothing was sent" in s.page.inner_text(".send__status"))
    s.close()

    # a build with a send address
    Collector.bodies.clear()
    Collector.status = 200
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Collector)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    endpoint = f"http://127.0.0.1:{srv.server_address[1]}/collect"
    with tempfile.TemporaryDirectory() as tmp:
        bq.build_app(spec, Path(tmp) / "index.html", endpoint=endpoint)
        web, ebase = serve(Path(tmp))
        s = Session(browser, ebase, state={"answers": answers, "others": others, "furthest": 20})
        s.page.on("console", lambda m: None)
        s.go("send")
        R.check("with an endpoint, Send my answers posts to it", s.page.locator(".send__actions .btn--primary").inner_text().strip() == "Send my answers")
        s.page.get_by_role("button", name="Send my answers").click()
        until(s.page, "() => { const t = document.querySelector('.send__status').textContent; return t.length > 0 && !/Sending/.test(t); }", what="the send result")
        R.check("the endpoint got one POST", len(Collector.bodies) == 1, str(len(Collector.bodies)))
        if Collector.bodies:
            ctype, body = Collector.bodies[0]
            data = json.loads(body)
            R.check("as JSON with the answers by id and the readable text",
                    data["form"] == "twireless" and data["complete"] is True and data["answers"]["name"] == "Answer for name" and "Which best describes you?" in data["text"])
            R.check("sent as text/plain, so no pre-flight request is needed", ctype.startswith("text/plain"), ctype)
        R.check("success is shown", "Sent. Thank you, Ali." in s.page.inner_text(".send__status"), s.page.inner_text(".send__status"))
        R.check("the saved state records it", s.saved().get("sent"))
        Collector.status = 500
        s.page.get_by_role("button", name="Send my answers").click()
        until(s.page, "() => /didn’t go through/.test(document.querySelector('.send__status').textContent)", what="the failure message")
        R.check("a failing endpoint shows a clear message and opens the text to copy", s.page.locator("details.raw[open]").count() == 1)
        csp = s.page.get_attribute('meta[http-equiv="Content-Security-Policy"]', "content")
        R.check("the page's policy allows only that address", f"connect-src {endpoint.rsplit('/', 1)[0]}" in csp, csp)
        s.close()
        web.shutdown()
    srv.shutdown()


def scenario_resume_and_history(browser, base: str, spec: dict) -> None:
    R.section("Closing the page and coming back; the Back gesture; the Sections menu")
    s = Session(browser, base)
    s.page.click("text=Start")
    s.wait_screen("about")
    s.page.fill("#f-name", "Ali")
    s.option("role", "I work at the store").click()
    s.next()
    s.wait_screen("details")
    s.page.reload()
    until(s.page, "() => document.body.dataset.screen", what="a screen")
    R.check("reloading keeps you on the same screen", s.screen == "details")
    s.go("welcome")
    R.check("the welcome screen offers to carry on", s.page.get_by_role("button", name="Carry on where you left off").count() == 1)
    s.page.get_by_role("button", name="Carry on where you left off").click()
    s.wait_screen("details")
    s.back()
    s.wait_screen("about")
    R.check("Back brings back what you typed", s.page.input_value("#f-name") == "Ali" and s.page.locator('[data-q="role"] input:checked').count() == 1)
    s.page.go_back()
    s.page.wait_for_timeout(200)
    R.check("the phone's own Back goes to the screen before", s.screen in ("details", "welcome"), s.screen)
    # a new tab on the same device
    page2 = s.ctx.new_page()
    page2.goto(base + "/index.html")
    until(page2, "() => document.body.dataset.screen", what="a screen")
    R.check("a fresh visit on the same device finds the saved answers", page2.get_by_role("button", name="Carry on where you left off").count() == 1)
    page2.goto(base + "/index.html#/gate1")
    until(page2, "() => document.body.dataset.screen", what="a screen")
    R.check("typing a later screen's address is not a way to skip ahead", page2.evaluate("document.body.dataset.screen") in ("details", "about"), page2.evaluate("document.body.dataset.screen"))
    page2.goto(base + "/index.html#/nonsense")
    until(page2, "() => document.body.dataset.screen", what="a screen")
    R.check("an address that means nothing goes to the welcome screen", page2.evaluate("document.body.dataset.screen") == "welcome")
    page2.close()

    s.go("details")
    s.page.click(".top__menu")
    R.check("the menu opens as a dialog with every section", s.page.locator('.menu__panel[role="dialog"]').count() == 1 and s.page.locator(".toc__item").count() == 19)
    R.check("the section you are on is marked", s.page.locator('.toc__item[aria-current="step"]').inner_text().strip() == "Your store’s details")
    R.check("sections you haven't reached are disabled", s.page.locator(".toc__item:disabled").count() == 17 and s.page.locator(".toc__item.is-done").count() == 1)
    R.check("focus is inside the menu", s.page.evaluate("!!document.activeElement.closest('.menu')"))
    for _ in range(25):
        s.page.keyboard.press("Tab")
    R.check("Tab stays inside the menu", s.page.evaluate("!!document.activeElement.closest('.menu')"))
    s.page.keyboard.press("Escape")
    R.check("Escape closes it and puts focus back on the button", s.page.locator(".menu").is_hidden() and s.page.evaluate("document.activeElement.className") == "top__menu")
    s.page.click(".top__menu")
    s.page.locator(".toc__item", has_text="About you").click()
    s.wait_screen("about")
    R.check("choosing a section goes there", s.screen == "about" and s.page.locator(".menu").is_hidden())

    s.go("welcome")
    R.check("going back to the welcome screen hides the header and bottom bar again", s.page.is_hidden("#top") and s.page.is_hidden("#foot"))
    erase = s.page.locator(".welcome__go .btn--quiet")  # its words change on the first tap, so find it by place, not by name
    erase.click()
    R.check("the first tap on Erase only asks", "Tap again" in erase.inner_text() and s.saved().get("answers", {}).get("name") == "Ali")
    erase.click()
    s.page.wait_for_timeout(200)
    R.check("a second tap erases everything", s.page.evaluate("localStorage.getItem('questionnaire:twireless:v1')") is None)
    R.check("and the screen shows a fresh Start straight away", s.page.get_by_role("button", name="Start").count() == 1
            and s.page.get_by_role("button", name="Carry on where you left off").count() == 0)
    s.page.click("text=Start")
    s.wait_screen("about")
    R.check("a fresh start has the old answers gone", s.page.input_value("#f-name") == "" and s.page.locator('[data-q="role"] input:checked').count() == 0)
    s.close()


def scenario_editing(browser, base: str, spec: dict) -> None:
    R.section("Editing from the review list, and carrying on after 'finish later'")
    answers, others = sample_answers(spec)
    model = bq.app_model(spec)
    ids = [sc["id"] for sc in model["screens"]]
    s = Session(browser, base, state={"answers": answers, "others": others, "furthest": len(ids)})
    s.go("send")
    s.page.locator(".rsec", has_text="About you").locator(".rsec__edit").click()
    s.wait_screen("about")
    R.check("Edit goes to that section", s.screen == "about")
    R.check("and the bottom button then takes you back to the review",
            s.page.locator("#foot .btn--primary").inner_text().strip() == "Back to my answers")
    s.page.fill("#f-name", "Ali Khan")
    s.page.click("#foot .btn--primary")
    s.wait_screen("send")
    R.check("pressing it returns to the review, not to the next section", s.screen == "send")
    R.check("the review shows the change", "Ali Khan" in s.page.inner_text(".review"))
    R.check("and everything is still marked finished", "That’s everything" in s.page.inner_text("h1") and s.saved()["furthest"] == len(ids))
    s.go("details")
    R.check("once back on the review, sections go back to Next", s.page.locator("#foot .btn--primary").inner_text().strip() == "Next")
    s.go("send")
    s.page.locator(".rsec", has_text="About you").locator(".rsec__edit").click()
    s.wait_screen("about")
    s.page.fill("#f-name", "")
    s.page.click("#foot .btn--primary")
    s.page.wait_for_timeout(150)
    R.check("while editing, a required answer left empty still stops you", s.screen == "about" and s.page.locator(".q.is-invalid").count() == 1)
    s.close()

    # finish later, change your mind, carry on: the menu must not offer to send half of Part 2
    s = Session(browser, base, state={"answers": {"name": "Ali", "role": "I work at the store"}, "others": {}, "furthest": ids.index("gate1")})
    s.go("gate1")
    s.page.locator(".stop__go .btn").nth(1).click()
    s.wait_screen("send")
    R.check("'finish later' opens the send screen", s.screen == "send")
    s.back()
    s.wait_screen("gate1")
    s.page.locator(".stop__go .btn").first.click()
    s.wait_screen(ids[ids.index("gate1") + 1])
    s.page.click(".top__menu")
    R.check("after 'keep going' the menu no longer offers to send", s.page.locator('.toc__item[data-go="send"]').is_disabled())
    s.page.keyboard.press("Escape")
    s.page.evaluate("() => { location.hash = '#/send'; }")
    s.page.wait_for_timeout(250)
    R.check("and typing the address of the send screen doesn't get you there", s.screen != "send", s.screen)
    s.close()

    # the send screen's Carry on, from a stop and from the middle of a part
    s = Session(browser, base, state={"answers": {"name": "Ali", "role": "I work at the store"}, "others": {}, "furthest": ids.index("gate1"), "ended": True})
    s.go("send")
    R.check("from a stop, Carry on says which part comes next",
            s.page.get_by_role("button", name="Carry on with Part 2").count() == 1)
    s.page.get_by_role("button", name="Carry on with Part 2").click()
    s.wait_screen(ids[ids.index("gate1") + 1])
    R.check("and goes to its first section", s.screen == ids[ids.index("gate1") + 1])
    s.close()
    mid = ids.index("offers")
    s = Session(browser, base, state={"answers": {"name": "Ali", "role": "I work at the store"}, "others": {}, "furthest": mid, "ended": True})
    s.go("send")
    R.check("from the middle of a part, Carry on resumes that section instead of skipping it",
            s.page.get_by_role("button", name="Carry on where you left off").count() == 1)
    s.page.get_by_role("button", name="Carry on where you left off").click()
    s.wait_screen("offers")
    R.check("and lands on it", s.screen == "offers")
    s.close()


def scenario_script_cannot_run(browser, base: str) -> None:
    R.section("When the script can't run")
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, java_script_enabled=False)
    page = ctx.new_page()
    page.goto(base + "/index.html")
    text = page.inner_text("body")
    R.check("with JavaScript off, the page says it needs JavaScript", "needs JavaScript" in text, text[:120])
    R.check("and doesn't also claim to be loading", "Loading the questions" not in text, text[:120])
    ctx.close()

    # a browser that starts the script but can't finish it: make the script fail on its first line
    for reduced in (False, True):
        ctx = browser.new_context(viewport={"width": 390, "height": 844}, reduced_motion="reduce" if reduced else "no-preference")
        page = ctx.new_page()

        def broken(route):
            resp = route.fetch()
            body = resp.text().replace("(function () {\n  'use strict';", "(function () {\n  'use strict'; throw new Error('simulated failure');", 1)
            route.fulfill(response=resp, body=body)

        page.route("**/index.html", broken)
        page.goto(base + "/index.html")
        opacity = lambda: float(page.evaluate("getComputedStyle(document.querySelector('.boot__late')).opacity"))
        early = opacity()
        shown = poll(page, "() => parseFloat(getComputedStyle(document.querySelector('.boot__late')).opacity) >= 0.99", timeout=9.0)
        how = "with reduced motion" if reduced else "normally"
        R.check(f"{how}: a script that fails shows 'Loading' first and no apology yet", early < 0.5 and "Loading the questions" in page.inner_text("main"))
        R.check(f"{how}: after a few seconds it says the browser can't run the page", shown and "taking longer than it should" in page.inner_text("main"))
        ctx.close()


def scenario_storage_blocked(browser, base: str) -> None:
    R.section("A browser that can't save")
    ctx = browser.new_context(viewport={"width": 390, "height": 844})
    ctx.add_init_script("Object.defineProperty(window, 'localStorage', { get() { throw new Error('blocked'); } });")
    page = ctx.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(base + "/index.html")
    until(page, "() => document.body.dataset.screen", what="a screen")
    R.check("the page still works", page.get_by_role("button", name="Start").count() == 1 and not errors, str(errors))
    R.check("and says it can't save", "can’t save your answers" in page.inner_text("main"))
    page.click("text=Start")
    until(page, "() => document.body.dataset.screen === 'about'", what="about")
    page.fill("#f-name", "Ali")
    R.check("typing still works with no storage", not errors and page.input_value("#f-name") == "Ali", str(errors))
    ctx.close()


def scenario_layout(browser, base: str, spec: dict, axe: Path | None) -> None:
    R.section("Widths from 320 to 1280, and tap sizes")
    answers, others = sample_answers(spec)
    model = bq.app_model(spec)
    ids = ["welcome"] + [sc["id"] for sc in model["screens"]] + ["send"]
    # A phone's browser widens its layout to fit anything that sticks out, so the page's own idea of its width can't
    # be trusted: compare with the width the screen really has (W), and fail if the page has grown past it.
    js = """(W) => {
      const w = W, bad = [];
      document.querySelectorAll('body *').forEach(e => {
        if (e.closest('.sr-only') || e.classList.contains('sr-only') || e.closest('[hidden]')) return;
        const r = e.getBoundingClientRect();
        if (r.width && (r.right > w + 1 || r.left < -1)) bad.push(e.tagName + '.' + e.className);
      });
      const small = [];
      document.querySelectorAll('button, .opt, .pill, input[type=text], textarea, summary').forEach(e => {
        if (e.closest('[hidden]') || !e.offsetParent && getComputedStyle(e).position !== 'fixed') return;
        const r = e.getBoundingClientRect();
        if (r.height && (r.height < 43.5 || (e.tagName === 'BUTTON' && r.width < 43.5))) small.push(e.tagName + '.' + e.className + ' ' + Math.round(r.width) + 'x' + Math.round(r.height));
      });
      return { scrollW: Math.max(document.documentElement.scrollWidth, window.innerWidth), w, bad: bad.slice(0, 4), small: small.slice(0, 4),
               top: document.querySelector('#top').hidden ? 0 : Math.round(document.querySelector('#top').getBoundingClientRect().height),
               line: document.querySelector('#top').hidden ? 0 : Math.round(document.querySelector('.top__where b').getBoundingClientRect().height) };
    }"""
    for width in (320, 360, 390, 430, 600, 768, 980, 1280):
        s = Session(browser, base, width=width, height=900 if width >= 700 else 844, reduced=True,
                    state={"answers": answers, "others": others, "furthest": 20})
        wide, small, tall = [], [], []
        for sid in ids:
            s.go(sid)
            res = s.page.evaluate(js, width)
            if res["scrollW"] > res["w"] or res["bad"]:
                wide.append(f"{sid}: {res['scrollW']}>{res['w']} {res['bad']}")
            if res["small"]:
                small.append(f"{sid}: {res['small']}")
            if res["top"] > 84:
                tall.append(f"{sid}: header {res['top']}px")
            if res["line"] > 24:
                tall.append(f"{sid}: the 'Part 1 of 3 · Section 1 of 7' line wraps ({res['line']}px tall)")
        R.check(f"{width}px: nothing sticks out sideways on any of the {len(ids)} screens", not wide, "; ".join(wide[:3]))
        R.check(f"{width}px: every button, answer and box is at least 44 px tall", not small, "; ".join(small[:3]))
        R.check(f"{width}px: the sticky header stays slim", not tall, "; ".join(tall[:3]))
        R.check(f"{width}px: no console problems", not s.problems, str(s.problems[:2]))
        if width in (390, 980):
            s.go("sells")
            axe_run(s, axe, f"{width}px, a section with a grid")
            s.go("send")
            axe_run(s, axe, f"{width}px, the send screen")
            s.go("about")
            s.page.click(".top__menu")
            axe_run(s, axe, f"{width}px, the Sections menu")
        s.close()


def scenario_motion_and_names(browser, base: str, spec: dict) -> None:
    R.section("Motion, headings and names")
    s = Session(browser, base, reduced=True)
    s.page.click("text=Start")
    s.wait_screen("about")
    R.check("with 'reduce motion' on, no screen slides in", "go-forward" not in (s.page.get_attribute(".card", "class") or ""))
    R.check("each screen has one h1 and it takes focus", s.page.locator("h1").count() == 1 and s.page.evaluate("document.activeElement.tagName") == "H1")
    R.check("the browser tab title names the section", s.page.title().startswith("About you"), s.page.title())
    R.check("the live region announces the new section",
            poll(s.page, "() => document.getElementById('live').textContent === 'Part 1, section 1 of 7: About you'"),
            s.page.inner_text("#live"))
    s.close()
    s = Session(browser, base, reduced=False)
    s.page.click("text=Start")
    s.wait_screen("about")
    R.check("by default the next screen slides in", "go-forward" in (s.page.get_attribute(".card", "class") or ""))
    s.close()
    # the first frame of the slide is the widest the page ever gets; hold it there with the safeguard against overflow removed
    s = Session(browser, base, width=320, reduced=False)
    s.page.add_style_tag(content=".main { overflow-x: visible !important; }")
    s.page.click("text=Start")
    s.wait_screen("about")
    worst = s.page.evaluate("() => { document.getAnimations().forEach(a => { a.pause(); a.currentTime = 0; }); "
                            "return [document.documentElement.scrollWidth, window.innerWidth, document.getAnimations().length]; }")
    R.check("a screen sliding in never makes the page wider than the phone, even without the clip safeguard",
            worst[2] >= 1 and max(worst[0], worst[1]) <= 320, str(worst))
    s.close()


# ---------------------------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=bq.HERE / "twireless.questionnaire.json")
    ap.add_argument("--axe", type=Path, help="path to axe-core's axe.min.js, to also run the accessibility rules")
    ap.add_argument("--only", help="run only the scenarios whose name contains this word")
    ns = ap.parse_args()
    if ns.axe and not ns.axe.exists():
        print(f"axe-core not found at {ns.axe}")
        return 2
    spec = bq.load(ns.data)
    problems = bq.validate(spec)
    if problems:
        print("The data file has problems:", *problems, sep="\n  - ")
        return 3
    with tempfile.TemporaryDirectory() as tmp:
        bq.build_app(spec, Path(tmp) / "index.html")
        srv, base = serve(Path(tmp))
        with sync_playwright() as p:
            browser = p.chromium.launch()
            wanted = lambda name: not ns.only or ns.only in name  # noqa: E731
            if wanted("build"):
                scenario_build(spec)
            if wanted("welcome"):
                scenario_welcome_and_errors(browser, base, ns.axe)
            if wanted("other"):
                scenario_other_and_limits(browser, base, spec, ns.axe)
            if wanted("gates"):
                scenario_gates(browser, base, spec)
            if wanted("everything"):
                scenario_everything(browser, base, spec, ns.axe)
            if wanted("share"):
                scenario_share_and_endpoint(browser, base, spec)
            if wanted("resume"):
                scenario_resume_and_history(browser, base, spec)
            if wanted("edit"):
                scenario_editing(browser, base, spec)
            if wanted("script"):
                scenario_script_cannot_run(browser, base)
            if wanted("storage"):
                scenario_storage_blocked(browser, base)
            if wanted("layout"):
                scenario_layout(browser, base, spec, ns.axe)
            if wanted("motion"):
                scenario_motion_and_names(browser, base, spec)
            browser.close()
        srv.shutdown()
    print(f"\n{R.total - R.failed} of {R.total} checks passed" + ("" if not R.failed else f", {R.failed} FAILED"))
    return 1 if R.failed else 0


if __name__ == "__main__":
    sys.exit(main())
