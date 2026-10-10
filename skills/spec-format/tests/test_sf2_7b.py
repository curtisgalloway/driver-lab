# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Review payloads, citation integration and exact generated projections in both views."""

import copy
from html.parser import HTMLParser
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'scripts'))

import peripheral
import records
import render_html
import render_md
import speccheck
import specload
from test_sf2_7a import Fixture, run
from test_resolve import GitFixture, SOURCE

class Tables(HTMLParser):
    """Independently read generated HTML rows and hardware list entries."""

    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.heading = self.current = ''
        self.capture = None
        self.tables = {}
        self.rows = []
        self.row = []
        self.cell = ''
        self.verify = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        if tag in ('h2', 'h3'):
            self.capture = 'heading'
            self.heading = ''
        elif tag == 'table':
            self.current = self.heading
            self.rows = []
        elif tag == 'tr':
            self.row = []
        elif tag in ('th', 'td'):
            self.capture = 'cell'
            self.cell = ''
        elif tag == 'li' and self.heading == 'Verify on hardware (generated)':
            self.capture = 'verify'
            self.verify.append('')

    def handle_endtag(self, tag):
        if tag in ('h2', 'h3', 'th', 'td', 'li'):
            self.capture = None
        if tag in ('th', 'td'):
            self.row.append(self.cell)
        elif tag == 'tr':
            self.rows.append(self.row)
        elif tag == 'table':
            self.tables.setdefault(self.current, []).append(self.rows)

    def handle_data(self, text):
        if self.capture == 'heading':
            self.heading += text
        elif self.capture == 'cell':
            self.cell += text
        elif self.capture == 'verify':
            self.verify[-1] += text


class ReviewFixture(Fixture):
    def setUp(self):
        super().setUp()
        self.file.unlink()
        self.file = self.root / 'widget-review.spec.yaml'
        self.data = specload.load_strict(HERE / 'fixtures/review/widget-review.spec.yaml')
        self.write()

    @property
    def finding(self):
        return self.data['facts'][0]['data']['finding']

    def schema_invalid(self):
        self.write()
        code, result = run('validate', self.file)
        self.assertEqual(code, 1, result)


