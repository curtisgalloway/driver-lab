# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""`spec.py check`: what a schema cannot check (design: Validation; SF2-2).

Given roots (directories holding a format 2 `board-specs.yaml`), the checker discovers every
`*.spec.yaml` below each root, validates it against the schema, and then checks, over the
already-parsed data and never over prose:

- roots: marker `license` an SPDX expression; `accepts` single identifiers in canonical
  spelling, none twice; root names unique among the roots read together; no symbolic link in or
  above a root; no nested marker; no file that looks like a spec but would not be discovered;
- composition: spec ids unique across every root (aliases too); `parts`, `variant_of`,
  `instances[].ip` and an overlay's target resolve, to the right kind; no `parts` cycle; an
  overlay merges no earlier than its target (layer) and uses its target kind's sections;
- names: every `doc`, `repo` and `assumption` name resolves in the citing file; document class
  matches the citation class; a `cite: false` document is never cited; numeric pages lie within
  the document's `pages`, written without leading zeros, `pages` in order; a `standard` locator
  is precise when its document is paged; `lines` in order; an anchored repos entry carries a
  `commit` and lists the cited path in `files`; `irq.intid` agrees with `number`;
- ids: fact ids (facts, instance and variant rows: the record keys) unique per spec id per root;
  assumption ids unique per file;
- references (`#id`, `spec#id`, `spec@root#id`, D1): resolve, the short forms only in the citing
  file's own root; never into a later layer; inference premises acyclic; a premise list or a
  relates list never names one fact twice;
- the license gate (D13), one function over one structure: every anchor and notice names a repos
  entry whose license the file's root accepts, and every fact reference reaches, through its
  target's citations and references followed transitively, only repos entries the citing root
  accepts; with --require-license, also every repos entry no anchor or notice names;
- under a `public` layer: no `access: internal`, no tool `via:` a skill not named with
  --public-skill; anywhere: no unsubstituted template placeholder (`<...>` outside code);
- stubs (--stub, --stubs-from): each names a `spec: <id>` that resolves;
- verification records (`resources/<name>.verify.yaml`, records.py, SF2-3): each belongs to the
  spec file of its name, its keys name that file's facts, its summary counts its verdicts; a
  current FAIL is an error; stale, upstream-stale, unverified and unknown verdicts and a critical
  fact without a second reader are warnings, errors under --require-verified (`pr`: all; `main`:
  all but upstream-stale, D19).

A finding in a --context-root's own files is a warning (that root fails in its own checks); a
finding is always attributed to the file it was found in, so a context root cannot downgrade a
checked root's finding.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import os
import re
import sys
from collections import deque
from pathlib import Path

LAYERS = ("public", "ip-vendor", "soc-vendor", "product", "local")
MARKER = "board-specs.yaml"
SECTIONS = {
    "board": ("quick-facts", "gotchas"),
    "soc": ("quick-facts", "gotchas"),
    "chip": ("quick-facts", "gotchas"),
    "ip": ("standards", "programming-model", "variants-quirks", "gotchas"),
}
ANCHORED = ("src", "DT", "rtl")
DOC_CLASS = {"databook": "databook", "standard": "standard", "doc": "doc"}  # citation -> document
PRECISE = ("section", "page", "pages", "table", "figure", "clause")
IRQ_OFFSET = {"SPI": 32, "PPI": 16}
REF = re.compile(r"(?:([a-z0-9][a-z0-9-]*)(?:@([a-z0-9][a-z0-9._-]*))?)?#([a-z0-9][a-z0-9-]*)")
DIGITS = re.compile(r"[0-9]+")
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)
STUB = re.compile(r"`spec:\s*([a-z0-9][a-z0-9\-]*)`")
SPDX_PY = Path(__file__).resolve().parents[2] / "board-expert" / "scripts" / "spdx.py"


class UsageError(Exception):
    """Exit 2."""


class PreconditionError(Exception):
    """Exit 3."""


def load_spdx():
    """board-expert's SPDX parser and acceptance rule, loaded by path (the gate's one rule)."""
    if not SPDX_PY.is_file():
        raise PreconditionError(f"{SPDX_PY} not found (install board-expert beside spec-format)")
    name = "_spec_format_spdx"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, SPDX_PY)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses look their module up while the class is built
    try:
        spec.loader.exec_module(module)
    except BaseException:
        del sys.modules[name]
        raise
    return module


@dataclasses.dataclass
class Finding:
    path: str
    line: int
    column: int
    message: str
    level: str = "error"

    def as_dict(self):
        return dataclasses.asdict(self)

    def __str__(self):
        return f"{self.path}:{self.line}:{self.column}: {self.level}: {self.message}"


@dataclasses.dataclass(eq=False)
class Root:
    given: Path
    real: Path
    context: bool
    order: int
    name: str | None = None
    layer: str | None = None
    rank: int = 0
    accepts: frozenset | None = None  # None: the marker is invalid; its specs are not read
    extension: dict | None = None
    marker: object = None  # the marker's Loaded, for positions
    files: list = dataclasses.field(default_factory=list)
    spec_paths: list = dataclasses.field(default_factory=list)  # every *.spec.yaml found
    record_paths: list = dataclasses.field(default_factory=list)  # resources/*.verify.yaml
    # Every error-severity finding its own check produced, before context downgrading. A root
    # with any is untrusted: no reference may rest on it (user decision, 2026-10-08).
    untrusted: list = dataclasses.field(default_factory=list)

    @property
    def label(self) -> str:
        return self.name or str(self.given)


