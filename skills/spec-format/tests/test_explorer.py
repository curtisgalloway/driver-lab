# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Spec explorer page and heading anchors: escaping, validation and deterministic publishing."""

import contextlib
import io
import json
from pathlib import Path
import re
import sys
import unittest
import unittest.mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'scripts'))
sys.path.insert(0, str(HERE.parent / 'ci'))
import explorer
import publish
from test_check import chip, fact
from test_render_html import Fixture, Tree
from test_records import record, verdict
from test_render_md import checked

BLOB = 'https://github.com/o/r/blob/' + 'c' * 40 + '/doc/boot.rst'
DOCS = ('    - {name: trm, class: databook, title: Widget TRM, '
        'url: "https://example.invalid/trm.pdf", pages: 80}\n'
        f'    - {{name: guide, class: doc, title: Guide, url: "{BLOB}"}}\n')


def heading_fact(fid, heading):
    return (f"  - id: {fid}\n    section: quick-facts\n    title: T {fid}\n    claim: C {fid}.\n"
            f'    support: [{{class: doc, doc: guide, at: [{{heading: "{heading}"}}]}}]\n')


# GitHub's two shapes: an id on the heading (AsciiDoc), or an a.anchor after it (Markdown, rst).
RENDERED = ('<h3 id="user-content-kernel_old"><code>kernel_old</code></h3>'
            '<div class="markdown-heading"><h2 class="heading-element">2. Setup the device tree</h2>'
            '<a id="user-content-2-setup" class="anchor" href="#2-setup-the-device-tree"></a></div>'
            '<div class="markdown-heading"><h2>Setup</h2><a class="anchor" href="#setup-1"></a></div>'
            '<div class="markdown-heading"><h2>Setup</h2><a class="anchor" href="#setup-2"></a></div>'
            '<h2>Unanchored</h2><p><a class="anchor" href="#stray">not a heading anchor</a></p>')


class Headings(unittest.TestCase):
    def parse(self, html):
        parser = explorer.Headings()
        parser.feed(html)
        return parser.found

    def test_both_github_shapes_first_occurrence_wins_and_prefix_dropped(self):
        found = self.parse(RENDERED)
        self.assertEqual(found['kernel_old'], 'kernel_old')
        self.assertEqual(found['2. setup the device tree'], '2-setup-the-device-tree')
        self.assertEqual(found['setup'], 'setup-1')
        self.assertNotIn('unanchored', found)

    def test_only_pinned_blobs_and_wikis_are_fetched(self):
        self.assertTrue(explorer.fetch_url(BLOB)[0].startswith('https://api.github.com/repos/o/r/contents/'))
        self.assertTrue(explorer.fetch_url(BLOB)[0].endswith('?ref=' + 'c' * 40))
        self.assertIsNotNone(explorer.fetch_url('https://github.com/o/r/wiki/Mailboxes'))
        for url in ('https://github.com/o/r/blob/main/doc/boot.rst', 'https://example.invalid/x.html',
                    'https://github.com/o/r/tree/' + 'c' * 40 + '/doc', 'http://github.com/o/r/wiki/X'):
            self.assertIsNone(explorer.fetch_url(url), url)
        for url in ('https://github.com/o/../blob/' + 'c' * 40 + '/x.md',
                    'https://github.com/o/r/blob/' + 'c' * 40 + '/a/../../x.md',
                    'https://github.com/o/r/wiki/..'):
            self.assertIsNone(explorer.fetch_url(url), url)

    def test_token_only_to_the_api_and_never_on_redirect(self):
        api = explorer.request('https://api.github.com/repos/o/r/contents/x', {}, 'tok')
        self.assertEqual(api.unredirected_hdrs.get('Authorization'), 'Bearer tok')
        self.assertNotIn('Authorization', api.headers)
        wiki = explorer.request('https://github.com/o/r/wiki/X', {}, 'tok')
        self.assertNotIn('Authorization', wiki.unredirected_hdrs)
        self.assertNotIn('Authorization', wiki.headers)