class ReviewRules(ReviewFixture):
    def test_design_example_and_views(self):
        self.assertEqual(self.check()[0], 0)
        self.assertEqual(run('validate', self.file)[0], 0)
        for fmt, key in (('md', 'markdown'), ('html', 'html')):
            code, result = run('render', self.root, '--format', fmt, '--with-status')
            self.assertEqual(code, 0, result)
            for text in ('f-baud-latch', 'previous baud rate', 'init-pair', 'dma-coverage', 'Widget TRM'):
                self.assertIn(text, result[key])
        html = render_html.render(self.checker())
        self.assertIn('badge assessment">bug', html)
        self.assertIn('badge assessment">suspect', html)
        self.assertIn('§4.2, p. 40', html)
        md = render_md.render(self.checker())
        self.assertIn(render_md.escape('Finding (generated)'), md)
        self.assertIn('Correspondence side: `impl`', md)
        self.assertIn('Correspondence side: `ref`', md)
        self.assertIn('§4', md)
        checker = self.checker()
        status = {e['file']: {r['key']: r for r in e['rows']} for e in checker.status}
        file = checker.files[0]
        article = render_html.fact(checker, file.records['f-baud-latch'], status, False)
        self.assertIn('badge class-databook', article)
        pair = render_html.payload(checker, file.records['init-pair'], status, False)
        self.assertIn('impl@' + '2' * 40, pair)
        self.assertIn('ref@' + '1' * 40, pair)
        pair_md = render_md.View()
        render_md._payload(pair_md, checker, file.records['init-pair'], status, False)
        self.assertIn('impl@' + '2' * 40, '\n'.join(pair_md))
        self.assertIn('ref@' + '1' * 40, '\n'.join(pair_md))
        finding_md = render_md.View()
        render_md._payload(finding_md, checker, file.records['f-baud-latch'], status, False)
        self.assertIn('databook: Widget TRM; ' + render_md.escape('§4.2, p. 40'), '\n'.join(finding_md))

    def test_bug_needs_independent_justification(self):
        self.finding.pop('settled_by')
        self.invalid('bug needs settled_by')
        self.finding.update(self_evident=True, reason='The write uses the wrong bit.')
        self.assertEqual(self.check()[0], 0)
        self.finding['self_evident'] = False
        self.schema_invalid()
        self.finding['self_evident'] = True
        self.finding.pop('reason')
        self.schema_invalid()
        self.finding.pop('self_evident')
        self.finding['reason'] = 'Unattached reason'
        self.schema_invalid()

    def test_settlement_is_a_checked_document_citation(self):
        base = copy.deepcopy(self.data)
        for entry in ([self.data['facts'][0]['support'][0]], [],
                      [{'class': 'inference', 'premises': [{'fact': '#init-pair'}], 'derivation': 'it follows'}]):
            self.data = copy.deepcopy(base)
            self.finding['settled_by'] = entry
            self.schema_invalid()
        for field, value, diagnostic in (('doc', 'missing', "document 'missing'"),
                                         ('class', 'doc', 'of class databook')):
            self.data = copy.deepcopy(base)
            self.finding['settled_by'][0][field] = value
            self.invalid(diagnostic)
        self.data = copy.deepcopy(base)
        self.finding['settled_by'][0]['at'][0]['page'] = '121'
        self.invalid('120')

    def test_required_closed_review_records(self):
        base = copy.deepcopy(self.data)
        objects = [((), ('id', 'name', 'resources')),
                   (('facts', 0, 'data', 'finding'), ('category', 'assessment', 'consequence', 'resolution')),
                   (('facts', 0, 'data', 'finding', 'resolution'), ('status',)),
                   (('facts', 1, 'data', 'pair'), ('impl', 'ref')),
                   (('facts', 2, 'data', 'coverage'), ('area', 'compared', 'read', 'reason'))]
        for path, required in objects:
            for key in (*required, 'unknown'):
                self.data = copy.deepcopy(base)
                value = self.data
                for part in path:
                    value = value[part]
                if key == 'unknown':
                    value[key] = 'invented'
                else:
                    value.pop(key)
                with self.subTest(path=path, key=key):
                    self.schema_invalid()
        for path in (('facts', 0, 'data', 'finding'), ('facts', 1, 'data', 'pair'),
                     ('facts', 2, 'data', 'coverage'), ('facts', 0, 'data', 'finding', 'resolution')):
            for value in ({}, [], 'value', None):
                self.data = copy.deepcopy(base)
                parent = self.data
                for part in path[:-1]:
                    parent = parent[part]
                parent[path[-1]] = value
                self.schema_invalid()

    def test_review_enums_types_and_empty_text(self):
        base = copy.deepcopy(self.data)
        cases = [(('facts', 0, 'data', 'finding', 'category'), ['unknown', '', 'missing\n']),
                 (('facts', 0, 'data', 'finding', 'assessment'), ['PASS', 'unknown', '']),
                 (('facts', 0, 'data', 'finding', 'consequence'), ['', ' ', '\n']),
                 (('facts', 0, 'data', 'finding', 'resolution', 'status'), ['', 'unknown']),
                 (('facts', 2, 'data', 'coverage', 'compared'), ['false', 0, None]),
                 (('facts', 2, 'data', 'coverage', 'area'), ['', ' ', 'dma\n']),
                 (('facts', 2, 'data', 'coverage', 'read'), ['', ' ']),
                 (('facts', 2, 'data', 'coverage', 'reason'), ['', ' ']),
                 (('facts', 1, 'data', 'pair', 'impl'), [[], [{}]]),
                 (('facts', 1, 'data', 'pair', 'ref'), [[], [{}]]),
                 (('areas',), [[]]), (('triggers',), [['widget']])]
        for path, values in cases:
            for value in values:
                self.data = copy.deepcopy(base)
                owner = self.data
                for part in path[:-1]:
                    owner = owner[part]
                owner[path[-1]] = value
                with self.subTest(path=path, value=value):
                    self.schema_invalid()
        for field in ('reason',):
            self.data = copy.deepcopy(base)
            self.finding.update(self_evident=True, **{field: ' '})
            self.schema_invalid()
        for name, path in (('settlement', ('facts', 0, 'data', 'finding', 'settled_by')),
                           ('impl', ('facts', 1, 'data', 'pair', 'impl')),
                           ('ref', ('facts', 1, 'data', 'pair', 'ref'))):
            self.data = copy.deepcopy(base)
            owner = self.data
            for part in path:
                owner = owner[part]
            owner.append(copy.deepcopy(owner[0]))
            self.schema_invalid()

    def test_resolution_shapes(self):
        for resolution in ({'status': 'open'}, {'status': 'fixed', 'commit': 'a' * 40},
                           {'status': 'wontfix', 'reason': 'Hardware compatibility.'}):
            self.finding['resolution'] = resolution
            self.assertEqual(self.check()[0], 0)
        for resolution in ({'status': 'fixed'}, {'status': 'wontfix'},
                           {'status': 'fixed', 'commit': 'short'},
                           {'status': 'wontfix', 'reason': ' '},
                           {'status': 'open', 'commit': 'a' * 40},
                           {'status': 'open', 'reason': 'Unexpected'},
                           {'status': 'fixed', 'commit': 'a' * 40, 'reason': 'Unexpected'},
                           {'status': 'wontfix', 'reason': 'Declined', 'commit': 'a' * 40}):
            self.finding['resolution'] = resolution
            self.schema_invalid()

    def test_section_payload_agreement_and_kind_boundaries(self):
        base = copy.deepcopy(self.data)
        for index, section, payload in ((0, 'findings', 'finding'), (1, 'correspondence', 'pair'),
                                        (2, 'coverage', 'coverage')):
            self.data = copy.deepcopy(base)
            self.data['facts'][index].pop('data')
            self.schema_invalid()
            self.data = copy.deepcopy(base)
            self.data['facts'][index]['section'] = 'agreements'
            self.schema_invalid()
            self.data = copy.deepcopy(base)
            self.data['facts'][index]['data']['register'] = {'name': 'CTRL', 'offset': '0x0'}
            self.schema_invalid()
        for kind in ('peripheral', 'review'):
            self.data = copy.deepcopy(base)
            if kind == 'peripheral':
                self.data['kind'] = kind
                self.data.pop('notes')
                for fact in self.data['facts']:
                    fact['section'] = 'identity'
            else:
                self.data['facts'] = [specload.load_strict(HERE / 'fixtures/peripheral/widget.spec.yaml')['facts'][0]]
                self.data['facts'][0]['section'] = 'identity'
            self.schema_invalid()
        self.data = copy.deepcopy(base)
        self.data['facts'][0]['section'] = 'registers'
        self.data['facts'][0]['data'] = {'register': {'name': 'CTRL', 'offset': '0x0'}}
        self.schema_invalid()
        self.data = copy.deepcopy(base)
        self.data['facts'][0].pop('data')
        self.data['facts'][0]['section'] = 'gotchas'
        self.schema_invalid()
        self.data = copy.deepcopy(base)
        self.data['facts'][0]['section'] = 'open-questions'
        self.data['facts'][0].pop('data')
        self.data['facts'][0]['todo'] = {'check': 'source', 'text': 'Read it.'}
        self.schema_invalid()

    def test_missing_requires_implementation_search_and_both_sides(self):
        self.finding['category'] = 'missing'
        self.invalid('impl search anchor')
        anchors = self.data['facts'][0]['support'][0]['anchors']
        anchors[0] = {'repo': 'impl', 'path': 'drivers/widget/widget_uart.c', 'search': 'widget_init'}
        self.assertEqual(self.check()[0], 0)
        anchors[:] = anchors[:1]
        self.invalid('both impl and ref')
        self.data['resources']['repos'][0]['role'] = 'source'
        self.invalid('both impl and ref')

    def test_pair_side_roles(self):
        for side, other in (('impl', 'ref'), ('ref', 'impl')):
            anchor = self.data['facts'][1]['data']['pair'][side][0]
            old = anchor['repo']
            anchor['repo'] = other
            self.invalid('pair ' + side + ' needs')
            anchor['repo'] = old
        self.data['resources']['repos'][0]['role'] = 'source'
        self.invalid('role: impl')

    def test_pair_citations_use_normal_guards_and_real_paths(self):
        base = copy.deepcopy(self.data)
        anchor = self.data['facts'][1]['data']['pair']['impl'][0]
        paths = list(speccheck.anchors(self.data['facts'][1], ('facts', 1)))
        self.assertEqual(len(paths), 2)
        self.assertEqual(paths[0][1], ('facts', 1, 'data', 'pair', 'impl', 0))
        self.assertEqual(paths[1][1], ('facts', 1, 'data', 'pair', 'ref', 0))
        for key, value, diagnostic in (('repo', 'missing', 'not in this file'),
                                        ('path', 'unlisted.c', 'not in the files'),
                                        ('lines', [31, 30], 'run backwards'),
                                        ('stale', {'was': 'a' * 40}, 'stale anchor')):
            self.data = copy.deepcopy(base)
            self.data['facts'][1]['data']['pair']['impl'][0][key] = value
            self.invalid(diagnostic)
        self.data = copy.deepcopy(base)
        self.data['resources']['repos'][0].pop('commit')
        self.data['resources']['repos'][0]['ref'] = 'main'
        self.invalid('pins a ref')
        self.data = copy.deepcopy(base)
        self.data['facts'] = [self.data['facts'][1]]
        marker = self.root / 'board-specs.yaml'
        marker.write_text(marker.read_text().replace('GPL-2.0-only, MIT, Apache-2.0', 'MIT'))
        self.invalid('GPL-2.0-only')

    def test_pair_traversal_is_only_at_the_fact_payload(self):
        nested = {'support': [{'class': 'source-observed', 'data': {'pair': {
            'impl': [{'repo': 'ignored'}], 'ref': [{'repo': 'ignored'}]}}}]}
        self.assertEqual(list(speccheck.supports(nested, ())), [(nested['support'][0], ('support', 0))])
        self.assertEqual(list(speccheck.anchors(nested, ())), [])

    def test_review_freshness_covers_pair_pins_settlement_and_payload(self):
        def bases():
            checker = self.checker()
            fresh = records.Freshness(checker)
            self.assertEqual(set(checker.files[0].records), {f['id'] for f in self.data['facts']})
            return {key: fresh.basis(rec)[0] for key, rec in checker.files[0].records.items()}
        before = bases()
        self.assertTrue(all(before.values()))
        self.data['resources']['repos'][0]['commit'] = 'a' * 40
        after = bases()
        self.assertEqual({k for k in before if before[k] != after[k]}, {'f-baud-latch', 'init-pair', 'f-delay'})
        before = after
        self.finding['settled_by'][0]['at'][0]['page'] = '41'
        after = bases()
        self.assertEqual({k for k in before if before[k] != after[k]}, {'f-baud-latch'})
        before = after
        self.data['facts'][2]['data']['coverage']['compared'] = True
        after = bases()
        self.assertEqual({k for k in before if before[k] != after[k]}, {'dma-coverage'})


