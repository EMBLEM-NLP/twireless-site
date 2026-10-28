/**
 * Receives the answers from the questionnaire web page and keeps them.
 *
 * When a person presses Send on the page, it posts their answers here. This script
 *   1. adds one row to a Google Sheet (it makes the Sheet the first time it is needed), and
 *   2. emails the answers, as readable text, to the account that owns this script.
 * It replies to the page with {"ok":true} or {"ok":false}, so the page can say whether it worked. Either the row or
 * the email is enough for "ok": if one fails, the other still keeps the answers.
 *
 * No email address is written in this file. The email goes to whoever owns the script; NOTIFY_EMAIL changes that.
 *
 * SET UP, once (about five minutes, best at a computer)
 *   1. Go to https://script.google.com signed in as the Google account that should receive the answers.
 *      Choose New project, delete the sample code, paste in this whole file and press Save.
 *   2. In the function menu choose "setup" and press Run. Google asks for permission. It warns that the app isn't
 *      verified, because it is your own new script: choose Advanced, then Go to the project, then Allow.
 *      "setup" makes the Sheet and sends you a test email, so you know both work. Delete the TEST row afterwards.
 *   3. Choose Deploy, then New deployment. Next to "Select type" press the gear and choose Web app.
 *      Set Execute as to Me and Who has access to Anyone ("Anyone" is the one that lets a visitor who is not signed
 *      in to Google send their answers). Press Deploy.
 *   4. Copy the Web app URL. It ends in /exec. That is the address the page sends answers to.
 *   5. Open that URL in a browser. It should show {"ok":true,"ready":true}.
 *
 * TO CHANGE THIS SCRIPT LATER: Deploy, Manage deployments, the pencil, Version: New version, Deploy. The URL stays
 * the same. Saving the code alone does not change what the live URL runs.
 *
 * WHAT IT DOES AND DOESN'T DO
 *   - The address is public, because the page has to know it. Anyone who has it can post to it. This script ignores
 *     anything that is not a set of answers from this questionnaire, keeps only plain text (a stranger can't plant a
 *     formula in the Sheet), cuts anything very long, and sends at most MAX_EMAILS_PER_DAY emails a day. The Sheet
 *     still gets a row for every valid message.
 *   - It sees only what the page sends: the answers and the time. Google doesn't pass this script a sender's address
 *     or device, and the script doesn't ask for one.
 *   - It makes no requests to any other service.
 */

var FORM = 'twireless';       // the page puts this in every message (client.slug in the data file); others are ignored
var NAME = 'T Wireless';      // the client's name, for the Sheet's title and the email's subject
var NOTIFY_EMAIL = '';        // empty: email the account that owns this script. To use another address, put it here.

var MAX_BODY = 200000;        // characters in one message. A full set of answers is about 20,000.
var MAX_CELL = 45000;         // a Sheets cell holds 50,000 characters
var MAX_EMAILS_PER_DAY = 40;  // a free Google account may send 100 a day; junk must not use them all
var LOCK_WAIT_MS = 15000;

var HEADER = ['Received', 'Sent (from the page)', 'All parts finished', 'Questions answered', 'Answers', 'Answers as data'];


/** Opening the address in a browser: says the receiver is there, and nothing else. */
function doGet() {
  return reply_({ ok: true, ready: true });
}

/** The page's Send button. */
function doPost(e) {
  var lock = LockService.getScriptLock();
  var held = false;
  try {
    held = lock.tryLock(LOCK_WAIT_MS);
    if (!held) return reply_({ ok: false, error: 'busy' });
    var message = read_(e);
    if (!message) return reply_({ ok: false, error: 'not an answer' });
    return reply_({ ok: keep_(message, false) });
  } catch (err) {
    console.error('doPost: ' + err);
    return reply_({ ok: false, error: 'failed' });
  } finally {
    if (held) lock.releaseLock();
  }
}

/** Run this once from the editor (see SET UP). It makes the Sheet and sends a test email. */
function setup() {
  var book = book_();
  var test = {
    form: FORM,
    sent_at: new Date().toISOString(),
    complete: false,
    answers: {},
    text: 'TEST. There are no answers here. This row and this email only check that the Sheet and the email work. ' +
      'You can delete the row.'
  };
  var ok = keep_(test, true);
  console.log('The Sheet: ' + book.getUrl());
  console.log('Emails go to: ' + recipient_());
  if (!ok) throw new Error('Neither the Sheet nor the email worked. Read the lines above for why.');
}


