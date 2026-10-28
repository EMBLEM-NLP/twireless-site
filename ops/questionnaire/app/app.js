/* The questionnaire app. One file, no libraries, nothing loaded from outside the page.
   It is written in plain ES2015 (no ?. or ??) so it runs on phones a few years old.

   The questions arrive as JSON in the page (#spec), made by build_questionnaire.py from the data file:
   SPEC.screens is the order of the screens, SPEC.pages holds the questions, SPEC.parts the parts.

   How it behaves, in short:
   - One section per screen. The address bar hash (#/details) says which, so the phone's Back gesture works.
   - Answers are saved on the device as you go (localStorage) and nothing leaves the device until a send button is pressed.
   - A "gate" question (Repairs: No) hides the questions after it; a "stop" screen ends a part.
   - The questionnaire is a first approach to a business that never asked for it, so almost nothing is required: the
     bottom button says Skip until something on the screen is answered, and only the choice at a stop must be made.
   - The progress bar has one segment per section, grouped by part and sized by how long each takes. */
(function () {
  'use strict';

  var SPEC = JSON.parse(document.getElementById('spec').textContent);
  var OTHER = '__other__';
  var STORE_KEY = 'questionnaire:' + SPEC.client.slug + ':v' + SPEC.version;
  var CAN_SHARE = typeof navigator.share === 'function';
  var NO_MOTION = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);

  var el = {
    top: document.getElementById('top'),
    main: document.getElementById('main'),
    foot: document.getElementById('foot'),
    menu: document.getElementById('menu'),
    live: document.getElementById('live')
  };

  /* ================================================================ small helpers */

  function h(tag, attrs) {
    var node = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        var v = attrs[k];
        if (v === null || v === undefined || v === false) return;
        if (k === 'class') node.className = v;
        else if (k === 'text') node.textContent = v;
        else if (k.slice(0, 2) === 'on') node.addEventListener(k.slice(2), v);
        else node.setAttribute(k, v === true ? '' : v);
      });
    }
    for (var i = 2; i < arguments.length; i++) append(node, arguments[i]);
    return node;
  }

  function append(node, kid) {
    if (kid === null || kid === undefined || kid === false) return;
    if (Array.isArray(kid)) { kid.forEach(function (k) { append(node, k); }); return; }
    node.appendChild(typeof kid === 'object' ? kid : document.createTextNode(String(kid)));
  }

  function trimmed(s) { return typeof s === 'string' ? s.replace(/^\s+|\s+$/g, '') : ''; }
  function each(list, fn) { Array.prototype.forEach.call(list, fn); }
  function plural(n, one, many) { return n + ' ' + (n === 1 ? one : many); }

  /* Paragraphs, bullet lists ("• ") and line breaks from the plain text in the data file. */
  function rich(text, cls) {
    var box = h('div', { class: cls || 'rich' });
    String(text).split(/\n{2,}/).forEach(function (block) {
      var list = null;
      var para = null;
      block.split('\n').forEach(function (line) {
        if (/^•\s/.test(line)) {
          para = null;
          if (!list) { list = h('ul'); box.appendChild(list); }
          list.appendChild(h('li', { text: line.replace(/^•\s+/, '') }));
        } else {
          list = null;
          if (!para) { para = h('p'); box.appendChild(para); } else { para.appendChild(document.createElement('br')); }
          para.appendChild(document.createTextNode(line));
        }
      });
    });
    return box;
  }

  var ICONS = {
    list: '<path d="M4 7h16M4 12h16M4 17h10" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/>',
    check: '<path d="M8 17l6 6 11-13" fill="none" stroke="#fff" stroke-width="3.6" stroke-linecap="round" stroke-linejoin="round"/>',
    alert: '<circle cx="12" cy="12" r="10" fill="#b3182b"/><path d="M12 7v6.2" stroke="#fff" stroke-width="2.4" stroke-linecap="round"/><circle cx="12" cy="16.9" r="1.4" fill="#fff"/>',
    share: '<path d="M12 15V3.5M7.6 7.6L12 3.2l4.4 4.4M5 11.5v7.2c0 1 .8 1.8 1.8 1.8h10.4c1 0 1.8-.8 1.8-1.8v-7.2" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>',
    copy: '<rect x="8.5" y="8.5" width="11" height="12" rx="2.2" fill="none" stroke="currentColor" stroke-width="2.1"/><path d="M15.5 5.2V5a1.8 1.8 0 00-1.8-1.8H6.3A1.8 1.8 0 004.5 5v9.4a1.8 1.8 0 001.8 1.8h.4" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round"/>',
    save: '<path d="M12 3.5V15M7.6 11.4L12 15.8l4.4-4.4M5 19.5h14" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>',
    out: '<path d="M14 4h6v6M20 4l-9 9M18 14v4.5a1.5 1.5 0 01-1.5 1.5h-11A1.5 1.5 0 014 18.5v-11A1.5 1.5 0 015.5 6H10" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>'
  };
  function icon(name) {
    var box = document.createElement('span');
    box.innerHTML = '<svg viewBox="' + (name === 'check' ? '0 0 32 32' : '0 0 24 24') + '" aria-hidden="true" focusable="false">' + ICONS[name] + '</svg>';
    return box.firstChild;
  }

  function announce(text) {
    el.live.textContent = '';
    window.setTimeout(function () { el.live.textContent = text; }, 60);
  }

  /* ================================================================ the questions */

  /* These maps are looked up with text from the address bar (#/constructor), so they have no prototype to answer with. */
  var PAGES = Object.create(null);
  var Q = Object.create(null);
  SPEC.pages.forEach(function (p) {
    PAGES[p.id] = p;
    p.questions.forEach(function (q) { Q[q.id] = q; });
  });
  var SCREENS = SPEC.screens;
  var BYID = Object.create(null);
  SCREENS.forEach(function (s, i) { s.index = i; BYID[s.id] = s; });
  var PARTS = SPEC.parts;
  var PART = Object.create(null);
  PARTS.forEach(function (p) { PART[p.id] = p; });

  /* How long a question takes, roughly. Only the ratios matter: each part is scaled to the minutes the data file gives it. */
  function weight(q) {
    switch (q.type) {
      case 'text': return 0.4;
      case 'paragraph': return 0.9;
      case 'choice': return 0.35;
      case 'checkbox': return 0.6;
      default: return 0.2 + 0.25 * q.rows.length;
    }
  }

  function screenQuestions(s) {
    var out = [];
    s.pages.forEach(function (pid) { PAGES[pid].questions.forEach(function (q) { out.push(q); }); });
    return out;
  }

  PARTS.forEach(function (part) {
    part.screens = SCREENS.filter(function (s) { return s.kind === 'section' && s.part === part.id; });
    var total = 0;
    part.screens.forEach(function (s) {
      s.weight = screenQuestions(s).reduce(function (n, q) { return n + weight(q); }, 0);
      total += s.weight;
    });
    part.screens.forEach(function (s, i) {
      s.no = i + 1;
      s.of = part.screens.length;
      s.mins = total ? (s.weight / total) * part.mins : 0;
    });
  });

  function lastSectionIndex() {
    for (var i = SCREENS.length - 1; i >= 0; i--) if (SCREENS[i].kind === 'section') return i;
    return -1;
  }

  /* ================================================================ saved state */

  var storageOk = true;

  function blank() {
    return { answers: {}, others: {}, furthest: -1, ended: false, shared: null, sent: null };
  }

  function clean(raw) {
    var s = blank();
    if (!raw || typeof raw !== 'object') return s;
    var answers = raw.answers || {};
    var others = raw.others || {};
    Object.keys(Q).forEach(function (id) {
      var q = Q[id];
      var a = answers[id];
      if (a === undefined || a === null) return;
      if (typeof others[id] === 'string') s.others[id] = others[id].slice(0, 2000);
      if (q.type === 'text' || q.type === 'paragraph') {
        if (typeof a === 'string') s.answers[id] = a.slice(0, 5000);
      } else if (q.type === 'choice') {
        if (typeof a === 'string' && (q.options.indexOf(a) >= 0 || (a === OTHER && q.other))) s.answers[id] = a;
      } else if (q.type === 'checkbox') {
        if (Array.isArray(a)) {
          var keep = [];
          a.forEach(function (x) {
            if ((q.options.indexOf(x) >= 0 || (x === OTHER && q.other)) && keep.indexOf(x) < 0) keep.push(x);
          });
          /* The screen never lets these happen, so saved answers shouldn't hold them either: an option that excludes
             the rest never sits beside another choice, and "choose up to N" holds. */
          var exclusive = q.exclusive || [];
          var plain = keep.filter(function (x) { return exclusive.indexOf(x) < 0; });
          if (plain.length && plain.length < keep.length) keep = plain;
          else if (!plain.length && keep.length > 1) keep = [keep[0]];
          if (q.max_choices && keep.length > q.max_choices) keep = keep.slice(0, q.max_choices);
          if (keep.length) s.answers[id] = keep;
        }
      } else if (q.type === 'grid') {
        if (typeof a === 'object') {
          var map = {};
          q.rows.forEach(function (r) { if (q.cols.indexOf(a[r]) >= 0) map[r] = a[r]; });
          s.answers[id] = map;
        }
      }
    });
    var f = parseInt(raw.furthest, 10);
    s.furthest = isNaN(f) ? -1 : Math.max(-1, Math.min(SCREENS.length, f));
    s.ended = raw.ended === true;
    s.shared = typeof raw.shared === 'number' ? raw.shared : null;
    s.sent = typeof raw.sent === 'number' ? raw.sent : null;
    return s;
  }

  function restore() {
    var raw = null;
    try {
      raw = window.localStorage.getItem(STORE_KEY);
      storageOk = true;
    } catch (e) {
      storageOk = false;
      return blank();
    }
    /* What was saved may not be readable (another version, a damaged value). That is not a reason to say the browser can't save. */
    var data = null;
    try { data = raw ? JSON.parse(raw) : null; } catch (e2) { data = null; }
    return clean(data);
  }

  var state = restore();

  function save() {
    try {
      window.localStorage.setItem(STORE_KEY, JSON.stringify(state));
      storageOk = true;
    } catch (e) {
      storageOk = false;
    }
  }

  function started() { return state.furthest >= 0; }
  function hasAnswers() { return Object.keys(state.answers).length > 0; }
  function isComplete() { return state.furthest >= SCREENS.length; }
  function sendAllowed() { return started() && (state.ended || isComplete()); }

  /* Questions that still need an answer on the sections the person has been through. Only Next checks as you go, so
     an edit that opens new questions, followed by a jump through the Sections menu, can leave some behind. The review,
     the header and the text we send must not say "done" while any are. */
  function openProblems() {
    var out = [];
    reachedSections().forEach(function (s) {
      visibleQuestions(s).forEach(function (q) { if (problem(q)) out.push({ s: s, q: q }); });
    });
    return out;
  }
  function allDone() { return isComplete() && !openProblems().length; }

  /* ================================================================ answers */

  function otherText(q) { return trimmed(state.others[q.id]); }

  /* How much of a question is answered: 0 to 1. A choice with "Other" needs the typed text to count. */
  function fraction(q) {
    var a = state.answers[q.id];
    var n;
    switch (q.type) {
      case 'text':
      case 'paragraph':
        return trimmed(a) ? 1 : 0;
      case 'choice':
        if (!a) return 0;
        return a === OTHER && !otherText(q) ? 0 : 1;
      case 'checkbox':
        if (!a || !a.length) return 0;
        if (a.length === 1 && a[0] === OTHER && !otherText(q)) return 0;
        return 1;
      default:
        n = 0;
        q.rows.forEach(function (r) { if (a && a[r]) n++; });
        return n / q.rows.length;
    }
  }
  function isAnswered(q) { return fraction(q) === 1; }

  /* What the person gave, in a shape both the review list and the text we send can use. */
  function answerOf(q) {
    var a = state.answers[q.id];
    var items;
    var rows;
    switch (q.type) {
      case 'text':
      case 'paragraph':
        return trimmed(a) ? { text: trimmed(a) } : null;
      case 'choice':
        if (!a) return null;
        if (a === OTHER) return otherText(q) ? { text: 'Other: ' + otherText(q) } : null;
        return { text: a };
      case 'checkbox':
        items = [];
        (a || []).forEach(function (x) {
          if (x !== OTHER) items.push(x);
          else if (otherText(q)) items.push('Other: ' + otherText(q));
        });
        return items.length ? { items: items } : null;
      default:
        rows = [];
        q.rows.forEach(function (r) { if (a && a[r]) rows.push([r, a[r]]); });
        return rows.length ? { rows: rows, all: rows.length === q.rows.length } : null;
    }
  }

  /* Which pages of a screen show. The first always does. A page that follows a gate question stays out until that
     question is answered, and goes for good if the answer jumps past it (Repairs: No skips "What you repair"). */
  function pageStates(s) {
    var out = [];
    var mode = 'visible';
    s.pages.forEach(function (pid) {
      var page = PAGES[pid];
      out.push({ page: page, state: mode });
      if (mode !== 'visible') return;
      page.questions.forEach(function (q) {
        if (!q.goto) return;
        var a = state.answers[q.id];
        if (!a) mode = 'pending';
        else if (q.goto[a] && q.goto[a] !== '@next') mode = 'skipped';
      });
    });
    return out;
  }

  function visibleQuestions(s) {
    var out = [];
    pageStates(s).forEach(function (ps) {
      if (ps.state === 'visible') ps.page.questions.forEach(function (q) { out.push(q); });
    });
    return out;
  }

  function problem(q) {
    var a = state.answers[q.id];
    var hint = q.options && q.options.indexOf('Not sure') >= 0 ? ' If you’re not sure, choose “Not sure”.' : '';
    var missing;
    if (q.type === 'grid') {
      missing = 0;
      q.rows.forEach(function (r) { if (!(a && a[r])) missing++; });
      if (q.required && missing) {
        return missing === q.rows.length ? 'Please answer every row.' : plural(missing, 'row still needs', 'rows still need') + ' an answer.';
      }
      return '';
    }
    var usesOther = q.type === 'choice' ? a === OTHER : (q.type === 'checkbox' && a && a.indexOf(OTHER) >= 0);
    if (usesOther && !otherText(q)) {
      // an optional question can always be left unanswered, so say how
      return 'Please type your answer in the Other box' + (q.required ? '.' : (q.type === 'choice' ? ', or clear your choice.' : ', or untick Other.'));
    }
    if (!q.required) return '';
    if (isAnswered(q)) return '';
    if (q.type === 'text' || q.type === 'paragraph') return 'Please type your answer.';
    if (q.type === 'checkbox') return 'Please choose at least one.' + hint;
    return 'Please choose an answer.' + hint;
  }

  /* ================================================================ progress */

  /* 0 to 1. A section the person has passed counts as full unless a question in it still needs an answer. */
  function sectionFill(s) {
    var passed = isComplete() || state.furthest > s.index;
    if (!passed && state.furthest < s.index) return 0;
    var total = 0;
    var done = 0;
    var gaps = 0;
    pageStates(s).forEach(function (ps) {
      ps.page.questions.forEach(function (q) {
        var w = weight(q);
        total += w;
        if (ps.state === 'skipped') {
          done += w;
        } else if (ps.state === 'visible') {
          done += w * fraction(q);
          if (passed && problem(q)) gaps++;
        }
      });
    });
    if (passed && !gaps) return 1;
    return total ? done / total : 0;
  }

  function partPassed(part) {
    var last = part.screens[part.screens.length - 1];
    return !!last && (isComplete() || last.index < state.furthest);
  }

  function minutesLeft(part) {
    var left = 0;
    part.screens.forEach(function (s) { left += s.mins * (1 - sectionFill(s)); });
    return left;
  }

  function overall() {
    var done = 0;
    var total = 0;
    PARTS.forEach(function (part) {
      part.screens.forEach(function (s) { total += s.mins; done += s.mins * sectionFill(s); });
    });
    return total ? done / total : 0;
  }

  function minutesText(part) {
    var m = minutesLeft(part);
    if (m <= 0.05) return partPassed(part) ? 'this part is done' : 'nearly done';
    if (m < 1) return 'under a minute left in this part';
    return 'about ' + Math.ceil(m - 0.05) + ' min left in this part';
  }

  /* ================================================================ routing */

  var current = null;
  var firstRender = true;
  var editing = false; // true after Edit on the review list: the bottom button then goes back to the review

  function routeFromHash() {
    var m = /^#\/([\w-]+)$/.exec(window.location.hash);
    return m ? m[1] : 'welcome';
  }

  /* Setting the hash to what it already is fires no event, so in that case draw the screen again ourselves. */
  function go(id) {
    if (routeFromHash() === id) { render(); return; }
    window.location.hash = '#/' + id;
  }

  function furthestId() {
    if (isComplete()) return 'send';
    return SCREENS[Math.max(0, state.furthest)].id;
  }

  function resolve(id) {
    if (id === 'welcome') return 'welcome';
    if (!started()) return 'welcome';
    if (id === 'send') return sendAllowed() ? 'send' : furthestId();
    var s = BYID[id];
    if (!s) return 'welcome';
    return s.index > state.furthest ? furthestId() : id;
  }

  function order(id) {
    if (id === 'welcome' || id === null) return -1;
    if (id === 'send') return SCREENS.length;
    return BYID[id].index;
  }

  function previousOf(id) {
    if (id === 'send') return state.ended ? SCREENS[Math.min(state.furthest, SCREENS.length - 1)].id : SCREENS[SCREENS.length - 1].id;
    var i = BYID[id].index;
    return i === 0 ? 'welcome' : SCREENS[i - 1].id;
  }

  function advanceFrom(s) {
    var next = s.index + 1;
    if (next >= SCREENS.length) {
      state.furthest = Math.max(state.furthest, SCREENS.length);
      state.ended = false;
      save();
      go('send');
      return;
    }
    state.furthest = Math.max(state.furthest, next);
    save();
    go(SCREENS[next].id);
  }

  /* ================================================================ the progress header */

  var hdr = null;

  function buildTop() {
    var meter = h('div', {
      class: 'meter', role: 'progressbar', 'aria-label': 'Progress through the questions',
      'aria-valuemin': '0', 'aria-valuemax': '100', 'aria-valuenow': '0'
    });
    var segs = {};
    PARTS.forEach(function (part) {
      var box = h('div', { class: 'meter__part' });
      var share = 0;
      part.screens.forEach(function (s) {
        var fill = h('i', { class: 'seg__fill' });
        var seg = h('span', { class: 'seg' }, fill);
        var grow = 0.7 + s.mins; // longer sections get a longer segment, but not by much
        seg.style.flexGrow = String(grow);
        share += grow;
        segs[s.id] = { seg: seg, fill: fill };
        box.appendChild(seg);
      });
      box.style.flexGrow = String(share);
      meter.appendChild(box);
    });
    var where = h('p', { class: 'top__where' });
    var line = h('b');
    var left = h('span', { class: 'top__left' });
    where.appendChild(line);
    where.appendChild(left);
    var menuBtn = h('button', { class: 'top__menu', type: 'button', 'aria-haspopup': 'dialog', onclick: openMenu }, icon('list'), 'Sections');
    var row = h('div', { class: 'top__row' }, menuBtn, where);
    var inner = h('div', { class: 'top__in' }, row, meter);
    el.top.textContent = '';
    el.top.appendChild(inner);
    hdr = { meter: meter, segs: segs, line: line, left: left, menuBtn: menuBtn };
  }

  function updateTop() {
    if (!hdr) buildTop();
    var s = BYID[current];
    var part = s ? PART[s.part] : null;
    PARTS.forEach(function (p) {
      p.screens.forEach(function (sc) {
        var t = hdr.segs[sc.id];
        t.fill.style.transform = 'scaleX(' + sectionFill(sc).toFixed(3) + ')';
        t.seg.className = 'seg' + (current === sc.id ? ' is-here' : '');
      });
    });
    var pct = Math.round(overall() * 100);
    var line = '';
    var left = '';
    if (current === 'send') {
      line = !countAnswers().answered ? 'Nothing answered yet' : (allDone() ? 'All done' : 'Check and send');
    } else if (s && s.kind === 'section') {
      line = 'Part ' + part.n + ' of ' + part.of + ' · Section ' + s.no + ' of ' + s.of;
      left = (part.optional ? 'Optional · ' : '') + minutesText(part);
    } else if (s) {
      line = 'Part ' + part.n + ' of ' + part.of + ' · done';
    }
    hdr.line.textContent = line;
    hdr.left.textContent = left;
    hdr.left.hidden = !left;
    hdr.meter.setAttribute('aria-valuenow', String(pct));
    hdr.meter.setAttribute('aria-valuetext', pct + ' percent done. ' + line + (left ? '. ' + left : ''));
  }

  /* ================================================================ the sections menu */

  var menuReturn = null;

  function openMenu() {
    menuReturn = document.activeElement;
    el.menu.textContent = '';
    var list = h('ol', { class: 'toc' });
    var needs = Object.create(null); // only for sections the person has passed: the one they are working on isn't "missing" anything yet
    openProblems().forEach(function (o) { if (isComplete() || o.s.index < state.furthest) needs[o.s.id] = true; });
    PARTS.forEach(function (part) {
      var items = h('ol');
      part.screens.forEach(function (s) {
        var reached = started() && s.index <= state.furthest;
        var done = started() && (isComplete() || s.index < state.furthest) && !needs[s.id];
        var btn = h('button', {
          type: 'button', class: 'toc__item' + (done ? ' is-done' : ''), 'data-go': s.id,
          'aria-current': current === s.id ? 'step' : null, disabled: !reached,
          onclick: function () { closeMenu(true); go(s.id); }
        }, h('span', { class: 'toc__mark', 'aria-hidden': 'true' }), h('span', { class: 'toc__name', text: s.title }),
        needs[s.id] ? h('span', { class: 'toc__need', text: 'Needs an answer' }) : null,
        done ? h('span', { class: 'sr-only', text: ' (done)' }) : null,
        !reached ? h('span', { class: 'sr-only', text: ' (not reached yet)' }) : null);
        items.appendChild(h('li', null, btn));
      });
      list.appendChild(h('li', { class: 'toc__part' },
        h('h3', { text: 'Part ' + part.n + ' of ' + part.of + ': ' + part.title }),
        h('p', { text: part.minutes + (part.optional ? ' · optional' : '') }), items));
    });
    var sendBtn = h('button', {
      type: 'button', class: 'toc__item', 'data-go': 'send', disabled: !sendAllowed(),
      'aria-current': current === 'send' ? 'step' : null,
      onclick: function () { closeMenu(true); go('send'); }
    }, h('span', { class: 'toc__mark', 'aria-hidden': 'true' }), h('span', { text: 'Check and send' }));
    list.appendChild(h('li', { class: 'toc__send' }, sendBtn));
    var closeBtn = h('button', { type: 'button', class: 'menu__close', onclick: function () { closeMenu(); } }, 'Close');
    var panel = h('div', { class: 'menu__panel', role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': 'menu-title' },
      h('div', { class: 'menu__head' }, h('h2', { id: 'menu-title', text: 'Sections' }), closeBtn), list);
    el.menu.appendChild(panel);
    el.menu.hidden = false;
    document.body.classList.add('is-locked');
    var here = panel.querySelector('[aria-current="step"]');
    (here || closeBtn).focus();
    if (here && here.scrollIntoView) here.scrollIntoView({ block: 'center' });
  }

  function closeMenu(skipFocus) {
    if (el.menu.hidden) return;
    el.menu.hidden = true;
    el.menu.textContent = '';
    document.body.classList.remove('is-locked');
    if (!skipFocus && menuReturn && menuReturn.focus) menuReturn.focus();
  }

  el.menu.addEventListener('click', function (e) { if (e.target === el.menu) closeMenu(); });
  el.menu.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' || e.key === 'Esc') { e.preventDefault(); closeMenu(); return; }
    if (e.key !== 'Tab') return;
    var items = el.menu.querySelectorAll('button:not([disabled])');
    if (!items.length) return;
    var first = items[0];
    var last = items[items.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  });

  /* ================================================================ questions on screen */

  function reqMark(q) {
    return q.required ? [' ', h('span', { class: 'req', 'aria-hidden': 'true', text: '*' }), h('span', { class: 'sr-only', text: ' (required)' })] : null;
  }

  function helpBlock(q) {
    return q.help ? h('div', { class: 'q__help', id: 'h-' + q.id }, rich(q.help, 'rich')) : null;
  }

  function optionRow(kind, name, value, label, checked) {
    var input = h('input', { type: kind, name: name, value: value, class: 'opt__input' });
    if (checked) input.checked = true;
    return h('label', { class: 'opt opt--' + (kind === 'radio' ? 'radio' : 'check') }, input,
      h('span', { class: 'opt__box' }, h('span', { class: 'opt__mark', 'aria-hidden': 'true' }), h('span', { class: 'opt__text', text: label })));
  }

  function otherField(q) {
    var input = h('input', {
      type: 'text', class: 'input', 'aria-label': 'Other: type your answer', placeholder: 'Type your answer', enterkeyhint: 'done'
    });
    input.value = state.others[q.id] || '';
    input.addEventListener('input', function () { state.others[q.id] = input.value; changed(q); });
    input.addEventListener('keydown', blurOnEnter);
    return input;
  }

  function blurOnEnter(e) {
    if (e.key === 'Enter') { e.preventDefault(); e.target.blur(); }
  }

  /* Tapping "Other" takes you to its box, which saves a tap. Choosing it with the arrow keys or the space bar must not:
     a person on a keyboard would be pulled out of the list and could not arrow back. The function this returns says
     whether the change that is being handled came from the keyboard. */
  function watchKeys(list) {
    var keyed = false;
    list.addEventListener('keydown', function (e) { if (e.key !== 'Tab') keyed = true; }, true);
    list.addEventListener('pointerdown', function () { keyed = false; }, true);
    return function () { var was = keyed; keyed = false; return was; };
  }

  function groupWrap(q, kind, body) {
    var wrap = h('div', { class: 'q q--' + q.type, 'data-q': q.id });
    wrap.appendChild(h('div', { class: 'q__title', id: 't-' + q.id }, q.title, reqMark(q)));
    append(wrap, helpBlock(q));
    body.setAttribute('role', kind);
    body.setAttribute('aria-labelledby', 't-' + q.id);
    if (q.help) body.setAttribute('aria-describedby', 'h-' + q.id);
    wrap.appendChild(body);
    return wrap;
  }

  function renderText(q) {
    var wrap = h('div', { class: 'q q--' + q.type, 'data-q': q.id });
    wrap.appendChild(h('label', { class: 'q__title', id: 't-' + q.id, for: 'f-' + q.id }, q.title, reqMark(q)));
    append(wrap, helpBlock(q));
    var field = q.type === 'text'
      ? h('input', { type: 'text', id: 'f-' + q.id, class: 'input', autocomplete: q.autocomplete || 'off', inputmode: q.inputmode || null, enterkeyhint: 'done' })
      : h('textarea', { id: 'f-' + q.id, class: 'input', rows: '4' });
    if (q.help) field.setAttribute('aria-describedby', 'h-' + q.id);
    field.value = state.answers[q.id] || '';
    field.addEventListener('input', function () { state.answers[q.id] = field.value; changed(q); });
    if (q.type === 'text') field.addEventListener('keydown', blurOnEnter);
    wrap.appendChild(field);
    return wrap;
  }

  function renderChoice(q) {
    var name = 'c-' + q.id;
    var cur = state.answers[q.id];
    var list = h('div', { class: 'opts' });
    q.options.forEach(function (o) { list.appendChild(optionRow('radio', name, o, o, cur === o)); });
    var field = null;
    if (q.other) {
      field = otherField(q);
      field.hidden = cur !== OTHER;
      list.appendChild(h('div', { class: 'opt-other' }, optionRow('radio', name, OTHER, 'Other', cur === OTHER), field));
    }
    var wrap = groupWrap(q, 'radiogroup', list);
    var clear = null;
    var viaKeyboard = watchKeys(list);
    if (!q.required) {
      clear = h('button', { type: 'button', class: 'q__clear', text: 'Clear my choice', onclick: function () {
        delete state.answers[q.id];
        var radios = list.querySelectorAll('input[type=radio]');
        each(radios, function (i) { i.checked = false; });
        if (field) field.hidden = true;
        clear.hidden = true; // the button the person pressed is going away, so put focus on the choices instead of losing it
        if (radios.length) radios[0].focus();
        changed(q);
      } });
      clear.hidden = !cur;
      wrap.appendChild(clear);
    }
    list.addEventListener('change', function (e) {
      if (e.target.type !== 'radio') return;
      var byKey = viaKeyboard();
      state.answers[q.id] = e.target.value;
      if (field) {
        field.hidden = e.target.value !== OTHER;
        if (e.target.value === OTHER && !byKey) field.focus();
      }
      if (clear) clear.hidden = false;
      changed(q);
    });
    return wrap;
  }

  function renderCheckbox(q) {
    var name = 'k-' + q.id;
    var cur = state.answers[q.id] || [];
    var exclusive = q.exclusive || [];
    var list = h('div', { class: 'opts' });
    q.options.forEach(function (o) { list.appendChild(optionRow('checkbox', name, o, o, cur.indexOf(o) >= 0)); });
    var field = null;
    if (q.other) {
      field = otherField(q);
      field.hidden = cur.indexOf(OTHER) < 0;
      list.appendChild(h('div', { class: 'opt-other' }, optionRow('checkbox', name, OTHER, 'Other', cur.indexOf(OTHER) >= 0), field));
    }
    var wrap = groupWrap(q, 'group', list);
    var count = null;
    if (q.max_choices) {
      count = h('p', { class: 'q__count', 'aria-live': 'polite' });
      wrap.appendChild(count);
    }
    function inputs() { return list.querySelectorAll('input[type=checkbox]'); }
    function limit() {
      if (!q.max_choices) return;
      var n = 0;
      each(inputs(), function (i) { if (i.checked) n++; });
      each(inputs(), function (i) { i.disabled = !i.checked && n >= q.max_choices; });
      count.textContent = n + ' of ' + q.max_choices + ' chosen';
    }
    var viaKeyboard = watchKeys(list);
    list.addEventListener('change', function (e) {
      var t = e.target;
      if (t.type !== 'checkbox') return;
      var byKey = viaKeyboard();
      if (t.checked) {
        each(inputs(), function (i) {
          if (i === t) return;
          var theirs = exclusive.indexOf(i.value) >= 0;
          if (exclusive.indexOf(t.value) >= 0 || theirs) i.checked = false;
        });
      }
      var chosen = [];
      each(inputs(), function (i) { if (i.checked) chosen.push(i.value); });
      if (chosen.length) state.answers[q.id] = chosen; else delete state.answers[q.id];
      if (field) {
        field.hidden = chosen.indexOf(OTHER) < 0;
        if (t.value === OTHER && t.checked && !byKey) field.focus();
      }
      limit();
      changed(q);
    });
    limit();
    return wrap;
  }

  function renderGrid(q) {
    var map = state.answers[q.id] || {};
    /* The group ties the question's words to its rows, so a screen reader says them when it enters the rows. */
    var grid = h('div', { class: 'grid', role: 'group', 'aria-labelledby': 't-' + q.id, 'aria-describedby': q.help ? 'h-' + q.id : null });
    var count = h('p', { class: 'q__count' });
    q.rows.forEach(function (row, ri) {
      var rid = 'r-' + q.id + '-' + ri;
      var pills = h('div', { class: 'pills', role: 'radiogroup', 'aria-labelledby': rid });
      q.cols.forEach(function (col) {
        var input = h('input', { type: 'radio', name: 'g-' + q.id + '-' + ri, value: col, class: 'pill__input' });
        if (map[row] === col) input.checked = true;
        pills.appendChild(h('label', { class: 'pill' }, input, h('span', { class: 'pill__text', text: col })));
      });
      pills.addEventListener('change', function (e) {
        var m = state.answers[q.id] || (state.answers[q.id] = {});
        m[row] = e.target.value;
        tally();
        changed(q);
      });
      grid.appendChild(h('div', { class: 'grid__row', 'data-row': String(ri) }, h('div', { class: 'grid__label', id: rid, text: row }), pills));
    });
    function tally() {
      var n = 0;
      q.rows.forEach(function (r) { if (state.answers[q.id] && state.answers[q.id][r]) n++; });
      count.textContent = n + ' of ' + q.rows.length + ' answered';
    }
    tally();
    var wrap = h('div', { class: 'q q--grid', 'data-q': q.id });
    wrap.appendChild(h('div', { class: 'q__title', id: 't-' + q.id }, q.title, reqMark(q)));
    append(wrap, helpBlock(q));
    wrap.appendChild(grid);
    wrap.appendChild(count);
    return wrap;
  }

  function renderQuestion(q) {
    if (q.type === 'text' || q.type === 'paragraph') return renderText(q);
    if (q.type === 'choice') return renderChoice(q);
    if (q.type === 'checkbox') return renderCheckbox(q);
    return renderGrid(q);
  }

  function renderPage(page, isFirst, animate) {
    var box = h('div', { class: 'page' + (animate && !NO_MOTION ? ' page--enter' : ''), 'data-page': page.id });
    if (!isFirst) {
      box.appendChild(h('h2', { class: 'page__title', text: page.title.replace(/^Part \d+ of \d+:\s*/, '') }));
      if (page.description) box.appendChild(h('div', { class: 'page__desc' }, rich(page.description)));
    }
    page.questions.forEach(function (q) { box.appendChild(renderQuestion(q)); });
    return box;
  }

  /* Show or hide the pages after a gate question as it is answered. */
  function syncPages(s, body, animate) {
    pageStates(s).forEach(function (ps, i) {
      var node = body.querySelector('[data-page="' + ps.page.id + '"]');
      if (ps.state === 'visible') {
        if (!node) body.appendChild(renderPage(ps.page, i === 0, animate));
      } else if (node) {
        body.removeChild(node);
      }
    });
  }

  /* ---------------------------------------------------------------- errors */

  function wrapOf(q) { return el.main.querySelector('[data-q="' + q.id + '"]'); }

  function showError(q, message) {
    var wrap = wrapOf(q);
    if (!wrap) return;
    var old = wrap.querySelector('.q__error');
    if (old) wrap.removeChild(old);
    wrap.className = wrap.className.replace(/\s*is-invalid/, '');
    each(wrap.querySelectorAll('.grid__row'), function (r) { r.className = r.className.replace(/\s*is-missing/, ''); });
    var targets = [];
    each(wrap.children, function (c) {
      if (c.tagName === 'INPUT' || c.tagName === 'TEXTAREA' || c.getAttribute('role') === 'radiogroup' || c.getAttribute('role') === 'group') targets.push(c);
    });
    targets.forEach(function (t) {
      t.removeAttribute('aria-invalid');
      var ids = (t.getAttribute('aria-describedby') || '').replace(/\s*e-\S+/, '');
      if (ids) t.setAttribute('aria-describedby', ids); else t.removeAttribute('aria-describedby');
    });
    if (!message) return;
    wrap.className += ' is-invalid';
    wrap.appendChild(h('p', { class: 'q__error', id: 'e-' + q.id }, icon('alert'), h('span', { text: message })));
    targets.forEach(function (t) {
      t.setAttribute('aria-invalid', 'true');
      t.setAttribute('aria-describedby', ((t.getAttribute('aria-describedby') || '') + ' e-' + q.id).replace(/^\s+/, ''));
    });
    if (q.type === 'grid') {
      var a = state.answers[q.id] || {};
      q.rows.forEach(function (r, ri) {
        if (!a[r]) {
          var row = wrap.querySelector('[data-row="' + ri + '"]');
          if (row) row.className += ' is-missing';
        }
      });
    }
  }

  function firstControl(q) {
    var wrap = wrapOf(q);
    if (!wrap) return null;
    return wrap.querySelector('input:checked:not([disabled])') || wrap.querySelector('input:not([disabled]):not([type=hidden]), textarea');
  }

  /* After any change: save, tidy that question's error, show or hide dependent pages, refresh the header and button. */
  function changed(q) {
    save();
    var s = BYID[current];
    var wrap = wrapOf(q);
    if (wrap && wrap.className.indexOf('is-invalid') >= 0) showError(q, problem(q));
    if (s && q.goto) {
      var body = el.main.querySelector('.body');
      if (body) syncPages(s, body, true);
    }
    updateTop();
    updateNext();
  }

  function validate(s) {
    var count = 0;
    var first = null;
    visibleQuestions(s).forEach(function (q) {
      var msg = problem(q);
      showError(q, msg);
      if (msg) { count++; if (!first) first = q; }
    });
    return { count: count, first: first };
  }

  /* ================================================================ screens */

  function hasRequired(s) {
    return screenQuestions(s).some(function (q) { return q.required; });
  }

  function renderSection(s) {
    var card = h('section', { class: 'card', 'aria-labelledby': 'h1' });
    var band = h('div', { class: 'band' }, h('h1', { id: 'h1', tabindex: '-1', text: s.title }));
    if (s.description) band.appendChild(rich(s.description));
    card.appendChild(band);
    var body = h('div', { class: 'body' });
    if (hasRequired(s)) {
      body.appendChild(h('p', { class: 'note' }, h('span', { class: 'req', 'aria-hidden': 'true', text: '*' }), ' means this question needs an answer.'));
    }
    card.appendChild(body);
    syncPages(s, body, false);
    return card;
  }

  function renderStop(s) {
    var q = PAGES[s.pages[0]].questions[0];
    var next = SCREENS[s.index + 1];
    var nextPart = next ? PART[next.part] : null;
    var buttons = h('div', { class: 'stop__go' });
    q.options.forEach(function (label) {
      var target = q.goto && q.goto[label];
      var ends = target === '@submit';
      buttons.appendChild(h('button', {
        type: 'button', class: 'btn ' + (ends ? 'btn--quiet' : 'btn--primary'),
        onclick: function () {
          state.answers[q.id] = label;
          if (ends) {
            state.ended = true;
            save();
            go('send');
          } else {
            state.ended = false;
            advanceFrom(s);
          }
        }
      }, h('span', null, label, !ends && nextPart ? h('small', { text: nextPart.minutes + (nextPart.optional ? ', optional' : '') }) : null)));
    });
    return h('section', { class: 'card stop', 'aria-labelledby': 'h1' },
      h('div', { class: 'stop__mark', 'aria-hidden': 'true' }, icon('check')),
      h('h1', { id: 'h1', tabindex: '-1', text: s.title }),
      s.description ? rich(s.description) : null,
      buttons);
  }

  /* Start, or carry on from the furthest screen. Answers saved with no position (damaged or older) begin at the top. */
  function begin() {
    if (!started()) { state.furthest = 0; save(); }
    go(furthestId());
  }

  function renderWelcome() {
    var card = h('section', { class: 'card welcome', 'aria-labelledby': 'h1' });
    card.appendChild(h('img', { class: 'logo', src: SPEC.logo, alt: SPEC.client.name, width: '230', height: '26' }));
    card.appendChild(h('h1', { id: 'h1', tabindex: '-1', text: SPEC.title }));
    var text = h('div', { class: 'welcome__text' });
    SPEC.intro.forEach(function (p) { text.appendChild(h('p', { text: p })); });
    card.appendChild(text);
    if (SPEC.preview && /^https:\/\//.test(SPEC.preview.url)) {
      // What we made, so the questions have something to be about. It opens beside this page, and the answers stay saved here.
      card.appendChild(h('p', { class: 'welcome__drafts' },
        h('a', { class: 'btn btn--quiet btn--block', href: SPEC.preview.url, target: '_blank', rel: 'noopener noreferrer' },
          icon('out'), SPEC.preview.label, h('span', { class: 'sr-only', text: ' (opens in a new tab)' }))));
    }
    var road = h('ol', { class: 'roadmap' });
    PARTS.forEach(function (part) {
      road.appendChild(h('li', null, h('span', { class: 'roadmap__n', 'aria-hidden': 'true', text: String(part.n) }),
        h('div', null, h('b', { text: 'Part ' + part.n + ': ' + part.title }), h('span', { class: 't', text: part.minutes + (part.optional ? ' · optional' : '') }))));
    });
    card.appendChild(road);
    var go1 = h('div', { class: 'welcome__go' });
    var saved = started() || hasAnswers();
    if (saved) {
      var box = h('div', { class: 'resume' }, h('p', { text: 'Welcome back. Your answers are saved on this device.' }));
      box.appendChild(h('button', { type: 'button', class: 'btn btn--primary btn--block', onclick: begin },
        started() ? 'Carry on where you left off' : 'Start'));
      var again = h('button', { type: 'button', class: 'btn btn--quiet btn--block', onclick: function () { eraseConfirm(again); } }, 'Erase my answers and start over');
      box.appendChild(again);
      go1.appendChild(box);
    } else {
      go1.appendChild(h('button', { type: 'button', class: 'btn btn--primary btn--block', onclick: begin }, 'Start'));
    }
    card.appendChild(go1);
    var ticks = h('ul', { class: 'ticks' },
      h('li', { text: 'One section at a time. Tap an answer, then Next. You can skip any question and go back to change anything.' }),
      h('li', { text: 'Your answers are saved on this device as you go, so you can close this page and come back to it. If you wait more than a week, your browser may clear them.' }),
      h('li', { text: SPEC.endpoint ? 'Your answers go to ' + SPEC.client.agency + ' only when you press Send at the end.' : 'Nothing is sent until you choose to send it at the end.' }));
    card.appendChild(ticks);
    if (!storageOk) {
      card.appendChild(h('p', { class: 'warn' }, 'This browser can’t save your answers, so keep this page open until you’ve sent them.'));
    }
    if (SPEC.byline) card.appendChild(h('p', { class: 'byline', text: SPEC.byline }));
    return card;
  }

  /* A two-step erase: the first tap asks, the second erases. */
  function eraseConfirm(btn) {
    if (btn.getAttribute('data-ask') !== '1') {
      btn.setAttribute('data-ask', '1');
      btn.textContent = 'Tap again to erase everything on this device';
      announce('Tap again to erase your answers.');
      window.setTimeout(function () {
        if (btn.parentNode) { btn.setAttribute('data-ask', ''); btn.textContent = 'Erase my answers and start over'; }
      }, 6000);
      return;
    }
    try { window.localStorage.removeItem(STORE_KEY); } catch (e) { /* nothing to remove */ }
    state = blank();
    current = null;
    go('welcome');
  }

  /* ---------------------------------------------------------------- send and review */

  function fmtDate(d) {
    return d.toLocaleDateString('en-CA', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' }) + ', ' +
      d.toLocaleTimeString('en-CA', { hour: 'numeric', minute: '2-digit' });
  }

  function reachedSections() {
    return SCREENS.filter(function (s) { return s.kind === 'section' && started() && s.index <= state.furthest; });
  }

  /* How many of the questions the person has been through they answered. Everything is optional, so it can be none. */
  function countAnswers() {
    var n = { shown: 0, answered: 0 };
    reachedSections().forEach(function (s) {
      visibleQuestions(s).forEach(function (q) {
        n.shown++;
        if (answerOf(q)) n.answered++;
      });
    });
    return n;
  }

  function exportText() {
    var out = [];
    var body = [];
    var lastPart = null;
    var open = openProblems();
    var tally = countAnswers();
    reachedSections().forEach(function (s) {
      var part = PART[s.part];
      if (part !== lastPart) {
        body.push('== PART ' + part.n + ' OF ' + part.of + ': ' + part.title.toUpperCase() + ' ==', '');
        lastPart = part;
      }
      body.push('-- ' + s.title + ' --', '');
      visibleQuestions(s).forEach(function (q) {
        var a = answerOf(q);
        body.push(q.title);
        if (!a) body.push('  (no answer)');
        else if (a.text) body.push('  ' + a.text.replace(/\n/g, '\n  '));
        else if (a.items) a.items.forEach(function (i) { body.push('  - ' + i); });
        else a.rows.forEach(function (r) { body.push('  ' + r[0] + (/[.?!]$/.test(r[0]) ? ' — ' : ': ') + r[1]); });
        body.push('');
      });
    });
    var status = PARTS.map(function (part) {
      var any = part.screens.some(function (s) { return started() && s.index <= state.furthest; });
      var gaps = open.filter(function (o) { return o.s.part === part.id; }).length;
      if (partPassed(part) && !gaps) return 'Part ' + part.n + ' finished';
      if (!any) return 'Part ' + part.n + ' not started';
      return 'Part ' + part.n + ' started' + (gaps ? ' (' + plural(gaps, 'question still needs', 'questions still need') + ' an answer)' : '');
    }).join('. ') + '.';
    /* "as of", not "sent": the same text is also copied or saved as a file. */
    out.push(SPEC.answersTitle, 'Answers as of: ' + fmtDate(new Date()), status, 'Questions answered: ' + tally.answered + ' of ' + tally.shown + '.', '');
    return out.concat(body).join('\n').replace(/\n+$/, '') + '\n';
  }

  function answersById() {
    var out = {};
    reachedSections().forEach(function (s) {
      visibleQuestions(s).forEach(function (q) {
        var a = answerOf(q);
        if (!a) return;
        if (a.text) out[q.id] = a.text;
        else if (a.items) out[q.id] = a.items;
        else { var m = {}; a.rows.forEach(function (r) { m[r[0]] = r[1]; }); out[q.id] = m; }
      });
    });
    return out;
  }

  function fileName() { return SPEC.client.slug + '-website-answers.txt'; }

  function setStatus(text, bad) {
    var node = el.main.querySelector('.send__status');
    if (!node) return;
    node.textContent = text;
    node.className = 'send__status' + (bad ? ' is-bad' : '');
  }

  function showRaw() {
    var d = el.main.querySelector('details.raw');
    if (d) d.open = true;
  }

  function doShare() {
    navigator.share({ title: SPEC.answersTitle, text: exportText() }).then(function () {
      state.shared = Date.now();
      save();
      setStatus('Thank you. If you sent the message, we’ll have your answers. You can send them again whenever you like.');
    }, function (err) {
      if (err && err.name === 'AbortError') setStatus('Nothing was sent. You can try again when you’re ready.');
      else { setStatus('Sharing didn’t work on this device. Try “Copy my answers” instead.', true); showRaw(); }
    });
  }

  function doCopy() {
    var text = exportText();
    function ok() { setStatus('Copied. Now paste it into a text, WhatsApp or email message.'); }
    function bad() { setStatus('Copying didn’t work here. Select the text below, copy it, and paste it into a message.', true); showRaw(); }
    function fallback() {
      try {
        var ta = h('textarea', { 'aria-hidden': 'true', tabindex: '-1' });
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.left = '-9999px';
        document.body.appendChild(ta);
        ta.focus();
        ta.select();
        ta.setSelectionRange(0, text.length);
        var done = document.execCommand('copy');
        document.body.removeChild(ta);
        if (done) ok(); else bad();
      } catch (e) { bad(); }
    }
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(ok, fallback);
    else fallback();
  }

  function doSave() {
    try {
      var blob = new Blob([exportText()], { type: 'text/plain;charset=utf-8' });
      var url = URL.createObjectURL(blob);
      var a = h('a', { href: url, download: fileName() });
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.setTimeout(function () { URL.revokeObjectURL(url); }, 5000);
      setStatus('Saved as ' + fileName() + '. Look in your Downloads or the Files app, then send that file.');
    } catch (e) {
      setStatus('Saving a file didn’t work here. Try “Copy my answers” instead.', true);
      showRaw();
    }
  }

  var sending = false; // a second tap while the first is on its way must not send the answers twice

  function doEndpoint() {
    if (sending) return;
    sending = true;
    setStatus('Sending…');
    var ctl = typeof AbortController === 'function' ? new AbortController() : null;
    var timer = window.setTimeout(function () { if (ctl) ctl.abort(); }, 25000);
    var body = JSON.stringify({
      form: SPEC.client.slug, version: SPEC.version, sent_at: new Date().toISOString(),
      complete: allDone(), answers: answersById(), text: exportText()
    });
    // "Sent" is only said when the receiver says so. A web address can answer 200 and still not have taken the answers
    // (a sign-in page, an error page), so the reply has to be {"ok":true}, not just a good status.
    fetch(SPEC.endpoint, { method: 'POST', headers: { 'Content-Type': 'text/plain;charset=utf-8' }, body: body, signal: ctl ? ctl.signal : undefined })
      .then(function (r) {
        if (!r.ok) throw new Error('status ' + r.status);
        return r.json();
      })
      .then(function (reply) {
        if (!reply || reply.ok !== true) throw new Error('the receiver did not accept it');
        window.clearTimeout(timer);
        sending = false;
        state.sent = Date.now();
        save();
        setStatus('Sent. Thank you.');
      })
      .catch(function () {
        window.clearTimeout(timer);
        sending = false;
        setStatus('That didn’t go through. Check your connection and try again, or use “Copy my answers”.', true);
        showRaw();
      });
  }

  function answerNode(q) {
    var a = answerOf(q);
    var flag = problem(q) ? h('span', { class: 'rq__flag', text: 'Needs an answer' }) : null;
    if (!a) return h('div', { class: 'rq__a rq__none' }, flag || 'No answer');
    var box = h('div', { class: 'rq__a' });
    if (a.text) box.appendChild(document.createTextNode(a.text));
    else if (a.items) box.appendChild(h('ul', null, a.items.map(function (i) { return h('li', { text: i }); })));
    else a.rows.forEach(function (r) { box.appendChild(h('span', { class: 'row' }, h('b', { text: r[1] }), ' · ' + r[0])); });
    if (flag) box.appendChild(flag);
    return box;
  }

  function renderSend() {
    if (!countAnswers().answered) {
      // Every question is optional, so a person can get here having answered none. There is nothing to send.
      return h('section', { class: 'card send', 'aria-labelledby': 'h1' },
        h('h1', { id: 'h1', tabindex: '-1', text: 'You haven’t answered anything yet.' }),
        rich('That’s fine. Nothing has been sent. You can go back and answer any question, or just close this page.'),
        h('div', { class: 'send__actions' },
          h('button', { type: 'button', class: 'btn btn--primary btn--block', onclick: function () { state.ended = false; editing = false; save(); go(SCREENS[0].id); } },
            'Go to the first question')));
    }
    var open = openProblems();
    var complete = isComplete() && !open.length;
    var card = h('section', { class: 'card send', 'aria-labelledby': 'h1' });
    card.appendChild(h('h1', { id: 'h1', tabindex: '-1', text: complete ? 'That’s everything. Thank you.' : 'Thank you. Here’s what you have so far.' }));
    card.appendChild(rich(complete ? SPEC.done : SPEC.partial));
    if (open.length) {
      // Reached by an edit that opened new questions and a jump through the Sections menu: say so instead of "that's everything".
      card.appendChild(h('div', { class: 'send__needs' },
        h('h2', { text: plural(open.length, 'question still needs', 'questions still need') + ' an answer' }),
        h('p', { text: 'They are marked in your answers below. You can send what you have now, or answer them first.' }),
        h('button', { type: 'button', class: 'btn btn--quiet btn--block', onclick: function () { editing = true; go(open[0].s.id); } }, 'Go to the first one')));
    }
    var actions = h('div', { class: 'send__actions' });
    function button(label, fn, primary, ic) {
      return h('button', { type: 'button', class: 'btn btn--block ' + (primary ? 'btn--primary' : 'btn--quiet'), onclick: fn }, icon(ic), label);
    }
    if (SPEC.endpoint) actions.appendChild(button('Send my answers', doEndpoint, true, 'share'));
    if (CAN_SHARE) actions.appendChild(button(SPEC.endpoint ? 'Share instead' : 'Send my answers', doShare, !SPEC.endpoint, 'share'));
    actions.appendChild(button('Copy my answers', doCopy, !SPEC.endpoint && !CAN_SHARE, 'copy'));
    actions.appendChild(button('Save as a file', doSave, false, 'save'));
    card.appendChild(actions);
    var how = SPEC.endpoint
      ? 'This sends your answers and the time to ' + SPEC.client.agency + '. Your name, number and email aren’t part of it unless you wrote them in an answer.'
      : (CAN_SHARE
        ? 'Tap Send my answers, choose a text, WhatsApp or email, and send it to the person who sent you this link.'
        : 'Copy your answers, then paste them into a text, WhatsApp or email to the person who sent you this link.');
    card.appendChild(h('p', { class: 'send__how', text: how }));
    card.appendChild(h('p', { class: 'send__status', role: 'status', 'aria-live': 'polite' }));
    var raw = h('details', { class: 'raw' }, h('summary', { text: 'Show the text that gets sent' }));
    var ta = h('textarea', { readonly: true, 'aria-label': 'The text of your answers', rows: '10' });
    ta.value = exportText();
    raw.appendChild(ta);
    card.appendChild(raw);

    if (!isComplete()) {
      var at = SCREENS[Math.max(0, Math.min(state.furthest, SCREENS.length - 1))];
      var target = at.kind === 'stop' ? SCREENS[at.index + 1] : at; // a stop is passed; anywhere else, resume there
      if (target) {
        var targetPart = PART[target.part];
        var fromStop = at.kind === 'stop';
        card.appendChild(h('div', { class: 'send__more' },
          h('h2', { text: 'Not finished?' }),
          h('p', { text: 'You can send this now and still carry on with ' + (fromStop ? 'Part ' + targetPart.n + ' (' + targetPart.minutes + ')' : 'the rest of Part ' + targetPart.n) + ' whenever you like.' }),
          h('button', { type: 'button', class: 'btn btn--quiet btn--block', onclick: function () {
            state.ended = false;
            if (fromStop) { advanceFrom(at); } else { save(); go(at.id); }
          } }, fromStop ? 'Carry on with Part ' + targetPart.n : 'Carry on where you left off')));
      }
    }

    var review = h('div', { class: 'review' }, h('h2', { text: 'Check your answers' }),
      h('p', { class: 'review__lead', text: 'Tap Edit to change anything. Your changes are saved as you make them.' }));
    reachedSections().forEach(function (s) {
      var sec = h('div', { class: 'rsec' }, h('div', { class: 'rsec__head' }, h('h3', { text: s.title }),
        h('button', { type: 'button', class: 'rsec__edit', onclick: function () { editing = true; go(s.id); } }, 'Edit', h('span', { class: 'sr-only', text: ' ' + s.title }))));
      visibleQuestions(s).forEach(function (q) {
        sec.appendChild(h('div', { class: 'rq' }, h('div', { class: 'rq__t', text: q.title }), answerNode(q)));
      });
      review.appendChild(sec);
    });
    PARTS.forEach(function (part) {
      var any = part.screens.some(function (s) { return started() && s.index <= state.furthest; });
      if (!any) review.appendChild(h('p', { class: 'rpart' }, h('b', { text: 'Part ' + part.n + ': ' + part.title }), ' isn’t started. ' + (part.optional ? 'It’s optional.' : 'You can do it later.')));
    });
    var erase = h('div', { class: 'erase' }, h('p', { text: 'Finished? You can erase your answers from this device. Send them first.' }));
    var eraseBtn = h('button', { type: 'button', class: 'btn btn--quiet btn--block', onclick: function () { eraseConfirm(eraseBtn); } }, 'Erase my answers and start over');
    erase.appendChild(eraseBtn);
    review.appendChild(erase);
    var wrapper = h('div', null, card, h('section', { class: 'card', 'aria-label': 'Your answers' }, review));
    wrapper.className = 'sendwrap';
    return wrapper;
  }

  /* ================================================================ bottom bar */

  var nextBtn = null;

  function updateNext() {
    if (!nextBtn) return;
    var s = BYID[current];
    if (!s || s.kind !== 'section') return;
    var qs = visibleQuestions(s);
    var anyRequired = qs.some(function (q) { return q.required; });
    var anyAnswered = qs.some(function (q) { return fraction(q) > 0; });
    var last = s.index === lastSectionIndex();
    nextBtn.textContent = editing ? 'Back to my answers' : (last ? 'Check and send' : (!anyRequired && !anyAnswered ? 'Skip' : 'Next'));
  }

  function onNext() {
    var s = BYID[current];
    var v = validate(s);
    if (v.count) {
      var control = firstControl(v.first);
      var wrap = wrapOf(v.first);
      if (wrap && wrap.scrollIntoView) wrap.scrollIntoView({ block: 'start', behavior: NO_MOTION ? 'auto' : 'smooth' });
      if (control) { try { control.focus({ preventScroll: true }); } catch (e) { control.focus(); } }
      announce(plural(v.count, 'question needs', 'questions need') + ' an answer.');
      return;
    }
    if (editing) { go('send'); return; }
    advanceFrom(s);
  }

  function renderFoot() {
    el.foot.textContent = '';
    nextBtn = null;
    if (current === 'welcome') { el.foot.hidden = true; return; }
    el.foot.hidden = false;
    var s = BYID[current];
    var inner = h('div', { class: 'foot__in' });
    inner.appendChild(h('button', { type: 'button', class: 'btn btn--quiet', onclick: function () { go(previousOf(current)); } }, 'Back'));
    if (s && s.kind === 'section') {
      nextBtn = h('button', { type: 'button', class: 'btn btn--primary', onclick: onNext }, 'Next');
      inner.appendChild(nextBtn);
      updateNext();
    }
    el.foot.appendChild(inner);
  }

  /* ================================================================ render */

  function titleFor(id) {
    if (id === 'welcome') return SPEC.title;
    if (id === 'send') return 'Check and send · ' + SPEC.title;
    return BYID[id].title.replace(/^Part \d+ of \d+:\s*/, '') + ' · ' + SPEC.title;
  }

  function render() {
    var want = routeFromHash();
    var id = resolve(want);
    if (id !== want) {
      try { window.history.replaceState(null, '', '#/' + id); } catch (e) { window.location.hash = '#/' + id; }
    }
    closeMenu(true);
    if (id === 'send') editing = false;
    var before = order(current);
    var after = order(id);
    current = id;
    el.main.textContent = '';
    var node;
    if (id === 'welcome') node = renderWelcome();
    else if (id === 'send') node = renderSend();
    else node = BYID[id].kind === 'stop' ? renderStop(BYID[id]) : renderSection(BYID[id]);
    if (!firstRender && !NO_MOTION && before !== after) {
      node.className += after > before ? ' go-forward' : ' go-back';
    }
    el.main.appendChild(node);
    el.top.hidden = id === 'welcome';
    if (id !== 'welcome') updateTop();
    renderFoot();
    document.title = titleFor(id);
    document.body.setAttribute('data-screen', id);
    if (!firstRender) {
      window.scrollTo(0, 0);
      var heading = el.main.querySelector('h1');
      if (heading) { try { heading.focus({ preventScroll: true }); } catch (e) { heading.focus(); } }
      var s = BYID[id];
      announce(s && s.kind === 'section' ? 'Part ' + PART[s.part].n + ', section ' + s.no + ' of ' + s.of + ': ' + s.title : titleFor(id));
    }
    firstRender = false;
  }

  window.addEventListener('hashchange', render);

  try {
    var boot = document.getElementById('boot');
    if (boot) boot.parentNode.removeChild(boot);
    render();
  } catch (err) {
    el.main.textContent = '';
    el.main.appendChild(h('div', { class: 'boot' }, h('p', { text: 'Something went wrong showing the questions. Reload the page. If it happens again, tell ' + SPEC.client.agency + ' and we’ll send the questions another way.' })));
    if (window.console && console.error) console.error(err);
  }
})();
