# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Generate a Markdown reading view from checked format 2 data, never from parsed prose.

Author Markdown is verbatim, inert fenced text. Generated values cannot become links,
images or HTML, including under GFM. The HTML viewer renders author Markdown (SF2-5).
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
import re
import string
from pathlib import Path

import records
import speccheck
import specload
import specmd
import textcheck


def escape(value) -> str:
    """Literal generated text, including table delimiters and HTML/entity punctuation."""
    text = specload.visible_name(str(value).replace("\n", " ").replace("\r", " ")).lstrip()
    if re.search(r"[@:|*_`<\[]|www\.", text, re.IGNORECASE):
        return code(text)
    return re.sub(r"([" + re.escape(string.punctuation) + r"])", r"\\\1", text)


def code(value) -> str:
    """A literal CommonMark code span, even for backticks or leading/trailing spaces."""
    text = specload.visible_name(str(value).replace("\n", " ").replace("\r", " "))
    fence = "`" * (max((len(m[0]) for m in re.finditer(r"`+", text)), default=0) + 1)
    assert len(fence) <= textcheck.MAX_BACKTICKS + 1, "code span exceeds 33 backticks"
    pad = " " if text.startswith("`") or text.endswith("`") or (
        text.startswith(" ") and text.endswith(" ") and text.strip()) else ""
    # Empty spans do not exist in CommonMark; use escaped empty text instead.
    return fence + pad + text + pad + fence if text else ""


def _value(value) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


class View(list):
    """Track intended layout constructs while assembling the view, before parsing it."""

    def __init__(self):
        super().__init__()
        self.expected = Counter()
        self.line = 0

    def append(self, value):
        super().append(value)
        self.line += value.count("\n") + 1

    def extend(self, values):
        for value in values:
            self.append(value)

    def heading(self, level, value):
        self.expected[(self.line, "heading_open", "")] += 1
        self.extend(["#" * level + " " + value, ""])

    def author(self, value, label="Author text"):
        self.extend([label + " (author text):", ""])
        fence = "`" * max(3, max((len(m[0]) + 1 for m in re.finditer(r"`+", value)), default=3))
        assert len(fence) <= textcheck.MAX_BACKTICKS + 1, "author fence exceeds 33 backticks"
        content = value + ("\n" if value and not value.endswith("\n") else "")
        self.expected[(self.line, "fence", content)] += 1
        self.extend([fence + "\n" + content + fence, ""])


def _author(out, value, label="Author text"):
    out.author(value, label)


def _table(out, title, entries):
    if not entries:
        return
    out.heading(3, escape(title))
    keys = list(dict.fromkeys(k for e in entries for k in e if k not in ("note", "files")))
    out.extend(["| " + " | ".join(escape(k).replace("|", "\\|") for k in keys) + " |",
                "| " + " | ".join("---" for _ in keys) + " |"])
    for entry in entries:
        out.append("| " + " | ".join(escape(_value(entry.get(k, ""))).replace("|", "\\|")
                                      for k in keys) + " |")
    out.append("")
    for entry in entries:
        if "note" in entry:
            out.extend(["Note for " + code(entry.get("name", entry.get("path", title))) + ":",
                        ""])
            _author(out, entry["note"])
        if "files" in entry:
            _table(out, "Files: " + entry["name"], entry["files"])


def _resources(out, file):
    if file.data.get("resources"):
        out.heading(2, "Resources: " + escape(file.root.label))
        for group, entries in file.data["resources"].items():
            _table(out, group.capitalize(), entries)


def _locator(at) -> str:
    parts = []
    for key, value in at.items():
        if key == "pages":
            parts.append("pp. " + "–".join(value))
        else:
            label = {"page": "p. ", "section": "§", "heading": 'heading: '}.get(key, key + " ")
            parts.append(label + value)
    return ", ".join(parts)


