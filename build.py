#!/usr/bin/env python3
"""Build the T Wireless website into dist/.

    python3 build.py                      preview build into dist/
    python3 build.py --release            same, but stops if example offers remain or base_url is empty
    python3 build.py --logo-placeholders --out preview/
                                          preview build that shows labelled frames where carrier logos go
    python3 build.py --demo --base-path /twireless-site/ --out docs/
                                          public demo for GitHub Pages: a "preview" banner, forms that
                                          don't send, no search indexing, and a 404 page that works under
                                          the project path
    python3 build.py --design design-2
                                          build another design into dist-design-2/ from designs/design-2/ (its own pages,
                                          partials, CSS, fonts and photos) with the same store content

Demo extras: --switch "Design 1=/twireless-site/=design-1;Design 2=/twireless-site/design-2/=design-2" adds links to
the other designs in the preview banner, and --public-url https://emblem-nlp.github.io/twireless-site
gives shared links a preview image (og:image) without a canonical link.

Designs: design 1 lives in src/. Each other design has designs/<id>/design.json, pages/, partials/
(any partial it doesn't have comes from src/partials), assets/ (copied over the shared scripts and
images from src/assets), an optional design.py whose extend(page_context, kit) adds that design's
own snippets, and an optional content.json: the design's own wording for the shared lists (repairs,
FAQ) and its small pieces of microcopy, which replace those keys of src/site.json for that design
only. Facts (store, hours, site, carriers, offers) stay in src/site.json and can't be overridden.
design.json can also relabel the navigation ("nav": {"mobile": "Phones"}). A navigation entry whose
page a design doesn't have is left out of that design's menu and footer (business.html exists only in
design 2 so far), so a new page can be added to one design at a time.
Photos come from assets/img/photos/photos.json, written by rsi/imagery.py.

Carrier logos: put the official files in src/assets/img/brands/ as bell, virgin-plus and
lucky-mobile (.svg preferred, or .png on a transparent background, optionally with a .webp twin
that browsers with WebP load instead). Pages show each logo once its file is there, and keep
the plain-text names and icons until then.

Store details, hours, offers, repairs and FAQ live in src/site.json (a design's content.json can
reword the repairs and FAQ for that design).
Page copy lives in src/pages/*.html; shared parts in src/partials/*.html.
Tokens: {{ name }} inserts escaped text, {{{ name }}} inserts ready-made HTML.
Needs only Python 3.8+ (no packages).
"""
import datetime
import hashlib
import html
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
DIST = ROOT / "dist"
DESIGNS = ROOT / "designs"

WEEK = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
JS_DAY = {"Sunday": 0, "Monday": 1, "Tuesday": 2, "Wednesday": 3, "Thursday": 4, "Friday": 5, "Saturday": 6}
NAV = [
    ("deals", "deals.html", "Deals"),
    ("brands", "brands.html", "Bell family"),
    ("mobile", "mobile.html", "Mobile"),
    ("internet-tv", "internet-tv.html", "Internet and TV"),
    ("repairs", "repairs.html", "Repairs"),
    ("business", "business.html", "Business solutions"),
    ("visit", "visit.html", "Visit us"),
]
OFFER_ART = {"mobile": "art-mobile", "home": "art-home", "repairs": "art-repair"}
FACT_KEYS = ("store", "hours", "site", "carriers", "offers")  # shared by every design; content.json can't change them
LOGO_DIR = SRC / "assets" / "img" / "brands"
LOGO_EXTS = (".svg", ".png", ".webp")  # a .png wins over .webp so it can serve as the fallback
TOKEN = re.compile(r"\{\{\{\s*([\w.]+)\s*\}\}\}|\{\{\s*([\w.]+)\s*\}\}")
PAGE_META = re.compile(r"\A<!--page\s*(\{.*?\})\s*-->\s*", re.S)


def esc(value):
    return html.escape(str(value), quote=True)


def lookup(ctx, path):
    cur = ctx
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            raise KeyError(path)
    return cur


