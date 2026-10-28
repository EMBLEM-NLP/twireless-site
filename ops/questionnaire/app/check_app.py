#!/usr/bin/env python3
"""End-to-end check of the questionnaire web app, in a headless Chromium.

    python3 ops/questionnaire/app/check_app.py                 # build to a temp folder and test that
    python3 ops/questionnaire/app/check_app.py --axe axe.min.js  # also run axe-core (see below)

It builds the app from the data file, serves it on localhost and then does what a person does: taps through
every screen, skips them all, leaves answers empty, picks "No" where a question skips others, finishes a part
and stops, closes the page and comes back, presses Copy, Save and Share, and rotates through phone, tablet and
desktop widths. It also rehearses sending the answers to a receiver (a stand-in on this computer, then a stand-in for
Google's Apps Script address and its redirect) and runs receive_answers.gs against what the page really posts.
It fails (exit 1) if any check fails.

It builds the page twice. The first is the data file as written, where (apart from the choices at the stops)
nothing is required, because the questionnaire is a first approach to a business that never asked for it. The
second is the same questions with every one of them required, which is how the checks on required answers run.

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
import re
import sys
import tempfile
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import build_questionnaire as bq  # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402

OTHER = "__other__"

# Questions with choices that have no Other box on purpose: each is a plain yes, no or not sure to a single fact, or a
# scale that already says "It varies", so a list can't miss anything. Every other question with choices must have an
# Other box, so the store can write its own answer, unless its answer decides what is asked next (Google Forms can't
# combine Other with a jump).
CLOSED = ("repair_quote", "tbooth", "google_profile", "rating", "facebook", "logos", "maker_logos", "bell_approval",
          "reply", "photos", "staff_photos", "recycle")


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
    delay = 0.0
    reply = b'{"ok":true}'  # what the real receiver says when it has kept the answers
    ctype = "application/json; charset=utf-8"

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
        time.sleep(Collector.delay)
        self.send_response(Collector.status)
        self._cors()
        self.send_header("Content-Type", Collector.ctype)
        self.end_headers()
        self.wfile.write(Collector.reply)


# ---------------------------------------------------------------------------------------------
# helpers


def untimed(text: str) -> str:
    """The text with its 'Answers as of: <date and time>' line removed. The time is taken when a button is pressed,
    so two copies made a minute apart differ in that line only."""
    return "\n".join(l for l in text.splitlines() if not l.startswith("Answers as of: "))


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
                 reduced: bool = False, clipboard: bool = False, path: str = "/index.html", ignore_https_errors: bool = False) -> None:
        mobile = width < 700
        self.ctx = browser.new_context(
            viewport={"width": width, "height": height}, device_scale_factor=2 if mobile else 1,
            is_mobile=mobile, has_touch=mobile, accept_downloads=True,
            reduced_motion="reduce" if reduced else "no-preference",
            permissions=["clipboard-read", "clipboard-write"] if clipboard else [],
            ignore_https_errors=ignore_https_errors,
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
# what the checks need to know about the questionnaire, worked out from the data file


def strict_variant(spec: dict) -> dict:
    """The same questions with every one of them required, as a stricter client might want. The questionnaire itself makes
    nothing required (it is a first approach to a business that never asked for it), so this is how the checks on
    required answers are exercised."""
    out = json.loads(json.dumps(spec))
    for s in out["sections"]:
        for q in s["questions"]:
            q["required"] = True
    return out


def find_question(spec: dict, test) -> dict:
    for s in spec["sections"]:
        for q in s["questions"]:
            if test(q):
                return q
    raise LookupError("no question matches")


class Known:
    """What the scenarios and fixes need to know about the questionnaire, worked out from the data file."""

    def __init__(self, spec: dict) -> None:
        self.spec = spec
        self.answers, self.others = sample_answers(spec)
        self.model = bq.app_model(spec)
        screens = self.model["screens"]
        self.ids = [sc["id"] for sc in screens]
        self.kinds = {sc["id"]: sc["kind"] for sc in screens}
        self.titles = {sc["id"]: sc["title"] for sc in screens}
        self.first = self.ids[0]
        self.second = self.ids[1]
        self.sections = [sc for sc in screens if sc["kind"] == "section"]
        self.stops = [sc["id"] for sc in screens if sc["kind"] == "stop"]
        self.part_sections = {p["id"]: [sc for sc in self.sections if sc["part"] == p["id"]] for p in self.model["parts"]}
        page_of = {q["id"]: pg["id"] for pg in self.model["pages"] for q in pg["questions"]}
        screen_of = {pid: sc["id"] for sc in screens for pid in sc["pages"]}
        self.screen_for = lambda qid: screen_of[page_of[qid]]
        self.part_of = lambda sid: next(p for p in self.model["parts"] if p["id"] == next(sc["part"] for sc in screens if sc["id"] == sid))
        self.complete = {"answers": self.answers, "others": self.others, "furthest": len(self.ids)}
        self.questions = [q for s in spec["sections"] for q in s["questions"]]

    def screen_ids_before(self, sid: str) -> set:
        """The ids of the questions on every screen before this one."""
        end = self.ids.index(sid)
        return {q["id"] for sc in self.model["screens"][:end] for pg in self.model["pages"] if pg["id"] in sc["pages"] for q in pg["questions"]}


def start(s: "Session") -> None:
    s.page.get_by_role("button", name="Start", exact=True).click()


# ---------------------------------------------------------------------------------------------
# scenarios


def scenario_build(k: Known) -> None:
    R.section("The build")
    spec, model = k.spec, k.model
    kinds = [s["kind"] for s in model["screens"]]
    R.check("19 sections and 3 stops", kinds.count("section") == 19 and kinds.count("stop") == 3, str(kinds))
    R.check("every question is on exactly one screen", sorted(q["id"] for p in model["pages"] for q in p["questions"])
            == sorted(q["id"] for s in spec["sections"] for q in s["questions"]))
    R.check("no team notes reach the page", not any(key in json.dumps(model) for key in ('"unlocks"', '"why"', 'check:')))
    contact = spec["client"]["contact"]
    chrome = json.dumps({key: model[key] for key in ("title", "answersTitle", "intro", "byline", "done", "partial", "client")})
    R.check("the contact's name is not in the page's own words or in its data", contact not in chrome)
    R.check("the data check accepts the data file", not bq.validate(spec), str(bq.validate(spec)))

    def refused(change) -> list:
        copy = json.loads(json.dumps(spec))
        change(copy)
        return bq.validate(copy)

    R.check("the data check refuses a drafts link that isn't https",
            refused(lambda c: c["form"]["app"].update(preview={"label": "See the drafts", "url": "http://example.com/"})))
    R.check("and one with no label", refused(lambda c: c["form"]["app"].update(preview={"label": " ", "url": "https://example.com/"})))
    R.check("and an unknown word under form.app", refused(lambda c: c["form"]["app"].update(surprise="x")))
    consumer = "https://script.google.com/macros/s/AKfycbxAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA/exec"
    workspace = "https://script.google.com/a/macros/example.com/s/AKfycbxAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA/exec"
    for ok_url in (consumer, workspace, ""):
        R.check(f"the data check accepts a receiver address: {ok_url[:48] or '(none)'}", not refused(lambda c, u=ok_url: c["form"]["app"].update(endpoint=u)))
    for bad_url, why in (
        (consumer[:-5] + "/dev", "a /dev address, which only the script's owner can use"),
        (consumer.replace("https", "http"), "one that isn't https"),
        (consumer.replace("script.google.com", "example.com"), "another host"),
        (consumer.replace("AKfycbxAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "short"), "one with no real id"),
        (consumer + "?x=1", "one with a query"),
        (consumer + "/", "one with a trailing slash"),
        ("https://script.google.com/macros/s/AKfycbxAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA/exec#a b", "one with a space"),
        (7, "a number"),
    ):
        R.check(f"the data check refuses {why}", refused(lambda c, u=bad_url: c["form"]["app"].update(endpoint=u)))
    R.check("the /dev mistake gets a hint", any("/exec" in m for m in refused(lambda c: c["form"]["app"].update(endpoint=consumer[:-5] + "/dev"))))
    R.check("an address asked for on the command line wins, and an empty one means none",
            bq.endpoint_of(spec, "https://x.test/y") == "https://x.test/y" and bq.endpoint_of(spec, "") == "")
    with_data = json.loads(json.dumps(spec))
    with_data["form"]["app"]["endpoint"] = consumer
    R.check("otherwise the data file's address is used", bq.endpoint_of(with_data, None) == consumer)
    plain = json.loads(json.dumps(spec))
    plain["form"]["app"].pop("endpoint", None)
    R.check("and no address when neither is set", bq.endpoint_of(plain, None) == "")
    with tempfile.TemporaryDirectory() as tmp:
        bq.build_app(with_data, Path(tmp) / "a.html")
        bq.build_app(with_data, Path(tmp) / "b.html", endpoint="")
        a_html, b_html = ((Path(tmp) / n).read_text(encoding="utf-8") for n in ("a.html", "b.html"))
        R.check("a build uses the data file's address, and its policy reaches only Google's two",
                consumer in a_html and "connect-src https://script.google.com https://script.googleusercontent.com;" in bq.content_security_policy(consumer)
                and bq.esc(bq.content_security_policy(consumer)) in a_html)
        R.check("a build with an empty address has no address and a policy that reaches nothing",
                consumer not in b_html and "connect-src 'none';" in bq.content_security_policy("") and bq.esc(bq.content_security_policy("")) in b_html)
    R.check("the data file's address never reaches the Google Form's script or its preview",
            consumer not in bq.script_spec(with_data) and "endpoint" not in bq.script_spec(with_data))
    shipped = bq.APP_OUT
    if shipped.exists():
        page = shipped.read_text(encoding="utf-8")
        want = bq.endpoint_of(spec)
        R.check("the page that is published matches the data file's address (rebuild it if not)",
                bq.esc(bq.content_security_policy(want)) in page and (want in page if want else "script.google.com" not in page),
                want or "no address set")
    for bad, why in (
        ({"sections": [{"id": "a", "part": "p", "title": "A", "questions": [{"id": "q", "type": "choice", "options": ["x", "y"], "goto": {"x": "@submit"}}]}]},
         "a question outside a gate ending the form"),
    ):
        try:
            bq.app_screens({"sections": [dict(bad["sections"][0])]})
            R.check(f"build refuses {why}", False)
        except ValueError:
            R.check(f"build refuses {why}", True)


def scenario_cold_call(browser, base: str, k: Known, axe: Path | None) -> None:
    R.section("A first approach: nothing is required, and nobody is asked who they are")
    spec = k.spec
    gates = {s["questions"][0]["id"] for s in spec["sections"] if s.get("gate")}
    required = {q["id"] for q in k.questions if q["required"]}
    R.check("the only required questions are the choices at the stops", required == gates, str(sorted(required - gates)))
    names = [q["id"] for q in k.questions if q["id"] == "name"
             or re.search(r"\byour (full |first |last )?name\b", q["title"], re.I)
             or (q["type"] == "text" and re.search(r"\bname\b", q["title"], re.I))]
    R.check("no question asks for the person's own name", not names, str(names))
    contact = spec["client"]["contact"]
    quoting = sorted(q["id"] for q in k.questions
                     if re.search(rf"\b{contact}\b", " ".join([q["title"], q.get("help", "")] + q.get("options", [])), re.I))
    R.check(f"{contact}'s name is only in the question that quotes the drafts' Visit page", quoting == ["visit_contact"], str(quoting))

    s = Session(browser, base)
    welcome = s.page.inner_text("main")
    R.check("the welcome screen says who we are", spec["client"]["agency"] in welcome)
    R.check("it says nobody asked for this", re.search(r"nobody asked|didn.t ask", welcome, re.I) is not None, welcome[:160])
    R.check("it says every question is optional", "optional" in welcome.lower())
    R.check("it offers to take the drafts down", re.search(r"taken down|take (them|the drafts) down", welcome, re.I) is not None)
    declining = [q for q in k.questions if any(re.search(r"take the drafts down", o, re.I) for o in q.get("options", []))]
    R.check("and one of the questions is a way to say so", len(declining) == 1 and not declining[0]["required"], str([q["id"] for q in declining]))
    R.check("it doesn't greet anyone by name", contact not in welcome)
    preview = spec["form"]["app"]["preview"]
    link = s.page.get_by_role("link", name=preview["label"])
    R.check("it links to the drafts", link.count() == 1 and link.get_attribute("href") == preview["url"], str(link.count()))
    R.check("the link opens in a new tab and doesn't hand over the page",
            link.get_attribute("target") == "_blank" and "noopener" in (link.get_attribute("rel") or "") and "noreferrer" in (link.get_attribute("rel") or ""))
    R.check("and tells a screen reader that it does", "opens in a new tab" in (link.inner_text() or ""))
    meta = s.page.evaluate("""() => ({ site: document.querySelector('meta[property="og:site_name"]').content,
        title: document.querySelector('meta[property="og:title"]').content,
        desc: document.querySelector('meta[name="description"]').content,
        ogdesc: document.querySelector('meta[property="og:description"]').content })""")
    summary = bq.form_words(spec)["summary"]
    R.check("a link preview names the agency, not the store", meta["site"] == spec["client"]["agency"], meta["site"])
    R.check("and gives the data file's title and summary", meta["title"] == spec["form"]["title"] and meta["desc"] == summary == meta["ogdesc"]
            and "{minutes}" not in summary and spec["parts"][0]["minutes"].split(",")[0] in summary, str(meta))
    axe_run(s, axe, "welcome")
    start(s)
    s.wait_screen(k.first)
    R.check("nothing is marked as required, and no screen says it needs an answer",
            s.page.locator(".req").count() == 0 and "needs an answer" not in s.page.inner_text(".card"))
    nxt = s.page.locator("#foot .btn--primary")
    R.check("with nothing answered, the button says Skip", nxt.inner_text().strip() == "Skip")
    s.page.locator('[data-q="postal"] label.opt').first.click()
    R.check("once something is answered it says Next", nxt.inner_text().strip() == "Next")
    s.page.locator('[data-q="postal"] .q__clear').click()
    R.check("and Skip again when the choice is cleared", nxt.inner_text().strip() == "Skip")
    s.option("postal", "Other").click()
    s.next()
    s.page.wait_for_timeout(150)
    error = s.page.inner_text('[data-q="postal"] .q__error') if s.page.locator('[data-q="postal"] .q__error').count() else ""
    R.check("an optional question left on Other with nothing typed says how to get out of it",
            s.screen == k.first and "Other box" in error and "clear your choice" in error, error)
    s.page.locator('[data-q="postal"] .q__clear').click()
    s.next()
    s.wait_screen(k.second)
    R.check("clearing the choice lets the section be skipped", s.screen == k.second)

    guard = 0
    while s.screen != "send" and guard < 60:
        guard += 1
        sid = s.screen
        if k.kinds[sid] == "stop":
            s.page.locator(".stop__go .btn").first.click()
        else:
            s.next()
        until(s.page, "id => document.body.dataset.screen !== id", sid, what=f"leaving {sid}")
    R.check("every screen can be skipped, all the way to the end", s.screen == "send", s.screen)
    R.check("with nothing answered the send screen says so",
            "You haven’t answered anything yet." in s.page.inner_text("h1") and "Nothing has been sent" in s.page.inner_text(".send"))
    R.check("and has nothing to send, copy or save",
            all(s.page.get_by_role("button", name=name).count() == 0 for name in ("Send my answers", "Copy my answers", "Save as a file")))
    R.check("the header says so too", "Nothing answered yet" in s.page.inner_text("#top"), s.page.inner_text("#top"))
    axe_run(s, axe, "the send screen with nothing answered")
    s.page.get_by_role("button", name="Go to the first question").click()
    s.wait_screen(k.first)
    R.check("Go to the first question goes back to the start", s.screen == k.first)
    R.check("no console errors, no warnings", not s.problems, str(s.problems))
    s.close()

    s = Session(browser, base, state=dict(k.complete))
    s.go(k.stops[0])
    stop_text = s.page.inner_text("main")
    s.go("send")
    send_text = s.page.inner_text(".send")
    R.check("a stop and the send screen don't name anyone", contact not in stop_text and contact not in send_text)
    s.close()


def scenario_welcome_and_errors(browser, base: str, k: Known, axe: Path | None) -> None:
    R.section("Welcome, and leaving required answers empty (every question made required)")
    s = Session(browser, base)
    R.check("starts on the welcome screen", s.screen == "welcome")
    R.check("no header or bottom bar on the welcome screen", s.page.is_hidden("#top") and s.page.is_hidden("#foot"))
    R.check("the intro text from the data file shows", k.model["intro"][0] in s.page.inner_text("main"))
    start(s)
    s.wait_screen(k.first)
    R.check("Start goes to the first section", s.screen == k.first)
    part = k.model["parts"][0]
    where = f"Part 1 of {len(k.model['parts'])} · Section 1 of {len(k.part_sections[part['id']])}"
    R.check(f"header says {where}", where in s.page.inner_text("#top"), s.page.inner_text("#top"))
    R.check("the progress bar starts at 0", s.page.get_attribute(".meter", "aria-valuenow") == "0")
    here = [q["id"] for sc in k.model["screens"][:1] for pg in k.model["pages"] if pg["id"] in sc["pages"] for q in pg["questions"]]
    s.next()
    s.page.wait_for_timeout(150)
    invalid = [q["id"] for q in s.questions() if q["invalid"]]
    R.check("Next with required questions empty stays put and flags them", s.screen == k.first and invalid == here, str(invalid))
    R.check("each flagged question has a message", s.page.locator(".q__error").count() == len(here))
    R.check("focus moves to the first problem",
            s.page.evaluate("(q) => !!document.activeElement.closest('[data-q=\"' + q + '\"]')", here[0]))
    R.check("the problem is announced",
            poll(s.page, "(n) => document.getElementById('live').textContent.includes(n + ' questions need an answer')", len(here)),
            s.page.inner_text("#live"))
    axe_run(s, axe, "section with errors")
    first_label = s.page.locator(f'[data-q="{here[0]}"] label.opt').first
    chosen = first_label.locator(".opt__text").inner_text()
    first_label.click()
    R.check("choosing an answer clears that question's message", not [q for q in s.questions() if q["id"] == here[0] and q["invalid"]])
    for qid in here[1:]:
        s.page.locator(f'[data-q="{qid}"] label.opt').first.click()
    R.check("answering the rest clears the other messages", s.page.locator(".q__error").count() == 0)
    s.next()
    s.wait_screen(k.second)
    R.check("Next moves on when the required answers are there", s.screen == k.second)
    R.check("the answers are saved on the device", s.saved().get("answers", {}).get(here[0]) == chosen)
    s.close()


def scenario_other_and_limits(browser, base: str, k: Known, axe: Path | None) -> None:
    R.section("Other boxes, 'choose up to', and options that exclude the rest")
    box = '[data-q="postal"] .opt-other input.input'
    s = Session(browser, base, state={"answers": {}, "others": {}, "furthest": 3})
    s.go(k.first)
    R.check("the Other box is hidden until Other is chosen", s.page.locator(box).is_hidden())
    s.option("postal", "Other").click()
    R.check("choosing Other shows the box and focuses it", s.page.locator(box).is_visible()
            and s.page.evaluate("document.activeElement.getAttribute('aria-label')") == "Other: type your answer")
    s.next()
    s.page.wait_for_timeout(150)
    R.check("Other with nothing typed is refused", s.screen == k.first and "Please type your answer in the Other box" in s.page.inner_text('[data-q="postal"] .q__error'))
    s.page.fill(box, "L6X 1A1")
    R.check("typing in the box clears the message", s.page.locator('[data-q="postal"] .q__error').count() == 0)
    R.check("the typed text is what gets saved", s.saved()["others"]["postal"] == "L6X 1A1" and s.saved()["answers"]["postal"] == OTHER)
    s.next()
    s.wait_screen(k.second)
    s.back()
    s.wait_screen(k.first)
    R.check("going back keeps the Other text", s.page.input_value(box) == "L6X 1A1")
    s.close()

    s = Session(browser, base, state=dict(k.complete, answers={key: v for key, v in k.answers.items() if key != "goals"}))
    s.go(k.screen_for("goals"))
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
    s.close()

    # every question with an option that should clear the rest ("None of these", "Nothing special", ...)
    excl_qs = [q for q in k.questions if (q.get("app") or {}).get("exclusive")]
    R.check("there are questions with an option that excludes the rest", len(excl_qs) >= 4, str([q["id"] for q in excl_qs]))
    blank = {q["id"] for q in excl_qs}
    s = Session(browser, base, state=dict(k.complete, answers={key: v for key, v in k.answers.items() if key not in blank}))
    for q in excl_qs:
        exclusive = q["app"]["exclusive"][0]
        plain = [o for o in q["options"] if o not in q["app"]["exclusive"]]
        s.go(k.screen_for(q["id"]))
        s.option(q["id"], plain[0]).click()
        s.option(q["id"], plain[1]).click()
        s.option(q["id"], exclusive).click()
        sel = f'[data-q="{q["id"]}"] input:checked'
        R.check(f"{q['id']}: '{exclusive}' clears the other ticks", s.page.locator(sel).count() == 1 and s.saved()["answers"][q["id"]] == [exclusive],
                f"{s.page.locator(sel).count()} checked")
        s.option(q["id"], plain[0]).click()
        R.check(f"{q['id']}: ticking something else clears '{exclusive}'", s.saved()["answers"][q["id"]] == [plain[0]])
    s.close()


def scenario_custom_answers(browser, base: str, k: Known, axe: Path | None) -> None:
    R.section("A custom answer: an Other box wherever the choices might miss what the store does")
    choosy = [q for q in k.questions if q["type"] in ("choice", "checkbox") and not q.get("goto")]
    ids = {q["id"] for q in choosy}
    missing = [q["id"] for q in choosy if not q.get("other") and q["id"] not in CLOSED]
    stale = [i for i in CLOSED if i not in ids or find_question(k.spec, lambda q, i=i: q["id"] == i).get("other")]
    R.check("every question with choices has an Other box, unless it is on the closed list", not missing, str(missing))
    R.check("and nothing on the closed list has one, or has gone from the questionnaire", not stale, str(stale))
    R.check("the questions that decide what comes next have none, because Google Forms can't combine Other with a jump",
            not [q["id"] for q in k.questions if q.get("goto") and q.get("other")])

    withother = [q for q in choosy if q.get("other")]
    s = Session(browser, base, state=dict(k.complete))
    typed: dict = {}
    problems: list[str] = []
    for q in withother:
        qid = q["id"]
        sel = f'[data-q="{qid}"]'
        box = f"{sel} .opt-other input.input"
        s.go(k.screen_for(qid))
        if s.page.locator(box).is_visible():
            problems.append(f"{qid}: the box is open before Other is chosen")
        s.page.locator(f"{sel} .opt-other label.opt").click()
        if not s.page.locator(box).is_visible():
            problems.append(f"{qid}: no box after choosing Other")
            continue
        if s.page.evaluate("document.activeElement.getAttribute('aria-label')") != "Other: type your answer":
            problems.append(f"{qid}: the box doesn't take the focus")
        typed[qid] = f"Custom answer for {qid}"
        s.page.fill(box, typed[qid])
        saved = s.saved()
        a = saved["answers"].get(qid)
        picked = a == OTHER if q["type"] == "choice" else (isinstance(a, list) and OTHER in a)
        if not picked or saved["others"].get(qid) != typed[qid]:
            problems.append(f"{qid}: saved {a!r} and {saved['others'].get(qid)!r}")
    R.check(f"on all {len(withother)} of them, choosing Other opens a box, takes the focus and saves what is typed", not problems, "; ".join(problems[:3]))
    axe_run(s, axe, "a screen with an Other box open")
    s.go("send")
    export = s.raw_text()
    lost = [qid for qid, text in typed.items() if f"Other: {text}" not in export]
    R.check("every custom answer is in the text that gets sent", not lost and len(typed) == len(withother), str(lost[:3]))
    s.close()

    # with an option that excludes the rest ("None of these"), Other never stays ticked beside it, and what was typed is kept
    s = Session(browser, base, state=dict(k.complete))
    bad: list[str] = []
    for q in [q for q in withother if (q.get("app") or {}).get("exclusive")]:
        qid, ex = q["id"], q["app"]["exclusive"][0]
        sel = f'[data-q="{qid}"]'
        box = f"{sel} .opt-other input.input"
        s.go(k.screen_for(qid))
        s.page.locator(f"{sel} .opt-other label.opt").click()
        s.page.fill(box, "Something else")
        s.option(qid, ex).click()
        a = s.saved()["answers"][qid]
        if a != [ex] or s.page.locator(box).is_visible():
            bad.append(f"{qid}: '{ex}' left Other behind ({a})")
        s.page.locator(f"{sel} .opt-other label.opt").click()
        a = s.saved()["answers"][qid]
        if a != [OTHER] or s.page.input_value(box) != "Something else" or s.saved()["others"].get(qid) != "Something else":
            bad.append(f"{qid}: Other didn't clear '{ex}' or lost its text ({a})")
    R.check("Other and an option that excludes the rest never stay ticked together, and the text typed is kept", not bad, "; ".join(bad[:3]))
    s.close()


def scenario_required_stop(browser, base: str, k: Known) -> None:
    R.section("A question that decides what is asked next, made required")
    s = Session(browser, base, state={"answers": {key: v for key, v in k.answers.items() if key in k.screen_ids_before("repairs_q")},
                                      "others": {}, "furthest": k.ids.index("repairs_q")})
    s.go("repairs_q")
    s.next()
    s.page.wait_for_timeout(100)
    R.check("the question itself is required", s.screen == "repairs_q" and s.page.locator(".q.is-invalid").count() == 1)
    s.close()


def scenario_gates(browser, base: str, k: Known) -> None:
    R.section("Skipping questions that don't apply, and the stops between the parts")
    # Part 2: the person has answered everything before Repairs, so the only blanks are the ones this scenario leaves
    s = Session(browser, base, state={"answers": {key: v for key, v in k.answers.items() if key in k.screen_ids_before("repairs_q")},
                                      "others": {}, "furthest": k.ids.index("repairs_q")})
    s.go("repairs_q")
    R.check("the repair details are hidden until the question is answered", s.page.locator('[data-page="repairs_detail"]').count() == 0)
    R.check("with nothing answered the section can be skipped", s.page.locator("#foot .btn--primary").inner_text().strip() == "Skip")
    s.option("repairs", "Yes, in the store").click()
    R.check("answering Yes shows what you repair", s.page.locator('[data-page="repairs_detail"]').count() == 1
            and "What you repair" in s.page.inner_text('[data-page="repairs_detail"] h2'))
    R.check("and the app doesn't repeat the data file's 'skip this section' line, which is for the Google Form",
            "Skip this section" not in s.page.inner_text('[data-page="repairs_detail"]'))
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
    s.wait_screen("works")
    R.check("and then on to how the store works", s.screen == "works")
    s.close()

    # the stop between Part 1 and Part 2
    gate = k.stops[0]
    after = k.ids[k.ids.index(gate) + 1]
    s = Session(browser, base, state={"answers": {key: v for key, v in k.answers.items() if key in k.screen_ids_before(gate)},
                                      "others": {}, "furthest": k.ids.index(gate)})
    s.go(gate)
    R.check("a stop shows two choices, Back and no Next", s.page.locator(".stop__go .btn").count() == 2 and s.page.locator("#foot .btn--primary").count() == 0)
    text = s.page.inner_text(".stop")
    R.check("the stop explains how to come back in app words, not the Google Form's", "Edit your response" not in text and "saved on this device" in text, text)
    s.page.locator(".stop__go .btn").nth(1).click()
    s.wait_screen("send")
    R.check("'finish later' goes to the send screen", s.screen == "send")
    export = s.raw_text()
    R.check("the send screen says it is partial", "Here’s what you have so far" in s.page.inner_text("h1"))
    status = ". ".join(["Part 1 finished"] + [f"Part {p['n']} not started" for p in k.model["parts"][1:]]) + "."
    R.check("the text says the later parts were not started", status in export, export[:300])
    R.check("a hidden question is not in the text", "Which brands do you repair?" not in export)
    part2 = k.part_of(after)
    R.check("the Carry on button is offered", s.page.get_by_role("button", name=f"Carry on with Part {part2['n']}").count() == 1)
    s.page.get_by_role("button", name=f"Carry on with Part {part2['n']}").click()
    s.wait_screen(after)
    R.check("Carry on goes to Part 2", s.screen == after)
    s.back()
    s.wait_screen(gate)
    s.close()


def scenario_everything(browser, base: str, k: Known, axe: Path | None, label: str, optional: bool) -> dict:
    R.section(f"All four parts, start to finish ({label})")
    spec, model = k.spec, k.model
    s = Session(browser, base, clipboard=True)
    record: dict = {}
    titles: dict = {}
    visited: list[str] = []
    grid_screen = k.screen_for(find_question(spec, lambda q: q["type"] == "grid")["id"])
    start(s)
    s.wait_screen(k.first)
    progress: list[int] = []
    guard = 0
    while s.screen != "send" and guard < 60:
        guard += 1
        sid = s.screen
        visited.append(sid)
        if k.kinds[sid] == "stop":
            if sid == k.stops[0]:
                axe_run(s, axe, "a stop screen")
            s.page.locator(".stop__go .btn").first.click()
            until(s.page, "id => document.body.dataset.screen !== id", sid, what=f"leaving {sid}")
            continue
        fill_screen(s, record, titles, optional=optional)
        progress.append(int(s.page.get_attribute(".meter", "aria-valuenow")))
        if sid == grid_screen:
            axe_run(s, axe, "a section with a grid")
        s.next()
        until(s.page, "id => document.body.dataset.screen !== id", sid, what=f"leaving {sid}")
    R.check("walked every screen in order", visited == k.ids, str(visited))
    R.check("ended on the send screen", s.screen == "send")
    R.check("the progress bar only ever goes up while you go forward", progress == sorted(progress), str(progress))
    R.check("the progress bar is nearly full by the end", progress[-1] >= 90, str(progress))
    R.check("the header says all done", "All done" in s.page.inner_text("#top"))
    R.check("the send screen says everything is done", "That’s everything. Thank you." in s.page.inner_text("h1"))
    R.check("no console errors, no warnings", not s.problems, str(s.problems))
    R.check("the page asked for nothing but itself", all(u.startswith(base) for u in s.requests) and len(s.requests) == 1, str(s.requests))
    axe_run(s, axe, "send screen")

    export = s.raw_text()
    lines = export.splitlines()
    R.check("the text starts with its own title, not the invitation's, and a date",
            lines[0] == model["answersTitle"] != spec["form"]["title"] and lines[1].startswith("Answers as of: "), "\n".join(lines[:3]))
    R.check("it says every part is finished", " ".join(f"Part {p['n']} finished." for p in model["parts"]) in export)
    missing = [titles[q] for q in titles if titles[q] not in export]
    R.check("every question that was answered is in the text", not missing, str(missing[:3]))
    wrong = []
    for qid, value in record.items():
        values = [value] if isinstance(value, str) else (value if isinstance(value, list)
                                                       else [key + (" — " if key[-1] in ".?!" else ": ") + v for key, v in value.items()])
        for v in values:
            if v not in export:
                wrong.append(f"{qid}: {v}")
    R.check("every answer given is in the text", not wrong, str(wrong[:3]))
    order = [export.find(titles[q]) for q in titles]
    R.check("the questions are in the order of the form", order == sorted(order))
    R.check("nothing says 'Needs an answer' on the review list", s.page.locator(".rq__flag").count() == 0)
    answered = int(export.split("Questions answered: ")[1].split(" of ")[0])
    R.check("the count of answered questions matches", answered == len(titles), f"{answered} vs {len(titles)}")
    if optional:
        R.check("every question in the form was answered", len(titles) == len(k.questions) - len(k.stops), f"{len(titles)} vs {len(k.questions) - len(k.stops)}")

    # the three send buttons
    s.page.get_by_role("button", name="Copy my answers").click()
    s.page.wait_for_timeout(200)
    clip = s.page.evaluate("navigator.clipboard.readText()")
    R.check("Copy puts exactly that text on the clipboard", untimed(clip) == untimed(export) and clip.startswith(model["answersTitle"]))
    R.check("and says so", "Copied" in s.page.inner_text(".send__status"))
    with s.page.expect_download() as dl:
        s.page.get_by_role("button", name="Save as a file").click()
    saved_file = Path(dl.value.path()).read_text(encoding="utf-8")
    R.check("Save downloads a file with the same text", untimed(saved_file) == untimed(export) and dl.value.suggested_filename == "twireless-website-answers.txt", dl.value.suggested_filename)
    R.check("no console errors after copying and saving", not s.problems, str(s.problems))
    s.close()
    return {"record": record, "titles": titles, "export": export}


def scenario_share_and_endpoint(browser, base: str, k: Known) -> None:
    R.section("Share sheet and the optional send address")
    spec, model = k.spec, k.model
    first_title = spec["sections"][0]["questions"][0]["title"]
    text_q = find_question(spec, lambda q: q["type"] in ("text", "paragraph"))["id"]
    s = Session(browser, base, share=True, state=dict(k.complete))
    s.go("send")
    R.check("with a share sheet available, Send my answers is the main button",
            s.page.locator(".send__actions .btn--primary").inner_text().strip() == "Send my answers")
    s.page.get_by_role("button", name="Send my answers").click()
    s.page.wait_for_timeout(200)
    shared = s.page.evaluate("window.__shared")
    R.check("it hands the answers' title and the text to the share sheet", shared and shared["title"] == model["answersTitle"] and first_title in shared["text"])
    R.check("and that title is not the invitation's headline", shared["title"] != spec["form"]["title"] and not shared["text"].startswith(spec["form"]["title"]))
    R.check("and thanks, without saying it was delivered", "If you sent the message" in s.page.inner_text(".send__status"))
    s.close()

    s = Session(browser, base, share=True, state=dict(k.complete))
    s.page.evaluate("() => { navigator.share = function () { return Promise.reject(new DOMException('cancelled', 'AbortError')); }; }")
    s.go("send")
    s.page.get_by_role("button", name="Send my answers").click()
    s.page.wait_for_timeout(200)
    R.check("cancelling the share sheet says nothing was sent", "Nothing was sent" in s.page.inner_text(".send__status"))
    s.close()

    # a build with a send address
    Collector.bodies.clear()
    Collector.status = 200
    Collector.delay = 0.0
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Collector)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    endpoint = f"http://127.0.0.1:{srv.server_address[1]}/collect"
    with tempfile.TemporaryDirectory() as tmp:
        bq.build_app(spec, Path(tmp) / "index.html", endpoint=endpoint)
        web, ebase = serve(Path(tmp))
        s = Session(browser, ebase, state=dict(k.complete))
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
                    data["form"] == "twireless" and data["complete"] is True and data["answers"][text_q] == f"Answer for {text_q}" and first_title in data["text"])
            R.check("sent as text/plain, so no pre-flight request is needed", ctype.startswith("text/plain"), ctype)
        R.check("success is shown", "Sent. Thank you." in s.page.inner_text(".send__status"), s.page.inner_text(".send__status"))
        R.check("the saved state records it", s.saved().get("sent"))
        how = s.page.inner_text(".send__how")
        R.check("the send screen says what goes, and what doesn't",
                spec["client"]["agency"] in how and "aren’t part of it" in how and "who sent you this link" not in how, how)

        # two quick taps are one message
        Collector.bodies.clear()
        Collector.delay = 0.6
        s.page.get_by_role("button", name="Send my answers").dblclick()
        until(s.page, "() => /Sent/.test(document.querySelector('.send__status').textContent)", timeout=8.0, what="the second send result")
        s.page.wait_for_timeout(900)
        R.check("a double tap sends one message, not two", len(Collector.bodies) == 1, str(len(Collector.bodies)))
        Collector.delay = 0.0

        Collector.status = 500
        s.page.get_by_role("button", name="Send my answers").click()
        until(s.page, "() => /didn’t go through/.test(document.querySelector('.send__status').textContent)", what="the failure message")
        R.check("a failing endpoint shows a clear message and opens the text to copy", s.page.locator("details.raw[open]").count() == 1)
        csp = s.page.get_attribute('meta[http-equiv="Content-Security-Policy"]', "content")
        R.check("the page's policy allows only that address", f"connect-src {endpoint.rsplit('/', 1)[0]}" in csp, csp)
        s.close()

        # a good status is not enough: the receiver has to say yes. A sign-in page, an error page or a plain "ok" can all
        # come back with status 200 and not have kept anything.
        for what, reply, ctype in (
            ("plain text", b"ok", "text/plain"),
            ("a sign-in page", b"<!doctype html><title>Sign in</title><p>Sign in to continue.", "text/html; charset=utf-8"),
            ("JSON that says no", b'{"ok":false,"error":"busy"}', "application/json"),
            ("JSON that is not an answer", b"[true]", "application/json"),
            ("JSON null", b"null", "application/json"),
            ("an empty reply", b"", "application/json"),
            ("ok as the text \"true\"", b'{"ok":"true"}', "application/json"),
        ):
            Collector.status, Collector.reply, Collector.ctype = 200, reply, ctype
            s = Session(browser, ebase, state=dict(k.complete))
            s.page.on("console", lambda m: None)
            s.go("send")
            s.page.get_by_role("button", name="Send my answers").click()
            until(s.page, "() => { const t = document.querySelector('.send__status').textContent; return t.length > 0 && !/Sending/.test(t); }", what="the send result")
            status = s.page.inner_text(".send__status")
            R.check(f"not taken as sent when the reply is {what}", "didn’t go through" in status and "Sent." not in status, status)
            R.check(f"and not remembered as sent: {what}", not s.saved().get("sent"))
            R.check(f"and the text is opened so it can be copied: {what}", s.page.locator("details.raw[open]").count() == 1)
            s.close()
        Collector.status, Collector.reply, Collector.ctype = 200, b'{"ok":true,"note":"extra keys are fine"}', "application/json"
        s = Session(browser, ebase, state=dict(k.complete))
        s.page.on("console", lambda m: None)
        s.go("send")
        s.page.get_by_role("button", name="Send my answers").click()
        until(s.page, "() => { const t = document.querySelector('.send__status').textContent; return t.length > 0 && !/Sending/.test(t); }", what="the send result")
        R.check("a yes with other keys beside it is still a yes", "Sent. Thank you." in s.page.inner_text(".send__status"))
        s.close()
        Collector.reply, Collector.ctype = b'{"ok":true}', "application/json; charset=utf-8"

        # a question left on Other with nothing typed is not a finished answer: say so, don't claim "complete"
        Collector.status = 200
        Collector.bodies.clear()
        s = Session(browser, ebase, state=dict(k.complete, answers=dict(k.answers, postal=OTHER)))
        s.go("send")
        R.check("with a half-answered question the send screen says so", "so far" in s.page.inner_text("h1") and s.page.locator(".send__needs").count() == 1)
        s.page.get_by_role("button", name="Send my answers").click()
        until(s.page, "() => { const t = document.querySelector('.send__status').textContent; return t.length > 0 && !/Sending/.test(t); }", what="the send result")
        R.check("and what is posted says it is not complete", len(Collector.bodies) == 1 and json.loads(Collector.bodies[0][1])["complete"] is False)
        s.close()
        web.shutdown()
    srv.shutdown()


GOOGLE_EXEC = "https://script.google.com/macros/s/AKfycbxTESTTESTTESTTESTTESTTESTTESTTESTTESTTEST/exec"
GOOGLE_ECHO = "https://script.googleusercontent.com/macros/echo?user_content_key=abc123&lib=xyz"
CORS = {"Access-Control-Allow-Origin": "*"}


class GoogleStandIn(http.server.BaseHTTPRequestHandler):
    """Stands in for script.google.com (the receiver's address) and script.googleusercontent.com (where an Apps Script web
    app's reply is served), over HTTPS from this computer. It answers the way Apps Script web apps are documented and
    widely used: a POST to /exec is answered with a redirect to the second address, and a GET there returns what the
    script returned, as JSON. It has no doOptions, so a pre-flight request is refused, as Google would refuse it."""

    seen: list[tuple] = []
    mode = "redirect"  # redirect | direct | forbidden | hangup
    redirect_cors = True  # the redirect itself carries Access-Control-Allow-Origin
    echo_cors = True
    echo_body = b'{"ok":true}'
    echo_ctype = "application/json; charset=utf-8"
    redirect_to = GOOGLE_ECHO

    def log_message(self, *args) -> None:
        pass

    def _send(self, status: int, headers: dict, body: bytes = b"") -> None:
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _note(self, method: str, body: str = "") -> None:
        GoogleStandIn.seen.append(((self.headers.get("Host") or "").split(":")[0], method, self.path, self.headers.get("Content-Type", ""), body))

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._note("OPTIONS")
        self._send(405, {"Content-Type": "text/html"}, b"Method Not Allowed")

    def do_POST(self) -> None:  # noqa: N802
        self._note("POST", self.rfile.read(int(self.headers.get("Content-Length", 0))).decode("utf-8"))
        cls = GoogleStandIn
        if cls.mode == "hangup":
            self.close_connection = True
            return
        if cls.mode == "forbidden":
            self._send(403, {"Content-Type": "text/html", **CORS}, b"Forbidden")
        elif cls.mode == "direct":
            self._send(200, {"Content-Type": cls.echo_ctype, **CORS}, cls.echo_body)
        else:
            self._send(302, {"Location": cls.redirect_to, **(CORS if cls.redirect_cors else {})})

    def do_GET(self) -> None:  # noqa: N802
        self._note("GET")
        cls = GoogleStandIn
        self._send(200, {"Content-Type": cls.echo_ctype, **(CORS if cls.echo_cors else {})}, cls.echo_body)


def scenario_google_endpoint(p, k: Known) -> None:
    """The way the answers are meant to travel: a POST to script.google.com, which answers with a redirect to
    script.googleusercontent.com, which answers with the receiver's JSON. Google itself is not contacted: a Chromium of
    its own is pointed at a stand-in on this computer (with a certificate made for the test) that answers in the shape
    Apps Script web apps are known to use. So this shows how the page and the browser cope with that shape, including the
    page's content security policy and the browser's cross-origin rules, and with each way it can go wrong. It does not
    show that Google really answers this way."""
    import ssl
    import subprocess

    R.section("The Google path: a POST, a redirect to a second address, and nowhere else")
    spec = k.spec
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        hosts = ("script.google.com", "script.googleusercontent.com", "evil.example")
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2", "-subj", f"/CN={hosts[0]}",
                        "-keyout", str(tmp_path / "key.pem"), "-out", str(tmp_path / "cert.pem"),
                        "-addext", "subjectAltName=" + ",".join(f"DNS:{h}" for h in hosts)], check=True, capture_output=True)
        google = http.server.ThreadingHTTPServer(("127.0.0.1", 0), GoogleStandIn)
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.load_cert_chain(tmp_path / "cert.pem", tmp_path / "key.pem")
        google.socket = tls.wrap_socket(google.socket, server_side=True)
        threading.Thread(target=google.serve_forever, daemon=True).start()
        port = google.server_address[1]
        (tmp_path / "page").mkdir()
        bq.build_app(spec, tmp_path / "page" / "index.html", endpoint=GOOGLE_EXEC)
        web, base = serve(tmp_path / "page")
        # The browser's own proxy is a dead end except for the three stand-in hosts, so nothing here can reach the real Google.
        chromium = p.chromium.launch(proxy={"server": "http://127.0.0.1:9", "bypass": ",".join(hosts) + ",127.0.0.1"},
                                     args=["--host-resolver-rules=" + ", ".join(f"MAP {h} 127.0.0.1:{port}" for h in hosts)])

        def rehearse(**settings):
            """One press of Send, with the stand-in set up as given. Returns what the page said and what the stand-in saw."""
            defaults = dict(mode="redirect", redirect_cors=True, echo_cors=True, echo_body=b'{"ok":true}',
                            echo_ctype="application/json; charset=utf-8", redirect_to=GOOGLE_ECHO)
            for key, value in {**defaults, **settings}.items():
                setattr(GoogleStandIn, key, value)
            GoogleStandIn.seen = []
            s = Session(chromium, base, state=dict(k.complete), ignore_https_errors=True)
            s.go("send")
            s.page.get_by_role("button", name="Send my answers").click()
            until(s.page, "() => { const t = document.querySelector('.send__status').textContent; return t.length > 0 && !/Sending/.test(t); }",
                  timeout=10.0, what="the send result")
            out = (s.page.inner_text(".send__status"), list(GoogleStandIn.seen), bool(s.saved().get("sent")))
            s.close()
            return out

        try:
            status, seen, sent = rehearse()
            posts = [x for x in seen if x[1] == "POST"]
            R.check("through Google's redirect the page reads the receiver's yes, says Sent and remembers it", "Sent. Thank you." in status and sent, status)
            R.check("it made one POST to the first address, as text/plain",
                    len(posts) == 1 and posts[0][0] == "script.google.com" and posts[0][3].lower().startswith("text/plain"), str(seen)[:300])
            R.check("then one GET to the second address", [(x[0], x[1]) for x in seen if x[1] == "GET"] == [("script.googleusercontent.com", "GET")], str(seen)[:300])
            R.check("and no pre-flight request, which Google would refuse", not any(x[1] == "OPTIONS" for x in seen), str(seen)[:300])
            R.check("what it posted is this questionnaire's answers", bool(posts) and json.loads(posts[0][4])["form"] == spec["client"]["slug"])
            R.check("nothing else was contacted", {x[0] for x in seen} <= {"script.google.com", "script.googleusercontent.com"}, str(seen)[:300])

            cases = (
                ("an answer straight from the first address, with no redirect", dict(mode="direct"), True),
                ("a redirect that ends in a JSON yes with other keys", dict(echo_body=b'{"ok":true,"note":"x"}'), True),
                ("a redirect whose final answer has no cross-origin permission", dict(echo_cors=False), False),
                ("a redirect to a sign-in page", dict(echo_body=b"<!doctype html><title>Sign in</title>", echo_ctype="text/html; charset=utf-8"), False),
                ("a redirect to a JSON no", dict(echo_body=b'{"ok":false,"error":"busy"}'), False),
                ("a first address that answers 403", dict(mode="forbidden"), False),
                ("a first address that hangs up", dict(mode="hangup"), False),
                ("a redirect to an address outside Google's two", dict(redirect_to="https://evil.example/echo"), False),
            )
            for what, settings, should_send in cases:
                status, seen, sent = rehearse(**settings)
                if should_send:
                    R.check(f"{what}: sent", "Sent. Thank you." in status and sent, status)
                else:
                    R.check(f"{what}: not taken as sent", "didn’t go through" in status and "Sent." not in status and not sent, status)
                if "outside" in what:
                    R.check("the page's policy stopped the request before it left", all(x[0] != "evil.example" for x in seen), str(seen)[:300])
            status, seen, sent = rehearse(redirect_cors=False)
            print(f"  note  with no cross-origin permission on the redirect itself, Chromium {'sends' if sent else 'does not send'} the answers on: {status[:40]}")
        finally:
            chromium.close()
            web.shutdown()
            google.shutdown()


def real_message(browser, k: Known, state: dict) -> str:
    """The message the page really posts when Send is pressed, caught by a stand-in receiver."""
    Collector.bodies.clear()
    Collector.status, Collector.delay = 200, 0.0
    Collector.reply, Collector.ctype = b'{"ok":true}', "application/json; charset=utf-8"
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Collector)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            bq.build_app(k.spec, Path(tmp) / "index.html", endpoint=f"http://127.0.0.1:{srv.server_address[1]}/collect")
            web, base = serve(Path(tmp))
            s = Session(browser, base, state=state)
            s.go("send")
            s.page.get_by_role("button", name="Send my answers").click()
            until(s.page, "() => /Sent|didn/.test(document.querySelector('.send__status').textContent)", what="the send result")
            s.close()
            web.shutdown()
    finally:
        srv.shutdown()
    return Collector.bodies[0][1] if Collector.bodies else ""


def scenario_receiver(browser, k: Known) -> None:
    R.section("The receiving script (receive_answers.gs), against a stand-in for Google's services")
    import subprocess

    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp) / "data.json"
        data.write_text(json.dumps(k.spec), encoding="utf-8")
        for what, state in (("every question answered", dict(k.complete)),
                            ("one answered and the rest skipped", dict(k.complete, answers={"postal": "L6X 0G3"}))):
            body = real_message(browser, k, state)
            R.check(f"the page posted a message ({what})", body.startswith("{"), body[:80])
            msg = Path(tmp) / "message.json"
            msg.write_text(body, encoding="utf-8")
            r = subprocess.run(["node", str(bq.HERE / "check_receiver.js"), str(bq.RECEIVER), str(data), "--body", str(msg)],
                               capture_output=True, text=True)
            R.check(f"the script keeps that message and passes its own checks ({what})",
                    r.returncode == 0 and "including a message made by the real page" in r.stdout, (r.stdout + r.stderr).strip()[-400:])


def scenario_resume_and_history(browser, base: str, k: Known) -> None:
    R.section("Closing the page and coming back; the Back gesture; the Sections menu")
    first, second = k.first, k.second
    s = Session(browser, base)
    start(s)
    s.wait_screen(first)
    s.option("postal", "L6X 0G3").click()
    s.next()
    s.wait_screen(second)
    s.page.reload()
    until(s.page, "() => document.body.dataset.screen", what="a screen")
    R.check("reloading keeps you on the same screen", s.screen == second)
    s.go("welcome")
    R.check("the welcome screen offers to carry on", s.page.get_by_role("button", name="Carry on where you left off").count() == 1)
    s.page.get_by_role("button", name="Carry on where you left off").click()
    s.wait_screen(second)
    s.back()
    s.wait_screen(first)
    R.check("Back brings back what you chose", s.page.locator('[data-q="postal"] input:checked').count() == 1
            and s.page.locator('[data-q="postal"] input:checked').get_attribute("value") == "L6X 0G3")
    s.page.go_back()
    s.page.wait_for_timeout(200)
    R.check("the phone's own Back goes to the screen before", s.screen in (second, "welcome"), s.screen)
    # a new tab on the same device
    page2 = s.ctx.new_page()
    page2.goto(base + "/index.html")
    until(page2, "() => document.body.dataset.screen", what="a screen")
    R.check("a fresh visit on the same device finds the saved answers", page2.get_by_role("button", name="Carry on where you left off").count() == 1)
    page2.goto(base + "/index.html#/" + k.stops[0])
    until(page2, "() => document.body.dataset.screen", what="a screen")
    R.check("typing a later screen's address is not a way to skip ahead", page2.evaluate("document.body.dataset.screen") in (first, second), page2.evaluate("document.body.dataset.screen"))
    page2.goto(base + "/index.html#/nonsense")
    until(page2, "() => document.body.dataset.screen", what="a screen")
    R.check("an address that means nothing goes to the welcome screen", page2.evaluate("document.body.dataset.screen") == "welcome")
    page2.close()

    s.go(second)
    s.page.click(".top__menu")
    n = len(k.sections)
    R.check("the menu opens as a dialog with every section", s.page.locator('.menu__panel[role="dialog"]').count() == 1 and s.page.locator(".toc__item").count() == n + 1,
            str(s.page.locator(".toc__item").count()))
    R.check("the section you are on is marked", s.page.locator('.toc__item[aria-current="step"] .toc__name').inner_text().strip() == k.titles[second])
    R.check("sections you haven't reached are disabled", s.page.locator(".toc__item:disabled").count() == n - 2 + 1 and s.page.locator(".toc__item.is-done").count() == 1,
            f"{s.page.locator('.toc__item:disabled').count()} disabled, {s.page.locator('.toc__item.is-done').count()} done")
    R.check("focus is inside the menu", s.page.evaluate("!!document.activeElement.closest('.menu')"))
    for _ in range(25):
        s.page.keyboard.press("Tab")
    R.check("Tab stays inside the menu", s.page.evaluate("!!document.activeElement.closest('.menu')"))
    s.page.keyboard.press("Escape")
    R.check("Escape closes it and puts focus back on the button", s.page.locator(".menu").is_hidden() and s.page.evaluate("document.activeElement.className") == "top__menu")
    s.page.click(".top__menu")
    s.page.locator(".toc__item", has_text=k.titles[first]).click()
    s.wait_screen(first)
    R.check("choosing a section goes there", s.screen == first and s.page.locator(".menu").is_hidden())

    s.go("welcome")
    R.check("going back to the welcome screen hides the header and bottom bar again", s.page.is_hidden("#top") and s.page.is_hidden("#foot"))
    erase = s.page.locator(".welcome__go .btn--quiet")  # its words change on the first tap, so find it by place, not by name
    erase.click()
    R.check("the first tap on Erase only asks", "Tap again" in erase.inner_text() and s.saved().get("answers", {}).get("postal") == "L6X 0G3")
    erase.click()
    s.page.wait_for_timeout(200)
    R.check("a second tap erases everything", s.page.evaluate("localStorage.getItem('questionnaire:twireless:v1')") is None)
    R.check("and the screen shows a fresh Start straight away", s.page.get_by_role("button", name="Start", exact=True).count() == 1
            and s.page.get_by_role("button", name="Carry on where you left off").count() == 0)
    start(s)
    s.wait_screen(first)
    R.check("a fresh start has the old answers gone", s.page.locator('[data-q="postal"] input:checked').count() == 0)
    s.close()


def scenario_editing(browser, base: str, k: Known, ks: Known, sbase: str) -> None:
    R.section("Editing from the review list, and carrying on after 'finish later'")
    ids, first = k.ids, k.first
    s = Session(browser, base, state=dict(k.complete))
    s.go("send")
    s.page.locator(".rsec", has_text=k.titles[first]).locator(".rsec__edit").click()
    s.wait_screen(first)
    R.check("Edit goes to that section", s.screen == first)
    R.check("and the bottom button then takes you back to the review",
            s.page.locator("#foot .btn--primary").inner_text().strip() == "Back to my answers")
    s.option("phone", "Yes, for calls only").click()
    s.page.click("#foot .btn--primary")
    s.wait_screen("send")
    R.check("pressing it returns to the review, not to the next section", s.screen == "send")
    R.check("the review shows the change", "Yes, for calls only" in s.page.inner_text(".review"))
    R.check("and everything is still marked finished", "That’s everything" in s.page.inner_text("h1") and s.saved()["furthest"] == len(ids))
    s.go(first)
    R.check("once back on the review, sections go back to Next", s.page.locator("#foot .btn--primary").inner_text().strip() == "Next")
    s.close()

    # with every question required, an answer emptied while editing still stops you
    text_q = find_question(ks.spec, lambda q: q["type"] in ("text", "paragraph"))["id"]
    screen = ks.screen_for(text_q)
    s = Session(browser, sbase, state=dict(ks.complete))
    s.go("send")
    s.page.locator(".rsec", has_text=ks.titles[screen]).locator(".rsec__edit").click()
    s.wait_screen(screen)
    s.page.fill(f"#f-{text_q}", "")
    s.page.click("#foot .btn--primary")
    s.page.wait_for_timeout(150)
    R.check("while editing, a required answer left empty still stops you", s.screen == screen and s.page.locator(".q.is-invalid").count() == 1)
    s.close()

    # finish later, change your mind, carry on: the menu must not offer to send half of Part 2
    gate = k.stops[0]
    some = {"postal": "L6X 0G3"}
    s = Session(browser, base, state={"answers": some, "others": {}, "furthest": ids.index(gate)})
    s.go(gate)
    s.page.locator(".stop__go .btn").nth(1).click()
    s.wait_screen("send")
    R.check("'finish later' opens the send screen", s.screen == "send")
    s.back()
    s.wait_screen(gate)
    s.page.locator(".stop__go .btn").first.click()
    s.wait_screen(ids[ids.index(gate) + 1])
    s.page.click(".top__menu")
    R.check("after 'keep going' the menu no longer offers to send", s.page.locator('.toc__item[data-go="send"]').is_disabled())
    s.page.keyboard.press("Escape")
    s.page.evaluate("() => { location.hash = '#/send'; }")
    s.page.wait_for_timeout(250)
    R.check("and typing the address of the send screen doesn't get you there", s.screen != "send", s.screen)
    s.close()

    # the send screen's Carry on, from a stop and from the middle of a part
    nextpart = k.part_of(ids[ids.index(gate) + 1])["n"]
    s = Session(browser, base, state={"answers": some, "others": {}, "furthest": ids.index(gate), "ended": True})
    s.go("send")
    R.check("from a stop, Carry on says which part comes next",
            s.page.get_by_role("button", name=f"Carry on with Part {nextpart}").count() == 1)
    s.page.get_by_role("button", name=f"Carry on with Part {nextpart}").click()
    s.wait_screen(ids[ids.index(gate) + 1])
    R.check("and goes to its first section", s.screen == ids[ids.index(gate) + 1])
    s.close()
    mid = ids.index("offers")
    s = Session(browser, base, state={"answers": some, "others": {}, "furthest": mid, "ended": True})
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


def scenario_storage_blocked(browser, base: str, k: Known) -> None:
    R.section("A browser that can't save")
    ctx = browser.new_context(viewport={"width": 390, "height": 844})
    ctx.add_init_script("Object.defineProperty(window, 'localStorage', { get() { throw new Error('blocked'); } });")
    page = ctx.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(base + "/index.html")
    until(page, "() => document.body.dataset.screen", what="a screen")
    R.check("the page still works", page.get_by_role("button", name="Start", exact=True).count() == 1 and not errors, str(errors))
    R.check("and says it can't save", "can’t save your answers" in page.inner_text("main"))
    page.get_by_role("button", name="Start", exact=True).click()
    until(page, f"() => document.body.dataset.screen === '{k.first}'", what="the first section")
    box = '[data-q="postal"] .opt-other input.input'
    page.locator('[data-q="postal"] label.opt').filter(has=page.get_by_text("Other", exact=True)).click()
    page.fill(box, "L6X 1A1")
    R.check("typing still works with no storage", not errors and page.input_value(box) == "L6X 1A1", str(errors))
    ctx.close()


def scenario_layout(browser, base: str, k: Known, axe: Path | None) -> None:
    R.section("Widths from 320 to 1280, and tap sizes")
    ids = ["welcome"] + k.ids + ["send"]
    grid_screen = k.screen_for(find_question(k.spec, lambda q: q["type"] == "grid")["id"])
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
      document.querySelectorAll('button, a.btn, .opt, .pill, input[type=text], textarea, summary').forEach(e => {
        if (e.closest('[hidden]') || !e.offsetParent && getComputedStyle(e).position !== 'fixed') return;
        const r = e.getBoundingClientRect();
        if (r.height && (r.height < 43.5 || (e.tagName === 'BUTTON' && r.width < 43.5))) small.push(e.tagName + '.' + e.className + ' ' + Math.round(r.width) + 'x' + Math.round(r.height));
      });
      return { scrollW: Math.max(document.documentElement.scrollWidth, window.innerWidth), w, bad: bad.slice(0, 4), small: small.slice(0, 4),
               top: document.querySelector('#top').hidden ? 0 : Math.round(document.querySelector('#top').getBoundingClientRect().height),
               line: document.querySelector('#top').hidden ? 0 : Math.round(document.querySelector('.top__where b').getBoundingClientRect().height) };
    }"""
    for width in (320, 360, 390, 430, 600, 768, 980, 1280):
        s = Session(browser, base, width=width, height=900 if width >= 700 else 844, reduced=True, state=dict(k.complete))
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
                tall.append(f"{sid}: the 'Part N of M · Section n of m' line wraps ({res['line']}px tall)")
        R.check(f"{width}px: nothing sticks out sideways on any of the {len(ids)} screens", not wide, "; ".join(wide[:3]))
        R.check(f"{width}px: every button, answer and box is at least 44 px tall", not small, "; ".join(small[:3]))
        R.check(f"{width}px: the sticky header stays slim", not tall, "; ".join(tall[:3]))
        R.check(f"{width}px: no console problems", not s.problems, str(s.problems[:2]))
        if width in (390, 980):
            s.go(grid_screen)
            axe_run(s, axe, f"{width}px, a section with a grid")
            s.go("send")
            axe_run(s, axe, f"{width}px, the send screen")
            s.go(k.first)
            s.page.click(".top__menu")
            axe_run(s, axe, f"{width}px, the Sections menu")
        s.close()


def scenario_motion_and_names(browser, base: str, k: Known) -> None:
    R.section("Motion, headings and names")
    title = k.titles[k.first]
    where = f"Part 1, section 1 of {len(k.part_sections[k.part_of(k.first)['id']])}: {title}"
    s = Session(browser, base, reduced=True)
    start(s)
    s.wait_screen(k.first)
    R.check("with 'reduce motion' on, no screen slides in", "go-forward" not in (s.page.get_attribute(".card", "class") or ""))
    R.check("each screen has one h1 and it takes focus", s.page.locator("h1").count() == 1 and s.page.evaluate("document.activeElement.tagName") == "H1")
    R.check("the browser tab title names the section", s.page.title().startswith(title), s.page.title())
    R.check("the live region announces the new section",
            poll(s.page, "(t) => document.getElementById('live').textContent === t", where), s.page.inner_text("#live"))
    s.close()
    s = Session(browser, base, reduced=False)
    start(s)
    s.wait_screen(k.first)
    R.check("by default the next screen slides in", "go-forward" in (s.page.get_attribute(".card", "class") or ""))
    s.close()
    # the first frame of the slide is the widest the page ever gets; hold it there with the safeguard against overflow removed
    s = Session(browser, base, width=320, reduced=False)
    s.page.add_style_tag(content=".main { overflow-x: visible !important; }")
    start(s)
    s.wait_screen(k.first)
    worst = s.page.evaluate("() => { document.getAnimations().forEach(a => { a.pause(); a.currentTime = 0; }); "
                            "return [document.documentElement.scrollWidth, window.innerWidth, document.getAnimations().length]; }")
    R.check("a screen sliding in never makes the page wider than the phone, even without the clip safeguard",
            worst[2] >= 1 and max(worst[0], worst[1]) <= 320, str(worst))
    s.close()


# ---------------------------------------------------------------------------------------------
# problems an independent review found


def fix_blank_required(browser, base: str, k: Known, axe: Path | None) -> None:
    """With every question required: an edit that opens new questions, then a jump through the Sections menu, must not end in "that's everything"."""
    blank = ("repair_brands", "repair_types", "repair_quote")
    part = k.part_of("repairs_q")["n"]
    gap = {key: v for key, v in k.answers.items() if key not in blank}
    s = Session(browser, base, state={**k.complete, "answers": gap})
    s.go("send")
    heading = s.page.inner_text("h1")
    notice = s.page.inner_text(".send__needs") if s.page.locator(".send__needs").count() else "(no notice)"
    R.check("required answers blank: the send screen does not say everything is done", "That’s everything" not in heading and "so far" in heading, heading)
    R.check("it says how many questions still need an answer", "3 questions still need an answer" in notice, notice)
    R.check("the header does not say All done", "All done" not in s.page.inner_text("#top"), s.page.inner_text("#top"))
    export = s.raw_text()
    R.check("the text says that part is started, and how many are blank",
            f"Part {part} started (3 questions still need an answer)" in export, export[:300])
    R.check("the review flags each blank question", s.page.locator(".rq__flag").count() == 3, str(s.page.locator(".rq__flag").count()))
    R.check("it doesn't offer to 'carry on' from a place the person has already passed", s.page.locator(".send__more").count() == 0)
    axe_run(s, axe, "the send screen with questions still needing an answer")
    s.page.click(".top__menu")
    flagged = s.page.locator(".toc__item", has=s.page.locator(".toc__need"))
    R.check("the Sections menu marks the one section that needs an answer", flagged.count() == 1 and k.titles["repairs_q"] in flagged.inner_text(), str(flagged.all_inner_texts()))
    s.page.keyboard.press("Escape")
    s.page.get_by_role("button", name="Go to the first one").click(timeout=3000)
    s.wait_screen("repairs_q")
    R.check("Go to the first one opens that section, with the way back to the review",
            s.screen == "repairs_q" and s.page.locator("#foot .btn--primary").inner_text().strip() == "Back to my answers")
    s.next()
    s.page.wait_for_timeout(150)
    R.check("and it can't be left with those still blank", s.screen == "repairs_q" and s.page.locator(".q.is-invalid").count() == 3)
    axe_run(s, axe, "required choices and ticks left empty")
    for qid in blank:
        s.page.locator(f'[data-q="{qid}"] label.opt').first.click()
    s.next()
    s.wait_screen("send")
    R.check("once they are answered, the review says everything is done",
            "That’s everything" in s.page.inner_text("h1") and "All done" in s.page.inner_text("#top") and s.page.locator(".send__needs").count() == 0)
    s.close()


def fix_start_without_place(browser, base: str, k: Known, axe: Path | None) -> None:
    """Answers saved with no place in the questions: Start has to work."""
    text_q = find_question(k.spec, lambda q: q["type"] in ("text", "paragraph"))
    s = Session(browser, base, state={"answers": {text_q["id"]: "something typed"}, "others": {}})
    R.check("answers saved with no place in the questions offer Start", s.page.get_by_role("button", name="Start", exact=True).count() == 1)
    s.page.get_by_role("button", name="Start", exact=True).click(timeout=3000)
    s.wait_screen(k.first)
    R.check("and Start takes you to the first section", s.screen == k.first and s.page.locator("#top").is_visible())
    s.close()


def fix_object_names_in_address(browser, base: str, k: Known, axe: Path | None) -> None:
    """Names the page's own objects have must not be taken for screens."""
    s = Session(browser, base, state={"answers": {}, "others": {}, "furthest": 3})
    bad = []
    for name in ("constructor", "__proto__", "toString", "hasOwnProperty", "valueOf"):
        page = s.ctx.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e, errors=errors: errors.append(str(e)))
        page.goto(f"{base}/index.html#/{name}")
        until(page, "() => document.body.dataset.screen", what="a screen")
        shown = page.evaluate("document.body.dataset.screen")
        if "Something went wrong" in page.inner_text("main") or errors or shown not in k.ids + ["welcome", "send"]:
            bad.append(f"{name}: {shown} {errors[:1]}")
        page.close()
    R.check("an address such as #/constructor shows a real screen, not an error", not bad, "; ".join(bad))
    s.close()


