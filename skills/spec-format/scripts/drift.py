# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Compare one repository pin and optionally rewrite only marked YAML spans.

spec.py drift COMMIT FILE --pin NAME [--rewrite] [resolver options]
COMMIT is a full immutable id, never a branch or a refspec. With one cited
repository --pin may be omitted. Changed search scopes block rewriting: the
schema intentionally gives search anchors no stale field.
"""

from __future__ import annotations

import copy
import os
from pathlib import Path
import re
import secrets
import stat
import tempfile

import resolve
import speccheck


def compare(old, new, anchor):
    """Return (same|moved|stale|search-changed, new span or None)."""
    span, cited = resolve.cited_lines(old, anchor)
    if "search" in anchor:
        try:
            unchanged = old.entry(anchor["path"]) == new.entry(anchor["path"])
        except resolve.LimitExceeded:
            raise
        except resolve.ContentError:
            unchanged = False
        return ("same" if unchanged else "search-changed"), None
    try:
        lines = new.lines(anchor["path"])
    except resolve.LimitExceeded:
        raise
    except resolve.ContentError:
        return "stale", None
    candidate = copy.deepcopy(anchor)
    if "lines" not in anchor:
        try:
            new_span, new_cited = resolve.cited_lines(new, anchor)
        except resolve.LimitExceeded:
            raise
        except resolve.ContentError:
            return "stale", None
        return ("same" if new_cited == cited else "stale"), new_span
    if lines[span[0] - 1 : span[1]] == cited:
        matches = [span[0]]
    else:
        matches = [
            i + 1
            for i in range(len(lines) - len(cited) + 1)
            if lines[i : i + len(cited)] == cited and any(s.strip() for s in cited)
        ]
    if len(matches) != 1:
        return "stale", None
    moved = [matches[0], matches[0] + len(cited) - 1]
    candidate["lines"] = moved
    try:
        resolve.cited_lines(new, candidate)
    except resolve.LimitExceeded:
        raise
    except resolve.ContentError:
        return "stale", None
    return ("same" if moved == span else "moved"), moved


def nodes(source):
    """PyYAML node marks only; strict loading already established data validity."""
    import yaml

    found = {}

    def walk(node, at):
        found[at] = node
        if isinstance(node, yaml.MappingNode):
            for key, value in node.value:
                walk(value, at + (key.value,))
        elif isinstance(node, yaml.SequenceNode):
            for i, value in enumerate(node.value):
                walk(value, at + (i,))

    walk(yaml.compose(source, Loader=yaml.BaseLoader), ())
    return found


def rewrite(source, commit_at, commit, changes, was):
    """Patch scalar spans and insert stale keys without reserializing the document."""
    marked, edits = nodes(source), []

    def scalar(at, value):
        node = marked[at]
        if node.style in ("|", ">"):
            header_end = source.index("\n", node.start_mark.index) + 1
            content = source[header_end:node.end_mark.index]
            old_value = node.value
            if old_value.endswith("\n") or not old_value:
                raise resolve.ContentError("block commit must strip its final newline (use |- or >-)")
            match = list(re.finditer(re.escape(old_value), content))
            if len(match) != 1:
                raise resolve.ContentError("block commit must occupy one contiguous line; folded multi-line commits cannot be rewritten")
            hit = match[0]
            edits.append((header_end + hit.start(), header_end + hit.end(), str(value)))
            return
        quote = node.style if node.style in ("'", '"') else ""
        if isinstance(value, str) and value.isdecimal():
            quote = quote or "'"
        edits.append(
            (node.start_mark.index, node.end_mark.index, quote + str(value) + quote)
        )

    scalar(commit_at, commit)
    newline = "\r\n" if "\r\n" in source else "\n"
    for at, status, span in changes:
        if status == "moved":
            for i, value in enumerate(span):
                scalar(at + ("lines", i), value)
        elif status == "stale":
            node = marked[at]
            if node.flow_style:
                pos = node.end_mark.index - 1
                tail = source[node.value[-1][1].end_mark.index:pos]
                import yaml

                comma = any(
                    isinstance(token, yaml.FlowEntryToken)
                    for token in yaml.scan("{" + tail + "}")
                )
                separator = " " if comma else ", "
                start = pos
                if comma:
                    while start > node.value[-1][1].end_mark.index and source[start - 1] in " \t":
                        start -= 1
                edits.append((start, pos, f"{separator}stale: {{was: '{was}'}}"))
            else:
                first_key = node.value[0][0]
                pos = source.rfind("\n", 0, node.end_mark.index) + 1
                if node.end_mark.index == len(source) and not source.endswith("\n"):
                    pos = len(source)
                    prefix = newline
                else:
                    prefix = ""
                edits.append(
                    (
                        pos,
                        pos,
                        prefix
                        + " " * first_key.start_mark.column
                        + f"stale: {{was: '{was}'}}"
                        + newline,
                    )
                )
    for start, end, value in sorted(edits, reverse=True):
        source = source[:start] + value + source[end:]
    return source


def replace_snapshot(path, original, replacement):
    """Stage with O_EXCL beside the original, then compare and atomically replace."""
    mode = stat.S_IMODE(path.stat().st_mode)
    staged = path.parent / ("spec-rewrite-" + secrets.token_hex(16))
    fd = os.open(staged, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(replacement)
            stream.flush()
            os.fsync(stream.fileno())
        if path.read_bytes() != original:
            raise resolve.ResolutionError("spec changed during drift; original retained")
        os.replace(staged, path)
    finally:
        staged.unlink(missing_ok=True)


def run(args):
    import spec

    if len(args.files) != 1:
        raise spec.Usage("drift rewrites exactly one spec file per invocation")
    try:
        resolve.check_commit(args.revision)
    except resolve.ResolutionError as exc:
        raise spec.Usage(str(exc)) from exc
    files, validation, local = resolve.prepare(args)
    findings = [f.as_dict() for f in validation]
    output = []
    if validation:
        return resolve.result_object(args.files, findings, [], [])
    path, loaded = files[0]
    data = loaded.data
    all_anchors = [
        (a, at)
        for r, base in resolve.records(data)
        for a, at in speccheck.anchors(r, base)
    ]
    names = {a["repo"] for a, _ in all_anchors}
    pin = args.pin or (next(iter(names)) if len(names) == 1 else None)
    if pin not in names:
        raise spec.Usage("--pin must select one cited repos entry")
    entries = [
        (i, entry)
        for i, entry in enumerate(data.get("resources", {}).get("repos", []))
        if entry["name"] == pin
    ]
    if len(entries) != 1:
        raise spec.Usage("--pin must select exactly one repos entry")
    index, entry = entries[0]
    changes = []
    try:
        original = loaded.raw
        source = original.decode("utf-8")
        resolve.check_url(entry["url"])
        resolve.check_commit(entry.get("commit"))
        with tempfile.TemporaryDirectory(prefix="spec-drift-") as scratch:

            def get(item, suffix):
                return (
                    resolve.Repository(
                        local[pin], item["commit"], args.timeout, args.limit_mb << 20
                    )
                    if pin in local
                    else resolve.fetch(
                        item, Path(scratch) / suffix, args.timeout, args.limit_mb << 20
                    )
                )

            old = get(entry, "old")
            new = get(dict(entry, commit=args.revision), "new")
            for anchor, at in all_anchors:
                if anchor["repo"] != pin:
                    continue
                resolve.check_license(old, entry, anchor)
                status, span = compare(old, new, anchor)
                if status in ("same", "moved") and "search" not in anchor:
                    try:
                        resolve.check_license(new, entry, anchor)
                    except resolve.LimitExceeded:
                        raise
                    except resolve.ContentError:
                        status, span = "stale", None
                changes.append((at, status, span))
                output.append(dict(path=anchor["path"], status=status, lines=span))
            if any(status == "search-changed" for _, status, _ in changes):
                raise resolve.ResolutionError(
                    "search scope changed: manually re-verify before "
                    "moving this pin; search cannot carry stale"
                )
            if args.rewrite:
                replacement = rewrite(
                    source,
                    ("resources", "repos", index, "commit"),
                    args.revision,
                    changes,
                    entry["commit"],
                )
                encoded = replacement.encode("utf-8")
                raw = []
                extension = (
                    spec.read_root(args.root, spec.load_schemas(), raw)
                    if args.root
                    else None
                )
                valid, _, _ = spec.validate_file(
                    path, spec.load_schemas(), extension, raw, raw=encoded
                )
                if not valid or raw:
                    raise resolve.ResolutionError(
                        "rewritten spec failed validation; original retained"
                    )
                replace_snapshot(path, original, encoded)
    except (resolve.ResolutionError, OSError) as exc:
        findings.append(
            dict(path=str(path), line=1, column=1, level="error", message=str(exc))
        )
    stale = sum(status == "stale" for _, status, _ in changes)
    if stale:
        findings.append(
            dict(
                path=str(path),
                line=1,
                column=1,
                level="error",
                message=f"{stale} changed anchor(s) need re-verification",
            )
        )
    code, result = resolve.result_object(args.files, findings, [], [])
    result["changes"] = output
    result["_text"] = [
        resolve.display_line(f"{c['path']}: {c['status']} {c['lines'] or ''}") for c in output
    ] + result["_text"]
    return code, result


def register(subparsers):
    parser = subparsers.add_parser(
        "drift", help=__doc__.splitlines()[0], allow_abbrev=False
    )
    parser.add_argument("revision", help="new full lowercase commit id")
    resolve.add_arguments(parser)
    parser.add_argument(
        "--pin", help="repos entry to move (required with several cited entries)"
    )
    parser.add_argument("--rewrite", action="store_true")
    parser.set_defaults(handler=run)
