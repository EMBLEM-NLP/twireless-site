# T Wireless website

The website for T Wireless, Bell Authorised Retailer, 965 Bovaird Dr W, Unit 1, Brampton.
Prepared by EMBLEM-NLP (Romar Johnson), October 26, 2026.

Store details come from the T Wireless business card: Ali, 647-707-1093, twireless965@gmail.com, www.twireless.ca, 965 Bovaird Dr. West, Unit 1.

## What's in this folder

| Path | What it is |
| --- | --- |
| `dist/` | The finished website. Upload this folder to your host. Built by `build.py`, not stored in git. |
| `docs/` | The public demo that GitHub Pages serves, built with `--demo`. |
| `src/site.json` | Store details, hours, the Bell family cards, offers, repairs and FAQ. Most edits happen here. |
| `src/pages/` | The copy for each page. |
| `src/partials/` | Shared parts: header, footer, storefront illustration, store card, map, icons, phone action bar. |
| `src/assets/` | Styles, script, fonts and logo. |
| `src/_headers` | Security and caching headers (Netlify and Cloudflare Pages read this file). |
| `build.py` | Rebuilds `dist/` from `src/`. Needs Python 3.8 or newer, nothing else. |
| `rsi/` | The WEB-DESIGN-RSI-1.0 design test: contract, harness and the measured runs for this redesign. |

## Pages

Home, Deals, Bell family, Mobile, Internet and TV, Repairs, Visit us, Privacy, a thank-you page shown after a form is sent, and a 404 page.

The **Bell family** page explains each brand the store sells: Bell (with Bell SmartPay and the Device Return Option), Virgin Plus (Member Benefits, the end of Virgin Plus prepaid on January 15, 2027, and the end of new Virgin Plus internet and TV sign-ups in Ontario on January 14, 2026), Lucky Mobile (prepaid, no credit check), Bell home services (Bell Internet, Fibe TV and the Fibe TV app, Satellite TV, Home Phone, bundles) and Bell for business. The brand facts were checked against Bell, iPhone in Canada, MobileSyrup, WhistleOut and PlanHub pages on October 26, 2026.

## Change something

1. Edit `src/site.json`, or a page in `src/pages/`.
2. Run `python3 build.py`.
3. Upload the new `dist/` folder.

Hours, phone number, email and address are typed once in `site.json` and appear on every page, in the open/closed signs (including the neon sign in the storefront illustration) and in the search-engine data.

An offer in `site.json` looks like this:

```json
{
  "brand": "Bell",
  "category": "mobile",
  "title": "New phone on a Bell plan",
  "price": "$55/mo",
  "detail": "Pay for your phone monthly with an eligible Bell plan.",
  "terms": "24-month term on eligible plans. Plus applicable taxes. Ends Nov 30."
}
```

`category` is `mobile`, `home` or `repairs`. It picks the card's illustration and drives the filters on the Deals page. The first three offers also appear on the home page. Offers marked `"status": "example"` show an "Example offer" badge.

### Carrier logos

The logos live in `src/assets/img/brands/`: `bell.svg` (Bell blue), `virgin-plus.png` with a smaller `virgin-plus.webp` twin (red tile with black "plus"), and `lucky-mobile.svg` (the current "lucky mobile by Bell" logo). They come from the T Wireless carrier logo pack supplied on October 26, 2026, which collected them from bell.ca, virginplus.ca and luckymobile.ca. Each one sits unaltered on a white plate in the home page's "Plans from" row, on the brand cards on Home and Mobile, beside each brand heading on the Bell family page, and on the deal cards (the repair deal shows the T Wireless logo).

To swap a logo, replace the file with the same name and run `python3 build.py`. For example, the business card uses the older "lucky mobile" wordmark: copy `Lucky-Mobile-logo-classic.svg` from the pack over `lucky-mobile.svg` to match it. A `.svg` file is used first, then `.png` (with a `.webp` twin if present). Delete a carrier's file and the site falls back to that brand's name and icon. `python3 build.py --logo-placeholders --out preview` shows labelled empty frames for any logo that's missing.

### Map

