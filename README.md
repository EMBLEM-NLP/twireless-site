# T Wireless website

The website for T Wireless, Bell Authorised Retailer, 965 Bovaird Dr W, Unit 1, Brampton.
Prepared by EMBLEM-NLP (Romar Johnson), October 26, 2026.

Store details come from the T Wireless business card: Ali, 647-707-1093, twireless965@gmail.com, www.twireless.ca, 965 Bovaird Dr. West, Unit 1.

The store's content is written once (`src/site.json` and the page copy) and offered in several designs, so the owner can choose one. Two are built; a third is planned.

| Design | The idea | Demo |
| --- | --- | --- |
| Design 1 | Illustrated storefront: a navy awning, serif headlines, drawn illustrations and a live neon "Open" sign. Source in `src/`. | https://emblem-nlp.github.io/twireless-site/ |
| Design 2 ("In hand") | Photo-led: every picture centres on a phone in someone's hand, a home or the repair bench, and the logos are part of the pictures. White page, Bell blue for actions, one typeface (Atkinson Hyperlegible Next). Source in `designs/design-2/`. | https://emblem-nlp.github.io/twireless-site/design-2/ |
| Design 3 | Planned: bold retail signage (big shelf-tag type, price-tag deal cards, few photos), so the three stay clearly different. | |

## What's in this folder

| Path | What it is |
| --- | --- |
| `dist/` | Design 1, finished. Upload this folder to your host. Built by `build.py`, not stored in git. |
| `dist-design-2/` | Design 2, finished (`python3 build.py --design design-2`). Not stored in git. |
| `docs/` | The public demo that GitHub Pages serves: design 1 at the root, design 2 in `docs/design-2/`. Built by `demo.py`. |
| `src/site.json` | Store details, hours, the Bell family cards, offers, repairs and FAQ, shared by every design. Most edits happen here. |
| `src/pages/`, `src/partials/`, `src/assets/` | Design 1's page copy, shared parts, styles, script, fonts and logos. The script, logos and icons are shared with the other designs. |
| `designs/design-2/` | Design 2: `design.json`, page copy (`pages/`), its own parts (`partials/`), styles and font (`assets/`), photos (`assets/img/photos/`), `design.py` for its photo and logo blocks, and `imagery/` (where each photo came from, its licence and crops, and the phone screens composited onto photos). |
| `src/_headers` | Security and caching headers (Netlify and Cloudflare Pages read this file). |
| `build.py` | Builds one design. Needs Python 3.8 or newer, nothing else. |
| `demo.py` | Builds the GitHub Pages demo of every design into `docs/`. |
| `rsi/` | The WEB-DESIGN-RSI-2.0 design test: harness, imagery tool, a contract per design and the measured runs. |

## Pages

Home, Deals, Bell family, Mobile, Internet and TV, Repairs, Visit us, Privacy, a thank-you page shown after a form is sent, and a 404 page. Design 2 adds a Photo credits page.

The **Bell family** page explains each brand the store sells: Bell (with Bell SmartPay and the Device Return Option), Virgin Plus (Member Benefits, the end of Virgin Plus prepaid on January 15, 2027, and the end of new Virgin Plus internet and TV sign-ups in Ontario on January 14, 2026), Lucky Mobile (prepaid, no credit check), Bell home services (Bell Internet, Fibe TV and the Fibe TV app, Satellite TV, Home Phone, bundles) and Bell for business. The brand facts were checked against Bell, iPhone in Canada, MobileSyrup, WhistleOut and PlanHub pages on October 26, 2026. Both designs carry the same facts; the design test checks for them on every page.

## Change something

1. Edit `src/site.json`, or a page in `src/pages/` (design 1) or `designs/design-2/pages/` (design 2).
2. Run `python3 build.py` (design 1, into `dist/`) or `python3 build.py --design design-2` (into `dist-design-2/`).
3. Upload the new folder.

