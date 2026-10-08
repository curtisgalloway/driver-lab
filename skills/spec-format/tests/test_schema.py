#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for the format 2 schemas through `spec.py validate`.

Run in the pinned environment:
  uv run --with-requirements skills/spec-format/requirements.txt \
    python3 -m unittest discover -s skills/spec-format/tests -v

Valid fixtures: one file per kind under fixtures/valid (plus a root marker with a test
extension fragment and a verification record), and the design's worked example under
fixtures/worked-example. Invalid inputs are built here from small valid documents, one rule
broken per case, written to a temporary file and validated; each must fail with the expected
message, and every base document must pass, so a case fails only for the rule it breaks.
"""

import contextlib
import copy
import io
import json
import pathlib
import re
import sys
import tempfile
import unittest

import yaml

HERE = pathlib.Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
FIX = HERE / "fixtures"
VALID = FIX / "valid"
WORKED = FIX / "worked-example"
DESIGN = HERE.parents[2] / "docs" / "SPEC-FORMAT-V2.md"
sys.path.insert(0, str(SCRIPTS))
import spec as spec_cli  # noqa: E402

DROP = object()
COMMIT = "1a2b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d"
SHA = "1218036a6a0562504adedd37088e5136036a3099cf8581832e0c7353d7256cbd"
FRAGMENT = {
    "type": "object",
    "required": ["observer"],
    "properties": {"observer": {"type": "string", "pattern": "\\S"}},
}


def run(argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        code = spec_cli.main(argv)
    text = out.getvalue()
    return code, (json.loads(text) if "--json" in argv else text)


class _NoAliases(yaml.SafeDumper):
    def ignore_aliases(self, data):
        return True


def dump(data) -> str:
    return yaml.dump(data, Dumper=_NoAliases, sort_keys=False, allow_unicode=True, width=1000)


def apply(base: dict, changes: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in changes.items():
        if v is DROP:
            out.pop(k, None)
        else:
            out[k] = v
    return out


READ = {
    "databook": {"class": "databook", "doc": "trm", "at": [{"section": "1.2", "page": "4"}]},
    "standard": {"class": "standard", "doc": "std", "at": [{"clause": "4"}]},
    "doc": {"class": "doc", "doc": "web", "at": [{"heading": "Setup"}]},
    "rtl": {"class": "rtl", "design": "uart", "revision": "r1p0", "module": "rx",
            "anchors": [{"repo": "linux", "path": "rtl/uart.v", "lines": [1, 2]}]},
    "DT": {"class": "DT",
           "anchors": [{"repo": "linux", "path": "arch/x.dtsi", "lines": [10, 11]}]},
    "src": {"class": "src", "anchors": [{"repo": "linux", "path": "drivers/x.c",
                                         "lines": [5, 5], "symbol": "X_EN"}]},
    "hardware": {"class": "hardware", "board": "rev B", "method": "read it", "date": "2026-10-01"},
    "emulated": {"class": "emulated", "model": "qemu", "version": "9.1", "runs": ["r1"]},
    "press": {"class": "press", "title": "A review", "url": "https://example.invalid/r"},
    "inference": {"class": "inference", "premises": [{"fact": "#f0"}], "derivation": "so"},
    "source-observed": {"class": "source-observed", "observer": "someone"},
}
# Required fields per class, as the design's provenance-class table states them.
REQUIRED = {
    "databook": ["doc", "at"], "standard": ["doc", "at"], "doc": ["doc", "at"],
    "rtl": ["design", "revision", "module", "anchors"], "DT": ["anchors"], "src": ["anchors"],
    "hardware": ["board", "method", "date"], "emulated": ["model", "version", "runs"],
    "press": ["title", "url"], "inference": ["premises", "derivation"],
    "source-observed": ["observer"],
}
# A field another class has and this one does not.
FOREIGN = {
    "databook": "anchors", "standard": "anchors", "doc": "anchors", "rtl": "symbol",
    "DT": "doc", "src": "note", "hardware": "url", "emulated": "doc", "press": "anchors",
    "inference": "doc", "source-observed": "doc",
}
NEEDS_TODO = {"press", "inference", "emulated", "source-observed"}
TODO = {"check": "hardware", "text": "check it on a board"}


def fact(**changes) -> dict:
    return apply({"id": "f1", "section": "quick-facts", "title": "T", "claim": "C.",
                  "support": [copy.deepcopy(READ["databook"])]}, changes)


RESOURCES = {
    "documents": [
        {"name": "trm", "class": "databook", "title": "TRM", "url": "https://example.invalid/trm"},
        {"name": "std", "class": "standard", "title": "Std", "url": "https://example.invalid/std"},
        {"name": "web", "class": "doc", "title": "Web", "url": "https://example.invalid/web"},
    ],
    "repos": [
        {"name": "linux", "url": "https://example.invalid/linux", "commit": COMMIT,
         "license": "GPL-2.0-only", "files": [{"path": "drivers/x.c", "license_from": "spdx-line"}]},
    ],
}


def soc(facts=None, **changes) -> dict:
    base = {"format": 2, "kind": "soc", "id": "w", "name": "W", "triggers": ["w"],
            "instances": [], "resources": copy.deepcopy(RESOURCES),
            "facts": facts if facts is not None else [fact()]}
    return apply(base, changes)


def instance(**changes) -> dict:
    return apply({"id": "uart0", "name": "uart0", "ip": "uart", "reg": "0x7e201000",
                  "irq": {"kind": "SPI", "number": 1}, "clocks": [],
                  "support": [copy.deepcopy(READ["databook"])]}, changes)


def repo(**changes) -> dict:
    return apply(RESOURCES["repos"][0], changes)


def document(**changes) -> dict:
    return apply(RESOURCES["documents"][0], changes)


def with_repo(**changes) -> dict:
    return soc(resources={"repos": [repo(**changes)]})


def with_document(**changes) -> dict:
    return soc(resources={"documents": [document(**changes)]})


def board(**changes) -> dict:
    return apply({"format": 2, "kind": "board", "id": "wb", "name": "WB", "triggers": ["wb"],
                  "parts": ["w"], "cache": "wb-resources", "facts": [fact()]}, changes)


def ip(**changes) -> dict:
    return apply({"format": 2, "kind": "ip", "id": "u", "name": "U", "triggers": ["u"],
                  "resources": copy.deepcopy(RESOURCES),
                  "facts": [fact(section="programming-model")]}, changes)


def chip(**changes) -> dict:
    return apply({"format": 2, "kind": "chip", "id": "c", "name": "C", "triggers": ["c"],
                  "facts": [fact()]}, changes)


def overlay(**changes) -> dict:
    return apply({"format": 2, "kind": "overlay", "overlays": "w", "facts": [fact()]}, changes)


def facts_file(**changes) -> dict:
    return apply({"format": 2, "kind": "facts", "resources": copy.deepcopy(RESOURCES),
                  "facts": [fact(section="facts", title=DROP)]}, changes)


def marker(**changes) -> dict:
    return apply({"format": 2, "layer": "public", "name": "r"}, changes)


def verdict(**changes) -> dict:
    return apply({"basis": SHA, "verdict": "PASS", "date": "2026-10-08", "verifier": "v",
                  "contrary_evidence": "none-found", "citation_precision": "exact"}, changes)


def record(verdicts=None, **changes) -> dict:
    return apply({"format": 2, "spec": "w", "spec_file": "w.spec.yaml", "spec_sha256": SHA,
                  "canonical": "fact-v1", "sources": [{"name": "linux", "commit": COMMIT}],
                  "summary": {"pass": 1, "fail": 0, "unverifiable": 0, "gap": 0,
                              "adjudicate": 0},
                  "verdicts": verdicts if verdicts is not None else {"f1": verdict()}}, changes)


class Validator(unittest.TestCase):
    def validate(self, data, name="w.spec.yaml", fragment=None, raw=None):
        """Write `data` and validate it; with `fragment`, under a root naming it."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            argv = ["validate", "--json"]
            if fragment is not None:
                (tmp / "frag.json").write_text(json.dumps(fragment), encoding="utf-8")
                (tmp / "board-specs.yaml").write_text(dump(marker(extensions=[
                    {"class": "source-observed", "schema": "frag.json"}])), encoding="utf-8")
                argv += ["--root", str(tmp)]
            path = tmp / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(raw if raw is not None else dump(data), encoding="utf-8")
            code, result = run(argv + [str(path)])
        return code, result

    def assert_valid(self, data, **kw):
        code, result = self.validate(data, **kw)
        self.assertEqual(code, 0, json.dumps(result["findings"], indent=1))

    def assert_invalid(self, data, expected: str, **kw):
        code, result = self.validate(data, **kw)
        messages = [f["message"] for f in result["findings"]]
        self.assertEqual(code, 1, f"expected a failure mentioning {expected!r}")
        self.assertTrue(any(expected in m for m in messages),
                        f"{expected!r} not in {json.dumps(messages, indent=1)}")
        for f in result["findings"]:
            self.assertGreaterEqual(f["line"], 1)
            self.assertGreaterEqual(f["column"], 1)