function reply_(body) {
  return ContentService.createTextOutput(JSON.stringify(body)).setMimeType(ContentService.MimeType.JSON);
}

/** The message the page sent, or null if it is not one. */
function read_(e) {
  var raw = e && e.postData && e.postData.contents;
  if (typeof raw !== 'string' || raw.length === 0 || raw.length > MAX_BODY) return null;
  var m;
  try { m = JSON.parse(raw); } catch (err) { return null; }
  if (!m || typeof m !== 'object' || m.form !== FORM) return null;
  if (typeof m.text !== 'string' || m.text.replace(/\s/g, '') === '') return null;
  if (!m.answers || typeof m.answers !== 'object' || Array.isArray(m.answers)) return null;
  return m;
}

/** Writes the row and sends the email. True if either one worked. */
function keep_(message, isTest) {
  var count = Object.keys(message.answers).length;
  var finished = message.complete === true;
  var sent = typeof message.sent_at === 'string' ? message.sent_at.slice(0, 40) : '';
  var text = clip_(message.text);
  var data = clip_(JSON.stringify(message.answers));
  var book = null;
  var saved = false;
  var emailed = false;
  try {
    book = book_();
    var sheet = book.getSheetByName('Answers') || book.getSheets()[0];
    var row = [stamp_(), sent, finished ? 'yes' : 'no', String(count), text, data].map(plain_);
    var range = sheet.getRange(sheet.getLastRow() + 1, 1, 1, row.length);
    range.setNumberFormat('@'); // plain text, so nothing in an answer is read as a formula
    range.setValues([row]);
    saved = true;
  } catch (err) {
    console.error('could not add the row: ' + err);
  }
  try {
    emailed = email_(text, count, finished, sent, book, isTest);
  } catch (err) {
    console.error('could not send the email: ' + err);
  }
  return saved || emailed;
}

function recipient_() {
  return NOTIFY_EMAIL || Session.getEffectiveUser().getEmail();
}

function email_(text, count, finished, sent, book, isTest) {
  var to = recipient_();
  if (!to || !takeEmailSlot_()) return false;
  var subject = (isTest ? 'TEST: ' : '') + NAME + ' questionnaire: ' + count + (count === 1 ? ' answer' : ' answers') +
    (finished ? ', all parts finished' : ', not all parts finished');
  var body = text + '\n\n' +
    (sent ? 'Sent from the page at ' + sent + '.\n' : '') +
    (book ? 'Every answer so far is in this Sheet: ' + book.getUrl() + '\n' : '');
  MailApp.sendEmail({ to: to, subject: subject, body: body, name: NAME + ' questionnaire' });
  return true;
}

/** Counts today's emails, so a flood of junk can't use up the day's allowance. */
function takeEmailSlot_() {
  var props = PropertiesService.getScriptProperties();
  var today = Utilities.formatDate(new Date(), 'UTC', 'yyyy-MM-dd');
  var seen;
  try { seen = JSON.parse(props.getProperty('EMAILS') || '{}'); } catch (err) { seen = {}; }
  if (!seen || seen.day !== today) seen = { day: today, n: 0 };
  if (seen.n >= MAX_EMAILS_PER_DAY) return false;
  seen.n += 1;
  props.setProperty('EMAILS', JSON.stringify(seen));
  return true;
}

/** The Sheet the rows go in. It is made once and remembered. */
function book_() {
  var props = PropertiesService.getScriptProperties();
  var id = props.getProperty('SHEET_ID');
  if (id) {
    try { return SpreadsheetApp.openById(id); } catch (err) { console.error('the Sheet is gone, making a new one: ' + err); }
  }
  var book = SpreadsheetApp.create(NAME + ': questionnaire answers');
  props.setProperty('SHEET_ID', book.getId());
  try {
    var sheet = book.getSheets()[0];
    sheet.setName('Answers');
    sheet.getRange(1, 1, 1, HEADER.length).setValues([HEADER]).setFontWeight('bold');
    sheet.setFrozenRows(1);
    sheet.setColumnWidth(5, 600);
  } catch (err) {
    console.error('could not set up the Sheet\'s first row: ' + err);
  }
  return book;
}

function stamp_() {
  return Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd HH:mm:ss z');
}

function clip_(s) {
  s = String(s);
  return s.length > MAX_CELL ? s.slice(0, MAX_CELL - 30) + '\n[cut: too long to keep]' : s;
}

/** Text that starts like a formula gets a space in front, in case the Sheet is later exported to a file. */
function plain_(v) {
  v = String(v);
  return /^[=+\-@\t\r]/.test(v) ? ' ' + v : v;
}
