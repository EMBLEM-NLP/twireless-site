"""Design 2 ("In hand"): snippets the page templates use, added to each page's context by build.py.

Photos come from assets/img/photos/photos.json (rsi/imagery.py render). Carrier logos always sit on
white plates with clear space around them, whether on a photo or beside text. The wording of the
snippets built here (carrier lines, the deal button) comes from content.json, so it stays this
design's own.
"""
import re

# Which photo goes with which carrier, home service or offer.
CARRIER_PHOTO = {"bell": "two-phones", "virgin-plus": "concert", "lucky-mobile": "train"}
OFFER_PHOTO = {("Bell", "mobile"): "two-phones", ("Virgin Plus", "mobile"): "concert",
               ("Lucky Mobile", "mobile"): "train", ("Bell", "home"): "living-room",
               ("T Wireless", "repairs"): "cracked-screen"}
SIZES = {
    "hero": "(min-width: 900px) 480px, calc(100vw - 16px)",
    "provider": "(min-width: 900px) 360px, 40vw",
    "wide": "(min-width: 900px) 660px, calc(100vw - 32px)",
    "half": "(min-width: 900px) 560px, calc(100vw - 32px)",
    "card": "(min-width: 900px) 360px, calc(100vw - 32px)",
    "tile": "(min-width: 900px) 360px, calc(100vw - 32px)",
    "thumb": "104px",
}
ICON = '<svg class="icon" aria-hidden="true"><use href="#{0}"></use></svg>'


def icons_only(sprite):
    """Design 2 draws no illustrations, so the inline sprite keeps only the icons."""
    return re.sub(r'\s*<symbol id="art-[^"]*".*?</symbol>', "", sprite, flags=re.S)


