# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""SF2-7b guard mutations in isolated TMPDIR trees, qualified by assertions only."""

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
CODE = [
    ('missing-search-impl-side', 'review', '"search" in anchor for anchor in sides["impl"]', '"search" in anchor for side in sides.values() for anchor in side'),
    ('review-overlay-payload', 'speccheck', 'if tf.kind == "review" and any(', 'if False and any('),
    ('pair-gap-support', 'speccheck', 'return bool(data.get("support") or data.get("data", {}).get("pair"))', 'return bool(data.get("support"))'),
    ('pair-gap-verdict', 'records', 'gap = not speccheck.has_support(rec.data)', 'gap = "support" not in rec.data'),
    ('pair-gap-html', 'render_html', 'if not speccheck.has_support(data):', 'if not data.get("support"):'),
    ('pair-gap-markdown', 'render_md', 'if not speccheck.has_support(data):', 'if not data.get("support"):'),
    ('html-child-metadata', 'render_html', 'out.append(verification(rec.file, rec.id + "." + key, child, notes))', 'pass'),
    ('html-verdict-date', 'render_html', "text = row['verdict'] + ' ' + verdict['date'] + (' · carried' if row['carried'] else '')", "text = row['verdict']"),
    ('html-verifier', 'render_html', "out.append('<p>Verifier: ' + literal(verdict['verifier']) + '</p>')", 'pass'),
    ('html-verifier-escape', 'render_html', "literal(verdict['verifier'])", "str(verdict['verifier'])"),
    ('html-reader-escape', 'render_html', "literal(reader['verifier'])", "str(reader['verifier'])"),
    ('html-readers', 'render_html', "for reader in verdict.get('readers', []):", 'for reader in []:'),
    ('html-second-reader', 'render_html', "out.append('<p>second reader missing</p>')", 'pass'),
    ('html-carried', 'render_html', "out.append('<p>carried from format ' + literal(verdict['carried_from']['format']) + '</p>')", 'pass'),
    ('html-record-note', 'render_html', "notes.append(('Record note', verdict['note']))", 'pass'),
    ('html-finding-table', 'render_html', "for name in ('register', 'layout', 'finding', 'coverage'):", "for name in ('register', 'layout', 'coverage'):"),
    ('html-fact-coverage-table', 'render_html', "for name in ('register', 'layout', 'finding', 'coverage'):", "for name in ('register', 'layout', 'finding'):"),
    ('html-pair-side-label', 'render_html', "out.append('<div class=\"provenance\"><p>Correspondence side: ' + literal(side) + '</p>')", "out.append('<div class=\"provenance\">')"),
    ('markdown-pair-side-label', 'render_md', 'out.extend(["Correspondence side: " + code(side), ""])', 'pass'),
    ('html-settled-by-label', 'render_html', "out.append('<p>Settled by</p>')", 'pass'),
    ('markdown-settled-by-label', 'render_md', 'out.extend(["Settled by:", ""])', 'pass'),
    ('bug-justification', 'review', 'if finding["assessment"] == "bug" and not (', 'if False and not ('),
    ('both-review-sides', 'review', 'if not all(sides.values()):', 'if False:'),
    ('missing-search', 'review', 'if finding["category"] == "missing" and not any(', 'if False and not any('),
    ('pair-roles', 'review', 'if entry and entry[0].get("role") != side:', 'if False:'),
    ('review-check', 'speccheck', 'review.check_file(self, f)', 'pass'),
    ('settlement-traversal', 'speccheck', 'if key in ("support", "settled_by"):', 'if key == "support":'),
    ('pair-traversal', 'speccheck', 'for side, value in data.get("data", {}).get("pair", {}).items():', 'for side, value in {}.items():'),
    ('pair-traversal-boundary', 'speccheck', 'if _payload:', 'if True:'),
    ('pair-anchor-path', 'speccheck', '((a,) if path[-1] in ("impl", "ref") else ("anchors", a))', '("anchors", a)'),
    ('findings-projection', 'peripheral', 'findings.append(dict(payload["finding"], fact=fid))', 'pass'),
    ('pairs-projection', 'peripheral', 'pairs.append(dict(payload["pair"], fact=fid))', 'pass'),
    ('coverage-projection', 'peripheral', 'coverage.append(dict(payload["coverage"], fact=fid))', 'pass'),
    ('suspect-hardware', 'peripheral', 'if payload["finding"]["assessment"] == "suspect":', 'if False:'),
    ('suspect-requirement-deduplication', 'peripheral', '== "as-implemented" and not sequence_steps and not suspect:', '== "as-implemented" and not sequence_steps:'),
    ('suspect-todo-deduplication', 'peripheral', '== "hardware" and not sequence_steps and not suspect:', '== "hardware" and not sequence_steps:'),
    ('markdown-review-trigger', 'render_md', 'f.kind in ("peripheral", "review")', 'f.kind == "peripheral"'),
    ('markdown-finding', 'render_md', '_table(out, "Finding (generated)", [{k: v for k, v in finding.items() if k != "settled_by"}])', 'pass'),
    ('markdown-settlement', 'render_md', '_support(out, checker, rec.file, finding.get("settled_by", []))', 'pass'),
    ('markdown-pair', 'render_md', '_support(out, checker, rec.file, [{"class": "src", "anchors": anchors}])', 'pass'),
    ('markdown-findings', 'render_md', '_table(out, "Findings (generated)", summary["findings"])', 'pass'),
    ('markdown-pairs', 'render_md', '_table(out, "Correspondence (generated)", summary["pairs"])', 'pass'),
    ('markdown-coverage', 'render_md', '_table(out, "Comparison coverage (generated)", summary["coverage"])', 'pass'),
    ('html-assessment', 'render_html', "out.append(badge('assessment', finding['assessment']))", 'pass'),
    ('html-settlement', 'render_html', "out.append(support(checker, file, finding.get('settled_by', []), notes))", 'pass'),
    ('html-payload', 'render_html', 'out.append(payload(checker, rec, status, with_status))', 'pass'),
    ('html-cell-escape', 'render_html', "'<td>' + literal(entry.get(key, '')) + '</td>'", "'<td>' + str(entry.get(key, '')) + '</td>'"),
    ('html-heading-escape', 'render_html', "out = ['<h3>' + literal(title) + '</h3><table><thead><tr>']", "out = ['<h3>' + title + '</h3><table><thead><tr>']"),
    ('html-column-escape', 'render_html', "'<th>' + literal(key) + '</th>' for key in keys", "'<th>' + key + '</th>' for key in keys"),
    ('html-pair-citation', 'render_html', "out.append(support(checker, rec.file, [{'class': 'src', 'anchors': anchors}], notes))", 'pass'),
    ('html-child-support', 'render_html', "out.append(support(checker, rec.file, row.get('support', []), notes))", 'pass'),
    ('html-child-requirement', 'render_html', "requirement = row.get('requirement', rec.data.get('requirement'))", "requirement = row.get('requirement')"),
    ('html-child-verdict', 'render_html', "out.append(badge(VERDICTS[row['verdict']], text))", 'pass'),
    ('html-child-freshness', 'render_html', "out.append(badge(FRESHNESS[row['status']], row['status']))", 'pass'),
    ('html-payload-note', 'render_html', "notes.append(('Payload note', row['note']))", 'pass'),
    ('html-provenance', 'render_html', "literal(', '.join(summary['classes']))", "literal('')"),
    ('html-canonical', 'render_html', "out.append(table('Canonical references (generated)', summary['references']))", 'pass'),
    ('html-registers', 'render_html', "out.append(table('Register map (generated)', peripheral.register_rows(summary)))", 'pass'),
    ('html-findings', 'render_html', "out.append(table('Findings (generated)', summary['findings']))", 'pass'),
    ('html-pairs', 'render_html', "out.append(table('Correspondence (generated)', summary['pairs']))", 'pass'),
    ('html-coverage', 'render_html', "out.append(table('Comparison coverage (generated)', summary['coverage']))", 'pass'),
    ('html-verify', 'render_html', "for row in summary['verify']:", 'for row in []:'),
    ('html-questions', 'render_html', "out.append(table('Open questions (generated)', summary['questions']))", 'pass'),
    ('html-areas', 'render_html', "out.append(table('Area confidence', file.data.get('areas', [])))", 'pass'),
    ('html-generated-trigger', 'render_html', "if typed_spec or any('data' in f for f in file.data['facts']):", 'if False:'),
    ('html-review-trigger', 'render_html', "f.kind in ('peripheral', 'review')", "f.kind == 'peripheral'"),
    ('register-field-projection', 'peripheral', 'row["fields"] = [{k: field[k] for k in ("id", "name", "bits", "meaning")}', 'row["fields"] = [{k: field[k] for k in ("id", "name")}'),
]