def render(text, ctx, where, escape=True):
    def sub(match):
        key = match.group(1) or match.group(2)
        try:
            value = lookup(ctx, key)
        except KeyError:
            raise SystemExit(f"{where}: unknown token '{key}'")
        value = "" if value is None else str(value)
        return value if (match.group(1) or not escape) else esc(value)
    return TOKEN.sub(sub, text)


def minify_css(css):
    """Drop comments and extra whitespace. Leaves spaces inside values (calc, selectors) alone."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    css = re.sub(r"\s+", " ", css)
    css = re.sub(r"\s*([{};,])\s*", r"\1", css)
    return css.replace(";}", "}").strip() + "\n"


def time_label(hhmm):
    h, m = (int(x) for x in hhmm.split(":"))
    h12 = h % 12 or 12
    suffix = "a.m." if h < 12 else "p.m."
    nbsp = " "  # keeps "8 p.m." together, so a line never ends on "8" and starts on "p.m."
    return f"{h12}{nbsp}{suffix}" if m == 0 else f"{h12}:{m:02d}{nbsp}{suffix}"


def day_span(hours):
    return f"{time_label(hours[0])} to {time_label(hours[1])}" if hours else "Closed"


def hours_text(hours):
    """Return (summary sentence, phrase for use inside a sentence)."""
    spans = [day_span(hours.get(d)) for d in WEEK]
    if len(set(spans)) == 1 and spans[0] != "Closed":
        sentence = f"Open every day, {spans[0]}"
        return (sentence if sentence.endswith(".") else sentence + "."), f"every day from {spans[0]}"
    groups, start = [], 0
    for i in range(1, 8):
        if i == 7 or spans[i] != spans[start]:
            days = WEEK[start] if i - 1 == start else f"{WEEK[start]} to {WEEK[i - 1]}"
            groups.append(f"{days}, {spans[start].lower() if spans[start] == 'Closed' else spans[start]}")
            start = i
    return "; ".join(groups) + ".", "during store hours"


def hours_rows(hours):
    return "\n".join(
        f'<tr data-day="{JS_DAY[d]}"><th scope="row">{d}</th><td>{esc(day_span(hours.get(d)))}</td></tr>'
        for d in WEEK
    )


def hours_for_js(hours):
    order = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    return json.dumps([hours.get(d) for d in order], separators=(",", ":"))


class Logos:
    """Carrier logos for the templates.

    Uses the official file from src/assets/img/brands/ when the owner has added one. In preview
    mode (--logo-placeholders) a missing file becomes a labelled empty frame; otherwise callers
    get None and keep the text name or icon they showed before.
    """

    def __init__(self, carriers, placeholders):
        self.by_id = {c["id"]: c for c in carriers}
        self.by_name = {c["name"]: c for c in carriers}
        self.placeholders = placeholders
        self.files = {}
        self.webp = {}
        for c in carriers:
            for ext in LOGO_EXTS:
                if (LOGO_DIR / (c["id"] + ext)).is_file():
                    self.files[c["id"]] = c["id"] + ext
                    break
            # A raster logo can ship as .webp with a .png twin for browsers without WebP (older iPhones).
            if self.files.get(c["id"], "").endswith(".png") and (LOGO_DIR / (c["id"] + ".webp")).is_file():
                self.webp[c["id"]] = c["id"] + ".webp"

    def active(self):
        return bool(self.files) or self.placeholders

    def plate(self, cid, root, alt=None, cls="logo-plate"):
        """A white plate with the carrier's logo. alt="" marks it decorative (name shown beside it)."""
        c = self.by_id.get(cid)
        if not c:
            return None
        if cid in self.files:
            text = c["name"] if alt is None else alt
            img = (f'<img src="{root}assets/img/brands/{esc(self.files[cid])}" '
                   f'alt="{esc(text)}" decoding="async">')
            if cid in self.webp:
                img = (f'<picture><source type="image/webp" srcset="{root}assets/img/brands/{esc(self.webp[cid])}">'
                       f'{img}</picture>')
            return f'<span class="{cls} logo-plate--{esc(cid)}">{img}</span>'
        if self.placeholders:
            hidden = ' aria-hidden="true"' if alt == "" else ""
            return f'<span class="{cls} logo-plate--placeholder"{hidden}>{esc(c["name"])} logo</span>'
        return None


