// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0
// Board atlas page script (atlas.py). *_html fields come from the fixed-element renderer and
// are the only values assigned to innerHTML; everything else is inserted with textContent.
(() => {
'use strict';
const DATA = JSON.parse(document.getElementById('spec-data').textContent);
const $ = (s, r = document) => r.querySelector(s);
const SVG = 'http://www.w3.org/2000/svg';
function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}
function sv(tag, attrs) {
  const e = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs || {})) e.setAttribute(k, v);
  return e;
}
function html(tag, cls, markup) { const e = el(tag, cls); e.innerHTML = markup; return e; }
function store(key, value) {
  try { if (value === undefined) return localStorage.getItem(key); localStorage.setItem(key, value); } catch (_) {}
  return null;
}

/* ---------- model ---------- */
const KNOWN_KINDS = ['board', 'soc', 'chip', 'peripheral', 'ip'];
const kindClass = k => KNOWN_KINDS.includes(k) ? k : 'other';
const specs = DATA.specs;
const specById = new Map(specs.map(s => [s.id, s]));
const focusSpec = specById.get(DATA.focus);
const facts = DATA.facts.map(f => ({ ...f, out: [], inc: [] }));
const factByKey = new Map(facts.map(f => [f.key, f]));
for (const f of facts) for (const r of f.relates) {
  const t = factByKey.get(r.to);
  if (!t) continue;
  f.out.push({ fact: t, relation: r.relation });
  t.inc.push({ fact: f, relation: r.relation });
}
const instByKey = new Map(DATA.instances.map(i => [i.key, i]));
const factsOf = sid => facts.filter(f => f.spec === sid);
const humanSec = s => s.replace(/-/g, ' ').replace(/^./, c => c.toUpperCase());
function sectionsOf(sid) {
  const order = specById.get(sid).sections;
  const rank = s => { const i = order.indexOf(s); return i < 0 ? 99 : i; };
  return [...new Set(factsOf(sid).map(f => f.section))].sort((a, b) => rank(a) - rank(b));
}
const verdictOf = f => f.verdict || 'none';
const isStale = f => ['stale', 'upstream-stale', 'unknown'].includes(f.freshness);
const rootNames = DATA.roots.map(r => r.name);
const prefix = (() => {
  if (rootNames.length < 2) return '';
  let p = rootNames[0];
  for (const n of rootNames) while (!n.startsWith(p)) p = p.slice(0, -1);
  const cut = p.lastIndexOf('-');
  return cut > 0 ? p.slice(0, cut + 1) : '';
})();
const shortRoot = n => n.startsWith(prefix) ? n.slice(prefix.length) : n;
const JOIN_LABEL = { parts: 'Parts', ip: 'IP blocks', programming: 'Peripheral programming', related: 'Related specs' };
const childrenOf = sid => specs.filter(s => s.parent === sid);

/* ---------- masthead ---------- */
$('#eyebrow').textContent = focusSpec.kind + ' spec · composed from ' + rootNames.join(' + ');
const h1 = $('#title');
h1.append(focusSpec.name, ' ');
const partNames = childrenOf(focusSpec.id).filter(s => s.join === 'parts').map(s => s.id.toUpperCase());
if (partNames.length) h1.append(el('span', 'chip', '· ' + partNames.join(', ')));
const count = pred => facts.filter(pred).length;
for (const [cls, n, label] of [
  ['', specs.length, 'specs'], ['', facts.length, 'facts'], ['pass', count(f => f.verdict === 'PASS'), 'verified'],
  ['gap', count(f => f.verdict === 'GAP'), 'gaps'], ['crit', count(f => f.critical), 'critical'], ['', count(f => f.todo), 'open checks'],
  ['', facts.reduce((n, f) => n + f.row_todos.length, 0), 'row checks'],
]) { const s = el('div', 'stat ' + cls); s.append(el('b', null, String(n)), el('span', null, label)); $('#stats').append(s); }

/* ---------- shared bits ---------- */
const HELP = {
  PASS: 'Verified: an independent reader opened the cited evidence and it supports the claim as stated. It does not mean an open check has been carried out.',
  GAP: 'Gap: no source read so far states this, so the fact has no citation, only a recorded check that would settle it.',
  FAIL: 'Failed: a reader found the claim disagrees with its evidence, or a citation is wrong or missing. The author must fix the spec.',
  ADJUDICATE: 'Adjudicate: two independent readings disagree and a person has to decide.',
  UNVERIFIABLE: 'Unverifiable: the cited evidence could not be read, so nothing was established.',
  none: 'No verdict: no verification record covers this fact yet.',
  critical: 'Critical: the author marked this fact as needed for a first bring-up.',
  open: 'Open check: a follow-up is still recorded on the bench, in a document or in source code. A verified fact can still carry one.',
  stale: 'Stale: the fact, its evidence or a fact it rests on changed after the verdict was recorded.',
};
const WORD = { PASS: 'verified', GAP: 'gap', FAIL: 'failed', ADJUDICATE: 'needs adjudication', UNVERIFIABLE: 'unverifiable', none: 'no verdict' };
function pill(f) { const v = verdictOf(f); return el('span', 'pill ' + v, v === 'none' ? '—' : v); }
function evChips(f) {
  const c = el('span', 'chips');
  for (const cls of f.classes) c.append(el('span', 'ev ' + cls.replace(/[^\w-]/g, ''), cls));
  return c;
}
function factLink(f, onClick) {
  const b = el('button', 'link', f.title);
  b.title = f.key;
  b.addEventListener('click', e => { e.preventDefault(); e.stopPropagation(); (onClick || select)(f); });
  return b;
}
function vbar(list) {
  const b = el('span', 'vbar'); const n = list.length || 1;
  for (const [cls, v] of [['p', 'PASS'], ['g', 'GAP'], ['f', 'FAIL']]) {
    const k = list.filter(f => f.verdict === v).length;
    if (k) { const i = el('i', cls); i.style.width = (100 * k / n) + '%'; b.append(i); }
  }
  b.title = list.filter(f => f.verdict === 'PASS').length + ' of ' + list.length + ' verified';
  return b;
}
const tip = $('#tip');
function showTip(e, text) { tip.textContent = text; tip.hidden = false; moveTip(e); }
function moveTip(e) {
  tip.style.left = Math.max(8, Math.min(e.clientX + 14, window.innerWidth - tip.offsetWidth - 8)) + 'px';
  tip.style.top = (e.clientY + 16) + 'px';
}
function hideTip() { tip.hidden = true; }
function hoverHelp(node, text) {
  node.addEventListener('mouseenter', e => showTip(e, text)); node.addEventListener('mousemove', moveTip);
  node.addEventListener('mouseleave', hideTip);
}

