# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Document section indexes (#155): `spec.py index` and their checks.

An index is `<root>/index/<name>.index.yaml`: each section's number, title, level and page
range (a PDF's outline) or line range (a Markdown file's headings), with the document's
`sha256`. It holds headings and locators only, never document text, so it can be published in
a root whose documents cannot be. A PDF section's range runs to the page where the next
section at its level or above starts, that page included (a section may end part-way down it);
a parent's range covers its children's even when the outline lists pages out of order. A question no fact covers is looked up here first, and only
the cited pages are read (board-expert's fallback); the answer is then labeled
`unverified (doc-read)`.

`spec.py index <name> --root <root> --docs-dir <dir>` reads `<dir>/<name>`, the bytes of the
document the root's specs list as `<name>`, refuses them unless they hash to the registry's
`sha256`, and writes the index. The output depends only on the bytes: the same document always
gives the same file. `spec.py check` validates every index and warns when its `sha256` differs
from the registry's (or the registry records none), when no spec of the root lists its
document, or when a PDF index's page count differs from the registry's `pages`.

pypdf parses the PDF with no time or size bound of its own. That is acceptable because only
bytes that already hash to the registry's `sha256` are parsed: the document is one the root
names, not arbitrary input.
"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
import unicodedata
from pathlib import Path

DIR = "index"
SUFFIX = ".index.yaml"
NUMBER = re.compile(r"((?:[0-9]+|[A-Z])(?:\.[0-9]+)+|[0-9]+)\.?\s+\S")


class NotIndexable(Exception):
    """The document cannot be indexed (exit 1, with this message)."""


def title(text: str) -> str:
    """A single-line NFC title holding no character the strict loader refuses (controls,
    invisible and bidirectional formatting, private use, noncharacters): each becomes a space,
    and runs of space collapse, so every title `index` writes loads again."""
    import specload

    text = unicodedata.normalize("NFC", str(text))
    text = "".join(" " if ch.isspace() or specload._refused(ch) else ch for ch in text)
    return unicodedata.normalize("NFC", " ".join(text.split()))


def section(name: str, level: int, rng: tuple, key: str) -> dict:
    out = {}
    m = NUMBER.match(name)
    if m:
        out["number"] = m.group(1)
    out.update({"title": name, "level": level, key: list(rng)})
    return out


def from_pdf(data: bytes) -> dict:
    import io

    import pypdf

    try:
        reader = pypdf.PdfReader(io.BytesIO(data))
        count = len(reader.pages)
        flat = []

        def walk(items, level):
            for item in items:
                if isinstance(item, list):
                    walk(item, level + 1)
                    continue
                page = reader.get_destination_page_number(item)
                name = title(getattr(item, "title", "") or "")
                if page is None or page < 0 or not name:
                    continue  # an external or broken destination: not a place in this file
                flat.append((name, level, page + 1))

        walk(reader.outline, 1)
    except NotIndexable:
        raise
    except Exception as exc:  # pylint: disable=broad-except
        raise NotIndexable(f"cannot read the PDF outline: {type(exc).__name__}: {exc}") from None
    if not flat:
        raise NotIndexable("the PDF has no outline (bookmarks) to index; an index is never "
                          "guessed from page text")
    firsts = [first for _, _, first in flat]
    lasts = []
    for i, (_, level, first) in enumerate(flat):
        last = count
        for _, later_level, later_first in flat[i + 1:]:
            if later_level <= level and later_first >= first:
                last = later_first  # the next section may start part-way down this page
                break
        lasts.append(max(first, last))
    for i in reversed(range(len(flat))):  # a parent covers its children, in any page order
        for j in range(i + 1, len(flat)):
            if flat[j][1] <= flat[i][1]:
                break
            firsts[i], lasts[i] = min(firsts[i], firsts[j]), max(lasts[i], lasts[j])
    sections = [section(name, level, (firsts[i], lasts[i]), "pages")
                for i, (name, level, _) in enumerate(flat)]
    return {"source": "pdf", "pages": count, "sections": sections}


def from_markdown(data: bytes) -> dict:
    from markdown_it import MarkdownIt

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise NotIndexable("neither a PDF nor UTF-8 Markdown") from None
    count = max(1, len(text.splitlines()))
    tokens = MarkdownIt("commonmark").parse(text)
    heads = []
    for i, tok in enumerate(tokens):
        if tok.type == "heading_open" and tok.map:
            name = title(tokens[i + 1].content)
            if name:
                heads.append((name, int(tok.tag[1:]), tok.map[0] + 1))
    if not heads:
        raise NotIndexable("the Markdown file has no headings to index")
    sections = []
    for i, (name, level, first) in enumerate(heads):
        last = count
        for _, later_level, later_first in heads[i + 1:]:
            if later_level <= level:
                last = later_first - 1
                break
        sections.append(section(name, level, (first, max(first, last)), "lines"))
    return {"source": "markdown", "lines": count, "sections": sections}


def build(name: str, data: bytes) -> dict:
    # readers accept a PDF header anywhere in the first KiB
    body = from_pdf(data) if b"%PDF-" in data[:1024] else from_markdown(data)
    return {"format": 2, "document": name, "sha256": hashlib.sha256(data).hexdigest(), **body}


def dump(index: dict, header: list[str]) -> str:
    """Deterministic YAML: the marker's SPDX lines, then one flow mapping per section."""
    import yaml

    def scalar(value):
        return yaml.safe_dump(value, default_flow_style=True, allow_unicode=True,
                              width=10 ** 6).strip().removesuffix("\n...").strip()

    lines = list(header)
    lines.append("# Generated by spec.py index: headings and locators only. Do not edit.")
    for key in ("format", "document", "sha256", "source", "pages", "lines"):
        if key in index:
            lines.append(f"{key}: {scalar(index[key])}")
    lines.append("sections:" if index["sections"] else "sections: []")
    for s in index["sections"]:
        lines.append("  - " + scalar(s))
    return "\n".join(lines) + "\n"


def registry(checker, root, name: str) -> list:
    """Every resources.documents entry named `name` in the root's spec files."""
    return [f.documents[name][0] for f in root.files if name in f.documents]


# --- the command ----------------------------------------------------------------------------

def command(api, args):
    import speccheck

    checker = api._run_check(argparse_like(args))
    root = next(r for r in checker.roots if not r.context)
    entries = registry(checker, root, args.document)
    if not entries:
        raise api.Usage(f"no spec in root {root.label} lists a document named {args.document!r}")
    hashes = {e["sha256"] for e in entries if "sha256" in e}
    if not hashes:
        raise api.Usage(f"document {args.document!r} has no sha256 in resources.documents: "
                        f"an index is pinned to known bytes, so record the hash first")
    if len(hashes) > 1:
        raise api.Usage(f"the root's specs give document {args.document!r} {len(hashes)} "
                        f"different sha256 values")
    path = args.docs_dir / args.document
    if not path.is_file() or speccheck.through_link(path):
        raise api.Usage(f"--docs-dir has no regular file named {args.document!r}")
    data = path.read_bytes()
    want = hashes.pop()
    have = hashlib.sha256(data).hexdigest()
    if have != want:
        return api.EXIT_INVALID, {"ok": False, "path": None, "_text": [
            f"{path}: sha256 {have} is not the registry's {want}; not indexed"]}
    try:
        index = build(args.document, data)
    except NotIndexable as exc:
        return api.EXIT_INVALID, {"ok": False, "path": None, "_text": [f"{path}: {exc}"]}
    marker = (root.given / speccheck.MARKER).read_text(encoding="utf-8").splitlines()
    header = [line for line in marker if line.startswith("# SPDX-")]
    folder = root.given / DIR
    out = folder / (args.document + SUFFIX)
    if (speccheck.through_link(folder) or out.is_symlink()
            or (folder.exists() and not folder.is_dir())
            or (out.exists() and not out.is_file())):
        raise api.Usage(f"{out}: is, or is reached through, a symbolic link, or is not a "
                        f"regular file in a directory; not written")
    folder.mkdir(exist_ok=True)
    # write beside it and rename over it: never through a link, never half a file
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(dump(index, header))
        os.replace(tmp, out)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    shown = len(index["sections"])
    return api.EXIT_OK, {"ok": True, "path": str(out), "sections": shown,
                         "_text": [f"{out}: {shown} section(s) from {index['source']}"]}


def argparse_like(args):
    """The check `index` runs first: the one root, no context, no stubs."""
    import types

    return types.SimpleNamespace(roots=[args.root], context_root=[], require_license=False,
                                 public_skill=[], root=None)


def register(sub):
    p = sub.add_parser("index", help="write a document's section index (headings and locators)",
                       allow_abbrev=False)
    p.add_argument("document", help="the resources.documents name")
    p.add_argument("--root", type=Path, required=True, help="the spec root whose specs list it")
    p.add_argument("--docs-dir", type=Path, required=True,
                   help="document files named exactly by document name")
    p.add_argument("--json", action="store_true", help="one JSON object on stdout")
    p.set_defaults(handler=_run)


def _run(args):
    import spec

    code, result = command(spec, args)
    result["_text"] = [spec.visible_name(line) for line in result["_text"]]
    return code, result


# --- the check ------------------------------------------------------------------------------

def check(checker):
    for root in checker.roots:
        for path, loaded in root.indexes:
            data = loaded.data
            name = data["document"]
            where = (path, root, loaded)

            def warn(at, message):
                checker.add(where, at, message, level="warning")

            if path.name != name + SUFFIX:
                warn(("document",), f"index for {name!r} is named {path.name}: name it "
                                    f"{name}{SUFFIX}")
            entries = registry(checker, root, name)
            if not entries:
                warn(("document",), f"no spec of root {root.label} lists document {name!r}")
                continue
            hashes = {e["sha256"] for e in entries if "sha256" in e}
            if not hashes:
                warn(("sha256",), f"the registry records no sha256 for document {name!r}, so "
                                  f"nothing pins the bytes this index describes")
            elif data["sha256"] not in hashes:
                warn(("sha256",), f"index sha256 is not the registry's for document {name!r}: "
                                  f"the index describes other bytes; regenerate it with "
                                  f"spec.py index")
            counts = {e["pages"] for e in entries if "pages" in e}
            if "pages" in data and counts and data["pages"] not in counts:
                warn(("pages",), f"index counts {data['pages']} pages; the registry gives "
                                 f"{', '.join(str(c) for c in sorted(counts))}")


# --- links for the views --------------------------------------------------------------------

def links(root) -> list[dict]:
    """Each index of the root, its sections, and the fact ids citing each section: a citation
    with a `section` locator at or under the section's number, a `heading` equal to its title,
    or (PDF page numbering only) a page inside its range."""
    import speccheck

    out = []
    for path, loaded in sorted(root.indexes, key=lambda x: x[1].data["document"]):
        data = loaded.data
        name = data["document"]
        cites = []  # (fact full id, locator, pdf-numbered)
        for f in root.files:
            doc = f.documents.get(name, (None,))[0]
            if doc is None:
                continue
            pdf = doc.get("page_numbering") == "pdf"
            for rec in f.records.values():
                for entry, _ in speccheck.supports(rec.data, rec.path):
                    if entry.get("doc") == name:
                        cites += [(rec.full, loc, pdf) for loc in entry.get("at", [])]
        rows = []
        for s in data["sections"]:
            hit = set()
            for full, loc, pdf in cites:
                number = s.get("number")
                if number and "section" in loc and (loc["section"] == number
                                                    or loc["section"].startswith(number + ".")):
                    hit.add(full)
                elif loc.get("heading") == s["title"]:
                    hit.add(full)
                elif pdf and "pages" in s and _within(loc, s["pages"]):
                    hit.add(full)
            rows.append({**s, "facts": sorted(hit)})
        out.append({"document": name, "source": data["source"], "sha256": data["sha256"],
                    "sections": rows})
    return out


def _within(loc, rng) -> bool:
    numbers = [loc["page"]] if "page" in loc else list(loc.get("pages", []))
    return any(n.isascii() and n.isdecimal() and rng[0] <= int(n) <= rng[1]
               for n in numbers if len(n) < 9)
