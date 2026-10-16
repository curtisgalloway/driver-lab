# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Board atlas: one interactive page for a board (or any spec) and the specs around it.

`spec.py render --format atlas --spec ID` selects the spec, the closure of its `parts`, the
peripheral specs whose `describes` names one of those, every spec one fact link (`relates` or an
inference premise) away from the spec or a part, and the IP and peripheral specs named by the
instances of all of those, then embeds them as one JSON document in a page with outline, graph,
memory map, coverage, open-items and about views. Specs in the rendered roots it does not place
are listed, so none is left out silently. The page loads no script from elsewhere. Its *_html fields are render_html.author()
output (the fixed-element renderer); every other value is a string the page script inserts
with textContent.
"""

from __future__ import annotations

import math
from pathlib import Path
import re

import explorer
import render_html
import render_md
import speccheck

HERE = Path(__file__).resolve().parent
HEX = re.compile(r'0x[0-9a-fA-F]+')


def _base(spec_id, files):
    """The spec's own (non-overlay) file among the files being rendered, or None.

    Never from outside them: without --merged a context root's file has not been through
    refuse_unsafe_fields and that root may not check clean."""
    for f in files:
        if f.spec_id == spec_id and not f.is_overlay:
            return f
    return None


def _address(value):
    """An instance's reg as an integer, or None when absent or not a single number."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and HEX.fullmatch(value.strip()):
        return int(value.strip(), 16)
    return None


def _size(n):
    for unit, shift in (('GiB', 30), ('MiB', 20), ('KiB', 10)):
        if n >= 1 << shift:
            v = n / (1 << shift)
            return (f'{v:.0f}' if v == int(v) else f'{v:.1f}') + ' ' + unit
    return f'{n} bytes'


def select(checker, spec_id, merged=False):
    """Spec ids to show, each mapped to (parent id, how it joins the parent), in a stable order."""
    files = [f for f in checker.files if merged or not f.root.context]
    present = {f.spec_id for f in files}
    if spec_id not in present:
        raise speccheck.UsageError(f'no spec {spec_id!r} in the rendered roots')
    placed = {spec_id: (None, '')}

    def add(child, parent, how):
        if child in present and child not in placed:
            placed[child] = (parent, how)
            return True
        return False

    queue = [spec_id]
    while queue:
        sid = queue.pop(0)
        base = _base(sid, files)
        for part in (base.data.get('parts', []) if base else []):
            if add(part, sid, 'parts'):
                queue.append(part)
    core = list(placed)

    def add_ips(ids):
        """The ip and peripheral specs the instances of these specs name, overlays included."""
        for sid in ids:
            for f in files:
                if f.spec_id == sid:
                    for row in f.data.get('instances', []):
                        add(row.get('ip'), sid, 'ip')
                        add(row.get('peripheral'), sid, 'programming')

    add_ips(core)
    # A peripheral spec joins the first core spec it describes. It stays out of core, so the
    # fact-link pass below stays one hop from the spec and its parts.
    for f in files:
        if f.kind == 'peripheral' and not f.is_overlay:
            for target in f.data.get('describes', []):
                if target in core and add(f.spec_id, target, 'programming'):
                    break
    counts = {}
    for f in files:
        for rec in f.records.values():
            if rec.path[0] != 'facts' or rec.parent is not None:
                continue
            for _, ref, _ in speccheck.references(rec.data, rec.path):
                target, why = checker.resolve(f, ref)
                if why or target is None:
                    continue
                a, b = f.spec_id, target.file.spec_id
                for inside, outside in ((a, b), (b, a)):
                    if inside in core and outside not in placed and outside in present:
                        counts.setdefault(outside, {}).setdefault(inside, 0)
                        counts[outside][inside] += 1
    linked = []
    for outside in sorted(counts):
        parent = max(sorted(counts[outside]), key=lambda s: counts[outside][s])
        base = _base(outside, files)
        kind = base.kind if base else ''
        add(outside, parent, 'programming' if kind == 'peripheral' else 'related')
        linked.append(outside)
    add_ips(linked)
    return placed, files


