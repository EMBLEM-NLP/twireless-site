"""Design 3 ("Lamplight"): snippets the page templates use, added to each page's context by build.py.

Photos come from assets/img/photos/photos.json (rsi/imagery.py render); the engine-turned ornaments
in assets/img/ornaments/ are drawn by imagery/ornaments.py. Carrier logos always sit on pearl
"mount cards" (rgb 247, 246, 245: never on a photograph and never on the dark page), whatever the
surroundings. The store's own wordmark is different: it is drawn in a champagne-gold version
(imagery/logo_light.py) straight onto the dark page, with no card.

Phones get a bottom tab bar instead of a header menu: Home, Phones, Repairs and Visit sit in the bar and
the three other pages open from its More button (the shared menu script drives it: the bar carries
data-menu). From 900px up the header shows a centred masthead over a row of links instead.
"""
import re

# Sizes hints for the browser: how wide each kind of picture is drawn.
SIZES = {
    "hero": "(min-width: 900px) 64vw, 100vw",
    "tall": "(min-width: 900px) 480px, calc(100vw - 40px)",
    "half": "(min-width: 900px) 600px, calc(100vw - 40px)",
    "tile": "(min-width: 900px) 270px, calc(50vw - 27px)",
    "thumb": "104px",
}
ICON = '<svg class="icon" aria-hidden="true"><use href="#{0}"></use></svg>'

# Icons this design adds to the shared sprite (same 24px, 2px-stroke drawing style).
EXTRA_ICONS = (
    '<symbol id="i-house" viewBox="0 0 24 24"><path fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" d="M3.5 11 12 4l8.5 7v9.5h-17z"/>'
    '<path fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" d="M9.5 20.5V14h5v6.5"/></symbol>'
    '<symbol id="i-tag" viewBox="0 0 24 24"><path fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" d="M3.5 12.2V4.5a1 1 0 0 1 1-1h7.7a1 1 0 0 1 .7.3l7.6 7.6a1 1 0 0 1 0 1.4l-7.3 7.3a1 1 0 0 1-1.4 0l-7.6-7.6a1 1 0 0 1-.7-.7z"/>'
    '<circle cx="8" cy="8" r="1.4" fill="currentColor"/></symbol>'
    '<symbol id="i-more" viewBox="0 0 24 24"><circle cx="5" cy="12" r="1.7" fill="currentColor"/><circle cx="12" cy="12" r="1.7" fill="currentColor"/><circle cx="19" cy="12" r="1.7" fill="currentColor"/></symbol>'
)

# One order everywhere (Home, Phones, Plans, Home services, Repairs, Offers, Visit): the header row on wide screens,
# the bar on phones (four of them, then More), the More sheet (the rest) and the footer all follow it.
# The header row on wide screens: (page key, label).
WIDE_NAV = [("mobile", "Phones"), ("brands", "Plans"), ("internet-tv", "Home services"), ("repairs", "Repairs"),
            ("deals", "Offers"), ("visit", "Visit")]
# The bar on phones: (page key, label, icon). Everything else opens from More: (page key, label, note).
DECK_TABS = [("index", "Home", "i-house"), ("mobile", "Phones", "i-phone"), ("repairs", "Repairs", "i-wrench"),
             ("visit", "Visit", "i-pin")]
DECK_MORE = [("brands", "Plans", "Bell, Virgin Plus or Lucky Mobile"),
             ("internet-tv", "Home services", "Internet, TV and a home phone line"),
             ("deals", "Offers", "Deals, and ways to pay")]
# The order the Offers page shows its groups in: (category in src/site.json, heading).
OFFER_GROUPS = [("mobile", "Phones and plans"), ("home", "Home internet"), ("repairs", "Repairs")]


def icons_only(sprite):
    """Design 3 draws no illustrations, so the inline sprite keeps only the icons (plus the few drawn here)."""
    sprite = re.sub(r'\s*<symbol id="art-[^"]*".*?</symbol>', "", sprite, flags=re.S)
    return sprite.replace("</svg>", EXTRA_ICONS + "</svg>", 1)


def t_wireless_mark(root, cls="mark"):
    """The store's own wordmark, in the champagne-gold version made for the dark page (no card behind it)."""
    return (f'<span class="{cls}"><picture>'
            f'<source type="image/webp" srcset="{root}assets/img/t-wireless-logo-light-480.webp 480w, {root}assets/img/t-wireless-logo-light-960.webp 960w" sizes="192px">'
            f'<img src="{root}assets/img/t-wireless-logo-light-480.png" srcset="{root}assets/img/t-wireless-logo-light-480.png 480w, {root}assets/img/t-wireless-logo-light-960.png 960w" sizes="192px" width="480" height="55" alt="T Wireless" decoding="async">'
            f'</picture></span>')