@dataclasses.dataclass(eq=False)
class SpecFile:
    path: Path
    root: Root
    loaded: object
    data: dict
    records: dict = dataclasses.field(default_factory=dict)  # fact id -> Record
    duplicated: set = dataclasses.field(default_factory=set)  # fact ids declared twice here
    assumptions: dict = dataclasses.field(default_factory=dict)  # id -> path
    documents: dict = dataclasses.field(default_factory=dict)  # name -> (entry, path)
    repos: dict = dataclasses.field(default_factory=dict)  # name -> (entry, path)
    # Names this file declares twice, so a citation of them is ambiguous (freshness: unknown):
    # ("documents", name), ("repos", name), ("assumptions", id), ("files", repos name, path).
    ambiguous: set = dataclasses.field(default_factory=set)
    # Its verification record (records.py): none | ok | invalid | shared; valid verdicts by id.
    record_state: str = "none"
    record_path: Path | None = None
    record_loaded: object = None
    verdicts: dict = dataclasses.field(default_factory=dict)  # fact id -> (verdict, key path)

    @property
    def kind(self) -> str:
        return self.data["kind"]

    @property
    def is_overlay(self) -> bool:
        return self.kind == "overlay"

    @property
    def spec_id(self) -> str:
        return self.data["overlays"] if self.is_overlay else self.data["id"]


@dataclasses.dataclass(eq=False)
class Record:
    """A fact, an instance row or a variant row: anything a verification record keys."""

    file: SpecFile
    path: tuple
    data: dict

    @property
    def id(self) -> str:
        return self.data["id"]

    @property
    def full(self) -> str:
        return f"{self.file.spec_id}@{self.file.root.label}#{self.id}"


def supports(data: dict, base: tuple):
    """Every support entry a record carries, with its path: its own, its premises', and its
    conflicts' (a premise's or a conflict's support is never an inference: the schema)."""
    for i, entry in enumerate(data.get("support", [])):
        yield entry, base + ("support", i)
        if entry.get("class") == "inference":
            for j, premise in enumerate(entry.get("premises", [])):
                for k, sub in enumerate(premise.get("support", [])):
                    yield sub, base + ("support", i, "premises", j, "support", k)
    for c, conflict in enumerate(data.get("conflicts", [])):
        for k, sub in enumerate(conflict.get("support", [])):
            yield sub, base + ("conflicts", c, "support", k)


def references(data: dict, base: tuple):
    """Every fact reference a record makes: (kind, reference, path of the value)."""
    for i, entry in enumerate(data.get("support", [])):
        if entry.get("class") == "inference":
            for j, premise in enumerate(entry.get("premises", [])):
                if "fact" in premise:
                    yield "premise", premise["fact"], base + ("support", i, "premises", j, "fact")
    for r, relation in enumerate(data.get("relates", [])):
        yield "relates", relation["fact"], base + ("relates", r, "fact")
    for entry, path in supports(data, base):
        if entry.get("class") == "emulated" and "observation" in entry:
            yield "observation", entry["observation"], path + ("observation",)


def anchors(data: dict, base: tuple):
    """Every anchor of an anchored class (src, DT, rtl) a record carries, with its path."""
    for entry, path in supports(data, base):
        if entry.get("class") in ANCHORED:
            for a, anchor in enumerate(entry.get("anchors", [])):
                yield anchor, path + ("anchors", a)


def through_link(path: Path) -> bool:
    """Whether path is, or is reached through, a symbolic link; each component as given, so
    the link in `/bin/../x` is seen although `..` cancels it lexically."""
    cur = Path(path.anchor) if path.is_absolute() else Path.cwd()
    for part in path.parts[1:] if path.is_absolute() else path.parts:
        cur = cur / part
        if cur.is_symlink():
            return True
    return False


