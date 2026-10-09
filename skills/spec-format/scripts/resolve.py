# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Resolve format 2 anchors and display their evidence at immutable Git pins.

CLI: spec.py resolve|show FILE... [--repo NAME=CHECKOUT] [--docs-dir DIR].
Unbound repositories are fetched into disposable shallow, blob-less repositories.
Only size/time limits skip. A skipped anchor is counted explicitly, never resolved.
Document bytes are supplied as DIR/NAME (no extension guessing or network retrieval).
Search checks scope existence, not the truth of the author's negative/global claim.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import subprocess
import tempfile

import speccheck

COMMIT = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
SAFE = [
    "-c",
    "protocol.allow=never",
    "-c",
    "protocol.https.allow=always",
    "-c",
    "http.followRedirects=false",
    "-c",
    "core.hooksPath=/dev/null",
]
SYMBOL_BEFORE = 200


class ResolutionError(ValueError):
    """A definite failure, never a skip."""


class LimitExceeded(ResolutionError):
    """Only transfer/read size and elapsed-time limits may skip resolution."""


class ContentError(ResolutionError):
    """Missing or changed content, rather than an operational read failure."""


def git_env():
    """Keep caller Git configuration and URL rewrites out of network operations."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_TERMINAL_PROMPT="0",
        GIT_ALLOW_PROTOCOL="https",
        GIT_NO_REPLACE_OBJECTS="1",
    )
    return env


def git(directory, args, timeout, limit):
    """Run without a shell; bound captured bytes before reading them into memory."""
    command = ["git", *SAFE, "-C", str(directory), *args]
    try:
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
            proc = subprocess.run(
                command,
                stdout=out,
                stderr=err,
                env=git_env(),
                timeout=timeout,
                check=False,
            )
            err.seek(0)
            reason = err.read(1024).decode("utf-8", errors="replace").strip()
            if proc.returncode:
                raise ResolutionError(f"git {args[0]} failed: {reason}")
            if out.tell() > limit:
                raise LimitExceeded("size limit exceeded by Git output")
            out.seek(0)
            return out.read()
    except subprocess.TimeoutExpired as exc:
        raise LimitExceeded(f"time limit exceeded ({timeout} seconds)") from exc
    except OSError as exc:
        raise ResolutionError(f"cannot run git: {exc}") from exc


def check_url(url):
    """Check the schema's HTTPS grammar again at the fetch boundary."""
    import spec

    pattern = spec.load_schemas()["spec"]["$defs"]["httpsUrl"]["pattern"]
    if not isinstance(url, str) or re.fullmatch(pattern, url) is None:
        raise ResolutionError("repository URL must be an https:// URL")


def check_commit(commit):
    if not isinstance(commit, str) or not COMMIT.fullmatch(commit):
        raise ResolutionError("pin must be a full lowercase commit id")


