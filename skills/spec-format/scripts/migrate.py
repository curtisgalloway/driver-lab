# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Mechanically migrate one format 1 spec; leave judgments to the citation pass.

Uses the existing format 1 Markdown reader, at its shared peripheral-spec location.
Document and inference parentheticals remain verbatim in the report. Inference-nested
anchors are structured as report candidates, never promoted into read support.
"""

from __future__ import annotations

import copy
import hashlib
import re
import sys
from collections import Counter
from pathlib import Path

LEGACY = Path(__file__).resolve().parents[2] / "peripheral-spec" / "scripts"
sys.path.insert(0, str(LEGACY))
import mdtokens  # pylint: disable=wrong-import-position

SECTIONS = {
    "Quick-facts": "quick-facts", "Gotchas": "gotchas",
    "Standards and databook": "standards", "Programming model": "programming-model",
    "Known variants and quirks": "variants-quirks",
}
TAG = re.compile(r"`?\[(databook|standard|doc|rtl|DT|src|hardware|emulated|press|inference|source-observed)\]`?")
TODO = re.compile(r"`?TODO\s*\(verify\s+on\s+hardware\)`?\s*:\s*")
SOURCE = re.compile(
    r"\[src:([a-z0-9][a-z0-9._-]*):\s*([^\s:]+):(\d+)(?:-(\d+))?\s+\(([^()\n]+)\)\]"
)
DT = re.compile(r"([^\s,]+\.dtsi?)\s+lines?\s+([\d\s–-]+(?:and\s+[\d\s–-]+)*),\s*([a-z0-9][a-z0-9._-]*)")
COMMIT = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?\Z")
URL = re.compile(r"https://[^\s<>\"')]+")


class MigrationError(ValueError):
    """An input cannot be converted without guessing."""


def slug(text):
    result = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if not result:
        raise MigrationError("a lead-in or resource title has no ASCII slug")
    return result


def frontmatter(raw, name):
    import specload

    match = re.match(r"\A---\n(.*?)\n---(?:\n|\Z)", raw, re.DOTALL)
    if not match:
        raise MigrationError("expected format 1 YAML front matter")
    metadata = specload.load_strict_marked(name, match[1].encode("utf-8")).data
    if not isinstance(metadata, dict) or metadata.get("format", 1) != 1:
        raise MigrationError("expected a format 1 mapping")
    headers = re.findall(r"^# SPDX-[^\n]+", match[1], re.MULTILINE)
    return metadata, raw[match.end():], headers


def token_matches(raw, pattern):
    """Find class tokens using the legacy reader's recorded inline-code/link spans.

    The private Markdown instance is the one used by mdtokens.parse, not another
    parser or a fallback. Its spans let us keep the original claim bytes while
    excluding tag lookalikes in ordinary code or link destinations.
    """
    parsed = mdtokens.parse(raw)
    spans = []
    offset = 0
    for index, line in enumerate(parsed.lines):
        if index in parsed.code_lines:
            spans.append((offset, offset + len(line) + 1))
        offset += len(line) + 1
    for token in mdtokens._markdown().parseInline(raw):  # pylint: disable=protected-access
        for child in token.children or ():
            meta = child.meta or {}
            if child.type == "code_inline" and "span" in meta:
                if not mdtokens.TOKEN_SPAN_RE.fullmatch(child.content.strip()):
                    spans.append(meta["span"])
            elif child.type == "link_open" and "span" in meta:
                spans.append((meta["label_end"], meta["span"][1]))
    return [m for m in pattern.finditer(raw)
            if not any(start <= m.start() < end for start, end in spans)]


def tag_matches(raw):
    return token_matches(raw, TAG)


def clauses(raw):
    """Top-level class clauses; nested premise tags belong to their parenthetical."""
    matches = tag_matches(raw)
    out, end = [], 0
    for match in matches:
        if match.start() < end:
            continue
        pos = match.end()
        while pos < len(raw) and raw[pos].isspace():
            pos += 1
        if pos >= len(raw) or raw[pos] != "(":
            raise MigrationError(f"{match.group(1)} tag lacks a parenthetical")
        depth, cursor = 1, pos + 1
        while cursor < len(raw) and depth:
            if raw[cursor] == "(":
                depth += 1
            elif raw[cursor] == ")":
                depth -= 1
            cursor += 1
        if depth:
            raise MigrationError("unclosed citation parenthetical")
        out.append((match.group(1), raw[pos + 1:cursor - 1], raw[match.start():cursor]))
        end = cursor
    return out


def read_bullets(body):
    doc = mdtokens.parse(body)
    problems = mdtokens.profile_violations(doc) + mdtokens.anchor_problems(doc)
    if problems:
        raise MigrationError("outside the format 1 Markdown profile: " + problems[0][1])
    counts, bullets = Counter(), []
    for item in doc.items:
        section = mdtokens.section_of(doc, item.start)
        if item.parent is not None or section not in SECTIONS:
            continue
        lines = doc.lines[item.start:item.end]
        start = re.match(r"^(?:[-+*]|\d+[.)])\s+\*\*(.+?)\*\*\s*", lines[0])
        if not start:
            raise MigrationError("each fact bullet needs a bold lead-in")
        title = start[1].removesuffix(".")
        counts[section] += 1
        text = lines[0][start.end():] + "\n" + "\n".join(
            line[2:] if line.startswith("  ") else line for line in lines[1:])
        text = text.rstrip()
        matches = tag_matches(text)
        marker = next(iter(token_matches(text, TODO)), None)
        cut = matches[0].start() if matches else marker.start() if marker else len(text)
        claim = text[:cut].rstrip()
        if not claim:
            raise MigrationError("empty claim")
        provenance = text[cut:marker.start() if marker else len(text)].strip()
        parsed = clauses(provenance)
        classes = {c for c, _, _ in parsed}
        key = f'{section}/{counts[section]} "{title}"'
        bullets.append({"key": key, "title": title, "section": SECTIONS[section],
                        "claim": claim, "provenance": provenance, "clauses": parsed,
                        "original_todo": text[marker.end():] if marker else None,
                        "mixed": "inference" in classes and len(classes) > 1})
    bases = Counter(slug(b["title"]) for b in bullets)
    used = set()
    for bullet in bullets:
        fact_id = slug(bullet["title"])
        if bases[fact_id] > 1:
            fact_id += "-" + slug(bullet["section"])
        if fact_id in used:
            raise MigrationError("duplicate lead-ins in one section; choose ids in a later pass")
        used.add(fact_id)
        bullet["id"] = fact_id
    return doc, bullets


def anchors(kind, content, repos):
    """Convert only complete, unambiguous citation payloads at a declared full pin."""
    result = []
    if kind == "src":
        matches = list(SOURCE.finditer(content))
        remainder = SOURCE.sub("", content).strip(" \n;,`")
        if not matches or remainder:
            return None
        for match in matches:
            repo, path, first, last, symbol = match.groups()
            result.append({"repo": repo, "path": path,
                           "lines": [int(first), int(last or first)], "symbol": symbol})
    elif kind == "DT":
        match = DT.fullmatch(" ".join(content.split()))
        if not match:
            return None
        basename, ranges, repo = match.groups()
        paths = [f["path"] for f in repos.get(repo, {}).get("files", [])
                 if f["path"] == basename or Path(f["path"]).name == basename]
        if len(paths) != 1:
            return None
        for part in re.split(r"\s+and\s+", ranges.strip()):
            span = re.fullmatch(r"(\d+)\s*(?:[-–]\s*(\d+))?", part.strip())
            if not span:
                return None
            result.append({"repo": repo, "path": paths[0],
                           "lines": [int(span[1]), int(span[2] or span[1])]})
    else:
        return None
    for anchor in result:
        entry = repos.get(anchor["repo"], {})
        if not COMMIT.fullmatch(str(entry.get("commit", ""))):
            return None
        if anchor["path"] not in {f["path"] for f in entry.get("files", [])}:
            return None
        if anchor["lines"][0] < 1 or anchor["lines"][1] < anchor["lines"][0]:
            return None
    return result


def resources_v2(resources, license_from):
    result, notes = {}, []
    for key, value in resources.items():
        if not value:
            continue
        if key not in ("docs", "repos"):
            result[key] = copy.deepcopy(value)
    documents, used = [], set()
    for item in resources.get("docs", []):
        doc = copy.deepcopy(item)
        name = slug(doc["title"])
        if name in used:
            raise MigrationError("document titles do not have unique slugs")
        used.add(name)
        doc["name"] = name
        doc["class"] = "doc"
        notes.append(f"citation-pass: document {name}: provisional class doc; assign its read class and locators.")
        if doc.get("cite") is True:
            del doc["cite"]
        fetch_via = doc.pop("fetch_via", "")
        note = doc.get("note", "")
        hashes = set(re.findall(r"SHA-256\s+([0-9a-f]{64})", note + " " + fetch_via))
        if len(hashes) > 1:
            raise MigrationError("conflicting document hashes")
        if hashes:
            doc["sha256"] = next(iter(hashes))
            note = re.sub(r"SHA-256\s+[0-9a-f]{64}", "", note).strip(" ;,")
        urls = list(dict.fromkeys(URL.findall(fetch_via) + re.findall(
            r"also served at (https://[^\s;.]+(?:\.[^\s;.]+)*)", note)))
        if urls:
            doc["retrieval"] = [{"url": url.rstrip(".,;")} for url in urls]
        elif fetch_via:
            notes.append(f"citation-pass: {name}: fetch guidance retained in report: {fetch_via}")
        pins = set(re.findall(r"/(?:blob|tree)/([0-9a-f]{40})/", doc["url"]))
        pins.update(re.findall(r"(?:wiki )?commit ([0-9a-f]{40})", note + " " + fetch_via))
        if len(pins) > 1:
            raise MigrationError("conflicting document commits")
        if pins:
            doc["commit"] = next(iter(pins))
        pages = re.search(r"(\d+)-page|\b(\d+) pp\b", note + " " + fetch_via)
        if pages:
            doc["pages"] = int(pages[1] or pages[2])
        if "printed page" in note.lower():
            doc["page_numbering"] = "printed"
        if note:
            doc["note"] = note
        else:
            doc.pop("note", None)
        documents.append(doc)
    if documents:
        result["documents"] = documents
    repos = []
    for item in resources.get("repos", []):
        repo = copy.deepcopy(item)
        pin = repo.get("ref")
        if isinstance(pin, str) and COMMIT.fullmatch(pin):
            repo["commit"] = repo.pop("ref")
        files = []
        for file in repo.get("files", []):
            if isinstance(file, dict):
                files.append(file)
                continue
            key = f'{repo["name"]}:{file}'
            method = license_from.get(key)
            if method not in {"spdx-line", "notice", "license-file"}:
                raise MigrationError(f"supply --license-from {key}=METHOD; format 1 does not declare that field")
            files.append({"path": file, "license_from": method})
        if files:
            repo["files"] = files
        else:
            repo.pop("files", None)
        repos.append(repo)
    if repos:
        result["repos"] = repos
    return result, notes


def convert(raw, name=Path("input.spec.md"), *, license_from=None):
    metadata, body, headers = frontmatter(raw, name)
    doc, bullets = read_bullets(body)
    result = {"format": 2, **copy.deepcopy(metadata)}
    result["kind"] = "overlay" if "overlays" in metadata else metadata.get("kind")
    for key in ("aliases", "not_triggers", "parts", "variants"):
        if result.get(key) == []:
            result.pop(key)
    resources, resource_notes = resources_v2(metadata.get("resources", {}), license_from or {})
    if resources:
        result["resources"] = resources
    else:
        result.pop("resources", None)
    repos = {r["name"]: r for r in resources.get("repos", [])}
    facts, rows = [], []
    for bullet in bullets:
        fact = {key: bullet[key] for key in ("id", "section", "title", "claim")}
        support, pending, candidates = [], [], []
        for kind, content, literal in bullet["clauses"]:
            converted = anchors(kind, content, repos)
            if converted:
                support.append({"class": kind, "anchors": converted})
            else:
                pending.append(literal)
            if kind == "inference":
                for nested_kind, nested_content, _ in clauses(content):
                    nested = anchors(nested_kind, nested_content, repos)
                    if nested:
                        candidates.append({"class": nested_kind, "anchors": nested})
                for match in SOURCE.finditer(content):
                    nested = anchors("src", match[0], repos)
                    if nested and not any(a in c["anchors"] for c in candidates for a in nested):
                        candidates.append({"class": "src", "anchors": nested})
        if support:
            fact["support"] = support
        citation_pass = bool(pending or (not support and not bullet["original_todo"]))
        todo = []
        if bullet["original_todo"]:
            todo.append(bullet["original_todo"])
        if citation_pass:
            todo.append(f'citation-pass: structure the original provenance retained under {bullet["id"]} in the migration report; no verdict carries yet.')
        if bullet["mixed"]:
            todo.append("split-mixed: separate the read claim and derived conclusion in a later pass.")
        if todo:
            fact["todo"] = {"check": "hardware" if bullet["original_todo"] else "document",
                            "text": "\n\n".join(todo)}
        facts.append(fact)
        rows.append({**bullet, "structured": support, "candidates": candidates,
                     "citation_pass": citation_pass})
    result["facts"] = facts
    orientation = []
    notices = []
    headings = doc.headings + [(len(doc.lines), 1, "")]
    fact_ranges = [(i.start, i.end) for i in doc.items
                   if i.parent is None and mdtokens.section_of(doc, i.start) in SECTIONS]
    for index, (line, level, heading) in enumerate(headings[:-1]):
        end = headings[index + 1][0]
        text = "\n".join(doc.lines[line + 1:end]).strip()
        if heading == "Source notices":
            fences = re.findall(r"```(?:text)?\n(.*?)\n```", text, re.DOTALL)
            for notice in fences:
                paths = [(r["name"], f["path"]) for r in repos.values()
                         for f in r.get("files", []) if f["license_from"] == "notice"]
                if len(paths) != 1:
                    raise MigrationError("source notice has no unique declared notice file")
                notices.append({"repo": paths[0][0], "path": paths[0][1], "text": notice})
            if not fences:
                raise MigrationError("source notices need a fenced literal notice")
        elif heading not in SECTIONS and text:
            orientation.append(text)
        elif heading in SECTIONS:
            extra = "\n".join(doc.lines[n] for n in range(line + 1, end)
                              if not any(a <= n < b for a, b in fact_ranges)).strip()
            if extra:
                raise MigrationError("prose outside fact bullets in a fact section needs manual placement")
    if orientation:
        result["orientation"] = "\n\n".join(orientation)
    if notices:
        result["notices"] = notices
    summary = {"facts": len(facts), "structured_citations": sum(
        len(s["anchors"]) for row in rows for s in row["structured"]),
        "deferred_anchor_candidates": sum(len(s["anchors"]) for row in rows for s in row["candidates"]),
        "citation_pass_todos": sum(row["citation_pass"] for row in rows),
        "mixed_bullets": sum(row["mixed"] for row in rows)}
    return result, {"summary": summary, "rows": rows, "resources": resource_notes,
                    "original_resources": metadata.get("resources", {}),
                    "headers": headers, "input_sha256": hashlib.sha256(raw.encode()).hexdigest()}


def yaml_text(data, headers=()):
    import yaml

    class Dumper(yaml.SafeDumper):
        def ignore_aliases(self, data):
            return True

    def represent_string(dumper, value):
        return dumper.represent_scalar("tag:yaml.org,2002:str", value,
                                       style="|" if "\n" in value else '"')

    Dumper.add_representer(str, represent_string)
    return "".join(h + "\n" for h in headers) + yaml.dump(
        data, Dumper=Dumper, sort_keys=False, allow_unicode=True, width=100)


def map_verdict_keys(raw, report):
    """Retain exact record keys, including punctuation, without carrying judgments."""
    _, body, _ = frontmatter(raw, Path("input.verify.md"))
    doc = mdtokens.parse(body)
    by_position = {row["key"].split(' "', 1)[0]: row for row in report["rows"]}
    seen = set()
    for item in doc.items:
        if item.parent is not None:
            continue
        match = re.match(r'^[-+*]\s+(.+?/\d+) "(.*?)": (?:PASS|FAIL|GAP|UNVERIFIABLE|ADJUDICATE)\b', doc.lines[item.start])
        if not match:
            continue
        position, title = match.groups()
        row = by_position.get(position)
        if row is None or position in seen or title.removesuffix(".") != row["title"]:
            raise MigrationError("verification keys do not match spec positions and lead-ins")
        row["key"] = f'{position} "{title}"'
        seen.add(position)
    if seen != set(by_position):
        raise MigrationError("verification record does not cover every fact exactly once")


def fence(text):
    ticks = "`" * max(3, max((len(m[0]) + 1 for m in re.finditer(r"`+", text)), default=3))
    return f"{ticks}\n{text}\n{ticks}"


def report_text(report):
    lines = ["<!-- SPDX-FileCopyrightText: 2026 contributors; SPDX-License-Identifier: Apache-2.0 -->",
             "# Mechanical migration report", "",
             "Terms: a fact is one claim record; support is structured evidence; citation-pass marks",
             "work for a later reader. See driver-lab's GLOSSARY.md. No verdicts are carried.", "",
             f'Input SHA-256: `{report["input_sha256"]}`.', "",
             "Counts: " + ", ".join(f"{key}={value}" for key, value in report["summary"].items()) + ".", "",
             "Structured citations count emitted anchors, not support groups. Deferred anchor candidates",
             "belong to inference premises; they are not support for the whole conclusion.", "",
             "Claim extraction removes the list marker, bold lead-in and two-space continuation indent",
             "and trims the separating whitespace before provenance. Internal newlines remain unchanged.", "",
             "## Verdict key map", "", "| Format 1 key | Format 2 fact id | Follow-up |",
             "| --- | --- | --- |"]
    for row in report["rows"]:
        flags = [flag for flag, enabled in (("citation-pass", row["citation_pass"]),
                                           ("split-mixed", row["mixed"])) if enabled]
        key = row["key"].replace("|", "&#124;")
        lines.append(f'| {key} | `{row["id"]}` | {", ".join(flags) or "fidelity check"} |')
    lines += ["", "## Resource follow-up", "", *report["resources"], "",
              "Document classes default provisionally to doc: the citation pass must classify them.",
              "license_from fields are caller declarations, not new source verification.", "",
              "Original format 1 resources (retained so fetch/revision guidance is not lost):", "",
              fence(yaml_text(report["original_resources"]).rstrip()), "",
              "## Original provenance and deferred candidates", ""]
    for row in report["rows"]:
        claim_hash = hashlib.sha256(row["claim"].encode("utf-8")).hexdigest()
        lines += [f'### {row["id"]}', "", row["key"], "",
                  f"Extracted claim SHA-256: `{claim_hash}`.", "",
                  "Original provenance (verbatim after continuation indentation removal):", "",
                  fence(row["provenance"] or "(no citation)"), ""]
        if row["original_todo"]:
            lines += ["Original hardware TODO:", "", fence(row["original_todo"]), ""]
        if row["candidates"]:
            lines += ["Deferred structured anchor candidates (premise assignment still required):", "",
                      fence(yaml_text(row["candidates"]).rstrip()), ""]
    return "\n".join(lines) + "\n"


def run(args):
    import spec
    import specload

    source = args.file
    if not source.is_file() or source.is_symlink() or not source.name.endswith(".spec.md"):
        raise spec.Usage("migrate expects an existing *.spec.md file")
    output = args.output or source.with_suffix(".yaml")
    report_path = args.report or output.with_name(output.name.removesuffix(".spec.yaml") + ".migration-report.md")
    if not output.name.endswith(".spec.yaml"):
        raise spec.Usage("migrate output must end in .spec.yaml")
    mappings = {}
    for assignment in args.license_from:
        key, sep, value = assignment.partition("=")
        if not sep or ":" not in key or value not in {"spdx-line", "notice", "license-file"} or key in mappings:
            raise spec.Usage("--license-from expects a unique REPO:PATH=spdx-line|notice|license-file")
        mappings[key] = value
    try:
        raw = source.read_text(encoding="utf-8")
        data, report = convert(raw, source, license_from=mappings)
        verdicts = args.verdicts or source.parent / "resources" / (
            source.name.removesuffix(".spec.md") + ".verify.md")
        if args.verdicts or verdicts.exists():
            map_verdict_keys(verdicts.read_text(encoding="utf-8"), report)
        payloads = [(output, yaml_text(data, report["headers"])), (report_path, report_text(report))]
        marker = args.marker or source.parent / "board-specs.yaml"
        if args.marker or marker.exists():
            marker_data = specload.load_strict(marker)
            if not isinstance(marker_data, dict) or marker_data.get("format", 1) != 1:
                raise MigrationError("expected a format 1 root marker")
            marker_data = {**marker_data, "format": 2}
            marker_headers = re.findall(r"^# SPDX-[^\n]+", marker.read_text(encoding="utf-8"), re.MULTILINE)
            payloads.append((output.parent / "board-specs.yaml", yaml_text(marker_data, marker_headers)))
        paths = [p.absolute() for p, _ in payloads]
        if len(set(paths)) != len(paths) or any(p.exists() or p.is_symlink() for p in paths):
            raise spec.Usage("migration outputs must be distinct new files; nothing was overwritten")
        if any(parent.is_symlink() for path in paths for parent in path.parents):
            raise spec.Usage("migration output paths cannot pass through symlinks")
        findings = []
        schemas = spec.load_schemas()
        for path, text in payloads:
            if path != report_path:
                spec.validate_file(path, schemas, None, findings, raw=text.encode("utf-8"))
        if findings:
            return 1, {"ok": False, "summary": report["summary"],
                       "findings": [f.as_dict() for f in findings],
                       "_text": [str(f) for f in findings]}
        for path, text in payloads:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("x", encoding="utf-8") as stream:
                stream.write(text)
    except (MigrationError, specload.LoadError, UnicodeError, OSError) as exc:
        return 1, {"ok": False, "findings": [{"message": str(exc)}], "_text": [str(exc)]}
    return 0, {"ok": True, "summary": report["summary"],
               "files": [str(p) for p, _ in payloads], "findings": [],
               "_text": [f"migrated {report['summary']['facts']} facts; citation pass and fidelity check remain"]}


def register(subparsers):
    parser = subparsers.add_parser("migrate", help=__doc__.splitlines()[0], allow_abbrev=False)
    parser.add_argument("file", type=Path)
    parser.add_argument("--output", type=Path, help="new *.spec.yaml (default: beside input)")
    parser.add_argument("--report", type=Path, help="new migration report Markdown file")
    parser.add_argument("--marker", type=Path, help="format 1 marker (default: beside input if present)")
    parser.add_argument("--verdicts", type=Path,
                        help="v1 record for exact key mapping (default: sibling resources record if present)")
    parser.add_argument("--license-from", action="append", default=[], metavar="REPO:PATH=METHOD",
                        help="declare each v1 file's license location; no source reading or guessing")
    parser.add_argument("--json", action="store_true")
    parser.set_defaults(handler=run)