def fix_unreadable_saved_value(browser, base: str, k: Known, axe: Path | None) -> None:
    ctx = browser.new_context(viewport={"width": 390, "height": 844})
    ctx.add_init_script("localStorage.setItem('questionnaire:twireless:v1', '{this is not json');")
    page = ctx.new_page()
    page.goto(base + "/index.html")
    until(page, "() => document.body.dataset.screen", what="a screen")
    R.check("a saved value that can't be read is ignored, and the page doesn't claim the browser can't save",
            "can’t save" not in page.inner_text("main") and page.get_by_role("button", name="Start", exact=True).count() == 1, page.inner_text("main")[-200:])
    page.get_by_role("button", name="Start", exact=True).click()
    until(page, f"() => document.body.dataset.screen === '{k.first}'", what="the first section")
    readable = page.evaluate("() => { try { JSON.parse(localStorage.getItem('questionnaire:twireless:v1')); return true; } catch (e) { return false; } }")
    R.check("and starting writes a readable value over it", readable)
    ctx.close()


def fix_saved_answers_screen_would_refuse(browser, base: str, k: Known, axe: Path | None) -> None:
    excl = find_question(k.spec, lambda q: q["type"] == "checkbox" and (q.get("app") or {}).get("exclusive"))
    upto = find_question(k.spec, lambda q: q["type"] == "checkbox" and q.get("max_choices"))
    exclusive = excl["app"]["exclusive"]
    plain = [o for o in excl["options"] if o not in exclusive][0]
    odd = dict(k.answers)
    odd[excl["id"]] = [plain, exclusive[0]]
    odd[upto["id"]] = upto["options"][: upto["max_choices"] + 1]
    s = Session(browser, base, state={**k.complete, "answers": odd})
    s.go(k.screen_for(excl["id"]))
    values = s.page.eval_on_selector_all(f'[data-q="{excl["id"]}"] input:checked', "els => els.map(e => e.value)")
    R.check("saved ticks that contradict each other: the option that excludes the rest is dropped", values == [plain], str(values))
    s.go(k.screen_for(upto["id"]))
    values = s.page.eval_on_selector_all(f'[data-q="{upto["id"]}"] input:checked', "els => els.map(e => e.value)")
    n = upto["max_choices"]
    R.check("saved ticks past 'choose up to N' are cut to N", len(values) == n and f"{n} of {n} chosen" in s.page.inner_text(f'[data-q="{upto["id"]}"] .q__count'), str(values))
    s.close()


