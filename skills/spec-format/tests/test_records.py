#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for verification records and per-fact freshness (SF2-3; records.py, `spec.py status`,
`spec.py check --require-verified pr|main`).

Fixtures:
- fixtures/records/verify_root: board-expert's format 1 verify_root cases in format 2 (current,
  stale, current FAIL, stale FAIL, malformed, none), with basis hashes the generator in run
  sf2-3-20261008-01 computed;
- fixtures/worked-example: the design's slices (its record carries zeros for `<64 hex>`).
Everything else is built in temporary roots, one rule each.

Run in the pinned environment:
  .venv-sf2/bin/python -m unittest discover -s skills/spec-format/tests -v
"""

import contextlib
import hashlib
import io
import json
import pathlib
import shutil
import sys
import tempfile
import unicodedata
import unittest

HERE = pathlib.Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "spec.py"
FIX = HERE / "fixtures"
VROOT = FIX / "records" / "verify_root"
WORKED = FIX / "worked-example"
sys.path.insert(0, str(SCRIPT.parent))
import records  # noqa: E402
import spec as spec_cli  # noqa: E402

HDR = "# SPDX-FileCopyrightText: 2026 contributors\n# SPDX-License-Identifier: Apache-2.0\n"
COMMIT = "1a2b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d"
# TRM as its citing fact's basis reads it: every field but the bookkeeping (verified, fetch)
TRM_HASHED = {"name": "trm", "class": "databook", "title": "Widget TRM",
              "url": "https://example.invalid/trm.pdf", "pages": 80}
TRM = ('    - {name: trm, class: databook, title: Widget TRM, url: "https://example.invalid/trm.pdf",'
       ' pages: 80, verified: 2026-10-01, fetch: ok}\n')
LINUX = ("    - name: linux\n      url: https://example.invalid/linux\n"
         f'      commit: "{COMMIT}"\n      license: GPL-2.0-only\n      role: source\n'
         "      files:\n        - {path: drivers/w.c, license_from: spdx-line}\n"
         "        - {path: drivers/x.c, license_from: spdx-line}\n"
         "      verified: 2026-10-01\n      fetch: ok\n")


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = spec_cli.main([str(a) for a in argv])
    return code, out.getvalue(), err.getvalue()


def check(*argv):
    code, out, _ = run("check", "--json", *argv)
    return code, json.loads(out)


def status(*argv):
    code, out, _ = run("status", "--json", *argv)
    return code, json.loads(out)


def errors(result, text=None):
    return [f for f in result["findings"] if f["level"] == "error"
            and (text is None or text in f["message"])]


def warnings(result, text=None):
    return [f for f in result["findings"] if f["level"] == "warning"
            and (text is None or text in f["message"])]


def need(found):
    if not found:
        raise AssertionError("expected a finding, found none")
    return found


def only(found):
    if len(found) != 1:
        raise AssertionError(f"expected one finding, found {len(found)}: {found}")
    return found[0]


def rows(result):
    """{full reference: status row} over every spec of a status result."""
    return {r["ref"]: r for s in result["specs"] for r in s["facts"]}


def marker(name, accepts="[]", lic="CC-BY-4.0", layer="public"):
    return (HDR + f"format: 2\nlayer: {layer}\nname: {name}\nlicense: {lic}\naccepts: {accepts}\n")


def fact(fid, claim=None, extra="", support=None, section="quick-facts"):
    support = support or '    support: [{class: databook, doc: trm, at: [{section: "1"}]}]\n'
    return (f"  - id: {fid}\n    section: {section}\n    title: T {fid}\n"
            f"    claim: {claim or f'C {fid}.'}\n" + support + extra)


def ref_fact(fid, *refs, extra=""):
    """An inference fact whose premises are the given references."""
    return (f"  - id: {fid}\n    section: quick-facts\n    title: T {fid}\n    claim: C {fid}.\n"
            "    support:\n      - class: inference\n        premises:\n"
            + "".join(f'          - fact: "{r}"\n' for r in refs)
            + "        derivation: it follows\n    todo: {check: hardware, text: check it.}\n"
            + extra)


def chip(sid="widgetchip", facts="", repos="", head="", docs=TRM):
    text = (HDR + f"format: 2\nkind: chip\nid: {sid}\nname: Widget\ntriggers: [{sid}]\n" + head
            + "resources:\n  documents:\n" + docs)
    if repos:
        text += "  repos:\n" + repos
    return text + "facts:\n" + (facts or "  []\n")


def overlay(target="widgetchip", facts="", repos=""):
    text = HDR + f"format: 2\nkind: overlay\noverlays: {target}\n"
    if repos:
        text += "resources:\n  repos:\n" + repos
    return text + "facts:\n" + (facts or "  []\n")


def verdict(basis, value="PASS", **extra):
    v = {"basis": basis, "verdict": value, "date": "2026-10-08", "verifier": "a model",
         "contrary_evidence": "none-found", "citation_precision": "exact"}
    if value == "FAIL":
        v["correction"] = "the fix"
    if value == "ADJUDICATE":
        v["readings"] = [{"verifier": "a", "verdict": "PASS", "reasoning": "r"},
                         {"verifier": "b", "verdict": "FAIL", "reasoning": "s"}]
    v.update(extra)
    return {k: v[k] for k in v if v[k] is not None}


def record(sid, spec_file, verdicts, summary=None):
    """A record as JSON text (JSON is YAML the strict loader reads)."""
    counts = dict.fromkeys(records.SUMMARY, 0)
    for v in verdicts.values():
        counts[v["verdict"].lower()] += 1
    data = {"format": 2, "spec": sid, "spec_file": spec_file, "spec_sha256": "0" * 64,
            "canonical": "fact-v1", "sources": [], "summary": summary or counts,
            "verdicts": verdicts}
    return HDR + json.dumps(data, indent=2) + "\n"


class Roots(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = pathlib.Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def root(self, name, files: dict) -> pathlib.Path:
        d = self.tmp / name
        for rel, text in files.items():
            p = d / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
        return d

    def write(self, root, rel, text):
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def bases(self, *argv):
        code, result = status(*argv)
        self.assertNotIn("error", result, result)
        return {ref: r["basis"] for ref, r in rows(result).items()}

    def verify_all(self, root, sid, spec_file, *argv, extra=None):
        """Write a record giving every fact of spec_file a current PASS (with its upstream map)."""
        code, result = status(*argv)
        found = [s for s in result["specs"] if s["path"] == str(root / spec_file)]
        self.assertEqual(len(found), 1, result)
        verdicts = {}
        for r in found[0]["facts"]:
            v = verdict(r["basis"], **(extra or {}).get(r["key"], {}))
            if r["upstream"]:
                v["upstream"] = r["upstream"]
            if r["second_reader"] != "not-needed":
                v["readers"] = [{"verifier": "a second model", "verdict": v["verdict"]}]
            verdicts[r["key"]] = v
        stem = pathlib.Path(spec_file).name[:-len(".spec.yaml")]
        self.write(root, f"resources/{stem}.verify.yaml", record(sid, spec_file, verdicts))


# --- canonical form and the basis hash --------------------------------------------------------

class Canonical(unittest.TestCase):
    def test_sorted_keys_no_white_space_utf8(self):
        self.assertEqual(records.canonical({"b": [1, True, None], "a": "é"}),
                         '{"a":"é","b":[1,true,null]}')

    def test_nfc(self):
        nfd, nfc = unicodedata.normalize("NFD", "café"), "café"
        self.assertNotEqual(nfd, nfc)
        self.assertEqual(records.canonical({nfd: nfd}), records.canonical({nfc: nfc}))

    def test_integers_and_booleans_stay_apart(self):
        self.assertNotEqual(records.canonical([1]), records.canonical([True]))
        self.assertNotEqual(records.canonical(["1"]), records.canonical([1]))

    def test_refuses_what_the_format_does_not_hold(self):
        for bad, says in ((1.5, "float is not part"), ({1: "x"}, "key 1 is not a string"),
                          ((1, 2), "tuple is not part"), (b"x", "bytes is not part"),
                          ({"a": float("nan")}, "float is not part")):
            with self.assertRaisesRegex(TypeError, says, msg=repr(bad)):
                records.canonical(bad)
        with self.assertRaises(TypeError):
            records.canonical({unicodedata.normalize("NFD", "é"): 1, "é": 2})


class BasisFormula(Roots):
    """The design's formula, written out here independently of records.py (a model)."""

    @staticmethod
    def model(fact, documents, repos, assumptions, lines):
        def c(x):
            return json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

        text = ("fact-v1\n" + c(fact) + "\n" + c({"documents": documents, "repos": repos})
                + "\n" + c(assumptions) + "\n" + "\n".join(sorted(lines)))
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def test_a_cited_fact_and_a_fact_resting_on_it(self):
        assumption = "  - {id: same-silicon, text: the parts are the same die}\n"
        r = self.root("r", {
            "board-specs.yaml": marker("r", accepts="[GPL-2.0-only]", lic="GPL-2.0-only"),
            "w.spec.yaml": chip(head="assumptions:\n" + assumption, repos=LINUX, facts=(
                fact("a", extra="    assumes: [same-silicon]\n")
                + fact("b", support=("    support:\n      - class: src\n        anchors: "
                                     "[{repo: linux, path: drivers/w.c, lines: [3, 4], "
                                     "symbol: w_probe}]\n"))
                + ref_fact("c", "#a", "#b"))),
        })
        bases = self.bases(r)
        a = self.model({"id": "a", "title": "T a", "claim": "C a.", "assumes": ["same-silicon"],
                        "support": [{"class": "databook", "doc": "trm", "at": [{"section": "1"}]}]},
                       {"trm": TRM_HASHED}, {},
                       {"same-silicon": {"id": "same-silicon",
                                         "text": "the parts are the same die"}}, [])
        b = self.model({"id": "b", "title": "T b", "claim": "C b.",
                        "support": [{"class": "src", "anchors": [{
                            "repo": "linux", "path": "drivers/w.c", "lines": [3, 4],
                            "symbol": "w_probe"}]}]},
                       {}, {"linux": {"name": "linux", "url": "https://example.invalid/linux",
                                      "commit": COMMIT, "license": "GPL-2.0-only",
                                      "role": "source", "files": [
                                          {"path": "drivers/w.c", "license_from": "spdx-line"}]}},
                       {}, [])
        c = self.model({"id": "c", "title": "T c", "claim": "C c.",
                        "support": [{"class": "inference", "premises": [{"fact": "#a"},
                                                                         {"fact": "#b"}],
                                     "derivation": "it follows"}],
                        "todo": {"check": "hardware", "text": "check it."}},
                       {}, {}, {}, [f"widgetchip@r#a {a}", f"widgetchip@r#b {b}"])
        self.assertEqual(bases["widgetchip@r#a"], a)
        self.assertEqual(bases["widgetchip@r#b"], b)
        self.assertEqual(bases["widgetchip@r#c"], c)


