# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Searchable explorer page over every published fact, plus heading-anchor resolution.

The page embeds one JSON document. Its *_html fields are render_html output: author() for author
text (the per-spec viewer's fixed-element renderer) and literal() for a record's generated
fields; search text is extracted from them. Every other value is a string the page script
inserts with textContent. Anchors are fetched once at build time (anchors.json in the site),
validated on every load, and only ever become the fragment of a document URL the spec declares.
"""

from __future__ import annotations

from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
from urllib.parse import quote
import urllib.request

import render_html
import render_md
import speccheck

HERE = Path(__file__).resolve().parent
ANCHORS_FORMAT = 1
BLOB = re.compile(r'https://github\.com/([\w.-]+)/([\w.-]+)/blob/([0-9a-f]{40})/([\w./-]+)')
WIKI = re.compile(r'https://github\.com/([\w.-]+)/([\w.-]+)/wiki/([\w.-]+)')
REASON = re.compile(r'no such heading on the rendered page|fetch limit reached|fetch failed: \w+')
ANCHOR = re.compile(r'[^\x00-\x20\x7f"<>\\`#]{1,200}')


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def plain(html):
    """Search text of a fragment that render_html produced."""
    parser = _Text()
    parser.feed(html)
    return re.sub(r'\s+', ' ', ''.join(parser.parts)).strip()


def heading_key(text):
    return re.sub(r'\s+', ' ', str(text)).strip().casefold()


class Headings(HTMLParser):
    """Heading text and anchor id from GitHub-rendered HTML.

    GitHub puts the id on the heading (AsciiDoc) or on an `a.anchor` that follows it inside
    the same heading wrapper (Markdown, reStructuredText); `user-content-` is GitHub's prefix.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.found, self.open, self.text, self.pending = {}, None, [], None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if re.fullmatch(r'h[1-6]', tag):
            self.open, self.text, self.pending = attrs.get('id') or '', [], None
        elif self.pending is not None:
            # Only an anchor directly after the heading belongs to it.
            href = attrs.get('href') or ''
            if tag == 'a' and 'anchor' in (attrs.get('class') or '').split() and href.startswith('#'):
                self._add(self.pending, href[1:])
            self.pending = None

    def handle_endtag(self, tag):
        if self.open is not None and re.fullmatch(r'h[1-6]', tag):
            text = ''.join(self.text)
            if self.open:
                self._add(text, self.open)
            else:
                self.pending = text
            self.open = None

    def handle_data(self, data):
        if self.open is not None:
            self.text.append(data)

    def _add(self, text, anchor):
        anchor = anchor.removeprefix('user-content-')
        self.found.setdefault(heading_key(text), anchor)


MAX_FETCHES = 500


def _dots(*parts):
    return any(seg in ('.', '..') for part in parts for seg in part.split('/'))


def fetch_url(url):
    """The rendered-HTML request for a document URL, or None when it has no anchors to find."""
    m = BLOB.fullmatch(url)
    if m:
        owner, repo, commit, path = m.groups()
        if _dots(owner, repo, path):
            return None
        api = f'https://api.github.com/repos/{owner}/{repo}/contents/{quote(path)}?ref={commit}'
        return api, {'Accept': 'application/vnd.github.html'}
    m = WIKI.fullmatch(url)
    if m and not _dots(*m.groups()):
        return url, {'Accept': 'text/html'}
    return None


def request(request_url, headers, token=None):
    """The token goes only to api.github.com and is never forwarded on a redirect."""
    req = urllib.request.Request(request_url, headers=dict(headers, **{'User-Agent': 'spec-explorer'}))
    if token and request_url.startswith('https://api.github.com/'):
        req.add_unredirected_header('Authorization', 'Bearer ' + token)
    return req


def _get(request_url, headers):
    token = os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_TOKEN')
    with urllib.request.urlopen(request(request_url, headers, token), timeout=30) as response:
        return response.read(5_000_000).decode('utf-8', 'replace')


def wanted(checker):
    """Document URL -> cited heading texts, over every published (non-context) file."""
    out = {}
    for file in checker.files:
        if file.root.context:
            continue
        for rec in file.records.values():
            for entry, _ in speccheck.supports(rec.data, ()):
                doc = file.documents.get(entry.get('doc'), (None,))[0]
                if not doc:
                    continue
                for at in entry.get('at', []):
                    if 'heading' in at and fetch_url(doc['url']):
                        out.setdefault(doc['url'], set()).add(str(at['heading']))
    return out


def resolve_anchors(checker, get=_get):
    """Fetch each cited page once. A failure leaves that heading unresolved, never fails."""
    anchors, unresolved = {}, []
    for count, (url, headings) in enumerate(sorted(wanted(checker).items())):
        if count >= MAX_FETCHES:
            unresolved.extend({'url': url, 'heading': h, 'reason': 'fetch limit reached'}
                              for h in sorted(headings))
            continue
        try:
            parser = Headings()
            parser.feed(get(*fetch_url(url)))
            found = parser.found
            reason = 'no such heading on the rendered page'
        except Exception as exc:  # network, HTTP or decoding: report and continue
            found, reason = {}, 'fetch failed: ' + type(exc).__name__
        for heading in sorted(headings):
            anchor = found.get(heading_key(heading))
            if anchor and ANCHOR.fullmatch(anchor):
                anchors.setdefault(url, {})[heading] = anchor
            else:
                unresolved.append({'url': url, 'heading': heading, 'reason': reason})
    return {'format': ANCHORS_FORMAT, 'anchors': anchors, 'unresolved': unresolved}


def empty_anchors():
    return {'format': ANCHORS_FORMAT, 'anchors': {}, 'unresolved': []}


def dump_anchors(data):
    return json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False) + '\n'