def fix_arrow_keys_onto_other(browser, base: str, k: Known, axe: Path | None) -> None:
    """Arrowing onto Other must not pull focus out of the list."""
    oq = find_question(k.spec, lambda q: q["type"] == "choice" and q.get("other") and len(q["options"]) >= 2)
    s = Session(browser, base, state=dict(k.complete))
    s.go(k.screen_for(oq["id"]))
    sel = f'[data-q="{oq["id"]}"]'
    s.page.focus(f"{sel} input[type=radio]")
    for _ in range(len(oq["options"])):
        s.page.keyboard.press("ArrowDown")
    R.check("arrowing onto Other selects it and leaves focus on the choice",
            s.page.evaluate("document.activeElement.value") == OTHER and s.page.locator(f"{sel} .opt-other input.input").is_visible())
    s.page.keyboard.press("ArrowUp")
    R.check("so the arrow keys still work: Up goes back to the option above", s.page.evaluate("document.activeElement.value") == oq["options"][-1])
    s.page.keyboard.press("ArrowDown")
    s.page.keyboard.press("Tab")
    R.check("and Tab then reaches the Other box", s.page.evaluate("document.activeElement.getAttribute('aria-label')") == "Other: type your answer")
    s.close()


def fix_clear_my_choice_focus(browser, base: str, k: Known, axe: Path | None) -> None:
    cq = find_question(k.spec, lambda q: q["type"] == "choice" and not q["required"])
    s = Session(browser, base, state=dict(k.complete))
    s.go(k.screen_for(cq["id"]))
    s.page.locator(f'[data-q="{cq["id"]}"] .q__clear').click()
    R.check("after Clear my choice, focus stays with that question's choices",
            s.page.evaluate("(q) => { const a = document.activeElement; return !!a && a.type === 'radio' && !!a.closest('[data-q=\"' + q + '\"]'); }", cq["id"]))
    s.close()


