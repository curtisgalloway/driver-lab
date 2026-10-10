# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Static format 2 viewer. Author tokens cannot emit generated classes or identifiers."""

from __future__ import annotations

import hashlib
from html import escape
from pathlib import Path
import re
from urllib.parse import quote

import records
import render_md
import speccheck
import specmd
import textcheck

STYLE = Path(__file__).with_name("viewer.css")
CLASSES = {name: "class-" + name.lower() for name in (
    "databook", "standard", "doc", "rtl", "DT", "src", "hardware", "emulated",
    "press", "inference", "source-observed")}
VERDICTS = {v: "verdict-" + v.lower() for v in (
    "PASS", "FAIL", "UNVERIFIABLE", "GAP", "ADJUDICATE")}
FRESHNESS = {v: "status-" + v for v in (
    "current", "stale", "upstream-stale", "unverified", "unknown")}


def literal(value):
    return escape(render_md._value(value), quote=True)


def link(url, label):
    """Only the href of an allowed destination may come from input; no other attributes."""
    if not specmd.allowed_link(url):
        return label
    return '<a href="' + escape(url, quote=True) + '">' + label + '</a>'


def author(text):
    """Render only a fixed element set. Ignore ALL token attributes except checked URLs.

    No title, start number, language, class, id, style or other attribute is copied. Raw HTML
    is disabled during parsing and escaped defensively if a caller supplies an HTML token.
    Images become a destination link with their alternative text rendered independently.
    """
    tags = {"paragraph": "p", "blockquote": "blockquote", "bullet_list": "ul",
            "ordered_list": "ol", "list_item": "li", "em": "em", "strong": "strong"}

    def emit(tokens, allow_links=True):
        out = []
        for token in tokens:
            kind = token.type
            if kind == "inline":
                out.append(emit(token.children or [], allow_links))
            elif kind in ("text", "text_special", "html_inline", "html_block"):
                out.append(escape(token.content))
            elif kind == "code_inline":
                out.append('<code>' + escape(token.content) + '</code>')
            elif kind in ("fence", "code_block"):
                out.append('<pre><code>' + escape(token.content) + '</code></pre>')
            elif kind == "image":
                label = emit(token.children or [], False)
                # Images within an existing link keep that link's destination. Their nested
                # label cannot introduce another anchor: HTML forbids anchors inside anchors.
                out.append(link(token.attrGet("src") or "", label) if
                           allow_links and not any(links) else label)
            elif kind == "link_open":
                url = token.attrGet("href") or ""
                allowed = allow_links and not any(links) and specmd.allowed_link(url)
                out.append('<a href="' + escape(url, quote=True) + '">' if allowed else '<span>')
                links.append(allowed)
            elif kind == "link_close":
                # The parser balances links; use an independent stack rather than input attrs.
                out.append('</a>' if links.pop() else '</span>')
            elif kind == "softbreak":
                out.append('\n')
            elif kind == "hardbreak":
                out.append('<br>')
            elif kind == "hr":
                out.append('<hr>')
            elif kind.endswith(("_open", "_close")) and kind.rsplit("_", 1)[0] in tags:
                tag, edge = kind.rsplit("_", 1)
                out.append('<' + ('/' if edge == 'close' else '') + tags[tag] + '>')
            else:
                raise ValueError("unsupported viewer token: " + kind)
        return ''.join(out)

    links = []
    return emit(specmd.viewer_tokens(text))


def badge(kind, text):
    """Kind is chosen by generator code, never by author prose."""
    return '<span class="badge ' + kind + '">' + literal(text) + '</span>'


def field(label, text):
    return '<div class="author"><p>' + literal(label) + ' (author text)</p>' + author(text) + '</div>'