/* ---------- inspector ---------- */
const panel = $('#panel');
const app = $('.app');
const narrow = () => matchMedia('(max-width: 900px)').matches;
const hist = [];
function setPanel(open, remember) {
  app.classList.toggle('panel-off', !open);
  const t = $('#panel-toggle');
  t.setAttribute('aria-pressed', String(open));
  t.querySelector('span').textContent = open ? 'Hide details' : 'Show details';
  if (remember) store('atlas-panel', open ? '1' : '0');
}
$('#panel-toggle').addEventListener('click', () => setPanel(app.classList.contains('panel-off'), true));
function panelEmpty() {
  panel.replaceChildren();
  const d = el('div', 'panel-empty');
  d.append(el('div', 'big', 'Pick something to inspect'),
    el('div', null, 'Click a spec in the graph, open a fact in the outline, or click a block in the memory map or a square in the coverage grid.'));
  if (focusSpec.orientation_html) d.append(el('h3', null, 'About this spec'), html('div', 'claim', focusSpec.orientation_html));
  panel.append(d);
}
function show(view, nested) {
  if (nested) hist.push(view); else hist.splice(0, hist.length, view);
  if (narrow()) setPanel(true, false);
  render(view);
}
function render(view) {
  panel.replaceChildren();
  const close = el('button', 'btn close', 'Close'); close.addEventListener('click', () => setPanel(false, false));
  panel.append(close);
  if (hist.length > 1) {
    const prev = hist[hist.length - 2];
    const b = el('button', 'link back', '← ' + (prev.type === 'fact' ? prev.f.title : prev.type === 'spec' ? prev.s.name : 'Fact links'));
    b.addEventListener('click', () => { hist.pop(); render(hist[hist.length - 1]); });
    panel.append(b);
  }
  if (view.type === 'fact') renderFact(view.f);
  else if (view.type === 'spec') renderSpec(view.s);
  else renderEdge(view.l);
  panel.scrollTop = 0;
}
const select = (f, nested) => show({ type: 'fact', f }, nested);
const selectSpec = (s, nested) => show({ type: 'spec', s }, nested);
function factRow(f) {
  const li = el('li');
  const j = el('button', 'jump', 'outline'); j.title = 'Show in outline';
  j.addEventListener('click', e => { e.stopPropagation(); revealInOutline(f); });
  li.append(pill(f), factLink(f, x => select(x, true)), j);
  return li;
}
function kv(pairs) {
  const dl = el('dl', 'kv');
  for (const [k, v] of pairs) dl.append(el('dt', null, k), el('dd', null, v || '—'));
  return dl;
}
function renderFact(f) {
  const spec = specById.get(f.spec);
  const top = el('div', 'row');
  const sb = el('button', 'link', spec.id); sb.addEventListener('click', () => selectSpec(spec, true));
  top.append(el('span', 'kind ' + kindClass(spec.kind), spec.kind), sb, el('span', 'eyebrow', '· ' + humanSec(f.section)));
  panel.append(top, el('h2', null, f.title));
  const badges = el('div', 'row');
  badges.append(pill(f));
  if (isStale(f)) badges.append(el('span', 'stale', f.freshness));
  if (f.critical) badges.append(el('span', 'crit', '◆ critical'));
  badges.append(el('span', 'layer', shortRoot(f.root)), evChips(f));
  panel.append(badges, el('div', 'idline', f.key));
  if (f.claim_html) panel.append(el('h3', null, 'Claim'), html('div', 'claim', f.claim_html));
  if (f.todo) {
    panel.append(el('h3', null, 'Open check'));
    const t = el('div', 'todo'); t.append(el('b', null, f.todo.check || 'check'), f.todo.text); panel.append(t);
  }
  if (f.row_todos.length) {
    panel.append(el('h3', null, 'Open checks on rows'));
    for (const r of f.row_todos) {
      const t = el('div', 'todo'); t.append(el('b', null, r.check), r.fact + ' (' + r.kind + '): ' + r.text + (r.method ? ' Method: ' + r.method : '')); panel.append(t);
    }
  }
  if (f.out.length || f.inc.length) {
    panel.append(el('h3', null, 'Relations'));
    const ul = el('ul', 'list');
    for (const [r, verb] of [...f.out.map(r => [r, r.relation + ' →']), ...f.inc.map(r => [r, '← ' + r.relation])]) {
      const li = el('li', 'rel'); li.append(el('span', 'verb', verb), factLink(r.fact, x => select(x, true))); ul.append(li);
    }
    panel.append(ul);
  }
  if (f.sources.length) {
    panel.append(el('h3', null, 'Evidence'));
    panel.append(kv(f.sources.map(s => [s.class, s.source])));
  }
  if (f.verdict) {
    panel.append(el('h3', null, 'Verification'));
    panel.append(kv([['verdict', f.verdict], ['freshness', f.freshness], ['date', f.date], ['verifier', f.verifier]]));
  }
  const act = el('div', 'actions');
  const a1 = el('button', 'btn', 'Show in outline'); a1.addEventListener('click', () => revealInOutline(f));
  const a2 = el('button', 'btn', 'Show spec in graph'); a2.addEventListener('click', () => { setTab('graph'); graph.focusSpec(f.spec); });
  act.append(a1, a2); panel.append(act);
  graph.markSpec(f.spec);
}
function renderSpec(spec) {
  const mine = factsOf(spec.id);
  const top = el('div', 'row');
  top.append(el('span', 'kind ' + kindClass(spec.kind), spec.kind), el('span', 'eyebrow', spec.id + ' · ' + spec.roots.map(shortRoot).join(' + ')));
  panel.append(top, el('h2', null, spec.name));
  const sr = el('div', 'statrow');
  for (const [cls, n, label] of [['', mine.length, 'facts'], ['pass', mine.filter(f => f.verdict === 'PASS').length, 'verified'],
    ['gap', mine.filter(f => f.verdict === 'GAP').length, 'gaps'], ['', mine.filter(f => f.todo).length, 'open checks']]) {
    const s = el('div', 'stat ' + cls); s.append(el('b', null, String(n)), el('span', null, label)); sr.append(s);
  }
  panel.append(sr);
  const act = el('div', 'actions');
  const a1 = el('button', 'btn', 'Show in outline'); a1.addEventListener('click', () => revealSpec(spec));
  const a2 = el('button', 'btn', 'Show in graph'); a2.addEventListener('click', () => { setTab('graph'); graph.focusSpec(spec.id); });
  act.append(a1, a2); panel.append(act);
  if (spec.orientation_html) panel.append(el('h3', null, 'Orientation'), html('div', 'claim', spec.orientation_html));
  const nb = graph.neighbors(spec.id);
  if (nb.length) {
    panel.append(el('h3', null, 'Connected specs'));
    const ul = el('ul', 'list');
    for (const n of nb) {
      const li = el('li', 'rel');
      const b = el('button', 'link', n.spec.name); b.addEventListener('click', () => selectSpec(n.spec, true));
      li.append(el('span', 'verb', n.label), b);
      if (n.link) {
        const e = el('button', 'jump', n.link.pairs.length + ' links'); e.title = 'List the fact links';
        e.addEventListener('click', () => show({ type: 'edge', l: n.link }, true)); li.append(e);
      }
      ul.append(li);
    }
    panel.append(ul);
  }
  const secs = sectionsOf(spec.id);
  if (secs.length) panel.append(el('h3', null, 'Facts'));
  for (const sec of secs) {
    const list = mine.filter(f => f.section === sec);
    const d = el('details', 'psec');
    d.open = secs.length <= 2 || list.some(f => f.critical && f.verdict !== 'PASS');
    const s = el('summary'); s.append(el('span', null, humanSec(sec)), el('span', 'count', String(list.length)), vbar(list));
    const ul = el('ul', 'flist');
    for (const f of list) ul.append(factRow(f));
    d.append(s, ul);
    panel.append(d);
  }
  graph.markSpec(spec.id);
}
function renderEdge(l) {
  panel.append(el('div', 'eyebrow', 'Fact links between two specs'), el('h2', null, l.a + ' ↔ ' + l.b));
  const ul = el('ul', 'list');
  for (const p of l.pairs) {
    const li = el('li', 'rel');
    li.append(factLink(p.from, x => select(x, true)), el('span', 'verb', p.relation + ' →'), factLink(p.to, x => select(x, true)));
    ul.append(li);
  }
  panel.append(ul);
}