def fix_grid_is_a_group(browser, base: str, k: Known, axe: Path | None) -> None:
    gq = find_question(k.spec, lambda q: q["type"] == "grid" and q.get("help"))
    s = Session(browser, base, state=dict(k.complete))
    s.go(k.screen_for(gq["id"]))
    info = s.page.evaluate("""(q) => {
      const g = document.querySelector('[data-q="' + q + '"] .grid');
      const l = document.getElementById(g.getAttribute('aria-labelledby'));
      const d = g.getAttribute('aria-describedby') ? document.getElementById(g.getAttribute('aria-describedby')) : null;
      return { role: g.getAttribute('role'), label: l ? l.textContent : '', help: !!d };
    }""", gq["id"])
    R.check("a grid is a group named by its question, with the help tied to it", info["role"] == "group" and gq["title"] in info["label"] and info["help"], str(info))
    s.close()


def fix_focus_not_under_bars(browser, base: str, k: Known, axe: Path | None) -> None:
    """Focus must never land under the header or the bottom bar."""
    busiest = max((sc for sc in k.model["screens"] if sc["kind"] == "section"),
                  key=lambda sc: sum(len(pg["questions"]) for pg in k.model["pages"] if pg["id"] in sc["pages"]))["id"]
    s = Session(browser, base, width=390, height=700, state=dict(k.complete))
    s.go(busiest)
    probe = """() => {
      const a = document.activeElement;
      if (!a || a === document.body || a.closest('#top, #foot')) return null;
      const r = (a.closest('.opt, .pill') || a).getBoundingClientRect();
      const foot = document.querySelector('#foot');
      return { top: r.top, bottom: r.bottom, header: document.querySelector('#top').getBoundingClientRect().bottom,
               foot: foot.hidden ? window.innerHeight : foot.getBoundingClientRect().top, name: (a.name || a.id || a.tagName) + ' ' + (a.value || '') };
    }"""
    hidden: list[str] = []
    for key in ("Tab", "Shift+Tab"):
        s.page.evaluate("window.scrollTo(0, 0)")
        for _ in range(60):
            s.page.keyboard.press(key)
            r = s.page.evaluate(probe)
            if r and (r["top"] < r["header"] - 1 or r["bottom"] > r["foot"] + 1):
                hidden.append(f"{key} {r['name']} at {r['top']:.0f}-{r['bottom']:.0f} (bars: {r['header']:.0f}, {r['foot']:.0f})")
    R.check(f"on '{busiest}', the focused control is never hidden behind the header or the bottom bar", not hidden, "; ".join(hidden[:2]))
    s.close()


