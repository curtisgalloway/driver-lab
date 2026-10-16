# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Board atlas page (render --format atlas): selection, memory map, escaping and the CLI."""

import contextlib
import io
import json
from pathlib import Path
import re
import sys
import tempfile
from types import SimpleNamespace
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'scripts'))
import atlas
import spec
import speccheck
from test_check import chip, fact, marker


def relating(fid, target, relation='refines', claim=None):
    text = fact(fid, f'    relates: [{{fact: "{target}", relation: {relation}}}]\n')
    return text.replace(f'claim: C {fid}.', 'claim: ' + claim) if claim else text


def kind(text, new):
    return text.replace('kind: chip', 'kind: ' + new, 1)


INSTANCES = ('instances:\n'
             '  - {id: u0, name: UART0, ip: wuart, reg: "0x7e201000", irq: {kind: SPI, number: 5}, '
             'clocks: [uclk], support: [{class: databook, doc: trm, at: [{section: "2"}]}]}\n'
             '  - {id: t0, name: Timer, ip: wuart, reg: "0x10000000", irq: {kind: PPI, number: 14}, clocks: [], '
             'support: [{class: databook, doc: trm, at: [{section: "3"}]}]}\n'
             '  - {id: g0, name: GPIO, ip: wuart, reg: null, irq: {kind: SPI, number: 6}, clocks: [], '
             'todo: {check: document, text: find the base.}}\n')