def _citation(file, entry) -> str:
    """Only structured fields decide the citation. Every generated component is escaped."""
    cls = entry["class"]
    bits = []
    if "doc" in entry:
        doc = file.documents[entry["doc"]][0]
        title = doc["title"] + (" (" + doc["revision"] + ")" if "revision" in doc else "")
        bits.append(escape(title))
        bits.extend(escape(_locator(at)) for at in entry.get("at", []))
    for anchor in entry.get("anchors", []):
        repo = file.repos[anchor["repo"]][0]
        text = f"{repo['name']}@{repo['commit']} ({repo['license']}) {anchor['path']}"
        if "lines" in anchor:
            text += " lines " + "–".join(map(str, anchor["lines"]))
        for key in ("symbol", "node", "search"):
            if key in anchor:
                text += f"; {key}: {anchor[key]}"
        if anchor.get("comment"):
            text += "; comment"
        if "stale" in anchor:
            text += "; stale: " + _value(anchor["stale"])
        bits.append(escape(text))
    skip = {"class", "doc", "at", "anchors", "note", "premises", "derivation"}
    for key, value in entry.items():
        if key not in skip:
            bits.append(escape(key + ": " + _value(value)))
    return escape(cls) + (": " + "; ".join(bits) if bits else "")


def _support(out, checker, file, entries, prefix="- ", notes=None):
    indent = prefix[:-2]
    for entry in entries:
        if entry["class"] != "inference":
            out.append(prefix + _citation(file, entry))
        else:
            out.append(prefix + "inference, from:")
            for premise in entry["premises"]:
                if "fact" in premise:
                    rec, why = checker.resolve(file, premise["fact"])
                    if why:
                        raise ValueError(why)
                    text = code(rec.full) + " (" + escape(rec.data.get("title", rec.id)) + ")"
                    if "uses" in premise:
                        text += ": " + escape(premise["uses"])
                    out.append(indent + "  - " + text)
                elif "states" in premise:
                    out.append(indent + "  - Stated premise (author text below)")
                    if notes is not None:
                        notes.append(("States", premise["states"]))
                    _support(out, checker, file, premise["support"], indent + "    - ", notes)
                else:
                    assumption = file.data["assumptions"][file.assumptions[premise["assumption"]][1]]
                    out.append(indent + "  - assumption " + code(assumption["id"]) + ": " +
                               escape(assumption["text"]))
            out.append(prefix + "derivation: " + escape(entry["derivation"]))
            if "confidence" in entry:
                out.append(prefix + "confidence: " + escape(entry["confidence"]))
        if "note" in entry and notes is not None:
            notes.append(("Support note", entry["note"]))


def _fact(out, checker, rec, status, with_status):
    data, file = rec.data, rec.file
    out.heading(4, escape(data.get("title", data.get("name", rec.id))))
    if "claim" in data:
        _author(out, data["claim"], "Claim")
    else:
        # Instance and variant rows remain visible, using their structured fields.
        for key, value in data.items():
            if key not in ("id", "support", "note", "todo", "title", "name"):
                out.append("- " + escape(key) + ": " + escape(_value(value)))
        out.append("")
    out.extend(["Provenance (generated):", ""])
    if not data.get("support"):
        out.append("- Gap")
    notes = []
    _support(out, checker, file, data.get("support", []), notes=notes)
    for aid in data.get("assumes", []):
        assumption = file.data["assumptions"][file.assumptions[aid][1]]
        out.append("- assumes " + code(aid) + ": " + escape(assumption["text"]))
    if "todo" in data:
        todo = data["todo"]
        out.append("- TODO (verify on " + escape(todo["check"]) + "): " + escape(todo["text"]))
        if "method" in todo:
            out.append("- method: " + escape(todo["method"]))
    if "scope" in data:
        out.append("- scope: " + "; ".join(escape(k) + ": " + ", ".join(escape(v) for v in vals)
                                         for k, vals in data["scope"].items()))
    for relation in data.get("relates", []):
        target, why = checker.resolve(file, relation["fact"])
        if why:
            raise ValueError(why)
        out.append("- " + escape(relation["relation"]) + ": " + code(target.full))
    for conflict in data.get("conflicts", []):
        out.append("- conflict" + (" (contested)" if "resolution" not in conflict else "") +
                   ": " + escape(conflict["reading"]))
        _support(out, checker, file, conflict["support"], "  - ", notes)
        if "note" in conflict:
            notes.append(("Conflict note", conflict["note"]))
        for key in ("resolution", "assumption", "decided"):
            if key in conflict:
                out.append("  - " + key + ": " + escape(_value(conflict[key])))
    text = "- " + code(rec.full)
    if data.get("critical"):
        text += " · bring-up critical"
    if with_status:
        row = status[file][rec.id]
        verdict = file.verdicts.get(rec.id, (None, None))[0]
        if row["verdict"]:
            text += " · " + escape(row["verdict"] + " " + verdict["date"])
        text += " · " + escape(row["status"])
        status_notes = []
        if row["carried"]:
            status_notes.append("carried from format " + str(verdict["carried_from"]["format"]))
        if row["second_reader"] == "missing":
            status_notes.append("second reader missing")
        if status_notes:
            text += " (" + escape("; ".join(status_notes)) + ")"
        if verdict and "note" in verdict:
            notes.append(("Record note", verdict["note"]))
    out.extend([text, ""])
    if "note" in data:
        notes.append(("Fact note", data["note"]))
    for label, note in notes:
        _author(out, note, label)