The map on Home and Visit us is a drawn sketch in `src/partials/map.html`, north up and roughly to scale (the bar shows 100 m). It shows Bovaird Dr W and Chinguacousy Rd at their real angles, the plaza, and T Wireless on the south side of Bovaird about 150 m east of the intersection. The line under it ("South side of Bovaird, just east of Chinguacousy Rd") comes from `store.directions_hint` in `site.json`. "Show the map" loads the live Google map only when a visitor taps it, and "Open in Google Maps" opens the listing.

## Before launch

These are things I couldn't confirm from public listings. Please check each one.

- [ ] **Postal code.** The business card reads "I6X OG3", which the site shows as **L6X 0G3**; the Google listing also shows L6X 0G3. Bell's store locator lists the store at **L6X 5K7**. Check with Canada Post and fix `store.postal` in `site.json` if needed.
- [ ] **Sunday hours.** The site and Bell's store locator say 10 a.m. to 8 p.m. every day, but the Google listing shows Sunday 10:30 a.m. to 7 p.m. Confirm Sunday hours and update `hours` in `site.json`; the open/closed signs follow automatically.
- [ ] Replace the five example offers with real ones, or delete them. `python3 build.py --release` refuses to build while any remain.
- [ ] Confirm the site will live at `https://www.twireless.ca` (set in `site.base_url`; it drives canonical links, the sitemap and the social preview image).
- [ ] Confirm the Bell family page matches what the store can set up, especially Satellite TV, Home Phone, business plans, Bell SmartPay and the Device Return Option. Re-check it when Bell changes a program.
- [ ] Confirm the repair list, and that you quote repairs before starting.
- [ ] Confirm walk-ins are welcome (FAQ answer), that staff will call back form requests, and that Ali is happy to be named on the Visit page.
- [ ] **Carrier logos.** The logos on the site came from the brands' public websites, not from Bell's dealer kit. Before launch, get sign-off from your Bell dealer or brand contact for showing the Bell, Virgin Plus and Lucky Mobile logos online, and swap in their files if they send different versions (see "Carrier logos" above). Check their rules on clear space, minimum size and backgrounds, and on using Bell blue (Pantone 301, a shade Bell has applied to trademark).
- [ ] Review the Privacy page. It says the site sets no tracking cookies and that you delete old requests.
- [ ] Update the Google rating in `site.json` from time to time (4.1 from 91 reviews on October 26, 2026), or remove it from the home page.
- [ ] Optional: add real photos of the store and staff next to the illustration.

## Demo on GitHub Pages

The demo for showing the store owner lives at **https://emblem-nlp.github.io/twireless-site/** and is served from the `docs/` folder of this repository.

GitHub Pages setup (one time): in the repository, go to **Settings → Pages**. Under **Build and deployment**, set **Source** to **Deploy from a branch**, pick **main** and **/docs**, then **Save**. The site appears at the address above about a minute later. Don't pick **/ (root)**: the root holds the source files, so Pages would show this README instead of the site. On GitHub's free plan Pages only works for public repositories; a private repository needs GitHub Team.

The demo differs from the real site in four ways:
- a yellow bar at the top says it's a preview and that forms don't send;
- the repair and visit forms go to a thank-you page that says nothing was sent, because GitHub Pages can't receive form posts;
- every page tells search engines not to index it, and `robots.txt` blocks crawlers, so the demo never competes with twireless.ca;
- the 404 page loads its styles from `/twireless-site/`.

To update the demo after a change, rebuild it and push:

```sh
python3 build.py --demo --base-path /twireless-site/ --out docs
git add -A && git commit -m "Update demo" && git push
```

Anyone with the link can open the demo. For a password-protected preview, use a host with access control instead (for example Netlify or Cloudflare Pages with password protection).

## Put it online

**Netlify (simplest, forms work without extra setup)**
1. Go to app.netlify.com, add a new site and drag the `dist/` folder in.
2. In the site's Forms settings, turn on form detection, then set an email notification so requests reach the store.
3. Connect your domain in Domain settings.