class ValidFixtures(Validator):
    def test_one_valid_file_per_kind(self):
        files = sorted(VALID.glob("*.spec.yaml")) + sorted(VALID.glob("*.facts.yaml"))
        kinds = set()
        for path in files:
            kinds.add(yaml.safe_load(path.read_text(encoding="utf-8"))["kind"])
        self.assertEqual(kinds, {"board", "soc", "chip", "ip", "overlay", "facts"})
        record = VALID / "resources" / "widget-soc.verify.yaml"
        code, result = run(["validate", "--json", "--root", str(VALID),
                            str(VALID / "board-specs.yaml"), str(record)]
                           + [str(p) for p in files])
        self.assertEqual(code, 0, json.dumps(result["findings"], indent=1))
        self.assertEqual(len(result["files"]), len(files) + 2)

    def test_every_support_class_appears_in_the_valid_fixtures(self):
        text = "".join(p.read_text(encoding="utf-8") for p in VALID.glob("*.yaml"))
        for cls in READ:
            self.assertRegex(text, rf"class: {re.escape(cls)}\b")

    def test_worked_example_validates(self):
        files = sorted(str(p) for p in WORKED.rglob("*.yaml"))
        self.assertEqual(len(files), 4)
        code, result = run(["validate", "--json"] + files)
        self.assertEqual(code, 0, json.dumps(result["findings"], indent=1))

    def test_worked_example_matches_the_design(self):
        """The fixtures are the design's YAML blocks, with <64 hex> filled in the record."""
        design = DESIGN.read_text(encoding="utf-8")
        heads = {
            "docs/bcm2711.spec.yaml": "### `hardware-specs-docs/specs/bcm2711.spec.yaml`",
            "permissive/bcm2711.spec.yaml":
                "### `hardware-specs-permissive/specs/bcm2711.spec.yaml`",
            "gpl/bcm2711.spec.yaml": "### `hardware-specs-gpl/specs/bcm2711.spec.yaml`",
            "gpl/resources/bcm2711.verify.yaml":
                "### `hardware-specs-gpl/specs/resources/bcm2711.verify.yaml`",
        }
        for rel, head in heads.items():
            start = design.index("```yaml\n", design.index(head)) + len("```yaml\n")
            block = design[start:design.index("\n```", start)] + "\n"
            block = block.replace("<64 hex>", "0" * 64)
            self.assertEqual((WORKED / rel).read_text(encoding="utf-8"), block, rel)


