# T Wireless website

The website for T Wireless, Bell Authorised Retailer, 965 Bovaird Dr W, Unit 1, Brampton.
Prepared by EMBLEM-NLP (Romar Johnson), October 26, 2026.

Store details come from the T Wireless business card: Ali, 647-707-1093, twireless965@gmail.com, www.twireless.ca, 965 Bovaird Dr. West, Unit 1.

The store's content is written once (`src/site.json` and the page copy) and offered in several designs, so the owner can choose one. Two are built; a third is planned.

| Design | The idea | Demo |
| --- | --- | --- |
| Design 1 | Illustrated storefront: a navy awning, serif headlines, drawn illustrations and a live neon "Open" sign. Source in `src/`. | https://emblem-nlp.github.io/twireless-site/ |
| Design 2 ("In hand") | Photo-led and conversational: real stock photographs of a phone in a hand, homes and the repair bench, with the carrier logos on white plates beside them, and its own plain-spoken wording. White page, Bell blue for actions, one typeface (Atkinson Hyperlegible Next). Source in `designs/design-2/`. | https://emblem-nlp.github.io/twireless-site/design-2/ |
| Design 3 | Planned: bold retail signage (big shelf-tag type, price-tag deal cards, few photos), so the three stay clearly different. | |

## What's in this folder

| Path | What it is |
| --- | --- |
| `dist/` | Design 1, finished. Upload this folder to your host. Built by `build.py`, not stored in git. |
| `dist-design-2/` | Design 2, finished (`python3 build.py --design design-2`). Not stored in git. |
| `docs/` | The public demo that GitHub Pages serves: design 1 at the root, design 2 in `docs/design-2/`. Built by `demo.py`. |
| `src/site.json` | Store details, hours, the Bell family cards, offers, repairs and FAQ, shared by every design. Most edits happen here. |
| `src/pages/`, `src/partials/`, `src/assets/` | Design 1's page copy, shared parts, styles, script, fonts and logos. The script, logos and icons are shared with the other designs. |
| `designs/design-2/` | Design 2: `design.json`, page copy (`pages/`), `content.json` (its own wording for the carrier lines, repairs and FAQ), its own parts (`partials/`), styles and font (`assets/`), photos (`assets/img/photos/`), `design.py` for its photo and logo blocks, and `imagery/` (where each photo came from, its licence, crops and any retouching). |
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

## Design 2: photos, logos and wording

**Photos.** Twelve stock photos from Pexels, used under the [Pexels License](https://www.pexels.com/license/): free for commercial use, edits allowed, no credit required (the site credits each photographer anyway on the Photo credits page). The licence has four conditions this design keeps: people in a photo must not appear to endorse the store; nobody identifiable is shown in a bad light; no photo becomes part of a trademark or business name; no reselling or redistributing the files. The footer and the credits page say the photos are stock photos that don't show the store, its staff or its customers.

The photos are shown as photographs. The hero on the home page is a real photograph of a hand holding a smartphone in front of garden flowers, cropped to fit with nothing added; no photo has a screen, logo or text added to it, and the only changes are a light colour match and the removal of other companies' printing (see Retouching below). The carrier logos are separate pieces of the page: white plates laid over or under a photo, never edited into the picture. (Earlier builds, v1 to v3, put a composited phone screen with the logos in the hero; the owner didn't like it, and the design test now allows no composited photos.)