def load_anchors(text, checker):
    """Refuse anything build would not have written; return the anchors the page may use."""
    try:
        data = json.loads(text)
        if not isinstance(data, dict) or set(data) != {'format', 'anchors', 'unresolved'}:
            raise ValueError('unexpected keys')
        if type(data['format']) is not int or data['format'] != ANCHORS_FORMAT:
            raise ValueError('unsupported format')
        cited = wanted(checker)
        for item in data['unresolved']:
            if not (isinstance(item, dict) and set(item) == {'url', 'heading', 'reason'} and
                    all(isinstance(v, str) for v in item.values())):
                raise ValueError('malformed unresolved entry')
            if item['heading'] not in cited.get(item['url'], ()):
                raise ValueError('unresolved entry for a heading no spec cites')
            if not REASON.fullmatch(item['reason']):
                raise ValueError('unknown unresolved reason')
        pairs = [(i['url'], i['heading']) for i in data['unresolved']]
        if pairs != sorted(set(pairs)):
            raise ValueError('unresolved entries must be unique and sorted')
        kept = {}
        for url, table in data['anchors'].items():
            if not table:
                raise ValueError('empty anchor table')
            for heading, anchor in table.items():
                if not (isinstance(anchor, str) and ANCHOR.fullmatch(anchor)):
                    raise ValueError('malformed anchor')
                if heading not in cited.get(url, ()):
                    raise ValueError('anchor for a heading no spec cites')
                kept.setdefault(url, {})[heading] = anchor
                if (url, heading) in pairs:
                    raise ValueError('heading both resolved and unresolved')
        return kept
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError('anchors.json: ' + str(exc)) from None


def _citations(checker, file, entries, anchors, notes):
    """Flat citation list; stated premises add their own support after the inference."""
    out = []
    for entry in entries:
        item = {'class': entry['class'], 'title': '', 'url': '', 'at': [], 'premises': []}
        doc = file.documents.get(entry.get('doc'), (None,))[0]
        if doc:
            item['title'] = doc['title'] + (' (' + doc['revision'] + ')' if 'revision' in doc else '')
            if render_html.specmd.allowed_link(doc['url']):
                item['url'] = doc['url']
        for at in entry.get('at', []):
            loc = {'label': render_md._locator(at), 'href': ''}
            anchor = anchors.get(item['url'], {}).get(str(at.get('heading', '')))
            if anchor:
                loc['href'] = item['url'] + '#' + quote(anchor, safe='')
            item['at'].append(loc)
        for anchor in entry.get('anchors', []):
            item['at'].append({'label': anchor['repo'] + ': ' + anchor['path'] + (
                ' lines ' + '–'.join(map(str, anchor['lines'])) if 'lines' in anchor else ''), 'href': ''})
        nested = []
        if entry['class'] == 'inference':
            item['title'] = 'Derivation: ' + str(entry.get('derivation', ''))
            for premise in entry.get('premises', []):
                if 'fact' in premise:
                    target, why = checker.resolve(file, premise['fact'])
                    if why:
                        raise ValueError(why)
                    item['premises'].append('Fact ' + target.full +
                                            (': ' + str(premise['uses']) if 'uses' in premise else ''))
                elif 'states' in premise:
                    item['premises'].append('Stated: ' + plain(render_html.author(premise['states'])))
                    nested.extend(_citations(checker, file, premise.get('support', []), anchors, notes))
                else:
                    a = file.data['assumptions'][file.assumptions[premise['assumption']][1]]
                    item['premises'].append('Assumption ' + str(a['id']) + ': ' + str(a['text']))
        if 'note' in entry:
            notes.append(render_html.author(entry['note']))
        out.append(item)
        out.extend(nested)
    return out