class Kinds(Validator):
    def test_bases_are_valid(self):
        for name, data in [("w.spec.yaml", soc()), ("w.spec.yaml", board()),
                           ("w.spec.yaml", ip()), ("w.spec.yaml", chip()),
                           ("w.spec.yaml", overlay()), ("w.facts.yaml", facts_file())]:
            with self.subTest(data["kind"]):
                self.assert_valid(data, name=name)

    def test_keys_by_kind(self):
        cases = [
            ("format 1", soc(format=1), "format"),
            ("format as a string", soc(format="2"), "format"),
            ("peripheral not yet", soc(kind="peripheral"), "kind"),
            ("unknown top-level key", soc(extra="x"), "unknown key 'extra'"),
            ("soc without instances", soc(instances=DROP), "'instances' is a required"),
            ("soc with parts", soc(parts=["x"]), "unknown key 'parts'"),
            ("soc with variants", soc(variants=[]), "unknown key 'variants'"),
            ("soc without triggers", soc(triggers=DROP), "'triggers' is a required"),
            ("empty triggers", soc(triggers=[]), "should be non-empty"),
            ("blank trigger", soc(triggers=[" "]), "does not match"),
            ("duplicate triggers", soc(triggers=["a", "a"]), "non-unique"),
            ("board without parts", board(parts=DROP), "'parts' is a required"),
            ("board without cache", board(cache=DROP), "'cache' is a required"),
            ("board with instances", board(instances=[]), "unknown key 'instances'"),
            ("board with overlays", board(overlays="x"), "unknown key 'overlays'"),
            ("board with empty parts", board(parts=[]), "should be non-empty"),
            ("ip without resources", ip(resources=DROP), "'resources' is a required"),
            ("ip with instances", ip(instances=[]), "unknown key 'instances'"),
            ("chip with variants", chip(variants=[]), "unknown key 'variants'"),
            ("overlay with id", overlay(id="w"), "unknown key 'id'"),
            ("overlay with triggers", overlay(triggers=["w"]), "unknown key 'triggers'"),
            ("overlay with cache", overlay(cache="w"), "unknown key 'cache'"),
            ("overlay without overlays", overlay(overlays=DROP), "'overlays' is a required"),
            ("id not normalized", soc(id="Tensor G5"), "does not match"),
            ("alias not an id", soc(aliases=["Bad_Alias"]), "does not match"),
            ("blank orientation", soc(orientation="  "), "does not match"),
            ("resources unknown list", soc(resources={"docs": []}), "unknown key 'docs'"),
        ]
        for label, data, expected in cases:
            with self.subTest(label):
                self.assert_invalid(data, expected)

    def test_facts_file(self):
        self.assert_invalid(facts_file(triggers=["x"]), "unknown key 'triggers'",
                            name="w.facts.yaml")
        self.assert_invalid(facts_file(resources=DROP), "'resources' is a required",
                            name="w.facts.yaml")
        self.assert_invalid(facts_file(facts=[fact()]), "'facts' was expected",
                            name="w.facts.yaml")
        self.assert_invalid(facts_file(), "kind: facts belongs in a *.facts.yaml file")
        self.assert_invalid(soc(), "a *.facts.yaml file holds kind: facts",
                            name="w.facts.yaml")

    def test_sections_by_kind(self):
        self.assert_invalid(soc(facts=[fact(section="standards")]), "is not one of")
        self.assert_invalid(ip(facts=[fact(section="quick-facts")]), "is not one of")
        self.assert_invalid(board(facts=[fact(section="registers")]), "is not one of")
        self.assert_invalid(overlay(facts=[fact(section="facts")]), "is not one of")
        self.assert_valid(overlay(facts=[fact(section="programming-model")]))
        self.assert_invalid(soc(facts=[fact(title=DROP)]), "'title' is a required")
        self.assert_invalid(overlay(facts=[fact(title=DROP)]), "'title' is a required")
        self.assert_valid(facts_file(facts=[fact(section="facts", title=DROP)]),
                          name="w.facts.yaml")


class Facts(Validator):
    def test_fact_rules(self):
        cases = [
            ("unknown key", fact(verdict="PASS"), "unknown key 'verdict'"),
            ("no claim", fact(claim=DROP), "'claim' is a required"),
            ("blank claim", fact(claim=" \n "), "does not match"),
            ("empty claim", fact(claim=""), "does not match"),
            ("no id", fact(id=DROP), "'id' is a required"),
            ("id with a dot", fact(id="a.b"), "does not match"),
            ("id with a capital", fact(id="Addressing"), "does not match"),
            ("no section", fact(section=DROP), "'section' is a required"),
            ("critical false", fact(critical=False), "True was expected"),
            ("critical as a word", fact(critical="yes"), "True was expected"),
            ("gap without todo", fact(support=DROP), "a gap (no support) must carry a todo"),
            ("empty support", fact(support=[]), "should be non-empty"),
            ("support not a list", fact(support=READ["databook"]), "is not of type 'array'"),
            ("empty assumes", fact(assumes=[]), "should be non-empty"),
            ("assumes written as a reference", fact(assumes=["#a"]), "does not match"),
            ("empty scope", fact(scope={}), "should be non-empty"),
            ("unknown scope key", fact(scope={"socs": ["x"]}), "unknown key 'socs'"),
            ("empty scope list", fact(scope={"boards": []}), "should be non-empty"),
            ("empty relates", fact(relates=[]), "should be non-empty"),
            ("bad reference", fact(relates=[{"fact": "#", "relation": "refines"}]),
             "does not match"),
            ("reference without #", fact(relates=[{"fact": "f2", "relation": "refines"}]),
             "does not match"),
            ("reference with two roots",
             fact(relates=[{"fact": "a@b@c#d", "relation": "refines"}]), "does not match"),
            ("unknown relation", fact(relates=[{"fact": "#f2", "relation": "supports"}]),
             "is not one of"),
            ("todo without text", fact(todo={"check": "hardware"}), "'text' is a required"),
            ("todo unknown check", fact(todo={"check": "board", "text": "x"}), "is not one of"),
            ("todo unknown key", fact(todo=dict(TODO, how="x")), "unknown key 'how'"),
            ("blank note", fact(note=" "), "does not match"),
            ("data payload not yet", fact(data={"register": {}}), "unknown key 'data'"),
            ("requirement not yet", fact(requirement="hw-required"),
             "unknown key 'requirement'"),
        ]
        for label, f, expected in cases:
            with self.subTest(label):
                self.assert_invalid(soc(facts=[f]), expected)

    def test_gap_fact_and_optional_fields(self):
        self.assert_valid(soc(facts=[fact(support=DROP, todo=TODO)]))
        self.assert_valid(soc(facts=[fact(
            critical=True, assumes=["a"], scope={"boards": ["b"]}, note="n",
            relates=[{"fact": "w@r.x-y#f2", "relation": "same-as"}],
            todo=dict(TODO, method="a method"))],
            assumptions=[{"id": "a", "text": "t", "todo": TODO}]))

    def test_conflicts(self):
        good = {"reading": "r", "support": [READ["doc"]], "resolution": "x",
                "assumption": "y", "decided": {"by": "user", "date": "2026-10-08"}}
        self.assert_valid(soc(facts=[fact(conflicts=[good])]))
        self.assert_valid(soc(facts=[fact(conflicts=[{"reading": "r",
                                                      "support": [READ["press"]]}])]))
        cases = [
            ("resolution without decided", apply(good, {"decided": DROP}), "'decided' is"),
            ("decided without resolution",
             apply(good, {"resolution": DROP, "assumption": DROP}), "'resolution' is"),
            ("assumption without resolution",
             apply(good, {"resolution": DROP, "decided": DROP}), "'resolution' is"),
            ("no support", apply(good, {"support": DROP}), "'support' is a required"),
            ("inference support", apply(good, {"support": [READ["inference"]]}),
             "never another inference"),
            ("unknown key", apply(good, {"by": "x"}), "unknown key 'by'"),
            ("bad date", apply(good, {"decided": {"by": "u", "date": "2026-13-01"}}),
             "does not match"),
        ]
        for label, conflict, expected in cases:
            with self.subTest(label):
                self.assert_invalid(soc(facts=[fact(conflicts=[conflict])]), expected)

    def test_assumptions(self):
        self.assert_invalid(soc(assumptions=[{"id": "a"}]), "'text' is a required")
        self.assert_invalid(soc(assumptions=[{"id": "A", "text": "t"}]), "does not match")
        self.assert_invalid(soc(assumptions=[{"id": "a", "text": "t", "x": 1}]),
                            "unknown key 'x'")