/* ---------- tabs ---------- */
const views = {};
document.querySelectorAll('main.view').forEach(v => { views[v.dataset.view] = v; });
function setTab(name) {
  for (const [k, v] of Object.entries(views)) v.hidden = k !== name;
  document.querySelectorAll('.tab').forEach(t => t.setAttribute('aria-selected', String(t.dataset.tab === name)));
  if (name === 'graph') graph.ensure();
  store('atlas-tab', name);
}
document.querySelectorAll('.tab').forEach(t => t.addEventListener('click', () => setTab(t.dataset.tab)));

/* ---------- outline ---------- */
const factEls = new Map();
const specEls = new Map();
function factNode(f) {
  const d = el('details', 'fact');
  const s = el('summary');
  const meta = el('span', 'meta');
  if (isStale(f)) meta.append(el('span', 'stale', 'stale'));
  if (f.critical) meta.append(el('span', 'crit', '◆'));
  meta.append(el('span', 'layer', shortRoot(f.root)), evChips(f));
  s.append(pill(f), el('span', 't', f.title), meta);
  d.append(s);
  s.addEventListener('click', () => { if (!d.open) select(f); });
  d.addEventListener('toggle', () => {
    if (!d.open || d.querySelector('.fbody')) return;
    const b = el('div', 'fbody');
    if (f.claim_html) b.append(html('div', 'claim', f.claim_html));
    if (f.todo) { const t = el('div', 'todo'); t.append(el('b', null, f.todo.check || 'check'), f.todo.text); b.append(t); }
    for (const r of f.row_todos) { const t = el('div', 'todo'); t.append(el('b', null, r.check), r.fact + ' (' + r.kind + '): ' + r.text); b.append(t); }
    for (const r of f.out) { const li = el('div', 'rel'); li.append(el('span', 'verb', r.relation + ' →'), factLink(r.fact, revealInOutline)); b.append(li); }
    for (const r of f.inc) { const li = el('div', 'rel'); li.append(el('span', 'verb', '← ' + r.relation), factLink(r.fact, revealInOutline)); b.append(li); }
    b.append(el('span', 'idline mono', f.key));
    d.append(b);
  });
  factEls.set(f.key, d);
  return d;
}
function specNode(spec, top) {
  const d = el('details', 'spec' + (top ? ' top' : ''));
  specEls.set(spec.id, d);
  const mine = factsOf(spec.id);
  const s = el('summary');
  s.addEventListener('click', () => { if (!d.open) selectSpec(spec); });
  s.append(el('span', 'kind ' + kindClass(spec.kind), spec.kind), el('span', 'name', spec.name), el('span', 'sid', spec.id),
    el('span', 'count', mine.length + ' facts'), vbar(mine));
  d.append(s);
  const kids = el('div', 'kids');
  for (const sec of sectionsOf(spec.id)) {
    const list = mine.filter(f => f.section === sec);
    const sd = el('details', 'sec');
    const ss = el('summary');
    ss.append(el('span', 'label', humanSec(sec)), el('span', 'count', String(list.length)), vbar(list));
    const sk = el('div', 'kids');
    for (const f of list) sk.append(factNode(f));
    sd.append(ss, sk);
    kids.append(sd);
  }
  for (const join of Object.keys(JOIN_LABEL)) {
    const list = childrenOf(spec.id).filter(c => c.join === join);
    if (!list.length) continue;
    const g = el('details', 'group');
    g.open = true;
    const gs = el('summary'); gs.append(el('span', null, JOIN_LABEL[join]), el('span', 'count', String(list.length)));
    const gk = el('div', 'kids');
    for (const c of list) gk.append(specNode(c, false));
    g.append(gs, gk);
    kids.append(g);
  }
  d.append(kids);
  return d;
}
const rootSpec = specNode(focusSpec, true);
rootSpec.open = true;
$('#tree').append(rootSpec);
for (const c of childrenOf(focusSpec.id)) if (c.join === 'parts') specEls.get(c.id).open = true;