class Anchors(Fixture):
    def setUp(self):
        super().setUp()
        self.path.write_text(chip(docs=DOCS, facts=heading_fact('a', '2. Setup the device tree') +
                                  heading_fact('b', 'Missing heading') + fact('c')))
        self.checker = checked(self.root)

    def test_resolve_records_anchor_and_unresolved_without_failing(self):
        calls = []

        def get(url, headers):
            calls.append(url)
            return RENDERED
        data = explorer.resolve_anchors(self.checker, get=get)
        self.assertEqual(len(calls), 1)
        self.assertEqual(data['anchors'], {BLOB: {'2. Setup the device tree': '2-setup-the-device-tree'}})
        self.assertEqual([u['heading'] for u in data['unresolved']], ['Missing heading'])

    def test_fetch_failure_leaves_headings_unresolved(self):
        def get(url, headers):
            raise OSError('offline')
        data = explorer.resolve_anchors(self.checker, get=get)
        self.assertEqual(data['anchors'], {})
        self.assertTrue(all(u['reason'] == 'fetch failed: OSError' for u in data['unresolved']))

    def test_unsafe_fetched_anchor_is_not_kept(self):
        def get(url, headers):
            return '<h2 id="x&quot;onclick=&quot;y">2. Setup the device tree</h2>'
        data = explorer.resolve_anchors(self.checker, get=get)
        self.assertEqual(data['anchors'], {})

    def test_load_refuses_anything_build_would_not_write(self):
        good = {'format': 1, 'anchors': {BLOB: {'2. Setup the device tree': 'ok'}},
                'unresolved': [{'url': BLOB, 'heading': 'Missing heading', 'reason': 'fetch failed: OSError'}]}
        kept = explorer.load_anchors(json.dumps(good), self.checker)
        self.assertEqual(kept, {BLOB: {'2. Setup the device tree': 'ok'}})
        bad = [{'format': 2, 'anchors': {}}, {'format': 1, 'anchors': {BLOB: 'x'}},
               {'format': 1, 'anchors': {BLOB: {'2. Setup the device tree': 'a"b'}}},
               {'format': 1, 'anchors': {BLOB: {'2. Setup the device tree': 'a#b'}}},
               {'format': 1, 'anchors': {}, 'unresolved': [{'url': 1}]},
               {'format': 1, 'anchors': {}},
               {'format': True, 'anchors': {}, 'unresolved': []},
               {'format': 1, 'anchors': {}, 'unresolved': [], 'extra': 1},
               {'format': 1, 'unresolved': [], 'anchors': {BLOB: {'Uncited': 'x'}}},
               {'format': 1, 'anchors': {}, 'unresolved': [{'url': BLOB, 'heading': 'Uncited', 'reason': 'r'}]},
               {'format': 1, 'unresolved': [], 'anchors': {'https://github.com/o/r/wiki/X': {'h': 'y'}}},
               {'format': 1, 'unresolved': [], 'anchors': {'https://github.com/o/r/wiki/X': {}}},
               {'format': 1, 'anchors': {}, 'unresolved': [{'url': BLOB, 'heading': 'Missing heading', 'reason': '<script>'}]},
               {'format': 1, 'anchors': {}, 'unresolved': [{'url': BLOB, 'heading': 'Missing heading', 'reason': 'fetch limit reached'}] * 2},
               {'format': 1, 'anchors': {BLOB: {'Missing heading': 'x'}},
                'unresolved': [{'url': BLOB, 'heading': 'Missing heading', 'reason': 'fetch limit reached'}]}]
        for value in bad:
            with self.assertRaises(ValueError, msg=value):
                explorer.load_anchors(json.dumps(value), self.checker)

    def test_jump_link_only_on_the_declared_document_url(self):
        kept = {BLOB: {'2. Setup the device tree': 'a b'}}
        spec = explorer.data(self.checker, kept, [])[0]
        at = {f['id']: f['cites'][0]['at'] for f in spec['facts']}
        self.assertEqual(at['a'], [{'label': 'heading: 2. Setup the device tree', 'href': BLOB + '#a%20b'}])
        self.assertEqual(at['b'][0]['href'], '')
        self.assertEqual(at['c'][0]['href'], '')