class SupportClasses(Validator):
    def check(self, cls, entry, expected=None):
        f = fact(support=[entry])
        if cls in NEEDS_TODO:
            f["todo"] = TODO
        if cls == "emulated":
            f["support"].append(copy.deepcopy(READ["databook"]))
        frag = FRAGMENT if cls == "source-observed" else None
        if expected is None:
            self.assert_valid(soc(facts=[f]), fragment=frag)
        else:
            self.assert_invalid(soc(facts=[f]), expected, fragment=frag)

    def test_each_class_valid(self):
        for cls, entry in READ.items():
            with self.subTest(cls):
                self.check(cls, entry)

    def test_each_class_rejects_a_missing_required_field(self):
        for cls, fields in REQUIRED.items():
            for field in fields:
                with self.subTest(f"{cls} without {field}"):
                    entry = apply(READ[cls], {field: DROP})
                    self.check(cls, entry, "is a required property")

    def test_each_class_rejects_an_unknown_field(self):
        for cls in READ:
            with self.subTest(f"{cls} with bogus"):
                self.check(cls, dict(READ[cls], bogus="x"), "unknown key 'bogus'")
            with self.subTest(f"{cls} with {FOREIGN[cls]}"):
                self.check(cls, dict(READ[cls], **{FOREIGN[cls]: "x"}),
                           f"unknown key '{FOREIGN[cls]}'")

    def test_class_names(self):
        for bad in ["Src", "SRC", "dt", "impl", "ref", "src ", "", "inferred"]:
            with self.subTest(bad):
                self.check("src", dict(READ["src"], **{"class": bad}), "is not one of")
        self.check("src", apply(READ["src"], {"class": DROP}), "'class' is a required")

    def test_combination_rules(self):
        cases = [
            ("press without todo", [READ["press"]], None, "require a todo"),
            ("inference without todo", [READ["inference"]], None, "require a todo"),
            ("emulated without todo", [READ["emulated"], READ["databook"]], None,
             "require a todo"),
            ("inference with a sibling", [READ["inference"], READ["databook"]], TODO,
             "an inference stands alone"),
            ("two inferences", [READ["inference"], READ["inference"]], TODO,
             "an inference stands alone"),
            ("emulated alone", [READ["emulated"]], TODO, "emulated never stands alone"),
            ("two emulated", [READ["emulated"], READ["emulated"]], TODO,
             "emulated never stands alone"),
        ]
        for label, support, todo, expected in cases:
            with self.subTest(label):
                f = fact(support=copy.deepcopy(support))
                if todo:
                    f["todo"] = todo
                self.assert_invalid(soc(facts=[f]), expected)
        self.assert_valid(soc(facts=[fact(support=[READ["emulated"], READ["press"]],
                                          todo=TODO)]))

    def test_no_repeated_entries(self):
        """A repeated entry is a second spelling of the list without it."""
        db, src = READ["databook"], READ["src"]
        cases = [
            ("support", fact(support=[db, db])),
            ("locators", fact(support=[dict(db, at=[{"section": "1"}, {"section": "1"}])])),
            ("anchors", fact(support=[dict(src, anchors=src["anchors"] * 2)])),
            ("relates", fact(relates=[{"fact": "#f2", "relation": "refines"}] * 2)),
            ("premises", fact(support=[dict(READ["inference"],
                                            premises=[{"fact": "#f0"}] * 2)], todo=TODO)),
        ]
        for label, f in cases:
            with self.subTest(label):
                self.assert_invalid(soc(facts=[f]), "has non-unique elements")

    def test_locators(self):
        db = READ["databook"]
        cases = [
            ("heading alone in a databook", apply(db, {"at": [{"heading": "x"}]}),
             "a databook locator needs"),
            ("empty locator", apply(db, {"at": [{}]}), "should be non-empty"),
            ("no locators", apply(db, {"at": []}), "should be non-empty"),
            ("page as an integer", apply(db, {"at": [{"page": 92}]}),
             "92 was read as an integer"),
            ("page and pages", apply(db, {"at": [{"page": "1", "pages": ["1", "2"]}]}),
             "should not be valid"),
            ("one-item pages", apply(db, {"at": [{"pages": ["1"]}]}), "is too short"),
            ("three-item pages", apply(db, {"at": [{"pages": ["1", "2", "3"]}]}),
             "at most 2 items"),
            ("unknown locator key", apply(db, {"at": [{"line": "4"}]}), "unknown key 'line'"),
            ("blank section", apply(db, {"at": [{"section": ""}]}), "does not match"),
            ("doc name with a capital", apply(db, {"doc": "TRM"}), "does not match"),
        ]
        for label, entry, expected in cases:
            with self.subTest(label):
                self.check("databook", entry, expected)
        self.check("doc", apply(READ["doc"], {"at": [{"heading": "only"}]}))

    def test_anchors(self):
        src = READ["src"]["anchors"][0]
        cases = [
            ("lines without symbol", apply(src, {"symbol": DROP}), "'symbol' is a required"),
            ("symbol without lines", apply(src, {"lines": DROP}), "'lines' is a required"),
            ("search with lines", dict(src, search="s"), "a search anchor carries no"),
            ("search with symbol", {"repo": "linux", "path": "d/", "search": "s",
                                    "symbol": "x"}, "a search anchor carries no"),
            ("search with comment", {"repo": "linux", "path": "d/", "search": "s",
                                     "comment": True}, "a search anchor carries no"),
            ("blank search", {"repo": "linux", "path": "d/", "search": " "}, "does not match"),
            ("comment false", dict(src, comment=False), "True was expected"),
            ("line zero", dict(src, lines=[0, 1]), "less than the minimum"),
            ("one line number", dict(src, lines=[5]), "is too short"),
            ("three line numbers", dict(src, lines=[5, 6, 7]), "at most 2 items"),
            ("line as a string", dict(src, lines=["5", "6"]), "is not of type 'integer'"),
            ("absolute path", dict(src, path="/etc/passwd"), "does not match"),
            ("dot-dot path", dict(src, path="a/../b.c"), "does not match"),
            ("leading dot-dot", dict(src, path="../b.c"), "does not match"),
            ("dot segment", dict(src, path="a/./b.c"), "does not match"),
            ("empty segment", dict(src, path="a//b.c"), "does not match"),
            ("option-like path", dict(src, path="-rf"), "does not match"),
            ("path with a space", dict(src, path="a b.c"), "does not match"),
            ("empty path", dict(src, path=""), "does not match"),
            ("blank symbol", dict(src, symbol=" "), "does not match"),
            ("repo name with a slash", dict(src, repo="a/b"), "does not match"),
            ("stale with a short commit", dict(src, stale={"was": "abc123"}), "does not match"),
            ("unknown anchor key", dict(src, node="x"), "unknown key 'node'"),
        ]
        for label, anchor, expected in cases:
            with self.subTest(label):
                self.check("src", {"class": "src", "anchors": [anchor]}, expected)
        self.check("src", {"class": "src", "anchors": []}, "should be non-empty")
        self.check("src", {"class": "src", "anchors": [dict(src, stale={"was": COMMIT})]})
        dt = READ["DT"]["anchors"][0]
        dt_cases = [
            (".dtsi with node only", apply(dt, {"lines": DROP, "node": "soc"}),
             "'lines' is a required"),
            (".dts with node only", apply(dt, {"lines": DROP, "node": "soc",
                                               "path": "a/b.dts"}), "'lines' is a required"),
            ("neither lines nor node", apply(dt, {"lines": DROP, "path": "a/b.dtb"}),
             "is not valid under any"),
            ("search in DT", dict(dt, search="s"), "unknown key 'search'"),
        ]
        for label, anchor, expected in dt_cases:
            with self.subTest(label):
                self.check("DT", {"class": "DT", "anchors": [anchor]}, expected)
        self.check("DT", {"class": "DT", "anchors": [
            {"repo": "linux", "path": "fw/b.dtb", "node": "/soc"}]})
        rtl = READ["rtl"]
        self.check("rtl", apply(rtl, {"anchors": DROP}), "is not valid under any")
        self.check("rtl", apply(rtl, {"doc": "trm"}), "'at' is a dependency")
        self.check("rtl", apply(rtl, {"at": [{"section": "1"}]}), "'doc' is a dependency")
        self.check("rtl", apply(rtl, {"anchors": DROP, "doc": "trm", "at": [{"section": "1"}]}))
        self.check("rtl", apply(rtl, {"anchors": [{"repo": "linux", "path": "r.v"}]}),
                   "'lines' is a required")

    def test_other_class_fields(self):
        hw = READ["hardware"]
        self.check("hardware", dict(hw, date="2026-10-8"), "does not match")
        self.check("hardware", dict(hw, runs=[]), "should be non-empty")
        em = READ["emulated"]
        self.check("emulated", apply(em, {"runs": DROP, "observation": "#f2"}))
        self.check("emulated", apply(em, {"runs": DROP, "observation": "f2"}), "does not match")
        self.check("emulated", apply(em, {"version": 9}), "quote it")
        pr = READ["press"]
        self.check("press", dict(pr, url="http://example.invalid/r"), "does not match")
        self.check("press", dict(pr, date="yesterday"), "does not match")
        inf = READ["inference"]
        self.check("inference", dict(inf, premises=[]), "should be non-empty")
        self.check("inference", dict(inf, confidence="certain"), "is not one of")

    def test_premises(self):
        cases = [
            ("fact and states", {"fact": "#f0", "states": "s", "support": [READ["doc"]]},
             "is valid under each of"),
            ("fact and assumption", {"fact": "#f0", "assumption": "a"},
             "is valid under each of"),
            ("nothing", {"uses": "x"}, "is not valid under any"),
            ("states without support", {"states": "s"}, "'support' is a dependency"),
            ("support without states", {"fact": "#f0", "support": [READ["doc"]]},
             "'states' is a dependency"),
            ("uses without fact", {"states": "s", "support": [READ["doc"]], "uses": "u"},
             "'fact' is a dependency"),
            ("inference in a premise",
             {"states": "s", "support": [READ["inference"]]}, "never another inference"),
            ("empty premise support", {"states": "s", "support": []}, "should be non-empty"),
            ("unknown premise key", {"fact": "#f0", "why": "x"}, "unknown key 'why'"),
            ("assumption as a reference", {"assumption": "#a"}, "does not match"),
            ("bad fact reference", {"fact": "f0"}, "does not match"),
        ]
        for label, premise, expected in cases:
            with self.subTest(label):
                entry = {"class": "inference", "premises": [premise], "derivation": "d"}
                self.check("inference", entry, expected)
        self.check("inference", {"class": "inference", "derivation": "d", "premises": [
            {"fact": "a@b#c", "uses": "u"}, {"assumption": "a"},
            {"states": "s", "support": [READ["src"], READ["emulated"], READ["press"]]}]})