class Checker:
    def __init__(self, api, spdx, *, require_license=False, public_skills=(),
                 require_verified=None):
        self.api = api
        self.require_verified = require_verified  # None, "pr" or "main" (D19)
        self.schemas = None
        self.status: list = []  # per spec file: freshness rows (records.second_pass)
        self.spdx = spdx
        self.require_license = require_license
        self.public_skills = set(public_skills)
        self.roots: list[Root] = []
        self.files: list[SpecFile] = []
        self.findings: list[Finding] = []
        self.stubs = 0
        self.unreadable_markers: list = []  # markers whose root name is therefore unknown
        self._resolved: dict = {}
        # (file, path) of every reference the check rejected: the one record of "this reference
        # failed", read by the trust pass and by freshness (a fact resting on one is unknown)
        self._failed_refs: set = set()
        # (file, path) of every citation (a document citation, an anchor, an assumption name)
        # the check rejected, under the citing record's path: freshness reads the record as
        # unknown (review round 2)
        self._failed_cites: set = set()
        self._reach: dict = {}

    # --- findings ----------------------------------------------------------------------------

    def add(self, where, path: tuple, message: str, *, level="error", key=False,
            downgrade=True):
        """A finding at a value (or its key) of a spec file, or at line 1 of a plain path.

        where is a SpecFile, or (Path, Root, Loaded-or-None). A finding in a context root's own
        file is a warning, unless downgrade is False: a condition of the run's inputs that
        could change what a checked root's references resolve to stays an error."""
        if isinstance(where, SpecFile):
            file, root, loaded = where.path, where.root, where.loaded
        else:
            file, root, loaded = where
        mark = loaded.mark(path, key=key) if loaded is not None else None
        line, column = (mark.line, mark.column) if mark else (1, 1)
        if root is not None and level == "error":
            root.untrusted.append(f"{file}:{line}:{column}: {message}")
        if root is not None and root.context and downgrade:
            level, message = "warning", f"context root: {message}"
        self.findings.append(Finding(str(file), line, column, message, level))

    def reject(self, f, path: tuple, message: str, *, citation=False):
        """An error at a reference, or at a citation (citation=True): reported, and recorded as
        failed, in one step."""
        (self._failed_cites if citation else self._failed_refs).add((f, path))
        self.add(f, path, message)

    def _schema_findings(self, raw, root):
        for f in raw:
            level, message = "error", f.message
            if root is not None:
                root.untrusted.append(f"{f.path}:{f.line}:{f.column}: {message}")
            if root is not None and root.context:
                level, message = "warning", f"context root: {message}"
            self.findings.append(Finding(f.path, f.line, f.column, message, level))

    # --- loading -----------------------------------------------------------------------------

    def load_roots(self, checked: list[Path], context: list[Path], schemas):
        self.schemas = schemas
        given = [(p, False) for p in checked] + [(p, True) for p in context]
        for p, _ in given:
            if not p.is_dir():
                raise UsageError(f"{p}: not a directory")
        reals = [(p.resolve(), p, ctx) for p, ctx in given]
        for i, (a, pa, ca) in enumerate(reals):
            for b, pb, cb in reals[i + 1:]:
                if a == b:
                    raise UsageError(f"{pa} and {pb} are the same root; give each root once")
                if a in b.parents or b in a.parents:
                    inner, outer = (pa, pb) if b in a.parents else (pb, pa)
                    kind = "a context root and a checked root" if ca != cb else "two roots"
                    raise UsageError(f"{inner} sits inside {outer}: {kind} must be separate "
                                     f"directories")
        for order, (real, p, ctx) in enumerate(reals):
            root = Root(given=p, real=real, context=ctx, order=order)
            if through_link(p):
                if ctx:
                    raise UsageError(f"--context-root {p} is, or is reached through, a symbolic "
                                     f"link; give its real path")
                self.add((p, root, None), (), "spec root is, or is reached through, a symbolic "
                                              "link: give its real path")
                continue
            if not (p / MARKER).is_file():
                raise PreconditionError(f"{p}: no {MARKER} (not a spec root)")
            self.roots.append(root)
            self.read_marker(root, schemas)
            files = self.walk(root)
            if root.accepts is None:
                root.record_paths = []
                continue  # an invalid marker: its specs are not read (references to it dangle)
            root.spec_paths = files
            for path in files:
                self.load_spec(root, path, schemas)

    def read_marker(self, root: Root, schemas):
        marker = root.given / MARKER
        raw = []
        ok, _, loaded = self.api.validate_file(marker, schemas, None, raw)
        self._schema_findings(raw, root)
        if not ok:
            self.unreadable_markers.append(marker)  # its root's name is unknown
            return
        data = loaded.data
        root.marker = loaded
        root.name, root.layer = data["name"], data["layer"]
        root.rank = LAYERS.index(root.layer)
        root.extension = self.api.load_extension(marker, data, [])
        where = (marker, root, loaded)
        try:
            self.spdx.parse(data["license"])
        except self.spdx.SpdxError as exc:
            self.add(where, ("license",), f"license: {exc}")
        accepts, seen = set(), {}
        for i, item in enumerate(data["accepts"]):
            try:
                canonical = self.spdx.parse_identifier(item)
            except self.spdx.SpdxError as exc:
                self.add(where, ("accepts", i), f"accepts entry {item!r}: {exc}")
                continue
            if canonical != item:
                self.add(where, ("accepts", i), f"accepts entry {item!r}: write it as "
                                                f"{canonical!r}, its one spelling")
            if canonical in seen:
                self.add(where, ("accepts", i), f"accepts lists {canonical} twice (as "
                                                f"{seen[canonical]!r} and {item!r})")
            seen.setdefault(canonical, item)
            accepts.add(canonical)
        root.accepts = frozenset(accepts)

    def walk(self, root: Root) -> list[Path]:
        """The spec files below root, found without following links. A link is a finding in a
        checked root and a usage error in a context root; so is a nested marker, and a file
        whose name says spec but which discovery would pass over."""
        found, failures = [], []
        for top, dirs, names in os.walk(root.given, followlinks=False, onerror=failures.append):
            dirs.sort()
            for name in sorted(dirs) + sorted(names):
                path = Path(top) / name
                if path.is_symlink():
                    if root.context:
                        raise UsageError(f"--context-root {root.given}: {path} is a symbolic "
                                         f"link; a root holds its files itself")
                    self.add((path, root, None), (), "symbolic link in a spec root: a root "
                                                     "holds its files itself, never through links")
                    continue
                if name not in names:
                    continue
                lower = name.lower()
                if name == MARKER and Path(top) != root.given:
                    self.add((path, root, None), (), f"a nested {MARKER} inside root "
                                                     f"{root.label}: one root, one marker")
                elif name.endswith(".spec.yaml"):
                    found.append(path)
                elif name.endswith(".verify.yaml"):
                    if Path(top) == root.given / "resources":
                        root.record_paths.append(path)
                    else:
                        self.add((path, root, None), (), "a verification record lives in the "
                                                         "root's own resources/ directory: move "
                                                         "it there")
                elif lower.endswith(".spec.md"):
                    self.add((path, root, None), (), "a format 1 spec in a format 2 root: "
                                                     "convert it to <name>.spec.yaml")
                elif ".spec." in lower or ".facts." in lower:
                    # .spec.yml, a case variant, a backup (.bak, ~, .orig) or a facts file: a
                    # file discovery passes over could hide a candidate, so it is an error
                    want = ("a facts file does not belong in a spec root"
                            if ".facts." in lower else "name it *.spec.yaml (lowercase, .yaml), "
                            "or move it out of the root")
                    self.add((path, root, None), (), f"not read as a spec: {want}")
                elif ".verify." in lower or (Path(top) == root.given / "resources"
                                             and "verify" in lower):
                    # .verify.yml, a case variant, a backup, a format 1 .verify.md, and in
                    # resources/ any name with "verify" in it (w.verify, wverify.yaml): a record
                    # discovery passes over would leave its verdicts unread without a word
                    self.add((path, root, None), (), "not read as a verification record: name "
                                                     "it <name>.verify.yaml (lowercase, .yaml) "
                                                     "in resources/, or move it out of the root")
            dirs[:] = [d for d in dirs if not (Path(top) / d).is_symlink()]
        for exc in failures:
            where = Path(getattr(exc, "filename", None) or root.given)
            self.add((where, root, None), (), f"cannot list this directory "
                                              f"({exc.strerror or exc}); the root's specs are "
                                              f"not all known, so the check cannot pass",
                     downgrade=False)
        return found

    def load_spec(self, root: Root, path: Path, schemas):
        raw = []
        ok, _, loaded = self.api.validate_file(path, schemas, root.extension, raw)
        self._schema_findings(raw, root)
        if not ok:
            return  # its schema findings make the root untrusted
        f = SpecFile(path, root, loaded, loaded.data)  # kind facts fails validation by its name
        root.files.append(f)
        self.files.append(f)

    # --- per file ----------------------------------------------------------------------------

    def index_file(self, f: SpecFile):
        """Ids and names declared in one file; a second declaration is a finding."""
        for key in ("facts", "instances", "variants"):
            for i, item in enumerate(f.data.get(key, [])):
                rid = item["id"]
                if rid in f.records:
                    f.duplicated.add(rid)
                    other = f.records[rid]
                    self.add(f, (key, i, "id"), f"fact id {rid!r} is used twice in this file "
                                                f"(first at {_where(other.path)}); ids are the "
                                                f"record's keys")
                    continue
                f.records[rid] = Record(f, (key, i), item)
        for i, item in enumerate(f.data.get("assumptions", [])):
            if item["id"] in f.assumptions:
                f.ambiguous.add(("assumptions", item["id"]))
                self.add(f, ("assumptions", i, "id"), f"assumption id {item['id']!r} is used "
                                                      f"twice in this file")
            else:
                f.assumptions[item["id"]] = ("assumptions", i)
        resources = f.data.get("resources", {})
        for group, table in (("documents", f.documents), ("repos", f.repos)):
            for i, entry in enumerate(resources.get(group, [])):
                if entry["name"] in table:
                    f.ambiguous.add((group, entry["name"]))
                    self.add(f, ("resources", group, i, "name"),
                             f"{group} entry {entry['name']!r} is listed twice in this file")
                else:
                    table[entry["name"]] = (entry, ("resources", group, i))
        for name, (entry, path) in f.repos.items():
            seen = set()
            for i, item in enumerate(entry.get("files", [])):
                if item["path"] in seen:
                    f.ambiguous.add(("files", name, item["path"]))
                    self.add(f, path + ("files", i, "path"),
                             f"repos entry {name!r} lists {item['path']!r} twice in files")
                seen.add(item["path"])

    def check_file(self, f: SpecFile):
        import textcheck

        textcheck.check_file(self, f)
        cited = set()  # repos names an anchor or a notice of this file names
        for rec in f.records.values():
            self.check_record(f, rec, cited)
        for i, notice in enumerate(f.data.get("notices", [])):
            cited.add(notice["repo"])
            self.gate_name(f, ("notices", i, "repo"), notice["repo"], "a notice")
        for i, series in enumerate(f.data.get("resources", {}).get("series", [])):
            if "target" in series and series["target"] not in f.repos:
                self.add(f, ("resources", "series", i, "target"),
                         f"series target {series['target']!r} names no repos entry of this file")
        for name, (entry, path) in f.repos.items():
            try:
                self.spdx.parse(entry["license"])
            except self.spdx.SpdxError as exc:
                self.add(f, path + ("license",), f"repos entry {name!r}: license: {exc}")
                continue
            if self.require_license and name not in cited:
                reason = self.gate(f.root, entry["license"])
                if reason:
                    self.add(f, path + ("license",),
                             f"repos entry {name!r}: {reason} (--require-license gates every "
                             f"repos entry, cited or not)")
        if f.root.layer == "public":
            self.check_public(f)
        self.check_placeholders(f)

    def check_record(self, f: SpecFile, rec: Record, cited: set):
        what = f"{_label(rec)} {rec.id!r}"
        for entry, path in supports(rec.data, rec.path):
            if "doc" in entry:
                self.check_citation(f, what, entry, path)
        for anchor, path in anchors(rec.data, rec.path):
            name = anchor["repo"]
            cited.add(name)
            if "lines" in anchor and anchor["lines"][0] > anchor["lines"][1]:
                self.reject(f, path + ("lines",), f"{what}: lines [{anchor['lines'][0]}, "
                                               f"{anchor['lines'][1]}] run backwards; write "
                                               f"[first, last]", citation=True)
            if not self.gate_name(f, path + ("repo",), name, f"{what}: an anchor",
                                  citation=True):
                continue
            entry, epath = f.repos[name]
            if "commit" not in entry:
                self.reject(f, path + ("repo",), f"{what}: anchor names repos entry {name!r}, "
                                                 f"which pins a ref, not a commit; a cited entry "
                                                 f"carries the full commit", citation=True)
            listed = {item["path"] for item in entry.get("files", [])}
            if anchor["path"] not in listed:
                self.reject(f, path + ("path",), f"{what}: {anchor['path']!r} is not in the "
                                                 f"files of repos entry {name!r} (the closed "
                                                 f"list of cited paths, D12)", citation=True)
        names = [(a, rec.path + ("assumes", i)) for i, a in enumerate(rec.data.get("assumes", []))]
        for i, entry in enumerate(rec.data.get("support", [])):
            for j, premise in enumerate(entry.get("premises", [])):
                if "assumption" in premise:
                    names.append((premise["assumption"],
                                  rec.path + ("support", i, "premises", j, "assumption")))
        for name, path in names:
            if name not in f.assumptions:
                self.reject(f, path, f"{what}: assumption {name!r} is not in this file's "
                                     f"assumptions", citation=True)
        irq = rec.data.get("irq")
        if isinstance(irq, dict) and "intid" in irq and irq["kind"] in IRQ_OFFSET:
            want = irq["number"] + IRQ_OFFSET[irq["kind"]]
            if irq["intid"] != want:
                self.add(f, rec.path + ("irq", "intid"),
                         f"{what}: intid {irq['intid']} does not agree with {irq['kind']} "
                         f"{irq['number']} (INTID {want})")

    def check_citation(self, f: SpecFile, what: str, entry: dict, path: tuple):
        """A document citation's checks; every error here is a rejected citation."""
        name, cls = entry["doc"], entry["class"]

        def add(where, message):
            self.reject(f, where, message, citation=True)

        if name not in f.documents:
            add(path + ("doc",), f"{what}: document {name!r} is not in this file's "
                                 f"resources.documents")
            return
        doc, _ = f.documents[name]
        if doc.get("cite") is False:
            add(path + ("doc",), f"{what}: document {name!r} is marked cite: false "
                                 f"(a map only); it cannot be cited")
        if cls in DOC_CLASS and doc["class"] != DOC_CLASS[cls]:
            add(path + ("doc",), f"{what}: a {cls} citation names document {name!r} "
                                 f"of class {doc['class']}")
        count = doc.get("pages")
        for i, loc in enumerate(entry.get("at", [])):
            lpath = path + ("at", i)
            if cls == "standard" and count is not None and not any(k in loc for k in PRECISE):
                add(lpath, f"{what}: document {name!r} is paged, so a standard "
                           f"locator needs a section, page, pages, table, figure or "
                           f"clause, not a heading alone")
            numbers = []
            if "page" in loc:
                numbers.append((loc["page"], lpath + ("page",)))
            if "pages" in loc:
                numbers += [(p, lpath + ("pages", k)) for k, p in enumerate(loc["pages"])]
            for value, vpath in numbers:
                if not DIGITS.fullmatch(value):
                    continue
                if len(value) > 1 and value[0] == "0":
                    add(vpath, f"{what}: page {_short(value)}: write "
                               f"{_short(value.lstrip('0') or '0')} (no leading zeros)")
                if count is not None and not (_number(value) >= _number("1")
                                              and _number(value) <= _number(str(count))):
                    add(vpath, f"{what}: page {_short(value)} is outside the {count} "
                               f"pages of document {name!r}")
            if "pages" in loc and all(DIGITS.fullmatch(p) for p in loc["pages"]):
                first, last = (_number(p) for p in loc["pages"])
                if first > last:
                    add(lpath + ("pages",), f"{what}: pages [{_short(loc['pages'][0])}, "
                                            f"{_short(loc['pages'][1])}] run backwards; "
                                            f"write [first, last]")

    def check_public(self, f: SpecFile):
        for group, entries in f.data.get("resources", {}).items():
            for i, entry in enumerate(entries):
                label = entry.get("name") or entry.get("title")
                if entry.get("access") == "internal":
                    self.add(f, ("resources", group, i, "access"),
                             f"{group} entry {label!r}: access: internal under a public root")
                via = entry.get("via") if group == "tools" else None
                if via is not None and via[len("skill:"):] not in self.public_skills:
                    self.add(f, ("resources", group, i, "via"),
                             f"{group} entry {label!r}: via {via!r} is not a public skill "
                             f"(pass --public-skill NAME if it is)")

    def check_placeholders(self, f: SpecFile):
        import specmd
        import textcheck

        author_paths = {path for path, _, _ in textcheck.fields(f.data)}

        def walk(node, path):
            if isinstance(node, dict):
                for k, v in node.items():
                    if k == "symbol" or (path[:1] == ("notices",) and k == "text"):
                        continue  # a symbol is spelled as the source spells it; a notice is verbatim
                    walk(v, path + (k,))
            elif isinstance(node, list):
                for i, v in enumerate(node):
                    walk(v, path + (i,))
            elif isinstance(node, str) and "<" in node:
                found = specmd.placeholders(node, skip_html=path in author_paths)
                if found:
                    self.add(f, path, f"{_where(path)}: unsubstituted template placeholder "
                                      f"{found[0][2]!r}")

        walk(f.data, ())

    # --- the license gate --------------------------------------------------------------------

    def gate(self, root: Root, expression: str) -> str | None:
        """None when root accepts the expression; otherwise why not. The one gate rule."""
        try:
            tree = self.spdx.parse(expression)
        except self.spdx.SpdxError as exc:
            return f"its license {expression!r} is not an SPDX expression ({exc})"
        accepts = root.accepts or frozenset()
        if self.spdx.accepted(tree, accepts):
            return None
        shown = ", ".join(sorted(accepts)) or "none: documents only"
        return f"{tree} is not accepted by root {root.label} (accepts: {shown})"

    def gate_name(self, f: SpecFile, path: tuple, name: str, what: str, *,
                  citation=False) -> bool:
        """Direct gate for one anchor or notice: the repos entry it names, in its own file,
        against its file's root. False when the name resolves to nothing. An anchor's
        failure is a rejected citation (citation=True)."""
        if name not in f.repos:
            self.reject(f, path, f"{what} names repos entry {name!r}, which is not in this "
                                 f"file's resources.repos", citation=citation)
            return False
        reason = self.gate(f.root, f.repos[name][0]["license"])
        if reason:
            self.reject(f, path, f"{what} names repos entry {name!r}: {reason}",
                        citation=citation)
        return True

    def reach(self, rec: Record):
        """What a record's citations reach, its own and those of every fact it references,
        transitively: ({(file, repos name): the record that cites it}, [unestablished hops]).
        An unestablished hop is (record, reference, why) for a reference that resolves to
        nothing, to more than one fact, or into what could not be read: the gate fails closed
        on it, since what lies beyond it is unknown."""
        if rec in self._reach:
            return self._reach[rec]
        out, problems, seen, queue = {}, [], {rec}, deque([rec])
        while queue:
            cur = queue.popleft()
            for anchor, _ in anchors(cur.data, cur.path):
                out.setdefault((cur.file, anchor["repo"]), cur)
            for _, ref, _ in references(cur.data, cur.path):
                target, why = self.resolve(cur.file, ref)
                if target is None:
                    problems.append((cur, ref, why))
                elif target not in seen:
                    seen.add(target)
                    queue.append(target)
        self._reach[rec] = (out, problems)
        return self._reach[rec]

    # --- references --------------------------------------------------------------------------

    def resolve(self, f: SpecFile, ref: str):
        """(Record, None), or (None, why not) when the reference resolves to nothing, to more
        than one record, or into a root or file that could not be read in full."""
        key = (f, ref)
        if key not in self._resolved:
            self._resolved[key] = self._resolve(f, ref)
        return self._resolved[key]

    def _resolve(self, f: SpecFile, ref: str):
        m = REF.fullmatch(ref)
        spec_id, root_name, fact_id = m.group(1), m.group(2), m.group(3)
        if spec_id is None:
            if fact_id in f.duplicated:
                return None, f"is ambiguous: this file declares fact {fact_id!r} twice"
            rec = f.records.get(fact_id)
            return (rec, None) if rec else (None, f"resolves to nothing: no fact {fact_id!r} "
                                                  f"in this file")
        if root_name is not None and self.unreadable_markers:
            return None, (f"cannot be resolved: the marker {self.unreadable_markers[0]} could "
                          f"not be read, so that root's name is unknown and could be "
                          f"{root_name!r}; every root-qualified reference fails closed")
        roots = [f.root] if root_name is None else [r for r in self.roots if r.name == root_name]
        if not roots:
            return None, (f"resolves to nothing: no root named {root_name!r} among the roots "
                          f"read (a renamed root leaves every reference to it dangling)")
        if len(roots) > 1:
            return None, (f"is ambiguous: {len(roots)} roots read are named {root_name!r} "
                          f"({', '.join(str(r.given) for r in roots)})")
        root = roots[0]
        if root is not f.root and root.untrusted:
            return None, f"cannot be resolved: {_untrusted(root)}"
        owners = [g for g in root.files if g.spec_id == spec_id]
        found = [g.records[fact_id] for g in owners if fact_id in g.records]
        if len(found) > 1 or any(fact_id in g.duplicated for g in owners):
            places = ", ".join(_rel(r.file) for r in found)
            return None, (f"is ambiguous: spec {spec_id!r} declares fact {fact_id!r} more "
                          f"than once in root {root.label} ({places})")
        if found:
            return found[0], None
        where = (f"resolves to nothing: spec {spec_id!r} has no fact {fact_id!r} in root "
                 f"{root.label}" if owners else
                 f"resolves to nothing: root {root.label} holds no spec {spec_id!r}")
        elsewhere = [g for g in self.files if g.root is not root
                     and g.spec_id == spec_id and fact_id in g.records]
        if elsewhere and root_name is None:
            other = elsewhere[0].root.label
            where += (f"; it is in root {other}, and a reference into another root names "
                      f"it: {spec_id}@{other}#{fact_id}")
        return None, where

    def check_references(self):
        premise_edges: dict = {}
        for f in self.files:
            for rec in f.records.values():
                what = f"{_label(rec)} {rec.id!r}"
                seen: dict = {}
                edges = premise_edges.setdefault(rec, [])
                for kind, ref, path in references(rec.data, rec.path):
                    target, why = self.resolve(f, ref)
                    if target is None:
                        self.reject(f, path, f"{what}: reference {ref!r} {why}")
                        continue
                    if kind != "observation":
                        relation = None
                        if kind == "relates":
                            relation = rec.data["relates"][path[-2]]["relation"]
                        dup = (kind, target, relation)
                        if dup in seen:
                            self.reject(f, path, f"{what}: {ref!r} names {target.full}, as "
                                                 f"{seen[dup]!r} already does in this {kind} list")
                        seen.setdefault(dup, ref)
                    if target is rec and kind != "premise":
                        self.reject(f, path, f"{what}: {ref!r} names the fact itself")
                    if kind == "premise":
                        edges.append((target, path))
                    if target.file.root.rank > f.root.rank:
                        self.reject(f, path, f"{what}: {ref!r} names a fact in layer "
                                             f"{target.file.root.layer}, which merges after this "
                                             f"file's layer {f.root.layer}")
                    self.gate_reference(f, what, ref, path, target)
        self.check_cycles(premise_edges)

    def gate_reference(self, f: SpecFile, what: str, ref: str, path: tuple, target: Record):
        """The transitive gate for one reference: everything its target reaches must be
        accepted by the citing file's root, and every hop on the way must be established."""
        reached, unknown = self.reach(target)
        problems = []
        for (g, name), via in sorted(reached.items(),
                                     key=lambda item: (str(item[0][0].path), item[0][1])):
            through = "" if via is target else f" through {via.full}"
            if name not in g.repos:
                problems.append(f"an anchor of {via.full} naming repos entry {name!r}, which "
                                f"its file does not list (its license is unknown)")
                continue
            reason = self.gate(f.root, g.repos[name][0]["license"])
            if reason:
                problems.append(f"repos entry {name!r} of {_rel(g)}{through}: {reason}")
        for problem in problems:
            self.reject(f, path, f"{what}: reference {ref!r} reaches {problem} (license gate, "
                                 f"D13)")
        for via, hop, why in unknown:
            self.reject(f, path, f"{what}: reference {ref!r} reaches {via.full}, whose reference "
                                 f"{hop!r} {why}; what lies beyond is unknown, so the license gate "
                                 f"fails closed")

    def reach_roots(self, rec: Record) -> dict:
        """Every root a record rests on: its own and those of every fact it references,
        transitively: {root: the first record reached there}."""
        out, seen, queue = {}, {rec}, deque([rec])
        while queue:
            cur = queue.popleft()
            out.setdefault(cur.file.root, cur)
            for _, ref, _ in references(cur.data, cur.path):
                target, _ = self.resolve(cur.file, ref)
                if target is not None and target not in seen:
                    seen.add(target)
                    queue.append(target)
        return out

    def check_trust(self):
        """A reference may only rest on a root that checks clean. Run after every other check,
        and repeated until nothing changes: a finding here is an error that makes the citing
        file's own root untrusted in turn."""
        emitted = set()
        while True:
            changed = False
            for f in self.files:
                for rec in f.records.values():
                    what = f"{_label(rec)} {rec.id!r}"
                    for _, ref, path in references(rec.data, rec.path):
                        target, _ = self.resolve(f, ref)
                        if target is None or (f, path) in self._failed_refs:
                            continue  # already an error at this reference
                        for root, via in self.reach_roots(target).items():
                            if root is f.root or not root.untrusted:
                                continue
                            if (f, path, root) in emitted:
                                continue
                            emitted.add((f, path, root))
                            through = "" if via is target else f" through {via.full}"
                            trusted = not f.root.untrusted
                            self.reject(f, path, f"{what}: reference {ref!r} rests on "
                                                 f"{_untrusted(root)}{through}")
                            changed = changed or trusted
            if not changed:
                return

    def check_cycles(self, edges: dict):
        """Inference premises form a directed acyclic graph: report every fact on a cycle."""
        index, low, stack, on_stack, counter = {}, {}, [], set(), [0]
        sccs = []

        def strong(v):
            work = [(v, iter(edges.get(v, [])))]
            index[v] = low[v] = counter[0]
            counter[0] += 1
            stack.append(v)
            on_stack.add(v)
            while work:
                node, it = work[-1]
                advanced = False
                for w, _ in it:
                    if w not in index:
                        index[w] = low[w] = counter[0]
                        counter[0] += 1
                        stack.append(w)
                        on_stack.add(w)
                        work.append((w, iter(edges.get(w, []))))
                        advanced = True
                        break
                    if w in on_stack:
                        low[node] = min(low[node], index[w])
                if advanced:
                    continue
                work.pop()
                if work:
                    low[work[-1][0]] = min(low[work[-1][0]], low[node])
                if low[node] == index[node]:
                    scc = []
                    while True:
                        w = stack.pop()
                        on_stack.discard(w)
                        scc.append(w)
                        if w is node:
                            break
                    sccs.append(scc)

        for v in list(edges):
            if v not in index:
                strong(v)
        for scc in sccs:
            members = set(scc)
            if len(scc) == 1 and not any(t is scc[0] for t, _ in edges.get(scc[0], [])):
                continue
            names = ", ".join(sorted(r.full for r in scc))
            for rec in scc:
                for target, path in edges.get(rec, []):
                    if target in members:
                        self.reject(rec.file, path, f"{_label(rec)} {rec.id!r}: its inference "
                                                    f"premises form a cycle among {names}")

    # --- across files ------------------------------------------------------------------------

    def check_roots(self):
        by_name: dict = {}
        for root in self.roots:
            if root.name is not None:
                by_name.setdefault(root.name, []).append(root)
        for name, owners in by_name.items():
            if len(owners) > 1:
                for root in owners:
                    others = ", ".join(str(r.given) for r in owners if r is not root)
                    self.add((root.given / MARKER, root, root.marker), ("name",),
                             f"root name {name!r} is also the name of {others}; roots read "
                             f"together have distinct names (references name them)",
                             downgrade=False)

    def check_composition(self):
        base: dict = {}
        for f in self.files:
            if not f.is_overlay:
                base.setdefault(f.spec_id, []).append(f)
        for sid, owners in base.items():
            if len(owners) > 1:
                for f in owners:
                    others = ", ".join(_rel(g) for g in owners if g is not f)
                    self.add(f, ("id",), f"spec id {sid!r} is also declared by {others}; ids "
                                         f"are unique across every root read together")
        names: dict = {}
        for f in self.files:
            for i, alias in enumerate(f.data.get("aliases", [])):
                names.setdefault(alias, []).append((f, ("aliases", i)))
        for alias, uses in names.items():
            if alias in base:
                for f, path in uses:
                    self.add(f, path, f"alias {alias!r} is the id of another spec")
                for g in base[alias]:  # the declaration is in conflict too, wherever it sits
                    others = ", ".join(_rel(f) for f, _ in uses)
                    self.add(g, ("id",), f"spec id {alias!r} is also an alias in {others}")
            elif len(uses) > 1:
                for f, path in uses:
                    self.add(f, path, f"alias {alias!r} is also an alias of another spec")
        parts_graph: dict = {}
        for f in self.files:
            if f.is_overlay:
                self.check_overlay(f, base)
                continue
            for i, part in enumerate(f.data.get("parts", [])):
                parts_graph.setdefault(f.spec_id, []).append(part)
                if part not in base:
                    self.add(f, ("parts", i), f"parts entry {part!r} resolves to no spec")
                    continue
                other = base[part][0].data.get("cache")
                if other and f.data.get("cache") and other != f.data["cache"]:
                    self.add(f, ("parts", i), f"part {part!r} names cache {other!r}, this spec "
                                              f"{f.data['cache']!r}", level="warning")
            if "variant_of" in f.data:
                target = f.data["variant_of"]
                if target == f.spec_id:
                    self.add(f, ("variant_of",), "variant_of names the spec itself")
                elif target not in base:
                    self.add(f, ("variant_of",), f"variant_of {target!r} resolves to no spec")
                elif base[target][0].kind != "board":
                    self.add(f, ("variant_of",), f"variant_of {target!r} is not a board spec "
                                                 f"(kind {base[target][0].kind})")
            self.check_instances(f, base)
        self.check_parts_cycles(parts_graph, base)
        overlays: dict = {}
        for f in self.files:
            if f.is_overlay:
                overlays.setdefault((f.spec_id, f.root), []).append(f)
        for (target, root), owners in overlays.items():
            if len(owners) > 1:
                for f in owners:
                    self.add(f, ("overlays",), f"{len(owners)} overlays of {target!r} in root "
                                               f"{root.label}; their merge order is undefined",
                             level="warning")
        records: dict = {}
        for f in self.files:
            for rid, rec in f.records.items():
                key = (f.spec_id, f.root, rid)
                if key in records:
                    first = records[key]
                    self.add(f, rec.path + ("id",), f"fact id {rid!r} is also used by "
                                                    f"{_rel(first.file)} (spec {f.spec_id!r}, "
                                                    f"root {f.root.label}); ids are unique per "
                                                    f"spec id per root")
                else:
                    records[key] = rec

    def check_instances(self, f: SpecFile, base: dict):
        for i, row in enumerate(f.data.get("instances", [])):
            ip = row["ip"]
            if ip not in base:
                self.add(f, ("instances", i, "ip"), f"instance {row['name']!r}: ip {ip!r} "
                                                    f"resolves to no spec")
            elif base[ip][0].kind != "ip":
                self.add(f, ("instances", i, "ip"), f"instance {row['name']!r}: {ip!r} is not "
                                                    f"an ip spec (kind {base[ip][0].kind})")

    def check_overlay(self, f: SpecFile, base: dict):
        target = f.spec_id
        if target not in base:
            self.add(f, ("overlays",), f"overlays {target!r} resolves to no spec")
            return
        tf = base[target][0]
        if tf.root.rank > f.root.rank:
            self.add(f, ("overlays",), f"overlays {target!r}, which is in layer "
                                       f"{tf.root.layer}, after this root's layer "
                                       f"{f.root.layer}; an overlay merges after its target")
        allowed = SECTIONS.get(tf.kind, ())
        for i, fact in enumerate(f.data.get("facts", [])):
            if fact["section"] not in allowed:
                self.add(f, ("facts", i, "section"), f"section {fact['section']!r} is not a "
                                                     f"section of the target, kind {tf.kind} "
                                                     f"({', '.join(allowed)})")
        if "instances" in f.data and tf.kind not in ("soc", "chip"):
            self.add(f, ("instances",), f"instances: the target {target!r} is of kind "
                                        f"{tf.kind}, which has no instances")
        self.check_instances(f, base)

    def check_parts_cycles(self, graph: dict, base: dict):
        """parts compose specs into a tree: report every parts entry on a cycle."""
        color, cycles = {}, []
        for start in sorted(graph):
            if color.get(start):
                continue
            color[start], path, stack = 1, [start], [iter(graph[start])]
            while stack:
                nxt = next(stack[-1], None)
                if nxt is None:
                    stack.pop()
                    color[path.pop()] = 2
                elif color.get(nxt) == 1:
                    cycles.append(path[path.index(nxt):])
                elif not color.get(nxt) and nxt in graph:
                    color[nxt] = 1
                    path.append(nxt)
                    stack.append(iter(graph[nxt]))
        for cycle in cycles:
            shown = " -> ".join(cycle + [cycle[0]])
            for k, node in enumerate(cycle):
                nxt = cycle[(k + 1) % len(cycle)]
                for g in base.get(node, []):
                    parts = g.data.get("parts", [])
                    if nxt in parts:
                        self.add(g, ("parts", parts.index(nxt)), f"parts form a cycle: {shown}")

    # --- stubs -------------------------------------------------------------------------------

    def check_stubs(self, stubs: list[Path], stubs_from: list[Path]):
        import specmd

        for d in stubs_from:
            if not d.is_dir():
                raise PreconditionError(f"--stubs-from {d}: not a directory")
            for path in sorted(d.glob("*/SKILL.md")):
                m = FRONTMATTER.match(path.read_text(encoding="utf-8"))
                if m and "stub over" in m.group(1):
                    stubs.append(path)
        ids = {f.spec_id for f in self.files if not f.is_overlay}
        self.stubs = len(stubs)
        for path in stubs:
            if not path.is_file():
                self.findings.append(Finding(str(path), 1, 1, "stub file not found"))
                continue
            text = path.read_text(encoding="utf-8")

            def at(index: int, message: str):
                line = text.count("\n", 0, index) + 1
                column = index - (text.rfind("\n", 0, index) + 1) + 1
                self.findings.append(Finding(str(path), line, column, message))

            for line, column, found in specmd.placeholders(text)[:1]:
                self.findings.append(Finding(str(path), line, column, f"unsubstituted template "
                                                                      f"placeholder {found!r}"))
            names = list(STUB.finditer(text))
            if not names:
                at(0, "stub names no `spec: <id>`")
            for m in names:
                if m.group(1) not in ids:
                    at(m.start(), f"stub spec id {m.group(1)!r} resolves to no spec")

    # --- driver ------------------------------------------------------------------------------

    def run(self):
        import records

        self.check_roots()
        for f in self.files:
            self.index_file(f)
        for f in self.files:
            self.check_file(f)
        records.check_structure(self, self.schemas)
        self.check_composition()
        self.check_references()
        records.first_pass(self)  # current FAILs: defects of a root's data, before trust
        self.check_trust()
        records.second_pass(self, self.require_verified)


