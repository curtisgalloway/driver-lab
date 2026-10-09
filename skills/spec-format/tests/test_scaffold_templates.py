#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Exercise every YAML scaffold through the real format 2 CLI.

Included in the existing spec-format discovery command, using its hash-pinned environment.
Substitution is text-based, so quoting and scalar types in the shipped templates are tested.
"""

import contextlib
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
TEMPLATES = HERE.parents[1] / 'board-spec-scaffold' / 'templates'
sys.path.insert(0, str(HERE.parent / 'scripts'))
import spec as spec_cli
from specload import load_strict

PLACEHOLDER = re.compile(r'<([A-Za-z][A-Za-z0-9 -]*)>')
VALUES = {
    'board-id': 'fixture-board', 'soc-id': 'fixture-soc', 'chip-id': 'fixture-chip',
    'ip-id': 'fixture-ip', 'base-root': 'fixture-docs', 'root-name': 'fixture-source',
    'layer': 'public', 'root-license': 'Apache-2.0', 'docs-license': 'CC-BY-4.0',
    'accepted-license': 'MIT', 'source-license': 'MIT',
    'commit': '1a2b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d',
    'dt-path': 'arch/fixture.dtsi', 'driver-path': 'drivers/fixture.c',
    'dt-license-from': 'spdx-line', 'driver-license-from': 'spdx-line',
    'dt-first': '1', 'dt-last': '3', 'dt-node': '/soc/serial@1000',
    'driver-first': '4', 'driver-last': '6', 'driver-symbol': 'fixture_init',
    'uart-instance': 'uart0', 'uart-base': '0x1000', 'uart-spi': '7',
    'uart-intid': '39', 'uart-clock': 'uartclk', 'uart-page': '12',
    'addressing-page': '4',
}


def substitute(text):
    def value(match):
        key = match.group(1)
        if key in VALUES:
            return VALUES[key]
        if key.endswith('-url'):
            return 'https://example.invalid/' + key
        return key + ' fixture text'
    filled = PLACEHOLDER.sub(value, text)
    if re.search(r'<[^>]*>', filled):
        raise AssertionError('unsubstituted or unrecognized placeholder')
    return filled


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = spec_cli.main([str(a) for a in argv] + ['--json'])
    return code, json.loads(out.getvalue()), err.getvalue()


class ScaffoldTemplates(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR'))
        self.addCleanup(self.temp.cleanup)
        self.tmp = Path(self.temp.name)

    def write(self, template, destination):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(substitute((TEMPLATES / template).read_text(encoding='utf-8')),
                               encoding='utf-8')
        return destination

    def composition(self):
        docs, source, extra = (self.tmp / name for name in ('docs', 'source', 'extra'))
        self.write('docs-root/board-specs.yaml', docs / 'board-specs.yaml')
        self.write('board-specs.yaml', source / 'board-specs.yaml')
        self.write('docs-root/board-specs.yaml', extra / 'board-specs.yaml')
        marker = extra / 'board-specs.yaml'
        marker.write_text(marker.read_text().replace('fixture-docs', 'fixture-extra'))
        for kind, id in [('board', 'fixture-board'), ('soc', 'fixture-soc'),
                         ('chip', 'fixture-chip'), ('ip', 'fixture-ip')]:
            self.write(kind + '.spec.yaml', docs / (id + '.spec.yaml'))
        self.write('overlay.spec.yaml', source / 'source-overlay.spec.yaml')
        self.write('docs-root/overlay.spec.yaml', extra / 'docs-overlay.spec.yaml')
        return docs, source, extra

    def test_every_template_validates_after_text_substitution(self):
        paths = sorted(TEMPLATES.rglob('*.yaml'))
        self.assertEqual({str(p.relative_to(TEMPLATES)) for p in paths}, {
            'board.spec.yaml', 'soc.spec.yaml', 'chip.spec.yaml', 'ip.spec.yaml',
            'overlay.spec.yaml', 'board-specs.yaml', 'docs-root/board-specs.yaml',
            'docs-root/overlay.spec.yaml',
        })
        for template in paths:
            with self.subTest(template=template.relative_to(TEMPLATES)):
                path = self.write(template.relative_to(TEMPLATES),
                                  self.tmp / template.relative_to(TEMPLATES))
                code, result, err = run('validate', path)
                self.assertEqual(code, 0, (result, err))
                self.assertTrue(result['ok'])
                self.assertEqual(result['findings'], [])

    def test_composition_and_cross_root_references_check(self):
        docs, source, extra = self.composition()
        code, result, err = run('check', docs, source, extra, '--require-license')
        self.assertEqual(code, 0, (result, err))
        self.assertEqual(result['specs'], 6)
        self.assertFalse([f for f in result['findings'] if f['level'] == 'error'])
        self.assertTrue(result['verification']['unverified'])

    def test_documents_only_templates_have_no_repos_and_check(self):
        docs, _, extra = self.composition()
        self.assertEqual(load_strict(docs / 'board-specs.yaml')['accepts'], [])
        for root in (docs, extra):
            for path in root.glob('*.spec.yaml'):
                self.assertNotIn('repos', load_strict(path).get('resources', {}))
        code, result, err = run('check', docs, extra, '--require-license')
        self.assertEqual(code, 0, (result, err))

    def test_source_overlay_is_refused_by_a_documents_only_root(self):
        docs, source, _ = self.composition()
        marker = source / 'board-specs.yaml'
        marker.write_text(marker.read_text().replace('accepts: [MIT]', 'accepts: []'))
        code, result, err = run('check', docs, source, '--require-license')
        self.assertEqual(code, 1, (result, err))
        self.assertTrue(any('license gate' in f['message'] and f['level'] == 'error'
                            for f in result['findings']))


if __name__ == '__main__':
    unittest.main()