def schema_mutations():
    result = []
    for name, keys in (('finding', ('category', 'assessment', 'consequence', 'resolution')),
                       ('resolution', ('status',)), ('pair', ('impl', 'ref')),
                       ('coverage', ('area', 'compared', 'read', 'reason'))):
        for key in keys:
            result.append((name + '-required-' + key, ('$defs', name, 'required'), 'remove', key))
        result.append((name + '-closed', ('$defs', name, 'additionalProperties'), 'set', True))
        if name != 'resolution':
            result.append((name + '-object', ('$defs', name, 'type'), 'set', ['object', 'array']))
    for name, key in (('finding', 'category'), ('finding', 'assessment'), ('resolution', 'status')):
        result.append((name + '-' + key + '-enum', ('$defs', name, 'properties', key), 'set', {}))
    for key in ('self_evident', 'reason', 'consequence'):
        result.append(('finding-' + key + '-shape', ('$defs', 'finding', 'properties', key), 'set', {}))
    result.append(('self-evident-reason', ('$defs', 'finding', 'dependentRequired'), 'set', {}))
    for key in ('compared', 'area', 'read', 'reason'):
        result.append(('coverage-' + key + '-shape', ('$defs', 'coverage', 'properties', key), 'set', {}))
    for side in ('impl', 'ref'):
        result.append(('pair-' + side + '-nonempty', ('$defs', 'pair', 'properties', side, 'minItems'), 'set', 0))
        result.append(('pair-' + side + '-anchors', ('$defs', 'pair', 'properties', side, 'items'), 'set', {}))
        result.append(('pair-' + side + '-unique', ('$defs', 'pair', 'properties', side, 'uniqueItems'), 'set', False))
    for key in ('minItems', 'items'):
        result.append(('settlement-' + key, ('$defs', 'finding', 'properties', 'settled_by', key), 'set', 0 if key == 'minItems' else {}))
    result.append(('settlement-document-class', ('$defs', 'finding', 'properties', 'settled_by', 'items', 'allOf', 1), 'set', {}))
    result.append(('settlement-unique', ('$defs', 'finding', 'properties', 'settled_by', 'uniqueItems'), 'set', False))
    for index, name in enumerate(('fixed', 'wontfix', 'open')):
        result.append(('resolution-' + name, ('$defs', 'resolution', 'allOf', index), 'set', {}))
    for key in ('commit', 'reason'):
        result.append(('resolution-' + key, ('$defs', 'resolution', 'properties', key), 'set', {}))
    for key in ('id', 'name', 'resources'):
        result.append(('review-required-' + key, ('allOf', -2, 'then', 'required'), 'remove', key))
    result.append(('review-sections', ('allOf', -2, 'then', 'properties', 'facts', 'items', 'properties', 'section'), 'set', {}))
    result.append(('review-payload-kinds', ('allOf', -2, 'then', 'properties', 'facts', 'items', 'properties', 'data'), 'set', {}))
    result.append(('review-areas-nonempty', ('allOf', -2, 'then', 'properties', 'areas', 'minItems'), 'set', 0))
    for index, name in enumerate(('findings', 'correspondence', 'coverage')):
        for delta, label in ((0, 'needs-payload'), (1, 'payload-section')):
            result.append((name + '-' + label, ('$defs', 'fact', 'allOf', 6 + index * 2 + delta), 'set', {}))
    result.extend([
        ('pair-support-todo', ('$defs', 'supportRules', 'anyOf', 1), 'set', {'required': ['support']}),
        ('settlement-document-required', ('$defs', 'support', 'allOf', 0, 'then', 'required'), 'remove', 'doc'),
        ('settlement-extra-keys', ('$defs', 'support', 'unevaluatedProperties'), 'set', True),
        ('review-agreements-section', ('allOf', -2, 'then', 'properties', 'facts', 'items', 'properties', 'section', 'enum'), 'remove', 'agreements'),
        ('overlay-findings-section', ('allOf', 4, 'then', 'properties', 'facts', 'items', 'properties', 'section', 'enum'), 'remove', 'findings'),
        ('review-id-shape', ('allOf', -2, 'then', 'properties', 'id'), 'set', {}),
        ('review-notes-shape', ('allOf', -2, 'then', 'properties', 'notes'), 'set', {}),
        ('review-cache-shape', ('allOf', -2, 'then', 'properties', 'cache'), 'set', {}),
    ])
    return result