| Photo | What it shows | Photographer | Source | People, edits |
| --- | --- | --- | --- | --- |
| `hand-blue-phone` | A hand holding a blue smartphone with garden flowers blurred behind it (the hero) | Imad Clicks | [Pexels 11772521](https://www.pexels.com/photo/a-person-holding-a-smartphone-11772521/) | no faces; retouched: the maker's name faintly printed on the phone |
| `unboxing` | Hands lifting a new smartphone out of its box on a white desk | Pavel Danilyuk | [Pexels 7190924](https://www.pexels.com/photo/a-person-holding-a-phone-in-the-box-7190924/) | no faces; retouched: the words printed on the card and the phone pictured on the retail carton |
| `two-phones` | Close-up of hands holding two smartphones | Kaboompics | [Pexels 5398928](https://www.pexels.com/photo/person-holding-two-cellphones-5398928/) | no faces; retouched: words printed on the clear case, a faint logo on the white case |
| `concert` | An audience member recording a concert on a smartphone | Chase R. Smith | [Pexels 17964711](https://www.pexels.com/photo/a-person-holding-a-smartphone-at-a-concert-17964711/) | no faces; retouched: the lettering on the wristband |
| `train` | Adult in a black coat checking a smartphone while commuting | MART PRODUCTION | [Pexels 7251087](https://www.pexels.com/photo/person-using-a-smartphone-while-riding-a-train-7251087/) | no faces (crops start below the face); retouched: a transit operator's logo and a sticker on the ticket machine, and a dark smear on a pole in the background |
| `family-tv` | A family enjoying time together on the sofa in a living room | World Sikh Organization of Canada | [Pexels 14798018](https://www.pexels.com/photo/a-family-watching-together-in-the-living-room-14798018/) | identifiable |
| `living-room` | A bright living room with a grey couch and a TV | Lisa Anna | [Pexels 19899066](https://www.pexels.com/photo/modern-living-room-with-tv-19899066/) | none |
| `video-call` | A woman on a video call at her kitchen table | Katrin Bolovtsova | [Pexels 4049991](https://www.pexels.com/photo/happy-woman-video-chatting-on-laptop-in-kitchen-4049991/) | identifiable |
| `repair-mat` | Disassembled smartphone parts on a blue repair mat with tools | Fotografia Lui Vlad | [Pexels 31862950](https://www.pexels.com/photo/disassembled-smartphone-on-repair-workbench-31862950/) | none; retouched: the Apple logo and every printed mark on the battery's label, the Apple logo on the logic board chip, a part's name and logo, the lettering printed on the mat |
| `cracked-screen` | Two phones with cracked screens on an orange background | Towfiqu barbhuiya | [Pexels 11921157](https://www.pexels.com/photo/cracked-screen-of-a-smartphone-11921157/) | none |
| `cafe-business` | A woman using her phone and laptop in a café | RDNE Stock project | [Pexels 10375885](https://www.pexels.com/photo/smiling-woman-using-smart-phone-at-cafe-10375885/) | identifiable; retouched: the emblems embroidered on her polo shirt |
| `seniors-phone` | An older couple at a kitchen table looking at a phone | T Leish | [Pexels 6975187](https://www.pexels.com/photo/an-elderly-couple-using-a-smart-phone-6975187/) | identifiable |

**Retouching.** Stock photos show real products with real printing on them. The design test requires that no photo shows a third-party brand name, logo or emblem a visitor could read, so `sources.json` lists what to remove and `imagery.py render` does it to the finished crops; the original files are never changed. Each photo's `retouched` list in `photos.json` records what was removed, and the Photo credits page says so. An earlier run of this check missed several marks that show only at full size (the "Designed by Apple in California" line on the unboxing card, words on a clear phone case and on the repair mat, a "Taptic Engine" label, a faint Apple logo on a white case, and the emblems on the café photo's polo shirt). They were found by reading every photo at full size and by running text recognition over every file the site serves, and they are removed now. A separate agent's read of v4 then found three smaller leftovers (faint lettering on the concert wristband, and on the repair photo's battery label a certification mark, a recycling symbol and small print, plus a faint smudge where the Apple logo had been erased); v6 removes the wristband lettering and the whole battery label, plus two more things found on the way: the picture of a phone printed on the unboxing photo's carton and a dark smear on the train photo's background pole. Earlier runs had answered the test's question about brand marks "yes, none"; that answer was wrong, and the question is answered again for this version.

**Logos next to photos.** Carrier logos sit unaltered on white plates over the provider, brand and deal photos, but only on photos where nobody can be recognised (hands, a crowd from behind, rooms, parts), so no one appears to endorse a brand or the store. The home page's hero carries the "Plans from" bar of the three logos along its foot. The social preview image (shown when a link is texted) is a plain crop of the hero photograph, with nothing added to it.

**Numbers.** Atkinson Hyperlegible Next draws a slashed zero so that 0 and O can't be mistaken for each other, which means the phone number and the hours show slashed zeros. It's the typeface's own design for legibility and the font file here has no plain-zero alternate. Say if you'd rather have a different typeface.

**Wording.** Design 2 doesn't reuse design 1's sentences. Facts every design must state (the store's details and hours, the example offers, the carriers, and program names such as Bell SmartPay) come from `src/site.json` and are shared; everything else is written for this design: its page copy in `designs/design-2/pages/`, and its `content.json` (the one-line description of each carrier, the repair list, the FAQ and the thank-you messages). The design test compares the two designs' wording, and a page that reuses design 1's sentences, headings or navigation labels fails it. A sentence counts as reused when it is at least 60% the same as one of design 1's, so changing a few words isn't enough. The deal cards show the same example offers in both designs, because the offers are shared placeholders until the store supplies real ones.

**Changing a photo.** Everything about a photo lives in `designs/design-2/imagery/sources.json`: where it came from, its licence, who is in it (`none`, `no faces` or `identifiable`), its alt text, its crops (shape, focus point, zoom, widths and, optionally, which file types to write; the link-preview crop is a single JPEG) and any retouch (a box or polygon to fill, with the reason). A retouch fills the area in one of five ways: `smooth` (the default) blends a box from its four edges, `inpaint` uses OpenCV inpainting, `rows` continues each row of a band from its two ends, and `marks` erases only the printed pixels inside a box or polygon, optionally keeping a finger or an edge untouched (`keep`, `protect_sat`), filling from the surface itself or, with `"method": "laplace"`, by smoothly continuing the tone around the mark, and, with `"texture": "copy"`, laying a clean patch's real weave and grain under the fill so it can't be seen. Then (needs Python 3.10+, Pillow, numpy, OpenCV and Playwright with Chromium):

```sh
python3 rsi/imagery.py fetch --design designs/design-2    # download originals and record their fingerprints
python3 rsi/imagery.py render --design designs/design-2   # grade, retouch, crop, encode AVIF/WebP/JPEG, write photos.json
python3 rsi/imagery.py audit --design designs/design-2    # licences, hosts, credits, fingerprints, no faces where none are declared
python3 rsi/imagery.py sheet --design designs/design-2 --out sheet.png   # contact sheet with credits
python3 build.py --design design-2
```

Originals aren't stored in git (`fetch` restores them and checks they're the same files). The rendered photos are, because the site needs them. Only `images.pexels.com` and `images.unsplash.com` are accepted as sources, and paid Unsplash+ images are refused.

## Before launch

These are things I couldn't confirm from public listings. Please check each one. The same list is the `unconfirmed` entry in `src/site.json`: every build prints it as a "Before launch" note, and `python3 build.py --release` refuses to build until the example offers are replaced and that list is empty. Delete an entry once the store has confirmed it.

- [ ] **Postal code.** The business card reads "I6X OG3", which the site shows as **L6X 0G3**; the Google listing also shows L6X 0G3. Bell's store locator lists the store at **L6X 5K7**. Check with Canada Post and fix `store.postal` in `site.json` if needed.
- [ ] **Sunday hours.** The site and Bell's store locator say 10 a.m. to 8 p.m. every day, but the Google listing shows Sunday 10:30 a.m. to 7 p.m. Confirm Sunday hours and update `hours` in `site.json`; the open/closed signs follow automatically.
- [ ] Replace the five example offers with real ones, or delete them. `python3 build.py --release` refuses to build while any remain.
- [ ] Confirm the site will live at `https://www.twireless.ca` (set in `site.base_url`; it drives canonical links, the sitemap and the social preview image).
- [ ] Confirm the Bell family page matches what the store can set up, especially Satellite TV, Home Phone, business plans, Bell SmartPay and the Device Return Option. Re-check it when Bell changes a program.
- [ ] Confirm the repair list, and that you quote repairs before starting.
- [ ] **Things the site says that I couldn't verify.** Confirm each, or tell me to change it: the entrance is wheelchair accessible (from the store's Google listing; it appears on Home, Visit us and in the FAQ); the map sketch and the line under it, "South side of Bovaird, just east of Chinguacousy Rd", match the real storefront; you take trade-ins ("Ask if it can earn credit toward the new one"); and what you ask customers to bring when they set up a plan or move a number (design 2 says a recent bill with the account number, and photo ID in case you need it; design 1 says government-issued photo ID). Also the way the store works, as the pages describe it: repairs are quoted before work starts, you give a collection time and the customer tries the phone at the counter; you handle a number transfer and the old plan then closes by itself; you look up the address and book the Bell technician for home internet and TV.
- [ ] **Program details to double-check.** A few lines about the brands come from Bell and third-party pages read on October 26, 2026, and the independent reviewer couldn't open Virgin Plus's or Lucky Mobile's own pages to check them: that Member Benefits perks change over time, that some bundles include Crave (design 1 only; design 2 doesn't say it), that a phone or tablet can keep some Fibe TV recordings and on-demand shows for offline viewing, and the Lucky Mobile lines (no credit check, no lock-in, no overage charges for data). Confirm each with your Bell contact.
- [ ] Confirm walk-ins are welcome (FAQ answer), that staff will call back form requests, and that Ali is happy to be named on the Visit page.
- [ ] **Carrier logos.** The logos on the site came from the brands' public websites, not from Bell's dealer kit. Before launch, get sign-off from your Bell dealer or brand contact for showing the Bell, Virgin Plus and Lucky Mobile logos online, and swap in their files if they send different versions (see "Carrier logos" above). Check their rules on clear space, minimum size and backgrounds, and on using Bell blue (Pantone 301, a shade Bell has applied to trademark). If design 2 is chosen, show them the logos on photos and on the phone screens too.
- [ ] Review the Privacy page. It says the site sets no tracking cookies and that you delete old requests.
- [ ] Update the Google rating in `site.json` from time to time (4.1 from 91 reviews on October 26, 2026), or remove it from the home page.
- [ ] Design 2: the photos are stock photos. Real photos of the store, the counter and the repair bench would be stronger; add them to `sources.json` the same way (with written consent from anyone recognisable in them). Four stock photos show recognisable people (`family-tv`, `video-call`, `cafe-business`, `seniors-phone`); Pexels' pages mention no model release for them, and the Pexels License doesn't promise one, so swap them for your own photos if you want that risk gone.
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

Version 2.0 keeps every 1.0 run valid (design 1's results re-evaluate to the same numbers) and adds what several designs with photography need; version 2.1 of the tool adds the wording and composite checks below. A contract switches each part on:
- **Imagery.** Every photo on a page must be listed in the design's `photos.json` under an allowed licence, served as AVIF or WebP with a JPEG fallback for older iPhones, sharp but not oversized for its shown size, within a byte budget, lazy below the first screen, with the biggest photo on the first screen loaded first. The imagery audit (licences, sources, fingerprints, and a face detector confirming that photos declared faceless show no faces) must pass, and the build must carry the design's current `photos.json`. A contract can also cap composited photos per page (design 2 allows none) and require that the hero is a real photograph.
- **Logos.** Each page shows the logos its role needs; logo files are byte-for-byte the approved ones; each logo is drawn big enough, undistorted and on a clean white plate; no logo sits on a photo of someone who can be recognised.
- **Distinctness.** The design's first screens (phone and desktop), palette and typefaces are compared with the other designs' runs: structural similarity of the first screens at most 0.45, palette distance at least 12, a different headline typeface. Calibration: two builds of design 1 that differ below the fold score 1.0 and 0; design 1's first version against its redesign scores 0.16 and 8.6 (same design family, so not distinct enough).
- **Wording.** Two designs for one store must say the same facts but not the same sentences. `measure` (against each sibling design named in the contract) and `distinct` take the shared facts out (store details, hours, offers, carriers, listed program and place names) and compare what is left: how many four-word phrases the two designs share, how many whole sentences are reused, how many headings and navigation labels match, and how alike each page's title, description, heading and lead are. Design 2's contract allows at most 0.15 phrase overlap, 0.05 reused sentences (a sentence is reused when it is 0.6 alike to one of the sibling's; the tool's default is 0.85), 0.15 shared headings and 3 shared navigation labels, and no page field more than 0.7 alike. `python3 rsi/web_design_rsi.py copy --a <run or build> --b <run or build> --contract ...` shows the comparison on its own and lists every flagged page.
- **Accuracy questions from the contract.** Design 2's review also answers: are the photos licensed for commercial use; does any photo imply it shows the store, staff or customers; are carrier logos unaltered on clean plates; are there third-party brand marks in the photos; was the wording written for this design rather than reused from another.
- **Evidence.** Each page is scrolled so lazy photos load before full-page screenshots; the first phone screen of each page, the imagery contact sheet and the distinctness screenshots are kept too.

| Path | What it is |
| --- | --- |
| `rsi/web_design_rsi.py` | The harness: `measure`, `template`, `evaluate`, `compare`, `distinct`, `copy`. |
| `rsi/imagery.py` | The imagery tool: `fetch`, `render`, `sheet`, `audit`. |
| `rsi/models/` | The YuNet face detector the audit uses (OpenCV Zoo, MIT licence). |
| `rsi/contracts/design-1.json` | Design 1's 1.0 contract: weights for 11 dimensions, the gates, pages and roles, measured thresholds. |
| `rsi/contracts/design-2.json` | Design 2's 2.0 contract: 13 dimensions (adds imagery quality, logo integration and distinctiveness), eight accuracy questions, imagery, logo, distinctness and wording checks, and the client's feedback that led to them. |
| `rsi/runs/design-1/` | Design 1's runs, v1 to v6. |
| `rsi/runs/design-2/` | Design 2's runs, v1 to v6. Each folder holds `measured.json`, the exact build it measured (`site/`), hashed screenshots (`evidence/`), the producer's `review.json` and `result.json`, and for v4 and v5 an independent agent's `review-independent.json` (v4 has only that one; v6's review is being added). |

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

Results on October 26, 2026. The producer (EMBLEM-NLP) scored v1, v2, v3 and v5 below (v4 and v6 are measured only so far). v4 and v5 were also read by a separate Claude agent that saw only the screenshots and files and wasn't shown the producer's scores (see "Independent read" below); that is not a human reviewer, so release stays blocked. v1 to v3 had 289 measured checks each; v4 to v6 have 305 (49 kinds): the test gained five wording checks, a composited-photo limit on each page and a check that each hero is a real photograph, and dropped the old logo-composite check. Whether a photo carries a third-party mark isn't something the test can measure; it's one of the review's accuracy questions, answered from reading every photo at full size.

| Run | What it is | Measured checks | Review score | Gate result |
| --- | --- | --- | --- | --- |
| `v1-candidate` | First full build, with a composited phone screen as the hero | 0 of 289 failed | 85.9 | Fails the accuracy gate: two photos still carried third-party marks (Apple logos on the repair photo's battery, a transit operator's logo on the train photo's ticket machine). The two-phones photo also appeared twice on the Mobile page, the phone navigation scrolled sideways, and the Bell family comparison table scrolled sideways on phones. |
| `v2-candidate` | v1 with the marks retouched out, a second phone-in-hand composite for "New phones", all six pages shown in the phone navigation, and the comparison stacked into cards on phones | 0 of 289 failed | 88.8 | **Promoted over v1 (+2.9)**, no dimension regressed. Status `DIAGNOSTIC_PROMOTED_RELEASE_BLOCKED`. |
| `v3-candidate` | v2 plus two fixes from the HTML validator, with no visual change (the first demo the owner saw) | 0 of 289 failed | 88.8 | Not promoted over v2 (+0.0); same design. |
| `v4-candidate` | The rebuild after the owner's feedback ("not a fan of this composed hero image", "the copy remains exactly the same as our first version"): a real, uncomposed hero photograph, wording written for this design, no composited photos, and the third-party marks that v1 to v3 missed retouched out of the photos | 0 of 305 failed | not scored by the producer | Measured only. The independent agent read it. Superseded by v5, which only adds styling polish. |
| `v5-candidate` | v4 plus a polish pass: the footer is its own tint with a red top rule, more space under headings, a checklist no longer touching the rating line, and an evenly wrapped header tagline | 0 of 305 failed | 84.9 | Not promoted: 84.9 is under the 85 overall gate and 3.9 under v2's 88.8 (see below). Every other gate passes: critical dimensions, page roles and accuracy. |
| `v6-candidate` | v5 plus the fixes from the independent read of v4 and v5: the remaining printed marks retouched out of the photos, the link preview is a plain crop of the hero photograph, wording rewritten wherever it echoed design 1 (a sentence now counts as reused at 60% alike, not 85%), the first-screen buttons on Home and Visit us clear of the bottom bar on a phone, a shorter opening on Compare plans, and desktop alignment fixes (the build in `dist-design-2/` and the demo) | 0 of 305 failed | being reviewed | Measured only so far. |

**Why v5 scores below v2.** The producer scored v5 more strictly than v1 to v3. v2's 88.8 came from a review that attested no photo carried a third-party mark (wrong, as above), and v1 to v3 were scored before the test measured wording or composites, so their scores can't be compared with v5's. Five dimensions drop in the comparison (imagery, navigation, brand identity, trust signals, information economy; half a point each). The measured layer is clean (0 of 305 failed), and v5 is the only design 2 build that passes the contract's current wording and composite rules: v3 shares 80% of its four-word phrases, 79% of its sentences and 98% of its headings with design 1, where v5 shares 6.5%, none and none. Whether to ship v5 is the owner's call.

Against design 1, design 2's first screens (v6) score 0.11 for structural similarity (0.06 on a phone, 0.16 on desktop; the limit is 0.45) and 14.0 for palette distance (the minimum is 12; v5 scored 15.7 before the hero became a plain photograph), with different headline and body typefaces (Atkinson Hyperlegible Next against Source Serif 4 and Figtree). On wording, 2.9% of design 2's four-word phrases appear in design 1 (5.0% the other way round; the limit is 15%), no sentence is reused (at the stricter 60% rule), no heading is shared, and three navigation labels match (Deals, Internet and TV, Repairs; the limit is 3).

In the producer's v5 review, design 2's weakest dimension was brand identity (3.5 of 5): the page is Bell blue and white, as briefed, and the store's own red appears only in its logo and the footer's top rule. Imagery, navigation, trust signals, information economy and grid rhythm each scored 4: every photo is stock and none shows the store; the header isn't fixed, so on the two longest pages (about eight and a half phone screens each) only the Call, Directions and Book bar stays in view; and the home page repeats some of the Phones and Compare plans content. The Deals page's information gain stays at 3.5 of 5 until real offers replace the examples.

Lighthouse 13.5.0 (mobile) for design 2's build (v6), with the photos a phone loads on each page:

| Page | Performance | Accessibility | Best practices | SEO | Largest paint | Layout shift | Transfer | Photos (size) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Home | 99 | 100 | 100 | 100 | 2.0 s | 0.002 | 218 KB | 6 (95 KB) |
| Bell family | 100 | 100 | 100 | 100 | 1.9 s | 0.000 | 172 KB | 5 (119 KB) |
| Deals | 99 | 100 | 100 | 100 | 2.0 s | 0.000 | 174 KB | 5 (56 KB) |
| Mobile | 99 | 100 | 100 | 100 | 2.0 s | 0.000 | 207 KB | 6 (89 KB) |
| Internet and TV | 100 | 100 | 100 | 100 | 1.9 s | 0.000 | 179 KB | 3 (80 KB) |
| Repairs | 100 | 100 | 100 | 100 | 1.7 s | 0.000 | 143 KB | 2 (45 KB) |
| Visit us | 100 | 100 | 100 | 100 | 1.7 s | 0.000 | 99 KB | 0 (0 KB) |

Both designs pass html-validate's recommended rules except two style rules left off on purpose: one asks for a non-breaking hyphen and spaces inside every phone number (that would stop a search for the number with ordinary hyphens from finding it on the page), the other limits titles to 70 characters (six of design 2's run 72 to 82 characters, which search engines may shorten). Every internal link, anchor and icon reference resolves, and no page scrolls sideways at 360, 390 or 1440 pixels. Each run folder keeps the exact build it measured (`site/`) and its hashed screenshots (`evidence/`), so `evaluate` and `compare` can re-check them anywhere. The screenshots are large, so they ship in a separate `t-wireless-rsi-evidence.zip`; unzip it in the same place as this folder and the `evidence/` folders drop into their runs.

### Running the test

Needs Python 3.10+, Playwright for Python with Chromium, Lighthouse, and for 2.0 contracts Pillow, numpy and OpenCV. To clear a release block, an independent reviewer scores the build that ships from its screenshots:

```sh
python3 rsi/web_design_rsi.py template --measured rsi/runs/design-2/v5-candidate/measured.json --contract rsi/contracts/design-2.json --reviewer-id REVIEWER-NAME --reviewer-role independent_reviewer --out rsi/runs/design-2/v5-candidate/review-independent.json
# fill in each 0-5 score and rationale, set "status": "reviewed", answer the accuracy questions
python3 rsi/web_design_rsi.py evaluate --contract rsi/contracts/design-2.json --measured rsi/runs/design-2/v5-candidate/measured.json --review rsi/runs/design-2/v5-candidate/review-independent.json --out rsi/runs/design-2/v5-candidate/result-independent.json
```

For design 1 use `rsi/contracts/design-1.json` and `rsi/runs/design-1/v6-candidate/`. Then set `"approved_for_production": true` in the contract once the owner signs off. To test a later change to design 2:

```sh
python3 build.py --design design-2
python3 rsi/web_design_rsi.py measure --site dist-design-2 --contract rsi/contracts/design-2.json --out rsi/runs/design-2/v6-candidate
python3 rsi/web_design_rsi.py template --measured rsi/runs/design-2/v6-candidate/measured.json --contract rsi/contracts/design-2.json --reviewer-id REVIEWER-NAME --out rsi/runs/design-2/v6-candidate/review.json
# fill in the review, then compare with the build it replaces (v5)
python3 rsi/web_design_rsi.py compare --contract rsi/contracts/design-2.json --incumbent-measured rsi/runs/design-2/v5-candidate/measured.json --incumbent-review rsi/runs/design-2/v5-candidate/review.json --measured rsi/runs/design-2/v6-candidate/measured.json --review rsi/runs/design-2/v6-candidate/review.json --out rsi/runs/design-2/v6-candidate/promotion.json
```

`measure` copies the build into the run, so `dist-design-2/` can be rebuilt afterwards. To see how different any two designs look: `python3 rsi/web_design_rsi.py distinct --run-a rsi/runs/design-2/v5-candidate --run-b rsi/runs/design-1/v6-candidate --contract rsi/contracts/design-2.json`. The wording numbers read "how much of A's wording is in B", so put the design you're checking first (design 2 against design 1 gives 6.5%, design 1 against design 2 gives 10.7%). A design 3 gets its own folder in `designs/`, its own contract (with designs 1 and 2 as siblings for the distinctness check) and its own runs folder.

Scores are reviewer observations backed by Lighthouse and browser measurements. They are not a measure of how visitors behave.

## Rights

© 2026 EMBLEM-NLP. All rights reserved. This repository has no open-source licence on purpose: the code, copy and illustrations may not be copied, reused or adapted without written permission. Who owns the site after launch is set by the agreement with T Wireless. Parts made by others keep their own terms:
- Source Serif 4, Figtree and Atkinson Hyperlegible Next fonts: SIL Open Font License (licence files in `src/assets/fonts/` and `designs/design-2/assets/fonts/`).
- Design 2's photos: their photographers on Pexels, used under the Pexels License (listed above and on the Photo credits page). The licence doesn't allow redistributing them on their own.
- YuNet face detection model: MIT License (`rsi/models/LICENSE-yunet.txt`).
- T Wireless logo and phone mark: T Wireless.
- Bell, Virgin Plus and Lucky Mobile logos: trademarks of Bell Canada and its licensors, used to show the brands an authorised retailer sells, subject to Bell's approval.

## Credits

Fonts: Source Serif 4, Figtree and Atkinson Hyperlegible Next, all under the SIL Open Font License. Photos in design 2: Imad Clicks, Pavel Danilyuk, Kaboompics, Chase R. Smith, MART PRODUCTION, World Sikh Organization of Canada, Lisa Anna, Katrin Bolovtsova, Fotografia Lui Vlad, Towfiqu barbhuiya, RDNE Stock project and T Leish, on Pexels. Logo and phone mark: T Wireless. Bell, Virgin Plus and Lucky Mobile logos: trademarks of Bell Canada and its licensors, shown as supplied. Design 1's storefront, map and service illustrations are drawn for this site.
