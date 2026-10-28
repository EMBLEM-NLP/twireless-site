#!/usr/bin/env node
/**
 * Dry run of the generated Google Apps Script against a stand-in for Google Forms.
 *
 *   node check_form_script.js create_twireless_form.gs twireless.questionnaire.json
 *
 * The stand-in only has the Forms methods the script is meant to use, so a typo or a missing
 * method fails here instead of halfway through a real run. It then compares the form it built
 * with the data file, item by item: titles, help text, required flags, options, grids, jumps.
 * It can't check how Google draws the form, only that the script builds what the data says.
 */
'use strict';
const fs = require('fs');
const vm = require('vm');

const [, , scriptPath, dataPath] = process.argv;
if (!scriptPath || !dataPath) {
  console.error('usage: node check_form_script.js <script.gs> <data.json>');
  process.exit(2);
}
const spec = JSON.parse(fs.readFileSync(dataPath, 'utf8'));
const code = fs.readFileSync(scriptPath, 'utf8');

const PageNavigationType = { CONTINUE: 'CONTINUE', GO_TO_PAGE: 'GO_TO_PAGE', RESTART: 'RESTART', SUBMIT: 'SUBMIT' };
const Alignment = { LEFT: 'LEFT', CENTER: 'CENTER', RIGHT: 'RIGHT' };
const logs = [];

function methods(allowed, impl) {
  const out = {};
  for (const name of allowed) {
    if (!impl[name]) throw new Error('stand-in has no ' + name);
    out[name] = impl[name];
  }
  return out;
}

function makeItem(form, type) {
  const st = {
    type, title: '', help: '', required: null, choices: null, other: false,
    rows: null, cols: null, validation: null, alt: null, align: null, image: null,
  };
  const item = { _st: st };
  const impl = {
    setTitle(t) { if (typeof t !== 'string') throw new Error('title must be text'); st.title = t; return item; },
    setHelpText(h) { if (typeof h !== 'string') throw new Error('help must be text'); st.help = h; return item; },
    setRequired(r) { st.required = !!r; return item; },
    setValidation(v) { st.validation = v; return item; },
    setImage(blob) {
      if (!blob || !blob.bytes || blob.bytes[0] !== 0x89 || blob.bytes[1] !== 0x50) throw new Error('banner is not a PNG');
      st.image = blob; return item;
    },
    setAltText(a) { st.alt = a; return item; },
    setAlignment(a) { if (!Alignment[a]) throw new Error('bad alignment'); st.align = a; return item; },
    setWidth(w) { return item; },
    setGoToPage() { return item; },
    setChoiceValues(values) {
      if (!Array.isArray(values) || !values.length) throw new Error('no choices');
      if (new Set(values).size !== values.length) throw new Error('duplicate choice values');
      st.choices = values.map((v) => ({ value: v, nav: null, _item: item }));
      return item;
    },
    createChoice(value, nav) {
      if (nav !== undefined && !(nav && nav._st && nav._st.type === 'pagebreak') && !PageNavigationType[nav]) {
        throw new Error('bad navigation for choice "' + value + '"');
      }
      if (nav && nav._st && !form._items.includes(nav)) throw new Error('jump target is not in this form');
      return { value, nav: nav === undefined ? null : nav, _item: item };
    },
    setChoices(choices) {
      if (!Array.isArray(choices) || !choices.length) throw new Error('no choices');
      for (const c of choices) if (!c || c._item !== item) throw new Error('choice was not made by this question');
      const values = choices.map((c) => c.value);
      if (new Set(values).size !== values.length) throw new Error('duplicate choice values');
      if (st.other && choices.some((c) => c.nav)) throw new Error('Other can not be combined with jumps');
      st.choices = choices; return item;
    },
    showOtherOption(on) {
      if (on && st.choices && st.choices.some((c) => c.nav)) throw new Error('Other can not be combined with jumps');
      st.other = !!on; return item;
    },
    setRows(rows) { if (!rows.length || new Set(rows).size !== rows.length) throw new Error('bad rows'); st.rows = rows; return item; },
    setColumns(cols) { if (!cols.length || new Set(cols).size !== cols.length) throw new Error('bad columns'); st.cols = cols; return item; },
  };
  const allowed = {
    image: ['setImage', 'setAltText', 'setAlignment', 'setTitle', 'setHelpText', 'setWidth'],
    header: ['setTitle', 'setHelpText'],
    pagebreak: ['setTitle', 'setHelpText', 'setGoToPage'],
    text: ['setTitle', 'setHelpText', 'setRequired', 'setValidation'],
    paragraph: ['setTitle', 'setHelpText', 'setRequired', 'setValidation'],
    choice: ['setTitle', 'setHelpText', 'setRequired', 'setChoiceValues', 'setChoices', 'createChoice', 'showOtherOption'],
    checkbox: ['setTitle', 'setHelpText', 'setRequired', 'setChoiceValues', 'setChoices', 'createChoice', 'showOtherOption', 'setValidation'],
    grid: ['setTitle', 'setHelpText', 'setRequired', 'setRows', 'setColumns'],
  }[type];
  Object.assign(item, methods(allowed, impl));
  return item;
}