def execute(case, store):
    label = case[0]
    dest = store / label
    for relative in ('skills/spec-format', 'skills/board-expert/scripts', 'skills/hardware-investigator/examples'):
        shutil.copytree(REPO / relative, dest / relative, ignore=shutil.ignore_patterns('__pycache__'))
    if isinstance(case[1], str):
        _, module, before, after = case
        path = dest / 'skills/spec-format/scripts' / (module + '.py')
        text = path.read_text()
        if text.count(before) != 1:
            return {'mutation': label, 'killed': False, 'reason': 'guard is not unique'}
        path.write_text(text.replace(before, after))
    else:
        _, trail, action, value = case
        path = dest / 'skills/spec-format/schema/spec.schema.json'
        schema = json.loads(path.read_text())
        parent = schema
        for part in trail[:-1]:
            parent = parent[part]
        if action == 'remove':
            parent[trail[-1]].remove(value)
        else:
            parent[trail[-1]] = value
        path.write_text(json.dumps(schema))
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1',
               PYTHONPATH=str(dest / 'skills/spec-format/tests'))
    proc = subprocess.run([sys.executable, '-m', 'unittest', 'test_sf2_7b', 'test_render_html', '-q'],
                          cwd=dest, env=env, capture_output=True, text=True, timeout=120)
    output = proc.stdout + proc.stderr
    (store / (label + '.log')).write_text(output)
    match = re.search(r'FAILED \(failures=(\d+)(?:, errors=(\d+))?\)', output)
    killed = bool(proc.returncode and match and not match[2] and 'AssertionError' in output
                  and "'error': 'internal'" not in output and '"error": "internal"' not in output)
    return {'mutation': label, 'killed': killed, 'exit': proc.returncode,
            'failures': int(match[1]) if match else 0}


def main():
    store = Path(tempfile.mkdtemp(prefix='sf2-7b-mutations-'))
    cases = CODE + schema_mutations()
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda case: execute(case, store), cases))
    (store / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
    for result in results:
        print(result['mutation'] + ': ' + ('assertion kill' if result['killed'] else 'UNQUALIFIED'))
    print(f"{sum(r['killed'] for r in results)}/{len(results)} qualified; logs: {store}")
    return int(not all(r['killed'] for r in results))


if __name__ == '__main__':
    sys.exit(main())