const filt = { q: '', crit: false, gap: false, todo: false, root: '' };
const segRoot = $('#f-root');
for (const [value, label] of [['', 'All roots'], ...rootNames.map(n => [n, shortRoot(n)])]) {
  const b = el('button', null, label); b.dataset.r = value; b.setAttribute('aria-pressed', String(value === ''));
  segRoot.append(b);
}
if (rootNames.length < 2) segRoot.hidden = true;
function mark(span, text, q) {
  span.replaceChildren();
  const i = q ? text.toLowerCase().indexOf(q) : -1;
  if (i < 0) { span.textContent = text; return; }
  span.append(text.slice(0, i), el('mark', null, text.slice(i, i + q.length)), text.slice(i + q.length));
}
function applyFilter() {
  const q = filt.q.toLowerCase();
  const active = q || filt.crit || filt.gap || filt.todo || filt.root;
  let shown = 0;
  for (const f of facts) {
    const d = factEls.get(f.key);
    const hay = (f.title + ' ' + f.text + ' ' + f.key + ' ' + (f.todo ? f.todo.text : '') + ' ' + f.row_todos.map(r => r.text).join(' ')).toLowerCase();
    const ok = (!q || hay.includes(q)) && (!filt.crit || f.critical) && (!filt.gap || f.verdict === 'GAP')
      && (!filt.todo || f.todo || f.row_todos.length) && (!filt.root || f.root === filt.root);
    d.hidden = !ok;
    if (ok) shown++;
    mark(d.querySelector('summary .t'), f.title, q);
  }
  for (const c of [...$('#tree').querySelectorAll('details.sec, details.group, details.spec')].reverse()) {
    const any = [...c.querySelectorAll('details.fact')].some(x => !x.hidden);
    c.hidden = !any && !!active;
    if (active && any) c.open = true;
  }
  $('#q-count').textContent = active ? shown + ' of ' + facts.length + ' facts' : '';
  $('#tree-empty').hidden = shown > 0;
}
function clearFilters() {
  Object.assign(filt, { q: '', crit: false, gap: false, todo: false, root: '' });
  $('#q').value = '';
  document.querySelectorAll('.toolbar .toggle').forEach(t => t.setAttribute('aria-pressed', 'false'));
  segRoot.querySelectorAll('button').forEach(x => x.setAttribute('aria-pressed', String(x.dataset.r === '')));
  applyFilter();
}
$('#q').addEventListener('input', e => { filt.q = e.target.value.trim(); applyFilter(); });
for (const [id, key] of [['#f-crit', 'crit'], ['#f-gap', 'gap'], ['#f-todo', 'todo']]) {
  $(id).addEventListener('click', e => { filt[key] = !filt[key]; e.currentTarget.setAttribute('aria-pressed', String(filt[key])); applyFilter(); });
}
segRoot.addEventListener('click', e => {
  const b = e.target.closest('button'); if (!b) return;
  filt.root = b.dataset.r;
  segRoot.querySelectorAll('button').forEach(x => x.setAttribute('aria-pressed', String(x === b)));
  applyFilter();
});
$('#expand').addEventListener('click', () => $('#tree').querySelectorAll('details').forEach(d => { if (!d.hidden) d.open = true; }));
$('#collapse').addEventListener('click', () => $('#tree').querySelectorAll('details').forEach(d => { if (d !== rootSpec) d.open = false; }));
const smooth = () => matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth';
function openAncestors(d) { for (let p = d; p; p = p.parentElement) if (p.tagName === 'DETAILS') p.open = true; }
function revealInOutline(f) {
  setTab('outline');
  const d = factEls.get(f.key);
  if (d.hidden) clearFilters();
  openAncestors(d);
  d.scrollIntoView({ block: 'center', behavior: smooth() });
  d.classList.remove('flash'); void d.offsetWidth; d.classList.add('flash');
}
function revealSpec(spec) {
  setTab('outline');
  const d = specEls.get(spec.id);
  if (d.hidden) clearFilters();
  openAncestors(d);
  d.scrollIntoView({ block: 'start', behavior: smooth() });
}

