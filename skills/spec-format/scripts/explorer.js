// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0
// Spec explorer. Fields ending in _html were produced at build time by render_html (author()
// for author text, literal() for a record's generated fields) and are the only values assigned
// to innerHTML; everything else goes in as text.
(() => {
  'use strict';
  const DATA = JSON.parse(document.getElementById('spec-data').textContent);
  const SPECS = DATA.specs;
  const FACTS = [];
  for (const s of SPECS) {
    for (const f of s.facts) {
      f.spec = s.id;
      const page = s.pages.find(p => p.label === f.source);
      f.page = page ? page.html : '';
      f.hay = [f.title, f.text, s.id, s.name, f.section, f.todo ? f.todo.text : '', ...f.row_todos.map(r => r.text),
        ...f.cites.map(c => c.title + ' ' + c.at.map(a => a.label).join(' '))].join(' ').toLowerCase();
      FACTS.push(f);
    }
  }
  const KIND = { board: 'Boards', soc: 'SoCs', chip: 'Chips', ip: 'IP blocks', peripheral: 'Peripherals', review: 'Reviews' };
  const PROBLEM = new Set(['FAIL', 'UNVERIFIABLE', 'ADJUDICATE']);
  const state = { spec: null, q: '', crit: false, verdict: null, todo: null, cls: null, open: new Set() };

  function el(tag, attrs, ...kids) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (k === 'class') n.className = v;
      else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
      else if (v !== false && v != null) n.setAttribute(k, v);
    }
    for (const k of kids.flat()) if (k != null && k !== false) n.append(k);
    return n;
  }
  function trusted(tag, cls, html) { const n = el(tag, { class: cls }); n.innerHTML = html; return n; }
  function link(href, text) {
    return /^https?:\/\//i.test(href) ? el('a', { href, target: '_blank', rel: 'noopener noreferrer' }, text) : text;
  }
  const terms = () => state.q.toLowerCase().split(/\s+/).filter(Boolean);
  function highlight(text, hl) {
    const frag = document.createDocumentFragment();
    if (!hl.length) { frag.append(text); return frag; }
    const re = new RegExp('(' + hl.map(t => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|') + ')', 'gi');
    String(text).split(re).forEach((p, i) => frag.append(i % 2 ? el('mark', {}, p) : p));
    return frag;
  }
  function score(f, ts) {
    let s = 0;
    for (const t of ts) {
      if (!f.hay.includes(t)) return -1;
      s += 1 + (f.title.toLowerCase().includes(t) ? 5 : 0) + (f.text.toLowerCase().includes(t) ? 2 : 0);
    }
    return s;
  }
  const childProblem = f => f.children.some(c => PROBLEM.has(c.verdict) || (c.status && c.status !== 'current'));
  const isProblem = f => PROBLEM.has(f.verdict) || (f.status && f.status !== 'current') || f.contested ||
    f.second_reader_missing || childProblem(f);
  function matches(f) {
    if (state.spec && f.spec !== state.spec) return false;
    if (state.crit && !f.critical) return false;
    if (state.verdict === 'PASS' && !(f.verdict === 'PASS' && !isProblem(f))) return false;
    if (state.verdict === 'GAP' && !f.gap) return false;
    if (state.verdict === 'PROBLEM' && !isProblem(f)) return false;
    if (state.todo && !((f.todo && f.todo.check === state.todo) || f.row_todos.some(r => r.check === state.todo))) return false;
    if (state.cls && !f.cites.some(c => c.class === state.cls)) return false;
    return true;
  }
  const scoped = () => FACTS.filter(f => !state.spec || f.spec === state.spec);

  function renderRail() {
    const box = document.getElementById('devs');
    box.replaceChildren();
    const btn = (id, label, n, nm) => el('button', {
      class: 'dev', 'aria-pressed': String(state.spec === id),
      onclick: () => { state.spec = id; state.open.clear(); render(); }
    }, el('span', { class: 'id' }, label), el('span', { class: 'n' }, String(n)), nm ? el('span', { class: 'nm' }, nm) : null);
    box.append(btn(null, 'All specs', FACTS.length));
    const kinds = [...new Set(SPECS.map(s => s.kind))];
    for (const kind of kinds) {
      box.append(el('h2', {}, KIND[kind] || kind || 'Overlays'));
      for (const s of SPECS.filter(x => x.kind === kind)) box.append(btn(s.id, s.id, s.facts.length, s.name));
    }
    const pages = document.getElementById('pages');
    pages.replaceChildren(el('h2', {}, 'Full pages'), el('ul', { class: 'pagelist' },
      SPECS.flatMap(s => s.pages.map(p => el('li', {}, el('a', { href: p.html }, p.label), ' · ',
        el('a', { href: p.markdown }, 'Markdown'))))));
  }

  function renderFilters(shown) {
    const chip = (label, on, fn) => el('button', { class: 'chip', 'aria-pressed': String(!!on), onclick: () => { fn(); render(); } }, label);
    const toggle = (key, value) => () => { state[key] = state[key] === value ? null : value; };
    const todos = [...new Set(scoped().flatMap(f => (f.todo ? [f.todo] : []).concat(f.row_todos)).map(t => t.check))].sort();
    const classes = [...new Set(scoped().flatMap(f => f.cites.map(c => c.class)))].sort();
    const any = state.crit || state.verdict || state.todo || state.cls || state.q;
    document.getElementById('filters').replaceChildren(...[
      el('span', { class: 'lbl' }, 'Show'),
      chip('Bring-up critical', state.crit, () => { state.crit = !state.crit; }),
      chip('Verified', state.verdict === 'PASS', toggle('verdict', 'PASS')),
      chip('Gaps', state.verdict === 'GAP', toggle('verdict', 'GAP')),
      FACTS.some(isProblem) ? chip('Needs attention', state.verdict === 'PROBLEM', toggle('verdict', 'PROBLEM')) : null,
      todos.length ? [el('span', { class: 'sep' }), el('span', { class: 'lbl' }, 'Open check'),
        ...todos.map(t => chip(t, state.todo === t, toggle('todo', t)))] : null,
      classes.length ? [el('span', { class: 'sep' }), el('span', { class: 'lbl' }, 'Cited from'),
        ...classes.map(c => chip(c, state.cls === c, toggle('cls', c)))] : null,
      el('span', { class: 'sep' }),
      el('span', { class: 'count' }, shown + ' of ' + scoped().length + ' facts'),
      any ? el('button', { class: 'clear', onclick: () => {
        Object.assign(state, { q: '', crit: false, verdict: null, todo: null, cls: null });
        document.getElementById('q').value = ''; render();
      } }, 'Clear') : null].flat().filter(Boolean));
  }

  function renderOverview() {
    const box = document.getElementById('overview');
    box.replaceChildren();
    const s = SPECS.find(x => x.id === state.spec);
    if (!s) return;
    const count = p => s.facts.filter(p).length;
    box.append(el('section', { class: 'overview' },
      el('h1', {}, s.name),
      el('div', { class: 'ov-meta' }, el('span', { class: 'mono' }, s.id), el('span', {}, s.kind),
        s.triggers.length ? el('span', {}, 'Matches: ' + s.triggers.join(', ')) : null,
        s.pages.map(p => el('a', { href: p.html }, s.pages.length > 1 ? 'Full page: ' + p.label : 'Full page'))),
      s.orientation_html ? trusted('div', 'ov-text', s.orientation_html) : null,
      el('div', { class: 'stats' }, [[s.facts.length, 'facts'], [count(f => f.verdict === 'PASS' && !isProblem(f)), 'verified'],
        [count(f => f.gap), 'gaps'], [count(f => f.critical), 'bring-up critical'],
        [count(f => f.todo && f.todo.check === 'hardware'), 'need hardware check'], [s.facts.reduce((n, f) => n + f.row_todos.length, 0), 'row checks'], [s.documents.length, 'documents']]
        .map(([v, l]) => el('div', { class: 'stat' }, el('b', {}, String(v)), el('span', {}, l)))),
      s.documents.length ? el('details', {}, el('summary', {}, 'Source documents (' + s.documents.length + ')'),
        el('ul', { class: 'doclist' }, s.documents.map(d => el('li', {}, el('span', { class: 'cls' }, d.class),
          el('span', {}, link(d.url, d.title), d.pages ? ' · ' + d.pages + ' pp.' : ''))))) : null));
  }

  function verdictTag(f) {
    if (f.gap && !isProblem(f)) return el('span', { class: 'tag t-gap' }, 'gap');
    if (f.verdict === 'PASS' && !isProblem(f)) return el('span', { class: 'tag t-pass' }, 'verified');
    if (f.contested) return el('span', { class: 'tag t-other' }, 'contested');
    if (f.second_reader_missing) return el('span', { class: 'tag t-other' }, 'second reader missing');
    if (childProblem(f)) return el('span', { class: 'tag t-other' }, 'entry needs attention');
    return el('span', { class: 'tag t-other' }, (f.verdict || 'unverified') + (f.status && f.status !== 'current' ? ' · ' + f.status : ''));
  }

  function citations(f) {
    if (!f.cites.length) return el('p', { class: 'note' }, 'No support yet' + (f.todo ? ': open check on ' + f.todo.check + '.' : '.'));
    return el('ul', { class: 'cites' }, f.cites.map(c => el('li', {}, el('span', { class: 'cls' }, c.class),
      el('span', {}, c.title ? link(c.url, c.title) : null,
        c.premises.length ? el('ul', { class: 'premises' }, c.premises.map(p => el('li', {}, p))) : null,
        c.at.length ? el('span', { class: 'jumps' }, c.at.map(a => a.href
          ? el('a', { class: 'jump', href: a.href, target: '_blank', rel: 'noopener noreferrer', title: 'Open the document at this heading' }, '→ ' + a.label)
          : el('span', { class: 'jump-off' }, a.label))) : null))));
  }

  function row(f, hl) {
    const open = state.open.has(f.ref);
    const li = el('li', { class: 'fact' + (f.gap ? ' is-gap' : isProblem(f) ? ' is-other' : '') + (open ? ' open' : '') });
    li.append(el('button', { 'aria-expanded': String(open), onclick: () => {
      open ? state.open.delete(f.ref) : state.open.add(f.ref);
      li.replaceWith(row(f, hl));
    } },
    el('span', { class: 'fact-title' }, highlight(f.title, hl)),
    el('span', { class: 'tags' }, state.spec ? null : el('span', { class: 'tag t-spec' }, f.spec),
      f.critical ? el('span', { class: 'tag t-crit' }, 'critical') : null, verdictTag(f),
      f.todo ? el('span', { class: 'tag t-todo' }, 'check: ' + f.todo.check) : null),
    el('span', { class: 'fact-sum' }, highlight(f.text, hl))));
    if (open) {
      const copy = el('button', { class: 'copy', onclick: e => {
        navigator.clipboard.writeText(f.ref).then(() => { e.target.textContent = 'Copied'; },
          () => { e.target.textContent = 'Select the reference to copy'; });
      } }, 'Copy reference');
      const reviewers = [f.verifier ? 'Verifier: ' + f.verifier : null,
        ...f.readers.map(r => 'Second reader: ' + r.verifier + ' · ' + r.verdict)].filter(Boolean);
      li.append(el('div', { class: 'body' },
        trusted('div', 'claim', f.claim_html),
        el('div', { class: 'kv' }, el('h4', {}, 'Sources'), citations(f)),
        f.assumes.length ? el('div', { class: 'kv' }, el('h4', {}, 'Assumes'),
          f.assumes.map(a => el('p', { class: 'note' }, a.id + ': ' + a.text))) : null,
        f.conflicts.length ? el('div', { class: 'kv' }, el('h4', {}, 'Conflicting readings'),
          f.conflicts.map(c => el('p', { class: 'note' }, (c.resolved ? 'Resolved: ' : 'Unresolved: ') + c.reading))) : null,
        f.children.length ? el('div', { class: 'kv' }, el('h4', {}, 'Entries'),
          f.children.map(c => el('p', { class: 'note' }, c.key + ': ' + [c.verdict || 'unverified', c.status].filter(Boolean).join(' · ')))) : null,
        f.todo ? el('div', { class: 'kv' }, el('h4', {}, 'Open check: ' + f.todo.check), el('p', { class: 'note' }, f.todo.text)) : null,
        f.row_todos.length ? el('div', { class: 'kv' }, el('h4', {}, 'Open checks on rows'),
          f.row_todos.map(r => el('p', { class: 'note' }, r.check + ' · ' + r.fact + ' (' + r.kind + '): ' + r.text + (r.method ? ' Method: ' + r.method : '')))) : null,
        el('div', { class: 'meta' }, el('span', {}, [f.verdict, f.date, f.status].filter(Boolean).join(' · ')),
          el('span', {}, f.origin), el('span', { class: 'mono' }, f.ref), copy,
          f.page ? el('a', { href: f.page + '#' + encodeURIComponent(f.ref) }, 'Full page') : null),
        (reviewers.length || f.notes_html.length) ? el('details', {}, el('summary', { class: 'note' }, 'Review notes'),
          reviewers.map(r => el('p', { class: 'note' }, r)), f.notes_html.map(h => trusted('div', 'note', h))) : null));
    }
    return li;
  }

  function renderFacts() {
    const box = document.getElementById('results');
    box.replaceChildren();
    const ts = terms();
    const list = FACTS.filter(matches).map(f => [f, ts.length ? score(f, ts) : 0]).filter(([, s]) => s >= 0);
    if (ts.length) {
      list.sort((a, b) => b[1] - a[1]);
      box.append(el('div', { class: 'group' }, el('h3', {}, 'Best matches'), el('ul', { class: 'facts' }, list.map(([f]) => row(f, ts)))));
    } else {
      const groups = new Map();
      for (const [f] of list) {
        const key = (state.spec ? '' : f.spec + ' · ') + f.section.replace(/-/g, ' ');
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(f);
      }
      for (const [k, fs] of groups) box.append(el('div', { class: 'group' }, el('h3', {}, k), el('ul', { class: 'facts' }, fs.map(f => row(f, ts)))));
    }
    if (!list.length) box.append(el('p', { class: 'empty' }, 'No facts match. Try fewer words or clear a filter.'));
    return list.length;
  }

  function render() { renderRail(); renderOverview(); renderFilters(renderFacts()); }

  const q = document.getElementById('q');
  let timer;
  q.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(() => { state.q = q.value; state.open.clear(); render(); }, 80); });
  document.addEventListener('keydown', e => {
    if (e.key === '/' && document.activeElement !== q) { e.preventDefault(); q.focus(); }
    else if (e.key === 'Escape' && document.activeElement === q) { q.value = ''; state.q = ''; render(); }
  });
  let target = null;
  try { target = FACTS.find(f => f.ref === decodeURIComponent(location.hash.slice(1))); } catch (e) { target = null; }
  if (target) { state.spec = target.spec; state.open.add(target.ref); }
  render();
  if (target) {
    const opened = document.querySelector('.fact.open');
    if (opened) opened.scrollIntoView({ block: 'start' });
  }
})();