class Invariance(Roots):
    """Plan acceptance 1: layout never counts; each edit changes exactly the expected hashes."""

    LINUX2 = LINUX.replace("name: linux", "name: tools").replace("/linux", "/tools")

    def setUp(self):
        super().setUp()
        self.docs = self.root("docs", {
            "board-specs.yaml": marker("up"),
            "u.spec.yaml": chip("upchip", facts=fact("mode") + fact("other")),
        })

    def spec(self, claim_a="C a.", section="quick-facts", trm=TRM, linux=LINUX,
             assumption="the parts are the same die", order=None):
        facts = {
            "a": fact("a", claim=claim_a, section=section),
            "b": fact("b", support=("    support:\n      - class: src\n        anchors: "
                                    "[{repo: linux, path: drivers/w.c, lines: [3, 4], "
                                    "symbol: w_probe}]\n")),
            "c": ref_fact("c", "#a"),
            "d": fact("d", extra='    relates: [{fact: "#c", relation: qualifies}]\n'),
            "e": fact("e", extra="    assumes: [same-silicon]\n"),
            "f": ref_fact("f", "upchip@up#mode"),
            "g": fact("g", support=("    support:\n      - class: src\n        anchors: "
                                    "[{repo: linux, path: drivers/x.c, lines: [1, 2], "
                                    "symbol: x_init}]\n")),
            "h": fact("h"),
            # names its assumption only through an inference premise, never in `assumes`
            "i": ("  - id: i\n    section: quick-facts\n    title: T i\n    claim: C i.\n"
                  "    support:\n      - class: inference\n        premises:\n"
                  "          - assumption: same-silicon\n        derivation: it follows\n"
                  "    todo: {check: hardware, text: check it.}\n"),
        }
        order = order or sorted(facts)
        return chip(head=f"assumptions:\n  - {{id: same-silicon, text: {assumption}}}\n",
                    docs=trm, repos=linux, facts="".join(facts[k] for k in order))

    def gpl(self, text, name="gpl"):
        return self.root(name, {"board-specs.yaml": marker("g", accepts="[GPL-2.0-only]",
                                                           lic="GPL-2.0-only"),
                                "w.spec.yaml": text})

    def changed(self, edited_spec=None, docs=None):
        base = self.bases(self.gpl(self.spec()), "--context-root", self.docs)
        root = self.gpl(edited_spec or self.spec(), name=f"g{len(list(self.tmp.iterdir()))}")
        after = self.bases(root, "--context-root", docs or self.docs)
        self.assertEqual(set(base), set(after))
        self.assertTrue(all(after.values()), after)
        return sorted(k.split("#")[1] for k in base if base[k] != after[k])

    def test_layout_changes_nothing(self):
        text = self.spec()
        variants = {
            "keys reordered": text.replace("    title: T a\n    claim: C a.\n",
                                           "    claim: C a.\n    title: T a\n"),
            "comments": text.replace("facts:\n", "# a comment\nfacts:  # another\n"),
            "facts reordered": self.spec(order=list("ihgfedcba")),
            "folded and reflowed": text.replace("    claim: C a.\n", "    claim: >-\n      C\n"
                                                                    "      a.\n"),
            "flow to block": text.replace(
                '    support: [{class: databook, doc: trm, at: [{section: "1"}]}]\n',
                '    support:\n      - class: databook\n        doc: trm\n'
                '        at:\n          - section: "1"\n', 1),
            "section moved": self.spec(section="gotchas"),
        }
        for name, edited in variants.items():
            with self.subTest(name):
                self.assertNotEqual(edited, text)
                self.assertEqual(self.changed(edited), [])

    def test_bookkeeping_changes_nothing(self):
        """Only the named bookkeeping fields (records.BOOKKEEPING); ReviewRound2 shows every
        other field counts."""
        variants = {
            "document verified, fetch, note": self.spec(
                trm=TRM.replace("verified: 2026-10-01, fetch: ok", "verified: 2026-10-07, "
                                "fetch: blocked, note: n")),
            "repos verified, fetch, fetch_via, note": self.spec(
                linux=LINUX.replace("verified: 2026-10-01\n      fetch: ok\n",
                                    "verified: 2026-10-07\n      fetch: partial\n"
                                    "      fetch_via: git\n      note: n\n")),
            "a cited files entry's note": self.spec(linux=LINUX.replace(
                "{path: drivers/w.c, license_from: spdx-line}",
                "{path: drivers/w.c, license_from: spdx-line, note: Read for reset}")),
        }
        for name, edited in variants.items():
            with self.subTest(name):
                self.assertEqual(self.changed(edited), [])

    def test_each_edit_changes_exactly_its_facts(self):
        cases = {
            # a claim: the fact, the inference resting on it, and the fact relating to that one
            "claim": (self.spec(claim_a="C a, edited."), ["a", "c", "d"]),
            "locator": (self.spec().replace('[{section: "1"}]}]\n  - id: b',
                                            '[{section: "2"}]}]\n  - id: b'), ["a", "c", "d"]),
            "cited commit": (self.spec(linux=LINUX.replace(COMMIT, "f" * 40)), ["b", "g"]),
            "cited file's license entry": (self.spec(linux=LINUX.replace(
                "{path: drivers/x.c, license_from: spdx-line}",
                "{path: drivers/x.c, license_from: notice}")), ["g"]),
            "document identity": (self.spec(trm=TRM.replace("pages: 80", "pages: 81")),
                                  ["a", "c", "d", "e", "h"]),
            "assumption text": (self.spec(assumption="the parts share a die"), ["e", "i"]),
        }
        for name, (edited, want) in cases.items():
            with self.subTest(name):
                self.assertEqual(self.changed(edited), want)

    def test_a_referenced_fact_in_another_root(self):
        docs = self.root("docs2", {
            "board-specs.yaml": marker("up"),
            "u.spec.yaml": chip("upchip", facts=fact("mode", claim="C mode, edited.")
                                + fact("other")),
        })
        self.assertEqual(self.changed(docs=docs), ["f"])

    def test_every_document_identity_field_counts(self):
        for field, old, new in (("url", "https://example.invalid/trm.pdf",
                                 "https://example.invalid/trm2.pdf"),
                                ("revision", None, "revision: B"),
                                ("sha256", None, f'sha256: "{"a" * 64}"'),
                                ("commit", None, f'commit: "{"b" * 40}"'),
                                ("page_numbering", None, "page_numbering: pdf")):
            with self.subTest(field):
                trm = (TRM.replace(old, new) if old else
                       TRM.replace("pages: 80", f"pages: 80, {new}"))
                self.assertEqual(self.changed(self.spec(trm=trm)), ["a", "c", "d", "e", "h"])


class Cycles(Roots):
    def test_a_relates_cycle_has_bases_and_any_member_edit_stales_every_member(self):
        def spec(claim="C a."):
            return chip(facts=(
                fact("a", claim=claim, extra='    relates: [{fact: "#b", relation: same-as}]\n')
                + fact("b", extra='    relates: [{fact: "#a", relation: same-as}]\n')
                + ref_fact("c", "#b") + fact("d")))

        before = self.bases(self.root("r1", {"board-specs.yaml": marker("r"),
                                             "w.spec.yaml": spec()}))
        after = self.bases(self.root("r2", {"board-specs.yaml": marker("r"),
                                            "w.spec.yaml": spec("C a, edited.")}))
        self.assertTrue(all(before.values()), before)
        self.assertEqual(sorted(k[-1] for k in before if before[k] != after[k]), ["a", "b", "c"])
        self.assertNotEqual(before["widgetchip@r#a"], before["widgetchip@r#b"])

    def test_a_cycle_takes_in_what_its_members_rest_on_outside_it(self):
        def spec(claim="C d."):
            return chip(facts=(
                fact("a", extra='    relates: [{fact: "#b", relation: same-as}, '
                                '{fact: "#d", relation: refines}]\n')
                + fact("b", extra='    relates: [{fact: "#a", relation: same-as}]\n')
                + fact("d", claim=claim) + fact("e")))

        before = self.bases(self.root("r1", {"board-specs.yaml": marker("r"),
                                             "w.spec.yaml": spec()}))
        after = self.bases(self.root("r2", {"board-specs.yaml": marker("r"),
                                            "w.spec.yaml": spec("C d, edited.")}))
        self.assertEqual(sorted(k[-1] for k in before if before[k] != after[k]), ["a", "b", "d"])

    def test_the_cycle_digest_follows_the_design(self):
        r = self.root("r", {"board-specs.yaml": marker("r"), "w.spec.yaml": chip(facts=(
            fact("a", extra='    relates: [{fact: "#b", relation: same-as}]\n')
            + fact("b", extra='    relates: [{fact: "#a", relation: same-as}]\n')))})
        got = self.bases(r)

        def c(x):
            return json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

        def h(text):
            return hashlib.sha256(text.encode("utf-8")).hexdigest()

        res = c({"documents": {"trm": TRM_HASHED}, "repos": {}})
        local = {}
        for me, other in (("a", "b"), ("b", "a")):
            local[me] = (c({"id": me, "title": f"T {me}", "claim": f"C {me}.",
                            "support": [{"class": "databook", "doc": "trm",
                                         "at": [{"section": "1"}]}],
                            "relates": [{"fact": f"#{other}", "relation": "same-as"}]})
                         + "\n" + res + "\n{}")
        digest = h("fact-v1-cycle\n" + f"widgetchip@r#a {h(local['a'])}\n"
                   f"widgetchip@r#b {h(local['b'])}" + "\n")
        for me, other in (("a", "b"), ("b", "a")):
            self.assertEqual(got[f"widgetchip@r#{me}"],
                             h(f"fact-v1\n{local[me]}\nwidgetchip@r#{other} {digest}"))



# --- the record's own checks ------------------------------------------------------------------