/* ---------- graph (no library: a small force layout, run once to rest) ---------- */
const graph = (() => {
  const nodes = specs.map((s, i) => {
    const n = factsOf(s.id).length;
    const a = i * 2.39996, r0 = 40 * Math.sqrt(i + 0.5);
    return { id: s.id, spec: s, facts: factsOf(s.id), r: 16 + Math.sqrt(n) * 3, x: r0 * Math.cos(a), y: r0 * Math.sin(a), vx: 0, vy: 0 };
  });
  const byId = new Map(nodes.map(n => [n.id, n]));
  const links = [];
  for (const s of specs) if (s.parent) links.push({ a: s.parent, b: s.id, kind: 'struct', label: s.join });
  const rel = new Map();
  for (const f of facts) for (const r of f.out) {
    if (r.fact.spec === f.spec) continue;
    const [a, b] = [f.spec, r.fact.spec].sort();
    if (!rel.has(a + '~' + b)) rel.set(a + '~' + b, { a, b, kind: 'relates', pairs: [] });
    rel.get(a + '~' + b).pairs.push({ from: f, to: r.fact, relation: r.relation });
  }
  links.push(...rel.values());
  const adj = new Map(nodes.map(n => [n.id, new Set([n.id])]));
  for (const l of links) { adj.get(l.a).add(l.b); adj.get(l.b).add(l.a); }

  function layout() {
    let alpha = 1;
    for (let step = 0; step < 600; step++, alpha *= 0.991) {
      for (let i = 0; i < nodes.length; i++) for (let j = i + 1; j < nodes.length; j++) {
        const p = nodes[i], q = nodes[j];
        let dx = q.x - p.x, dy = q.y - p.y, d2 = dx * dx + dy * dy || 0.01;
        const d = Math.sqrt(d2), f = -1100 * alpha / d2;
        dx /= d; dy /= d;
        p.vx += dx * f; p.vy += dy * f; q.vx -= dx * f; q.vy -= dy * f;
        const min = p.r + q.r + 34;
        if (d < min) { const push = (min - d) / 2; p.x -= dx * push; p.y -= dy * push; q.x += dx * push; q.y += dy * push; }
      }
      for (const l of links) {
        const p = byId.get(l.a), q = byId.get(l.b);
        const want = l.kind === 'struct' ? 120 + p.r + q.r : 200, k = l.kind === 'struct' ? 0.06 : 0.008;
        const dx = q.x - p.x, dy = q.y - p.y, d = Math.hypot(dx, dy) || 0.01, f = (d - want) * k * alpha;
        p.vx += dx / d * f; p.vy += dy / d * f; q.vx -= dx / d * f; q.vy -= dy / d * f;
      }
      for (const n of nodes) {
        n.vx -= n.x * 0.004 * alpha; n.vy -= n.y * 0.004 * alpha;
        n.x += n.vx; n.y += n.vy; n.vx *= 0.6; n.vy *= 0.6;
      }
    }
  }

  const on = { struct: true, relates: true };
  for (const k of [...new Set(specs.map(s => kindClass(s.kind)))]) on['k:' + k] = true;
  let svg, root, view = { k: 1, x: 0, y: 0 }, built = false, marked = null, gNodes = new Map(), gLinks = [];
  const apply = () => root.setAttribute('transform', `translate(${view.x},${view.y}) scale(${view.k})`);
  function curve(l) {
    const p = byId.get(l.a), q = byId.get(l.b);
    if (l.kind === 'struct') return `M${p.x},${p.y}L${q.x},${q.y}`;
    const mx = (p.x + q.x) / 2, my = (p.y + q.y) / 2, dx = q.x - p.x, dy = q.y - p.y;
    return `M${p.x},${p.y}Q${mx - dy * 0.18},${my + dx * 0.18} ${q.x},${q.y}`;
  }
  function arc(r0, r1, a0, a1) {
    if (a1 - a0 >= Math.PI * 2 - 1e-6) {
      return `M${r1},0A${r1},${r1} 0 1,1 ${-r1},0A${r1},${r1} 0 1,1 ${r1},0M${r0},0A${r0},${r0} 0 1,0 ${-r0},0A${r0},${r0} 0 1,0 ${r0},0Z`;
    }
    const p = (r, a) => `${r * Math.sin(a)},${-r * Math.cos(a)}`, big = a1 - a0 > Math.PI ? 1 : 0;
    return `M${p(r1, a0)}A${r1},${r1} 0 ${big},1 ${p(r1, a1)}L${p(r0, a1)}A${r0},${r0} 0 ${big},0 ${p(r0, a0)}Z`;
  }
  function build() {
    layout();
    svg = $('#graph-svg');
    root = sv('g');
    svg.append(root);
    const lg = sv('g'), hg = sv('g'), ng = sv('g');
    root.append(lg, hg, ng);
    for (const l of links) {
      const p = sv('path', { d: curve(l), class: l.kind === 'struct' ? 'g-struct' : 'g-relates' });
      if (l.kind === 'relates') p.setAttribute('stroke-width', (1.2 + Math.sqrt(l.pairs.length) * 1.4).toFixed(2));
      lg.append(p);
      let hit = null;
      if (l.kind === 'relates') {
        hit = sv('path', { d: curve(l), class: 'g-hit' });
        const by = {}; for (const x of l.pairs) by[x.relation] = (by[x.relation] || 0) + 1;
        hoverHelp(hit, `${l.a} ↔ ${l.b}: ` + Object.entries(by).map(([k, v]) => `${v} ${k}`).join(', '));
        hit.addEventListener('click', () => show({ type: 'edge', l }));
        hg.append(hit);
      }
      gLinks.push({ l, p, hit });
    }
    for (const n of nodes) {
      const g = sv('g', { class: 'g-spec', tabindex: '0', role: 'button', 'aria-label': n.spec.name });
      g.append(sv('circle', { class: 'halo', r: n.r + 11 }));
      const total = n.facts.length || 1;
      let a = 0;
      for (const v of ['PASS', 'GAP', 'FAIL', 'ADJUDICATE', 'UNVERIFIABLE', 'none']) {
        const k = n.facts.filter(f => verdictOf(f) === v).length;
        if (!k) continue;
        const b = a + (Math.PI * 2) * k / total;
        g.append(sv('path', { class: 'arc-' + (v === 'none' ? 'unverified' : v), d: arc(n.r + 1.5, n.r + 6, a, b) }));
        a = b;
      }
      g.append(sv('circle', { class: 'core fill-' + kindClass(n.spec.kind), r: n.r }));
      const t = sv('text', { class: 'n', 'text-anchor': 'middle', dy: '0.35em' }); t.textContent = n.facts.length; g.append(t);
      const lb = sv('text', { class: 'lbl', 'text-anchor': 'middle', dy: n.r + 22 }); lb.textContent = n.spec.id; g.append(lb);
      g.setAttribute('transform', `translate(${n.x},${n.y})`);
      const verified = n.facts.filter(f => f.verdict === 'PASS').length;
      g.addEventListener('mouseenter', e => { focus(n.id); showTip(e, `${n.spec.name} · ${n.facts.length} facts, ${verified} verified`); });
      g.addEventListener('mousemove', moveTip);
      g.addEventListener('mouseleave', () => { hideTip(); focus(marked); });
      g.addEventListener('keydown', e => { if (e.key === 'Enter') selectSpec(n.spec); });
      ng.append(g);
      gNodes.set(n.id, g);
      n.g = g;
    }
    /* Pointer: drag a node to move it, drag the background to pan; wheel zooms at the cursor. */
    let drag = null;
    const toGraph = e => { const b = svg.getBoundingClientRect(); return [(e.clientX - b.left - view.x) / view.k, (e.clientY - b.top - view.y) / view.k]; };
    svg.addEventListener('pointerdown', e => {
      const g = e.target.closest('.g-spec');
      const n = g && nodes.find(x => x.g === g);
      drag = { n, sx: e.clientX, sy: e.clientY, vx: view.x, vy: view.y, moved: false, id: e.pointerId };
    });
    svg.addEventListener('pointermove', e => {
      if (!drag) return;
      if (!drag.moved && Math.abs(e.clientX - drag.sx) + Math.abs(e.clientY - drag.sy) > 3) {
        drag.moved = true;
        svg.setPointerCapture(drag.id);
      }
      if (!drag.moved) return;
      if (drag.n) {
        [drag.n.x, drag.n.y] = toGraph(e);
        drag.n.g.setAttribute('transform', `translate(${drag.n.x},${drag.n.y})`);
        for (const x of gLinks) if (x.l.a === drag.n.id || x.l.b === drag.n.id) { x.p.setAttribute('d', curve(x.l)); if (x.hit) x.hit.setAttribute('d', curve(x.l)); }
      } else { view.x = drag.vx + e.clientX - drag.sx; view.y = drag.vy + e.clientY - drag.sy; apply(); }
    });
    svg.addEventListener('pointerup', e => {
      if (drag && !drag.moved) {
        if (drag.n) selectSpec(drag.n.spec);
        else if (!e.target.closest('.g-hit')) focus(null);
      }
      drag = null;
    });
    svg.addEventListener('pointercancel', () => { drag = null; });
    svg.addEventListener('wheel', e => {
      e.preventDefault();
      const b = svg.getBoundingClientRect(), mx = e.clientX - b.left, my = e.clientY - b.top;
      const k = Math.max(0.25, Math.min(4, view.k * Math.exp(-e.deltaY * 0.0015)));
      view.x = mx - (mx - view.x) * k / view.k; view.y = my - (my - view.y) * k / view.k; view.k = k;
      apply();
    }, { passive: false });
    built = true;
    applyFilters();
    if (marked) markSpec(marked);
  }
  function fit() {
    const box = svg.getBoundingClientRect();
    const vis = nodes.filter(n => on['k:' + kindClass(n.spec.kind)]);
    if (!box.width || !vis.length) return;
    const x0 = Math.min(...vis.map(n => n.x - n.r)) - 70, x1 = Math.max(...vis.map(n => n.x + n.r)) + 70;
    const y0 = Math.min(...vis.map(n => n.y - n.r)) - 50, y1 = Math.max(...vis.map(n => n.y + n.r)) + 60;
    const k = Math.min(box.width / (x1 - x0), (box.height - 120) / (y1 - y0), 1.8);
    view = { k, x: box.width / 2 - k * (x0 + x1) / 2, y: box.height / 2 - k * (y0 + y1) / 2 };
    apply();
  }
  function focus(id) {
    if (!built) return;
    svg.classList.toggle('focus', !!id);
    const near = id ? adj.get(id) : new Set();
    for (const [nid, g] of gNodes) g.classList.toggle('hi', near.has(nid));
    for (const x of gLinks) x.p.classList.toggle('hi', !!id && (x.l.a === id || x.l.b === id));
  }
  function markSpec(id) {
    marked = id;
    if (!built) return;
    for (const [nid, g] of gNodes) g.classList.toggle('sel', nid === id);
    focus(id);
  }
  function applyFilters() {
    if (!built) return;
    const vis = id => on['k:' + kindClass(specById.get(id).kind)];
    for (const [nid, g] of gNodes) g.style.display = vis(nid) ? '' : 'none';
    for (const x of gLinks) {
      const shown = vis(x.l.a) && vis(x.l.b) && on[x.l.kind];
      x.p.style.display = shown ? '' : 'none';
      if (x.hit) x.hit.style.display = shown ? '' : 'none';
    }
  }
  const kinds = $('#g-kinds'), legend = $('#g-legend-kinds');
  for (const k of [...new Set(specs.map(s => kindClass(s.kind)))]) {
    const label = k === 'soc' ? 'SoC' : k === 'ip' ? 'IP' : k[0].toUpperCase() + k.slice(1);
    const b = el('button', 'toggle', label);
    b.dataset.f = 'k:' + k; b.setAttribute('aria-pressed', 'true'); kinds.append(b);
    const sw = el('span', 'sw'); const i = el('i'); i.style.background = `var(--k-${k})`; sw.append(i, label); legend.append(sw);
  }
  $('#g-filters').addEventListener('click', e => {
    const b = e.target.closest('button[data-f]'); if (!b) return;
    on[b.dataset.f] = !on[b.dataset.f];
    b.setAttribute('aria-pressed', String(on[b.dataset.f]));
    applyFilters();
  });
  $('#g-fit').addEventListener('click', fit);
  new ResizeObserver(() => { if (built && !views.graph.hidden) fit(); }).observe(views.graph);
  return {
    ensure() { if (!built) build(); requestAnimationFrame(fit); },
    focusSpec(id) {
      if (!built) build();
      const n = byId.get(id), box = svg.getBoundingClientRect();
      view = { k: 1.3, x: box.width / 2 - 1.3 * n.x, y: box.height / 2 - 1.3 * n.y };
      apply();
      markSpec(id);
    },
    markSpec,
    neighbors(id) {
      const out = [];
      for (const l of links) {
        if (l.a !== id && l.b !== id) continue;
        const other = specById.get(l.a === id ? l.b : l.a);
        if (l.kind === 'struct') out.push({ spec: other, label: l.a === id ? l.label + ' →' : '← ' + l.label });
        else out.push({ spec: other, label: 'fact links', link: l });
      }
      return out;
    },
  };
})();

