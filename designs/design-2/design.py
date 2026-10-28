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
    "provider": "(min-width: 900px) 360px, 40vw",
    "wide": "(min-width: 900px) 660px, calc(100vw - 32px)",
    "half": "(min-width: 900px) 560px, calc(100vw - 32px)",
    "card": "(min-width: 900px) 360px, calc(100vw - 32px)",
    "tile": "(min-width: 900px) 360px, calc(100vw - 32px)",
    "thumb": "104px",
    # A card on the Deals page is a row with a small photo on a phone and a full card from 600px up.
    "dealcard": "(min-width: 1100px) 360px, (min-width: 900px) 400px, (min-width: 600px) calc(50vw - 40px), 120px",
    # The store's own offer stacks on a phone, so its photo runs the full width of the card there.
    "dealown": "(min-width: 1100px) 360px, (min-width: 900px) 400px, (min-width: 600px) calc(50vw - 40px), calc(100vw - 32px)",
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
        photo_id = OFFER_PHOTO.get((text["brand"], offer.get("category"))) if with_photo else None
        # A carrier's logo sits on its photo (a hand, a crowd, a room: nobody recognisable). The store's own wordmark
        # never goes over a stock photo, which would make the photo look like the shop's own work; it heads the card,
        # as does any logo on an offer that has no photo.
        on_photo = bool(photo_id) and carrier is not None
        if carrier:
            mark = plate(carrier["id"], cls="plate plate--on-photo" if on_photo else "plate")
        else:
            mark = t_wireless_plate(root, "plate")
        example = offer.get("status") == "example"
        media = ""
        if photo_id:
            crop = "16x9" if "16x9" in photos.m["photos"][photo_id]["crops"] else "16x10"
            media = f'  <div class="deal__media">{pic(photo_id, crop, "dealcard" if carrier else "dealown", alt="", priority=first)}{mark if on_photo else ""}</div>\n'
        badge = '    <p class="deal__badge">Example offer</p>\n' if example else ""
        # An example card's terms are a note to the store ("Replace with this month's offer"), not something to show.
        terms = f'    <p class="deal__terms">{esc(text["terms"])}</p>\n' if text["terms"] and not example else ""
        head_mark = "" if on_photo else f"    {mark}\n"
        own = " deal--own" if carrier is None else ""
        return (f'<article class="offer deal{own}{" deal--example" if example else ""}" data-category="{esc(offer.get("category", "other"))}">\n'
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

    # The repair list as table rows: the fault, what you notice, what the store does about it. On a phone the
    # table's CSS stacks each row into a card, so every cell carries its column name in data-label.
    repair_rows = "\n".join(
        f'<tr><th scope="row">{esc(r["title"])}</th>'
        f'<td data-label="You notice">{esc(kit["render"](r["notice"], p, "repairs", escape=False))}</td>'
        f'<td data-label="We do">{esc(kit["render"](r["fix"], p, "repairs", escape=False))}</td></tr>' for r in data["repairs"])

    # The home page photo: a phone in a hand, cut three ways. A phone gets a 5:4 crop with the phone right of
    # centre (the open/closed chip sits in the sky to its left), a tablet the full banner (2:1), a desktop a square
    # around the phone beside the headline, and a phone on its side the 5:4 crop beside the headline.
    hero_photo = photos.picture(
        "foldable-in-hand", "5x4", root, "calc(100vw - 16px)", cls="hero__photo", priority=True,
        art=[("(max-width: 899px) and (max-height: 500px) and (orientation: landscape)", "5x4", "calc(50vw - 40px)"),
             ("(min-width: 900px)", "1x1", "(min-width: 1100px) 443px, 42vw"),
             ("(min-width: 600px)", "2x1", "calc(100vw - 16px)")])

    credits, supplied, generated = [], False, False
    for c in photos.credits():
        if c["provider"] == "Supplied by the client":
            supplied = True
            if c.get("ai_generated"):
                generated = True
                by = ('<p>An AI-generated image, supplied for this preview. Which tool made it, and what that tool’s terms '
                      'allow, are not confirmed yet, so it will be replaced or cleared before the site goes live.</p>')
            else:
                by = ('<p>Supplied for this preview. Where it came from and what it may be used for are not confirmed yet, '
                      'so it will be replaced or cleared before the site goes live.</p>')
        else:
            by = (f'<p>Photo by <a href="{esc(c["author_url"] or c["page_url"])}">{esc(c["author"])}</a> on '
                  f'<a href="{esc(c["page_url"])}">{esc(c["provider"])}</a>, used under the '
                  f'<a href="{esc(c["license_url"])}">{esc(c["license"])}</a>.</p>')
        credits.append(
            f'<li class="credit">\n'
            f'  {pic(c["id"], next(iter(photos.m["photos"][c["id"]]["crops"])), "thumb", alt="")}\n'
            f'  <div><p class="credit__what">{esc(c["alt"])}</p>\n'
            f'  {by}</div>\n'
            f'</li>')
    if generated:
        credits_lead = ("Every photo on this website is a stock photo, apart from one AI-generated image on the home page, marked "
                        "below. None of them shows our store, our staff or our customers. Thank you to the photographers who "
                        "share their work.")
    elif supplied:
        credits_lead = ("Every photo on this website is a stock photo, apart from the one marked as supplied. None of them shows "
                        "our store, our staff or our customers. Thank you to the photographers who share their work.")
    else:
        credits_lead = ("Every photo on this website is a stock photo, so none of them show our store, our staff or our customers. "
                        "Thank you to the photographers who share their work.")
    credits_note = ("We cropped and resized the photos, and lightly colour-matched most of them. In some of them we also removed small "
                    "printed brand names, logos and emblems, and a phone picture printed on a retail carton: on phones and a phone case, "
                    "a card, a repair mat and its parts, a shirt, a wristband, a ticket machine and a carton. We set the Bell, Virgin Plus "
                    "and Lucky Mobile logos on white plates over some of the photos. Bell, Virgin Plus and Lucky Mobile are trademarks of "
                    "their respective owners."
                    + (f" The app icons and widgets on the screen of the phone in the home page {'image' if generated else 'photo'} "
                       "belong to their respective owners." if supplied else ""))
    # The footer's one-line disclosure about the photos stays true while a supplied or generated picture is on the home page.
    if generated:
        footer_photos = ("Our pictures are stock photos and one AI-generated image, so none of them show the store, our staff "
                         "or our customers.")
    elif supplied:
        footer_photos = "Our photos are stock or supplied images, so none of them show the store, our staff or our customers."
    else:
        footer_photos = "Our photos are stock photos, so none of them show the store, our staff or our customers."

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
        "deals_all": "\n".join(deal(o, True) for o in data["offers"]),
        "repair_rows": repair_rows,
        "credits_list": "\n".join(credits),
        "credits_lead": credits_lead,
        "credits_note": credits_note,
        "footer_photos": footer_photos,
        "hero_plates": hero_plates,
        "provider_strip": provider_strip,
        "pic": {
            "hero": hero_photo,
            "living_wide": pic("living-room", "16x10", "wide"),
            "hand_bill": pic("seniors-phone", "16x10", "card", alt=""),
            "hand_repair": pic("cracked-screen", "16x9", "card", alt=""),
            "hand_home": pic("living-room", "16x10", "card", alt=""),
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