def fix_finished_part_wording(browser, base: str, k: Known, axe: Path | None) -> None:
    s = Session(browser, base, state=dict(k.complete))
    s.go(k.first)
    top = s.page.inner_text("#top")
    R.check("visiting a finished part says it is done, not 'nearly done'", "this part is done" in top and "nearly done" not in top, top)
    s.close()


def fix_markup_in_data(browser, base: str, k: Known, axe: Path | None) -> None:
    """Data with markup in it must not break the page."""
    evil = json.loads(json.dumps(k.spec))
    # no closing "-->" or "</script>": that is the form that leaves a browser reading to the end of the page
    evil["sections"][0]["questions"][0]["help"] = "<!-- <script>window.__evil = 1; a & b <b>not bold</b>"
    with tempfile.TemporaryDirectory() as tmp:
        bq.build_app(evil, Path(tmp) / "index.html", endpoint="")
        html = (Path(tmp) / "index.html").read_text(encoding="utf-8")
        blob = re.search(r'<script type="application/json" id="spec">(.*?)</script>', html, re.S).group(1)
        R.check("the data inside the page contains no '<', '>' or '&' of its own", not any(c in blob for c in "<>&"))
        web, ebase = serve(Path(tmp))
        s = Session(browser, ebase)
        R.check("a '<!--' followed by '<script' in the data doesn't stop the page from starting", s.page.get_by_role("button", name="Start", exact=True).count() == 1)
        start(s)
        s.wait_screen(k.first)
        shown = s.page.inner_text(".q__help")
        R.check("it shows as plain text and runs nothing", "<!-- <script>window.__evil = 1; a & b <b>not bold</b>" in shown
                and s.page.evaluate("typeof window.__evil") == "undefined" and s.page.locator(".q__help b").count() == 0, shown)
        s.close()
        web.shutdown()