def render(checker, *, spec_id=None, merged=False, with_status=False,
           source_commit=None, tool_commit=None) -> str:
    """Build selected checked-root views; repeat author-field containment before any output.

    In merged mode context bases/overlays are included only for ids in the checked roots.
    Each layer's resources stay local to that file. No context error can publish unsafe text.
    """
    selected = [f for f in checker.files if not f.root.context
                and (spec_id is None or f.spec_id == spec_id)]
    if not selected:
        raise speccheck.UsageError("no checked spec matches --spec" if spec_id else "no specs to render")
    ids = list(dict.fromkeys(f.spec_id for f in selected))
    if merged:
        groups = [[f for f in checker.files if f.spec_id == sid] for sid in ids]
    else:
        groups = [[f] for f in selected]
    roots = {f.root.given.absolute() for group in groups for f in group}
    commits = {}
    values = [source_commit] if isinstance(source_commit, str) else (source_commit or [])
    for value in values:
        if "=" in value:
            name, sha = value.rsplit("=", 1)
            root = Path(name).absolute()
            if not name or root not in roots:
                raise speccheck.UsageError("--source-commit ROOT must name a rendered root directory")
        else:
            if len(roots) != 1:
                raise speccheck.UsageError("bare --source-commit requires exactly one rendered root")
            root, sha = next(iter(roots)), value
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise speccheck.UsageError("commit must be 40 lowercase hex characters")
        if root in commits:
            raise speccheck.UsageError("--source-commit given twice for a root")
        commits[root] = sha
    for group in groups:
        group.sort(key=lambda f: (f.is_overlay, f.root.rank, f.root.order, str(f.path)))
        for file in group:
            for path, value, _ in textcheck.fields(file.data):
                bad = [f for f in specmd.findings(value) if f.level == "error"]
                if bad:
                    raise ValueError(f"{file.spec_id}: {speccheck._where(path)}: {bad[0].message}")
    status = {entry["file"]: {r["key"]: r for r in entry["rows"]} for entry in checker.status}
    out = View()
    for group in groups:
        base = group[0]
        if out:
            out.extend(["Generated view:", ""])
        out.extend(["Generated by " + code("spec.py render") + ". Do not edit.", "",
                    "Canonical form " + code(records.CANONICAL) + "; driver-lab " +
                    escape(tool_commit or "unavailable") + ".", ""])
        for file in group:
            relative = file.path.relative_to(file.root.given).as_posix()
            digest = hashlib.sha256(file.loaded.source_bytes).hexdigest()
            out.extend(["Source " + code(file.root.label + ":" + relative) + "; commit " +
                        escape(commits.get(file.root.given.absolute(), "unavailable")) +
                        "; SHA256 " + code(digest) + ".", ""])
        out.heading(1, escape(base.data.get("name", base.spec_id)))
        out.extend([code(base.spec_id) + " · " + escape(base.kind) + " · triggers: " +
                    ", ".join(escape(t) for t in base.data.get("triggers", [])), ""])
        for key in ("aliases", "not_triggers", "parts", "variant_of", "cache", "overlays"):
            if key in base.data:
                out.extend([escape(key) + ": " + escape(_value(base.data[key])), ""])
        for file in group:
            _resources(out, file)
        if any(any(key in f.data for key in ("orientation", "milestones", "notes")) for f in group):
            out.heading(2, "Context (not facts)")
            for file in group:
                if any(key in file.data for key in ("orientation", "milestones", "notes")):
                    if file.is_overlay:
                        out.heading(3, "Overlay: " + escape(file.root.layer) + " (" + escape(file.root.label) + ")")
                    if file != group[0] and not file.is_overlay:
                        out.extend(["Context (not facts):", ""])
                    for key in ("orientation", "milestones", "notes"):
                        if key in file.data:
                            _author(out, file.data[key], key.capitalize())
        sections = speccheck.SECTIONS.get(base.kind, ("facts",))
        if base.is_overlay:
            original = next(f for f in checker.files if f.spec_id == base.spec_id and not f.is_overlay)
            sections = speccheck.SECTIONS.get(original.kind, ("facts",))
        for section in sections:
            if not any(r.data.get("section") == section for f in group for r in f.records.values()):
                continue
            out.heading(2, section.capitalize())
            for file in group:
                facts = [r for r in file.records.values() if r.data.get("section") == section]
                if facts and file.is_overlay:
                    out.heading(3, "Overlay: " + escape(file.root.layer) + " (" + escape(file.root.label) + ")")
                for rec in facts:
                    _fact(out, checker, rec, status, with_status)
        for kind in ("instances", "variants"):
            for file in group:
                rows = [r for r in file.records.values() if r.path[0] == kind]
                if rows:
                    out.heading(2, kind.capitalize() + ": " + escape(file.root.label))
                    for rec in rows:
                        _fact(out, checker, rec, status, with_status)
        for file in group:
            if "notices" in file.data:
                out.heading(2, "Source notices: " + escape(file.root.label))
                for notice in file.data["notices"]:
                    out.extend([code(notice["repo"] + ":" + notice["path"]), ""])
                    _author(out, notice["text"], "Notice")
    view = "\n".join(out).rstrip() + "\n"
    specmd.check_view(view, out.expected)
    return view