def extend(p, kit):
    esc, logos, photos, data = kit["esc"], kit["logos"], kit["photos"], kit["data"]
    root = p["root"]
    store = p["store"]
    phone = store["phone_e164"]
    here = p["page"].get("nav", "")

    def pic(pid, crop, size, cls="", alt=None, priority=False):
        return photos.picture(pid, crop, root, SIZES[size], alt=alt, cls=cls, priority=priority)

    def plate(cid, alt=None, cls="plate"):
        return logos.plate(cid, root, alt=alt, cls=cls) or f'<span class="{cls} plate--text">{esc(logos.by_id[cid]["name"])}</span>'

    # The opening hours as a phrase whose time range never breaks across two lines ("8 / p.m.").
    hours_nb = re.sub(r"(\d{1,2}(?::\d{2})?\s[ap]\.m\. to \d{1,2}(?::\d{2})?\s[ap]\.m\.)", r'<span class="nb">\1</span>',
                      esc(p["hours_phrase"]))

    plates = {cid.replace("-", "_"): plate(cid) for cid in logos.by_id}
    plates["t_wireless"] = t_wireless_mark(root)
    plates_decorative = {cid.replace("-", "_"): plate(cid, alt="") for cid in logos.by_id}

    # Navigation. Wide screens: a row of links under the masthead. Phones: a bottom bar of four pages and a
    # More button whose sheet holds the rest, the live open/closed line and the two calls to action.
    def current(key):
        return ' aria-current="page"' if key == here else ""

    wide = "<ul>\n" + "\n".join(
        f'<li><a href="{root}{key}.html"{current(key)}>{esc(label)}</a></li>' for key, label in WIDE_NAV) + "\n</ul>"
    footer_links = "\n".join(
        f'<li><a href="{root}{key}.html">{esc(label)}</a></li>'
        for key, label in [("index", "Home")] + WIDE_NAV)
    tabs = "".join(
        f'<li><a class="deck__tab" href="{root}{key}.html"{current(key)}>{ICON.format(icon)}<span>{esc(label)}</span></a></li>'
        for key, label, icon in DECK_TABS)
    more_here = here in {key for key, _, _ in DECK_MORE}
    more_button = (f'<li><button class="deck__tab deck__more{" is-current" if more_here else ""}" type="button" '
                   f'aria-expanded="false" aria-controls="site-menu" data-menu-toggle>{ICON.format("i-more")}<span>More</span></button></li>')
    sheet_rows = "".join(
        f'<li><a href="{root}{key}.html"{current(key)}><span class="menu__name">{esc(label)}</span>'
        f'<span class="menu__note">{esc(note)}</span></a></li>' for key, label, note in DECK_MORE)
    deck_items = tabs + more_button
    deck_sheet = (
        f'<div class="menu" id="site-menu"><ul class="menu__list">{sheet_rows}</ul>'
        f'<div class="menu__foot"><p class="status" data-hours="{esc(p["hours_json"])}" data-tz="{esc(p["site"]["timezone"])}">'
        f'<span class="status__sign is-pending">Open</span><span class="status__text">{esc(p["hours_summary"])}</span></p>'
        f'<div class="buttons"><a class="button" href="tel:{esc(phone)}">{ICON.format("i-call")}Call {esc(store["phone_display"])}</a>'
        f'<a class="button button--line" href="{esc(store["directions_url"])}">Get directions</a></div></div></div>')

    # The three plan brands as three pearl cards in a row, each a link to its entry on the Plans page.
    cards = "".join(
        f'<li><a class="plate-link" href="{root}brands.html#{cid}">{plate(cid, cls="plate plate--chip")}</a></li>'
        for cid in ("bell", "virgin-plus", "lucky-mobile"))
    provider_strip = f'<div class="provider-strip"><ul>{cards}</ul></div>'
    hero_plates = (f'<div class="hero__plates"><p class="hero__plates-label" id="plans-from">Plans from</p>'
                   f'<ul aria-labelledby="plans-from">{cards}</ul></div>')

    # The Offers page: one list per kind of offer, each row a logo card, the offer, and its price.
    def deal(offer):
        text = {k: kit["render"](str(offer.get(k, "")), p, "offer", escape=False)
                for k in ("brand", "title", "price", "detail", "terms")}
        carrier = logos.by_name.get(text["brand"])
        mark = plate(carrier["id"]) if carrier else t_wireless_mark(root)
        example = offer.get("status") == "example"
        badge = '    <p class="offer__badge">Example offer</p>\n' if example else ""
        # An example's terms are a note to the store ("Replace with this month's offer"), not something to show.
        terms = f'    <p class="offer__terms">{esc(text["terms"])}</p>\n' if text["terms"] and not example else ""
        return (f'<li class="offer{" offer--example" if example else ""}">\n'
                f'  <div class="offer__mark">{mark}</div>\n'
                f'  <div class="offer__body">\n'
                f'    <h3 class="offer__title">{esc(text["title"])}</h3>\n'
                f'    <p class="offer__detail">{esc(text["detail"])}</p>\n{terms}{badge}'
                f'  </div>\n'
                f'  <p class="offer__price">{esc(text["price"])}</p>\n'
                f'</li>')

    groups = []
    seen = set()
    for cat, heading in OFFER_GROUPS + [(None, "More offers")]:
        rows = [o for o in data["offers"] if (o.get("category", "other") == cat if cat else o.get("category", "other") not in seen)]
        if not rows:
            continue
        if cat:
            seen.add(cat)
        gid = f"board-{cat or 'more'}"
        groups.append(f'<section class="board__group" aria-labelledby="{gid}">\n<h2 id="{gid}">{esc(heading)}</h2>\n'
                      f'<ul class="board__list">\n' + "\n".join(deal(o) for o in rows) + "\n</ul>\n</section>")
    deals_board = '<div class="board">\n' + "\n".join(groups) + "\n</div>"

    repair_items = "\n".join(
        f'<li>{ICON.format(esc(r.get("icon", "i-wrench")))}<div><h3>{esc(r["title"])}</h3>'
        f'<p>{esc(kit["render"](r["text"], p, "repairs", escape=False))}</p></div></li>' for r in data["repairs"])

    credits = []
    for c in photos.credits():
        entry = photos.m["photos"][c["id"]]
        changed = entry.get("retouched") or []
        change = (f'\n  <p>Changed: {esc("; ".join(x[0].lower() + x[1:] for x in changed))}, removed.</p>' if changed else "")
        credits.append(
            f'<li class="credit">\n'
            f'  {pic(c["id"], next(iter(entry["crops"])), "thumb", alt="")}\n'
            f'  <div><p class="credit__what">{esc(c["alt"])}</p>\n'
            f'  <p>Photographer: <a href="{esc(c["author_url"] or c["page_url"])}">{esc(c["author"])}</a>{"" if c["author"].endswith(".") else "."} '
            f'Source: <a href="{esc(c["page_url"])}">{esc(c["provider"])}</a>. '
            f'Licence: <a href="{esc(c["license_url"])}">{esc(c["license"])}</a>.</p>{change}</div>\n'
            f'</li>')

    # The hallmark: an engine-turned disc with the store's initial. It carries no words, so it claims nothing.
    seal = (
        '<svg class="seal" viewBox="0 0 160 160" aria-hidden="true" focusable="false">'
        '<circle cx="80" cy="80" r="79" fill="#150a0e" fill-opacity=".78" stroke="#dcbd88" stroke-opacity=".7"/>'
        f'<image href="{root}assets/img/ornaments/seal-lines.svg" x="14" y="14" width="132" height="132" opacity=".9"/>'
        '<circle cx="80" cy="80" r="66" fill="none" stroke="#dcbd88" stroke-opacity=".55" stroke-width=".7"/>'
        '<circle cx="80" cy="80" r="40" fill="#150a0e" fill-opacity=".72" stroke="#dcbd88" stroke-opacity=".6" stroke-width=".7"/>'
        '<text x="80" y="97" text-anchor="middle" font-family="Noto Serif Display, Georgia, serif" font-size="52" font-style="italic" fill="#dcbd88">T</text>'
        '</svg>')

    # While any offer is still an example, the Offers page says so in words, not only on each row, so that its
    # headline is not read as a promise. A build with real offers carries no note.
    example_note = ""
    if any(o.get("status") == "example" for o in data["offers"]):
        example_note = ('<p class="notice notice--example"><strong>Samples only.</strong> The entries below hold the place of '
                        'real offers. None of them is live.</p>')

    return {
        "nav": wide,
        "footer_nav": footer_links,
        "deck_items": deck_items,
        "deck_sheet": deck_sheet,
        "example_note": example_note,
        "hours_nb": hours_nb,
        "sprite": icons_only(p["sprite"]),
        "plate": plates,
        "plate_deco": plates_decorative,
        "deals_board": deals_board,
        "repair_items": repair_items,
        "credits_list": "\n".join(credits),
        "hero_plates": hero_plates,
        "provider_strip": provider_strip,
        "seal": seal,
        "pic": {
            "hero": pic("hand-black", "4x3", "hero", cls="hero__photo", priority=True),
            "phones_top": pic("wood-garnet", "4x5", "tall", priority=True),
            "living_top": pic("tv-wall", "4x5", "tall", priority=True),
            "house": pic("house-dusk", "4x5", "tall"),
            "repair_top": pic("internals", "16x10", "half", priority=True),
            "marble_top": pic("marble-gold", "4x5", "tall", alt="", priority=True),
            "amber_top": pic("bokeh-amber", "4x5", "tall", alt="", priority=True),
            "tile_phones": pic("wood-garnet", "1x1", "tile", alt=""),
            "tile_home": pic("tv-wall", "1x1", "tile", alt=""),
            "tile_repairs": pic("internals", "1x1", "tile", alt=""),
            "tile_offers": pic("marble-gold", "1x1", "tile", alt=""),
        },
    }