class Generated(ReviewFixture):
    def test_generated_review_projection_exact(self):
        file = self.checker().files[0]
        summary = peripheral.generated(file)
        self.assertEqual(summary['findings'], [dict(f['data']['finding'], fact=f['id'])
                                              for f in self.data['facts'] if 'finding' in f.get('data', {})])
        self.assertEqual(summary['pairs'], [dict(self.data['facts'][1]['data']['pair'], fact='init-pair')])
        self.assertEqual(summary['coverage'], [dict(self.data['facts'][2]['data']['coverage'], fact='dma-coverage')])
        self.assertEqual(summary['verify'], [{'fact': 'f-delay', 'text': 'The block may become ready after the first write.'}])
        self.assertEqual(summary['questions'], [dict(f['todo'], fact=f['id']) for f in self.data['facts'] if 'todo' in f])
        self.assertEqual(summary['classes'], ['databook', 'src'])
        for field in ('requirement', 'todo'):
            self.data['facts'][3].pop(field, None)
        self.assertEqual(peripheral.generated(self.checker().files[0])['verify'], summary['verify'])

    def assert_views(self, checker, titles):
        summary = peripheral.generated(checker.files[0])
        md = render_md.View()
        render_md._generated(md, checker.files[0])
        html = Tables(render_html.generated(checker.files[0]))
        for title, entries in titles(summary):
            with self.subTest(title=title):
                self.assertIn(title, html.tables)
                keys = list(dict.fromkeys(k for e in entries for k in e if k not in ('note', 'files')))
                expected = [[render_md._value(e.get(k, '')) for k in keys] for e in entries]
                actual = html.tables[title][0]
                actual_keys = actual[0]
                self.assertEqual([[row[actual_keys.index(k)] for k in keys] for row in actual[1:]], expected)
                md_rows = ['| ' + ' | '.join(render_md.escape(render_md._value(e.get(k, ''))).replace('|', '\\|')
                                            for k in keys) + ' |' for e in entries]
                heading = '### ' + render_md.escape(title)
                self.assertIn(heading + '\n', '\n'.join(md))
                section = '\n'.join(md).split(heading + '\n', 1)[1].split('\n#', 1)[0]
                self.assertEqual([line for line in section.splitlines() if line.startswith('| ')][2:], md_rows)
        expected_verify = [row['fact'] + ': ' + row['text'] for row in summary['verify']]
        self.assertEqual(html.verify, expected_verify)
        heading = '## Verify on hardware (generated)\n'
        self.assertIn(heading, '\n'.join(md))
        section = '\n'.join(md).split(heading)[1].split('\n#', 1)[0]
        self.assertEqual([line for line in section.splitlines() if line.startswith('- ')],
                         ['- ' + render_md.code(row['fact']) + ': ' + render_md.escape(row['text']) for row in summary['verify']])

    def test_exact_review_tables_in_both_views(self):
        self.assert_views(self.checker(), lambda s: [(title, s[key]) for title, key in (
            ('Findings (generated)', 'findings'), ('Correspondence (generated)', 'pairs'),
            ('Comparison coverage (generated)', 'coverage'), ('Open questions (generated)', 'questions'))] +
            [('Area confidence', self.data['areas']), ('Canonical references (generated)', s['references'])])

    def test_exact_peripheral_tables_in_both_views(self):
        self.data = specload.load_strict(HERE / 'fixtures/peripheral/widget.spec.yaml')
        rows = peripheral.register_rows(peripheral.generated(self.checker().files[0]))
        self.assertEqual(rows, [
            {'fact': 'reg-ctrl', 'offset': '0x0', 'name': 'WIDGET_CTRL', 'width': 32,
             'access': 'rw', 'reset': '0x0', 'fields': [{'id': 'en', 'name': 'WIDGET_CTRL_EN',
                                                     'bits': [0, 0], 'meaning': 'block enable'}]},
            {'fact': 'reg-baud', 'offset': '0x4', 'name': 'WIDGET_BAUD', 'width': 32,
             'access': 'rw', 'reset': '', 'fields': []},
            {'fact': 'reg-lcr', 'offset': '0x8', 'name': 'WIDGET_LCR', 'width': 32,
             'access': 'rw', 'reset': '', 'fields': [{'id': 'format', 'name': 'WIDGET_LCR_8N1',
                                                  'bits': [0, 1], 'meaning': '8N1 format'}]}])
        self.assert_views(self.checker(), lambda s: [('Register map (generated)', peripheral.register_rows(s)),
                                                   ('Open questions (generated)', s['questions'])])
        html = render_html.render(self.checker(), with_status=True)
        for value in ('write 0 to CTRL', 'Payload entry seq-init.s1', 'widget_frame', 'frame_payload',
                      'badge requirement">as-implemented', 'badge status-unverified'):
            self.assertIn(value, html)

    def test_html_payload_support_requirement_status_and_note(self):
        self.data = specload.load_strict(HERE / 'fixtures/peripheral/widget.spec.yaml')
        self.data['facts'][0]['requirement'] = 'as-implemented'
        self.data['facts'][0]['data']['fields'][0]['note'] = 'Supported child **note**.'
        checker = self.checker()
        file = checker.files[0]
        status = {e['file']: {r['key']: r for r in e['rows']} for e in checker.status}
        status[file]['reg-ctrl.en'].update(verdict='PASS', status='current')
        html = render_html.payload(checker, file.records['reg-ctrl'], status, True)
        for text in ('lines 5–5', 'badge requirement">as-implemented', 'badge verdict-pass',
                     'badge status-current', 'Supported child <strong>note</strong>'):
            self.assertIn(text, html)
        plain = render_html.payload(checker, file.records['reg-ctrl'], status, False)
        self.assertNotIn('badge verdict-pass', plain)
        self.assertNotIn('badge status-current', plain)

    def test_full_views_emit_all_generated_sections(self):
        for data in (self.data, specload.load_strict(HERE / 'fixtures/peripheral/widget.spec.yaml')):
            self.data = data
            self.write()
            for fmt, key in (('md', 'markdown'), ('html', 'html')):
                code, result = run('render', self.root, '--format', fmt)
                self.assertEqual(code, 0, result)
                view = result[key]
                for title in ('Provenance notice (generated)', 'Canonical references (generated)',
                              'Verify on hardware (generated)', 'Open questions (generated)'):
                    escaped = render_md.escape(title) if title in (
                        'Canonical references (generated)', 'Open questions (generated)') else title
                    self.assertIn(escaped if fmt == 'md' else title, view)
                if fmt == 'html':
                    self.assertIn('Support classes: databook, src.', view)
                    refs = Tables(view).tables['Canonical references (generated)'][0]
                    self.assertEqual(len(refs) - 1, sum(len(self.data['resources'][k]) for k in ('documents', 'repos')))

    def test_payloadless_overlay_lists_both_modes_both_kinds(self):
        from test_schema import dump
        overlay = Path(self.tmp.name) / 'overlay'
        overlay.mkdir()
        (overlay / 'board-specs.yaml').write_text('format: 2\nlayer: local\nname: local\nlicense: Apache-2.0\naccepts: [GPL-2.0-only, MIT]\n')
        for data in (self.data, specload.load_strict(HERE / 'fixtures/peripheral/widget.spec.yaml')):
            self.data = data
            (overlay / 'widget-overlay.spec.yaml').write_text(dump({'format': 2, 'kind': 'overlay',
                'overlays': data['id'], 'facts': [{'id': 'observe', 'section': 'identity', 'title': 'Clock',
                'claim': 'Observe the clock.', 'todo': {'check': 'hardware', 'text': 'Measure it.'}}]}))
            self.write()
            for flags in ((), ('--merged',)):
                for fmt, key in (('md', 'markdown'), ('html', 'html')):
                    code, result = run('render', self.root, overlay, '--format', fmt, *flags)
                    self.assertEqual(code, 0, result)
                    expected = '- `observe`: ' if fmt == 'md' else '<li><code>observe</code>: '
                    self.assertEqual(result[key].count(expected), 1)