Hours, phone number, email and address are typed once in `site.json` and appear on every page of every design, in the open/closed signs (the neon sign in design 1, the "Open until 8 p.m." tag on design 2's hero photo) and in the search-engine data.

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

`category` is `mobile`, `home` or `repairs`. It picks the card's picture and drives the filters on the Deals page. The first three offers also appear on the home page. Offers marked `"status": "example"` show an "Example offer" badge.

### Carrier logos

The logos live in `src/assets/img/brands/`: `bell.svg` (Bell blue), `virgin-plus.png` with a smaller `virgin-plus.webp` twin (red tile with black "plus"), and `lucky-mobile.svg` (the current "lucky mobile by Bell" logo). They come from the T Wireless carrier logo pack supplied on October 26, 2026, which collected them from bell.ca, virginplus.ca and luckymobile.ca. Each one sits unaltered on a white plate. In design 1 they appear in the home page's "Plans from" row, on the brand cards on Home and Mobile, beside each brand heading on the Bell family page, and on the deal cards. In design 2 they also sit on photos (see below).

To swap a logo, replace the file with the same name and run the build. For example, the business card uses the older "lucky mobile" wordmark: copy `Lucky-Mobile-logo-classic.svg` from the pack over `lucky-mobile.svg` to match it. A `.svg` file is used first, then `.png` (with a `.webp` twin if present). Delete a carrier's file and design 1 falls back to that brand's name and icon. `python3 build.py --logo-placeholders --out preview` shows labelled empty frames for any logo that's missing. Design 2's test holds the approved logo files by their fingerprints (`logos.files` in `rsi/contracts/design-2.json`), so after swapping a logo, update those fingerprints too.

### Map

The map on Home and Visit us is a drawn sketch in `src/partials/map.html`, shared by both designs, north up and roughly to scale (the bar shows 100 m). It shows Bovaird Dr W and Chinguacousy Rd at their real angles, the plaza, and T Wireless on the south side of Bovaird about 150 m east of the intersection. The line under it ("South side of Bovaird, just east of Chinguacousy Rd") comes from `store.directions_hint` in `site.json`. "Show the map" loads the live Google map only when a visitor taps it, and "Open in Google Maps" opens the listing.

## Design 2: photos and logos

**Photos.** Twelve stock photos from Pexels, used under the [Pexels License](https://www.pexels.com/license/): free for commercial use, edits allowed, no credit required (the site credits each photographer anyway on the Photo credits page). The licence has four conditions this design keeps: people in a photo must not appear to endorse the store; nobody identifiable is shown in a bad light; no photo becomes part of a trademark or business name; no reselling or redistributing the files. The footer and the credits page say the photos are stock photos that don't show the store, its staff or its customers.

| Photo | What it shows | Photographer | Source | People, edits |
| --- | --- | --- | --- | --- |
| `hand-phone` | Hand holding a smartphone with a blank screen outdoors | Nandhu Kumar | [Pexels 9164565](https://www.pexels.com/photo/person-holding-mobile-phone-9164565/) | no faces; T Wireless screen added |
| `hand-new-phones` | A hand holding a smartphone with a blank screen | Jakub Zerdzicki | [Pexels 30909364](https://www.pexels.com/photo/hand-holding-smartphone-with-blank-screen-30909364/) | no faces; T Wireless screen added |
| `two-phones` | Close-up of hands holding two smartphones | Kaboompics | [Pexels 5398928](https://www.pexels.com/photo/person-holding-two-cellphones-5398928/) | no faces |
| `concert` | An audience member recording a concert on a smartphone | Chase R. Smith | [Pexels 17964711](https://www.pexels.com/photo/a-person-holding-a-smartphone-at-a-concert-17964711/) | no faces |
| `train` | Adult in a black coat checking a smartphone while commuting | MART PRODUCTION | [Pexels 7251087](https://www.pexels.com/photo/person-using-a-smartphone-while-riding-a-train-7251087/) | no faces (crops start below the face); retouched: a transit operator's logo and a sticker on the ticket machine |
| `family-tv` | A family enjoying time together on the sofa in a living room | World Sikh Organization of Canada | [Pexels 14798018](https://www.pexels.com/photo/a-family-watching-together-in-the-living-room-14798018/) | identifiable |
| `living-room` | A bright living room with a grey couch and a TV | Lisa Anna | [Pexels 19899066](https://www.pexels.com/photo/modern-living-room-with-tv-19899066/) | none |
| `video-call` | A woman on a video call at her kitchen table | Katrin Bolovtsova | [Pexels 4049991](https://www.pexels.com/photo/happy-woman-video-chatting-on-laptop-in-kitchen-4049991/) | identifiable |
| `repair-mat` | Disassembled smartphone parts on a blue repair mat with tools | Fotografia Lui Vlad | [Pexels 31862950](https://www.pexels.com/photo/disassembled-smartphone-on-repair-workbench-31862950/) | none; retouched: Apple logos on the battery and the logic board chip |
| `cracked-screen` | Two phones with cracked screens on an orange background | Towfiqu barbhuiya | [Pexels 11921157](https://www.pexels.com/photo/cracked-screen-of-a-smartphone-11921157/) | none |
| `cafe-business` | A woman using her phone and laptop in a café | RDNE Stock project | [Pexels 10375885](https://www.pexels.com/photo/smiling-woman-using-smart-phone-at-cafe-10375885/) | identifiable |
| `seniors-phone` | An older couple at a kitchen table looking at a phone | T Leish | [Pexels 6975187](https://www.pexels.com/photo/an-elderly-couple-using-a-smart-phone-6975187/) | identifiable |

**Logos on photos.** The two "phone in hand" photos carry a T Wireless screen, composited onto the real screen with its shape, light, the thumb and the camera cutout kept in front: the hero shows the T Wireless logo, "Bell Authorised Retailer in Brampton" and the Bell, Virgin Plus and Lucky Mobile logos; the Mobile page's shows "New phones, iPhone and Android". Carrier logos also sit on white plates over the provider, brand and deal photos, but only on photos where nobody can be recognised (hands, a crowd from behind, rooms, parts), so no one appears to endorse a brand or the store. The social preview image (shown when a link is texted) is composed the same way.

**Changing a photo.** Everything about a photo lives in `designs/design-2/imagery/sources.json`: where it came from, its licence, who is in it (`none`, `no faces` or `identifiable`), its alt text, its crops (shape, focus point, zoom and widths), any retouch (a box to fill, with the reason) and, for a phone photo, the screen to put on it (`imagery/screens/*.html`). Then (needs Python 3.10+, Pillow, numpy, OpenCV and Playwright with Chromium):

```sh
python3 rsi/imagery.py fetch --design designs/design-2    # download originals and record their fingerprints
python3 rsi/imagery.py render --design designs/design-2   # grade, retouch, composite, crop, encode AVIF/WebP/JPEG, write photos.json
python3 rsi/imagery.py audit --design designs/design-2    # licences, hosts, credits, fingerprints, no faces where none are declared
python3 rsi/imagery.py sheet --design designs/design-2 --out sheet.png   # contact sheet with credits
python3 build.py --design design-2
```

Originals aren't stored in git (`fetch` restores them and checks they're the same files). The rendered photos are, because the site needs them. Only `images.pexels.com` and `images.unsplash.com` are accepted as sources, and paid Unsplash+ images are refused.

## Before launch

These are things I couldn't confirm from public listings. Please check each one.

- [ ] **Postal code.** The business card reads "I6X OG3", which the site shows as **L6X 0G3**; the Google listing also shows L6X 0G3. Bell's store locator lists the store at **L6X 5K7**. Check with Canada Post and fix `store.postal` in `site.json` if needed.
- [ ] **Sunday hours.** The site and Bell's store locator say 10 a.m. to 8 p.m. every day, but the Google listing shows Sunday 10:30 a.m. to 7 p.m. Confirm Sunday hours and update `hours` in `site.json`; the open/closed signs follow automatically.
- [ ] Replace the five example offers with real ones, or delete them. `python3 build.py --release` refuses to build while any remain.
- [ ] Confirm the site will live at `https://www.twireless.ca` (set in `site.base_url`; it drives canonical links, the sitemap and the social preview image).
- [ ] Confirm the Bell family page matches what the store can set up, especially Satellite TV, Home Phone, business plans, Bell SmartPay and the Device Return Option. Re-check it when Bell changes a program.
- [ ] Confirm the repair list, and that you quote repairs before starting.
- [ ] Confirm walk-ins are welcome (FAQ answer), that staff will call back form requests, and that Ali is happy to be named on the Visit page.
- [ ] **Carrier logos.** The logos on the site came from the brands' public websites, not from Bell's dealer kit. Before launch, get sign-off from your Bell dealer or brand contact for showing the Bell, Virgin Plus and Lucky Mobile logos online, and swap in their files if they send different versions (see "Carrier logos" above). Check their rules on clear space, minimum size and backgrounds, and on using Bell blue (Pantone 301, a shade Bell has applied to trademark). If design 2 is chosen, show them the logos on photos and on the phone screens too.
- [ ] Review the Privacy page. It says the site sets no tracking cookies and that you delete old requests.
- [ ] Update the Google rating in `site.json` from time to time (4.1 from 91 reviews on October 26, 2026), or remove it from the home page.
- [ ] Design 2: the photos are stock photos. Real photos of the store, the counter and the repair bench would be stronger; add them to `sources.json` the same way (with written consent from anyone recognisable in them).
- [ ] Optional for design 1: add real photos of the store and staff next to the illustration.

## Demo on GitHub Pages

The demos for showing the store owner are served from the `docs/` folder of this repository:
- Design 1: **https://emblem-nlp.github.io/twireless-site/**
- Design 2: **https://emblem-nlp.github.io/twireless-site/design-2/**

The yellow preview bar at the top of every page links to the same page in the other design ("Compare designs: Design 1 Design 2"), so the owner can flip between them on a phone.

GitHub Pages setup (one time): in the repository, go to **Settings → Pages**. Under **Build and deployment**, set **Source** to **Deploy from a branch**, pick **main** and **/docs**, then **Save**. The site appears at the address above about a minute later. Don't pick **/ (root)**: the root holds the source files, so Pages would show this README instead of the site. On GitHub's free plan Pages only works for public repositories; a private repository needs GitHub Team.

The demo differs from the real site in five ways:
- a yellow bar at the top says it's a preview, says forms don't send, and links to the other designs;
- the repair and visit forms go to a thank-you page that says nothing was sent, because GitHub Pages can't receive form posts;
- every page tells search engines not to index it, and `robots.txt` blocks crawlers, so the demo never competes with twireless.ca;
- shared links show a preview image from the demo address, with no canonical link to twireless.ca;
- the 404 page loads its styles from `/twireless-site/` (GitHub Pages shows design 1's 404 page for any missing address).

To update the demos after a change, rebuild them and push:

```sh
python3 demo.py
git add -A && git commit -m "Update demo" && git push
```

Anyone with the link can open the demo. For a password-protected preview, use a host with access control instead (for example Netlify or Cloudflare Pages with password protection).

## Put it online

Use `dist/` for design 1 or `dist-design-2/` for design 2.

**Netlify (simplest, forms work without extra setup)**
1. Go to app.netlify.com, add a new site and drag the folder in.
2. In the site's Forms settings, turn on form detection, then set an email notification so requests reach the store.
3. Connect your domain in Domain settings.

**GitHub Pages on twireless.ca**
Set `site.form_action` to a form service such as Formspree first (GitHub Pages can't receive forms). Then run `python3 build.py --out docs` (add `--design design-2` for design 2; without `--demo`), add a file `docs/CNAME` containing `www.twireless.ca`, push, and enter the domain under **Settings → Pages → Custom domain**. At the domain registrar, point `www` at `emblem-nlp.github.io` with a CNAME record. The security headers in `src/_headers` don't apply on GitHub Pages.

**Cloudflare Pages or another host**
Upload the folder. Forms need a form service (for example Formspree): put its address in `site.form_action`, add that address to `form-action` in `src/_headers`, and rebuild. Hosts that don't read `_headers` need the same headers set in their dashboard.

## Adding analytics or ad pixels later

The site loads nothing from outside companies, which keeps it fast and private. If you add Google Analytics or a Meta pixel, load them only after the visitor agrees to cookies, and add their domains to the Content-Security-Policy in `src/_headers`, or the browser will block them.

## Design test (WEB-DESIGN-RSI-2.0)

`rsi/` holds a website version of the EMBLEM RSI test suite's PDF design series (PDF-BRIEF-DESIGN-RSI-1.0). The loop: measure a build, review it with evidence, evaluate, then compare it with the version it replaces. A new version is promoted only if its measured layer passes, its review evidence is complete, every score gate passes, its overall score beats the old version by at least 1 point and no dimension drops by more than 3 points.

Version 2.0 keeps every 1.0 run valid (design 1's results re-evaluate to the same numbers) and adds what several designs with photography need. A contract switches each part on:
- **Imagery.** Every photo on a page must be listed in the design's `photos.json` under an allowed licence, served as AVIF or WebP with a JPEG fallback for older iPhones, sharp but not oversized for its shown size, within a byte budget, lazy below the first screen, with the biggest photo on the first screen loaded first. The imagery audit (licences, sources, fingerprints, and a face detector confirming that photos declared faceless show no faces) must pass, and the build must carry the design's current `photos.json`.
- **Logos.** Each page shows the logos its role needs; logo files are byte-for-byte the approved ones; each logo is drawn big enough, undistorted and on a clean white plate; no logo sits on a photo of someone who can be recognised; the home page shows the composite photo that carries all four marks.
- **Distinctness.** The design's first screens (phone and desktop), palette and typefaces are compared with the other designs' runs: structural similarity of the first screens at most 0.45, palette distance at least 12, a different headline typeface. Calibration: two builds of design 1 that differ below the fold score 1.0 and 0; design 1's first version against its redesign scores 0.16 and 8.6 (same design family, so not distinct enough).
- **Accuracy questions from the contract.** Design 2's review also answers: are the photos licensed for commercial use; does any photo imply it shows the store, staff or customers; are carrier logos unaltered on clean plates; are there third-party brand marks in the photos.
- **Evidence.** Each page is scrolled so lazy photos load before full-page screenshots; the first phone screen of each page, the imagery contact sheet and the distinctness screenshots are kept too.

| Path | What it is |
| --- | --- |
| `rsi/web_design_rsi.py` | The harness: `measure`, `template`, `evaluate`, `compare`, `distinct`. |
| `rsi/imagery.py` | The imagery tool: `fetch`, `render`, `sheet`, `audit`. |
| `rsi/models/` | The YuNet face detector the audit uses (OpenCV Zoo, MIT licence). |
| `rsi/contracts/design-1.json` | Design 1's 1.0 contract: weights for 11 dimensions, the gates, pages and roles, measured thresholds. |
| `rsi/contracts/design-2.json` | Design 2's 2.0 contract: 13 dimensions (adds imagery quality, logo integration and distinctiveness), seven accuracy questions, imagery, logo and distinctness checks. |
| `rsi/runs/design-1/` | Design 1's runs, v1 to v6. |
| `rsi/runs/design-2/` | Design 2's runs, v1 to v3. |

### Design 1 results

Results on October 26, 2026 (producer review by EMBLEM-NLP, not independent):

| Run | What it is | Measured checks | Review score | Gate result |
| --- | --- | --- | --- | --- |
| `v1-incumbent` | First version of the site | 3 of 128 failed (13 type sizes on the home page, 11 on Deals, no Bell family page) | 57.2 | Fails the gates |
| `v2-candidate` | Redesign, first pass | 0 of 151 failed | 84.6 | Not promoted: below the 85 overall gate. Inner pages still opened with text-only headers. |
| `v3-candidate` | Redesign, second pass | 0 of 151 failed | 86.0 | Promoted over v1 (+28.8), no dimension regressed. |
| `v4-candidate` | v3 plus the Bell, Virgin Plus and Lucky Mobile logos | 0 of 151 failed | not reviewed | Measured only. The Visit page showed a 0.04 layout shift (the open/closed line re-wrapping in the store card), so it was fixed first. |
| `v5-candidate` | v4 plus the Visit page fix | 0 of 151 failed | 87.0 | **Promoted over v3 (+1.0)**, no dimension regressed. Status `DIAGNOSTIC_PROMOTED_RELEASE_BLOCKED`. |
| `v6-candidate` | v5 with the map redrawn to show Bovaird Dr W and Chinguacousy Rd (the build in `dist/`) | 0 of 151 failed | 87.5 | Not promoted over v5 (+0.5; the gate needs +1), no dimension regressed. It's a factual fix to the map rather than a new design, so shipping it is the owner's call. |

`v5-candidate` is design 1's last promoted version; the build in `dist/` is `v6-candidate`, the same design with the corrected map. Release stays blocked until someone other than the producer reviews `v6-candidate` as `independent_reviewer` and the contract is marked `approved_for_production`. The weakest dimensions are conversion paths and information economy (4 of 5): the deals are still example placeholders, and a few facts repeat across pages.

Lighthouse 13.5.0 (mobile) for design 1's build:

| Page | Performance | Accessibility | Best practices | SEO | Largest paint | Layout shift | Transfer |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Home | 97 | 100 | 100 | 100 | 2.3 s | 0.001 | 214 KB |
| Bell family | 99 | 100 | 100 | 100 | 2.0 s | 0.001 | 140 KB |
| Deals | 99 | 100 | 100 | 100 | 2.0 s | 0.001 | 159 KB |
| Mobile | 99 | 100 | 100 | 100 | 2.0 s | 0.001 | 156 KB |
| Internet and TV | 99 | 100 | 100 | 100 | 1.8 s | 0.001 | 138 KB |
| Repairs | 100 | 100 | 100 | 100 | 1.7 s | 0.001 | 139 KB |
| Visit us | 99 | 100 | 100 | 100 | 1.8 s | 0.033 | 122 KB |

### Design 2 results

Results on October 26, 2026 (producer review by EMBLEM-NLP, not independent). Each run has 289 measured checks of 43 kinds.

| Run | What it is | Measured checks | Review score | Gate result |
| --- | --- | --- | --- | --- |
| `v1-candidate` | First full build | 0 of 289 failed | 85.9 | Fails the accuracy gate: two photos still carried third-party marks (Apple logos on the repair photo's battery, a transit operator's logo on the train photo's ticket machine). The two-phones photo also appeared twice on the Mobile page, the phone navigation scrolled sideways, and the Bell family comparison table scrolled sideways on phones. |
| `v2-candidate` | v1 with the marks retouched out, a second phone-in-hand composite for "New phones", all six pages shown in the phone navigation, and the comparison stacked into cards on phones | 0 of 289 failed | 88.8 | **Promoted over v1 (+2.9)**, no dimension regressed. Status `DIAGNOSTIC_PROMOTED_RELEASE_BLOCKED`. |
| `v3-candidate` | v2 plus two fixes from the HTML validator, with no visual change (the build in `dist-design-2/` and the demo) | 0 of 289 failed | 88.8 | Not promoted over v2 (+0.0); same design, so shipping it is the owner's call. |

Against design 1, design 2's first screens score 0.14 for structural similarity (0.10 on a phone, 0.19 on desktop) and 16.2 for palette distance, with different headline and body typefaces (Atkinson Hyperlegible Next against Source Serif 4 and Figtree). Its weakest dimensions are brand identity and grid rhythm (4 of 5): the store's own red appears only in its logo, and a few desktop sections leave wide space beside short text. The Deals page's information gain stays at 3.5 of 5 until real offers replace the examples.

Lighthouse 13.5.0 (mobile) for design 2's build, with the photos a phone loads on each page:

| Page | Performance | Accessibility | Best practices | SEO | Largest paint | Layout shift | Transfer | Photos (size) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Home | 99 | 100 | 100 | 100 | 2.0 s | 0.001 | 220 KB | 6 (92 KB) |
| Bell family | 100 | 100 | 100 | 100 | 1.8 s | 0.000 | 169 KB | 5 (120 KB) |
| Deals | 99 | 100 | 100 | 100 | 2.0 s | 0.000 | 172 KB | 5 (56 KB) |
| Mobile | 99 | 100 | 100 | 100 | 2.0 s | 0.000 | 206 KB | 6 (90 KB) |
| Internet and TV | 100 | 100 | 100 | 100 | 1.9 s | 0.000 | 177 KB | 3 (80 KB) |
| Repairs | 100 | 100 | 100 | 100 | 1.7 s | 0.000 | 141 KB | 2 (46 KB) |
| Visit us | 100 | 100 | 100 | 100 | 1.6 s | 0.000 | 97 KB | 0 (0 KB) |

Both designs pass html-validate, every internal link, anchor and icon reference resolves, and no page scrolls sideways at 360, 390 or 1440 pixels. Each run folder keeps the exact build it measured (`site/`) and its hashed screenshots (`evidence/`), so `evaluate` and `compare` can re-check them anywhere. The screenshots are large, so they ship in a separate `t-wireless-rsi-evidence.zip`; unzip it in the same place as this folder and the `evidence/` folders drop into their runs.

### Running the test

Needs Python 3.10+, Playwright for Python with Chromium, Lighthouse, and for 2.0 contracts Pillow, numpy and OpenCV. To clear a release block, an independent reviewer scores the build that ships from its screenshots:

```sh
python3 rsi/web_design_rsi.py template --measured rsi/runs/design-2/v3-candidate/measured.json --contract rsi/contracts/design-2.json --reviewer-id REVIEWER-NAME --reviewer-role independent_reviewer --out rsi/runs/design-2/v3-candidate/review-independent.json
# fill in each 0-5 score and rationale, set "status": "reviewed", answer the accuracy questions
python3 rsi/web_design_rsi.py evaluate --contract rsi/contracts/design-2.json --measured rsi/runs/design-2/v3-candidate/measured.json --review rsi/runs/design-2/v3-candidate/review-independent.json --out rsi/runs/design-2/v3-candidate/result-independent.json
```

For design 1 use `rsi/contracts/design-1.json` and `rsi/runs/design-1/v6-candidate/`. Then set `"approved_for_production": true` in the contract once the owner signs off. To test a later change to design 2:

```sh
python3 build.py --design design-2
python3 rsi/web_design_rsi.py measure --site dist-design-2 --contract rsi/contracts/design-2.json --out rsi/runs/design-2/v4-candidate
python3 rsi/web_design_rsi.py template --measured rsi/runs/design-2/v4-candidate/measured.json --contract rsi/contracts/design-2.json --reviewer-id REVIEWER-NAME --out rsi/runs/design-2/v4-candidate/review.json
# fill in the review, then compare with the last promoted version
python3 rsi/web_design_rsi.py compare --contract rsi/contracts/design-2.json --incumbent-measured rsi/runs/design-2/v2-candidate/measured.json --incumbent-review rsi/runs/design-2/v2-candidate/review.json --measured rsi/runs/design-2/v4-candidate/measured.json --review rsi/runs/design-2/v4-candidate/review.json --out rsi/runs/design-2/v4-candidate/promotion.json
```

`measure` copies the build into the run, so `dist-design-2/` can be rebuilt afterwards. To see how different any two designs look: `python3 rsi/web_design_rsi.py distinct --run-a rsi/runs/design-1/v6-candidate --run-b rsi/runs/design-2/v3-candidate`. A design 3 gets its own folder in `designs/`, its own contract (with designs 1 and 2 as siblings for the distinctness check) and its own runs folder.

Scores are reviewer observations backed by Lighthouse and browser measurements. They are not a measure of how visitors behave.

## Rights

© 2026 EMBLEM-NLP. All rights reserved. This repository has no open-source licence on purpose: the code, copy and illustrations may not be copied, reused or adapted without written permission. Who owns the site after launch is set by the agreement with T Wireless. Parts made by others keep their own terms:
- Source Serif 4, Figtree and Atkinson Hyperlegible Next fonts: SIL Open Font License (licence files in `src/assets/fonts/` and `designs/design-2/assets/fonts/`).
- Design 2's photos: their photographers on Pexels, used under the Pexels License (listed above and on the Photo credits page). The licence doesn't allow redistributing them on their own.
- YuNet face detection model: MIT License (`rsi/models/LICENSE-yunet.txt`).
- T Wireless logo and phone mark: T Wireless.
- Bell, Virgin Plus and Lucky Mobile logos: trademarks of Bell Canada and its licensors, used to show the brands an authorised retailer sells, subject to Bell's approval.

## Credits

Fonts: Source Serif 4, Figtree and Atkinson Hyperlegible Next, all under the SIL Open Font License. Photos in design 2: Nandhu Kumar, Jakub Zerdzicki, Kaboompics, Chase R. Smith, MART PRODUCTION, World Sikh Organization of Canada, Lisa Anna, Katrin Bolovtsova, Fotografia Lui Vlad, Towfiqu barbhuiya, RDNE Stock project and T Leish, on Pexels. Logo and phone mark: T Wireless. Bell, Virgin Plus and Lucky Mobile logos: trademarks of Bell Canada and its licensors, shown as supplied. Design 1's storefront, map and service illustrations are drawn for this site.