def scenario_review_fixes(browser, base: str, sbase: str, k: Known, ks: Known, axe: Path | None) -> None:
    R.section("Problems an independent review found")
    runs = [(fix_blank_required, sbase, ks)] + [
        (fix, base, k) for fix in (fix_start_without_place, fix_object_names_in_address, fix_unreadable_saved_value,
                                   fix_saved_answers_screen_would_refuse, fix_arrow_keys_onto_other, fix_clear_my_choice_focus,
                                   fix_grid_is_a_group, fix_focus_not_under_bars, fix_finished_part_wording, fix_markup_in_data)]
    for fix, where, known in runs:
        try:
            fix(browser, where, known, axe)
        except Exception as e:  # a check that can't finish counts as a failure, and the rest still run
            R.check(f"{fix.__name__}: the check could not finish", False, f"{type(e).__name__}: {str(e).splitlines()[0][:140]}")


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
    strict = strict_variant(spec)
    k, ks = Known(spec), Known(strict)
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as tmp_strict:
        bq.build_app(spec, Path(tmp) / "index.html", endpoint="")  # the scenarios that need an endpoint build their own
        bq.build_app(strict, Path(tmp_strict) / "index.html", endpoint="")
        srv, base = serve(Path(tmp))
        ssrv, sbase = serve(Path(tmp_strict))
        with sync_playwright() as p:
            browser = p.chromium.launch()
            wanted = lambda name: not ns.only or ns.only in name  # noqa: E731

            def attempt(scenario, *args, **kwargs) -> None:
                """A scenario that can't finish counts as a failure, and the others still run."""
                try:
                    scenario(*args, **kwargs)
                except Exception as e:
                    R.check(f"{scenario.__name__}: the scenario could not finish", False, f"{type(e).__name__}: {str(e).splitlines()[0][:160]}")

            if wanted("build"):
                attempt(scenario_build, k)
            if wanted("cold"):
                attempt(scenario_cold_call, browser, base, k, ns.axe)
            if wanted("welcome"):
                attempt(scenario_welcome_and_errors, browser, sbase, ks, ns.axe)
            if wanted("other"):
                attempt(scenario_other_and_limits, browser, base, k, ns.axe)
                attempt(scenario_custom_answers, browser, base, k, ns.axe)
            if wanted("gates"):
                attempt(scenario_required_stop, browser, sbase, ks)
                attempt(scenario_gates, browser, base, k)
            if wanted("everything"):
                attempt(scenario_everything, browser, base, k, ns.axe, "every question answered", optional=True)
                attempt(scenario_everything, browser, sbase, ks, ns.axe, "every question required", optional=False)
            if wanted("share"):
                attempt(scenario_share_and_endpoint, browser, base, k)
            if wanted("google"):
                attempt(scenario_google_endpoint, p, k)
            if wanted("receiver"):
                attempt(scenario_receiver, browser, k)
            if wanted("resume"):
                attempt(scenario_resume_and_history, browser, base, k)
            if wanted("edit"):
                attempt(scenario_editing, browser, base, k, ks, sbase)
            if wanted("script"):
                attempt(scenario_script_cannot_run, browser, base)
            if wanted("storage"):
                attempt(scenario_storage_blocked, browser, base, k)
            if wanted("layout"):
                attempt(scenario_layout, browser, base, k, ns.axe)
            if wanted("motion"):
                attempt(scenario_motion_and_names, browser, base, k)
            if wanted("fixes"):
                attempt(scenario_review_fixes, browser, base, sbase, k, ks, ns.axe)
            browser.close()
        srv.shutdown()
        ssrv.shutdown()
    print(f"\n{R.total - R.failed} of {R.total} checks passed" + ("" if not R.failed else f", {R.failed} FAILED"))
    return 1 if R.failed else 0


if __name__ == "__main__":
    sys.exit(main())