class RecordChecks(Roots):
    """Plan acceptance 3 and the design's record rules, one each, at the offending key."""

    def one(self, verdicts=None, summary=None, sid="widgetchip", spec_file="w.spec.yaml",
            facts=None, raw=None):
        r = self.root(f"r{len(list(self.tmp.iterdir()))}", {
            "board-specs.yaml": marker("r"),
            "w.spec.yaml": chip(facts=facts or (fact("a") + fact("b"))),
        })
        bases = self.bases(r)
        if raw is None:
            verdicts = verdicts(bases) if callable(verdicts) else verdicts
            raw = record(sid, spec_file, verdicts, summary)
        self.write(r, "resources/w.verify.yaml", raw)
        return r, check(r)

    def test_a_clean_record(self):
        r, (code, result) = self.one(lambda b: {"a": verdict(b["widgetchip@r#a"]),
                                                "b": verdict(b["widgetchip@r#b"])})
        self.assertEqual((code, result["findings"]), (0, []))
        self.assertEqual(result["verification"], {"current": 2, "stale": 0, "upstream-stale": 0,
                                                  "unverified": 0, "unknown": 0})

    def test_a_key_naming_no_fact(self):
        raw = (HDR + "format: 2\nspec: widgetchip\nspec_file: w.spec.yaml\n"
               f"spec_sha256: {'0' * 64}\ncanonical: fact-v1\nsources: []\n"
               "summary: {pass: 1, fail: 0, unverifiable: 0, gap: 0, adjudicate: 0}\n"
               "verdicts:\n  nosuch:\n"
               f"    basis: {'0' * 64}\n    verdict: PASS\n    date: 2026-10-08\n"
               "    verifier: a model\n    contrary_evidence: none-found\n"
               "    citation_precision: exact\n")
        r, (code, result) = self.one(raw=raw)
        self.assertEqual(code, 1)
        f = only(errors(result, "names no fact"))
        self.assertEqual((f["line"], f["column"]), (11, 3))  # the key itself
        self.assertIn("verdict key 'nosuch' names no fact, instance or variant of w.spec.yaml",
                      f["message"])
        self.assertTrue(f["path"].endswith("resources/w.verify.yaml"))

    def test_a_sub_key(self):
        r, (code, result) = self.one(lambda b: {"a.field": verdict(b["widgetchip@r#a"])})
        self.assertEqual(code, 1)
        self.assertIn("'a' has no field or step 'field' with its own support",
                      only(errors(result, "verdict key"))["message"])
        for bad in ("a.", ".a", "a.b.c", "A", "a..b"):  # the schema refuses other spellings
            r, (code, result) = self.one(lambda b: {bad: verdict(b["widgetchip@r#a"])})
            self.assertEqual(code, 1, bad)
            need(errors(result, "key"))

    def test_a_summary_that_does_not_match(self):
        r, (code, result) = self.one(
            lambda b: {"a": verdict(b["widgetchip@r#a"]), "b": verdict(b["widgetchip@r#b"])},
            summary={"pass": 1, "fail": 1, "unverifiable": 0, "gap": 0, "adjudicate": 0})
        self.assertEqual(code, 1)
        got = sorted(f["message"] for f in errors(result, "summary"))
        self.assertEqual(got, ["summary fail: 1, but 0 verdict(s) are FAIL",
                               "summary pass: 1, but 2 verdict(s) are PASS"])

    def test_summary_counts_adjudicate_and_needs_all_five_keys(self):
        r, (code, result) = self.one(
            lambda b: {"a": verdict(b["widgetchip@r#a"], "ADJUDICATE")},
            summary={"pass": 0, "fail": 0, "unverifiable": 0, "gap": 0, "adjudicate": 0})
        self.assertIn("summary adjudicate: 0, but 1 verdict(s) are ADJUDICATE",
                      only(errors(result, "summary"))["message"])
        r, (code, result) = self.one(
            lambda b: {"a": verdict(b["widgetchip@r#a"])},
            summary={"pass": 1, "fail": 0, "unverifiable": 0, "gap": 0})
        self.assertIn("'adjudicate' is a required property", only(errors(result))["message"])

    def test_spec_and_spec_file_name_the_file(self):
        r, (code, result) = self.one(lambda b: {}, sid="otherchip")
        self.assertIn("spec 'otherchip': the spec file 'w.spec.yaml' is spec 'widgetchip'",
                      only(errors(result))["message"])
        r, (code, result) = self.one(lambda b: {}, spec_file="sub/w.spec.yaml")
        self.assertIn("spec_file 'sub/w.spec.yaml': this record belongs to 'w.spec.yaml'",
                      only(errors(result))["message"])

    def test_an_orphan_record(self):
        r = self.root("r", {"board-specs.yaml": marker("r"), "w.spec.yaml": chip(),
                            "resources/gone.verify.yaml": record("gone", "gone.spec.yaml", {})})
        code, result = check(r)
        self.assertEqual(code, 1)
        self.assertIn("no spec file named gone.spec.yaml in root r",
                      only(errors(result))["message"])

    def test_a_record_for_a_spec_in_a_subdirectory(self):
        r = self.root("r", {"board-specs.yaml": marker("r"),
                            "ip/w.spec.yaml": chip(facts=fact("a"))})
        b = self.bases(r)
        self.write(r, "resources/w.verify.yaml",
                   record("widgetchip", "ip/w.spec.yaml", {"a": verdict(b["widgetchip@r#a"])}))
        code, result = check(r)
        self.assertEqual((code, result["findings"]), (0, []))

    def test_two_spec_files_sharing_a_record_name(self):
        r = self.root("r", {"board-specs.yaml": marker("r"), "w.spec.yaml": chip(facts=fact("a")),
                            "ip/w.spec.yaml": chip("otherchip", facts=fact("b"))})
        b = self.bases(r)
        # a record that would be current for either file, were it read: it is read for neither
        for sid, rel, key in (("widgetchip", "w.spec.yaml", "a"),
                              ("otherchip", "ip/w.spec.yaml", "b")):
            with self.subTest(rel):
                self.write(r, "resources/w.verify.yaml", record(sid, rel, {
                    key: verdict(b[f"{sid}@r#{key}"])}))
                code, result = check(r)
                self.assertEqual(code, 1)
                found = errors(result)
                self.assertTrue(all("would share the verification record "
                                    "resources/w.verify.yaml" in f["message"] for f in found),
                                found)
                self.assertEqual(sorted(pathlib.Path(f["path"]).relative_to(r).as_posix()
                                        for f in found), ["ip/w.spec.yaml", "w.spec.yaml"])
                st = rows(status(r)[1])
                self.assertEqual({k: (v["status"], v["verdict"]) for k, v in st.items()},
                                 {"widgetchip@r#a": ("unverified", None),
                                  "otherchip@r#b": ("unverified", None)})
                self.assertEqual(len(warnings(result, "its record name is shared")), 2)

    def test_records_discovery_passes_over_are_errors(self):
        for rel in ("w.verify.yaml", "resources/sub/w.verify.yaml", "resources/w.verify.yml",
                    "resources/w.VERIFY.yaml", "resources/w.verify.yaml~",
                    "resources/w.verify.yaml.bak", "resources/w.verify.md",
                    # only the root's own resources/ holds records, never a nested one
                    "sub/resources/w.verify.yaml",
                    # in resources/, any name with "verify" in it (review round 1)
                    "resources/w.verify", "resources/wverify.yaml",
                    "resources/W.Verify-notes.txt"):
            with self.subTest(rel):
                r = self.root(f"m{len(list(self.tmp.iterdir()))}", {
                    "board-specs.yaml": marker("r"), "w.spec.yaml": chip(), rel: "x\n"})
                code, result = check(r)
                self.assertEqual(code, 1)
                f = only(errors(result))
                self.assertTrue(f["path"].endswith(rel), f)
                self.assertRegex(f["message"], r"verification record")

    def test_a_record_that_does_not_validate_leaves_every_fact_unverified(self):
        r, (code, result) = self.one(raw=record("widgetchip", "w.spec.yaml", {})
                                     .replace('"canonical": "fact-v1"', '"canonical": "fact-v2"'))
        self.assertEqual(code, 1)
        self.assertEqual(len(warnings(result, "does not validate")), 2)
        self.assertEqual(result["verification"]["unverified"], 2)

    def test_degenerate_records(self):
        for name, raw in (("empty", ""), ("white space", "  \n\n"), ("empty mapping", "{}\n"),
                          ("a list", "[]\n"), ("null", "null\n"),
                          ("empty verdict", record("widgetchip", "w.spec.yaml", {})
                           .replace('"verdicts": {}', '"verdicts": {"a": {}}'))):
            with self.subTest(name):
                r, (code, result) = self.one(raw=raw)
                self.assertEqual(code, 1)
                need(errors(result))
                self.assertEqual(result["verification"]["unverified"], 2)
                self.assertEqual(result["verification"]["current"], 0)

    def test_gap_verdicts_belong_to_gap_facts(self):
        gap = "  - id: g\n    section: quick-facts\n    title: T g\n    claim: C g.\n" \
              "    todo: {check: hardware, text: measure it.}\n"
        r, (code, result) = self.one(
            lambda b: {"a": verdict(b["widgetchip@r#a"], "GAP"),
                       "g": verdict(b["widgetchip@r#g"], "PASS")}, facts=fact("a") + gap)
        got = sorted(f["message"] for f in errors(result, "GAP"))
        self.assertEqual(len(got), 2, got)
        self.assertIn("verdict GAP for 'a', which has support", got[0])
        self.assertIn("verdict PASS for 'g', a gap fact (no support): its verdict is GAP", got[1])
        r, (code, result) = self.one(lambda b: {"g": verdict(b["widgetchip@r#g"], "GAP")},
                                     facts=fact("a") + gap)
        self.assertEqual(errors(result), [])

    def test_a_reader_who_disagrees(self):
        r, (code, result) = self.one(lambda b: {"a": verdict(
            b["widgetchip@r#a"], readers=[{"verifier": "second", "verdict": "FAIL"}])})
        f = only(errors(result, "disagrees"))
        self.assertIn("a reader's verdict FAIL disagrees with PASS", f["message"])
        r, (code, result) = self.one(lambda b: {"a": verdict(
            b["widgetchip@r#a"], "ADJUDICATE", readers=[{"verifier": "x", "verdict": "FAIL"}])})
        self.assertEqual(errors(result, "disagrees"), [])

    def test_carried_verdicts(self):
        carried1 = {"repo": "widget-specs", "commit": COMMIT, "path": "specs/resources/w.verify.md",
                    "key": "Quick-facts/1", "format": 1}
        carried2 = dict(carried1, path="specs/resources/w.verify.yaml", key="a", format=2)

        def bare(basis, **extra):
            v = verdict(basis, **extra)
            del v["contrary_evidence"], v["citation_precision"]
            return v

        good = {
            "from format 1, without the two fields": lambda b: {
                "a": bare(b["widgetchip@r#a"], carried_from=carried1)},
            "from format 2, with them": lambda b: {
                "a": verdict(b["widgetchip@r#a"], carried_from=carried2)},
        }
        for name, make in good.items():
            with self.subTest(name):
                r, (code, result) = self.one(make)
                self.assertEqual(errors(result), [], result)
                st = rows(status(r)[1])["widgetchip@r#a"]
                self.assertEqual((st["status"], st["carried"]), ("current", True))
        bad = {
            "from format 1, with them": (lambda b: {
                "a": verdict(b["widgetchip@r#a"], carried_from=carried1)},
                "carried from a format 1 record leaves out"),
            "from format 2, without them": (lambda b: {
                "a": bare(b["widgetchip@r#a"], carried_from=carried2)},
                "or carried from a format 2 record, states"),
            "not carried, without them": (lambda b: {"a": bare(b["widgetchip@r#a"])},
                                          "reached under format 2"),
            "from format 3": (lambda b: {
                "a": bare(b["widgetchip@r#a"], carried_from=dict(carried1, format=3))},
                "carried_from.format"),
        }
        for name, (make, want) in bad.items():
            with self.subTest(name):
                r, (code, result) = self.one(make)
                self.assertEqual(code, 1)
                self.assertTrue(any(want in f["message"] for f in need(errors(result))),
                                result["findings"])

    def test_a_key_for_a_fact_declared_twice(self):
        r, (code, result) = self.one(lambda b: {"a": verdict("0" * 64)},
                                     facts=fact("a") + fact("a"))
        self.assertIn("fact id 'a' is declared twice in w.spec.yaml, so the key is ambiguous",
                      only(errors(result, "verdict key"))["message"])

    def test_instances_and_variants_are_keyed_too(self):
        soc = (HDR + "format: 2\nkind: soc\nid: wsoc\nname: W\ntriggers: [wsoc]\n"
               "instances:\n  - {id: uart0, name: uart0, ip: wuart, reg: \"0x1000\", "
               "irq: {kind: SPI, number: 1}, clocks: [],\n"
               '     support: [{class: databook, doc: trm, at: [{section: "2"}]}]}\n'
               "resources:\n  documents:\n" + TRM + "facts:\n" + fact("a"))
        ip = (HDR + "format: 2\nkind: ip\nid: wuart\nname: U\ntriggers: [wuart]\n"
              "resources:\n  documents:\n" + TRM + "facts:\n"
              + fact("u", section="programming-model"))
        r = self.root("r", {"board-specs.yaml": marker("r"), "s.spec.yaml": soc,
                            "u.spec.yaml": ip})
        b = self.bases(r)
        self.assertIn("wsoc@r#uart0", b)
        self.write(r, "resources/s.verify.yaml", record("wsoc", "s.spec.yaml", {
            "uart0": verdict(b["wsoc@r#uart0"]), "a": verdict(b["wsoc@r#a"])}))
        code, result = check(r)
        self.assertEqual(errors(result), [])
        self.assertEqual(rows(status(r)[1])["wsoc@r#uart0"]["kind"], "instance")

    def test_record_errors_make_the_root_untrusted(self):
        docs = self.root("docs", {"board-specs.yaml": marker("d"),
                                  "w.spec.yaml": chip(facts=fact("a")),
                                  "resources/w.verify.yaml": record("widgetchip", "w.spec.yaml",
                                                                    {"nosuch": verdict("0" * 64)})})
        gpl = self.root("gpl", {"board-specs.yaml": marker("g"),
                                "x.spec.yaml": chip("xchip", facts=ref_fact("b", "widgetchip@d#a"))})
        code, result = check(gpl, "--context-root", docs)
        self.assertEqual(code, 1)
        self.assertIn("cannot be resolved: root d, which is untrusted",
                      only(errors(result))["message"])


# --- freshness and the two CI modes -----------------------------------------------------------

