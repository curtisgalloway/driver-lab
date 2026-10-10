# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""SF2-5 guard mutations in TMPDIR; only assertion failures (with no errors) count as kills.

Run with the hash-pinned Python interpreter. The working tree is never mutated; logs and
results.json stay in a scratch copy. A failed baseline, crash or surviving mutation exits 1.
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
MUTATIONS = [
    ('html-disabled', 'scripts/specmd.py', 'parser.options["html"] = False', 'parser.options["html"] = True'),
    ('independent-parser-options', 'scripts/specmd.py', 'parser.options = copy.deepcopy(parser.options)', 'pass'),
    ('all-link-schemes', 'scripts/specmd.py',
     'return url.startswith("#") or bool(re.match(r"^(?:https?|mailto):", url, re.IGNORECASE))', 'return True'),
    ('image-schemes', 'scripts/render_html.py', 'if not specmd.allowed_link(url):', 'if False:'),
    ('image-link-only', 'scripts/render_html.py',
     'out.append(link(token.attrGet("src") or "", label) if\n                           allow_links and not any(links) else label)',
     'out.append(\'<img src="https://example.invalid/x">\')'),
    ('no-nested-label-links', 'scripts/render_html.py',
     'label = emit(token.children or [], False)', 'label = emit(token.children or [], True)'),
    ('no-nested-image-links', 'scripts/render_html.py',
     'allow_links and not any(links) else label)', 'True else label)'),
    ('url-attribute-escaping', 'scripts/render_html.py', 'escape(url, quote=True)', 'url'),
    ('text-escaping', 'scripts/render_html.py', 'out.append(escape(token.content))', 'out.append(token.content)'),
    ('code-escaping', 'scripts/render_html.py', "escape(token.content) + '</code>'", "token.content + '</code>'"),
    ('fence-escaping', 'scripts/render_html.py', "escape(token.content) + '</code></pre>'", "token.content + '</code></pre>'"),
    ('no-fence-attributes', 'scripts/render_html.py', "'<pre><code>' + escape(token.content)",
     "'<pre class=\"badge\"><code>' + escape(token.content)"),
    ('fixed-element-set', 'scripts/render_html.py', "+ tags[tag] + '>'", "+ token.tag + '>'"),
    ('unknown-token-refused', 'scripts/render_html.py', 'raise ValueError("unsupported viewer token: " + kind)',
     'out.append(token.content)'),
    ('notice-escaping', 'scripts/render_html.py', "escape(notice['text'])", "notice['text']"),
    ('structured-escaping', 'scripts/render_html.py', 'return escape(render_md._value(value), quote=True)',
     'return render_md._value(value)'),
    ('repeat-containment', 'scripts/render_html.py', 'if bad:', 'if False:'),
    ('repeat-record-containment', 'scripts/render_html.py', 'if file.record_loaded:', 'if False:'),
    ('context-trust', 'scripts/render_html.py', 'if file.root.context and file.root.untrusted:', 'if False:'),
    ('checked-source-hash', 'scripts/render_html.py', 'hashlib.sha256(file.loaded.raw)',
     'hashlib.sha256(file.path.read_bytes())'),
    ('support-badge', 'scripts/render_html.py', "badge(CLASSES.get(entry['class'], 'class-extension'), entry['class'])", "''"),
    ('origin-badge', 'scripts/render_html.py', "badge('origin', file.root.layer + ' · ' + file.root.label)", "''"),
    ('assumes-badge', 'scripts/render_html.py', "badge('assumes', 'assumes ' + aid)", "''"),
    ('todo-badge', 'scripts/render_html.py', "badge('todo', 'verify on ' + todo['check'])", "''"),
    ('critical-badge', 'scripts/render_html.py', "if data.get('critical'):", 'if False:'),
    ('second-reader', 'scripts/render_html.py',
     "' · second reader missing' if row['second_reader'] == 'missing' else ''", "''"),
    ('contested-badge', 'scripts/render_html.py', "if 'resolution' not in conflict:", 'if False:'),
    ('requirement-assessment', 'scripts/render_html.py', "for key in ('requirement', 'assessment'):", 'for key in ():'),
    ('gap-badge', 'scripts/render_html.py', "out.append(badge('gap', 'Gap'))", 'pass'),
    ('verdict-badge', 'scripts/render_html.py', "out.append(badge(VERDICTS[row['verdict']], text))", 'pass'),
    ('freshness-badge', 'scripts/render_html.py', "out.append(badge(FRESHNESS[row['status']], row['status']))", 'pass'),
    ('carried-status', 'scripts/render_html.py', "(' · carried' if row['carried'] else '')", "''"),
    ('no-partial-view', 'scripts/render_html.py', "'html': None, 'findings'", "'html': '<html>partial</html>', 'findings'"),
    ('source-inventory', 'ci/publish.py', 'for file in checker.files:', 'for file in checker.files[:1]:'),
    ('merged-pages', 'ci/publish.py', "for sid in overlays:", 'for sid in []:'),
    ('publish-containment', 'ci/publish.py', "result[stem + '.html'] = render_html.render(selected, **options)",
     "result[stem + '.html'] = ''"),
    ('publish-completeness', 'ci/publish.py', '    safe_output(args.out, checker)\n    expected = payloads(checker, args)',
     '    return\n    expected = payloads(checker, args)'),
    ('publish-byte-comparison', 'ci/publish.py', "if path.read_bytes() != text.encode('utf-8'):", 'if False:'),
    ('publish-regular-file', 'ci/publish.py', 'if path.is_symlink() or not path.is_file():', 'if not path.is_file():'),
    ('publish-output-symlinks', 'ci/publish.py', 'if any(p.is_symlink() for p in (absolute, *absolute.parents)):', 'if False:'),
    ('publish-verification-policy', 'ci/publish.py', 'require_verified=args.require_verified)', 'require_verified=None)'),
    ('workflow-read-only', 'ci/publish.yml', 'contents: read', 'contents: write'),
    ('workflow-main-only', 'ci/publish.yml', "github.ref == 'refs/heads/main'", 'true'),
    ('workflow-immutable-actions', 'ci/publish.yml',
     'actions/checkout@11d5960a326750d5838078e36cf38b85af677262', 'actions/checkout@v4'),
    ('workflow-deploy-verification', 'ci/publish.yml', 'publish.py verify', 'publish.py build'),
    ('workflow-require-hashes', 'ci/publish.yml', '--require-hashes', ''),
]