class Atlas(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'root'
        self.root.mkdir()
        (self.root / 'board-specs.yaml').write_text(marker('atlas-root'))
        files = {
            'wb': kind(chip('wb', relating('console', 'wsoc#uart-base',
                                           claim='"Console when 1 < 2 & 3 > 2."'),
                            head='parts: [wsoc]\ncache: wb-resources\n'), 'board'),
            'wsoc': kind(chip('wsoc', fact('uart-base').replace('C uart-base.', 'UART0 sits at 0x7E201000.'),
                              head='cache: wsoc-resources\n' + INSTANCES), 'soc'),
            'wuart': kind(chip('wuart', fact('fifo').replace('quick-facts', 'standards')), 'ip'),
            'wpmic': chip('wpmic', relating('rail', 'wsoc#uart-base', 'qualifies')
                           + relating('off', 'unrelated#reset')),
            'farther': chip('farther', relating('x', 'wpmic#rail')),
            'unrelated': chip('unrelated'),
        }
        for name, text in files.items():
            (self.root / f'{name}.spec.yaml').write_text(text)

    def checker(self):
        args = SimpleNamespace(roots=[self.root], context_root=[], require_license=False, public_skill=[])
        checker = spec._run_check(args)
        self.assertEqual([str(f) for f in checker.findings if f.level == 'error'], [])
        return checker

    def cli(self, *extra):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = spec.main(['render', str(self.root), '--format', 'atlas', '--json', *extra])
        return code, json.loads(out.getvalue())

    def test_selection_is_parts_instances_and_one_link_away(self):
        d = atlas.data(self.checker(), 'wb')
        joins = {s['id']: (s['parent'], s['join']) for s in d['specs']}
        self.assertEqual(joins, {'wb': (None, ''), 'wsoc': ('wb', 'parts'), 'wuart': ('wsoc', 'ip'),
                                 'wpmic': ('wsoc', 'related')})
        self.assertEqual({f['spec'] for f in d['facts']}, set(joins))

    def test_relations_resolve_to_full_references(self):
        d = atlas.data(self.checker(), 'wb')
        console = next(f for f in d['facts'] if f['id'] == 'console')
        self.assertEqual(console['relates'], [{'to': 'wsoc@atlas-root#uart-base', 'relation': 'refines'}])
        self.assertEqual(d['outside_links'], 1)
        off = next(f for f in d['facts'] if f['id'] == 'off')
        self.assertEqual(off['relates'], [])

    def test_memory_map_orders_by_address_skips_null_and_finds_citing_facts(self):
        d = atlas.data(self.checker(), 'wb')
        rows = d['memory_map']
        self.assertEqual([r['key'].split('#')[1] for r in rows], ['u0', 't0'])
        self.assertEqual(rows[0]['cites'], ['wsoc@atlas-root#uart-base'])
        self.assertEqual(rows[0]['gap'], '1.7 GiB')
        uart = next(i for i in d['instances'] if i['id'] == 'u0')
        self.assertEqual((uart['reg'], uart['irq'], uart['clocks']), ('0x7E201000', 'SPI 5', ['uclk']))
        self.assertEqual(next(i for i in d['instances'] if i['id'] == 'g0')['reg'], '')

    def test_author_text_is_escaped_and_the_page_loads_no_outside_script(self):
        page = atlas.page(self.checker(), 'wb')
        self.assertEqual(re.findall(r'<script[^>]*\bsrc=', page), [])
        self.assertEqual(re.findall(r'<link\b', page), [])
        payload = re.search(r'id="spec-data">(.*?)</script>', page, re.S).group(1)
        self.assertNotIn('<', payload)
        console = next(f for f in json.loads(payload)['facts'] if f['id'] == 'console')
        self.assertIn('1 &lt; 2 &amp; 3 &gt; 2', console['claim_html'])

    def test_output_is_deterministic(self):
        first = atlas.page(self.checker(), 'wb')
        (self.root / 'wpmic.spec.yaml').touch()
        self.assertEqual(first, atlas.page(self.checker(), 'wb'))

    def test_any_spec_can_be_the_center(self):
        d = atlas.data(self.checker(), 'wuart')
        self.assertEqual([s['id'] for s in d['specs']], ['wuart'])
        self.assertEqual(d['memory_map'], [])

    def test_unknown_spec_is_a_usage_error(self):
        with self.assertRaises(speccheck.UsageError):
            atlas.data(self.checker(), 'nope')

    def test_cli_needs_spec_and_returns_html_key(self):
        code, result = self.cli()
        self.assertEqual((code, result['error']), (spec.EXIT_USAGE, 'usage'))
        self.assertIsNone(result['html'])
        code, result = self.cli('--spec', 'nope')
        self.assertEqual((code, result['error']), (spec.EXIT_USAGE, 'usage'))
        code, result = self.cli('--spec', 'wb')
        self.assertEqual(code, spec.EXIT_OK)
        self.assertTrue(result['html'].startswith('<!doctype html>'))
        self.assertIn('<title>Widget atlas</title>', result['html'])

    def test_missing_spec_is_a_usage_error_even_when_files_have_errors(self):
        (self.root / 'wb.spec.yaml').write_text('format: 2\nkind: board\n')
        code, result = self.cli()
        self.assertEqual((code, result['error']), (spec.EXIT_USAGE, 'usage'))

    def test_small_base_addresses_cite_nothing(self):
        text = (self.root / 'wsoc.spec.yaml').read_text().replace('"0x10000000"', '"0x100"')
        (self.root / 'wsoc.spec.yaml').write_text(text.replace('UART0 sits at', 'Offset 0x100; UART0 sits at'))
        rows = atlas.data(self.checker(), 'wb')['memory_map']
        self.assertEqual(rows[-1]['cites'], [])


def peripheral(sid, head='', facts=None):
    """A kind: peripheral spec with one identity fact (or the facts given)."""
    body = facts if facts is not None else (
        '  - id: ident\n    section: identity\n    title: T\n    claim: C.\n'
        '    support: [{class: databook, doc: trm, at: [{section: "1"}]}]\n')
    return ('format: 2\nkind: peripheral\nid: ' + sid + '\nname: P ' + sid + '\n' + head
            + 'resources:\n  documents:\n    - {name: trm, class: databook, title: TRM, '
            'url: "https://example.invalid/trm.pdf", pages: 80}\nfacts:\n' + body)


class AtlasPeripherals(unittest.TestCase):
    """#127: peripheral specs join through `describes` and `instances[].peripheral`, premises
    count as fact links, links to rows on the page are not outside links, and specs the page
    leaves out are listed."""

    checker = Atlas.checker

    def setUp(self):
        Atlas.setUp(self)
        soc = (self.root / 'wsoc.spec.yaml').read_text()
        soc = soc.replace('  - {id: g0, name: GPIO, ip: wuart,', '  - {id: g0, name: GPIO, peripheral: wgpio,')
        (self.root / 'wsoc.spec.yaml').write_text(soc)
        files = {
            'wdma': peripheral('wdma', 'describes: [wsoc]\n'),
            'wgpio': peripheral('wgpio'),
            'wpwm': peripheral('wpwm', 'describes: [wpmic]\n'),
            'wclk': kind(chip('wclk', (
                '  - id: derived\n    section: quick-facts\n    title: D\n    claim: D.\n'
                '    support:\n      - class: inference\n        premises:\n'
                '          - fact: "wsoc#uart-base"\n        derivation: it follows\n'
                '    todo: {check: hardware, text: check it.}\n')), 'chip'),
            'wrow': chip('wrow', relating('at-row', 'wsoc#u0') + relating('at-fact', 'wb#console')
                         + relating('at-unmapped', 'wsoc#g0')),
        }
        for name, text in files.items():
            (self.root / f'{name}.spec.yaml').write_text(text)

    def test_peripheral_specs_join_by_describes_and_by_instance(self):
        d = atlas.data(self.checker(), 'wb')
        joins = {s['id']: (s['parent'], s['join']) for s in d['specs']}
        self.assertEqual(joins['wdma'], ('wsoc', 'programming'))
        self.assertEqual(joins['wgpio'], ('wsoc', 'programming'))
        # describes names a spec one link away, not the board or a part: not placed
        self.assertNotIn('wpwm', joins)
        gpio = next(i for i in d['instances'] if i['id'] == 'g0')
        self.assertEqual((gpio['ip'], gpio['peripheral']), ('', 'wgpio'))
        uart = next(i for i in d['instances'] if i['id'] == 'u0')
        self.assertEqual((uart['ip'], uart['peripheral']), ('wuart', ''))

    def test_inference_premises_are_fact_links(self):
        joins = {s['id']: s['join'] for s in atlas.data(self.checker(), 'wb')['specs']}
        self.assertEqual(joins['wclk'], 'related')

    def test_links_to_rows_on_the_page_are_not_outside_links(self):
        d = atlas.data(self.checker(), 'wb')
        joins = {s['id']: (s['parent'], s['join']) for s in d['specs']}
        self.assertEqual(joins['wrow'], ('wsoc', 'related'))  # two links to wsoc, one to wb
        at_row = next(f for f in d['facts'] if f['id'] == 'at-row')
        self.assertEqual(at_row['relates'], [])
        at_fact = next(f for f in d['facts'] if f['id'] == 'at-fact')
        self.assertEqual(at_fact['relates'], [{'to': 'wb@atlas-root#console', 'relation': 'refines'}])
        # wpmic#off is outside; so is wsoc#g0, a row with no base the memory map does not draw
        self.assertEqual((d['row_links'], d['outside_links']), (1, 2))

    def test_specs_left_out_are_listed_by_kind(self):
        d = atlas.data(self.checker(), 'wb')
        self.assertEqual(d['unplaced'], [
            {'id': 'farther', 'kind': 'chip', 'facts': 1},
            {'id': 'unrelated', 'kind': 'chip', 'facts': 1},
            {'id': 'wpwm', 'kind': 'peripheral', 'facts': 1},
        ])
        placed = {s['id'] for s in d['specs']}
        self.assertFalse(placed & {u['id'] for u in d['unplaced']})
        self.assertIn('DATA.unplaced', (Path(atlas.__file__).parent / 'atlas.js').read_text())

    def test_context_roots_are_not_listed(self):
        ctx = Path(self.temp.name) / 'ctx'
        ctx.mkdir()
        (ctx / 'board-specs.yaml').write_text(marker('ctx-root'))
        (ctx / 'lonely.spec.yaml').write_text(chip('lonely'))
        args = SimpleNamespace(roots=[self.root], context_root=[ctx], require_license=False,
                               public_skill=[])
        checker = spec._run_check(args)
        for merged in (False, True):
            ids = {u['id'] for u in atlas.data(checker, 'wb', merged=merged)['unplaced']}
            self.assertNotIn('lonely', ids)
            self.assertIn('unrelated', ids)


if __name__ == '__main__':
    unittest.main()