/* ---------- memory map ---------- */
(() => {
  const host = $('#mm');
  const rows = DATA.memory_map;
  const note = el('div', 'note');
  if (!rows.length) {
    note.append(el('b', null, 'No instance in these specs records a base address.'));
    host.append(note);
    return;
  }
  const inst = rows.map(r => instByKey.get(r.key));
  const classes = [...new Set(inst.flatMap(i => i.classes))];
  const n1 = el('div');
  n1.append(el('b', null, rows.length + ' instance' + (rows.length > 1 ? 's' : '') + ' with a recorded base address. '),
    'Their evidence is ' + (classes.join(', ') || 'not cited') + ', from ' + [...new Set(inst.map(i => shortRoot(i.root)))].join(', ') +
    '. Specs record base addresses, not window sizes, so rows are drawn at equal height. High addresses are at the top, as in a datasheet.');
  note.append(n1);
  host.append(note);
  const mm = el('div', 'mm');
  rows.forEach((row, idx) => {
    const i = instByKey.get(row.key);
    mm.append(el('div', 'addr', i.reg));
    const b = el('div', 'blk' + (idx === 0 ? ' first' : ''));
    b.tabIndex = 0;
    const left = el('div');
    left.append(el('div', 'bn', i.name), el('div', 'ipn', [i.ip, i.peripheral].filter(Boolean).join(' / ') + ' · ' + i.spec));
    const side = el('div', 'side');
    if (i.irq) side.append(el('span', 'irq', i.irq + (i.trigger ? ' · ' + i.trigger : '')));
    if (i.clocks.length) side.append(el('span', 'clk', i.clocks.join(' · ')));
    b.append(left, side);
    const cites = row.cites.map(k => factByKey.get(k)).filter(Boolean);
    const ipSpec = specById.get(i.ip);
    const periphSpec = specById.get(i.peripheral);
    const m = el('div', 'mentions');
    for (const [label, target] of [['IP spec: ', ipSpec], ['Peripheral spec: ', periphSpec]]) {
      if (!target) continue;
      const go = el('button', 'link', label + target.name);
      go.addEventListener('click', ev => { ev.stopPropagation(); selectSpec(target); });
      m.append(go);
    }
    if (cites.length) {
      m.append(el('span', 'lbl', cites.length + (cites.length > 1 ? ' facts cite' : ' fact cites') + ' this address:'));
      for (const f of cites.slice(0, 6)) m.append(factLink(f));
    }
    if (m.childNodes.length) b.append(m);
    const open = () => {
      if (cites[0]) select(cites[0]);
      else if (ipSpec || periphSpec) selectSpec(ipSpec || periphSpec);
    };
    b.addEventListener('click', open);
    b.addEventListener('keydown', e => { if (e.key === 'Enter') open(); });
    mm.append(b);
    if (row.gap) {
      mm.append(el('div', 'addr', ''));
      const g = el('div', 'gaprow', row.gap + ' to the next recorded base');
      g.style.height = Math.round(18 + 10 * row.gap_scale) + 'px';
      mm.append(g);
    }
  });
  host.append(mm);
})();

