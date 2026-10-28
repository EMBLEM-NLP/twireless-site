# Website questionnaire kit

A questionnaire for a business that has not asked for a website. We build draft designs from public information, then ask the business to correct them. One data file makes two things: a **web app** the business opens from a link (sections, a progress bar, answers saved on the phone), and a Google Form script for anyone who prefers a form. This copy is for T Wireless, a Bell Authorised Retailer in Brampton that has never heard of us.

That shapes the whole thing. The first screen says who we are and that nobody asked us to do this. Every question is optional, so the store can skip anything or everything. It never asks who the person is, only what the store does. The questions go from the lightest (is this postal code right?) to the heaviest (who runs your Google listing?), and the store can stop at the end of any part. Each question says what the public listings show, so the store can answer "yes, that's right" instead of writing from scratch.

| File | What it is |
| --- | --- |
| `twireless.questionnaire.json` | The questionnaire: every page, question, help line, option and jump, plus (for us only) which part of the site each answer unlocks. Edit this, then rebuild. |
| `build_questionnaire.py` | Checks the data, then makes everything below. |
| `app/` | The web app's parts: `template.html` (the page), `app.css`, `app.js`, and `check_app.py`, the browser test (see below). The build joins them and the data into one file. |
| `../../docs/questionnaire/index.html` | The web app, built: one self-contained page (fonts, logo and styles inside it, about 190 KiB) that GitHub Pages serves at <https://emblem-nlp.github.io/twireless-site/questionnaire/>. `demo.py` rebuilds it. |
| `assets/share.png` | The 1200 by 630 picture that shows when the web app's link is shared in a message. |
| `create_twireless_form.gs` | A Google Apps Script that builds the whole form in the account that runs it. The banner is inside it. |
| `assets/header.png` | The 1600 by 400 banner: the T Wireless logo, the street, "Prepared by EMBLEM-NLP", a red and blue strip. |
| `twireless-questionnaire-preview.pdf` | What the store will see in the Google Form, 17 pages, for reading on a phone. It is printed from an `.html` file the build also writes, which git ignores. |
| `check_form_script.js` | A dry run of the script against a stand-in for Google Forms (see below). |

## The web app (what the store opens)

The store gets the link. The first screen says who we are, what we made and from what ("using only public information"), that nobody asked us to, that every question is optional, and that if the store would rather not take part there is nothing to do, and if it wants the drafts taken down it only has to tell us. A button, "See the drafts", opens what we made in a new tab; the answers stay saved here while the store looks. Then come 19 short sections, one per screen, with a progress bar along the top and a Next button along the bottom. The bar has one segment per section, grouped by part, and says about how many minutes are left in the part. Most answers are one tap. A "Sections" button opens a list for jumping back; sections not reached yet are locked, so nothing is skipped by accident.