def _fact(checker, rec, row, children, anchors):
    data, file = rec.data, rec.file
    if 'claim' in data:
        claim = render_html.author(data['claim'])
    else:
        claim = ''.join('<p>' + render_html.literal(k) + ': ' + render_html.literal(v) + '</p>'
                        for k, v in data.items()
                        if k not in ('id', 'support', 'note', 'todo', 'title', 'name'))
    verdict = file.verdicts.get(rec.id, (None, None))[0] or {}
    notes = []
    cites = _citations(checker, file, data.get('support', []), anchors, notes)
    conflicts = []
    for conflict in data.get('conflicts', []):
        conflicts.append({'reading': str(conflict['reading']),
                          'resolved': 'resolution' in conflict})
        cites.extend(_citations(checker, file, conflict.get('support', []), anchors, notes))
        if 'note' in conflict:
            notes.append(render_html.author(conflict['note']))
    notes.extend(render_html.author(t) for t in (data.get('note'), verdict.get('note')) if t)
    assumes = []
    for aid in data.get('assumes', []):
        a = file.data['assumptions'][file.assumptions[aid][1]]
        assumes.append({'id': str(aid), 'text': str(a['text'])})
    todo = data.get('todo') or {}
    return {
        'ref': rec.full,
        'id': rec.id,
        'source': file.root.label + ':' + file.path.relative_to(file.root.given).as_posix(),
        'section': data.get('section') or rec.path[0],
        'title': str(data.get('title', data.get('name', rec.id))),
        'claim_html': claim,
        'text': plain(claim),
        'notes_html': notes,
        'critical': bool(data.get('critical')),
        'gap': not speccheck.has_support(data),
        'contested': any(not c['resolved'] for c in conflicts),
        'conflicts': conflicts,
        'assumes': assumes,
        'todo': {'check': str(todo['check']), 'text': str(todo.get('text', ''))} if todo else None,
        'verdict': row.get('verdict') or '',
        'date': str(verdict.get('date', '')),
        'status': row.get('status') or '',
        'second_reader_missing': row.get('second_reader') == 'missing',
        'children': children,
        'verifier': str(verdict.get('verifier', '')),
        'readers': [{'verifier': str(r['verifier']), 'verdict': str(r['verdict'])}
                    for r in verdict.get('readers', [])],
        'origin': (file.root.layer or '') + ' · ' + file.root.label,
        'cites': cites,
    }


def data(checker, anchors, pages):
    """One entry per published spec id; overlays fold into their target's entry."""
    status = {entry['file']: {r['key']: r for r in entry['rows']} for entry in checker.status}
    specs = {}
    for file in checker.files:
        if file.root.context:
            continue
        render_html.refuse_unsafe_fields(file)
        spec = specs.setdefault(file.spec_id, {
            'id': file.spec_id, 'name': '', 'kind': '', 'triggers': [], 'orientation_html': '',
            'documents': [], 'facts': [], 'pages': []})
        if not file.is_overlay:
            spec['name'] = str(file.data.get('name', file.spec_id))
            spec['kind'] = file.kind
            spec['triggers'] = [str(t) for t in file.data.get('triggers', [])]
            if 'orientation' in file.data:
                spec['orientation_html'] = render_html.author(file.data['orientation'])
        for doc in file.data.get('resources', {}).get('documents', []):
            spec['documents'].append({
                'class': str(doc.get('class', '')), 'title': str(doc.get('title', doc['name'])),
                'url': doc['url'] if render_html.specmd.allowed_link(doc.get('url', '')) else '',
                'pages': str(doc.get('pages', ''))})
        rows = status.get(file, {})
        for rec in file.records.values():
            children = [{'key': key, 'verdict': row.get('verdict') or '', 'status': row.get('status') or ''}
                        for key, row in sorted(rows.items()) if key.startswith(rec.id + '.')]
            spec['facts'].append(_fact(checker, rec, rows.get(rec.id, {}), children, anchors))
    for entry in pages:
        if entry['spec'] in specs:
            specs[entry['spec']]['pages'].append(
                {'label': entry['source'], 'html': entry['html'], 'markdown': entry['markdown']})
    for spec in specs.values():
        spec['name'] = spec['name'] or spec['id']
    return sorted(specs.values(), key=lambda s: s['id'])


def _json_for_script(value):
    """JSON that cannot close or comment the script element holding it."""
    text = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    return text.replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e')


def page(checker, anchors, pages, *, tool_commit=None):
    payload = {'specs': data(checker, anchors, pages), 'tool_commit': tool_commit or ''}
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            '<title>Spec explorer</title><style>' + (HERE / 'explorer.css').read_text(encoding='utf-8') +
            '</style></head><body>\n' + (HERE / 'explorer.html').read_text(encoding='utf-8') +
            '<script type="application/json" id="spec-data">' + _json_for_script(payload) + '</script>\n'
            '<script>' + (HERE / 'explorer.js').read_text(encoding='utf-8') + '</script>\n'
            '</body></html>\n')


def unresolved_report(data):
    return ['unresolved heading: ' + u['url'] + ' :: ' + u['heading'] + ' (' + u['reason'] + ')'
            for u in data['unresolved']]