class Page(Fixture):
    HOSTILE = ('</script><script>alert(1)</script> <img src=x onerror=alert(2)> '
               '<!-- x --> [l](javascript:alert(3)) `</script>`')

    def setUp(self):
        super().setUp()
        self.path.write_text(chip(facts=fact('a') + fact('b')).replace('claim: C a.', 'claim: "C a."'))

    def payload(self, html):
        m = re.search(r'<script type="application/json" id="spec-data">(.*?)</script>', html, re.S)
        return json.loads(m.group(1))

    def test_hostile_text_stays_inside_the_json_and_author_html_is_sanitized(self):
        import render_html
        text = self.path.read_text().replace('T a', 'T </script><b>a').replace(
            'claim: "C a."', 'claim: ' + json.dumps(self.HOSTILE))
        self.path.write_text(text)
        checker = checked(self.root)
        with unittest.mock.patch.object(render_html, 'refuse_unsafe_fields'):
            html = explorer.page(checker, {}, [], tool_commit='b' * 40)
        self.assertEqual(html.count('</script'), 2)
        self.assertEqual(html.lower().count('<script'), 2)
        fact_a = next(f for f in self.payload(html)['specs'][0]['facts'] if f['id'] == 'a')
        self.assertEqual(fact_a['title'], 'T </script><b>a')
        tree = Tree(fact_a['claim_html'])
        self.assertLessEqual({tag for tag, _, _ in tree.nodes}, {'p', 'span', 'code'})
        self.assertEqual([attrs for _, attrs, _ in tree.nodes if attrs], [])
        self.assertNotIn('javascript:', fact_a['claim_html'])
        self.assertIn('alert(1)', fact_a['text'])

    def test_unsafe_fields_are_refused_like_the_viewer(self):
        self.path.write_text(self.path.read_text().replace('claim: "C a."', 'claim: "<b>raw</b>"'))
        checker = checked(self.root)
        with self.assertRaises(ValueError):
            explorer.page(checker, {}, [])

    def test_payload_is_deterministic_and_carries_status_and_pages(self):
        checker = checked(self.root)
        pages = [{'source': 'viewer:widget.spec.yaml', 'spec': 'widgetchip', 'html': 'p.html', 'markdown': 'p.md'}]
        first = explorer.page(checker, {}, pages)
        self.assertEqual(first, explorer.page(checked(self.root), {}, pages))
        spec = self.payload(first)['specs'][0]
        self.assertEqual(spec['pages'][0]['html'], 'p.html')
        self.assertEqual([f['id'] for f in spec['facts']], ['a', 'b'])
        self.assertEqual(spec['facts'][0]['status'], 'unverified')
        self.assertEqual(spec['facts'][0]['cites'][0]['class'], 'databook')


