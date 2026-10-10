# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Build or verify a complete static spec site; run with the pinned spec-format environment."""

from __future__ import annotations

import argparse
import hashlib
from html import escape
import json
from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import render_html
import render_md
import spec
import speccheck


def catalog(checker):
    """Recompute expected pages from checked source files, never from the build's manifest."""
    pages = []
    for file in checker.files:
        if file.root.context:
            continue
        source = file.root.label + ':' + file.path.relative_to(file.root.given).as_posix()
        stem = 'spec-' + hashlib.sha256(source.encode('utf-8')).hexdigest()
        pages.append((stem, source, file, False))
    overlays = sorted({f.spec_id for f in checker.files if not f.root.context and f.is_overlay})
    for sid in overlays:
        stem = 'merged-' + hashlib.sha256(sid.encode('utf-8')).hexdigest()
        file = next(f for f in checker.files if not f.root.context and f.spec_id == sid)
        pages.append((stem, 'merged:' + sid, file, True))
    if not pages:
        raise ValueError('no specs to publish')
    return pages


def checked(args):
    problems = spec.check_dependencies()
    if problems:
        raise ValueError('; '.join(problems))
    checker = spec._run_check(SimpleNamespace(
        roots=[args.root], context_root=args.context_root, require_license=True,
        public_skill=args.public_skill), require_verified=args.require_verified)
    errors = [f for f in checker.findings if f.level == 'error']
    if errors:
        raise ValueError('\n'.join(str(f) for f in errors))
    if any(r.untrusted for r in checker.roots):
        raise ValueError('publishing context does not check clean')
    return checker


def payloads(checker, args):
    """Both renderers repeat field checks; nothing is written until every page succeeds."""
    result, entries = {}, []
    for stem, source, file, merged in catalog(checker):
        selected = checker
        included = [f for f in selected.files if f.spec_id == file.spec_id and
                    (merged or not f.root.context)]
        roots = {f.root.given.absolute() for f in included}
        commits = []
        for value in args.source_commit:
            if '=' not in value:
                raise ValueError('publishing requires ROOT=SHA source commits')
            root, sha = value.rsplit('=', 1)
            if Path(root).absolute() in roots:
                commits.append(value)
        if {Path(c.rsplit('=', 1)[0]).absolute() for c in commits} != roots:
            raise ValueError('every published root requires a source commit')
        options = dict(spec_id=file.spec_id, merged=merged, with_status=True,
                       source_commit=commits, tool_commit=args.tool_commit)
        result[stem + '.html'] = render_html.render(selected, **options)
        result[stem + '.md'] = render_md.render(selected, **options)
        entries.append({'source': source, 'html': stem + '.html', 'markdown': stem + '.md'})
    index = ['<!doctype html><html lang="en"><head><meta charset="utf-8">',
             '<title>Spec views</title></head><body><h1>Spec views</h1><ul>']
    for entry in entries:
        index.append('<li>' + escape(entry['source']) + ' <a href="' + entry['html'] +
                     '">Viewer</a> · <a href="' + entry['markdown'] + '">Markdown</a></li>')
    index.append('</ul></body></html>')
    result['index.html'] = '\n'.join(index) + '\n'
    manifest = {'pages': entries, 'sha256': {
        name: hashlib.sha256(text.encode('utf-8')).hexdigest() for name, text in result.items()}}
    result['manifest.json'] = json.dumps(manifest, sort_keys=True, indent=2) + '\n'
    return result


def safe_output(out, checker):
    """A build cannot write into its sources; neither operation follows output symlinks."""
    absolute = out.absolute()
    if any(p.is_symlink() for p in (absolute, *absolute.parents)):
        raise ValueError('site output must not use symlinks')
    absolute = absolute.resolve()
    for root in checker.roots:
        if absolute.is_relative_to(root.given.resolve()):
            raise ValueError('site output must be outside spec roots')


def build(checker, args):
    safe_output(args.out, checker)
    if args.out.exists() and any(args.out.iterdir()):
        raise ValueError('site output must be empty')
    expected = payloads(checker, args)
    args.out.mkdir(parents=True, exist_ok=True)
    for name, text in expected.items():
        (args.out / name).write_text(text, encoding='utf-8')
    verify(checker, args)


def verify(checker, args):
    """Re-render pinned sources and compare all bytes before upload or deployment.

    A manifest edited along with a truncated site cannot bypass this guard. A zero-byte page,
    stale page, missing Markdown view, link, directory or unexpected file also refuses deploy.
    """
    safe_output(args.out, checker)
    expected = payloads(checker, args)
    if not args.out.is_dir() or {p.name for p in args.out.iterdir()} != set(expected):
        raise ValueError('site is missing a spec page or has unexpected files')
    for name, text in expected.items():
        path = args.out / name
        if path.is_symlink() or not path.is_file():
            raise ValueError('site entry must be a regular file: ' + name)
        if path.read_bytes() != text.encode('utf-8'):
            raise ValueError('site page differs from checked sources: ' + name)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('build', 'verify'))
    parser.add_argument('root', type=Path)
    parser.add_argument('--context-root', action='append', type=Path, default=[])
    parser.add_argument('--public-skill', action='append', default=[])
    parser.add_argument('--source-commit', action='append', required=True, type=spec.source_commit_arg)
    parser.add_argument('--tool-commit', required=True, type=spec.commit_arg)
    parser.add_argument('--require-verified', choices=('pr', 'main'))
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        checker = checked(args)
        (build if args.mode == 'build' else verify)(checker, args)
    except (ValueError, OSError, spec.Usage, spec.Precondition, speccheck.UsageError,
            speccheck.PreconditionError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(args.mode + ': complete site (' + str(len(catalog(checker))) + ' spec views)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
