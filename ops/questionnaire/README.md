# Website questionnaire kit

A questionnaire a client fills in before their site goes live, built as a Google Form from one data file. This copy is for T Wireless (Ali is the contact). It asks only for facts the site would otherwise have to guess, and each question says what the public listings show, so the client can answer "yes, that's right" instead of writing from scratch.

| File | What it is |
| --- | --- |
| `twireless.questionnaire.json` | The questionnaire: every page, question, help line, option and jump, plus (for us only) which part of the site each answer unlocks. Edit this, then rebuild. |
| `build_questionnaire.py` | Checks the data, then makes the three files below. |
| `create_twireless_form.gs` | A Google Apps Script that builds the whole form in the account that runs it. The banner is inside it. |
| `assets/header.png` | The 1600 by 400 banner: the T Wireless logo, the street, "Prepared by EMBLEM-NLP", a red and blue strip. |
| `twireless-questionnaire-preview.pdf` | What the client will see, 17 pages, for reading on a phone. It is printed from an `.html` file the build also writes, which git ignores. |
| `check_form_script.js` | A dry run of the script against a stand-in for Google Forms (see below). |

## Put the form in a Google account (about three minutes, at a computer)

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
- **Part 2, before the site goes live (16).** How the store works, offers and dated notices, Bell's name and logos, where messages go, privacy, photos.
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
| `unlocks`, `why` | For us only, left out of the script: tags such as `check:4` (item 4 of the README's "Before launch"), `phase1:business`, `confirm:languages`, and a note on why we ask. They drive the coverage tables in the research notes. |

`python3 ops/questionnaire/build_questionnaire.py check` validates the file (unique ids, real jump targets, no empty options, nothing too long for Forms). `all` rebuilds the banner, the script (and runs the dry run) and the preview.

### For another client

Copy the data file, change `client` and the questions, and run `build_questionnaire.py all --data your-file.json`. The banner uses the logo in `src/assets/img/`; point `LOGO` in the script at theirs. The script, the preview and the dry run don't depend on T Wireless.

## What the dry run checks, and what it doesn't

`check_form_script.js` runs the script against a stand-in for Google Forms that has only the methods Forms is supposed to have, so a typo fails here and not halfway through a real run. It then compares what was built with the data file, item by item: titles, help text, required flags, options, grids, "Other", and where each choice jumps. It currently builds 98 items (a banner, 23 pages, 74 questions) and 7 jumps.

It can't check how Google draws the form, whether Google accepts every call, or the colours. The script was written from Google's Apps Script reference for `FormApp` and has not yet been run on real Google Forms, so send yourself a test response first (step 6 above).

## Sources the questions were written from

The questions quote what Bell's store finder, Yellow Pages, MapQuest and the Google listing show for the store, and what the registry and DNS lookups show for the web addresses, all read on October 28, 2026. The research notes (kept out of this public repository) list each source and what couldn't be checked.