def data(checker, spec_id, *, merged=False, source_commit=None, tool_commit=None):
    placed, files = select(checker, spec_id, merged)
    chosen = [f for f in files if f.spec_id in placed]
    groups = [[f for f in chosen if f.spec_id == sid] for sid in placed]
    commits = render_md.source_commits(groups, source_commit)
    for f in chosen:
        if f.root.context and f.root.untrusted:
            raise ValueError('cannot render merged input: context root does not check clean')
        render_html.refuse_unsafe_fields(f)
    status = {entry['file']: {r['key']: r for r in entry['rows']} for entry in checker.status}
    roots, specs, facts, instances = {}, [], [], []
    for sid, (parent, how) in placed.items():
        group = sorted((f for f in chosen if f.spec_id == sid),
                       key=lambda f: (f.is_overlay, f.root.rank, f.root.order, str(f.path)))
        base = _base(sid, group)
        bd = base.data if base else {}
        specs.append({
            'id': sid, 'name': str(bd.get('name', sid)), 'kind': base.kind if base else 'overlay',
            'parent': parent, 'join': how, 'roots': [f.root.label for f in group],
            'orientation_html': render_html.author(bd['orientation']) if 'orientation' in bd else '',
            'sections': list(speccheck.SECTIONS.get(base.kind if base else '', ())),
        })
        for f in group:
            root = f.root
            if root.label not in roots:
                marker = root.marker.data if root.marker is not None else {}
                roots[root.label] = {
                    'name': root.label, 'layer': root.layer or '', 'context': root.context,
                    'license': str(marker.get('license', '')),
                    'commit': commits.get(root.given.absolute(), '')}
            rows = status.get(f, {})
            for rec in f.records.values():
                if rec.parent is not None:
                    continue
                row = rows.get(rec.id, {})
                verdict = (f.verdicts.get(rec.id, (None, None))[0] or {})
                common = {
                    'key': rec.full, 'spec': sid, 'id': rec.id, 'root': root.label,
                    'verdict': row.get('verdict') or '', 'freshness': row.get('status') or '',
                    'verifier': str(verdict.get('verifier', '')), 'date': str(verdict.get('date', '')),
                }
                if rec.path[0] == 'facts':
                    facts.append(_fact(checker, f, rec, common))
                elif rec.path[0] == 'instances':
                    instances.append(_instance(rec, common))
    known = {x['key'] for x in facts}
    row_links = 0
    for x in facts:
        kept = []
        for r in x['relates']:
            row, spec = r.pop('row'), r.pop('spec')
            if r['to'] in known:
                kept.append(r)
            elif row and spec in placed:
                row_links += 1  # an instance or variant row of a spec on this page
            else:
                x['outside'] += 1
        x['relates'] = kept
    return {
        'focus': spec_id, 'specs': specs, 'facts': facts, 'memory_map': _memory_map(instances, facts),
        'instances': instances, 'roots': list(roots.values()),
        'outside_links': sum(x.pop('outside') for x in facts), 'row_links': row_links,
        'unplaced': _unplaced(checker, placed), 'tool_commit': tool_commit or '',
    }


def _unplaced(checker, placed):
    """Specs in the rendered (non-context) roots that the page does not show, by kind then id,
    each with its count of fact records."""
    out = {}
    for f in checker.files:
        if f.root.context or f.spec_id in placed:
            continue
        entry = out.setdefault(f.spec_id, {'id': f.spec_id, 'kind': '', 'facts': 0})
        if not f.is_overlay:
            entry['kind'] = f.kind
        entry['facts'] += sum(1 for r in f.records.values()
                              if r.path[0] == 'facts' and r.parent is None)
    for entry in out.values():
        entry['kind'] = entry['kind'] or 'overlay'
    return sorted(out.values(), key=lambda e: (e['kind'], e['id']))


