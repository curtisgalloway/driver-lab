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


def rewrite_file_check(path):
    """Refuse replacements that would break links, permissions or special modes."""
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode):
        raise resolve.ResolutionError("cannot rewrite a symbolic link spec file")
    if info.st_nlink > 1:
        raise resolve.ResolutionError("cannot rewrite a spec file with more than one hard link")
    if info.st_mode & (stat.S_ISUID | stat.S_ISGID):
        raise resolve.ResolutionError("cannot rewrite a setuid or setgid spec file")
    if not info.st_mode & 0o222 or not os.access(path, os.W_OK):
        raise resolve.ResolutionError("cannot rewrite a spec file not writable by the user")
    return stat.S_IMODE(info.st_mode)


def first_difference(expected, actual, at=()):
    """First unequal path, including type, key and sequence-length differences."""
    if type(expected) is not type(actual):
        return at
    if isinstance(expected, dict):
        for key in expected:
            if key not in actual:
                return at + (key,)
            difference = first_difference(expected[key], actual[key], at + (key,))
            if difference is not None:
                return difference
        for key in actual:
            if key not in expected:
                return at + (key,)
    elif isinstance(expected, list):
        for i, (left, right) in enumerate(zip(expected, actual)):
            difference = first_difference(left, right, at + (i,))
            if difference is not None:
                return difference
        if len(expected) != len(actual):
            return at + (min(len(expected), len(actual)),)
    elif expected != actual:
        return at
    return None


def expected_rewrite(data, commit_at, commit, changes, was):
    """Independent data update; never infer intended values from rewritten text."""
    expected = copy.deepcopy(data)

    def value(at):
        found = expected
        for key in at:
            found = found[key]
        return found

    value(commit_at[:-1])[commit_at[-1]] = commit
    for at, status, span in changes:
        if status == "moved":
            value(at)["lines"] = list(span)
        elif status == "stale":
            value(at)["stale"] = {"was": was}
    return expected


def comment_bytes(source):
    """Comment bytes outside YAML tokens; hashes inside scalars are data."""
    import yaml

    comments, end = [], 0
    for token in yaml.scan(source, Loader=yaml.BaseLoader):
        start = token.start_mark.index
        if start > end:
            comments.extend(re.findall(r"#[^\n]*", source[end:start]))
        end = max(end, token.end_mark.index)
    comments.extend(re.findall(r"#[^\n]*", source[end:]))
    return [comment.encode("utf-8") for comment in comments]


def header_bytes(source):
    """Preserve the leading comment header, including SPDX and its line endings."""
    header = []
    for line in source.splitlines(keepends=True):
        if line.strip() and not line.lstrip().startswith("#"):
            break
        header.append(line)
    return "".join(header).encode("utf-8")


def verify_rewrite(source, replacement, expected, actual):
    difference = first_difference(expected, actual)
    if difference is not None:
        path = "$" + "".join(f"[{key!r}]" for key in difference)
        raise resolve.ResolutionError(
            f"rewritten spec failed validation: data differs at {path}; original retained"
        )
    if comment_bytes(source) != comment_bytes(replacement):
        raise resolve.ResolutionError("rewritten spec changed comment bytes; original retained")
    if header_bytes(source) != header_bytes(replacement):
        raise resolve.ResolutionError("rewritten spec changed SPDX header bytes; original retained")


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
    mode = rewrite_file_check(path)
    staged = path.parent / ("spec-rewrite-" + secrets.token_hex(16))
    fd = os.open(staged, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(replacement)
            os.fchmod(stream.fileno(), mode)
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
    if args.rewrite:
        try:
            rewrite_file_check(args.files[0])
        except FileNotFoundError:
            pass  # prepare reports a missing input as a usage error.
        except (resolve.ResolutionError, OSError) as exc:
            return resolve.result_object(args.files, [dict(
                path=str(args.files[0]), line=1, column=1, level="error", message=str(exc)
            )], [], [])
    files, validation, local = resolve.prepare(args)
    findings = resolve.validation_findings(validation)
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
    index, entry = resolve.select_pin(data, args.pin)
    pin = entry["name"]
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
                valid, _, rewritten = spec.validate_file(
                    path, spec.load_schemas(), extension, raw, raw=encoded
                )
                expected = expected_rewrite(
                    data, ("resources", "repos", index, "commit"),
                    args.revision, changes, entry["commit"]
                )
                if rewritten is not None:
                    verify_rewrite(source, replacement, expected, rewritten.data)
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