def citation(file, entry):
    bits = []
    if "doc" in entry:
        doc = file.documents[entry["doc"]][0]
        title = doc["title"] + (" (" + doc["revision"] + ")" if "revision" in doc else "")
        bits.append(link(doc["url"], literal(title)))
        bits.extend(literal(render_md._locator(at)) for at in entry.get("at", []))
    for anchor in entry.get("anchors", []):
        repo = file.repos[anchor["repo"]][0]
        text = f"{repo['name']}@{repo['commit']} ({repo['license']}) {anchor['path']}"
        if "lines" in anchor:
            text += " lines " + "–".join(map(str, anchor["lines"]))
        url = repo["url"].removesuffix(".git")
        if url.startswith("https://github.com/"):
            url += '/blob/' + repo['commit'] + '/' + quote(anchor['path'], safe='/')
            if "lines" in anchor:
                url += f"#L{anchor['lines'][0]}-L{anchor['lines'][1]}"
        bits.append(link(url, literal(text)))
        for key in ("symbol", "node", "search", "comment", "stale"):
            if key in anchor:
                bits.append(literal(key + ': ' + render_md._value(anchor[key])))
    skip = {"class", "doc", "at", "anchors", "note", "premises", "derivation"}
    bits.extend(literal(k + ': ' + render_md._value(v)) for k, v in entry.items() if k not in skip)
    return '; '.join(bits)


def support(checker, file, entries, notes):
    out = ['<ul>'] if entries else []
    for entry in entries:
        out.append('<li>' + badge(CLASSES.get(entry['class'], 'class-extension'), entry['class']))
        out.append(' ' + citation(file, entry))
        if entry['class'] == 'inference':
            out.append('<ul>')
            for premise in entry['premises']:
                out.append('<li>')
                if 'fact' in premise:
                    rec, why = checker.resolve(file, premise['fact'])
                    if why:
                        raise ValueError(why)
                    out.append(link('#' + quote(rec.full, safe=''), literal(rec.full)))
                    if 'uses' in premise:
                        out.append(': ' + literal(premise['uses']))
                elif 'states' in premise:
                    out.append('Stated premise (author text below)')
                    notes.append(('States', premise['states']))
                    out.append(support(checker, file, premise['support'], notes))
                else:
                    a = file.data['assumptions'][file.assumptions[premise['assumption']][1]]
                    out.append('Assumption ' + literal(a['id']) + ': ' + literal(a['text']))
                out.append('</li>')
            out.append('</ul><p>Derivation: ' + literal(entry['derivation']) + '</p>')
        if 'note' in entry:
            notes.append(('Support note', entry['note']))
        out.append('</li>')
    if entries:
        out.append('</ul>')
    return ''.join(out)


def verification(file, key, row, notes):
    """Complete parent and child record metadata, using fixed elements and escaped text."""
    out = []
    verdict = file.verdicts.get(key, (None, None))[0]
    if row['verdict']:
        text = row['verdict'] + ' ' + verdict['date'] + (' · carried' if row['carried'] else '')
        out.append(badge(VERDICTS[row['verdict']], text))
        out.append('<p>Verifier: ' + literal(verdict['verifier']) + '</p>')
        for reader in verdict.get('readers', []):
            out.append('<p>Reader: ' + literal(reader['verifier']) + ' · ' +
                       literal(reader['verdict']) + '</p>')
    if row['second_reader'] == 'missing':
        out.append('<p>second reader missing</p>')
    if row['carried']:
        out.append('<p>carried from format ' + literal(verdict['carried_from']['format']) + '</p>')
    out.append(badge(FRESHNESS[row['status']], row['status']))
    if verdict and 'note' in verdict:
        notes.append(('Record note', verdict['note']))
    return ''.join(out)