def _fact(checker, file, rec, common):
    d = rec.data
    claim = render_html.author(d['claim']) if 'claim' in d else ''
    todo = d.get('todo') or {}
    relates, outside = [], 0
    for rel in d.get('relates', []):
        target, why = checker.resolve(file, rel['fact'])
        if why or target is None:
            outside += 1
            continue
        relates.append({'to': target.full, 'relation': str(rel.get('relation', '')),
                        'row': target.path[0] != 'facts', 'spec': target.file.spec_id})
    classes = []
    for s in d.get('support', []):
        if s.get('class') not in classes:
            classes.append(str(s.get('class')))
    sources = []
    for s in d.get('support', []):
        name = s.get('doc') or (s.get('anchors') or [{}])[0].get('repo') or s.get('title') or ''
        sources.append({'class': str(s.get('class', '')), 'source': str(name)})
    return dict(common, **{
        'section': str(d.get('section', 'facts')), 'title': str(d.get('title', rec.id)),
        'claim_html': claim, 'text': explorer.plain(claim), 'critical': d.get('critical') is True,
        'gap': not speccheck.has_support(d),
        'todo': {'check': str(todo.get('check', '')), 'text': str(todo.get('text', ''))} if todo else None,
        'classes': classes, 'sources': sources, 'relates': relates, 'outside': outside,
    })


def _instance(rec, common):
    d = rec.data
    irq = d.get('irq') if isinstance(d.get('irq'), dict) else {}
    base = _address(d.get('reg'))
    return dict(common, **{
        'name': str(d.get('name', rec.id)), 'ip': str(d.get('ip', '')),
        'peripheral': str(d.get('peripheral', '')),
        'reg': '' if base is None else f'0x{base:08X}', 'base': base,
        'irq': ' '.join(str(irq[k]) for k in ('kind', 'number') if k in irq),
        'trigger': str(irq.get('trigger', '')),
        'clocks': [str(c) for c in d.get('clocks', []) or []],
        'classes': list(dict.fromkeys(str(s.get('class')) for s in d.get('support', []))),
    })


def _memory_map(instances, facts):
    """Rows from high address to low, each with the facts that cite its base and the gap below."""
    rows = sorted((i for i in instances if i['base'] is not None), key=lambda i: -i['base'])
    texts = [(x['key'], x['text'].lower().replace('_', '')) for x in facts]
    out = []
    for n, i in enumerate(rows):
        needle = f"{i['base']:x}"
        # A small base (0x0, 0x100) is an offset that unrelated facts mention too.
        cites = ([k for k, t in texts if re.search(r'0x0*' + needle + r'\b', t)]
                 if i['base'] >= 0x10000 else [])
        below = rows[n + 1]['base'] if n + 1 < len(rows) else None
        gap = i['base'] - below if below is not None else 0
        out.append({'key': i['key'], 'cites': cites,
                    'gap': _size(gap) if gap > 0x10000 else '',
                    'gap_scale': round(math.log2(gap / 0x10000), 2) if gap > 0x10000 else 0})
    for i in instances:
        i.pop('base')
    return out


def page(checker, spec_id, *, merged=False, source_commit=None, tool_commit=None):
    payload = data(checker, spec_id, merged=merged, source_commit=source_commit,
                   tool_commit=tool_commit)
    focus = next(s for s in payload['specs'] if s['id'] == spec_id)
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            '<title>' + render_html.literal(focus['name'] + ' atlas') + '</title>\n'
            '<style>' + (HERE / 'atlas.css').read_text(encoding='utf-8') + '</style></head><body>\n' +
            (HERE / 'atlas.html').read_text(encoding='utf-8') +
            '<script type="application/json" id="spec-data">' + explorer._json_for_script(payload) +
            '</script>\n<script>' + (HERE / 'atlas.js').read_text(encoding='utf-8') + '</script>\n'
            '</body></html>\n')


def command(api, args):
    if not args.spec:
        raise api.Usage('--format atlas needs --spec ID: the board (or other spec) to center on')
    checker = api._run_check(args)
    findings = api._ordered(checker.findings)
    if any(f.level == 'error' for f in findings):
        return api.EXIT_INVALID, {'ok': False, 'html': None, 'findings': [f.as_dict() for f in findings],
                                  '_text': [str(f) for f in findings]}
    try:
        view = page(checker, args.spec, merged=args.merged, source_commit=args.source_commit,
                    tool_commit=args.tool_commit)
    except speccheck.UsageError as exc:
        raise api.Usage(str(exc)) from None
    except ValueError as exc:
        return api.EXIT_INVALID, {'ok': False, 'html': None, 'findings': [{'message': str(exc)}],
                                  '_text': [str(exc)]}
    return api.EXIT_OK, {'ok': True, 'html': view, 'findings': [f.as_dict() for f in findings],
                         '_text': [view.rstrip('\n')]}