def t_wireless_plate(root, cls):
    return (f'<span class="{cls} plate--t-wireless"><picture>'
            f'<source type="image/webp" srcset="{root}assets/img/t-wireless-logo-480.webp">'
            f'<img src="{root}assets/img/t-wireless-logo-480.png" width="480" height="55" alt="T Wireless" decoding="async"></picture></span>')


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
    plates_decorative = {cid.replace("-", "_"): plate(cid, alt="") for cid in logos.by_id}
    plates_on_photo = {cid.replace("-", "_"): plate(cid, alt="", cls="plate plate--on-photo") for cid in logos.by_id}
    plates_on_photo["t_wireless"] = t_wireless_plate(root, "plate plate--on-photo")

    # Three providers: a photo with the logo on it, then what each one is for.
    rows = []
    for c in data["carriers"]:
        cid = c["id"]
        rows.append(
            f'<li class="provider">\n'
            f'  <div class="provider__media">{pic(CARRIER_PHOTO[cid], "4x5", "provider", alt="")}{plate(cid, alt="", cls="plate plate--on-photo")}</div>\n'
            f'  <div class="provider__body">\n'
            f'    <h3 class="provider__name"><a href="{root}brands.html#{esc(cid)}">{esc(c["name"])}</a></h3>\n'
            f'    <p>{esc(copy["carrier_line"][cid])}</p>\n'
            f'  </div>\n'
            f'</li>')
    providers = '<ul class="providers">\n' + "\n".join(rows) + "\n</ul>"

    # The same three, as a compact list of logo plates with a short line each (no photographs), for pages
    # that already carry photographs of their own.
    short_rows = []
    for c in data["carriers"]:
        cid = c["id"]
        short_rows.append(
            f'<li class="name">\n'
            f'  {plate(cid, alt="")}\n'
            f'  <div class="name__body">\n'
            f'    <h3 class="name__title"><a href="{root}brands.html#{esc(cid)}">{esc(c["name"])}</a></h3>\n'
            f'    <p>{esc(copy["carrier_short"][cid])}</p>\n'
            f'  </div>\n'
            f'</li>')
    names = '<ul class="names">\n' + "\n".join(short_rows) + "\n</ul>"

    def deal(offer, with_photo, first=False):
        text = {k: kit["render"](str(offer.get(k, "")), p, "offer", escape=False)
                for k in ("brand", "title", "price", "detail", "terms")}
        carrier = logos.by_name.get(text["brand"])
        mark = (plate(carrier["id"], cls="plate plate--on-photo" if with_photo else "plate") if carrier
                else t_wireless_plate(root, "plate plate--on-photo" if with_photo else "plate"))
        example = offer.get("status") == "example"
        media = ""
        photo_id = OFFER_PHOTO.get((text["brand"], offer.get("category")))
        if with_photo and photo_id:
            crop = "16x9" if "16x9" in photos.m["photos"][photo_id]["crops"] else "16x10"
            media = f'  <div class="deal__media">{pic(photo_id, crop, "card", alt="", priority=first)}{mark}</div>\n'
        elif with_photo:
            media = f'  <div class="deal__media deal__media--plain">{mark}</div>\n'
        badge = '    <p class="deal__badge">Example offer</p>\n' if example else ""
        # An example card's terms are a note to the store ("Replace with this month's offer"), not something to show.
        terms = f'    <p class="deal__terms">{esc(text["terms"])}</p>\n' if text["terms"] and not example else ""
        head_mark = "" if with_photo else f"    {mark}\n"
        return (f'<article class="offer deal{" deal--example" if example else ""}" data-category="{esc(offer.get("category", "other"))}">\n'
                f'{media}'
                f'  <div class="deal__body">\n{head_mark}{badge}'
                f'    <h3 class="deal__title">{esc(text["title"])}</h3>\n'
                f'    <p class="deal__price">{esc(text["price"])}</p>\n'
                f'    <p class="deal__detail">{esc(text["detail"])}</p>\n{terms}'
                f'    <a class="button button--quiet" href="tel:{esc(phone)}">{esc(copy["deal_cta"])}</a>\n'
                f'  </div>\n</article>')

    # The three logos on one white bar along the foot of the hero photo.
    bar = "".join(f'<li>{logos.plate(cid, root, cls="mark") or esc(logos.by_id[cid]["name"])}</li>'
                  for cid in ("bell", "virgin-plus", "lucky-mobile"))
    hero_plates = f'<div class="hero__plates"><p class="hero__plates-label">Plans from</p><ul>{bar}</ul></div>'
    # The same three logos on a plate of their own, for the top of the Compare plans page.
    provider_strip = f'<div class="provider-strip"><ul>{bar}</ul></div>'

    repair_items = "\n".join(
        f'<li>{ICON.format(esc(r.get("icon", "i-wrench")))}<div><h3>{esc(r["title"])}</h3>'
        f'<p>{esc(kit["render"](r["text"], p, "repairs", escape=False))}</p></div></li>' for r in data["repairs"])
    repair_names = "\n".join(
        f'<li>{ICON.format(esc(r.get("icon", "i-check")))}<span>{esc(r["title"])}</span></li>' for r in data["repairs"])

    credits = []
    for c in photos.credits():
        credits.append(
            f'<li class="credit">\n'
            f'  {pic(c["id"], next(iter(photos.m["photos"][c["id"]]["crops"])), "thumb", alt="")}\n'
            f'  <div><p class="credit__what">{esc(c["alt"])}</p>\n'
            f'  <p>Photo by <a href="{esc(c["author_url"] or c["page_url"])}">{esc(c["author"])}</a> on '
            f'<a href="{esc(c["page_url"])}">{esc(c["provider"])}</a>, used under the '
            f'<a href="{esc(c["license_url"])}">{esc(c["license"])}</a>.</p></div>\n'
            f'</li>')

    # While any offer is still an example, the Offers page says so in words, so that its headline is not read as a promise.
    example_note = ""
    if any(o.get("status") == "example" for o in data["offers"]):
        example_note = ('<p class="notice notice--example"><strong>These are examples.</strong> The cards show how an offer '
                        'will look. The store\u2019s own offers will replace them.</p>')

    return {
        "example_note": example_note,
        "sprite": icons_only(p["sprite"]),
        "plate": plates,
        "plate_deco": plates_decorative,
        "plate_photo": plates_on_photo,
        "providers": providers,
        "names": names,
        "deals_preview": "\n".join(deal(o, False) for o in data["offers"][:3]),
        "deals_all": "\n".join(deal(o, True, first=(i == 0)) for i, o in enumerate(data["offers"])),
        "repair_items": repair_items,
        "repair_names": repair_names,
        "credits_list": "\n".join(credits),
        "hero_plates": hero_plates,
        "provider_strip": provider_strip,
        "pic": {
            "hero": pic("hand-blue-phone", "4x5", "hero", cls="hero__photo", priority=True),
            "living_wide": pic("living-room", "16x10", "wide"),
            "family_wide_top": pic("family-tv", "16x10", "wide", priority=True),
            "repair_wide": pic("repair-mat", "16x10", "wide"),
            "repair_wide_top": pic("repair-mat", "16x10", "wide", priority=True),
            "cracked_tile": pic("cracked-screen", "1x1", "tile"),
            "seniors_wide_top": pic("seniors-phone", "16x10", "wide", priority=True),
            "new_phones_wide": pic("unboxing", "16x10", "half"),
            "video_call_wide": pic("video-call", "16x10", "half"),
            "cafe_wide": pic("cafe-business", "16x10", "half"),
            "train_half": pic("train", "16x9", "half", alt=""),
            "card_bell": pic("two-phones", "16x9", "card", alt=""),
            "card_virgin": pic("concert", "16x9", "card", alt=""),
            "card_lucky": pic("train", "16x9", "card", alt=""),
            "half_home": pic("living-room", "16x9", "half", alt=""),
            "half_team": pic("unboxing", "16x10", "half", alt=""),
        },
    }
