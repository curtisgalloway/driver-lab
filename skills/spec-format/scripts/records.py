# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Verification records and per-fact freshness (design: Verification records; SF2-3).

A record, `<root>/resources/<name>.verify.yaml`, belongs to the spec file `<name>.spec.yaml`
of the same root and holds one verdict per fact, keyed by the bare fact id. Each verdict stores
the fact's **basis hash** when it was reached (D2):

    basis(fact) = sha256( "fact-v1\\n"
                          + canonical(fact without `section`)
                          + "\\n" + canonical(the resource entries the fact cites, all but
                                              bookkeeping fields)
                          + "\\n" + canonical(the assumptions it names)
                          + "\\n" + sorted "<full reference> <basis(ref)>" lines, one per fact
                                    it references )

*canonical* is JSON with keys sorted by code point, no insignificant white space, UTF-8, every
string and key in NFC; the data holds only strings, integers, booleans, null, lists and mappings
(anything else is a bug, never hashed). The resource part is `{"documents": {name: entry},
"repos": {name: entry}}` and the assumption part `{id: entry}`: each cited entry whole, minus the
named bookkeeping fields of its kind (BOOKKEEPING), so a field not named there, a future one
included, counts. A repos entry's `files` holds only the entries of the paths the fact cites,
by path, each minus its own bookkeeping. A fact references facts through inference premises,
`relates` and an emulated entry's `observation`.

References form a graph that `relates` can make cyclic (`same-as` both ways). A fact on a cycle
(a strongly connected component of more than one fact, or one naming itself) cannot take its
neighbors' bases first, so the component is hashed as one: its digest is

    sha256("fact-v1-cycle\\n" + sorted "<full reference> sha256(local part)" lines of its members
           + "\\n" + sorted "<full reference> <basis>" lines of the facts outside it they reference)

and a member's line for another member carries that digest in place of a basis. Outside cycles
this is exactly the formula above; on one, any change to any member stales every member.

A basis that cannot be established (a reference or citation the check rejected, a cited name the
file does not list or lists twice, a cited repos entry pinned by `ref` rather than `commit`, a
fact resting on such a fact) is **unknown**: never current.