class ReviewPins(GitFixture):
    def test_pair_resolves_and_drift_rewrites_only_the_selected_side(self):
        self.data['kind'] = 'review'
        self.data.pop('triggers')
        source = self.data['resources']['repos'][0]
        self.data['resources']['repos'] = [copy.deepcopy(dict(source, name=side, role=side))
                                         for side in ('impl', 'ref')]
        anchor = {'path': 'code.c', 'lines': [2, 2], 'symbol': 'VALUE'}
        self.data['facts'] = [{'id': 'pair', 'section': 'correspondence', 'claim': 'VALUE maps to VALUE.',
            'data': {'pair': {side: [copy.deepcopy(dict(anchor, repo=side))] for side in ('impl', 'ref')}},
            'support': [{'class': 'src', 'anchors': [copy.deepcopy(dict(anchor, repo='ref'))]}]}]
        self.assertEqual([at for anchor, at in speccheck.anchors(self.data['facts'][0], ('facts', 0))],
                         [('facts', 0, 'support', 0, 'anchors', 0),
                          ('facts', 0, 'data', 'pair', 'impl', 0),
                          ('facts', 0, 'data', 'pair', 'ref', 0)])
        self.write()
        code, result = run('resolve', self.path, '--repo', f'impl={self.repo}', '--repo', f'ref={self.repo}')
        self.assertEqual(code, 0, result)
        self.assertEqual(result['resolved'], 3)
        (self.repo / 'code.c').write_text('// inserted\n' + SOURCE)
        revision = self.commit_all()
        code, result = run('drift', revision, self.path, '--pin', 'impl', '--repo', f'impl={self.repo}',
                           '--repo', f'ref={self.repo}', '--rewrite')
        self.assertEqual(code, 0, result)
        self.assertEqual([r['status'] for r in result['changes']], ['moved'])
        data = specload.load_strict(self.path)
        self.assertEqual(data['facts'][0]['data']['pair']['impl'][0]['lines'], [3, 3])
        self.assertEqual(data['facts'][0]['data']['pair']['ref'][0]['lines'], [2, 2])
        self.assertEqual(data['resources']['repos'][0]['commit'], revision)
        self.assertEqual(data['resources']['repos'][1]['commit'], self.commit)
        self.assertEqual(run('validate', self.path)[0], 0)
        self.assertEqual(run('resolve', self.path, '--repo', f'impl={self.repo}', '--repo', f'ref={self.repo}')[0], 0)
