"""Design 3 ("Lamplight"): snippets the page templates use, added to each page's context by build.py.

Photos come from assets/img/photos/photos.json (rsi/imagery.py render); the engine-turned ornaments
in assets/img/ornaments/ are drawn by imagery/ornaments.py. Carrier logos always sit on pearl
"mount cards" (rgb 247, 246, 245: never on a photograph and never on the dark page), whatever the
surroundings. The store's own wordmark is different: it is drawn in a one-colour champagne version
(imagery/logo_light.py) straight onto the dark page, with no card. The wording of the snippets built here (carrier lines, the offer button) comes from
content.json, so it stays this design's own.
"""
import re

# Sizes hints for the browser: how wide each kind of picture is drawn.
SIZES = {
    "hero": "(min-width: 900px) 64vw, 100vw",
    "tall": "(min-width: 900px) 480px, calc(100vw - 60px)",
    "pair": "(min-width: 900px) 320px, calc(50vw - 40px)",
    "half": "(min-width: 900px) 600px, calc(100vw - 60px)",
    "band": "100vw",
    "thumb": "104px",
}
ICON = '<svg class="icon" aria-hidden="true"><use href="#{0}"></use></svg>'


def icons_only(sprite):
    """Design 3 draws no illustrations, so the inline sprite keeps only the icons."""
    return re.sub(r'\s*<symbol id="art-[^"]*".*?</symbol>', "", sprite, flags=re.S)


def t_wireless_mark(root, cls="mark"):
    """The store's own wordmark, in the one-colour champagne version made for the dark page (no card behind it)."""
    return (f'<span class="{cls}"><picture>'
            f'<source type="image/webp" srcset="{root}assets/img/t-wireless-logo-light-480.webp 480w, {root}assets/img/t-wireless-logo-light-960.webp 960w" sizes="192px">'
            f'<img src="{root}assets/img/t-wireless-logo-light-480.png" srcset="{root}assets/img/t-wireless-logo-light-480.png 480w, {root}assets/img/t-wireless-logo-light-960.png 960w" sizes="192px" width="480" height="55" alt="T Wireless" decoding="async">'
            f'</picture></span>')