class Photos:
    """Responsive photos listed in a design's photos.json (written by rsi/imagery.py render)."""

    def __init__(self, path):
        self.m = json.loads(path.read_text(encoding="utf-8")) if path and path.exists() else {"photos": {}, "cards": {}}

    def picture(self, pid, crop, root, sizes, alt=None, cls="", priority=False, art=None):
        """<picture> with AVIF and WebP sources and a JPEG fallback. Lazy unless it's the priority image.

        `art` gives other screens their own crop of the same photo: a list of (media query, crop name, sizes),
        most specific first. Each gets AVIF, WebP and JPEG sources, so a browser that can't read AVIF or WebP
        still gets that crop; `crop` and `sizes` serve every screen that matches none of them."""
        entry = self.m["photos"].get(pid)
        if not entry or crop not in entry["crops"]:
            raise SystemExit(f"Photo {pid} ({crop}) isn't in photos.json: run python3 rsi/imagery.py render")

        def srcset(files, fmt):
            return ", ".join(f'{root}assets/img/photos/{esc(f["file"])} {f["w"]}w' for f in files[fmt])
        files = entry["crops"][crop]["files"]
        big = max(files["jpg"], key=lambda f: f["w"])
        fallback = min(files["jpg"], key=lambda f: abs(f["w"] - 800))
        text = entry["alt"] if alt is None else alt
        sources = []
        for media, art_crop, art_sizes in art or []:
            if art_crop not in entry["crops"]:
                raise SystemExit(f"Photo {pid} ({art_crop}) isn't in photos.json: run python3 rsi/imagery.py render")
            art_files = entry["crops"][art_crop]["files"]
            for fmt, mime in (("avif", "image/avif"), ("webp", "image/webp"), ("jpg", "image/jpeg")):
                sources.append(f'<source media="{esc(media)}" type="{mime}" srcset="{srcset(art_files, fmt)}" sizes="{esc(art_sizes)}">')
        for fmt, mime in (("avif", "image/avif"), ("webp", "image/webp")):
            sources.append(f'<source type="{mime}" srcset="{srcset(files, fmt)}" sizes="{esc(sizes)}">')
        img = [f'src="{root}assets/img/photos/{esc(fallback["file"])}"', f'srcset="{srcset(files, "jpg")}"',
               f'sizes="{esc(sizes)}"', f'width="{big["w"]}"', f'height="{big["h"]}"', f'alt="{esc(text)}"',
               'decoding="async"', 'fetchpriority="high"' if priority else 'loading="lazy"']
        cls_attr = f' class="{esc(cls)}"' if cls else ""
        return f'<picture{cls_attr}>{"".join(sources)}<img {" ".join(img)}></picture>'

    def credits(self):
        """One entry per photo: who took it, where it's from and its licence."""
        return [dict(e["source"], id=pid, alt=e["alt"]) for pid, e in self.m["photos"].items()]


def load_design(name):
    """Design 1 is src/ as it has always been; any other design is designs/<name>/."""
    if not name or name == "design-1":
        return {"id": "design-1", "label": "Design 1", "pages": SRC / "pages", "partials": [SRC / "partials"],
                "assets": SRC / "assets", "skip": [], "og_image": "assets/img/og-image.png", "module": None,
                "photos": None, "content": None, "nav": {}}
    folder = DESIGNS / name
    if not (folder / "design.json").is_file():
        raise SystemExit(f"No design called {name}: designs/{name}/design.json is missing")
    cfg = json.loads((folder / "design.json").read_text(encoding="utf-8"))
    return {"id": cfg["id"], "label": cfg["label"], "pages": folder / "pages",
            "partials": [SRC / "partials", folder / "partials"], "assets": folder / "assets",
            "skip": cfg.get("skip_shared_assets", ["css", "fonts", "img/og-image.png"]),
            "og_image": cfg.get("og_image", ""), "module": folder / cfg["module"] if cfg.get("module") else None,
            "photos": folder / "assets" / "img" / "photos" / "photos.json",
            "content": folder / cfg["content"] if cfg.get("content") else None, "nav": cfg.get("nav", {})}