class SourceObserved(Validator):
    def entry_fact(self, entry):
        return soc(facts=[fact(support=[entry], todo=TODO)])

    def test_without_root_it_is_refused(self):
        self.assert_invalid(self.entry_fact(READ["source-observed"]),
                            "needs the extension's schema fragment")

    def test_fragment_fields(self):
        f = self.entry_fact(READ["source-observed"])
        self.assert_valid(f, fragment=FRAGMENT)
        self.assert_invalid(self.entry_fact({"class": "source-observed", "observer": 3}),
                            "was read as an integer", fragment=FRAGMENT)
        self.assert_invalid(soc(facts=[fact(support=[READ["source-observed"]])]),
                            "require a todo", fragment=FRAGMENT)

    def test_bad_fragments(self):
        cases = [
            ("opens the record", dict(FRAGMENT, additionalProperties=True),
             "not allowed in a fragment: additionalProperties"),
            ("unevaluated true", dict(FRAGMENT, unevaluatedProperties=True),
             "not allowed in a fragment"),
            ("pattern properties", dict(FRAGMENT, patternProperties={".*": {}}),
             "not allowed in a fragment"),
            ("a ref", dict(FRAGMENT, properties={"observer": {"$ref": "#/x"}}),
             "$ref at properties/observer not allowed"),
            ("an id", dict(FRAGMENT, properties={"observer": {"$id": "urn:x"}}),
             "$id at properties/observer not allowed"),
            ("a class field", dict(FRAGMENT, properties={"class": {"const": "x"}}),
             "field name 'class' not allowed"),
            ("no type", apply(FRAGMENT, {"type": DROP}), 'declares "type": "object"'),
            ("no properties", apply(FRAGMENT, {"properties": DROP, "required": DROP}),
             "non-empty properties"),
            ("required undeclared", dict(FRAGMENT, required=["x"]), "required lists only"),
            ("not a schema", dict(FRAGMENT, properties={"observer": {"type": "strung"}}),
             "not a valid JSON Schema"),
            ("an allOf", dict(FRAGMENT, allOf=[{"additionalProperties": True}]),
             "not allowed in a fragment: allOf"),
        ]
        for label, frag, expected in cases:
            with self.subTest(label):
                code, result = self.validate(self.entry_fact(READ["source-observed"]),
                                             fragment=frag)
                messages = [f["message"] for f in result["findings"]]
                self.assertEqual(code, 1)
                self.assertTrue(any(expected in m for m in messages), messages)

    def test_fragment_outside_the_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            (tmp / "root").mkdir()
            (tmp / "frag.json").write_text(json.dumps(FRAGMENT), encoding="utf-8")
            (tmp / "root" / "board-specs.yaml").write_text(dump(marker(extensions=[
                {"class": "source-observed", "schema": "../frag.json"}])), encoding="utf-8")
            code, result = run(["validate", "--json", str(tmp / "root" / "board-specs.yaml")])
            self.assertEqual(code, 1)
            (tmp / "root" / "link.json").symlink_to(tmp / "frag.json")
            (tmp / "root" / "board-specs.yaml").write_text(dump(marker(extensions=[
                {"class": "source-observed", "schema": "link.json"}])), encoding="utf-8")
            code, result = run(["validate", "--json", str(tmp / "root" / "board-specs.yaml")])
            self.assertEqual(code, 1)
            self.assertIn("outside the root", result["findings"][0]["message"])