class Fidelity(Fixture):
    """Every status signal the viewer shows reaches the explorer's data."""

    def test_premises_assumptions_conflicts_notes_and_second_reader(self):
        facts = (fact('a', "    critical: true\n    assumes: [s]\n"
                           "    conflicts:\n      - reading: another reading\n        support:\n"
                           "          - {class: databook, doc: trm, at: [{section: '2'}], note: conflict support}\n")
                 + "  - id: i\n    section: quick-facts\n    title: I\n    claim: I.\n"
                   "    support:\n      - class: inference\n        premises:\n"
                   "          - fact: '#a'\n            uses: the value\n"
                   "          - states: it is so\n            support:\n"
                   "              - {class: databook, doc: trm, at: [{section: '3'}], note: premise note}\n"
                   "        derivation: so\n    todo: {check: hardware, text: check.}\n")
        self.path.write_text(chip(facts=facts, head="assumptions:\n  - {id: s, text: the stub is stock}\n"))
        checker = checked(self.root)
        self.assertFalse([f for f in checker.findings if f.level == 'error'], checker.findings)
        row = next(r for r in checker.status[0]['rows'] if r['key'] == 'a')
        (self.root / 'resources').mkdir()
        (self.root / 'resources' / 'widget.verify.yaml').write_text(
            record('widgetchip', 'widget.spec.yaml', {'a': verdict(row['basis'])}))
        checker = checked(self.root)
        facts = {f['id']: f for f in explorer.data(checker, {}, [])[0]['facts']}
        a, i = facts['a'], facts['i']
        self.assertTrue(a['contested'])
        self.assertEqual(a['conflicts'], [{'reading': 'another reading', 'resolved': False}])
        self.assertEqual(a['assumes'], [{'id': 's', 'text': 'the stub is stock'}])
        self.assertTrue(a['second_reader_missing'])
        self.assertEqual(len(a['cites']), 2)
        self.assertTrue(any('conflict support' in n for n in a['notes_html']))
        self.assertEqual(i['cites'][0]['premises'][0], 'Fact widgetchip@viewer#a: the value')
        self.assertEqual(i['cites'][0]['premises'][1], 'Stated: it is so')
        self.assertEqual(i['cites'][1]['at'][0]['label'], '§3')
        self.assertTrue(any('premise note' in n for n in i['notes_html']))
        self.assertEqual(a['children'], [])
        self.assertEqual(a['source'], 'viewer:widget.spec.yaml')


class Publishing(Fixture):
    def base(self):
        out = Path(self.temp.name) / 'site'
        return out, ['build', str(self.root), '--out', str(out), '--source-commit',
                     str(self.root) + '=' + 'a' * 40, '--tool-commit', 'b' * 40]

    def run_main(self, argv):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return publish.main(argv)

    def test_build_writes_explorer_and_anchors_and_verify_rechecks_them(self):
        out, argv = self.base()
        self.assertEqual(self.run_main(argv), 0)
        self.assertEqual(json.loads((out / 'anchors.json').read_text()),
                         {'anchors': {}, 'format': 1, 'unresolved': []})
        self.assertIn('id="spec-data"', (out / 'index.html').read_text())
        manifest = json.loads((out / 'manifest.json').read_text())
        self.assertIn('anchors.json', manifest['sha256'])
        self.assertEqual(self.run_main(['verify', *argv[1:]]), 0)

    def test_verify_refuses_missing_malformed_or_rewritten_anchors(self):
        out, argv = self.base()
        self.assertEqual(self.run_main(argv), 0)
        stored = (out / 'anchors.json').read_text()
        for text in ('{"format": 1, "anchors": {"x": "y"}}',
                     stored.replace('"anchors": {}', '"anchors": {"https://github.com/o/r/wiki/X": {"h": "a\\"b"}}'),
                     json.dumps(json.loads(stored))):
            (out / 'anchors.json').write_text(text)
            self.assertEqual(self.run_main(['verify', *argv[1:]]), 1, text)
        (out / 'anchors.json').unlink()
        self.assertEqual(self.run_main(['verify', *argv[1:]]), 1)

    def test_fetch_anchors_flag_uses_the_network_resolver(self):
        out, argv = self.base()
        seen = []

        def fake(checker):
            seen.append(checker)
            return explorer.empty_anchors()
        with unittest.mock.patch.object(explorer, 'resolve_anchors', side_effect=fake):
            self.assertEqual(self.run_main([*argv, '--fetch-anchors']), 0)
            self.assertEqual(len(seen), 1)
            self.assertEqual(self.run_main(['verify', *argv[1:]]), 0)
            self.assertEqual(len(seen), 1)


if __name__ == '__main__':
    unittest.main()