def fact(checker, rec, status, with_status):
    data, file = rec.data, rec.file
    out = ['<article class="fact" id="' + escape(rec.full, quote=True) + '"><header><h4>' +
           literal(data.get('title', data.get('name', rec.id))) + '</h4></header><div class="claim">']
    if 'claim' in data:
        out.append(author(data['claim']))
    else:
        out.append('<dl>')
        for k, v in data.items():
            if k not in ('id', 'support', 'note', 'todo', 'title', 'name'):
                out.append('<dt>' + literal(k) + '</dt><dd>' + literal(v) + '</dd>')
        out.append('</dl>')
    out.append('</div><div class="provenance">')
    notes = []
    if not speccheck.has_support(data):
        out.append(badge('gap', 'Gap'))
    out.append(support(checker, file, data.get('support', []), notes))
    out.append(badge('origin', file.root.layer + ' · ' + file.root.label))
    for aid in data.get('assumes', []):
        a = file.data['assumptions'][file.assumptions[aid][1]]
        out.append(badge('assumes', 'assumes ' + aid) + '<p>' + literal(a['text']) + '</p>')
    if 'todo' in data:
        todo = data['todo']
        out.append(badge('todo', 'verify on ' + todo['check']) + '<p>' + literal(todo['text']) + '</p>')
        if 'method' in todo:
            out.append('<p>Method: ' + literal(todo['method']) + '</p>')
    for key in ('requirement', 'assessment'):
        if key in data:
            out.append(badge(key, data[key]))
    finding = data.get('data', {}).get('finding', {})
    if finding:
        out.append(badge('assessment', finding['assessment']))
        if finding.get('settled_by'):
            out.append('<p>Settled by</p>')
        out.append(support(checker, file, finding.get('settled_by', []), notes))
    if 'scope' in data:
        out.append('<p>Scope: ' + literal(data['scope']) + '</p>')
    for relation in data.get('relates', []):
        target, why = checker.resolve(file, relation['fact'])
        if why:
            raise ValueError(why)
        out.append('<p>' + literal(relation['relation']) + ': ' + literal(target.full) + '</p>')
    for conflict in data.get('conflicts', []):
        if 'resolution' not in conflict:
            out.append(badge('contested', 'Contested'))
        out.append('<p>Conflict: ' + literal(conflict['reading']) + '</p>')
        out.append(support(checker, file, conflict['support'], notes))
        for k in ('resolution', 'assumption', 'decided'):
            if k in conflict:
                out.append('<p>' + literal(k) + ': ' + literal(conflict[k]) + '</p>')
        if 'note' in conflict:
            notes.append(('Conflict note', conflict['note']))
    row = status[file][rec.id]
    if data.get('critical'):
        out.append(badge('critical', 'bring-up critical' +
                         (' · second reader missing' if row['second_reader'] == 'missing' else '')))
    if with_status:
        out.append(verification(file, rec.id, row, notes))
    out.append('<p>Fact reference: <code>' + literal(rec.full) + '</code></p></div>')
    out.append(payload(checker, rec, status, with_status))
    if 'note' in data:
        notes.append(('Fact note', data['note']))
    out.extend(field(label, text) for label, text in notes)
    out.append('</article>')
    return ''.join(out)


def table(title, entries):
    """Fixed table elements; every input cell and column name is literal text."""
    if not entries:
        return ''
    keys = list(dict.fromkeys(k for entry in entries for k in entry))
    out = ['<h3>' + literal(title) + '</h3><table><thead><tr>']
    out.extend('<th>' + literal(key) + '</th>' for key in keys)
    out.append('</tr></thead><tbody>')
    for entry in entries:
        out.append('<tr>')
        out.extend('<td>' + literal(entry.get(key, '')) + '</td>' for key in keys)
        out.append('</tr>')
    out.append('</tbody></table>')
    return ''.join(out)


def payload(checker, rec, status, with_status):
    """Keep child support, requirements and verdicts visible even when a claim exists."""
    import peripheral

    data = rec.data.get('data', {})
    out = []
    for name in ('register', 'layout', 'finding', 'coverage'):
        if name in data:
            entries = [{k: v for k, v in data[name].items() if k != 'settled_by'}]
            out.append(table(name.capitalize() + ' (generated)', entries))
    for side, anchors in data.get('pair', {}).items():
        notes = []
        out.append('<div class="provenance"><p>Correspondence side: ' + literal(side) + '</p>')
        out.append(support(checker, rec.file, [{'class': 'src', 'anchors': anchors}], notes))
        out.append('</div>')
    for row, path in peripheral.children(rec.data, rec.path):
        key = row.get('id', row.get('before', '') + '->' + row.get('after', ''))
        out.append(table('Payload entry ' + rec.id + '.' + key,
                         [{k: v for k, v in row.items() if k not in ('support', 'note')}]))
        notes = []
        out.append('<div class="provenance">')
        out.append(support(checker, rec.file, row.get('support', []), notes))
        requirement = row.get('requirement', rec.data.get('requirement'))
        if requirement:
            out.append(badge('requirement', requirement))
        child = status[rec.file].get(rec.id + '.' + key)
        if with_status and child:
            out.append(verification(rec.file, rec.id + "." + key, child, notes))
        out.append('</div>')
        if 'note' in row:
            notes.append(('Payload note', row['note']))
        out.extend(field(label, text) for label, text in notes)
    return ''.join(out)