class Instances(Validator):
    def test_instances(self):
        self.assert_valid(soc(instances=[instance()]))
        self.assert_valid(soc(instances=[instance(reg=None, irq=None, support=DROP, todo=TODO)]))
        self.assert_valid(soc(instances=[instance(irq={"kind": "extended", "number": 4,
                                                       "parent": "gia"})]))
        cases = [
            ("uppercase hex", instance(reg="0x7E201000"), "does not match"),
            ("hex with separators", instance(reg="0x7e20_1000"), "does not match"),
            ("reg as an integer", instance(reg=4096), "is not of type 'string', 'null'"),
            ("reg null without todo", instance(reg=None), "must carry a todo"),
            ("irq null without todo", instance(irq=None), "must carry a todo"),
            ("reg missing", instance(reg=DROP), "'reg' is a required"),
            ("clocks missing", instance(clocks=DROP), "'clocks' is a required"),
            ("extended without parent", instance(irq={"kind": "extended", "number": 4}),
             "'parent' is a required"),
            ("extended with intid", instance(irq={"kind": "extended", "number": 4,
                                                  "parent": "g", "intid": 36}),
             "should not be valid"),
            ("SPI with parent", instance(irq={"kind": "SPI", "number": 4, "parent": "g"}),
             "should not be valid"),
            ("negative irq", instance(irq={"kind": "SPI", "number": -1}),
             "less than the minimum"),
            ("irq kind lowercase", instance(irq={"kind": "spi", "number": 1}), "is not one of"),
            ("unknown key", instance(base="0x0"), "unknown key 'base'"),
            ("no support or todo", instance(support=DROP), "must carry a todo"),
            ("inference with a sibling", instance(support=[READ["inference"],
                                                           READ["databook"]], todo=TODO),
             "an inference stands alone"),
        ]
        for label, inst, expected in cases:
            with self.subTest(label):
                self.assert_invalid(soc(instances=[inst]), expected)

    def test_variants(self):
        variant = {"id": "lite", "name": "Lite", "triggers": ["lite"], "shares": ["soc"],
                   "differs": "less DRAM", "support": [READ["doc"]]}
        self.assert_valid(board(variants=[variant]))
        self.assert_invalid(board(variants=[apply(variant, {"differs": DROP})]),
                            "'differs' is a required")
        self.assert_invalid(board(variants=[dict(variant, tag="doc")]), "unknown key 'tag'")
        self.assert_invalid(board(variants=[apply(variant, {"support": [READ["press"]]})]),
                            "require a todo")
        self.assert_invalid(board(variant_of="Base"), "does not match")