Freshness of a verdict: **current** (its basis equals the fact's), **stale**, **upstream-stale**
(stale only because facts in other roots changed, reached through references that stay in the
fact's own root until they cross: the verdict's `upstream` map records those facts' bases when
it was reached, recomputing the basis with them gives back the verdict's, and nothing those
facts rest on lies in the fact's own root), **unverified** (no verdict) or **unknown**.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata

CANONICAL = "fact-v1"
# The only fields a basis leaves out of a cited entry, per kind: a closed list, each named in the
# design. Every other field, one the schema adds later included, is hashed (review round 2, the
# user's decision of 2026-10-08: "hash all but bookkeeping").
BOOKKEEPING = {
    "documents": frozenset({"verified", "fetch", "note"}),
    "repos": frozenset({"verified", "fetch", "fetch_via", "note"}),
    "files": frozenset({"note"}),  # a repos entry's `files` item
    "assumptions": frozenset({"todo"}),
}
SUMMARY = {"pass": "PASS", "fail": "FAIL", "unverifiable": "UNVERIFIABLE", "gap": "GAP",
           "adjudicate": "ADJUDICATE"}
STATUSES = ("current", "stale", "upstream-stale", "unverified", "unknown")
RECORD_SUFFIX = ".verify.yaml"
SPEC_SUFFIX = ".spec.yaml"


# --- canonical form and hashes ---------------------------------------------------------------

def _plain(value):
    """The value with every string and key in NFC; refuses any type the format does not hold."""
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, list):
        return [_plain(v) for v in value]
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if not isinstance(k, str):
                raise TypeError(f"canonical form: a mapping key {k!r} is not a string")
            nk = unicodedata.normalize("NFC", k)
            if nk in out:
                raise TypeError(f"canonical form: keys {k!r} collide in NFC")
            out[nk] = _plain(v)
        return out
    raise TypeError(f"canonical form: {type(value).__name__} is not part of the format")


def canonical(value) -> str:
    """The `fact-v1` canonical JSON text of value."""
    return json.dumps(_plain(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _entry(kind: str, entry: dict) -> dict:
    """A cited entry as its basis reads it: every field but the bookkeeping of its kind."""
    return {k: v for k, v in entry.items() if k not in BOOKKEEPING[kind]}


def local_part(rec):
    """(text, None) for the part of a record's basis its own file decides: the record without
    `section`, the resource entries it cites and the assumptions it names, each without its
    bookkeeping fields; or (None, why) when a cited name is not in its file or is listed twice,
    or a cited repos entry pins a ref, so the part cannot be established."""
    import speccheck
    import peripheral

    f = rec.file
    data = peripheral.basis_data(rec)
    fact = {k: v for k, v in data.items() if k != "section"}
    documents, repos, paths = {}, {}, {}
    for entry, _ in speccheck.supports(data, ()):
        if "doc" in entry:
            name = entry["doc"]
            if ("documents", name) in f.ambiguous:
                return None, f"{rec.full}: document {name!r} is listed twice in its file"
            if name not in f.documents:
                return None, f"{rec.full}: document {name!r} is not in its file's resources"
            doc = f.documents[name][0]
            documents[name] = _entry("documents", doc)
        if entry.get("class") in speccheck.ANCHORED:
            for anchor in entry.get("anchors", []):
                name = anchor["repo"]
                if ("repos", name) in f.ambiguous:
                    return None, f"{rec.full}: repos entry {name!r} is listed twice in its file"
                if name not in f.repos:
                    return None, f"{rec.full}: repos entry {name!r} is not in its file's resources"
                paths.setdefault(name, set()).add(anchor["path"])
    for name, cited in paths.items():
        entry = f.repos[name][0]
        if "commit" not in entry:
            return None, (f"{rec.full}: repos entry {name!r} pins a ref, not a commit, so what "
                          f"the fact cites through it is not fixed")
        listed = {item["path"]: item for item in entry.get("files", [])}
        missing = sorted(cited - set(listed))
        if missing:
            return None, (f"{rec.full}: {missing[0]!r} is not in the files of repos entry "
                          f"{name!r}, so its license entry is unknown")
        twice = sorted(p for p in cited if ("files", name, p) in f.ambiguous)
        if twice:
            return None, (f"{rec.full}: repos entry {name!r} lists {twice[0]!r} twice in "
                          f"files, so its license entry is ambiguous")
        entry = _entry("repos", entry)
        entry["files"] = [_entry("files", listed[p]) for p in sorted(cited)]
        repos[name] = entry
    names = list(data.get("assumes", []))
    for entry, _ in speccheck.supports(data, ()):
        names += [p["assumption"] for p in entry.get("premises", []) if "assumption" in p]
    assumptions = {}
    for name in names:
        if ("assumptions", name) in f.ambiguous:
            return None, f"{rec.full}: assumption {name!r} is declared twice in its file"
        if name not in f.assumptions:
            return None, f"{rec.full}: assumption {name!r} is not in its file's assumptions"
        assumptions[name] = _entry("assumptions", f.data["assumptions"][f.assumptions[name][1]])
    return (canonical(fact) + "\n" + canonical({"documents": documents, "repos": repos}) + "\n"
            + canonical(assumptions)), None


def compute(starts, edges, local, fixed, out):
    """Fill out[record] = (basis, None) or (None, why) for every record reachable from starts.

    edges(record) lists (reference, target or None, why) for each reference; local(record) is
    local_part; fixed maps records to a given basis (leaves, never entered). Records already in
    out are reused. Strongly connected components are found with Tarjan's algorithm, which
    finishes a component only after every component it reaches, so a fact's references are
    always hashed before the fact."""
    index, low, stack, on_stack, counter = {}, {}, [], set(), [0]
    cache: dict = {}

    def succ(v):
        if v not in cache:
            cache[v] = edges(v)
        return [t for _, t, _ in cache[v] if t is not None and t not in fixed and t not in out]

    def value(t):
        return fixed[t] if t in fixed else out[t][0]

    def why_of(t):
        return None if t in fixed else out[t][1]

    def finish(scc):
        members = set(scc)
        cyclic = len(scc) > 1 or any(t is scc[0] for _, t, _ in cache[scc[0]])
        parts, problem, external = {}, None, set()
        for m in scc:
            text, why = local(m)
            if text is None:
                problem = problem or why
            parts[m] = text
            for ref, t, why in cache[m]:
                if t is None:
                    problem = problem or f"{m.full}: reference {ref!r} {why}"
                elif t not in members:
                    if value(t) is None:
                        problem = problem or why_of(t)
                    else:
                        external.add(f"{t.full} {value(t)}")
        if problem:
            for m in scc:
                out[m] = (None, problem)
            return
        digest = None
        if cyclic:
            digest = sha256("fact-v1-cycle\n"
                            + "\n".join(sorted(f"{m.full} {sha256(parts[m])}" for m in scc))
                            + "\n" + "\n".join(sorted(external)))
        for m in scc:
            lines = {f"{t.full} {digest if t in members else value(t)}" for _, t, _ in cache[m]}
            out[m] = (sha256(f"{CANONICAL}\n{parts[m]}\n" + "\n".join(sorted(lines))), None)

    def strong(v):
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on_stack.add(v)
        work = [(v, iter(succ(v)))]
        while work:
            node, it = work[-1]
            advanced = False
            for w in it:
                if w not in index:
                    index[w] = low[w] = counter[0]
                    counter[0] += 1
                    stack.append(w)
                    on_stack.add(w)
                    work.append((w, iter(succ(w))))
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
                finish(scc)

    for s in starts:
        if s not in out and s not in fixed and s not in index:
            strong(s)
    return out


class Freshness:
    """Bases, frontiers and verdict freshness over one checker's resolved references.

    failed: (file, path) of references the check failed; with it, such a reference counts as
    not resolving (its target's basis is not one a verdict may rest on). failed_cites: (file,
    path) of citations the check failed; a record with one under its path is unknown."""

    def __init__(self, checker, failed=None, failed_cites=None):
        import speccheck

        self.checker = checker
        self.failed = failed
        self.cites: dict = {}
        for f, path in failed_cites or ():
            self.cites.setdefault(f, []).append(path)
        self._where = speccheck._where
        self._refs = speccheck.references
        self.bases: dict = {}
        self._edges: dict = {}

    def edges(self, rec):
        if rec not in self._edges:
            import peripheral

            out = []
            for _, ref, path in self._refs(peripheral.basis_data(rec), rec.path):
                target, why = self.checker.resolve(rec.file, ref)
                if target is not None and self.failed is not None and (rec.file, path) in self.failed:
                    target, why = None, "failed the check (see the error at that reference)"
                out.append((ref, target, why))
            self._edges[rec] = out
        return self._edges[rec]

    def local(self, rec):
        """local_part, or unknown when the check rejected one of the record's citations."""
        text, why = local_part(rec)
        if text is None:
            return text, why
        n = len(rec.path)
        import peripheral

        bad = sorted((p for p in self.cites.get(rec.file, ())
                      if p[:n] == rec.path and peripheral.owns_citation(rec, p)), key=repr)
        if bad:
            return None, (f"{rec.full}: the citation at {self._where(bad[0])} failed the check "
                          f"(see the error there)")
        return text, None

    def all(self, records):
        compute(records, self.edges, self.local, {}, self.bases)

    def basis(self, rec):
        if rec not in self.bases:
            compute([rec], self.edges, self.local, {}, self.bases)
        return self.bases[rec]

    def frontier(self, rec) -> dict:
        """The facts in other roots a record reaches through references that stay in its own
        root until they cross: {full reference: record}."""
        seen, queue, out = {rec}, [rec], {}
        while queue:
            cur = queue.pop()
            for _, t, _ in self.edges(cur):
                if t is None:
                    continue
                if t.file.root is not rec.file.root:
                    out[t.full] = t
                elif t not in seen:
                    seen.add(t)
                    queue.append(t)
        return out

    def returns_home(self, rec, frontier) -> bool:
        """Whether anything the frontier facts rest on, transitively, lies in rec's own root.
        Then the recorded upstream bases also fix facts of the fact's own root, so a change
        there could hide behind them: upstream-stale is refused (review round 1)."""
        seen, queue = set(frontier.values()), list(frontier.values())
        while queue:
            cur = queue.pop()
            for _, t, _ in self.edges(cur):
                if t is None or t in seen:
                    continue
                if t.file.root is rec.file.root:
                    return True
                seen.add(t)
                queue.append(t)
        return False

    def upstream_now(self, rec) -> dict | None:
        """{full reference: basis now} over the frontier, or None if one is unknown."""
        out = {}
        for full, t in self.frontier(rec).items():
            b, _ = self.basis(t)
            if b is None:
                return None
            out[full] = b
        return out

    def status(self, rec, verdict):
        """(status, detail) of one record's verdict (None: no verdict)."""
        basis, why = self.basis(rec)
        if basis is None:
            return "unknown", why
        if verdict is None:
            return "unverified", None
        if verdict["basis"] == basis:
            return "current", None
        recorded = verdict.get("upstream")
        frontier = self.frontier(rec)
        if not recorded or set(recorded) != set(frontier):
            return "stale", None
        if self.returns_home(rec, frontier):
            return "stale", None  # the closure beyond the frontier re-enters the own root
        fixed = {t: recorded[full] for full, t in frontier.items()}
        again = compute([rec], self.edges, self.local, fixed, {})
        if again.get(rec, (None,))[0] != verdict["basis"]:
            return "stale", None
        changed = sorted(full for full, t in frontier.items()
                         if self.basis(t)[0] != recorded[full])
        if not changed:
            return "stale", None  # a cycle across roots: the classification fails safe
        return "upstream-stale", changed


# --- records -------------------------------------------------------------------------------

def check_structure(checker, schemas):
    """Load and check every record of every root: its name maps to one spec file, `spec` and
    `spec_file` name it, every key names a fact (instance, variant) of that file, `summary`
    counts the verdicts, a GAP verdict belongs to a gap fact (never an instance or variant row)
    and a gap fact's verdict is GAP, and second readers agree with the verdict they confirm. Valid verdicts are attached to the
    spec file (`f.verdicts`) for freshness."""
    by_path = {f.path: f for f in checker.files}
    for root in checker.roots:
        stems: dict = {}
        for p in root.spec_paths:
            stems.setdefault(p.name[:-len(SPEC_SUFFIX)], []).append(p)
        for stem, paths in stems.items():
            if len(paths) > 1:
                for p in paths:
                    f = by_path.get(p)
                    others = ", ".join(_rel(root, q) for q in paths if q != p)
                    where = f if f is not None else (p, root, None)
                    checker.add(where, (), f"this file and {others} would share the "
                                           f"verification record resources/{stem}{RECORD_SUFFIX}; "
                                           f"give spec files distinct names")
                    if f is not None:
                        f.record_state = "shared"
        for rpath in root.record_paths:
            check_record(checker, schemas, root, rpath, stems, by_path)


def check_record(checker, schemas, root, rpath, stems, by_path):
    import speccheck

    raw = []
    ok, _, loaded = checker.api.validate_file(rpath, schemas, None, raw)
    checker._schema_findings(raw, root)
    stem = rpath.name[:-len(RECORD_SUFFIX)]
    owners = stems.get(stem, [])
    where = (rpath, root, loaded)
    if ok:
        import textcheck

        textcheck.check_data(checker, where, loaded.data)
    if not owners:
        checker.add(where, ("spec_file",) if ok else (),
                    f"no spec file named {stem}{SPEC_SUFFIX} in root {root.label}: a record "
                    f"belongs to the spec file of its name")
        return
    if len(owners) > 1:
        return  # the shared name is an error on each spec file
    f = by_path.get(owners[0])
    if f is None:
        return  # the spec file did not load: its own errors stand, and it has no facts here
    f.record_path = rpath
    if not ok:
        f.record_state = "invalid"
        return
    data = loaded.data
    rel = _rel(root, f.path)
    if data["spec_file"] != rel:
        checker.add(where, ("spec_file",), f"spec_file {data['spec_file']!r}: this record "
                                           f"belongs to {rel!r}, the spec file of its name")
    if data["spec"] != f.spec_id:
        checker.add(where, ("spec",), f"spec {data['spec']!r}: the spec file {rel!r} is "
                                      f"{'an overlay of' if f.is_overlay else 'spec'} "
                                      f"{f.spec_id!r}")
    f.record_state = "ok"
    counts = dict.fromkeys(SUMMARY.values(), 0)
    for key, v in data["verdicts"].items():
        counts[v["verdict"]] += 1
        kpath = ("verdicts", key)
        fid, dot, sub = key.partition(".")
        if fid in f.duplicated:
            checker.add(where, kpath, f"verdict key {key!r}: fact id {fid!r} is declared twice "
                                      f"in {rel}, so the key is ambiguous", key=True)
            continue
        if fid not in f.records:
            checker.add(where, kpath, f"verdict key {key!r} names no fact, instance or variant "
                                      f"of {rel}", key=True)
            continue
        if dot and (key not in f.records or key in f.duplicated):
            checker.add(where, kpath, f"verdict key {key!r}: {fid!r} has no field or step "
                                      f"{sub!r} with its own support (a sub-key names a "
                                      f"register field or sequence step, D16)", key=True)
            continue
        rec = f.records[key]
        if rec.path[0] == "facts":
            gap = not speccheck.has_support(rec.data)
            if gap and v["verdict"] != "GAP":
                checker.add(where, kpath + ("verdict",), f"verdict {v['verdict']} for {fid!r}, "
                                                         f"a gap fact (no support): its verdict "
                                                         f"is GAP")
            elif not gap and v["verdict"] == "GAP":
                checker.add(where, kpath + ("verdict",), f"verdict GAP for {fid!r}, which has "
                                                         f"support: GAP is a gap fact's verdict")
        elif v["verdict"] == "GAP":
            checker.add(where, kpath + ("verdict",), f"verdict GAP for {_what(rec)}: GAP is a gap "
                                                     f"fact's verdict, and an instance or variant "
                                                     f"row is never a gap")
        if v["verdict"] != "ADJUDICATE":
            for i, reader in enumerate(v.get("readers", [])):
                if reader["verdict"] != v["verdict"]:
                    checker.add(where, kpath + ("readers", i, "verdict"),
                                f"verdict key {key!r}: a reader's verdict {reader['verdict']} "
                                f"disagrees with {v['verdict']}; record the disagreement as "
                                f"ADJUDICATE with readings")
        f.verdicts[key] = (v, kpath)
    for name, value in SUMMARY.items():
        if data["summary"][name] != counts[value]:
            checker.add(where, ("summary", name), f"summary {name}: {data['summary'][name]}, but "
                                                  f"{counts[value]} verdict(s) are {value}")
    f.record_loaded = loaded


def _rel(root, path) -> str:
    try:
        return path.relative_to(root.given).as_posix()
    except ValueError:
        return str(path)


def _what(rec) -> str:
    return {"facts": "fact", "instances": "instance", "variants": "variant"}[rec.path[0]] + \
        f" {rec.id!r}"


def first_pass(checker):
    """Before the trust pass: errors that are defects of a root's own data and so make it
    untrusted. A current FAIL verdict (the fact as written was found wrong), and a current
    verdict whose `upstream` map does not match the facts and bases it rests on."""
    fresh = Freshness(checker)
    fresh.all([r for f in checker.files for r in f.records.values()])
    for f in checker.files:
        if f.record_state != "ok":
            continue
        where = (f.record_path, f.root, f.record_loaded)
        for fid, (v, kpath) in f.verdicts.items():
            rec = f.records[fid]
            basis, _ = fresh.basis(rec)
            if basis is None or v["basis"] != basis:
                continue
            if v["verdict"] == "FAIL":
                checker.add(f, rec.path + ("id",),
                            f"{_what(rec)}: its current verdict in {_rel(f.root, f.record_path)} "
                            f"is FAIL (correction: {_cut(v['correction'])})")
            want = fresh.upstream_now(rec) or {}
            have = v.get("upstream", {})
            if have != want:
                shown = ", ".join(f"{k}: {b}" for k, b in sorted(want.items())) or "none"
                checker.add(where, kpath + (("upstream",) if "upstream" in v else ()),
                            f"verdict key {fid!r}: upstream does not match the facts in other "
                            f"roots the fact rests on (now {shown}); a current verdict records "
                            f"their bases so a change upstream reads as upstream-stale",
                            key="upstream" not in v)


def second_pass(checker, mode):
    """After the trust pass: freshness of every verdict in the checked roots, as warnings, or
    as errors under --require-verified (`pr`: all; `main`: all but upstream-stale, D19). A
    reference or citation the check failed counts as not resolving, so a fact resting on it is
    unknown.
    These findings are a policy on the checked root, not a defect that could change what a
    reference resolves to, so they come after the trust pass."""
    fresh = Freshness(checker, failed=set(checker._failed_refs),
                      failed_cites=set(checker._failed_cites))
    fresh.all([r for f in checker.files for r in f.records.values()])
    checker.status = []

    def level(kind):
        if mode is None or (mode == "main" and kind == "upstream-stale"):
            return "warning"
        return "error"

    for f in checker.files:
        rows = []
        record = (_rel(f.root, f.record_path) if f.record_path is not None
                  else f"resources/{f.path.name[:-len(SPEC_SUFFIX)]}{RECORD_SUFFIX}")
        for rec in f.records.values():
            v, _ = f.verdicts.get(rec.id, (None, None))
            status, detail = fresh.status(rec, v)
            basis, _ = fresh.basis(rec)
            critical = rec.data.get("critical") is True
            others = [r for r in (v or {}).get("readers", [])
                      if _who(r["verifier"]) != _who(v["verifier"])]
            own = bool(v and v.get("readers")) and not others
            reader = ("not-needed" if not critical else "present" if others else "missing")
            rows.append({
                "key": rec.id, "ref": rec.full, "kind": _what(rec).split()[0], "status": status,
                "verdict": v["verdict"] if v else None, "carried": bool(v and "carried_from" in v),
                "basis": basis, "recorded": v["basis"] if v else None,
                "upstream": fresh.upstream_now(rec) if basis is not None else None,
                "changed": detail if status == "upstream-stale" else [],
                "reason": detail if status == "unknown" else None,
                "second_reader": reader,
            })
            if f.root.context:
                continue
            what, at = _what(rec), rec.path + ("id",)
            if status == "unknown":
                checker.add(f, at, f"{what}: freshness unknown: {detail}; no verdict can be "
                                   f"current", level=level(status))
            elif status == "unverified":
                why = {"ok": f"no verdict in {record}",
                       "invalid": f"its record {record} does not validate",
                       "shared": "its record name is shared with another spec file"}.get(
                           f.record_state, f"no record at {record}")
                checker.add(f, at, f"{what}: unverified: {why}", level=level(status))
            elif status == "stale":
                old = (f" (its {v['verdict']} was for that version)"
                       if v["verdict"] != "PASS" else "")
                checker.add(f, at, f"{what}: verdict stale: the fact, a resource it cites, an "
                                   f"assumption it names or a fact it rests on changed since the "
                                   f"verdict of {v['date']}{old}", level=level(status))
            elif status == "upstream-stale":
                checker.add(f, at, f"{what}: upstream-stale: {', '.join(detail)} changed since "
                                   f"the verdict of {v['date']}", level=level(status))
            elif v["verdict"] == "ADJUDICATE":
                checker.add(f, at, f"{what}: its verdict is ADJUDICATE, not yet settled",
                            level="warning")
            if status == "current" and reader == "missing":
                same = ("; a reader with the verdict's own verifier is not a second reader"
                        if own else "")
                checker.add(f, at, f"{what}: critical, so its verdict needs a second reader's "
                                   f"verdict in readers (D14){same}", level=level("reader"))
        checker.status.append({"file": f, "record": record if f.record_path else None,
                               "state": f.record_state, "rows": rows})


def _who(verifier: str) -> str:
    """A verifier's name for comparing readers: NFC, white space collapsed, case folded, so a
    respelling of the same verifier never counts as a second reader."""
    return " ".join(unicodedata.normalize("NFC", verifier).split()).casefold()


def _cut(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= 120 else text[:117] + "..."