def generated(file):
    import peripheral

    summary = peripheral.generated(file)
    out = ['<section><h2>Provenance notice (generated): ' + literal(file.root.label) +
           '</h2><p>Support classes: ' + literal(', '.join(summary['classes'])) + '.</p>']
    out.append(table('Canonical references (generated)', summary['references']))
    out.append(table('Register map (generated)', peripheral.register_rows(summary)))
    out.append(table('Findings (generated)', summary['findings']))
    out.append(table('Correspondence (generated)', summary['pairs']))
    out.append(table('Comparison coverage (generated)', summary['coverage']))
    if summary['verify']:
        out.append('<h2>Verify on hardware (generated)</h2><ul>')
        for row in summary['verify']:
            out.append('<li><code>' + literal(row['fact']) + '</code>: ' + literal(row['text']) + '</li>')
        out.append('</ul>')
    out.append(table('Open questions (generated)', summary['questions']))
    out.append(table('Area confidence', file.data.get('areas', [])))
    out.append('</section>')
    return ''.join(out)


def resources(file):
    out = ['<section><h2>Resources: ' + literal(file.root.label) + '</h2>']
    def table(title, entries):
        if not entries:
            return
        keys = list(dict.fromkeys(k for e in entries for k in e if k not in ('note', 'files')))
        out.append('<h3>' + literal(title) + '</h3><table><thead><tr>')
        out.extend('<th>' + literal(k) + '</th>' for k in keys)
        out.append('</tr></thead><tbody>')
        for entry in entries:
            out.append('<tr>')
            out.extend('<td>' + literal(entry.get(k, '')) + '</td>' for k in keys)
            out.append('</tr>')
        out.append('</tbody></table>')
        for entry in entries:
            if 'note' in entry:
                out.append(field('Resource note', entry['note']))
            if 'files' in entry:
                table('Files: ' + entry['name'], entry['files'])
    for group, entries in file.data.get('resources', {}).items():
        table(group.capitalize(), entries)
    out.append('</section>')
    return ''.join(out)