def extend(p, kit):
    esc, logos, photos, data = kit["esc"], kit["logos"], kit["photos"], kit["data"]
    root = p["root"]
    phone = p["store"]["phone_e164"]
    copy = data["copy"]

    def pic(pid, crop, size, cls="", alt=None, priority=False):
        return photos.picture(pid, crop, root, SIZES[size], alt=alt, cls=cls, priority=priority)

    def plate(cid, alt=None, cls="plate"):
        return logos.plate(cid, root, alt=alt, cls=cls) or f'<span class="{cls} plate--text">{esc(logos.by_id[cid]["name"])}</span>'

    plates = {cid.replace("-", "_"): plate(cid) for cid in logos.by_id}
    plates["t_wireless"] = t_wireless_mark(root)
    plates_decorative = {cid.replace("-", "_"): plate(cid, alt="") for cid in logos.by_id}

    # The three providers on the home page: a pearl card with the logo, then what each one is for.
    rows = []
    for c in data["carriers"]:
        cid = c["id"]
        rows.append(
            f'<li class="provider">\n'
            f'  {plate(cid, alt="", cls="plate plate--band")}\n'
            f'  <div class="provider__body">\n'
            f'    <h3 class="provider__name"><a href="{root}brands.html#{esc(cid)}">{esc(c["name"])}</a></h3>\n'
            f'    <p>{esc(copy["carrier_line"][cid])}</p>\n'
            f'  </div>\n'
            f'</li>')
    providers = '<ul class="providers">\n' + "\n".join(rows) + "\n</ul>"

    def deal(offer):
        text = {k: kit["render"](str(offer.get(k, "")), p, "offer", escape=False)
                for k in ("brand", "title", "price", "detail", "terms")}
        carrier = logos.by_name.get(text["brand"])
        mark = plate(carrier["id"]) if carrier else t_wireless_mark(root)
        example = offer.get("status") == "example"
        badge = '    <p class="offer__badge">Example offer</p>\n' if example else ""
        # An example card's terms are a note to the store ("Replace with this month's offer"), not something to show.
        terms = f'    <p class="offer__terms">{esc(text["terms"])}</p>\n' if text["terms"] and not example else ""
        return (f'<article class="offer{" offer--example" if example else ""}" data-category="{esc(offer.get("category", "other"))}">\n'
                f'  <div class="offer__top">{mark}\n{badge}  </div>\n'
                f'  <h3 class="offer__title">{esc(text["title"])}</h3>\n'
                f'  <p class="offer__price">{esc(text["price"])}</p>\n'
                f'  <p class="offer__detail">{esc(text["detail"])}</p>\n{terms}'
                f'  <a class="button button--line" href="tel:{esc(phone)}">{esc(copy["deal_cta"])}</a>\n'
                f'</article>')

    # The three logos in a row, each on its own pearl card: under the home headline, and on the Providers page.
    cards = "".join(f'<li>{plate(cid, cls="plate plate--chip")}</li>' for cid in ("bell", "virgin-plus", "lucky-mobile"))
    hero_plates = f'<div class="hero__plates"><p class="hero__plates-label" id="plans-from">Plans from</p><ul aria-labelledby="plans-from">{cards}</ul></div>'
    provider_strip = f'<div class="provider-strip"><ul>{cards}</ul></div>'

    repair_items = "\n".join(
        f'<li>{ICON.format(esc(r.get("icon", "i-wrench")))}<div><h3>{esc(r["title"])}</h3>'
        f'<p>{esc(kit["render"](r["text"], p, "repairs", escape=False))}</p></div></li>' for r in data["repairs"])
    repair_names = "\n".join(
        f'<li>{ICON.format(esc(r.get("icon", "i-check")))}<span>{esc(r["title"])}</span></li>' for r in data["repairs"])

    credits = []
    for c in photos.credits():
        entry = photos.m["photos"][c["id"]]
        changed = entry.get("retouched") or []
        change = (f'\n  <p>Changed: {esc("; ".join(x[0].lower() + x[1:] for x in changed))}, removed.</p>' if changed else "")
        credits.append(
            f'<li class="credit">\n'
            f'  {pic(c["id"], next(iter(entry["crops"])), "thumb", alt="")}\n'
            f'  <div><p class="credit__what">{esc(c["alt"])}</p>\n'
            f'  <p>Photographer: <a href="{esc(c["author_url"] or c["page_url"])}">{esc(c["author"])}</a>. '
            f'Source: <a href="{esc(c["page_url"])}">{esc(c["provider"])}</a>. '
            f'Licence: <a href="{esc(c["license_url"])}">{esc(c["license"])}</a>.</p>{change}</div>\n'
            f'</li>')

    # The hallmark: an engine-turned disc with the store's description set round its rim.
    seal = (
        '<svg class="seal" viewBox="0 0 160 160" aria-hidden="true" focusable="false">'
        '<defs><path id="seal-ring" d="M80 80m-60 0a60 60 0 1 1 120 0a60 60 0 1 1-120 0"/></defs>'
        '<circle cx="80" cy="80" r="79" fill="#150a0e" fill-opacity=".78" stroke="#dcbd88" stroke-opacity=".7"/>'
        f'<image href="{root}assets/img/ornaments/seal-lines.svg" x="22" y="22" width="116" height="116" opacity=".85"/>'
        '<circle cx="80" cy="80" r="70" fill="none" stroke="#dcbd88" stroke-opacity=".55" stroke-width=".7"/>'
        '<circle cx="80" cy="80" r="47" fill="#150a0e" fill-opacity=".55" stroke="#dcbd88" stroke-opacity=".6" stroke-width=".7"/>'
        '<text x="80" y="98" text-anchor="middle" font-family="Noto Serif Display, Georgia, serif" font-size="54" font-style="italic" fill="#dcbd88">T</text>'
        '<text font-family="Noto Serif Display, Georgia, serif" font-size="9.6" font-style="italic" fill="#dcbd88">'
        '<textPath href="#seal-ring" textLength="352" lengthAdjust="spacing">Bell Authorised Retailer in Brampton</textPath></text>'
        '</svg>')

    # While any offer is still an example, the Offers page says so in words, not only on each card, so that its
    # headline is not read as a promise. A build with real offers carries no note.
    example_note = ""
    if any(o.get("status") == "example" for o in data["offers"]):
        example_note = ('<p class="notice notice--example"><strong>Examples only.</strong> Nothing below is a live offer. Each card '
                        'is a stand-in, to be replaced by whatever the store is promoting that month.</p>')

    return {
        "example_note": example_note,
        "sprite": icons_only(p["sprite"]),
        "plate": plates,
        "plate_deco": plates_decorative,
        "providers": providers,
        "deals_preview": "\n".join(deal(o) for o in data["offers"][:3]),
        "deals_all": "\n".join(deal(o) for o in data["offers"]),
        "repair_items": repair_items,
        "repair_names": repair_names,
        "credits_list": "\n".join(credits),
        "hero_plates": hero_plates,
        "provider_strip": provider_strip,
        "seal": seal,
        "pic": {
            "hero": pic("candle-phone", "4x3", "hero", cls="hero__photo", priority=True),
            "wood": pic("wood-garnet", "16x9", "half"),
            "living": pic("tv-wall", "4x5", "pair"),
            "house": pic("house-dusk", "4x5", "pair"),
            "living_top": pic("tv-wall", "4x5", "tall", priority=True),
            "house_tall": pic("house-dusk", "4x5", "tall"),
            "handset_top": pic("hand-black", "4x5", "tall", priority=True),
            "rings_top": pic("mono-rings", "4x5", "tall", priority=True),
            "repair_half": pic("internals", "16x10", "half"),
            "repair_top": pic("internals", "16x10", "half", priority=True),
            "bench": pic("bench-lamp", "4x5", "tall"),
            "marble": pic("marble-gold", "16x9", "band", alt=""),
            "marble_top": pic("marble-gold", "16x9", "band", alt="", priority=True),
            "garnet": pic("bokeh-garnet", "21x9", "band", alt=""),
            "amber": pic("bokeh-amber", "21x9", "band", alt=""),
            "amber_top": pic("bokeh-amber", "21x9", "band", alt="", priority=True),
        },
    }