def main():
    run = Path(tempfile.mkdtemp(prefix='sf2-5-mutations-', dir=os.environ['TMPDIR']))
    tree = run / 'tree'
    destination = tree / 'skills/spec-format'
    shutil.copytree(HERE.parent, destination, ignore=shutil.ignore_patterns('__pycache__', '.*'))
    spdx = tree / 'skills/board-expert/scripts'
    spdx.mkdir(parents=True)
    shutil.copyfile(REPO / 'skills/board-expert/scripts/spdx.py', spdx / 'spdx.py')
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=str(destination / 'tests'))
    cmd = [sys.executable, '-m', 'unittest', 'test_render_html']
    def execute():
        return subprocess.run(cmd, cwd=tree, env=env, capture_output=True, text=True, check=False)
    baseline = execute()
    (run / 'baseline.log').write_text(baseline.stdout + baseline.stderr)
    if baseline.returncode:
        print('baseline failed: ' + str(run))
        return 1
    results = []
    for name, relative, before, after in MUTATIONS:
        path = destination / relative
        source = path.read_text()
        if before not in source:
            raise ValueError('mutation target missing: ' + name)
        changed = source.replace(before, after) if name in (
            'workflow-deploy-verification', 'workflow-require-hashes') else source.replace(before, after, 1)
        if path.suffix == '.py':
            compile(changed, str(path), 'exec')
        try:
            path.write_text(changed)
            result = execute()
        finally:
            path.write_text(source)
        log = result.stdout + result.stderr
        (run / (name + '.log')).write_text(log)
        crashed = any(marker in log for marker in (
            'ERROR:', 'internal error:', '"error": "internal"', 'AssertionError: 100', '(100,'))
        killed = result.returncode != 0 and 'FAIL:' in log and not crashed
        results.append({'name': name, 'killed_by_assertion': killed, 'exit': result.returncode})
        print(name + ': ' + ('assertion kill' if killed else 'SURVIVED OR CRASHED'), flush=True)
    (run / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
    print('artifacts: ' + str(run))
    return 0 if all(r['killed_by_assertion'] for r in results) else 1


if __name__ == '__main__':
    sys.exit(main())