function makeForm(title) {
  const form = { _items: [], _st: { title, settings: {} } };
  const add = (type) => () => { const it = makeItem(form, type); form._items.push(it); return it; };
  const set = (k) => (v) => { form._st.settings[k] = v; return form; };
  Object.assign(form, {
    setDescription: (d) => { form._st.description = d; return form; },
    setConfirmationMessage: (m) => { form._st.confirmation = m; return form; },
    setCollectEmail: set('collectEmail'),
    setShuffleQuestions: set('shuffle'),
    setProgressBar: set('progress'),
    setAllowResponseEdits: set('edits'),
    setShowLinkToRespondAgain: set('again'),
    setRequireLogin: set('login'),
    setLimitOneResponsePerUser: set('limit'),
    addImageItem: add('image'),
    addSectionHeaderItem: add('header'),
    addPageBreakItem: add('pagebreak'),
    addTextItem: add('text'),
    addParagraphTextItem: add('paragraph'),
    addMultipleChoiceItem: add('choice'),
    addCheckboxItem: add('checkbox'),
    addGridItem: add('grid'),
    getEditUrl: () => 'https://docs.google.com/forms/d/FORM/edit',
    getPublishedUrl: () => 'https://docs.google.com/forms/d/e/FORM/viewform',
    getItems: () => form._items,
  });
  return form;
}

let built = null;
const sandbox = {
  Logger: { log: (m) => logs.push(String(m)) },
  Utilities: {
    base64Decode: (s) => { const b = Buffer.from(s, 'base64'); return { bytes: b }; },
    newBlob: (data, mime, name) => ({ bytes: data.bytes, mime, name }),
  },
  FormApp: {
    PageNavigationType,
    Alignment,
    create: (title) => { built = makeForm(title); return built; },
    createCheckboxValidation: () => {
      const v = {};
      const b = {
        requireSelectAtMost: (n) => { v.atMost = n; return b; },
        setHelpText: (t) => { v.help = t; return b; },
        build: () => v,
      };
      return b;
    },
  },
};
vm.createContext(sandbox);

const failures = [];
const fail = (m) => failures.push(m);

try {
  vm.runInContext(code, sandbox, { filename: scriptPath });
  const result = vm.runInContext('createQuestionnaireForm()', sandbox);
  if (!result || !result.edit || !result.share) fail('the script did not return the two links');
} catch (e) {
  fail('the script threw: ' + (e && e.stack ? e.stack.split('\n').slice(0, 3).join(' | ') : e));
}

if (built) {
  const items = built._items;
  const expected = [];
  if (!/BANNER_BASE64 = ''/.test(code)) expected.push({ kind: 'image' });
  spec.sections.forEach((s, i) => {
    expected.push({ kind: i === 0 ? 'header' : 'pagebreak', section: s });
    s.questions.forEach((q) => expected.push({ kind: q.type, q, section: s }));
  });
  if (items.length !== expected.length) fail('built ' + items.length + ' items, the data has ' + expected.length);
  const pageOf = {};
  spec.sections.forEach((s, i) => { if (i > 0) pageOf[s.id] = items.find((it) => it._st.type === 'pagebreak' && it._st.title === s.title); });

  expected.forEach((e, i) => {
    const it = items[i];
    if (!it) return;
    const st = it._st;
    const where = e.q ? e.q.id : (e.section ? e.section.id : e.kind);
    if (st.type !== e.kind) { fail(where + ': built a ' + st.type + ', the data says ' + e.kind); return; }
    if (e.kind === 'header' || e.kind === 'pagebreak') {
      if (st.title !== e.section.title) fail(where + ': page title differs');
      if ((st.help || '') !== (e.section.description || '')) fail(where + ': page description differs');
    } else if (e.kind !== 'image') {
      const q = e.q;
      if (st.title !== q.title) fail(where + ': title differs');
      if ((st.help || '') !== (q.help || '')) fail(where + ': help text differs');
      if (st.required !== !!q.required) fail(where + ': required differs');
      if (q.type === 'choice' || q.type === 'checkbox') {
        const got = (st.choices || []).map((c) => c.value);
        if (JSON.stringify(got) !== JSON.stringify(q.options)) fail(where + ': options differ');
        if (st.other !== !!q.other) fail(where + ': Other differs');
        (st.choices || []).forEach((c) => {
          const want = (q.goto || {})[c.value];
          if (!want) { if (c.nav && c.nav !== PageNavigationType.CONTINUE) fail(where + ': "' + c.value + '" jumps but should not'); return; }
          if (want === '@submit') { if (c.nav !== PageNavigationType.SUBMIT) fail(where + ': "' + c.value + '" should submit'); }
          else if (want === '@next') { if (c.nav !== PageNavigationType.CONTINUE) fail(where + ': "' + c.value + '" should continue'); }
          else if (c.nav !== pageOf[want]) fail(where + ': "' + c.value + '" jumps to the wrong page');
        });
        if (q.max_choices && !(st.validation && st.validation.atMost === q.max_choices)) fail(where + ': choose-up-to limit missing');
      }
      if (q.type === 'grid') {
        if (JSON.stringify(st.rows) !== JSON.stringify(q.rows)) fail(where + ': grid rows differ');
        if (JSON.stringify(st.cols) !== JSON.stringify(q.cols)) fail(where + ': grid columns differ');
      }
    }
  });
  if (items[0] && items[0]._st.type !== 'image' && !/BANNER_BASE64 = ''/.test(code)) fail('the banner is not the first item');
  const s = built._st.settings;
  if (s.collectEmail !== false) fail('should not collect email addresses');
  if (s.login !== false) fail('should not require sign-in');

  const by = {};
  items.forEach((it) => { by[it._st.type] = (by[it._st.type] || 0) + 1; });
  const jumps = items.reduce((n, it) => n + ((it._st.choices || []).filter((c) => c.nav && c.nav !== PageNavigationType.CONTINUE).length), 0);
  console.log('dry run built ' + items.length + ' items: ' + Object.entries(by).map(([k, v]) => v + ' ' + k).join(', ') + '; ' + jumps + ' jumps');
}

if (failures.length) {
  console.error('DRY RUN FAILED');
  failures.slice(0, 25).forEach((f) => console.error('  - ' + f));
  process.exit(3);
}
console.log('dry run ok: the script builds what the data file says');