def render(checker, *, spec_id=None, merged=False, with_status=False,
           source_commit=None, tool_commit=None):
    """Repeat containment independently of a prior check; return one complete HTML document."""
    selected = [f for f in checker.files if not f.root.context and
                (spec_id is None or f.spec_id == spec_id)]
    if not selected:
        raise speccheck.UsageError('no specs to render')
    ids = list(dict.fromkeys(f.spec_id for f in selected))
    groups = [[f for f in checker.files if f.spec_id == sid] for sid in ids] if merged else [[f] for f in selected]
    roots = {f.root.given.absolute() for group in groups for f in group}
    commits = {}
    for value in ([source_commit] if isinstance(source_commit, str) else source_commit or []):
        if '=' in value:
            name, sha = value.rsplit('=', 1)
            root = Path(name).absolute()
            if not name or root not in roots:
                raise speccheck.UsageError('--source-commit ROOT must name a rendered root directory')
        else:
            if len(roots) != 1:
                raise speccheck.UsageError('bare --source-commit requires exactly one rendered root')
            root, sha = next(iter(roots)), value
        if not re.fullmatch(r'[0-9a-f]{40}', sha) or root in commits:
            raise speccheck.UsageError('source commit must be unique per root and 40 lowercase hex characters')
        commits[root] = sha
    for group in groups:
        group.sort(key=lambda f: (f.is_overlay, f.root.rank, f.root.order, str(f.path)))
        for file in group:
            if file.root.context and file.root.untrusted:
                raise ValueError('cannot render merged input: context root does not check clean')
            values = list(textcheck.fields(file.data))
            if file.record_loaded:
                values.extend(textcheck.fields(file.record_loaded.data))
            for path, value, _ in values:
                bad = [f for f in specmd.findings(value) if f.level == 'error']
                if bad:
                    raise ValueError(file.spec_id + ': ' + speccheck._where(path) + ': ' + bad[0].message)
    status = {entry['file']: {r['key']: r for r in entry['rows']} for entry in checker.status}
    out = ['<!doctype html><html lang="en"><head><meta charset="utf-8">',
           '<meta name="viewport" content="width=device-width, initial-scale=1">',
           '<title>Spec viewer</title><style>' + STYLE.read_text(encoding='utf-8') + '</style></head><body><main>']
    for group in groups:
        base = group[0]
        out.append('<section><p>Generated by spec.py render. Do not edit.</p><p>Canonical form ' +
                   literal(records.CANONICAL) + '; driver-lab ' + literal(tool_commit or 'unavailable') + '.</p>')
        for file in group:
            relative = file.path.relative_to(file.root.given).as_posix()
            out.append('<p>Source ' + literal(file.root.label + ':' + relative) + '; commit ' +
                       literal(commits.get(file.root.given.absolute(), 'unavailable')) + '; SHA256 ' +
                       hashlib.sha256(file.loaded.raw).hexdigest() + '.</p>')
        out.append('<h1>' + literal(base.data.get('name', base.spec_id)) + '</h1><p>' + literal(base.spec_id) +
                   ' · ' + literal(base.kind) + ' · triggers: ' + literal(base.data.get('triggers', [])) + '</p>')
        for key in ('aliases', 'not_triggers', 'parts', 'variant_of', 'cache', 'overlays'):
            if key in base.data:
                out.append('<p>' + literal(key) + ': ' + literal(base.data[key]) + '</p>')
        out.extend(resources(f) for f in group)
        typed_spec = any(f.spec_id == base.spec_id and f.kind in ('peripheral', 'review')
                         for f in checker.files)
        for file in group:
            if typed_spec or any('data' in f for f in file.data['facts']):
                out.append(generated(file))
        if any(key in f.data for f in group for key in ('orientation', 'milestones', 'notes')):
            out.append('<section class="context"><h2>Context (not facts)</h2>')
            for file in group:
                for key in ('orientation', 'milestones', 'notes'):
                    if key in file.data:
                        out.append(field(key.capitalize(), file.data[key]))
            out.append('</section>')
        original = next((f for f in checker.files if f.spec_id == base.spec_id and not f.is_overlay), base)
        for section in speccheck.SECTIONS.get(original.kind, ('facts',)):
            if not any(r.data.get('section') == section for f in group for r in f.records.values()):
                continue
            out.append('<section><h2>' + literal(section.capitalize()) + '</h2>')
            for file in group:
                rows = [r for r in file.records.values() if r.data.get('section') == section]
                if rows and file.is_overlay:
                    out.append('<h3>Overlay: ' + literal(file.root.layer) + ' (' + literal(file.root.label) + ')</h3>')
                out.extend(fact(checker, r, status, with_status) for r in rows)
            out.append('</section>')
        for kind in ('instances', 'variants'):
            for file in group:
                rows = [r for r in file.records.values() if r.path[0] == kind]
                if rows:
                    out.append('<section><h2>' + literal(kind.capitalize() + ': ' + file.root.label) + '</h2>')
                    out.extend(fact(checker, r, status, with_status) for r in rows)
                    out.append('</section>')
        for file in group:
            for notice in file.data.get('notices', []):
                out.append('<section><h2>Source notice: ' + literal(notice['repo'] + ':' + notice['path']) +
                           '</h2><pre>' + escape(notice['text']) + '</pre></section>')
        out.append('</section>')
    out.append('</main></body></html>')
    return '\n'.join(out) + '\n'


def command(api, args):
    checker = api._run_check(args)
    findings = api._ordered(checker.findings)
    errors = [f for f in findings if f.level == 'error']
    if errors:
        return api.EXIT_INVALID, {'ok': False, 'html': None, 'findings': [f.as_dict() for f in findings],
                                  '_text': [str(f) for f in findings]}
    try:
        view = render(checker, spec_id=args.spec, merged=args.merged, with_status=args.with_status,
                      source_commit=args.source_commit, tool_commit=args.tool_commit)
    except speccheck.UsageError as exc:
        raise api.Usage(str(exc)) from None
    except ValueError as exc:
        return api.EXIT_INVALID, {'ok': False, 'html': None, 'findings': [{'message': str(exc)}],
                                  '_text': [str(exc)]}
    return api.EXIT_OK, {'ok': True, 'html': view, 'findings': [f.as_dict() for f in findings],
                         '_text': [view.rstrip('\n')]}