/* ---------- coverage ---------- */
(() => {
  const host = $('#cov');
  const lg = el('div', 'cov-legend');
  const LEGEND = [
    ['PASS', 'verified', count(f => f.verdict === 'PASS'), HELP.PASS],
    ['GAP', 'gap', count(f => f.verdict === 'GAP'), HELP.GAP],
    ['FAIL', 'fail', count(f => f.verdict === 'FAIL'), HELP.FAIL],
    ['ADJUDICATE', 'adjudicate', count(f => f.verdict === 'ADJUDICATE'), HELP.ADJUDICATE],
    ['UNVERIFIABLE', 'unverifiable', count(f => f.verdict === 'UNVERIFIABLE'), HELP.UNVERIFIABLE],
    ['', 'no verdict', count(f => !f.verdict), HELP.none],
    ['PASS critical', 'critical (ringed)', count(f => f.critical), HELP.critical],
    ['PASS open', 'open check (hollow)', count(f => f.todo), HELP.open],
  ];
  for (const [cls, label, n, help] of LEGEND) {
    if (!n && ['ADJUDICATE', 'UNVERIFIABLE'].includes(cls)) continue;
    const w = el('span', 'sw help'); w.append(el('span', 'sq ' + cls), label + ' ' + n);
    w.tabIndex = 0; hoverHelp(w, help);
    w.addEventListener('focus', () => { const r = w.getBoundingClientRect(); showTip({ clientX: r.left, clientY: r.bottom }, help); });
    w.addEventListener('blur', hideTip);
    lg.append(w);
  }
  host.append(lg);
  const order = [];
  for (const s of specs) for (const sec of s.sections) if (!order.includes(sec)) order.push(sec);
  const secs = [...new Set(facts.map(f => f.section))].sort((a, b) => {
    const ra = order.indexOf(a), rb = order.indexOf(b);
    return (ra < 0 ? 99 : ra) - (rb < 0 ? 99 : rb);
  });
  const EV = ['databook', 'standard', 'doc', 'DT', 'src', 'rtl', 'hardware', 'emulated', 'press', 'inference'];
  const EVC = { databook: 'var(--k-soc)', standard: 'var(--k-ip)', doc: 'var(--k-board)', DT: 'var(--pass)', src: 'var(--k-peripheral)', rtl: 'var(--k-chip)', inference: 'var(--none)' };
  const wrap = el('div', 'cov-scroll');
  const t = el('table', 'cov');
  const hr = el('tr'); hr.append(el('th', null, 'Spec'));
  for (const s of secs) { const h = el('th', null, humanSec(s) + ' '); h.append(el('span', 'count', String(count(f => f.section === s)))); hr.append(h); }
  hr.append(el('th', null, 'Evidence mix'));
  const th = el('thead'); th.append(hr); t.append(th);
  const tb = el('tbody');
  for (const spec of specs) {
    const tr = el('tr');
    const h = el('th'); h.append(el('span', 'kind ' + kindClass(spec.kind), spec.kind), ' ', spec.name.length > 46 ? spec.id : spec.name, el('span', 'sid', spec.id));
    tr.append(h);
    const mine = factsOf(spec.id);
    for (const s of secs) {
      const td = el('td'); const c = el('div', 'cells');
      for (const f of mine.filter(x => x.section === s)) {
        const b = el('button', 'sq ' + (f.verdict || '') + (f.critical ? ' critical' : '') + (f.todo ? ' open' : ''));
        b.setAttribute('aria-label', f.title);
        hoverHelp(b, f.title + ' · ' + WORD[verdictOf(f)] + (isStale(f) ? ' (' + f.freshness + ')' : '') + (f.todo ? ' · open ' + f.todo.check + ' check' : ''));
        b.addEventListener('click', () => select(f));
        c.append(b);
      }
      td.append(c); tr.append(td);
    }
    const ev = el('td'); const bar = el('div', 'evbar');
    const all = mine.flatMap(f => f.sources.map(x => x.class));
    const parts = [];
    for (const k of [...EV, ...new Set(all.filter(x => !EV.includes(x)))]) {
      const n = all.filter(x => x === k).length; if (!n) continue;
      const i = el('i'); i.style.width = (100 * n / all.length) + '%'; i.style.background = EVC[k] || 'var(--k-other)'; bar.append(i);
      parts.push(k + ' ' + n);
    }
    ev.append(bar, el('div', 'count', parts.join(' · ')));
    tr.append(ev);
    tb.append(tr);
  }
  t.append(tb); wrap.append(t); host.append(wrap);
  for (const x of DATA.indexes) {
    const covered = x.sections.filter(s => s.facts.length).length;
    host.append(el('h3', 'cov-h', 'Document index · ' + x.document + ' · ' + shortRoot(x.root)));
    host.append(el('div', 'count', covered + ' of ' + x.sections.length + ' sections cited by a fact'));
    const w = el('div', 'cov-scroll'); const it = el('table', 'cov');
    const h = el('tr'); for (const k of ['Section', 'Title', x.source === 'pdf' ? 'Pages' : 'Lines', 'Facts']) h.append(el('th', null, k));
    const ih = el('thead'); ih.append(h); it.append(ih);
    const ib = el('tbody');
    for (const s of x.sections) {
      const tr = el('tr', 'ledger ' + (s.facts.length ? 'spec' : 'excluded'));
      const fc = el('td');
      for (const k of s.facts) { const f = factByKey.get(k); fc.append(f ? factLink(f) : el('span', null, k)); }
      if (!s.facts.length) fc.textContent = 'none';
      tr.append(el('td', null, s.number || ''), el('td', null, '\u00a0'.repeat(2 * (s.level - 1)) + s.title),
        el('td', null, (s.pages || s.lines).join('–')), fc);
      ib.append(tr);
    }
    it.append(ib); w.append(it); host.append(w);
  }
  for (const c of DATA.corpus) {
    host.append(el('h3', 'cov-h', 'Corpus ledger · ' + shortRoot(c.root)));
    for (const group of ['documents', 'blocks']) {
      const n = c[group].counts;
      host.append(el('div', 'count', group + ': ' + n.spec + ' specified · ' + n.planned + ' planned · ' + n.excluded + ' excluded' + (n.unresolved ? ' · ' + n.unresolved + ' unresolved' : '')));
      if (!c[group].rows.length) continue;
      const w = el('div', 'cov-scroll'); const lt = el('table', 'cov');
      const h = el('tr'); for (const k of ['Name', 'Subsystem', 'Disposition']) h.append(el('th', null, k));
      const lh = el('thead'); lh.append(h); lt.append(lh);
      const lb = el('tbody');
      for (const r of c[group].rows) {
        const tr = el('tr', 'ledger ' + r.state);
        tr.append(el('td', null, r.name), el('td', null, r.subsystem), el('td', null, r.disposition));
        lb.append(tr);
      }
      lt.append(lb); w.append(lt); host.append(w);
    }
  }
})();