class Resources(Validator):
    def test_repos(self):
        self.assert_valid(with_repo(commit=DROP, ref="main", files=DROP))
        self.assert_valid(with_repo(commit="a" * 64, role="target", status="merged"))
        cases = [
            ("http url", repo(url="http://example.invalid/linux"), "does not match"),
            ("ssh url", repo(url="git@example.invalid:linux"), "does not match"),
            ("file url", repo(url="file:///tmp/linux"), "does not match"),
            ("ext url", repo(url="ext::sh -c x"), "does not match"),
            ("option url", repo(url="--upload-pack=x"), "does not match"),
            ("user info", repo(url="https://user:pw@example.invalid/linux"), "does not match"),
            ("space in url", repo(url="https://example.invalid/a b"), "does not match"),
            ("newline in url", repo(url="https://example.invalid/a\nb"), "does not match"),
            ("empty host", repo(url="https:///x"), "does not match"),
            ("commit and ref", repo(ref="main"), "is valid under each of"),
            ("neither commit nor ref", repo(commit=DROP), "is not valid under any"),
            ("short commit", repo(commit="1a2b3c4"), "does not match"),
            ("uppercase commit", repo(commit=COMMIT.upper()), "does not match"),
            ("digit-only commit", repo(commit=int("1" * 40)), "quote it"),
            ("no license", repo(license=DROP), "'license' is a required"),
            ("blank license", repo(license=" "), "does not match"),
            ("license with a slash", repo(license="MIT/Apache-2.0"), "does not match"),
            ("unknown role", repo(role="impl-ref"), "is not one of"),
            ("empty files", repo(files=[]), "should be non-empty"),
            ("file without license_from", repo(files=[{"path": "a.c"}]),
             "'license_from' is a required"),
            ("unknown license_from", repo(files=[{"path": "a.c", "license_from": "guess"}]),
             "is not one of"),
            ("files as strings", repo(files=["a.c"]), "is not of type 'object'"),
            ("file path dot-dot", repo(files=[{"path": "../a.c", "license_from": "notice"}]),
             "does not match"),
            ("unknown key", repo(pin="x"), "unknown key 'pin'"),
        ]
        for label, entry, expected in cases:
            with self.subTest(label):
                self.assert_invalid(soc(resources={"repos": [entry]}), expected)

    def test_documents(self):
        self.assert_valid(with_document(cite=False, sha256=SHA, pages=1, page_numbering="pdf",
                                        access="internal", fetch="partial", commit=COMMIT,
                                        retrieval=[{"url": "https://example.invalid/x"}]))
        cases = [
            ("class src", document(**{"class": "src"}), "is not one of"),
            ("no class", document(**{"class": DROP}), "'class' is a required"),
            ("no name", document(name=DROP), "'name' is a required"),
            ("ftp url", document(url="ftp://example.invalid/x"), "does not match"),
            ("http retrieval", document(retrieval=[{"url": "http://example.invalid/x"}]),
             "does not match"),
            ("empty retrieval", document(retrieval=[]), "should be non-empty"),
            ("uppercase sha256", document(sha256=SHA.upper()), "does not match"),
            ("cite true", document(cite=True), "False was expected"),
            ("zero pages", document(pages=0), "less than the minimum"),
            ("pages as a string", document(pages="166"), "is not of type 'integer'"),
            ("page numbering", document(page_numbering="roman"), "is not one of"),
            ("fetch value", document(fetch="maybe"), "is not one of"),
            ("verified not a date", document(verified="last week"), "does not match"),
            ("v1 cite field", document(cite="yes"), "False was expected"),
            ("unknown key", document(fetch_via="curl"), "unknown key 'fetch_via'"),
        ]
        for label, entry, expected in cases:
            with self.subTest(label):
                self.assert_invalid(soc(resources={"documents": [entry]}), expected)

    def test_series_tools_notices(self):
        series = {"title": "t", "url": "https://example.invalid/s", "status": "superseded",
                  "files": ["a/b.c"]}
        self.assert_valid(soc(resources={"series": [series], "tools": [
            {"kind": "bench", "name": "b", "via": "skill:x"}]},
            notices=[{"repo": "linux", "path": "a.c", "text": "Copyright"}]))
        self.assert_invalid(soc(resources={"series": [dict(series, cite=True)]}),
                            "unknown key 'cite'")
        self.assert_invalid(soc(resources={"tools": [{"kind": "bench", "name": "b"}]}),
                            "'via' is a required")
        self.assert_invalid(soc(notices=[{"repo": "linux", "path": "a.c"}]),
                            "'text' is a required")