def command(api, args):
    """CLI adapter: small registration in spec.py, with no partial view on failure."""
    checker = api._run_check(args)
    if args.merged:
        for root in checker.roots:
            if root.context and root.untrusted:
                checker.add((root.given / speccheck.MARKER, root, root.marker), (),
                            "cannot render merged input: context root does not check clean",
                            downgrade=False)
    findings = api._ordered(checker.findings)
    errors = [f for f in findings if f.level == "error"]
    if errors:
        return api.EXIT_INVALID, {"ok": False, "findings": [f.as_dict() for f in findings],
                                  "markdown": None, "_text": [str(f) for f in findings]}
    try:
        view = render(checker, spec_id=args.spec, merged=args.merged, with_status=args.with_status,
                      source_commit=getattr(args, "source_commit", None),
                      tool_commit=getattr(args, "tool_commit", None))
    except speccheck.UsageError as exc:
        raise api.Usage(str(exc)) from None
    except ValueError as exc:
        return api.EXIT_INVALID, {"ok": False, "findings": [{"message": str(exc)}],
                                  "markdown": None, "_text": [str(exc)]}
    return api.EXIT_OK, {"ok": True, "findings": [f.as_dict() for f in findings],
                         "markdown": view, "_text": [view.rstrip("\n")]}