class Repository:
    """Read objects, never a worktree; paths and revisions always follow --."""

    def __init__(self, directory, commit, timeout=300, limit=50 << 20, fetched=False):
        check_commit(commit)
        self.directory, self.commit = Path(directory), commit
        self.timeout, self.limit = timeout, limit
        self._blobs = {}
        self._blob_bytes = 0
        self.fetched = fetched
        if self.run("cat-file", "-t", "--", commit).strip() != b"commit":
            raise ResolutionError("pin does not identify a commit")

    def run(self, *args):
        return git(self.directory, list(args), self.timeout, self.limit)

    def check_object_budget(self):
        if self.fetched:
            size = sum(
                p.stat().st_size
                for p in (self.directory / ".git").rglob("*")
                if p.is_file()
            )
            if size > self.limit:
                raise LimitExceeded("size limit exceeded by fetched objects")

    def entry(self, path):
        """Return (mode, kind, object id); literal paths only, no pathspec matching."""
        parts = path.rstrip("/").split("/")
        if (
            not path
            or path.startswith("-")
            or any(p in ("", ".", "..") or p.lower() == ".git" for p in parts)
        ):
            raise ResolutionError("invalid repository path")
        tree = self.commit
        found = None
        for part in parts:
            entries = self.run("ls-tree", "-z", "--", tree).split(b"\x00")
            found = None
            for entry in filter(None, entries):
                meta, name = entry.split(b"\t", 1)
                if name == part.encode("utf-8"):
                    found = tuple(meta.decode("ascii").split())
                    break
            if found is None:
                raise ContentError(f"{path}: path does not exist at {self.commit}")
            mode, _, tree = found
            if mode not in ("040000", "100644", "100755"):
                raise ContentError(
                    f"{path}: symlinks and submodules are not source files"
                )
        return found

    def blob(self, path):
        if path not in self._blobs:
            _, kind, oid = self.entry(path)
            if kind != "blob" or path.endswith("/"):
                raise ContentError(f"{path}: expected a file")
            size = int(self.run("cat-file", "-s", "--", oid))
            self.check_object_budget()
            if self._blob_bytes + size > self.limit:
                raise LimitExceeded(f"{path}: cumulative blob size limit exceeded")
            raw = self.run("cat-file", "blob", "--", oid)
            self.check_object_budget()
            if self._blob_bytes + len(raw) > self.limit:
                raise LimitExceeded(f"{path}: cumulative blob size limit exceeded")
            self._blobs[path] = raw
            self._blob_bytes += len(raw)
        return self._blobs[path]

    def lines(self, path):
        raw = self.blob(path)
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ContentError(
                f"{path}: source is not UTF-8; supply decompiled DT text"
            ) from exc
        lines = text.split("\n")
        if lines[-1] == "":
            lines.pop()
        return lines


def fetch(entry, directory, timeout=300, limit=50 << 20):
    """Port of fetch_src_pins' shallow/blob-less rules, with no local URL escape."""
    check_url(entry.get("url"))
    check_commit(entry.get("commit"))
    directory.mkdir(parents=True, exist_ok=True)
    init = ["init", "-q"]
    if len(entry["commit"]) == 64:
        init.append("--object-format=sha256")
    git(directory, init, timeout, limit)
    git(
        directory,
        [
            "fetch",
            "-q",
            "--depth",
            "1",
            "--filter=blob:none",
            "--",
            entry["url"],
            entry["commit"],
        ],
        timeout,
        limit,
    )
    size = sum(p.stat().st_size for p in (directory / ".git").rglob("*") if p.is_file())
    if size > limit:
        raise LimitExceeded("size limit exceeded by fetched objects")
    return Repository(directory, entry["commit"], timeout, limit, fetched=True)


def symbol_in(lines, symbol, first, last):
    pattern = re.compile(r"(?<![A-Za-z0-9_])" + re.escape(symbol) + r"(?![A-Za-z0-9_])")
    return any(pattern.search(line) for line in lines[max(0, first - 1) : last])