class RootMarker(Validator):
    def test_markers(self):
        self.assert_valid(marker(roots=["../other"], license="GPL-2.0-only",
                                 accepts=["GPL-2.0-only"]), name="board-specs.yaml")
        self.assert_valid(marker(accepts=[]), name="board-specs.yaml")
        cases = [
            ("no format", marker(format=DROP), "'format' is a required"),
            ("v1 marker", marker(format=1), "2 was expected"),
            ("no name", marker(name=DROP), "'name' is a required"),
            ("blank name", marker(name=""), "does not match"),
            ("name with a space", marker(name="hardware specs"), "does not match"),
            ("name with @", marker(name="a@b"), "does not match"),
            ("unknown layer", marker(layer="vendor"), "is not one of"),
            ("expression in accepts", marker(accepts=["MIT OR Apache-2.0"]), "does not match"),
            ("duplicate accepts", marker(accepts=["MIT", "MIT"]), "non-unique"),
            ("unknown key", marker(fact_prefix="x"), "unknown key 'fact_prefix'"),
            ("other extension class",
             marker(extensions=[{"class": "src", "schema": "x.json"}]), "was expected"),
            ("extension path outside", marker(extensions=[
                {"class": "source-observed", "schema": "../x.json"}]), "does not match"),
            ("extension not json", marker(extensions=[
                {"class": "source-observed", "schema": "x.yaml"}]), "does not match"),
            ("missing fragment file", marker(extensions=[
                {"class": "source-observed", "schema": "x.json"}]), "No such file"),
            ("two extensions", marker(extensions=[
                {"class": "source-observed", "schema": "x.json"}] * 2), "is too long"),
        ]
        for label, data, expected in cases:
            with self.subTest(label):
                self.assert_invalid(data, expected, name="board-specs.yaml")


class Records(Validator):
    def test_records(self):
        self.assert_valid(record(), name="resources/w.verify.yaml")
        self.assert_valid(record({"f1": verdict(), "reg-ctrl.en": verdict(verdict="GAP")}),
                          name="w.verify.yaml")
        carried = verdict(contrary_evidence=DROP, citation_precision=DROP, readers=[],
                          carried_from={"repo": "r", "commit": COMMIT, "path": "a.verify.md",
                                        "key": 'Quick-facts/2 "GIC node"', "format": 1})
        self.assert_valid(record({"f1": carried}), name="w.verify.yaml")
        readings = [{"verifier": "a", "verdict": "PASS", "reasoning": "r"}]
        cases = [
            ("summary without adjudicate",
             record(summary={"pass": 1, "fail": 0, "unverifiable": 0, "gap": 0}),
             "'adjudicate' is a required"),
            ("summary unknown key", record(summary={"pass": 1, "fail": 0, "unverifiable": 0,
                                                    "gap": 0, "adjudicate": 0, "stale": 0}),
             "unknown key 'stale'"),
            ("summary negative", record(summary={"pass": -1, "fail": 0, "unverifiable": 0,
                                                 "gap": 0, "adjudicate": 0}),
             "less than the minimum"),
            ("key is a reference", record({"#f1": verdict()}), "does not match"),
            ("key is a v1 key", record({"Quick-facts/2": verdict()}), "does not match"),
            ("key with two dots", record({"a.b.c": verdict()}), "does not match"),
            ("lowercase verdict", record({"f1": verdict(verdict="pass")}), "is not one of"),
            ("FAIL without correction", record({"f1": verdict(verdict="FAIL")}),
             "a FAIL carries a correction"),
            ("PASS with correction", record({"f1": verdict(correction="x")}),
             "only a FAIL carries a correction"),
            ("ADJUDICATE without readings", record({"f1": verdict(verdict="ADJUDICATE")}),
             "carries readings"),
            ("ADJUDICATE with adjudication",
             record({"f1": verdict(verdict="ADJUDICATE", readings=readings,
                                   adjudication={"decision": "d", "by": "u",
                                                 "date": "2026-10-08", "rule": "r"})}),
             "no adjudication until settled"),
            ("adjudication on UNVERIFIABLE",
             record({"f1": verdict(verdict="UNVERIFIABLE", readings=readings,
                                   adjudication={"decision": "d", "by": "u",
                                                 "date": "2026-10-08", "rule": "r"})}),
             "has the verdict PASS or FAIL"),
            ("adjudication without readings",
             record({"f1": verdict(adjudication={"decision": "d", "by": "u",
                                                 "date": "2026-10-08", "rule": "r"})}),
             "keeps its readings"),
            ("readings on a plain PASS", record({"f1": verdict(readings=readings)}),
             "readings belong to"),
            ("fresh verdict without contrary_evidence",
             record({"f1": verdict(contrary_evidence=DROP)}), "states contrary_evidence"),
            ("fresh verdict without citation_precision",
             record({"f1": verdict(citation_precision=DROP)}), "states contrary_evidence"),
            ("carried without key", record({"f1": apply(carried, {"carried_from": {
                "repo": "r", "commit": COMMIT, "path": "a", "format": 1}})}),
             "'key' is a required"),
            ("carried format 3", record({"f1": apply(carried, {"carried_from": dict(
                carried["carried_from"], format=3)})}), "is not one of"),
            ("short basis", record({"f1": verdict(basis="abc")}), "does not match"),
            ("unknown verdict key", record({"f1": verdict(score=1)}), "unknown key 'score'"),
            ("reader without verdict", record({"f1": verdict(readers=[{"verifier": "v"}])}),
             "'verdict' is a required"),
            ("canonical v2", record(canonical="fact-v2"), "was expected"),
            ("spec_file not a spec", record(spec_file="w.spec.md"), "does not match"),
            ("spec_file outside", record(spec_file="../w.spec.yaml"), "does not match"),
            ("source without identity", record(sources=[{"name": "linux"}]),
             "is not valid under any"),
            ("no summary", record(summary=DROP), "'summary' is a required"),
        ]
        for label, data, expected in cases:
            with self.subTest(label):
                self.assert_invalid(data, expected, name="w.verify.yaml")


if __name__ == "__main__":
    unittest.main()