def _untrusted(root: Root) -> str:
    first = root.untrusted[0]
    if len(first) > 200:
        first = first[:197] + "..."
    return (f"root {root.label}, which is untrusted: its own check found "
            f"{len(root.untrusted)} error(s) (first: {first}); a reference may only rest on a "
            f"root that checks clean")


def _number(digits: str) -> tuple:
    """A decimal string as an orderable key, without int(): Python refuses to convert a very
    long one, and a page number is only ever compared."""
    digits = digits.lstrip("0") or "0"
    return (len(digits), digits)


def _short(value: str) -> str:
    return repr(value) if len(value) <= 24 else repr(value[:12] + "..." + value[-6:])


def _label(rec: Record) -> str:
    return {"facts": "fact", "instances": "instance", "variants": "variant"}[rec.path[0]]


def _where(path: tuple) -> str:
    out = ""
    for p in path:
        out += f"[{p}]" if isinstance(p, int) else (f".{p}" if out else str(p))
    return out or "(top)"


def _rel(f: SpecFile) -> str:
    try:
        return f"{f.root.label}:{f.path.relative_to(f.root.given)}"
    except ValueError:
        return str(f.path)


def check(api, schemas, roots, *, context_roots=(), require_license=False, public_skills=(),
          stubs=(), stubs_from=(), require_verified=None):
    """Run the checker; returns the Checker (its roots, files, findings and status)."""
    spdx = load_spdx()
    checker = Checker(api, spdx, require_license=require_license, public_skills=public_skills,
                      require_verified=require_verified)
    checker.load_roots(list(roots), list(context_roots), schemas)
    checker.run()
    checker.check_stubs(list(stubs), list(stubs_from))
    return checker