/* ---------- open items ---------- */
(() => {
  const host = $('#iss');
  const fails = facts.filter(f => ['FAIL', 'ADJUDICATE'].includes(f.verdict));
  const gaps = facts.filter(f => f.verdict === 'GAP');
  const stale = facts.filter(isStale);
  const nov = facts.filter(f => !f.verdict || f.verdict === 'UNVERIFIABLE');
  const todo = facts.filter(f => (f.todo || f.row_todos.length) && f.verdict !== 'GAP');
  const checksOf = f => (f.todo ? [f.todo] : []).concat(f.row_todos);
  const bench = todo.filter(f => checksOf(f).some(t => t.check === 'hardware')), reading = todo.filter(f => checksOf(f).some(t => t.check !== 'hardware'));
  const order = list => list.slice().sort((a, b) => (b.critical - a.critical) || a.spec.localeCompare(b.spec));
  const cards = el('div', 'icards');
  const card = (n, label, cls, help, target) => {
    const c = el('button', 'icard ' + cls);
    c.append(el('b', null, String(n)), el('span', 'il', label), el('span', 'ih', help));
    c.addEventListener('click', () => $('#' + target).scrollIntoView({ block: 'start', behavior: smooth() }));
    cards.append(c);
  };
  card(fails.length, 'failed or disputed', fails.length ? 'bad' : 'good', fails.length ? 'Claims that disagree with their evidence, or readings that disagree. Fix these first.' : 'No claim disagrees with its evidence.', 'iss-fail');
  card(gaps.length, 'gaps', gaps.length ? 'warn' : 'good', 'Facts no source read so far states. Each names the check that would settle it.', 'iss-gap');
  card(stale.length, 'stale verdicts', stale.length ? 'warn' : 'good', 'Facts changed since their verdict, so it no longer counts.', 'iss-stale');
  card(bench.length, 'bench checks', '', 'Verified facts that still need a measurement on a real board.', 'iss-bench');
  card(reading.length, 'reading checks', '', 'Verified facts with a document or source passage still to read.', 'iss-reading');
  card(nov.length, 'without a verdict', nov.length ? 'warn' : 'good', 'Facts no verification record covers, or whose evidence could not be read.', 'iss-nov');
  host.append(cards);
  const section = (id, title, help, list, empty) => {
    const s = el('section', 'isec'); s.id = id;
    const h = el('h2', null, title + ' '); h.append(el('span', 'count', String(list.length)));
    s.append(h, el('p', 'ihelp', help));
    if (!list.length) { s.append(el('p', 'empty', empty)); host.append(s); return; }
    const ul = el('ul', 'ilist');
    for (const f of order(list)) {
      const li = el('li');
      const head = el('div', 'row');
      head.append(pill(f));
      if (isStale(f)) head.append(el('span', 'stale', f.freshness));
      if (f.critical) head.append(el('span', 'crit', '◆'));
      head.append(factLink(f), el('span', 'idline', f.spec));
      li.append(head);
      if (f.todo) { const t = el('div', 'todo'); t.append(el('b', null, f.todo.check || 'check'), f.todo.text); li.append(t); }
      for (const r of f.row_todos) { const t = el('div', 'todo'); t.append(el('b', null, r.check), r.fact + ' (' + r.kind + '): ' + r.text); li.append(t); }
      ul.append(li);
    }
    s.append(ul); host.append(s);
  };
  section('iss-fail', 'Failed or disputed verifications', HELP.FAIL + ' ' + HELP.ADJUDICATE, fails, 'None. Every verified claim on this page matches its cited evidence.');
  section('iss-gap', 'Gaps', HELP.GAP + ' Critical gaps are listed first: they block a first bring-up until settled.', gaps, 'None.');
  section('iss-stale', 'Stale verdicts', HELP.stale, stale, 'None. Every verdict was recorded against the current text.');
  section('iss-bench', 'Bench checks on verified facts', 'The evidence supports these claims, but the author recorded a measurement on real hardware that would confirm them.', bench, 'None.');
  section('iss-reading', 'Reading checks on verified facts', 'A document or source passage is still to be read to close these.', reading, 'None.');
  section('iss-nov', 'Facts without a verdict', HELP.none + ' ' + HELP.UNVERIFIABLE, nov, 'None. Every fact has a verification record.');
  const lim = el('section', 'isec');
  lim.append(el('h2', null, 'Limits of this view'));
  const ul = el('ul', 'ilimits');
  const crit = count(f => f.critical);
  const lines = [
    'The memory map shows base addresses only. Specs record no window sizes, so blocks are drawn at equal height.',
    'A verified fact means its evidence was read and agrees. It does not mean the claim was tested on a board.',
  ];
  if (crit > facts.length / 2) lines.push(`${crit} of ${facts.length} facts are marked critical, so the critical marker separates little.`);
  if (DATA.outside_links) lines.push(`${DATA.outside_links} fact links point at specs outside this page and are not drawn.`);
  if (DATA.row_links) lines.push(`${DATA.row_links} fact links point at instance rows in the memory map and are not drawn in the graph.`);
  if (DATA.unplaced.length) {
    const byKind = new Map();
    for (const u of DATA.unplaced) {
      if (!byKind.has(u.kind)) byKind.set(u.kind, []);
      byKind.get(u.kind).push(`${u.id} (${u.facts} fact${u.facts === 1 ? '' : 's'})`);
    }
    const groups = [...byKind].map(([k, ids]) => `${k}: ${ids.join(', ')}`).join('; ');
    const n = DATA.unplaced.length;
    lines.push(`${n} spec${n === 1 ? '' : 's'} in the rendered roots ${n === 1 ? 'is' : 'are'} not shown on this page: ${groups}.`);
  }
  for (const t of lines) ul.append(el('li', null, t));
  lim.append(ul); host.append(lim);
})();

/* ---------- about ---------- */
(() => {
  const dl = $('#about-roots');
  for (const r of DATA.roots) {
    dl.append(el('dt', 'mono', r.name),
      el('dd', null, [r.license || 'license not stated', r.context ? 'context root' : '', r.commit ? 'commit ' + r.commit.slice(0, 12) : 'commit not given'].filter(Boolean).join(' · ')));
  }
  $('#about-snap').textContent = 'Generated by spec.py render --format atlas. Do not edit. hwspecs ' + (DATA.tool_commit ? DATA.tool_commit.slice(0, 12) : 'commit unavailable') + '.';
})();

/* ---------- boot ---------- */
panelEmpty();
{
  const pref = store('atlas-panel');
  setPanel(pref ? pref === '1' : !narrow(), false);
}
const hash = location.hash.slice(1);
const known = name => Object.prototype.hasOwnProperty.call(views, name);
const saved = store('atlas-tab');
const start = known(hash) ? hash : known(saved) ? saved : 'outline';
setTab(start);
})();