def node_range(lines, node):
    """Locate a node in decompiled/source DTS, ignoring comments and strings.

    Absolute paths match their ancestry; short names/labels must be unique. This is
    a locator, not a DTS evaluator: included files must be cited separately.
    """
    source = "\n".join(lines)
    tokens = list(
        re.finditer(
            r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|&(?:\{[^}]+\}|[A-Za-z0-9_.,@/#+-]+)|[A-Za-z0-9_.,@/#+-]+|[{}:;=]',
            source,
            re.S,
        )
    )
    stack, matches, prefix = [], [], []
    for token in tokens:
        word = token.group()
        if word.startswith(("/*", "//", '"')):
            continue
        if word == "{":
            name = prefix[-1] if prefix else ""
            labels = [prefix[i - 1] for i in range(1, len(prefix)) if prefix[i] == ":"]
            override = name.startswith("&") or bool(stack and stack[-1][4])
            full = "/" + "/".join(
                [s[0] for s in stack if s[0] != "/"] + ([name] if name != "/" else [])
            )
            start = source.count("\n", 0, token.start()) + 1
            stack.append((name, labels, full, start, override))
            prefix = []
        elif word == "}":
            if not stack:
                raise ContentError("unbalanced DT node braces")
            name, labels, full, start, override = stack.pop()
            if not override and (node == full or (not node.startswith("/") and node in [name, *labels])):
                matches.append([start, source.count("\n", 0, token.end()) + 1])
            prefix = []
        elif word == ";":
            prefix = []
        else:
            prefix.append(word)
    if stack or len(matches) != 1:
        raise ContentError(f"DT node {node!r} does not resolve uniquely")
    return matches[0]


def cited_lines(repo, anchor):
    """Return (range, lines); search returns no lines and never runs its prose."""
    if "stale" in anchor:
        raise ContentError(
            f"stale anchor (was {anchor['stale']['was']}); re-verify it"
        )
    if "search" in anchor:
        _, kind, _ = repo.entry(anchor["path"])
        expected = "tree" if anchor["path"].endswith("/") else "blob"
        if kind != expected:
            raise ContentError("search path kind differs from its trailing slash")
        return None, []
    lines = repo.lines(anchor["path"])
    span = anchor.get("lines")
    if "node" in anchor:
        node_span = node_range(lines, anchor["node"])
        if span and not (node_span[0] <= span[0] <= span[1] <= node_span[1]):
            raise ContentError("cited lines are outside the DT node")
        span = span or node_span
    if not span or not (1 <= span[0] <= span[1] <= len(lines)):
        raise ContentError(f"line range is outside the file's {len(lines)} lines")
    if "symbol" in anchor and not symbol_in(
        lines, anchor["symbol"], span[0] - SYMBOL_BEFORE, span[1]
    ):
        raise ContentError(
            f"symbol {anchor['symbol']!r} is not near the cited range"
        )
    return span, lines[span[0] - 1 : span[1]]


def license_key(tree):
    """Normalize order/grouping as well as SPDX's deprecated identifier aliases."""
    if not hasattr(tree, "op"):
        return str(tree)
    children = set()
    for child in tree.args:
        key = license_key(child)
        if isinstance(key, tuple) and key[0] == tree.op:
            children.update(key[1])
        else:
            children.add(key)
    return tree.op, frozenset(children)


def check_license(repo, entry, anchor):
    """SPDX expressions must agree, including exceptions and AND/OR obligations."""
    path = anchor["path"]
    listed = [item for item in entry.get("files", []) if item["path"] == path]
    if len(listed) != 1:
        raise ContentError(
            f"{path}: must occur exactly once in the closed files list"
        )
    if path.endswith("/"):
        return
    spdx = speccheck.load_spdx()
    declarations = []
    closing = None
    for line in repo.lines(path)[:5]:
        text = line.strip()
        if not text or text.startswith("#!"):
            continue
        if closing is not None:
            comment = text
        elif text.startswith(("//", "#", ";")):
            comment = text
        elif text.startswith("/*"):
            closing, comment = "*/", text
        elif text.startswith("<!--"):
            closing, comment = "-->", text
        else:
            break
        if "SPDX-License-Identifier:" in comment:
            expression = comment.split("SPDX-License-Identifier:", 1)[1].strip()
            expression = re.sub(r"\s*(?:\*/|-->)\s*$", "", expression).strip()
            declarations.append(expression)
            break
        if closing and closing in comment:
            tail = comment.split(closing, 1)[1].strip()
            closing = None
            if tail:
                break
    if not declarations and listed[0]["license_from"] == "spdx-line":
        raise ContentError(f"{path}: declared spdx-line but no SPDX line exists")
    try:
        expected = license_key(spdx.parse(entry["license"]))
        for expression in declarations:
            if license_key(spdx.parse(expression)) != expected:
                raise ContentError(
                    f"{path}: SPDX line {expression!r} differs from "
                    f"entry license {entry['license']!r}"
                )
    except spdx.SpdxError as exc:
        raise ContentError(f"{path}: invalid SPDX expression: {exc}") from exc


def hex_values(text):
    return {int(v, 16) for v in re.findall(r"\b0[xX]([0-9a-fA-F]+)\b", text)}


def records(data):
    for group in ("facts", "instances", "variants"):
        for i, record in enumerate(data.get(group, [])):
            yield record, (group, i)


def bindings(values):
    import spec

    result = {}
    for value in values:
        name, sep, directory = value.partition("=")
        if not sep or not name or not directory.strip() or name in result:
            raise spec.Usage("--repo requires a unique NAME=CHECKOUT binding")
        path = Path(directory)
        if not path.is_dir():
            raise spec.Usage(f"--repo {name}: not a directory")
        result[name] = path
    return result


def check_bindings(local):
    import spec

    for name, path in local.items():
        try:
            top = git(path, ["rev-parse", "--show-toplevel"], 30, 1 << 20)
        except ResolutionError as exc:
            raise spec.Usage(f"--repo {name}: expected the top level of a checkout: {exc}") from exc
        if Path(os.fsdecode(top).strip()).resolve() != path.resolve():
            raise spec.Usage(f"--repo {name}: expected the top level of a checkout")


def prepare(args):
    """Validate every input before any source command can run."""
    import spec

    if args.timeout <= 0 or args.limit_mb <= 0:
        raise spec.Usage("--timeout and --limit-mb must be positive")
    if args.docs_dir is not None and not args.docs_dir.is_dir():
        raise spec.Usage("--docs-dir must be a directory")
    local = bindings(args.repo)
    schemas, findings, files = spec.load_schemas(), [], []
    extension = spec.read_root(args.root, schemas, findings) if args.root else None
    for path in args.files:
        if not path.is_file() or spec.schema_kind(path) != "spec":
            raise spec.Usage(f"{path}: expected a spec file")
        valid, _, loaded = spec.validate_file(path, schemas, extension, findings)
        if valid:
            files.append((path, loaded))
    names = {
        r["name"]
        for _, loaded in files
        for r in loaded.data.get("resources", {}).get("repos", [])
    }
    if local.keys() - names and not findings:
        raise spec.Usage("--repo names an entry absent from the input files")
    if not findings:
        check_bindings(local)
    return files, findings, local


def display_line(line):
    """Render terminal controls as printable escapes, preserving tabs."""
    return "".join(
        f"\\x{ord(char):02x}" if (ord(char) < 0x20 and char != "\t") or ord(char) == 0x7f else char
        for char in line.removesuffix("\r")
    )


def result_object(files, findings, anchors, facts):
    errors = [f for f in findings if f.get("level", "error") == "error"]
    result = {
        "ok": not errors,
        "files": [
            {"path": str(p), "valid": not any(f["path"] == str(p) for f in errors)}
            for p in files
        ],
        "findings": findings,
        "anchors": anchors,
        "facts": facts,
        "resolved": sum(a["status"] == "resolved" for a in anchors),
        "skipped": sum(a["status"] == "skipped" for a in anchors),
    }
    text = []
    for fact in facts:
        text.append(f"{fact['id']}: {fact['claim']}")
        for citation in fact["citations"]:
            text.append(
                f"  {citation['repo']}:{citation['path']} [{citation['status']}]"
            )
            for number, line in citation.get("source", []):
                text.append(f"  {number}: {display_line(line)}")
            if citation.get("search"):
                text.append(
                    f"  Search scope only (re-verify manually): {citation['search']}"
                )
    text.extend(
        f"{f['path']}:{f['line']}:{f['column']}: "
        f"{f.get('level', 'error')}: {f['message']}"
        for f in findings
    )
    text.append(f"{result['resolved']} anchor(s) resolved, {result['skipped']} skipped")
    result["_text"] = text
    return (1 if errors else 0), result


def run(args):
    """Shared resolve/show command; strict validation precedes all source work."""
    files, validation, local = prepare(args)
    findings = [f.as_dict() for f in validation]
    anchors, facts = [], []
    if validation:
        return result_object(args.files, findings, anchors, facts)
    with tempfile.TemporaryDirectory(prefix="spec-resolve-") as scratch:
        repos = {}
        for path, loaded in files:
            data = loaded.data

            def add(at, message, level="error", loaded=loaded, path=path):
                mark = loaded.mark(at)
                findings.append(
                    dict(
                        path=str(path),
                        line=mark.line,
                        column=mark.column,
                        level=level,
                        message=message,
                    )
                )

            entries = data.get("resources", {}).get("repos", [])
            by_name = {}
            for entry in entries:
                by_name.setdefault(entry["name"], []).append(entry)
            for record, base in records(data):
                display = dict(
                    id=record["id"],
                    claim=record.get("claim", record.get("name", "")),
                    citations=[],
                )
                own_lines = []
                for anchor, at in speccheck.anchors(record, base):
                    item = dict(
                        repo=anchor["repo"],
                        path=anchor["path"],
                        fact=record["id"],
                        status="failed",
                        source=[],
                    )
                    anchors.append(item)
                    display["citations"].append(item)
                    try:
                        if "stale" in anchor:
                            raise ResolutionError(
                                "stale anchor; re-verify before resolving"
                            )
                        choices = by_name.get(anchor["repo"], [])
                        if len(choices) != 1:
                            raise ResolutionError(
                                "anchor repo must name exactly one repos entry"
                            )
                        entry = choices[0]
                        check_url(entry["url"])
                        check_commit(entry.get("commit"))
                        key = (
                            entry["url"],
                            entry["commit"],
                            str(local.get(entry["name"], "")),
                        )
                        if key not in repos:
                            try:
                                repos[key] = (
                                    Repository(
                                        local[entry["name"]],
                                        entry["commit"],
                                        args.timeout,
                                        args.limit_mb << 20,
                                    )
                                    if entry["name"] in local
                                    else fetch(
                                        entry,
                                        Path(scratch) / str(len(repos)),
                                        args.timeout,
                                        args.limit_mb << 20,
                                    )
                                )
                            except ResolutionError as exc:
                                repos[key] = exc
                        repo = repos[key]
                        if isinstance(repo, ResolutionError):
                            raise repo
                        span, lines = cited_lines(repo, anchor)
                        check_license(repo, entry, anchor)
                        item.update(
                            status="resolved",
                            commit=entry["commit"],
                            source=[
                                (number, line.removesuffix("\r"))
                                for number, line in enumerate(lines, span[0])
                            ] if span else [],
                        )
                        if "search" in anchor:
                            item["search"] = anchor["search"]
                        if (
                            at[: len(base) + 1] == base + ("support",)
                            and len(at) == len(base) + 4
                        ):
                            own_lines.extend(lines)
                    except LimitExceeded as exc:
                        item["status"] = "skipped"
                        add(at, f"{record['id']}: resolution skipped: {exc}", "warning")
                    except ResolutionError as exc:
                        add(at, f"{record['id']}: {exc}")
                missing = hex_values(record.get("claim", "")) - hex_values(
                    "\n".join(own_lines)
                )
                if own_lines and missing:
                    add(
                        base + ("claim",),
                        "claim hex values absent from cited lines: "
                        + ", ".join(hex(v) for v in sorted(missing)),
                        "warning",
                    )
                if args.command == "show":
                    facts.append(display)
            if args.docs_dir is not None:
                for i, doc in enumerate(data.get("resources", {}).get("documents", [])):
                    if "sha256" not in doc:
                        continue
                    at = ("resources", "documents", i, "sha256")
                    document = args.docs_dir / doc["name"]
                    try:
                        if document.is_symlink() or not document.is_file():
                            raise ResolutionError(
                                f"document {doc['name']}: missing regular file"
                            )
                        with document.open("rb") as stream:
                            digest = hashlib.file_digest(stream, "sha256").hexdigest()
                        if digest != doc["sha256"]:
                            raise ResolutionError(
                                f"document {doc['name']}: sha256 mismatch"
                            )
                    except (ResolutionError, OSError) as exc:
                        add(at, str(exc))
    return result_object(args.files, findings, anchors, facts)


def register(subparsers):
    """Register commands without importing resolver dependencies before dep checks."""
    for name in ("resolve", "show"):
        parser = subparsers.add_parser(
            name, help=__doc__.splitlines()[0], allow_abbrev=False
        )
        add_arguments(parser)
        parser.set_defaults(handler=run)


def add_arguments(parser):
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--root", type=Path, help="root marker for schema extensions")
    parser.add_argument(
        "--repo",
        action="append",
        default=[],
        metavar="NAME=CHECKOUT",
        help="read an existing local repository at the declared commit",
    )
    parser.add_argument(
        "--docs-dir", type=Path, help="document files named exactly by document name"
    )
    parser.add_argument(
        "--timeout", type=int, default=300, help="seconds per Git operation"
    )
    parser.add_argument(
        "--limit-mb",
        type=int,
        default=50,
        help="retained objects and output limit; not a transfer-byte limit",
    )
    parser.add_argument("--json", action="store_true")