class VerifyRoot(unittest.TestCase):
    """board-expert's verify_root cases in format 2: every status, in every mode."""

    def test_the_fixture_bases_are_current_where_they_should_be(self):
        got = rows(status(VROOT)[1])
        for sid in ("vok", "vfail"):
            self.assertEqual(records_of(sid)["reset"]["basis"],
                             got[f"{sid}@verify#reset"]["basis"], sid)
        for sid in ("vstale", "vstalefail"):
            self.assertNotEqual(records_of(sid)["reset"]["basis"],
                                got[f"{sid}@verify#reset"]["basis"], sid)

    def test_every_status_in_every_mode(self):
        want = {"vok": "current", "vfail": "current", "vstale": "stale", "vstalefail": "stale",
                "vnone": "unverified", "vbad": "unverified"}
        for mode in (None, "pr", "main"):
            with self.subTest(mode=mode):
                code, result = check(VROOT, *(["--require-verified", mode] if mode else []))
                self.assertEqual(code, 1)
                self.assertEqual(result["verification"], {"current": 2, "stale": 2,
                                                          "upstream-stale": 0, "unverified": 2,
                                                          "unknown": 0})
                by_file = {}
                for f in result["findings"]:
                    by_file.setdefault(pathlib.Path(f["path"]).name, []).append(
                        (f["level"], f["message"]))
                level = "warning" if mode is None else "error"
                self.assertNotIn("vok.spec.yaml", by_file)
                self.assertEqual(by_file["vfail.spec.yaml"], [("error", by_file["vfail.spec.yaml"][0][1])])
                self.assertIn("its current verdict in resources/vfail.verify.yaml is FAIL "
                              "(correction: section 1 states 12 cycles)",
                              by_file["vfail.spec.yaml"][0][1])
                [(lv, msg)] = by_file["vstale.spec.yaml"]
                self.assertEqual(lv, level)
                self.assertIn("verdict stale", msg)
                self.assertNotIn("FAIL", msg)
                [(lv, msg)] = by_file["vstalefail.spec.yaml"]
                self.assertEqual(lv, level)
                self.assertIn("(its FAIL was for that version)", msg)
                [(lv, msg)] = by_file["vnone.spec.yaml"]
                self.assertEqual((lv, msg.split(": ", 1)[1]),
                                 (level, "unverified: no record at resources/vnone.verify.yaml"))
                [(lv, msg)] = by_file["vbad.spec.yaml"]
                self.assertEqual(lv, level)
                self.assertIn("its record resources/vbad.verify.yaml does not validate", msg)
                self.assertEqual(len(by_file["vbad.verify.yaml"]), 3)
                self.assertTrue(all(lv == "error" for lv, _ in by_file["vbad.verify.yaml"]))

    def test_a_verified_root_is_clean_in_both_modes(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = pathlib.Path(tmp) / "r"
            (r / "resources").mkdir(parents=True)
            shutil.copy(VROOT / "board-specs.yaml", r)
            shutil.copy(VROOT / "vok.spec.yaml", r)
            shutil.copy(VROOT / "resources" / "vok.verify.yaml", r / "resources")
            for mode in (None, "pr", "main"):
                code, result = check(r, *(["--require-verified", mode] if mode else []))
                self.assertEqual((code, result["findings"]), (0, []), mode)


def records_of(sid):
    import specload

    return specload.load_strict(VROOT / "resources" / f"{sid}.verify.yaml")["verdicts"]


class Upstream(Roots):
    """D19: a change in another root is upstream-stale: a warning under main, an error under pr;
    main never relaxes a fact staled by its own file."""

    def setUp(self):
        super().setUp()
        self.docs = self.make_docs("C mode.")
        self.gpl = self.root("gpl", {
            "board-specs.yaml": marker("g"),
            "x.spec.yaml": chip("xchip", facts=(
                ref_fact("direct", "upchip@up#mode")
                + ref_fact("through", "#direct")  # reaches docs through a same-root fact
                + fact("local"))),
        })
        self.verify_all(self.gpl, "xchip", "x.spec.yaml", self.gpl, "--context-root", self.docs)

    def make_docs(self, claim, name=None):
        return self.root(name or f"docs{len(list(self.tmp.iterdir()))}", {
            "board-specs.yaml": marker("up"),
            "u.spec.yaml": chip("upchip", facts=fact("mode", claim=claim) + fact("other")),
        })

    def test_verified_then_clean(self):
        for mode in (None, "pr", "main"):
            code, result = check(self.gpl, "--context-root", self.docs,
                                 *(["--require-verified", mode] if mode else []))
            self.assertEqual(errors(result), [], mode)
            self.assertEqual(result["verification"]["current"], 3)
        rec = records_of_root(self.gpl, "x")
        self.assertEqual(set(rec["direct"]["upstream"]), {"upchip@up#mode"})
        self.assertEqual(set(rec["through"]["upstream"]), {"upchip@up#mode"})
        self.assertNotIn("upstream", rec["local"])

    def test_an_upstream_edit_is_upstream_stale(self):
        docs = self.make_docs("C mode, edited.")
        expect = {None: "warning", "pr": "error", "main": "warning"}
        for mode, level in expect.items():
            with self.subTest(mode=mode):
                code, result = check(self.gpl, "--context-root", docs,
                                     *(["--require-verified", mode] if mode else []))
                self.assertEqual(code, 1 if level == "error" else 0, result["findings"])
                found = [f for f in result["findings"] if "upstream-stale" in f["message"]]
                self.assertEqual(sorted(f["message"].split(":")[0] for f in found),
                                 ["fact 'direct'", "fact 'through'"])
                for f in found:
                    self.assertEqual(f["level"], level)
                    self.assertIn("upstream-stale: upchip@up#mode changed since the verdict of "
                                  "2026-10-08", f["message"])
                self.assertEqual(result["verification"]["upstream-stale"], 2)
        st = rows(status(self.gpl, "--context-root", docs)[1])
        self.assertEqual(st["xchip@g#direct"]["changed"], ["upchip@up#mode"])
        self.assertEqual(st["xchip@g#local"]["status"], "current")

    def test_an_unrelated_upstream_edit_stales_nothing(self):
        docs = self.root("docs-other", {
            "board-specs.yaml": marker("up"),
            "u.spec.yaml": chip("upchip", facts=fact("mode") + fact("other", claim="edited")),
        })
        code, result = check(self.gpl, "--context-root", docs, "--require-verified", "pr")
        self.assertEqual((code, result["findings"]), (0, []))

    def test_main_does_not_relax_a_fact_staled_by_its_own_file(self):
        text = (self.gpl / "x.spec.yaml").read_text()
        own = text.replace("    claim: C direct.\n", "    claim: C direct, edited.\n")
        both_docs = self.make_docs("C mode, edited.")
        cases = (("own edit", own, self.docs, "direct"),
                 ("own edit and upstream edit", own, both_docs, "direct"),
                 ("own edit to a fact without upstream",
                  text.replace("C local.", "C local, edited."), self.docs, "local"))
        for name, spec, docs, edited in cases:
            with self.subTest(name):
                (self.gpl / "x.spec.yaml").write_text(spec)
                code, result = check(self.gpl, "--context-root", docs,
                                     "--require-verified", "main")
                self.assertEqual(code, 1)
                mine = [f for f in result["findings"]
                        if f["message"].startswith(f"fact '{edited}': ")]
                self.assertEqual([(f["level"], f["message"].split(": ")[1]) for f in mine],
                                 [("error", "verdict stale")])
        (self.gpl / "x.spec.yaml").write_text(text)

    def test_a_same_root_edit_reaching_through_is_stale_not_upstream(self):
        text = (self.gpl / "x.spec.yaml").read_text()
        (self.gpl / "x.spec.yaml").write_text(text.replace("    claim: C direct.\n",
                                                           "    claim: C direct, edited.\n"))
        code, result = check(self.gpl, "--context-root", self.docs, "--require-verified", "main")
        self.assertEqual(sorted(f["message"].split(":")[0] for f in errors(result)),
                         ["fact 'direct'", "fact 'through'"])
        self.assertTrue(all("verdict stale" in f["message"] for f in errors(result)))

    def test_a_current_verdict_records_its_upstream_exactly(self):
        rec = records_of_root(self.gpl, "x")
        good = rec["direct"]["upstream"]["upchip@up#mode"]
        cases = {
            "missing": None,
            "wrong value": {"upchip@up#mode": "f" * 64},
            "extra key": {"upchip@up#mode": good, "upchip@up#other": good},
            "not a full reference": {"#mode": good},
            "empty": {},
        }
        for name, value in cases.items():
            with self.subTest(name):
                edited = json.loads(json.dumps(rec))
                if value is None:
                    del edited["direct"]["upstream"]
                else:
                    edited["direct"]["upstream"] = value
                self.write(self.gpl, "resources/x.verify.yaml",
                           record("xchip", "x.spec.yaml", edited))
                code, result = check(self.gpl, "--context-root", self.docs)
                self.assertEqual(code, 1)
                f = only(errors(result))
                self.assertTrue(f["path"].endswith("resources/x.verify.yaml"))
                if name == "not a full reference":
                    self.assertIn("an upstream key is a fact's full reference", f["message"])
                elif name == "empty":
                    self.assertIn("should be non-empty", f["message"])
                else:
                    self.assertIn("verdict key 'direct': upstream does not match", f["message"])
        edited = json.loads(json.dumps(rec))
        edited["local"]["upstream"] = {"upchip@up#mode": good}
        self.write(self.gpl, "resources/x.verify.yaml", record("xchip", "x.spec.yaml", edited))
        code, result = check(self.gpl, "--context-root", self.docs)
        self.assertIn("verdict key 'local': upstream does not match the facts in other roots "
                      "the fact rests on (now none)", only(errors(result))["message"])

    def test_without_an_upstream_map_an_upstream_edit_reads_stale(self):
        """Classification fails safe: no recorded map, no relaxation under main."""
        rec = records_of_root(self.gpl, "x")
        del rec["direct"]["upstream"]
        self.write(self.gpl, "resources/x.verify.yaml", record("xchip", "x.spec.yaml", rec))
        code, result = check(self.gpl, "--context-root", self.make_docs("C mode, edited."),
                             "--require-verified", "main")
        self.assertIn("fact 'direct': verdict stale", "\n".join(
            f["message"] for f in errors(result)))

    def test_an_upstream_map_naming_other_facts_reads_stale(self):
        """Upstream-stale needs the recorded map's keys to be exactly the facts the fact rests
        on now; a map with an extra key explains nothing, so the verdict is plain stale."""
        rec = records_of_root(self.gpl, "x")
        good = rec["direct"]["upstream"]["upchip@up#mode"]
        rec["direct"]["upstream"] = {"upchip@up#mode": good, "upchip@up#other": good}
        self.write(self.gpl, "resources/x.verify.yaml", record("xchip", "x.spec.yaml", rec))
        code, result = check(self.gpl, "--context-root", self.make_docs("C mode, edited."),
                             "--require-verified", "main")
        self.assertEqual(code, 1)
        mine = [f for f in result["findings"] if f["message"].startswith("fact 'direct': ")]
        self.assertEqual([(f["level"], f["message"].split(": ")[1]) for f in mine],
                         [("error", "verdict stale")])

    def test_an_empty_upstream_on_a_fact_without_one_is_refused(self):
        rec = records_of_root(self.gpl, "x")
        rec["local"]["upstream"] = {}
        self.write(self.gpl, "resources/x.verify.yaml", record("xchip", "x.spec.yaml", rec))
        code, result = check(self.gpl, "--context-root", self.docs)
        self.assertIn("should be non-empty", only(errors(result))["message"])

    def test_a_dangling_upstream_is_unknown_and_an_error_in_both_modes(self):
        docs = self.root("docs-gone", {"board-specs.yaml": marker("up"),
                                       "u.spec.yaml": chip("upchip", facts=fact("other"))})
        for mode in ("pr", "main"):
            code, result = check(self.gpl, "--context-root", docs, "--require-verified", mode)
            self.assertEqual(code, 1)
            unknown = errors(result, "freshness unknown")
            self.assertEqual(sorted(f["message"].split(":")[0] for f in unknown),
                             ["fact 'direct'", "fact 'through'"])
        st = rows(status(self.gpl, "--context-root", docs)[1])
        self.assertEqual((st["xchip@g#through"]["status"], st["xchip@g#through"]["basis"]),
                         ("unknown", None))
        self.assertIsInstance(st["xchip@g#direct"]["reason"], str)
        self.assertIn("reference 'upchip@up#mode' resolves to nothing",
                      st["xchip@g#direct"]["reason"])
        # through rests on direct, whose reference the gate already failed
        self.assertIsInstance(st["xchip@g#through"]["reason"], str)
        self.assertIn("reference '#direct' failed the check", st["xchip@g#through"]["reason"])

    def test_a_current_fail_upstream_untrusts_its_root(self):
        b = self.bases(self.docs)
        self.write(self.docs, "resources/u.verify.yaml", record("upchip", "u.spec.yaml", {
            "mode": verdict(b["upchip@up#mode"]), "other": verdict(b["upchip@up#other"], "FAIL")}))
        code, result = check(self.gpl, "--context-root", self.docs)
        self.assertEqual(code, 1)
        self.assertEqual(len(warnings(result, "context root: fact 'other': its current verdict")), 1)
        found = need(errors(result, "which is untrusted"))
        self.assertIn("its current verdict in resources/u.verify.yaml is FAIL", found[0]["message"])
        st = rows(status(self.gpl, "--context-root", self.docs)[1])
        self.assertEqual(st["xchip@g#direct"]["status"], "unknown")

    def test_context_roots_get_no_freshness_findings(self):
        code, result = check(self.gpl, "--context-root", self.docs, "--require-verified", "pr")
        self.assertEqual((code, result["findings"]), (0, []))  # the docs facts have no record
        # check --json counts the checked roots only: the docs root's two unverified facts
        # are not counted
        self.assertEqual(result["verification"], {"current": 3, "stale": 0, "upstream-stale": 0,
                                                  "unverified": 0, "unknown": 0})
        code, result = status(self.gpl, "--context-root", self.docs)
        self.assertEqual([s["root"] for s in result["specs"]], ["g"])


def records_of_root(root, stem):
    import specload

    return specload.load_strict(root / "resources" / f"{stem}.verify.yaml")["verdicts"]


class Compute(unittest.TestCase):
    """records.compute on a hand-built graph, apart from any checker."""

    class Node:
        def __init__(self, full):
            self.full = full

    def test_resting_on_an_unknown_fact_is_unknown(self):
        """A reference that resolves to a fact whose basis is unknown makes the referring fact
        unknown too, with the first reason found; it never hashes the missing basis."""
        x, y, z = self.Node("s@r#x"), self.Node("s@r#y"), self.Node("s@r#z")
        graph = {x: [("#y", y, None)], y: [("#z", z, None)], z: []}
        local = {x: ("x", None), y: ("y", None), z: (None, "z cites an unlisted document")}
        out = records.compute([x], graph.__getitem__, local.__getitem__, {}, {})
        self.assertEqual(out, {z: (None, "z cites an unlisted document"),
                               y: (None, "z cites an unlisted document"),
                               x: (None, "z cites an unlisted document")})

    def test_a_fact_naming_itself_is_a_cycle_of_one(self):
        """A self-reference cannot take its own basis first, so it hashes as a cycle: the
        member's line for itself carries the cycle digest."""
        x = self.Node("s@r#x")
        out = records.compute([x], {x: [("#x", x, None)]}.__getitem__,
                              {x: ("x", None)}.__getitem__, {}, {})

        def h(text):
            return hashlib.sha256(text.encode("utf-8")).hexdigest()

        digest = h(f"fact-v1-cycle\ns@r#x {h('x')}\n")
        self.assertEqual(out[x], (h(f"fact-v1\nx\ns@r#x {digest}"), None))

    def test_resting_on_known_facts_hashes_their_bases(self):
        x, y = self.Node("s@r#x"), self.Node("s@r#y")
        out = records.compute([x], {x: [("#y", y, None)], y: []}.__getitem__,
                              {x: ("x", None), y: ("y", None)}.__getitem__, {}, {})
        y_basis = hashlib.sha256(b"fact-v1\ny\n").hexdigest()
        self.assertEqual(out[y], (y_basis, None))
        self.assertEqual(out[x], (hashlib.sha256(f"fact-v1\nx\ns@r#y {y_basis}".encode())
                                  .hexdigest(), None))


class CrossRootCycle(Roots):
    """A relates cycle across two roots hashes as one component. A verdict whose basis matches
    only the upstream recomputation (where the other root's fact is a leaf), with nothing
    upstream changed, is stale: the classification never relaxes what it cannot explain."""

    def test_nothing_changed_upstream_reads_stale_not_upstream_stale(self):
        a_text = chip("achip", facts=fact("a", extra='    relates: [{fact: "bchip@rb#b", '
                                                     'relation: same-as}]\n'))
        b_text = chip("bchip", facts=fact("b", extra='    relates: [{fact: "achip@ra#a", '
                                                     'relation: same-as}]\n'))
        ra = self.root("ra", {"board-specs.yaml": marker("ra"), "a.spec.yaml": a_text})
        rb = self.root("rb", {"board-specs.yaml": marker("rb"), "b.spec.yaml": b_text})
        st = rows(status(ra, rb)[1])
        b_now = st["bchip@rb#b"]["basis"]
        self.assertEqual(st["achip@ra#a"]["upstream"], {"bchip@rb#b": b_now})

        def c(x):
            return json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

        local = (c({"id": "a", "title": "T a", "claim": "C a.",
                    "support": [{"class": "databook", "doc": "trm", "at": [{"section": "1"}]}],
                    "relates": [{"fact": "bchip@rb#b", "relation": "same-as"}]})
                 + "\n" + c({"documents": {"trm": {"url": "https://example.invalid/trm.pdf",
                                                   "pages": 80}}, "repos": {}}) + "\n{}")
        leaf = hashlib.sha256(f"fact-v1\n{local}\nbchip@rb#b {b_now}".encode()).hexdigest()
        self.assertNotEqual(leaf, st["achip@ra#a"]["basis"])
        self.write(ra, "resources/a.verify.yaml", record("achip", "a.spec.yaml", {
            "a": verdict(leaf, upstream={"bchip@rb#b": b_now})}))
        self.assertEqual(rows(status(ra, rb)[1])["achip@ra#a"]["status"], "stale")


class SecondReaders(Roots):
    def test_a_critical_fact_needs_a_second_reader(self):
        r = self.root("r", {"board-specs.yaml": marker("r"), "w.spec.yaml": chip(
            facts=fact("a", extra="    critical: true\n") + fact("b"))})
        b = self.bases(r)
        self.write(r, "resources/w.verify.yaml", record("widgetchip", "w.spec.yaml", {
            "a": verdict(b["widgetchip@r#a"]), "b": verdict(b["widgetchip@r#b"])}))
        for mode, level in ((None, "warning"), ("pr", "error"), ("main", "error")):
            code, result = check(r, *(["--require-verified", mode] if mode else []))
            f = only([f for f in result["findings"] if "second reader" in f["message"]])
            self.assertEqual(f["level"], level, mode)
            self.assertIn("fact 'a': critical, so its verdict needs a second reader's verdict in "
                          "readers (D14)", f["message"])
        st = rows(status(r, "--stale")[1])
        self.assertEqual(list(st), ["widgetchip@r#a"])
        self.assertEqual(st["widgetchip@r#a"]["second_reader"], "missing")
        self.write(r, "resources/w.verify.yaml", record("widgetchip", "w.spec.yaml", {
            "a": verdict(b["widgetchip@r#a"], readers=[{"verifier": "b", "verdict": "PASS"}]),
            "b": verdict(b["widgetchip@r#b"])}))
        self.assertEqual(check(r, "--require-verified", "pr")[1]["findings"], [])
        self.assertEqual(status(r, "--stale")[1]["specs"], [])

    def test_a_stale_critical_fact_reports_stale_only(self):
        r = self.root("r", {"board-specs.yaml": marker("r"), "w.spec.yaml": chip(
            facts=fact("a", extra="    critical: true\n"))})
        self.write(r, "resources/w.verify.yaml", record("widgetchip", "w.spec.yaml", {
            "a": verdict("0" * 64)}))
        code, result = check(r, "--require-verified", "pr")
        self.assertIn("verdict stale", only(errors(result))["message"])


class Verdicts(Roots):
    def test_adjudicate_is_a_warning_in_every_mode(self):
        r = self.root("r", {"board-specs.yaml": marker("r"), "w.spec.yaml": chip(facts=fact("a"))})
        b = self.bases(r)
        self.write(r, "resources/w.verify.yaml", record("widgetchip", "w.spec.yaml", {
            "a": verdict(b["widgetchip@r#a"], "ADJUDICATE")}))
        for mode in (None, "pr", "main"):
            code, result = check(r, *(["--require-verified", mode] if mode else []))
            self.assertEqual(code, 0, mode)
            self.assertIn("its verdict is ADJUDICATE, not yet settled",
                          only(warnings(result))["message"])

    def test_unverifiable_and_gap_are_verdicts(self):
        gap = "  - id: g\n    section: quick-facts\n    title: T g\n    claim: C g.\n" \
              "    todo: {check: hardware, text: measure it.}\n"
        r = self.root("r", {"board-specs.yaml": marker("r"),
                            "w.spec.yaml": chip(facts=fact("a") + gap)})
        b = self.bases(r)
        self.write(r, "resources/w.verify.yaml", record("widgetchip", "w.spec.yaml", {
            "a": verdict(b["widgetchip@r#a"], "UNVERIFIABLE"),
            "g": verdict(b["widgetchip@r#g"], "GAP")}))
        code, result = check(r, "--require-verified", "pr")
        self.assertEqual((code, result["findings"]), (0, []))

    def test_a_basis_that_happens_to_match_is_not_current_when_unknown(self):
        """An unknown basis never compares equal, whatever the record says."""
        r = self.root("r", {"board-specs.yaml": marker("r"), "w.spec.yaml": chip(
            facts=ref_fact("a", "#nosuch"))})
        self.write(r, "resources/w.verify.yaml", record("widgetchip", "w.spec.yaml", {
            "a": verdict("0" * 64)}))
        st = rows(status(r)[1])["widgetchip@r#a"]
        self.assertEqual((st["status"], st["basis"], st["recorded"]), ("unknown", None, "0" * 64))

    def test_each_unlisted_name_makes_the_basis_unknown(self):
        """A cited document, repos entry, assumption or path the file does not list leaves the
        basis unknown, whatever else the fact cites; the reason names what is missing."""
        anchor = ("    support:\n      - class: src\n        anchors: [{{repo: {repo}, "
                  "path: {path}, lines: [1, 2], symbol: s}}]\n")
        facts = (fact("doc", support=('    support: [{class: databook, doc: nosuch, '
                                      'at: [{section: "1"}]}]\n'))
                 + fact("repo", support=anchor.format(repo="nosuch", path="drivers/w.c"))
                 + fact("path", support=anchor.format(repo="linux", path="drivers/zz.c"))
                 + fact("assumed", extra="    assumes: [nosuch]\n")
                 + fact("fine"))
        r = self.root("r", {"board-specs.yaml": marker("r", accepts="[GPL-2.0-only]",
                                                       lic="GPL-2.0-only"),
                            "w.spec.yaml": chip(repos=LINUX, facts=facts)})
        st = rows(status(r)[1])
        want = {"doc": "document 'nosuch' is not in its file's resources",
                "repo": "repos entry 'nosuch' is not in its file's resources",
                "path": "'drivers/zz.c' is not in the files of repos entry 'linux'",
                "assumed": "assumption 'nosuch' is not in its file's assumptions"}
        for key, reason in want.items():
            with self.subTest(key):
                row = st[f"widgetchip@r#{key}"]
                self.assertEqual((row["status"], row["basis"]), ("unknown", None))
                self.assertIsInstance(row["reason"], str)
                self.assertIn(reason, row["reason"])
        self.assertEqual(st["widgetchip@r#fine"]["status"], "unverified")

    def test_an_overlay_record(self):
        base = self.root("base", {"board-specs.yaml": marker("b"),
                                  "w.spec.yaml": chip(facts=fact("a"))})
        over = self.root("over", {"board-specs.yaml": marker("o", layer="product"),
                                  "w-extra.spec.yaml": overlay(facts=fact("x", support=(
                                      "    support: [{class: hardware, board: a widget board, "
                                      "method: a scope on the reset line, date: 2026-10-01}]\n"
                                  )))})
        b = self.bases(over, "--context-root", base)
        self.write(over, "resources/w-extra.verify.yaml", record(
            "widgetchip", "w-extra.spec.yaml", {"x": verdict(b["widgetchip@o#x"])}))
        code, result = check(over, "--context-root", base, "--require-verified", "pr")
        self.assertEqual((code, result["findings"]), (0, []))


class ReviewRound1(Roots):
    """The fixes of SF2-3's review round 1, one rule each."""

    def test_an_own_root_fact_reached_through_another_root_is_stale_not_upstream(self):
        """a1 rests on bchip@bb#b1, which rests on a2 in a1's own root. Editing a2 changes b1's
        basis, but the change is in a1's own root, so a1 is stale, and main does not relax it
        (upstream-stale needs the closure beyond the frontier to stay outside the own root)."""
        a = self.root("aa", {"board-specs.yaml": marker("aa"), "a.spec.yaml": chip(
            "achip", facts=ref_fact("a1", "bchip@bb#b1") + fact("a2"))})
        b = self.root("bb", {"board-specs.yaml": marker("bb"), "b.spec.yaml": chip(
            "bchip", facts=ref_fact("b1", "achip@aa#a2"))})
        self.verify_all(a, "achip", "a.spec.yaml", a, b)
        self.assertEqual(set(records_of_root(a, "a")["a1"]["upstream"]), {"bchip@bb#b1"})
        text = (a / "a.spec.yaml").read_text()
        (a / "a.spec.yaml").write_text(text.replace("C a2.", "C a2, edited."))
        st = rows(status(a, b)[1])
        self.assertEqual((st["achip@aa#a1"]["status"], st["achip@aa#a1"]["changed"]),
                         ("stale", []))
        code, result = check(a, b, "--require-verified", "main")
        self.assertEqual(code, 1)
        self.assertIn("fact 'a1': verdict stale", "\n".join(
            f["message"] for f in errors(result)))
        self.assertEqual(warnings(result, "upstream-stale"), [])

    def test_the_way_back_is_followed_through_every_fact_and_file(self):
        """The closure beyond the frontier is followed transitively (a1 -> b1 -> b2 -> a2) and
        by root, not by file (a1 -> b1 -> a spec in another file of a1's root)."""
        cases = {
            "through a second fact of the other root": (
                {"a.spec.yaml": chip("achip", facts=ref_fact("a1", "bchip@bb#b1") + fact("a2"))},
                ref_fact("b1", "#b2") + ref_fact("b2", "achip@aa#a2"), "a.spec.yaml", "C a2."),
            "into another file of the own root": (
                {"a.spec.yaml": chip("achip", facts=ref_fact("a1", "bchip@bb#b1")),
                 "d.spec.yaml": chip("dchip", facts=fact("d1"))},
                ref_fact("b1", "dchip@aa#d1"), "d.spec.yaml", "C d1."),
        }
        for name, (afiles, bfacts, edited, claim) in cases.items():
            with self.subTest(name):
                n = len(list(self.tmp.iterdir()))
                a = self.root(f"a{n}", {"board-specs.yaml": marker("aa"), **afiles})
                b = self.root(f"b{n}", {"board-specs.yaml": marker("bb"),
                                        "b.spec.yaml": chip("bchip", facts=bfacts)})
                self.verify_all(a, "achip", "a.spec.yaml", a, b)
                text = (a / edited).read_text()
                (a / edited).write_text(text.replace(claim, claim[:-1] + ", edited."))
                st = rows(status(a, b)[1])["achip@aa#a1"]
                self.assertEqual((st["status"], st["changed"]), ("stale", []))

    def test_a_forged_basis_on_a_cycle_across_roots_reads_stale(self):
        """a <-> b across roots, a edited: a verdict whose basis is a's recomputation with b
        fixed at its recorded basis still reads stale, never upstream-stale, because b's
        closure returns to a's own root."""
        def a_text(claim):
            return chip("achip", facts=fact("a", claim=claim, extra=(
                '    relates: [{fact: "bchip@rb#b", relation: same-as}]\n')))

        ra = self.root("ra", {"board-specs.yaml": marker("ra"), "a.spec.yaml": a_text("C a.")})
        rb = self.root("rb", {"board-specs.yaml": marker("rb"), "b.spec.yaml": chip(
            "bchip", facts=fact("b", extra='    relates: [{fact: "achip@ra#a", '
                                           'relation: same-as}]\n'))})
        old_b = rows(status(ra, rb)[1])["bchip@rb#b"]["basis"]
        (ra / "a.spec.yaml").write_text(a_text("C a, edited."))
        import types

        import speccheck

        api = types.SimpleNamespace(validate_file=spec_cli.validate_file,
                                    load_extension=spec_cli.load_extension)
        checker = speccheck.check(api, spec_cli.load_schemas(), [ra, rb])
        # the forgery: a's recomputation with b fixed at its recorded basis, as status() runs it
        fresh = records.Freshness(checker, failed=set(checker._failed_refs))
        rec = next(r for f in checker.files for r in f.records.values()
                   if r.full == "achip@ra#a")
        frontier = fresh.frontier(rec)
        forged = records.compute([rec], fresh.edges, records.local_part,
                                 {t: old_b for t in frontier.values()}, {})[rec][0]
        self.assertNotEqual(forged, fresh.basis(rec)[0])
        self.write(ra, "resources/a.verify.yaml", record("achip", "a.spec.yaml", {
            "a": verdict(forged, upstream={"bchip@rb#b": old_b})}))
        st = rows(status(ra, rb)[1])["achip@ra#a"]
        self.assertEqual((st["status"], st["changed"]), ("stale", []))

    def test_a_reference_into_another_file_of_the_same_root_is_not_upstream(self):
        """The frontier is by root, not by file: a fact resting on a fact in another spec file
        of its own root records no upstream map, and an edit there reads stale."""
        a = self.root("aa", {"board-specs.yaml": marker("aa"),
                             "a.spec.yaml": chip("achip", facts=ref_fact("a1", "dchip#d1")),
                             "d.spec.yaml": chip("dchip", facts=fact("d1"))})
        self.verify_all(a, "achip", "a.spec.yaml", a)
        self.verify_all(a, "dchip", "d.spec.yaml", a)
        self.assertNotIn("upstream", records_of_root(a, "a")["a1"])
        self.assertEqual(check(a, "--require-verified", "pr")[1]["findings"], [])
        (a / "d.spec.yaml").write_text((a / "d.spec.yaml").read_text().replace("C d1.",
                                                                               "C d1, edited."))
        st = rows(status(a)[1])
        self.assertEqual(st["achip@aa#a1"]["status"], "stale")
        code, result = check(a, "--require-verified", "main")
        self.assertIn("fact 'a1': verdict stale", "\n".join(
            f["message"] for f in errors(result)))

    def test_a_name_listed_twice_makes_the_basis_unknown(self):
        """A document, repos entry, assumption or files path listed twice is ambiguous: every
        fact citing it is unknown, even when a record once matched its basis."""
        anchor = ("    support:\n      - class: src\n        anchors: [{repo: linux, "
                  "path: drivers/w.c, lines: [1, 2], symbol: s}]\n")
        cases = {
            "documents": (TRM + TRM.replace("trm.pdf", "trm2.pdf"), LINUX, "", fact("a"),
                          "document 'trm' is listed twice in its file"),
            "repos": (TRM, LINUX + LINUX.replace("/linux", "/linux2"), "",
                      fact("a", support=anchor), "repos entry 'linux' is listed twice"),
            "assumptions": (TRM, LINUX, "assumptions:\n  - {id: s, text: one}\n"
                                        "  - {id: s, text: two}\n",
                            fact("a", extra="    assumes: [s]\n"),
                            "assumption 's' is declared twice in its file"),
            "files": (TRM, LINUX.replace(
                "        - {path: drivers/x.c, license_from: spdx-line}\n",
                "        - {path: drivers/w.c, license_from: notice}\n"), "",
                fact("a", support=anchor), "lists 'drivers/w.c' twice in files"),
        }
        for name, (docs, repos, head, facts, reason) in cases.items():
            with self.subTest(name):
                r = self.root(f"d{len(list(self.tmp.iterdir()))}", {
                    "board-specs.yaml": marker("r", accepts="[GPL-2.0-only]", lic="GPL-2.0-only"),
                    "w.spec.yaml": chip(docs=docs, repos=repos, head=head,
                                        facts=facts + fact("fine"))})
                self.write(r, "resources/w.verify.yaml", record("widgetchip", "w.spec.yaml", {
                    "a": verdict("0" * 64)}))
                st = rows(status(r)[1])
                row = st["widgetchip@r#a"]
                self.assertEqual((row["status"], row["basis"]), ("unknown", None))
                self.assertIsInstance(row["reason"], str)
                self.assertIn(reason, row["reason"])
                self.assertEqual(st["widgetchip@r#fine"]["status"],
                                 "unknown" if name == "documents" else "unverified")

    def test_every_reference_the_check_rejects_makes_the_fact_unknown(self):
        """A layer-order rejection after the verdict, a duplicate in a list and a fact relating
        to itself: each is reported, and each makes the referring fact unknown."""
        up = self.root("up", {"board-specs.yaml": marker("up"),
                              "u.spec.yaml": chip("upchip", facts=fact("mode"))})
        g = self.root("g", {"board-specs.yaml": marker("g"),
                            "x.spec.yaml": chip("xchip", facts=ref_fact("a", "upchip@up#mode"))})
        self.verify_all(g, "xchip", "x.spec.yaml", g, "--context-root", up)
        self.assertEqual(check(g, "--context-root", up, "--require-verified", "pr")[1]
                         ["findings"], [])
        (up / "board-specs.yaml").write_text(marker("up", layer="local"))
        code, result = check(g, "--context-root", up)
        self.assertEqual(code, 1)
        need(errors(result, "which merges after this file's layer public"))
        row = rows(status(g, "--context-root", up)[1])["xchip@g#a"]
        self.assertEqual(row["status"], "unknown")
        self.assertIn("failed the check", row["reason"])
        r = self.root("r", {"board-specs.yaml": marker("r"), "w.spec.yaml": chip(facts=(
            fact("b") + ref_fact("dup", "#b", "widgetchip@r#b")
            + fact("self", extra='    relates: [{fact: "#self", relation: same-as}]\n')
            + ref_fact("p", "#q") + ref_fact("q", "#p")))})
        st = rows(status(r)[1])
        for key in ("dup", "self", "p", "q"):
            self.assertEqual(st[f"widgetchip@r#{key}"]["status"], "unknown", key)
        self.assertEqual(st["widgetchip@r#b"]["status"], "unverified")
        # the license gate: a documents-only root resting on a fact cited from GPL source
        gpl = self.root("gpl", {"board-specs.yaml": marker("gpl", accepts="[GPL-2.0-only]",
                                                           lic="GPL-2.0-only"),
                                "g.spec.yaml": chip("gchip", repos=LINUX, facts=fact("g", support=(
                                    "    support:\n      - class: src\n        anchors: [{repo: "
                                    "linux, path: drivers/w.c, lines: [1, 2], symbol: s}]\n")))})
        docs = self.root("docs", {"board-specs.yaml": marker("docs"),
                                  "d.spec.yaml": chip("dchip", facts=ref_fact("d", "gchip@gpl#g"))})
        code, result = check(docs, "--context-root", gpl)
        need(errors(result, "license gate"))
        row = rows(status(docs, "--context-root", gpl)[1])["dchip@docs#d"]
        self.assertEqual(row["status"], "unknown")

    def test_a_reader_with_the_verdicts_own_verifier_is_not_a_second_reader(self):
        r = self.root("r", {"board-specs.yaml": marker("r"), "w.spec.yaml": chip(
            facts=fact("a", extra="    critical: true\n"))})
        b = self.bases(r)
        for who in ("a model", "A Model"):
            with self.subTest(who):
                self.write(r, "resources/w.verify.yaml", record("widgetchip", "w.spec.yaml", {
                    "a": verdict(b["widgetchip@r#a"],
                                 readers=[{"verifier": who, "verdict": "PASS"}])}))
                for mode, level in ((None, "warning"), ("pr", "error"), ("main", "error")):
                    code, result = check(r, *(["--require-verified", mode] if mode else []))
                    f = only(result["findings"])
                    self.assertEqual(f["level"], level, mode)
                    self.assertIn("a reader with the verdict's own verifier is not a second "
                                  "reader", f["message"])
                self.assertEqual(rows(status(r)[1])["widgetchip@r#a"]["second_reader"],
                                 "missing")

    def test_a_gap_verdict_on_an_instance_or_variant_row_is_an_error(self):
        """Rows have no gap notion (accepted in SF2-3): a row is never a gap, so GAP on one is
        an error, and its other verdicts are not checked against a gap rule."""
        soc = (HDR + "format: 2\nkind: soc\nid: wsoc\nname: W\ntriggers: [wsoc]\n"
               "instances:\n  - {id: uart0, name: uart0, ip: wuart, reg: \"0x1000\", "
               "irq: {kind: SPI, number: 1}, clocks: [],\n"
               '     support: [{class: databook, doc: trm, at: [{section: "2"}]}]}\n'
               "resources:\n  documents:\n" + TRM + "facts:\n" + fact("a"))
        ip = (HDR + "format: 2\nkind: ip\nid: wuart\nname: U\ntriggers: [wuart]\n"
              "resources:\n  documents:\n" + TRM + "facts:\n"
              + fact("u", section="programming-model"))
        r = self.root("r", {"board-specs.yaml": marker("r"), "s.spec.yaml": soc,
                            "u.spec.yaml": ip})
        b = self.bases(r)
        self.write(r, "resources/s.verify.yaml", record("wsoc", "s.spec.yaml", {
            "uart0": verdict(b["wsoc@r#uart0"], "GAP"), "a": verdict(b["wsoc@r#a"])}))
        code, result = check(r)
        self.assertEqual(code, 1)
        f = only(errors(result))
        self.assertIn("verdict GAP for instance 'uart0': GAP is a gap fact's verdict, and an "
                      "instance or variant row is never a gap", f["message"])
        self.assertTrue(f["path"].endswith("resources/s.verify.yaml"))
        self.write(r, "resources/s.verify.yaml", record("wsoc", "s.spec.yaml", {
            "uart0": verdict(b["wsoc@r#uart0"], "UNVERIFIABLE"), "a": verdict(b["wsoc@r#a"])}))
        self.assertEqual(errors(check(r)[1]), [])

    def test_status_text_prints_each_error(self):
        r = self.root("r", {"board-specs.yaml": marker("r"), "w.spec.yaml": chip(facts=fact("a"))})
        b = self.bases(r)
        self.write(r, "resources/w.verify.yaml", record(
            "widgetchip", "w.spec.yaml", {"a": verdict(b["widgetchip@r#a"])},
            summary={"pass": 99, "fail": 0, "unverifiable": 0, "gap": 0, "adjudicate": 0}))
        code, out, _ = run("status", "--stale", r)
        self.assertEqual(code, 1)
        found = [x for x in out.splitlines() if "summary pass: 99" in x]
        self.assertEqual(len(found), 1, out)
        self.assertIn("w.verify.yaml:", found[0])
        self.assertIn("error", found[0])
        self.assertTrue(out.splitlines()[-1].endswith("the check found 1 error(s), 0 warning(s)"))


SCHEMA = json.loads((HERE.parent / "schema" / "spec.schema.json").read_text())["$defs"]


def flow(entry, indent="    "):
    """One list item as a JSON flow mapping (JSON is YAML the strict loader reads)."""
    return f"{indent}- {json.dumps(entry)}\n"


class ReviewRound2(Roots):
    """The fixes of SF2-3's review round 2: a basis hashes every field of a cited entry but the
    named bookkeeping (the user's decision of 2026-10-08), a cited repos entry pinned by a ref
    is unknown, and a citation the check rejects makes the citing fact unknown."""

    DOC = {"name": "trm", "class": "databook", "title": "Widget TRM", "revision": "r1",
           "url": "https://example.invalid/trm.pdf",
           "retrieval": [{"url": "https://example.invalid/r.pdf", "via": "a mirror"}],
           "commit": "b" * 40, "sha256": "a" * 64, "pages": 80, "page_numbering": "printed",
           "access": "public", "verified": "2026-10-01", "fetch": "ok", "note": "n"}
    CITED = {"path": "drivers/w.c", "license_from": "spdx-line", "status": "merged",
             "note": "n"}
    REPO = {"name": "linux", "url": "https://example.invalid/linux", "commit": COMMIT,
            "license": "GPL-2.0-only", "role": "source", "status": "merged",
            "files": [CITED, {"path": "drivers/x.c", "license_from": "spdx-line"}],
            "verified": "2026-10-01", "fetch": "ok", "fetch_via": "git", "note": "n"}
    ASSUMPTION = {"id": "same-silicon", "text": "the parts are the same die",
                  "todo": {"check": "hardware", "text": "check it."}}
    ANCHOR = ("    support:\n      - class: src\n        anchors: [{repo: linux, "
              "path: drivers/w.c, lines: [1, 2], symbol: s}]\n")

    def spec(self, doc=None, repo=None, assumption=None, cite=None):
        """x cites the entry under test (the document, the repos entry and its files entry
        drivers/w.c, or the assumption); y rests on x."""
        if cite == "doc":
            x = fact("x")
        elif cite == "repo":
            x = fact("x", support=self.ANCHOR)
        else:
            x = fact("x", extra="    assumes: [same-silicon]\n")
        return chip(docs=flow(doc or self.DOC), repos=flow(repo or self.REPO),
                    head="assumptions:\n" + flow(assumption or self.ASSUMPTION, "  "),
                    facts=x + ref_fact("y", "#x"))

    def outcomes(self, cite, edits):
        """{name: (x's status, y's status)} after each edit, from a root verified before it."""
        out = {}
        for name, kwargs in edits.items():
            r = self.root(f"k{len(list(self.tmp.iterdir()))}", {
                "board-specs.yaml": marker("r", accepts="[GPL-2.0-only]", lic="GPL-2.0-only"),
                "w.spec.yaml": self.spec(cite=cite)})
            self.verify_all(r, "widgetchip", "w.spec.yaml", r)
            self.assertEqual(check(r, "--require-verified", "pr")[1]["findings"], [], name)
            self.write(r, "w.spec.yaml", self.spec(cite=cite, **kwargs))
            st = rows(status(r)[1])
            out[name] = (st["widgetchip@r#x"]["status"], st["widgetchip@r#y"]["status"])
        return out

    def every_field(self, kind, schema_def, base, arg, cite, changes):
        """Every property of the schema's definition is changed once: a bookkeeping field
        leaves both facts current, any other field stales them (or makes them unknown, where
        the change is also a citation the check rejects). A property the schema gains fails
        here until it is listed, and a field counts unless records.BOOKKEEPING names it."""
        self.assertEqual(set(changes), set(schema_def["properties"]))
        edits = {}
        for field, (value, _) in changes.items():
            entry = json.loads(json.dumps(base))
            if callable(value):
                value(entry)
            else:
                entry[field] = value
            self.assertNotEqual(entry, base, field)
            edits[field] = {arg: entry}
        got = self.outcomes(cite, edits)
        for field, (_, want) in changes.items():
            with self.subTest(f"{kind}: {field}"):
                self.assertEqual(got[field], (want, want))
        self.assertEqual(records.BOOKKEEPING[kind],
                         {k for k, (_, want) in changes.items() if want == "current"})

    def test_every_document_field_but_bookkeeping_counts(self):
        self.every_field("documents", SCHEMA["document"], self.DOC, "doc", "doc", {
            "name": ("trm2", "unknown"),  # the citation no longer names a listed document
            "class": ("standard", "unknown"),  # a databook citation of a standard: rejected
            "title": ("Widget TRM, second edition", "stale"),
            "revision": ("r2", "stale"),
            "url": ("https://example.invalid/trm2.pdf", "stale"),
            "retrieval": ([{"url": "https://example.invalid/r2.pdf", "via": "a mirror"}],
                          "stale"),
            "commit": ("c" * 40, "stale"),
            "sha256": ("d" * 64, "stale"),
            "pages": (81, "stale"),
            "page_numbering": ("pdf", "stale"),
            "access": ("internal", "stale"),
            "cite": (False, "unknown"),  # citing a map-only document: rejected
            "verified": ("2026-10-07", "current"),
            "fetch": ("blocked", "current"),
            "note": ("m", "current"),
        })

    def test_every_repos_field_but_bookkeeping_counts(self):
        def ref(entry):
            del entry["commit"]
            entry["ref"] = "main"

        def files(entry):
            entry["files"][0]["license_from"] = "notice"

        self.every_field("repos", SCHEMA["repo"], self.REPO, "repo", "repo", {
            "name": ("linux2", "unknown"),
            "url": ("https://example.invalid/linux2", "stale"),
            "commit": ("f" * 40, "stale"),
            "ref": (ref, "unknown"),  # pinned by a ref, not a commit (review round 2, S1)
            "license": ("GPL-2.0-only OR MIT", "stale"),
            "role": ("ref", "stale"),
            "status": ("unmerged", "stale"),
            "files": (files, "stale"),
            "verified": ("2026-10-07", "current"),
            "fetch": ("partial", "current"),
            "fetch_via": ("a tarball", "current"),
            "note": ("m", "current"),
        })

    def test_every_files_entry_field_but_bookkeeping_counts(self):
        items = SCHEMA["repo"]["properties"]["files"]["items"]
        changes = {"path": ("drivers/w2.c", "unknown"),  # the cited path is no longer listed
                   "license_from": ("notice", "stale"),
                   "status": ("unmerged", "stale"),
                   "note": ("m", "current")}
        self.assertEqual(set(changes), set(items["properties"]))
        edits = {}
        for field, (value, _) in changes.items():
            repo = json.loads(json.dumps(self.REPO))
            repo["files"][0][field] = value
            edits[field] = {"repo": repo}
        got = self.outcomes("repo", edits)
        for field, (_, want) in changes.items():
            with self.subTest(field):
                self.assertEqual(got[field], (want, want))
        self.assertEqual(records.BOOKKEEPING["files"],
                         {k for k, (_, want) in changes.items() if want == "current"})
        # a files entry the fact does not cite is not part of its basis
        repo = json.loads(json.dumps(self.REPO))
        repo["files"][1]["license_from"] = "notice"
        self.assertEqual(self.outcomes("repo", {"x.c": {"repo": repo}})["x.c"],
                         ("current", "current"))

    def test_every_assumption_field_but_bookkeeping_counts(self):
        self.every_field("assumptions", SCHEMA["assumption"], self.ASSUMPTION, "assumption",
                         "assumption", {
                             "id": ("other-silicon", "unknown"),
                             "text": ("the parts share a die", "stale"),
                             "todo": ({"check": "document", "text": "find it."}, "current"),
                         })

    def test_a_field_no_kind_names_is_hashed(self):
        """An unknown or future field counts by default, in every kind of cited entry: the
        basis reads the entry whole (the schema refuses such a field today, so the record is
        built directly)."""
        import types

        def rec():
            doc = json.loads(json.dumps(self.DOC))
            repo = json.loads(json.dumps(self.REPO))
            data = {"id": "x", "assumes": ["same-silicon"], "support": [
                {"class": "databook", "doc": "trm", "at": [{"section": "1"}]},
                {"class": "src", "anchors": [{"repo": "linux", "path": "drivers/w.c",
                                              "lines": [1, 2], "symbol": "s"}]}]}
            f = types.SimpleNamespace(ambiguous=set(), documents={"trm": (doc, ())},
                                      repos={"linux": (repo, ())},
                                      assumptions={"same-silicon": ("assumptions", 0)},
                                      data={"assumptions": [dict(self.ASSUMPTION)]})
            return types.SimpleNamespace(full="widgetchip@r#x", data=data, file=f)

        base, _ = records.local_part(rec())
        self.assertIsInstance(base, str)
        for kind, add in (("documents", lambda f: f.documents["trm"][0]),
                          ("repos", lambda f: f.repos["linux"][0]),
                          ("files", lambda f: f.repos["linux"][0]["files"][0]),
                          ("assumptions", lambda f: f.data["assumptions"][0])):
            with self.subTest(kind):
                r = rec()
                add(r.file)["future"] = "a field the schema adds later"
                text, _ = records.local_part(r)
                self.assertNotEqual(text, base)
                self.assertIn("a field the schema adds later", text)

    def test_a_cited_repos_entry_pinned_by_a_ref_is_unknown(self):
        """S1: a ref names no fixed tree, so nothing the fact cites through it is fixed; the
        fact and every fact resting on it are unknown, an error under both modes."""
        repo = dict(self.REPO)
        del repo["commit"]
        repo["ref"] = "v1"
        r = self.root("r", {"board-specs.yaml": marker("r", accepts="[GPL-2.0-only]",
                                                       lic="GPL-2.0-only"),
                            "w.spec.yaml": self.spec(repo=repo, cite="repo")})
        st = rows(status(r)[1])
        for key in ("x", "y"):
            row = st[f"widgetchip@r#{key}"]
            self.assertEqual((row["status"], row["basis"]), ("unknown", None), key)
        self.assertIn("repos entry 'linux' pins a ref, not a commit, so what the fact cites "
                      "through it is not fixed", st["widgetchip@r#x"]["reason"])
        for mode in ("pr", "main"):
            code, result = check(r, "--require-verified", mode)
            self.assertEqual(code, 1)
            self.assertEqual(len(errors(result, "freshness unknown")), 2, mode)

    def test_a_citation_the_check_rejects_makes_the_fact_unknown(self):
        """Codex should-fix 2: each citation-level rejection, made after the verdict, makes the
        citing fact unknown and the fact resting on it unknown, with the reason naming the
        rejected citation; the check reports the rejection itself."""
        cases = {
            "cite: false": ({"doc": dict(self.DOC, cite=False)}, "doc", "marked cite: false"),
            "class mismatch": ({"doc": dict(self.DOC, **{"class": "doc"})}, "doc",
                               "a databook citation names document 'trm' of class doc"),
            "license gate": ({"repo": dict(self.REPO, license="MIT")}, "repo",
                             "MIT is not accepted by root"),
        }
        for name, (kwargs, cite, says) in cases.items():
            with self.subTest(name):
                r = self.root(f"c{len(list(self.tmp.iterdir()))}", {
                    "board-specs.yaml": marker("r", accepts="[GPL-2.0-only]",
                                               lic="GPL-2.0-only"),
                    "w.spec.yaml": self.spec(cite=cite)})
                self.verify_all(r, "widgetchip", "w.spec.yaml", r)
                self.write(r, "w.spec.yaml", self.spec(cite=cite, **kwargs))
                code, result = check(r)
                self.assertEqual(code, 1)
                need(errors(result, says))
                st = rows(status(r)[1])
                for key in ("x", "y"):
                    self.assertEqual(st[f"widgetchip@r#{key}"]["status"], "unknown", key)
                self.assertIn("widgetchip@r#x: the citation at facts[0].support[0]",
                              st["widgetchip@r#x"]["reason"])
                self.assertIn("failed the check", st["widgetchip@r#x"]["reason"])
        # locator and anchor rejections, with nothing else changed: a page past the document,
        # backwards lines
        bad = {"page": fact("x", support=('    support: [{class: databook, doc: trm, '
                                          'at: [{page: "92"}]}]\n')),
               "lines": fact("x", support=self.ANCHOR.replace("[1, 2]", "[2, 1]"))}
        for name, x in bad.items():
            with self.subTest(name):
                r = self.root(f"c{len(list(self.tmp.iterdir()))}", {
                    "board-specs.yaml": marker("r", accepts="[GPL-2.0-only]",
                                               lic="GPL-2.0-only"),
                    "w.spec.yaml": chip(docs=flow(self.DOC), repos=flow(self.REPO),
                                        facts=x + ref_fact("y", "#x"))})
                st = rows(status(r)[1])
                for key in ("x", "y"):
                    self.assertEqual(st[f"widgetchip@r#{key}"]["status"], "unknown",
                                     (name, key))

    def test_a_gap_verdict_on_a_variant_row_is_an_error(self):
        """N3: the variant half of the row rule (round 1 tested the instance half)."""
        soc = (HDR + "format: 2\nkind: soc\nid: wsoc\nname: W\ntriggers: [wsoc]\n"
               "instances:\n  - {id: uart0, name: uart0, ip: wuart, reg: \"0x1000\", "
               "irq: {kind: SPI, number: 1}, clocks: [],\n"
               '     support: [{class: databook, doc: trm, at: [{section: "2"}]}]}\n'
               "resources:\n  documents:\n" + TRM + "facts:\n" + fact("s"))
        ip = (HDR + "format: 2\nkind: ip\nid: wuart\nname: U\ntriggers: [wuart]\n"
              "resources:\n  documents:\n" + TRM + "facts:\n"
              + fact("u", section="programming-model"))
        board = (HDR + "format: 2\nkind: board\nid: wboard\nname: W\ntriggers: [wboard]\n"
                 "parts: [wsoc]\ncache: c1\n"
                 "variants:\n  - id: v1\n    name: V1\n    triggers: [wv1]\n    shares: [all]\n"
                 "    differs: x\n"
                 '    support: [{class: databook, doc: trm, at: [{section: "2"}]}]\n'
                 "resources:\n  documents:\n" + TRM + "facts:\n" + fact("a"))
        r = self.root("r", {"board-specs.yaml": marker("r"), "s.spec.yaml": soc,
                            "u.spec.yaml": ip, "b.spec.yaml": board})
        b = self.bases(r)
        self.assertEqual(errors(check(r)[1]), [])
        self.write(r, "resources/b.verify.yaml", record("wboard", "b.spec.yaml", {
            "v1": verdict(b["wboard@r#v1"], "GAP"), "a": verdict(b["wboard@r#a"])}))
        code, result = check(r)
        self.assertEqual(code, 1)
        f = only(errors(result))
        self.assertIn("verdict GAP for variant 'v1': GAP is a gap fact's verdict, and an "
                      "instance or variant row is never a gap", f["message"])
        self.assertTrue(f["path"].endswith("resources/b.verify.yaml"))


class StatusCommand(Roots):
    def test_text_and_exit_codes(self):
        code, out, _ = run("status", VROOT)
        self.assertEqual(code, 1)  # the root has errors (a current FAIL, a malformed record)
        lines = out.splitlines()
        self.assertIn("verify:vok.spec.yaml (vok): resources/vok.verify.yaml: pass 1, fail 0, "
                      "unverifiable 0, gap 0, adjudicate 0", lines)
        self.assertIn("  current         reset  (PASS)", lines)
        self.assertIn("verify:vnone.spec.yaml (vnone): no record", lines)
        self.assertIn("verify:vbad.spec.yaml (vbad): resources/vbad.verify.yaml: invalid", lines)
        self.assertEqual(lines[-1], "2 current, 2 stale, 0 upstream-stale, 2 unverified, "
                                    "0 unknown; the check found 4 error(s), 4 warning(s)")
        code, out, _ = run("status", "--stale", VROOT)
        self.assertNotIn("verify:vok.spec.yaml (vok)", out)
        self.assertNotIn("verify:vfail.spec.yaml (vfail)", out)
        self.assertIn("verify:vstale.spec.yaml (vstale)", out)

    def test_json_shape(self):
        code, result = status(VROOT)
        self.assertEqual(set(result), {"ok", "roots", "errors", "warnings", "specs", "findings"})
        self.assertEqual(result["ok"], False)
        for s in result["specs"]:
            self.assertEqual(set(s), {"path", "root", "spec", "record", "state", "facts"})
            for r in s["facts"]:
                self.assertEqual(set(r), {"key", "ref", "kind", "status", "verdict", "carried",
                                          "basis", "recorded", "upstream", "changed", "reason",
                                          "second_reader"})
                self.assertIn(r["status"], records.STATUSES)

    def test_a_clean_root_exits_0(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = pathlib.Path(tmp) / "r"
            (r / "resources").mkdir(parents=True)
            shutil.copy(VROOT / "board-specs.yaml", r)
            shutil.copy(VROOT / "vok.spec.yaml", r)
            shutil.copy(VROOT / "resources" / "vok.verify.yaml", r / "resources")
            code, result = status(r)
            self.assertEqual((code, result["ok"], result["errors"]), (0, True, 0))

    def test_usage(self):
        for argv in (["status"], ["status", "--json"], ["check", str(VROOT), "--require-verified"],
                     ["check", str(VROOT), "--require-verified", "yes"],
                     ["check", str(VROOT), "--require-verified=PR"],
                     ["status", str(VROOT), "--require-verified", "pr"]):
            code, out, err = run(*argv)
            self.assertEqual(code, 2, argv)
        code, out, _ = run("status", "--json")
        result = json.loads(out)
        self.assertEqual((result["ok"], result["error"]), (False, "usage"))
        self.assertEqual(set(result), {"ok", "error", "roots", "errors", "warnings", "specs",
                                       "findings"})


class WorkedExample(Roots):
    """The design's narrative for its record slice, with the bases filled in."""

    def roots(self):
        docs = self.tmp / "docs"
        gpl = self.tmp / "gpl"
        shutil.copytree(WORKED / "docs", docs)
        shutil.copytree(WORKED / "gpl", gpl)
        return docs, gpl

    def fill(self, gpl, docs):
        b = self.bases(gpl, "--context-root", docs)
        path = gpl / "resources" / "bcm2711.verify.yaml"
        text = path.read_text()
        for key in ("gic-node", "reserved-stub-page"):
            start = text.index(f"  {key}:\n")
            text = (text[:start] + text[start:].replace("0" * 64, b[f"bcm2711@hardware-specs-gpl#{key}"], 1))
        path.write_text(text)

    def test_status_reads_as_the_design_says(self):
        docs, gpl = self.roots()
        self.fill(gpl, docs)
        code, result = status(gpl, "--context-root", docs)
        st = rows(result)
        got = {k.split("#")[1]: (r["status"], r["carried"], r["second_reader"])
               for k, r in st.items()}
        self.assertEqual(got, {
            "gic-node": ("current", True, "missing"),
            "reserved-stub-page": ("current", True, "not-needed"),
            "address-translation-in-the-tree": ("unverified", False, "missing"),
            "tree-describes-low-peripheral-mode": ("unverified", False, "not-needed"),
        })
        stale = {k.split("#")[1] for k in rows(status(gpl, "--context-root", docs, "--stale")[1])}
        self.assertEqual(stale, {"gic-node", "address-translation-in-the-tree",
                                 "tree-describes-low-peripheral-mode"})
        self.assertEqual(st["bcm2711@hardware-specs-gpl#tree-describes-low-peripheral-mode"]
                         ["upstream"], {"bcm2711@hardware-specs-docs#addressing-model":
                                        self.bases(docs)["bcm2711@hardware-specs-docs#"
                                                         "addressing-model"]})
        code, result = check(gpl, "--context-root", docs, "--require-verified", "pr")
        self.assertEqual(sorted(f["message"].split(":")[0] for f in errors(result)),
                         ["fact 'address-translation-in-the-tree'", "fact 'gic-node'",
                          "fact 'tree-describes-low-peripheral-mode'"])

    def test_a_docs_edit_to_addressing_model_stales_only_the_inference(self):
        docs, gpl = self.roots()
        self.verify_all(gpl, "bcm2711", "bcm2711.spec.yaml", gpl, "--context-root", docs)
        self.assertEqual(check(gpl, "--context-root", docs, "--require-verified", "pr")[1]
                         ["findings"], [])
        spec = docs / "bcm2711.spec.yaml"
        text = spec.read_text()
        anchor = text.index("  - id: addressing-model")
        claim = text.index("    claim:", anchor)
        spec.write_text(text[:claim] + "    note: an edit\n" + text[claim:])
        for mode, level, code_want in (("main", "warning", 0), ("pr", "error", 1)):
            code, result = check(gpl, "--context-root", docs, "--require-verified", mode)
            self.assertEqual(code, code_want, result["findings"])
            f = only(result["findings"])
            self.assertEqual(f["level"], level)
            self.assertIn("fact 'tree-describes-low-peripheral-mode': upstream-stale: "
                          "bcm2711@hardware-specs-docs#addressing-model changed", f["message"])


if __name__ == "__main__":
    unittest.main()
