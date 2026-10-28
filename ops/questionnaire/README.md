# Website questionnaire kit

A questionnaire a client fills in before their site goes live. One data file makes two things: a **web app** the client opens from a link (sections, a progress bar, answers saved on the client's phone), and a Google Form script for anyone who prefers a form. This copy is for T Wireless (Ali is the contact). It asks only for facts the site would otherwise have to guess, and each question says what the public listings show, so the client can answer "yes, that's right" instead of writing from scratch.

| File | What it is |
| --- | --- |
| `twireless.questionnaire.json` | The questionnaire: every page, question, help line, option and jump, plus (for us only) which part of the site each answer unlocks. Edit this, then rebuild. |
| `build_questionnaire.py` | Checks the data, then makes everything below. |
| `app/` | The web app's parts: `template.html` (the page), `app.css`, `app.js`, and `check_app.py`, the browser test (see below). The build joins them and the data into one file. |
| `../../docs/questionnaire/index.html` | The web app, built: one self-contained page (fonts, logo and styles inside it, about 180 KiB) that GitHub Pages serves at <https://emblem-nlp.github.io/twireless-site/questionnaire/>. `demo.py` rebuilds it. |
| `assets/share.png` | The 1200 by 630 picture that shows when the web app's link is shared in a message. |
| `create_twireless_form.gs` | A Google Apps Script that builds the whole form in the account that runs it. The banner is inside it. |
| `assets/header.png` | The 1600 by 400 banner: the T Wireless logo, the street, "Prepared by EMBLEM-NLP", a red and blue strip. |
| `twireless-questionnaire-preview.pdf` | What the client will see, 17 pages, for reading on a phone. It is printed from an `.html` file the build also writes, which git ignores. |
| `check_form_script.js` | A dry run of the script against a stand-in for Google Forms (see below). |

## The web app (what Ali opens)

Send Ali the link. Ali sees a welcome screen, then 18 short sections, one per screen, with a progress bar along the top and a Next button along the bottom. The bar has one segment per section, grouped by part, and says about how many minutes are left in the part. Most answers are one tap. A "Sections" button opens a list for jumping back; sections not reached yet are locked, so nothing is skipped by accident.

- **Same questions, same logic.** Every question, help line, option and "Other" box comes from the data file. "No" to repairs or to business customers hides the details that follow (answers typed earlier come back if the answer is changed back). The two "keep going or finish later" pages become stops between the parts.
- **Saved on the phone.** Every answer is saved in the browser as Ali goes, so Ali can close the page and open the link again later. The welcome screen then says "Welcome back" and offers to carry on or to erase everything. Saved answers live only in that browser: clearing the browser's data, or opening the link on another device, starts over, and some browsers clear it on their own after a week or more without a visit.
- **Required answers.** A required question that is empty stops Next, shows a message in words, and moves focus to it. The page also announces, in a live region, how many questions need an answer.
- **Sending.** The last screen lists every answer, with an Edit button on each section (after an edit, the bottom button reads "Back to my answers"). It offers **Send my answers** (the phone's share sheet: Ali picks Messages, WhatsApp or email and a person), **Copy my answers** and **Save as a file**. The text it sends is plain and readable, with Part 1, 2 and 3 marked finished or not started. "Finish later" at either stop goes straight to this screen, so Ali can send what there is so far; Part 1 alone is enough for Phase 1 of the site.
- **Nothing is sent by the page itself.** It has no email address inside it and, by its content security policy, no way to contact any server, so a person has to press Send and choose the recipient. The tradeoff is that nothing arrives unless Ali does. To have answers arrive on their own, build the page with an address that accepts them: `python3 ops/questionnaire/build_questionnaire.py app --endpoint https://example.com/receive`. Send then posts one JSON message (`form`, `version`, `sent_at`, `complete`, `answers` by question id, and the readable `text`) as `text/plain`, so the receiver needs CORS but no pre-flight. The page's policy then allows that one address and no other. This path has been tried only against a stand-in receiver on this computer, never a real one.
- **Unlisted, not private.** The page says `noindex`, so search engines that respect it leave it out. Anyone with the link can open it, and the repository is public, so don't put anything secret in the questions.

To change wording, edit `twireless.questionnaire.json` and run `python3 demo.py` (or `build_questionnaire.py app`). The data file has a few fields only the web app reads, all optional:

| Field | Meaning |
| --- | --- |
| `form.app.done`, `form.app.partial` | The line under the thank-you heading when everything is done, and when Ali is sending only part of it. |
| section `app.description` | Replaces the page description in the web app. Used on the two stops, where the Google Form's text talks about "Edit your response". |
| question `app.exclusive` | Options that clear the other ticks when chosen (such as "None of these"). |
| question `app.autocomplete`, `app.inputmode` | Hints for the phone's keyboard and autofill. |

`APP_VERSION` in `build_questionnaire.py` is part of the key the answers are saved under. Raise it when a change to the questions means answers saved on people's phones should no longer be used.

### The browser test

```sh
python3 ops/questionnaire/app/check_app.py              # builds the page to a temporary folder and tests that
python3 ops/questionnaire/app/check_app.py --axe PATH   # also runs axe-core's accessibility rules (PATH is its axe.min.js)
```

It needs Playwright for Python with Chromium. It acts like Ali: taps through all 20 screens, leaves required answers empty, picks "No" at the gates, reloads and comes back, tries the Other boxes and the "choose up to" limits, presses Copy, Save and Share, and checks that the text it produces holds every answer in order. It also checks that nothing sticks out sideways on any screen from 320 to 1280 px wide, that every tap target is at least 44 px tall, that the page asks the network for nothing but itself, and that the send address works against a local stand-in. It exits with 1 if any check fails.

What it can't tell you: how Safari on an iPhone draws and scrolls the page, how a screen reader reads it, what the share sheet offers on Ali's phone, or whether a real receiver accepts the post. Those need a real phone. Open the link on one before sending it, and send yourself a test.

## Optional: the same questions as a Google Form (about three minutes, at a computer)

The web app doesn't need this. Use it if you'd rather send a Google Form.

1. Go to <https://script.google.com> and choose **New project**. Delete the sample code, paste in the whole of `create_twireless_form.gs`, and press Save. (On a phone, open the file's **Raw** view on GitHub, select all, copy.)
2. Choose **createQuestionnaireForm** in the function menu and press **Run**. Google asks for permission to create and edit Google Forms and nothing else. It warns that the app isn't verified because it's your own new script: choose **Advanced**, then **Go to** the project, then **Allow**.
3. Open the **Execution log** at the bottom. It prints the link to edit the form and the link to send to the client.
4. In the form, open the palette icon. Set the theme colour to `#00549A`, the background to `#E6EEF7` and the font to **Basic**. A script can't set these. The banner is already at the top of the first page, and `assets/header.png` can also go in as the header image.
5. On the **Responses** tab, turn on email notifications. The three-dot menu can link a Google Sheet.
6. Send yourself a test response. Check the jumps (Repairs "No", Business "No", the two "finish later" choices), delete the test response, then send the client the link.

Each run makes a new form; delete extra copies from Google Drive. The script turns on "Allow response editing", so a client who stops after Part 1 or Part 2 can come back through the "Edit your response" link on the last page. It doesn't ask the client to sign in, and the form has no file upload (an upload question forces sign-in), so photos arrive by text or email.

## How the questionnaire is built

Three parts, each ending with a way out, so a busy shop owner can stop and still have given us something useful:

- **Part 1, what we need first (31 questions).** Store details that listings disagree on, the web address and online accounts, what the store sells and sets up, repairs, and business customers. Phase 1 of the recommendations (phones in store, repair brands, Business Solutions) needs only this part.
- **Part 2, before the site goes live (17).** How the store works, offers and dated notices, Bell's name and logos and the phone makers' logos, where messages go, privacy, photos.
- **Part 3, for the next pages (27, optional).** Trade-ins and recycling, accessories and payments, about the store (ownership, languages, team), repair terms, accessibility, social accounts and goals.

Two answers send the client past questions that don't apply: "No" to "Does the store repair devices?" skips the repair details, and "No" to "Does the store help businesses?" skips the business details. A page can also end the form (the two "finish later" choices).

### The data file

Top level: `client`, `form` (title, description, confirmation, theme, settings), `parts`, `sections`. A section is one page of the form. A question has:

| Field | Meaning |
| --- | --- |
| `id`, `title`, `help`, `required` | Identifier, the question, the grey line under it, whether it must be answered. |
| `type` | `text`, `paragraph`, `choice` (pick one), `checkbox` (pick any), `grid` (rows by columns). |
| `options`, `other` | The choices. `other` adds Google's "Other:" box. Google Forms can't combine "Other" with a jump, so a question with `goto` can't have it. |
| `rows`, `cols` | For a grid. |
| `max_choices` | For a checkbox: "choose up to N". |
| `goto` | `{ "option text": "section id" }` to skip ahead, `"@submit"` to end the form. Jumps only go forward. |
| `unlocks`, `why` | For us only, left out of the script and the web app: tags such as `check:4` (item 4 of the README's "Before launch"), `phase1:business`, `confirm:languages`, and a note on why we ask. They drive the coverage tables in the research notes. |
| `app` | Optional hints for the web app only (see above), also left out of the script. |

`python3 ops/questionnaire/build_questionnaire.py check` validates the file (unique ids, real jump targets, no empty options, nothing too long for Forms). `all` rebuilds the banner, the share picture, the script (and runs the dry run), the preview and the web app.

### For another client

Copy the data file, change `client` and the questions, and run `build_questionnaire.py all --data your-file.json`. The banner uses the logo in `src/assets/img/`; point `LOGO` in the script at theirs, and `APP_LOGO`, `FAVICON` and `APP_URL` for the web app. The web app's fonts are in `designs/design-2/assets/fonts/`. The script, the preview, the web app and the dry run don't otherwise depend on T Wireless, but `check_app.py` names this questionnaire's questions, so change those checks to match.

## What the dry run checks, and what it doesn't

`check_form_script.js` runs the script against a stand-in for Google Forms that has only the methods Forms is supposed to have, so a typo fails here and not halfway through a real run. It then compares what was built with the data file, item by item: titles, help text, required flags, options, grids, "Other", and where each choice jumps. It currently builds 99 items (a banner, 23 pages, 75 questions) and 7 jumps.

It can't check how Google draws the form, whether Google accepts every call, or the colours. The script was written from Google's Apps Script reference for `FormApp` and has not yet been run on real Google Forms, so send yourself a test response first (step 6 above).

## Sources the questions were written from

The questions quote what Bell's store finder, Yellow Pages, MapQuest and the Google listing show for the store, and what the registry and DNS lookups show for the web addresses, all read on October 28, 2026. The research notes (kept out of this public repository) list each source and what couldn't be checked.