**GitHub Pages on twireless.ca**
Set `site.form_action` to a form service such as Formspree first (GitHub Pages can't receive forms). Then run `python3 build.py --out docs` (without `--demo`), add a file `docs/CNAME` containing `www.twireless.ca`, push, and enter the domain under **Settings → Pages → Custom domain**. At the domain registrar, point `www` at `emblem-nlp.github.io` with a CNAME record. The security headers in `src/_headers` don't apply on GitHub Pages.

**Cloudflare Pages or another host**
Upload `dist/`. Forms need a form service (for example Formspree): put its address in `site.form_action`, add that address to `form-action` in `src/_headers`, and rebuild. Hosts that don't read `_headers` need the same headers set in their dashboard.

## Adding analytics or ad pixels later

The site loads nothing from outside companies, which keeps it fast and private. If you add Google Analytics or a Meta pixel, load them only after the visitor agrees to cookies, and add their domains to the Content-Security-Policy in `src/_headers`, or the browser will block them.

## Design test (WEB-DESIGN-RSI-1.0)

`rsi/` holds a website version of the EMBLEM RSI test suite's PDF design series (PDF-BRIEF-DESIGN-RSI-1.0). The loop is the same: measure a build, review it with evidence, evaluate, then compare it with the version it replaces. A new design is promoted only if its measured layer passes, its review evidence is complete, every score gate passes, its overall score beats the old version and no dimension drops by more than 3 points.

| File | What it is |
| --- | --- |
| `rsi/web_design_contract.json` | Weights for 11 design dimensions, the gates, the pages and their roles, and the measured thresholds (Lighthouse, layout shift, type scale, overflow at 360, 390 and 1440 pixels, required text). |
| `rsi/web_design_rsi.py` | The harness: `measure`, `template`, `evaluate`, `compare`. |
| `rsi/runs/v1-incumbent/` | The first version of the site: measured run, screenshots, review and result. |
| `rsi/runs/v2-candidate/` | First pass of the redesign: measured run, screenshots, review, result and the promotion decision (not promoted). |
| `rsi/runs/v3-candidate/` | Second pass of the redesign: measured run, screenshots, review, result and the promotion decision (promoted over v1). |
| `rsi/runs/v4-candidate/` | v3 plus the carrier logos: measured run and screenshots only. Its Visit page layout shift was fixed before review. |
| `rsi/runs/v5-candidate/` | v4 plus that fix: measured run, screenshots, review, result and the promotion decision (promoted over v3). |
| `rsi/runs/v6-candidate/` | v5 with the map redrawn to show the real intersection, the build in `dist/`: measured run, screenshots, review, result and the comparison with v5 (not promoted). |

Results on October 26, 2026 (producer review by EMBLEM-NLP, not independent):

| Run | What it is | Measured checks | Review score | Gate result |
| --- | --- | --- | --- | --- |
| `v1-incumbent` | First version of the site | 3 of 128 failed (13 type sizes on the home page, 11 on Deals, no Bell family page) | 57.2 | Fails the gates |
| `v2-candidate` | Redesign, first pass | 0 of 151 failed | 84.6 | Not promoted: below the 85 overall gate. Inner pages still opened with text-only headers. |
| `v3-candidate` | Redesign, second pass | 0 of 151 failed | 86.0 | Promoted over v1 (+28.8), no dimension regressed. |
| `v4-candidate` | v3 plus the Bell, Virgin Plus and Lucky Mobile logos | 0 of 151 failed | not reviewed | Measured only. The Visit page showed a 0.04 layout shift (the open/closed line re-wrapping in the store card), so it was fixed first. |
| `v5-candidate` | v4 plus the Visit page fix | 0 of 151 failed | 87.0 | **Promoted over v3 (+1.0)**, no dimension regressed. Status `DIAGNOSTIC_PROMOTED_RELEASE_BLOCKED`. |
| `v6-candidate` | v5 with the map redrawn to show Bovaird Dr W and Chinguacousy Rd (this build) | 0 of 151 failed | 87.5 | Not promoted over v5 (+0.5; the gate needs +1), no dimension regressed. It's a factual fix to the map rather than a new design, so shipping it is the owner's call. |

`v5-candidate` is the last promoted design; the build in `dist/` is `v6-candidate`, the same design with the corrected map. Release stays blocked until someone other than the producer reviews the build that ships (`v6-candidate`) as `independent_reviewer` and the contract is marked `approved_for_production`. The weakest dimensions are conversion paths and information economy (4 of 5): the deals are still example placeholders, and a few facts repeat across pages.

Lighthouse 13.5.0 (mobile) for this build:

| Page | Performance | Accessibility | Best practices | SEO | Largest paint | Layout shift | Transfer |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Home | 97 | 100 | 100 | 100 | 2.3 s | 0.001 | 214 KB |
| Bell family | 99 | 100 | 100 | 100 | 2.0 s | 0.001 | 140 KB |
| Deals | 99 | 100 | 100 | 100 | 2.0 s | 0.001 | 159 KB |
| Mobile | 99 | 100 | 100 | 100 | 2.0 s | 0.001 | 156 KB |
| Internet and TV | 99 | 100 | 100 | 100 | 1.8 s | 0.001 | 138 KB |
| Repairs | 100 | 100 | 100 | 100 | 1.7 s | 0.001 | 139 KB |
| Visit us | 99 | 100 | 100 | 100 | 1.8 s | 0.033 | 122 KB |

HTML passes html-validate, every internal link, anchor and icon reference resolves, every text colour meets WCAG AA contrast, and no page scrolls sideways at 360, 390 or 1440 pixels. Each run folder keeps the exact build it measured (`site/`) and its hashed screenshots (`evidence/`), so `evaluate` and `compare` can re-check them anywhere. The screenshots are large, so they ship in a separate `t-wireless-rsi-evidence.zip`; unzip it in the same place as this folder and the `evidence/` folders drop into their runs.

To clear the release block, an independent reviewer scores the build that ships from its screenshots (needs Python 3.10+):

```sh
python3 rsi/web_design_rsi.py template --measured rsi/runs/v6-candidate/measured.json --contract rsi/web_design_contract.json --reviewer-id REVIEWER-NAME --reviewer-role independent_reviewer --out rsi/runs/v6-candidate/review-independent.json
# fill in each 0-5 score and rationale, set "status": "reviewed", answer the three accuracy questions
python3 rsi/web_design_rsi.py evaluate --contract rsi/web_design_contract.json --measured rsi/runs/v6-candidate/measured.json --review rsi/runs/v6-candidate/review-independent.json --out rsi/runs/v6-candidate/result-independent.json
```

Then set `"approved_for_production": true` in the contract once the owner signs off. To test a later change (also needs Playwright for Python with Chromium, and Lighthouse):

```sh
python3 build.py
cp -r dist /tmp/site-v7
python3 rsi/web_design_rsi.py measure --site /tmp/site-v7 --contract rsi/web_design_contract.json --out rsi/runs/v7-candidate
python3 rsi/web_design_rsi.py template --measured rsi/runs/v7-candidate/measured.json --contract rsi/web_design_contract.json --reviewer-id REVIEWER-NAME --out rsi/runs/v7-candidate/review.json
# fill in the review, then compare with the current build
python3 rsi/web_design_rsi.py compare --contract rsi/web_design_contract.json --incumbent-measured rsi/runs/v6-candidate/measured.json --incumbent-review rsi/runs/v6-candidate/review.json --measured rsi/runs/v7-candidate/measured.json --review rsi/runs/v7-candidate/review.json --out rsi/runs/v7-candidate/promotion.json
```

Scores are reviewer observations backed by Lighthouse and browser measurements. They are not a measure of how visitors behave.

## Rights

© 2026 EMBLEM-NLP. All rights reserved. This repository has no open-source licence on purpose: the code, copy and illustrations may not be copied, reused or adapted without written permission. Who owns the site after launch is set by the agreement with T Wireless. Parts made by others keep their own terms:
- Source Serif 4 and Figtree fonts: SIL Open Font License (licence files in `src/assets/fonts/`).
- T Wireless logo and phone mark: T Wireless.
- Bell, Virgin Plus and Lucky Mobile logos: trademarks of Bell Canada and its licensors, used to show the brands an authorised retailer sells, subject to Bell's approval.

## Credits

Fonts: Source Serif 4 and Figtree, both under the SIL Open Font License (licence files in `src/assets/fonts/`). Logo and phone mark: T Wireless. Bell, Virgin Plus and Lucky Mobile logos: trademarks of Bell Canada and its licensors, shown as supplied. The storefront, map and service illustrations are drawn for this site.
