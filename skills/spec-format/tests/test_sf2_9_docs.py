# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Execute SF2-9's documented commands and record templates against SF2-7 fixtures.

Only placeholder substitution is allowed: the command arguments come from the shipped text.
Review implementation bytes are synthetic stand-ins, not evidence of hardware correctness.
"""

import json
import os
from pathlib import Path
import re
import shutil
import shlex
import subprocess
import sys
import tempfile
import unittest

import yaml

HERE = Path(__file__).resolve().parent
SKILLS = HERE.parents[1]
SPEC = HERE.parent / 'scripts' / 'spec.py'
GATE = SKILLS / 'hardware-investigator' / 'scripts' / 'license_gate.py'
FIX = HERE / 'fixtures'
INVESTIGATOR = SKILLS / 'hardware-investigator'
DOCUMENTS = [
    'peripheral-spec/SKILL.md',
    'peripheral-spec/templates/spec-subagent-prompt.md',
    'peripheral-spec/templates/verifier-prompt.md',
    'reference-driver-review/SKILL.md',
    'reference-driver-review/templates/review-subagent-prompt.md',
    'reference-driver-review/templates/verifier-prompt.md',
    'hardware-investigator/SKILL.md',
    'hardware-investigator/WORKED-EXAMPLE.md',
]
PLACEHOLDER = re.compile(r'<([A-Za-z][A-Za-z0-9 ._-]*)>')
FENCE = re.compile(r'^ *```(bash|yaml)\n(.*?)^ *```[ \t]*$', re.M | re.S)


def invoke(*args):
    return subprocess.run([str(a) for a in args], capture_output=True, text=True,
                          timeout=30, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})


def git(repo, *args):
    proc = invoke('git', '-C', repo, '-c', 'user.name=Fixture author',
                  '-c', 'user.email=fixture@example.com', '-c', 'commit.gpgsign=false',
                  *args)
    if proc.returncode:
        raise AssertionError(proc.stdout + proc.stderr)
    return proc.stdout.strip()


def fill(text, values, command=False):
    def value(match):
        key = match.group(1)
        if key not in values:
            raise AssertionError('unknown executable placeholder: ' + key)
        return shlex.quote(str(values[key])) if command else str(values[key])
    return PLACEHOLDER.sub(value, text)


class SkillDocumentation(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR'))
        self.addCleanup(self.scratch.cleanup)
        self.tmp = Path(self.scratch.name)
        self.source = self.tmp / 'linux'
        shutil.copytree(INVESTIGATOR / 'examples/sources/widget-linux', self.source)
        self.impl = self.tmp / 'impl'
        impl_file = self.impl / 'drivers/widget/widget_uart.c'
        impl_file.parent.mkdir(parents=True)
        impl_file.write_text('// SPDX-License-Identifier: MIT\n' + '\n' * 27 +
                             'void widget_init(void) {\n'
                             '    writel(WIDGET_LCR_8N1, base + WIDGET_LCR);\n'
                             '    writel(divisor, base + WIDGET_BAUD);\n}\n')
        self.fw = self.tmp / 'fw'
        shutil.copytree(INVESTIGATOR / 'examples/sources/widget-fw', self.fw)
        self.commits = {}
        for name, repo in [('linux', self.source), ('impl', self.impl), ('fw', self.fw)]:
            git(repo, 'init', '-q')
            git(repo, 'add', '.')
            git(repo, 'commit', '-q', '-m', 'fixture')
            self.commits[name] = git(repo, 'rev-parse', 'HEAD')
        with (self.source / 'drivers/tty/serial/widget.c').open('a') as stream:
            stream.write('\n/* Uncited addition for drift. */\n')
        git(self.source, 'add', 'drivers/tty/serial/widget.c')
        git(self.source, 'commit', '-q', '-m', 'uncited addition')
        self.new_source = git(self.source, 'rev-parse', 'HEAD')
        with impl_file.open('a') as stream:
            stream.write('\n/* Uncited addition for drift. */\n')
        git(self.impl, 'add', 'drivers/widget/widget_uart.c')
        git(self.impl, 'commit', '-q', '-m', 'uncited addition')
        self.new_impl = git(self.impl, 'rev-parse', 'HEAD')
        for name in ('peripheral', 'review'):
            dest = self.tmp / name
            shutil.copytree(FIX / name, dest)
            for file in dest.glob('*.spec.yaml'):
                file.write_text(file.read_text().replace('1' * 40, self.commits['linux'])
                                .replace('2' * 40, self.commits['impl']))
        for name in ('gpl', 'permissive'):
            shutil.copytree(INVESTIGATOR / 'examples/roots' / name, self.tmp / name)
        for name in ('linux', 'fw'):
            file = self.tmp / ('answer-' + name + '.facts.yaml')
            source = INVESTIGATOR / 'examples/expected' / file.name
            file.write_text(source.read_text().replace('1' * 40, self.commits[name]))

    def values(self, document):
        review = document.startswith('reference-driver-review/')
        investigator = document.startswith('hardware-investigator/')
        root = self.tmp / ('review' if review else 'gpl' if investigator else 'peripheral')
        return {
            'python': sys.executable, 'spec.py': SPEC, 'gate.py': GATE,
            'root': root, 'permissive-root': self.tmp / 'permissive',
            'source-checkout': self.source, 'impl-checkout': self.impl,
            'ref-checkout': self.source, 'fw-checkout': self.fw,
            'spec': self.tmp / 'peripheral/widget.spec.yaml',
            'review': self.tmp / 'review/widget-review.spec.yaml',
            'register-spec': self.tmp / 'peripheral/widget.spec.yaml',
            'register-root': self.tmp / 'peripheral',
            'header': 'drivers/tty/serial/widget.c',
            'facts': self.tmp / 'answer-linux.facts.yaml',
            'facts-fw': self.tmp / 'answer-fw.facts.yaml',
            'new-commit': self.new_impl if review else self.new_source,
            'source-commit': self.commits['linux'], 'ref-commit': self.commits['linux'],
            'impl-commit': self.commits['impl'], 'source-license': 'GPL-2.0-only',
            'file-license': 'Apache-2.0', 'copyright-year': '2026',
            'copyright-holder': 'Fixture authors', 'device-id': 'template-widget',
            'device-name': 'Template Widget UART', 'review-id': 'template-review',
            'review-name': 'Template Widget review',
        }

    def commands(self, document):
        text = (SKILLS / document).read_text()
        values = self.values(document)
        previous = 0
        count = 0
        for match in FENCE.finditer(text):
            prefix = text[previous:match.start()]
            previous = match.end()
            if match.group(1) != 'bash':
                continue
            expected = 1 if '**Expected exit: 1.**' in prefix else 0
            for line in match.group(2).replace('\\\n', '').splitlines():
                if not line.strip():
                    continue
                args = shlex.split(fill(line, values, command=True))
                self.assertEqual(args[0], sys.executable)
                proc = invoke(*args)
                output = proc.stdout + proc.stderr
                self.assertEqual(proc.returncode, expected, (document, line, output))
                if args[1] == str(SPEC) and args[2] in ('resolve', 'show'):
                    self.assertRegex(output, r'[1-9][0-9]* anchor\(s\) resolved, 0 skipped')
                if args[1] == str(SPEC) and args[2] == 'inventory':
                    self.assertIn('inventory: 5 names; 5 covered; 0 unknown values', output)
                    self.assertIn('result: PASS', output)
                if expected == 1:
                    self.assertRegex(output, 'refused:|is not accepted')
                count += 1
        self.assertGreater(count, 0, document)
        return count

    def test_peripheral_skill_commands(self):
        self.assertEqual(self.commands(DOCUMENTS[0]), 6)

    def test_peripheral_prompt_commands(self):
        self.assertEqual(self.commands(DOCUMENTS[1]), 4)
        self.assertEqual(self.commands(DOCUMENTS[2]), 5)

    def test_review_skill_commands(self):
        self.assertEqual(self.commands(DOCUMENTS[3]), 6)

    def test_review_prompt_commands(self):
        self.assertEqual(self.commands(DOCUMENTS[4]), 4)
        self.assertEqual(self.commands(DOCUMENTS[5]), 5)

    def test_investigator_skill_and_worked_example_commands(self):
        self.assertEqual(self.commands(DOCUMENTS[6]), 5)
        self.assertEqual(self.commands(DOCUMENTS[7]), 13)

    def test_record_templates_validate_check_and_resolve(self):
        for document in (DOCUMENTS[1], DOCUMENTS[4]):
            with self.subTest(document=document):
                values = self.values(document)
                blocks = [m.group(2) for m in FENCE.finditer((SKILLS / document).read_text())
                          if m.group(1) == 'yaml']
                self.assertEqual(len(blocks), 1)
                root = self.tmp / ('template-' + document.split('/')[0])
                root.mkdir()
                shutil.copy(FIX / 'peripheral/board-specs.yaml', root)
                path = root / 'template.spec.yaml'
                path.write_text(fill(blocks[0], values))
                bindings = []
                repos = {'linux': self.source, 'impl': self.impl, 'ref': self.source}
                for entry in yaml.safe_load(path.read_text())['resources']['repos']:
                    bindings.extend(['--repo', f"{entry['name']}={repos[entry['name']]}"])
                for args in (['validate', path], ['check', root, '--require-license'],
                             ['resolve', path, '--root', root, *bindings]):
                    proc = invoke(sys.executable, SPEC, *args, '--json')
                    result = json.loads(proc.stdout)
                    self.assertEqual(proc.returncode, 0, result)
                    self.assertTrue(result['ok'], result)
                header = path.read_text().splitlines()[:2]
                self.assertEqual(header, ['# SPDX-FileCopyrightText: 2026 Fixture authors',
                                          '# SPDX-License-Identifier: Apache-2.0'])

    def test_overlay_uses_the_documented_resolve_show_commands(self):
        text = (SKILLS / DOCUMENTS[3]).read_text()
        values = self.values(DOCUMENTS[3])
        values['review'] = self.tmp / 'review/widget-overlay.spec.yaml'
        executed = 0
        for match in FENCE.finditer(text):
            if match.group(1) != 'bash':
                continue
            for line in match.group(2).splitlines():
                args = shlex.split(fill(line, values, command=True))
                if len(args) < 3 or args[2] not in ('resolve', 'show'):
                    continue
                proc = invoke(*args)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                self.assertRegex(proc.stdout, r'[1-9][0-9]* anchor\(s\) resolved, 0 skipped')
                executed += 1
        self.assertEqual(executed, 2)

    def test_current_procedures_have_no_format_one_citation_rules(self):
        for document in DOCUMENTS:
            with self.subTest(document=document):
                text = (SKILLS / document).read_text()
                self.assertNotRegex(text, r'Source pin:|\[(?:src|impl|ref|doc):')
                self.assertNotIn('anchor_check.py', text)
                self.assertNotIn('inventory_check.py', text)
                if document != DOCUMENTS[7]:
                    self.assertIn('FORMAT-1.md', text)
        for name in ('peripheral-spec', 'reference-driver-review', 'hardware-investigator'):
            archive = (SKILLS / name / 'FORMAT-1.md').read_text()
            self.assertIn('retained until SF2-12', archive)
            self.assertIn('Source pin:' if name != 'reference-driver-review' else 'Impl pin:', archive)


if __name__ == '__main__':
    unittest.main()