def load_module(path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("design_" + path.parent.name.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def copy_assets(design, dist):
    """Shared scripts and images from src/assets, then the design's own assets on top."""
    skip = {Path(s) for s in design["skip"]}

    def ignore(folder, names):
        rel = Path(folder).relative_to(SRC / "assets")
        return [n for n in names if rel / n in skip]
    shutil.copytree(SRC / "assets", dist / "assets", ignore=ignore if skip else None)
    if design["assets"] != SRC / "assets":
        shutil.copytree(design["assets"], dist / "assets", dirs_exist_ok=True)


def parse_switch(value):
    """'Design 1=/twireless-site/=design-1;Design 2=/twireless-site/design-2/=design-2'
    -> [(label, base path, page file names)]. The design id is optional; with it, a page that the
    other design doesn't have links to its home page instead."""
    pairs = []
    for part in (value or "").split(";"):
        bits = [b.strip() for b in part.split("=")]
        if len(bits) >= 2:
            pages = None
            if len(bits) > 2 and bits[2]:
                pages = {p.name for p in load_design(bits[2])["pages"].glob("*.html")}
            pairs.append((bits[0], bits[1], pages))
    return pairs


def switch_banner(pairs, current, page_name):
    links = []
    for label, path, pages in pairs:
        same = page_name != "404.html" and (pages is None or page_name in pages)
        target = path + (page_name if same else "index.html")
        here = ' aria-current="page"' if label == current else ""
        links.append(f'<a href="{esc(target)}"{here}>{esc(label)}</a>')
    return ('\n<div class="demo-banner"><p>Preview of the new T Wireless website. It isn\'t live yet, so forms here don\'t send.</p>'
            f'<p class="demo-banner__designs">Compare designs: {" ".join(links)}</p></div>')


def offer_brand(brand, logos, root):
    carrier = logos.by_name.get(brand)
    if carrier:
        plate = logos.plate(carrier["id"], root, cls="offer__brand offer__brand--logo")
        if plate:
            return plate
    if brand == "T Wireless" and logos.active():
        return (f'<span class="offer__brand offer__brand--logo"><picture>'
                f'<source type="image/webp" srcset="{root}assets/img/t-wireless-logo-480.webp">'
                f'<img src="{root}assets/img/t-wireless-logo-480.png" alt="T Wireless" decoding="async"></picture></span>')
    return f'<p class="offer__brand">{esc(brand)}</p>'


def carrier_strip(carriers, logos, root):
    """'Plans from' row of carrier logos for the home hero; empty until there is something to show."""
    plates = [p for p in (logos.plate(c["id"], root) for c in carriers) if p]
    if not plates:
        return ""
    items = "\n".join(f"    <li>{p}</li>" for p in plates)
    return ('<div class="carriers">\n'
            '  <p class="carriers__label" id="carriers-label">Plans from</p>\n'
            f'  <ul class="carriers__list" aria-labelledby="carriers-label">\n{items}\n  </ul>\n'
            '</div>')


def offer_card(offer, ctx, logos, root=""):
    example = offer.get("status") == "example"
    text = {k: render(str(offer.get(k, "")), ctx, "offer", escape=False) for k in ("brand", "title", "price", "detail", "terms")}
    art = OFFER_ART.get(offer.get("category"), "art-mobile")
    badge = '<p class="offer__badge">Example offer</p>\n  ' if example else ""
    # An example card's terms are a note to the store ("Replace with this month's offer"), not something to show.
    terms = f'\n    <p class="offer__terms">{esc(text["terms"])}</p>' if text["terms"] and not example else ""
    return (
        f'<article class="offer{" offer--example" if example else ""}" data-category="{esc(offer.get("category", "other"))}">\n'
        f'  {badge}<div class="offer__art">\n'
        f'    <svg viewBox="0 0 160 96" aria-hidden="true" focusable="false"><use href="#{art}"></use></svg>\n'
        f'    {offer_brand(text["brand"], logos, root)}\n'
        f'  </div>\n'
        f'  <div class="offer__body">\n'
        f'    <h3 class="offer__title">{esc(text["title"])}</h3>\n'
        f'    <p class="offer__price">{esc(text["price"])}</p>\n'
        f'    <p class="offer__detail">{esc(text["detail"])}</p>{terms}\n'
        f'    <a class="btn btn--ghost btn--small offer__cta" href="tel:{esc(ctx["store"]["phone_e164"])}">Call about this deal</a>\n'
        f'  </div>\n'
        f'</article>'
    )


def brand_cards(family, root, logos, limit=None):
    """Bell family cards. The whole card is clickable through the heading link."""
    items = []
    for b in family[:limit]:
        mark = (logos.plate(b["id"], root, alt="", cls="logo-plate brand-card__logo")
                or f'<span class="brand-card__icon"><svg class="icon" aria-hidden="true"><use href="#{esc(b["icon"])}"></use></svg></span>')
        wide = b.get("wide")
        li_class = ' class="family__wide"' if wide else ""
        card_class = "brand-card brand-card--blue" if wide else "brand-card"
        art = (f'    <svg class="brand-card__art" viewBox="0 0 160 96" aria-hidden="true" focusable="false"><use href="#{esc(b["art"])}"></use></svg>\n'
               if b.get("art") else "")
        items.append(
            f'<li{li_class}>\n'
            f'  <article class="{card_class}">\n'
            f'    {mark}\n'
            f'    <h3 class="brand-card__name"><a class="brand-card__link" href="{root}brands.html#{esc(b["id"])}">{esc(b["name"])}</a></h3>\n'
            f'    <p class="brand-card__text">{esc(b["short"])}</p>\n'
            f'{art}'
            f'  </article>\n'
            f'</li>')
    return "\n".join(items)


def jsonld(data, base):
    store, hours = data["store"], data["hours"]
    groups = {}
    for d in WEEK:
        if hours.get(d):
            groups.setdefault(tuple(hours[d]), []).append(d)
    obj = {
        "@context": "https://schema.org",
        "@type": "MobilePhoneStore",
        "name": store["name"],
        "description": "Bell Authorised Retailer in Brampton selling phones and plans from Bell, Virgin Plus and Lucky Mobile, Bell internet, TV and home phone, and phone and tablet repair.",
        "telephone": "+1-" + store["phone_display"],
        "email": store["email"],
        "address": {
            "@type": "PostalAddress",
            "streetAddress": store["street"],
            "addressLocality": store["city"],
            "addressRegion": store["province"],
            "postalCode": store["postal"],
            "addressCountry": store["country"],
        },
        "openingHoursSpecification": [
            {"@type": "OpeningHoursSpecification", "dayOfWeek": days, "opens": o, "closes": c}
            for (o, c), days in groups.items()
        ],
        "hasMap": store["maps_url"],
    }
    if base:
        obj["url"] = base + "/"
        obj["image"] = base + "/assets/img/t-wireless-logo-960.png"
    body = json.dumps(obj, ensure_ascii=False, indent=1).replace("</", "<\\/")
    return f'<script type="application/ld+json">\n{body}\n</script>'


def nav_entries(pages=None):
    """The navigation list for one design: every entry whose page the design has (all of them when pages is None)."""
    return [(key, href, label) for key, href, label in NAV if pages is None or href in pages]


def nav_html(current, root, labels=None, pages=None):
    labels = labels or {}
    items = []
    for key, href, label in nav_entries(pages):
        here = ' aria-current="page"' if key == current else ""
        items.append(f'<li><a href="{root}{href}"{here}>{esc(labels.get(key, label))}</a></li>')
    return "<ul>\n" + "\n".join(items) + "\n</ul>"


def footer_nav(root, labels=None, pages=None):
    labels = labels or {}
    links = [("index.html", labels.get("index", "Home"))] + [(href, labels.get(key, label)) for key, href, label in nav_entries(pages)]
    return "\n".join(f'<li><a href="{root}{href}">{esc(label)}</a></li>' for href, label in links)


def head_extra(base, out_name, noindex, og_image="assets/img/og-image.png", public_url=""):
    """Robots, canonical and social-preview tags. A demo gets preview tags from --public-url, no canonical."""
    parts = []
    if noindex:
        parts.append('<meta name="robots" content="noindex">')
    page = "" if out_name == "index.html" else out_name
    if base:
        url = base + "/" + page
        parts.append(f'<link rel="canonical" href="{esc(url)}">')
        parts.append(f'<meta property="og:url" content="{esc(url)}">')
    elif public_url:
        parts.append(f'<meta property="og:url" content="{esc(public_url + "/" + page)}">')
    prefix = base or public_url
    if prefix and og_image:
        parts.append(f'<meta property="og:image" content="{esc(prefix)}/{esc(og_image)}">')
        parts.append(f'<meta name="twitter:image" content="{esc(prefix)}/{esc(og_image)}">')
    return "\n".join(parts)


def main():
    release = "--release" in sys.argv
    placeholders = "--logo-placeholders" in sys.argv
    demo = "--demo" in sys.argv
    base_path = sys.argv[sys.argv.index("--base-path") + 1] if "--base-path" in sys.argv else "/"
    if not (base_path.startswith("/") and base_path.endswith("/")):
        raise SystemExit("--base-path must start and end with /, for example /twireless-site/")
    if demo and release:
        raise SystemExit("--demo and --release can't be combined")
    design = load_design(sys.argv[sys.argv.index("--design") + 1] if "--design" in sys.argv else None)
    default_out = DIST if design["id"] == "design-1" else ROOT / f"dist-{design['id']}"
    dist = Path(sys.argv[sys.argv.index("--out") + 1]).resolve() if "--out" in sys.argv else default_out
    switch = parse_switch(sys.argv[sys.argv.index("--switch") + 1]) if "--switch" in sys.argv and demo else []
    public_url = (sys.argv[sys.argv.index("--public-url") + 1].rstrip("/")
                  if "--public-url" in sys.argv and demo else "")
    data = json.loads((SRC / "site.json").read_text(encoding="utf-8"))
    if design["content"]:  # the design's own wording for the lists and microcopy it rewrites
        content = json.loads(design["content"].read_text(encoding="utf-8"))
        clash = [k for k in content if k in FACT_KEYS]
        if clash:
            raise SystemExit(f"{design['content'].name}: {', '.join(clash)} are facts shared by every design: change them in src/site.json")
        data.update(content)
    # A demo never points search engines or social previews at the real domain.
    base = "" if demo else (data["site"].get("base_url") or "").rstrip("/")
    problems, notes = [], []

    examples = [o["title"] for o in data["offers"] if o.get("status") == "example"]
    if examples:
        (problems if release else notes).append(
            f"{len(examples)} example offer(s) still in src/site.json: replace them with real offers or delete them.")
    unconfirmed = data.get("unconfirmed") or []
    if unconfirmed:
        (problems if release else notes).append(
            f"{len(unconfirmed)} thing(s) the store still has to confirm (the \"unconfirmed\" list in src/site.json, "
            "each with a matching item in README.md under Before launch). Delete an entry once the store has confirmed it.")
    if not base and not demo:
        (problems if release else notes).append(
            'site.base_url is empty: set it to the live address (for example "https://www.yourdomain.ca") for canonical links and the sitemap.')
    logos = Logos(data.get("carriers", []), placeholders)
    missing = [c["name"] for c in data.get("carriers", []) if c["id"] not in logos.files]
    if missing:
        notes.append(f"No official logo file yet for {', '.join(missing)}: add them to src/assets/img/brands/ "
                     "(bell, virgin-plus, lucky-mobile as .svg, .webp or .png).")
    if problems:
        for p in problems:
            print("STOP:", p)
        sys.exit(1)

    if dist.exists():
        shutil.rmtree(dist)
    copy_assets(design, dist)
    if demo:
        (dist / ".nojekyll").write_text("", encoding="utf-8")  # GitHub Pages: serve the files as they are
    else:
        (dist / "assets" / "css" / "demo.css").unlink(missing_ok=True)
        if (SRC / "_headers").exists():
            shutil.copy(SRC / "_headers", dist / "_headers")
    for css in (dist / "assets" / "css").glob("*.css"):
        css.write_text(minify_css(css.read_text(encoding="utf-8")), encoding="utf-8")

    digest = hashlib.sha1()
    for f in sorted((design["assets"] / "css").glob("*.css")) + sorted((SRC / "assets" / "js").glob("*.js")):
        if f.name == "demo.css" and not demo:
            continue
        digest.update(f.read_bytes())

    partials = {}
    for folder in design["partials"]:  # a design's own partials replace the shared ones of the same name
        partials.update({p.stem: p.read_text(encoding="utf-8") for p in folder.glob("*.html")})
    photos = Photos(design["photos"])
    module = load_module(design["module"]) if design["module"] else None
    summary, phrase = hours_text(data["hours"])
    form_action = data["site"].get("form_action") or ""
    form_attrs = (f'action="{esc(form_action)}"' if form_action
                  else 'action="thanks.html" data-netlify="true" netlify-honeypot="company"')
    if demo:
        form_attrs = 'action="thanks.html"'  # GitHub Pages can't receive forms; the thank-you page explains
    phone_link = f'<a href="tel:{esc(data["store"]["phone_e164"])}">{esc(data["store"]["phone_display"])}</a>'
    thanks = data.get("copy", {}).get("thanks", {})
    thanks_message = ((thanks.get("demo") or "This is a preview of the new website, so your request wasn't sent. To reach the store, call {phone}.")
                      if demo else
                      (thanks.get("live") or "We'll contact you at the number you gave us. If it's urgent, call the store at {phone}."))
    thanks_message = thanks_message.replace("{phone}", phone_link)
    demo_banner = ('\n<p class="demo-banner">Preview of the new T Wireless website. It isn\'t live yet, so forms here don\'t send.</p>'
                   if demo else "")

    ctx = dict(data)
    ctx.update({
        "year": datetime.date.today().year,
        "version": digest.hexdigest()[:8],
        "hours_summary": summary,
        "hours_phrase": phrase,
        "hours_json": hours_for_js(data["hours"]),
        "hours_rows": hours_rows(data["hours"]),
        "form_attrs": form_attrs,
        "thanks_message": thanks_message,
        "demo_banner": demo_banner,
        "jsonld": jsonld(data, base),
    })
    ctx["offers_all"] = "\n".join(offer_card(o, ctx, logos) for o in data["offers"])
    ctx["offers_preview"] = "\n".join(offer_card(o, ctx, logos) for o in data["offers"][:3])
    # While any offer is still an example, the Deals page says so in words, so its headline isn't read as a promise.
    ctx["offers_note"] = (
        '<div class="callout callout--examples"><p><strong>Sample offers.</strong> The cards below show the layout. '
        'The store’s real offers for the month will take their place.</p></div>'
        if any(o.get("status") == "example" for o in data["offers"]) else "")
    ctx["repairs_short"] = "\n".join(
        f'<li><svg class="icon" aria-hidden="true"><use href="#{esc(r.get("icon", "i-check"))}"></use></svg><span>{esc(r["title"])}</span></li>'
        for r in data["repairs"])
    ctx["repairs_full"] = "\n".join(
        f'<li><svg class="icon" aria-hidden="true"><use href="#{esc(r.get("icon", "i-wrench"))}"></use></svg>'
        f'<h3>{esc(r["title"])}</h3><p>{esc(render(r.get("text") or r.get("notice", ""), ctx, "repairs", escape=False))}</p></li>'
        for r in data["repairs"])
    ctx["faq_items"] = "\n".join(
        f'<details><summary>{esc(f["q"])}</summary><p>{esc(render(f["a"], ctx, "faq", escape=False))}</p></details>'
        for f in data["faq"])

    booking = data["site"].get("booking_url") or "visit.html#book"
    available = {p.name for p in design["pages"].glob("*.html")}  # which navigation entries this design has a page for
    kit = {"esc": esc, "render": render, "logos": logos, "photos": photos, "data": data, "nav": nav_entries(available),
           "day_span": day_span, "design": design, "demo": demo}
    built, sitemap = [], []
    for path in sorted(design["pages"].glob("*.html")):
        raw = path.read_text(encoding="utf-8")
        match = PAGE_META.match(raw)
        if not match:
            raise SystemExit(f"{path.name}: missing <!--page {{...}} --> header")
        meta = json.loads(match.group(1))
        page = {"body_class": "", "header_class": "", "nav": "",
                "logo_sizes": "(min-width: 900px) 260px, 200px"}
        page.update(meta)
        root = meta.get("root", "")
        if root == "/":
            root = base_path  # pages served from any path (the 404 page) link from the site's base path
        pctx = dict(ctx)
        pctx.update({
            "page": page,
            "root": root,
            "booking_href": booking if booking.startswith("http") else root + booking,
            "nav": nav_html(page["nav"], root, design["nav"], available),
            "footer_nav": footer_nav(root, design["nav"], available),
            "head_extra": head_extra(base, path.name, meta.get("noindex") or demo, design["og_image"], public_url),
            "sprite": partials["sprite"],
        })
        if switch:
            pctx["demo_banner"] = switch_banner(switch, design["label"], path.name)
        pctx["family_cards"] = brand_cards(data["family"], root, logos)
        pctx["mobile_cards"] = brand_cards(data["family"], root, logos, 3)
        pctx["carrier_strip"] = carrier_strip(data.get("carriers", []), logos, root)
        pctx["brand_mark"] = {
            b["id"].replace("-", "_"): (logos.plate(b["id"], root, alt="", cls="logo-plate detail__logo")
                                        or f'<span class="detail__icon"><svg class="icon" aria-hidden="true"><use href="#{esc(b["icon"])}"></use></svg></span>')
            for b in data["family"]}
        pctx["demo_head"] = (f'\n<link rel="stylesheet" href="{root}assets/css/demo.css?v={ctx["version"]}">' if demo else "")
        if module:
            pctx.update(module.extend(pctx, kit))
        pctx["storefront"] = render(partials["storefront"], pctx, "storefront")
        pctx["store_card"] = render(partials["store-card"], pctx, "store-card")
        pctx["map"] = render(partials["map"], pctx, "map")
        pctx["head"] = render(partials["head"], pctx, "head")
        pctx["header"] = render(partials["header"], pctx, "header")
        pctx["footer"] = render(partials["footer"], pctx, "footer")
        pctx["actionbar"] = render(partials["actionbar"], pctx, "actionbar")
        pctx["content"] = render(raw[match.end():], pctx, path.name)
        out = render(partials["base"], pctx, "base")
        out = re.sub(r"\b([ap])\.m\.\.", r"\1.m.", out)  # "8 p.m." at the end of a sentence
        if demo:
            out = out.replace('method="post"', 'method="get"')
        (dist / path.name).write_text(out, encoding="utf-8")
        built.append(path.name)
        if not meta.get("noindex"):
            sitemap.append("" if path.name == "index.html" else path.name)

    robots = "User-agent: *\nDisallow: /\n" if demo else "User-agent: *\nAllow: /\n"
    if base:
        robots += f"Sitemap: {base}/sitemap.xml\n"
        today = datetime.date.today().isoformat()
        urls = "\n".join(f"  <url><loc>{esc(base)}/{p}</loc><lastmod>{today}</lastmod></url>" for p in sitemap)
        (dist / "sitemap.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{urls}\n</urlset>\n', encoding="utf-8")
    (dist / "robots.txt").write_text(robots, encoding="utf-8")

    print(f"Built {len(built)} pages into {dist}: {', '.join(built)}")
    for n in notes:
        print("Before launch:", n)


if __name__ == "__main__":
    main()