- **Nothing is required, and nobody is asked who they are.** The only questions that can't be left alone are the choices at the three stops between the parts (keep going, or stop and send), because those are what moves the person on. Everywhere else the bottom button reads **Skip** until something on the screen is answered, then **Next**, and an answered choice can be cleared again ("Clear my choice"). The one thing the page still refuses is an "Other" answer with nothing typed in its box, and it says how to get out of it. If someone skips every screen, the last screen says "You haven't answered anything yet", offers nothing to send, and takes them back to the first question. There is no name, phone number or email field. The questions are about the store, and a name appears in only one of them, quoting what the drafts' Visit page says.
- **Same questions, same logic.** Every question, help line, option and "Other" box comes from the data file. "No" to repairs, to business customers or to trade-ins hides the details that follow (answers typed earlier come back if the answer is changed back). The three "keep going or finish later" pages become stops between the parts.
- **Saved on the phone.** Every answer is saved in the browser as the person goes, so they can close the page and open the link again later. The welcome screen then says "Welcome back" and offers to carry on or to erase everything. Saved answers live only in that browser: clearing the browser's data, or opening the link on another device, starts over, and some browsers clear it on their own after a week or more without a visit.
- **Sending.** The last screen lists every answer, with an Edit button on each section (after an edit, the bottom button reads "Back to my answers"). It offers **Send my answers** (the phone's share sheet: the person picks Messages, WhatsApp or email and a recipient), **Copy my answers** and **Save as a file**. The text it sends is plain and readable, starts with its own title ("T Wireless: answers about the draft website"), and marks each part finished, started or not started. "Finish later" at a stop goes straight to this screen, so the store can send what there is so far; Parts 1 and 2 are enough for Phase 1 of the site.
- **Nothing is sent by the page itself.** It has no email address inside it (only the store's own public one, as an answer to pick) and, by its content security policy, no way to contact any server, so a person has to press Send and choose the recipient. The tradeoff is that nothing arrives unless the store does it. To have answers arrive on their own, build the page with an address that accepts them: `python3 ops/questionnaire/build_questionnaire.py app --endpoint https://example.com/receive`. Send then posts one JSON message (`form`, `version`, `sent_at`, `complete`, `answers` by question id, and the readable `text`) as `text/plain`, so the receiver needs CORS but no pre-flight. `complete` is true only when the person has been through every part and nothing is half answered. The page's policy then allows that one address and no other. This path has been tried only against a stand-in receiver on this computer, never a real one.
- **Unlisted, not private.** The page says `noindex`, so search engines that respect it leave it out. Anyone with the link can open it, and the repository is public, so don't put anything secret in the questions.
- **Which phones.** The layout uses flexbox `gap`, which needs iOS or Safari 14.5 (April 2021) or newer, or a current Chrome. On something older the page still works, but the spacing between some items is lost.

The link goes out in a first message, and that message is yours to write. It should say who you are and why you're writing, and give a way to say no, as the first screen does. In Canada an unsolicited text or email that promotes something can fall under the anti-spam law (CASL); check what it asks of you.

To change wording, edit `twireless.questionnaire.json` and run `python3 demo.py` (or `build_questionnaire.py app`). The data file has a few fields only the web app and its pictures read, all optional:

| Field | Meaning |
| --- | --- |
| `form.app.done`, `form.app.partial` | The line under the thank-you heading when everything is done, and when the store is sending only part of it. |
| `form.app.summary` | One or two sentences for the page's link preview and the share picture. `{minutes}` becomes Part 1's time. |
| `form.app.answers_title` | The first line of the answers text, and the title handed to the share sheet. It is the store's message to us, so it isn't the invitation's headline. |
| `form.app.banner_title`, `form.app.share_title` | The line under the logo on the Google Form's banner, and the large line on the share picture. |
| `form.app.preview` | `{ "label": "See the drafts", "url": "https://…" }`: the link on the welcome screen. It must be https. Leave it out for no link. |
| section `app.description` | Replaces the page description in the web app. Used on the stops, where the Google Form's text talks about "Edit your response". An empty string leaves the description out, which is right for a page that only appears after a "Yes" and whose Google Form text says to skip it. |
| question `app.exclusive` | Options that clear the other ticks when chosen (such as "None of these"). |
| question `app.autocomplete`, `app.inputmode` | Hints for the phone's keyboard and autofill. |

`APP_VERSION` in `build_questionnaire.py` is part of the key the answers are saved under. Raise it when a change to the questions means answers saved on people's phones should no longer be used.

### The browser test

```sh
python3 ops/questionnaire/app/check_app.py              # builds the page to a temporary folder and tests that
python3 ops/questionnaire/app/check_app.py --axe PATH   # also runs axe-core's accessibility rules (PATH is its axe.min.js)
```

It needs Playwright for Python with Chromium. It acts like the store: skips every screen and checks that nothing was asked of it, then taps through all 24 screens answering every question, picks "No" where a question skips others, stops at the end of a part and comes back, reloads, tries the Other boxes and the "choose up to" limits, presses Copy, Save and Share, and checks that the text it produces holds every answer in order. It checks that no question asks for a name, that the welcome screen says who we are, and that the page links to the drafts safely. It also builds a second copy of the page with every question made required, so the checks on required answers still run, though the questionnaire itself has almost none. It checks that nothing sticks out sideways on any screen from 320 to 1280 px wide, that every tap target is at least 44 px tall, that the page asks the network for nothing but itself, and that the send address works against a local stand-in. It exits with 1 if any check fails.

What it can't tell you: how Safari on an iPhone draws and scrolls the page, how a screen reader reads it, what the share sheet offers on the store's phone, or whether a real receiver accepts the post. Those need a real phone. Open the link on one before sending it, and send yourself a test.

## Optional: the same questions as a Google Form (about three minutes, at a computer)

The web app doesn't need this. Use it if you'd rather send a Google Form.

1. Go to <https://script.google.com> and choose **New project**. Delete the sample code, paste in the whole of `create_twireless_form.gs`, and press Save. (On a phone, open the file's **Raw** view on GitHub, select all, copy.)
2. Choose **createQuestionnaireForm** in the function menu and press **Run**. Google asks for permission to create and edit Google Forms and nothing else. It warns that the app isn't verified because it's your own new script: choose **Advanced**, then **Go to** the project, then **Allow**.
3. Open the **Execution log** at the bottom. It prints the link to edit the form and the link to send to the store.
4. In the form, open the palette icon. Set the theme colour to `#00549A`, the background to `#E6EEF7` and the font to **Basic**. A script can't set these. The banner is already at the top of the first page, and `assets/header.png` can also go in as the header image.
5. On the **Responses** tab, turn on email notifications. The three-dot menu can link a Google Sheet.
6. Send yourself a test response. Check the jumps (Repairs "No", Business "No", Trade-ins "No", the three "finish later" choices), delete the test response, then send the store the link.

Each run makes a new form; delete extra copies from Google Drive. The script turns on "Allow response editing", so a store that stops after Part 1 or Part 2 can come back through the "Edit your response" link on the last page. It doesn't ask anyone to sign in, and the form has no file upload (an upload question forces sign-in), so photos arrive by text or email. Only the three choices at the stops are required, so Google Forms shows its "* Indicates a required question" line at the top; no other question is required.

## How the questionnaire is built

Four parts, each ending with a way out (a stop where the store can send what it has), so a busy shop owner can stop and still have given us something useful. They run from what the store can check at a glance to what it may have to look up:

- **Part 1, check the basics (12 questions, about 4 minutes).** The postal code, phone, email, opening hours and holidays the listings disagree on; whether the entrance is step-free and how to describe where the store is; which phone brands and kinds of phone it sells; who is answering and what the store would like us to do next, including a way to say no (take the drafts down and stop).
- **Part 2, what the store does (14, about 6 minutes).** The services it can set up for each carrier, repairs, business customers, how the store works, offers and two dated notices. Phase 1 of the recommendations (phones in store, repair brands, Business Solutions) needs only Parts 1 and 2.
- **Part 3, online and Bell's rules (11, about 4 minutes).** The web address and who owns it, the Google listing, the Facebook page, who set things up, how Bell writes the store's title, and whether Bell has allowed the carrier and phone-maker logos on a website.
- **Part 4, more about the store (30, about 9 minutes, optional).** Messages and privacy, photos, trade-ins, recycling, accessories and payments, about the store (ownership, languages, story), repair terms, accessibility, social accounts and goals.

Three answers send the person past questions that don't apply: "No" to "Does the store repair devices?" skips the repair details, "No" to "Does the store help businesses?" skips the business details, and "No" to "Do you take trade-ins?" skips the trade-in details. A page can also end the form (the three "finish later" choices).

### The data file

Top level: `client`, `form` (title, description, confirmation, theme, settings, and the optional `app` words above), `parts`, `sections`. `client.contact` is the person we would speak to; it is only in the data, and the web app never shows it. A section is one page of the form. A question has:

| Field | Meaning |
| --- | --- |
| `id`, `title`, `help`, `required` | Identifier, the question, the grey line under it, whether it must be answered. Every question must say `required` either way. |
| `type` | `text`, `paragraph`, `choice` (pick one), `checkbox` (pick any), `grid` (rows by columns). |
| `options`, `other` | The choices. `other` adds Google's "Other:" box. Google Forms can't combine "Other" with a jump, so a question with `goto` can't have it. |
| `rows`, `cols` | For a grid. |
| `max_choices` | For a checkbox: "choose up to N". |
| `goto` | `{ "option text": "section id" }` to skip ahead, `"@submit"` to end the form. Jumps only go forward. |
| `unlocks`, `why` | For us only, left out of the script and the web app: tags such as `check:4` (item 4 of the README's "Before launch"), `phase1:business`, `confirm:languages`, and a note on why we ask. They drive the coverage tables in the research notes. |
| `app` | Optional hints for the web app only (see above), also left out of the script. |

`python3 ops/questionnaire/build_questionnaire.py check` validates the file (unique ids, real jump targets, no empty options, nothing too long for Forms, a drafts link that is https). `all` rebuilds the banner, the share picture, the script (and runs the dry run), the preview and the web app.

### For another client

Copy the data file, change `client` and the questions, and run `build_questionnaire.py all --data your-file.json`. The banner uses the logo in `src/assets/img/`; point `LOGO` in the script at theirs, and `APP_LOGO`, `FAVICON` and `APP_URL` for the web app. The web app's fonts are in `designs/design-2/assets/fonts/`. The script, the preview, the web app and the dry run don't otherwise depend on T Wireless, but `check_app.py` names this questionnaire's questions, so change those checks to match.

## What the dry run checks, and what it doesn't

`check_form_script.js` runs the script against a stand-in for Google Forms that has only the methods Forms is supposed to have, so a typo fails here and not halfway through a real run. It then compares what was built with the data file, item by item: titles, help text, required flags, options, grids, "Other", and where each choice jumps. It currently builds 96 items (a banner, a header, 24 page breaks, 70 questions) and 9 jumps.

It can't check how Google draws the form, whether Google accepts every call, or the colours. The script was written from Google's Apps Script reference for `FormApp` and has not yet been run on real Google Forms, so send yourself a test response first (step 6 above).

## Sources the questions were written from

The questions quote what Bell's store finder, Yellow Pages, MapQuest and the Google listing show for the store, and what the registry and DNS lookups show for the web addresses, all read on October 28, 2026. The research notes (kept out of this public repository) list each source and what couldn't be checked.
