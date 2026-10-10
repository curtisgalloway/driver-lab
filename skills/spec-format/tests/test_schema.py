#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for the format 2 schemas through `spec.py validate`.

Run in the pinned environment (pip checks the hashes; `uv run --with-requirements` does not):
  .venv-sf2/bin/python -m unittest discover -s skills/spec-format/tests -v

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
    return apply({"format": 2, "layer": "public", "name": "r", "license": "MIT", "accepts": ["MIT"]},
                 changes)


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
        self.assertEqual(kinds, {"board", "soc", "chip", "ip", "overlay", "facts", "peripheral"})
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
        # three slices and the record, plus the three root markers SF2-2 added for spec.py check
        self.assertEqual(len(files), 7)
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
            ("board kinds have no payload", fact(data={"register": {}}), "should not be valid"),
            ("board kinds have no requirement", fact(requirement="hw-required"),
             "should not be valid"),
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
             "$ref at properties/observer/$ref not allowed"),
            ("an id", dict(FRAGMENT, properties={"observer": {"$id": "urn:x"}}),
             "$id at properties/observer/$id not allowed"),
            ("a class field", dict(FRAGMENT, properties={"class": {"const": "x"}}),
             "field name 'class' is a core field"),
            ("a ref under a field named properties",
             {"type": "object", "required": ["properties"],
              "properties": {"properties": {"$ref": "https://example.invalid/s"}}},
             "$ref at properties/properties/$ref not allowed"),
            ("a dynamic ref", dict(FRAGMENT, properties={"observer": {"$dynamicRef": "#x"}}),
             "$dynamicRef at properties/observer/$dynamicRef not allowed"),
            ("a ref deep in items", dict(FRAGMENT, properties={"observer": {
                "type": "array", "items": {"anyOf": [{"$ref": "#"}]}}}),
             "$ref at properties/observer/items/anyOf/0/$ref not allowed"),
            ("a core field: anchors", dict(FRAGMENT, properties={"anchors": {"type": "array"}}),
             "field name 'anchors' is a core field"),
            ("a core field: url", dict(FRAGMENT, properties={"url": {"type": "string"}}),
             "field name 'url' is a core field"),
            ("a citation field: repo", dict(FRAGMENT, properties={"repo": {"type": "string"}}),
             "field name 'repo' at properties carries a citation"),
            ("a citation field: path, nested", dict(FRAGMENT, properties={"where": {
                "type": "object", "properties": {"path": {"type": "string"}}}}),
             "field name 'path' at properties/where/properties carries a citation"),
            ("a citation field: lines, in items", dict(FRAGMENT, properties={"spots": {
                "type": "array", "items": {"type": "object", "properties": {"lines": {}}}}}),
             "field name 'lines' at properties/spots/items/properties carries a citation"),
            ("nested patternProperties (Codex round 2)", dict(FRAGMENT, properties={"evidence": {
                "type": "object", "patternProperties": {"repo|path": {"type": "string"}},
                "additionalProperties": False}}),
             "patternProperties at properties/evidence/patternProperties not allowed"),
            ("nested dependentSchemas", dict(FRAGMENT, properties={"evidence": {
                "type": "object", "dependentSchemas": {"x": {"required": ["repo"]}}}}),
             "dependentSchemas at properties/evidence/dependentSchemas not allowed"),
            ("nested dependentRequired", dict(FRAGMENT, properties={"e": {
                "type": "object", "dependentRequired": {"x": ["y"]}}}),
             "dependentRequired at properties/e/dependentRequired not allowed"),
            ("nested propertyNames", dict(FRAGMENT, properties={"e": {
                "type": "object", "propertyNames": {"pattern": "r"}}}),
             "propertyNames at properties/e/propertyNames not allowed"),
            ("nested if/then", dict(FRAGMENT, properties={"e": {
                "type": "object", "if": {"required": ["a"]}, "then": {"required": ["b"]}}}),
             "if at properties/e/if not allowed"),
            ("additionalProperties schema", dict(FRAGMENT, properties={"e": {
                "type": "object", "additionalProperties": {"type": "string"}}}),
             "additionalProperties at properties/e/additionalProperties not allowed with a "
             "schema value"),
            ("unevaluatedProperties schema", dict(FRAGMENT, properties={"e": {
                "type": "object", "unevaluatedProperties": {"type": "string"}}}),
             "unevaluatedProperties at properties/e/unevaluatedProperties not allowed with a "
             "schema value"),
            ("items as a list", dict(FRAGMENT, properties={"e": {
                "type": "array", "items": [{"type": "string"}]}}), "items at properties/e/items"),
            ("required not strings", dict(FRAGMENT, required=[{}]), "required lists only"),
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

    def test_plain_nested_fragment_is_allowed(self):
        frag = dict(FRAGMENT, properties={"observer": {"type": "string", "pattern": "\\S"},
                                          "where": {"type": "object", "required": ["board"],
                                                    "properties": {"board": {"enum": ["a", "b"]},
                                                                   "pins": {"type": "array",
                                                                            "items": {"type": "integer",
                                                                                      "minimum": 0}}},
                                                    "additionalProperties": False}})
        entry = soc(facts=[fact(support=[{"class": "source-observed", "observer": "o",
                                          "where": {"board": "a", "pins": [1]}}], todo=TODO)])
        code, result = self.validate(entry, fragment=frag)
        self.assertEqual(code, 0, result["findings"])

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
            ("no license", marker(license=DROP), "'license' is a required"),
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
        carried = verdict(contrary_evidence=DROP, citation_precision=DROP,
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


class EndOfString(Validator):
    """Codex 1: Python's `$` also matches before a final newline; every pattern refuses one."""

    def test_trailing_newline_in_every_pattern_family(self):
        src = READ["src"]["anchors"][0]
        nl = "\n"
        spec_cases = [
            ("spec id", soc(id="w" + nl)),
            ("alias", soc(aliases=["w2" + nl])),
            ("fact id", soc(facts=[fact(id="f1" + nl)])),
            ("fact reference", soc(facts=[fact(relates=[{"fact": "#f2" + nl,
                                                         "relation": "refines"}])])),
            ("assumption id", soc(facts=[fact(assumes=["a" + nl])])),
            ("document name", with_document(name="trm" + nl)),
            ("cache name", soc(cache="c" + nl)),
            ("date", with_document(verified="2026-10-01" + nl)),
            ("sha256", with_document(sha256=SHA + nl)),
            ("commit", with_repo(commit=COMMIT + nl)),
            ("git ref", with_repo(commit=DROP, ref="main" + nl)),
            ("https URL", with_repo(url="https://example.invalid/linux" + nl)),
            ("license", with_repo(license="MIT" + nl)),
            ("path", soc(facts=[fact(support=[{"class": "src", "anchors": [
                dict(src, path="drivers/x.c" + nl)]}])])),
            ("symbol", soc(facts=[fact(support=[{"class": "src", "anchors": [
                dict(src, symbol="X_EN" + nl)]}])])),
            ("DT node", soc(facts=[fact(support=[{"class": "DT", "anchors": [
                {"repo": "linux", "path": "fw/b.dtb", "node": "/soc" + nl}]}])])),
            ("hex", soc(instances=[instance(reg="0x10" + nl)])),
            ("single-line title", soc(facts=[fact(title="Title" + nl)])),
            ("trigger", soc(triggers=["w" + nl])),
            ("tool via", soc(resources={"tools": [{"kind": "bench", "name": "b",
                                                   "via": "skill:x" + nl}]})),
            ("retrieval via", with_document(retrieval=[{"url": "https://example.invalid/x",
                                                        "via": "git" + nl}])),
        ]
        for label, data in spec_cases:
            with self.subTest(label):
                self.assert_invalid(data, "does not match")
        self.assert_invalid(marker(name="r" + nl), "does not match", name="board-specs.yaml")
        self.assert_invalid(marker(accepts=["MIT" + nl]), "does not match",
                            name="board-specs.yaml")
        self.assert_invalid(marker(extensions=[{"class": "source-observed",
                                                "schema": "x.json" + nl}]),
                            "does not match", name="board-specs.yaml")
        self.assert_invalid(record(spec_file="w.spec.yaml" + nl), "does not match",
                            name="w.verify.yaml")
        self.assert_invalid(record({"f1" + nl: verdict()}), "does not match",
                            name="w.verify.yaml")
        self.assert_invalid(record({"f1": verdict(basis=SHA + nl)}), "does not match",
                            name="w.verify.yaml")

    def test_block_scalar_newline_is_refused_in_an_id(self):
        raw = dump(chip()).replace("id: c\n", "id: |\n  c\n")
        self.assertIn("id: |", raw)
        self.assert_invalid(None, "does not match", raw=raw)

    def test_multi_line_text_keeps_its_newline(self):
        self.assert_valid(soc(facts=[fact(claim="Line one.\nLine two.\n")]))


class SingleLineAndIdentifiers(Validator):
    def test_single_line_text(self):
        for bad in [" pi 4", "pi 4 ", "pi  4", "pi\n4", ""]:
            with self.subTest(repr(bad)):
                self.assert_invalid(soc(triggers=[bad]), "does not match")
                self.assert_invalid(soc(name=bad), "does not match")
        self.assert_valid(soc(triggers=["pi 4", "raspberry pi 4 soc"]))

    def test_identifiers_that_reach_a_command_line(self):
        src = READ["src"]["anchors"][0]
        cases = [
            ("ref as an option", with_repo(commit=DROP, ref="--upload-pack=touch /tmp/x")),
            ("ref with a shell character", with_repo(commit=DROP, ref="main;rm")),
            ("ref with a space", with_repo(commit=DROP, ref="main rm")),
            ("ref with dot-dot", with_repo(commit=DROP, ref="../../x")),
            ("ref ending in .lock", with_repo(commit=DROP, ref="main.lock")),
            ("ref with @{", with_repo(commit=DROP, ref="main@{1}")),
            ("ref ending in /", with_repo(commit=DROP, ref="rpi/")),
            ("ref with a dot component", with_repo(commit=DROP, ref="a/.b")),
            ("symbol as an option", soc(facts=[fact(support=[{"class": "src", "anchors": [
                dict(src, symbol="--help")]}])])),
            ("symbol with a doubled space", soc(facts=[fact(support=[{"class": "src", "anchors": [
                dict(src, symbol="struct  x")]}])])),
            ("symbol with a trailing space", soc(facts=[fact(support=[{"class": "src", "anchors": [
                dict(src, symbol="x ")]}])])),
            ("node as an option", soc(facts=[fact(support=[{"class": "DT", "anchors": [
                {"repo": "linux", "path": "fw/b.dtb", "node": "-oProxyCommand=x"}]}])])),
            ("tool via not a skill", soc(resources={"tools": [{"kind": "bench", "name": "b",
                                                               "via": "sh -c x"}]})),
            ("retrieval via with a shell character",
             with_document(retrieval=[{"url": "https://example.invalid/x", "via": "curl|sh"}])),
            ("fetch_via with a semicolon", with_repo(fetch_via="a;b")),
            ("fetch_via as an option", with_repo(fetch_via="--exec=x")),
        ]
        for label, data in cases:
            with self.subTest(label):
                self.assert_invalid(data, "does not match")
        self.assert_valid(with_repo(commit=DROP, ref="rpi-6.12.y", fetch_via="git clone"))
        self.assert_valid(soc(facts=[fact(support=[{"class": "src", "anchors": [
            dict(src, symbol="ops->probe".replace("->", "."))]}])]))

    def test_urls_and_paths(self):
        src = READ["src"]["anchors"][0]
        for url in ["https://-x/r", "https://../r", "https://.", "https://a..b/",
                    "https://x-/r", "https://a/b\\c"]:
            with self.subTest(url):
                self.assert_invalid(with_repo(url=url), "does not match")
        self.assert_valid(with_repo(url="https://git.example.invalid:8443/a/b.git"))
        for path in [".git/config", "a/.git/x", "a/.GIT", "~/x", "a/~b"]:
            with self.subTest(path):
                self.assert_invalid(soc(facts=[fact(support=[{"class": "src", "anchors": [
                    dict(src, path=path)]}])]), "does not match")
        self.assert_invalid(soc(facts=[fact(support=[{"class": "src", "anchors": [
            dict(src, path="drivers/")]}])]), "does not match")
        self.assert_invalid(soc(facts=[fact(support=[{"class": "DT", "anchors": [
            {"repo": "linux", "path": "arch/", "lines": [1, 2]}]}])]), "does not match")
        self.assert_invalid(soc(facts=[fact(support=[{"class": "DT", "anchors": [
            {"repo": "linux", "path": "arch/x.DTS", "node": "soc"}]}])]),
            "'lines' is a required")
        self.assert_valid(soc(facts=[fact(support=[{"class": "src", "anchors": [
            {"repo": "linux", "path": "drivers/", "search": "nothing else"}]}])]))

    def test_dates(self):
        for bad in ["2026-02-31", "2026-02-29", "1900-02-29", "2026-04-31", "2026-00-10"]:
            with self.subTest(bad):
                self.assert_invalid(with_document(verified=bad), "does not match")
        for good in ["2024-02-29", "2000-02-29", "2026-12-31", "2026-02-28"]:
            with self.subTest(good):
                self.assert_valid(with_document(verified=good))

    def test_hex_has_one_spelling(self):
        for bad in ["0x00", "0x07e201000", "0X10", "0x", "10"]:
            with self.subTest(bad):
                self.assert_invalid(soc(instances=[instance(reg=bad)]), "does not match")
        self.assert_valid(soc(instances=[instance(reg="0x0")]))
        self.assert_valid(soc(instances=[instance(reg="0x7e201000")]))

    def test_other_spellings(self):
        self.assert_invalid(soc(facts=[fact(relates=[{"fact": "#Bad", "relation": "refines"}])]),
                            "does not match")
        self.assert_invalid(ip(facts=[fact(section="gotchas", title=DROP)]),
                            "'title' is a required")
        self.assert_invalid(soc(facts=[fact(support=[dict(READ["databook"], at=[
            {"pages": ["9", "9"]}])])]), "has non-unique elements")
        conflict = {"reading": "r", "support": [READ["doc"], READ["doc"]]}
        self.assert_invalid(soc(facts=[fact(conflicts=[conflict])]), "has non-unique elements")
        premise = {"states": "s", "support": [READ["doc"], READ["doc"]]}
        self.assert_invalid(soc(facts=[fact(support=[dict(READ["inference"],
                                                          premises=[premise])], todo=TODO)]),
                            "has non-unique elements")

    def test_support_null_is_not_called_a_todo_problem(self):
        code, result = self.validate(soc(facts=[fact(support=None)]))
        messages = [f["message"] for f in result["findings"]]
        self.assertEqual(code, 1)
        self.assertTrue(any("is not of type 'array'" in m for m in messages), messages)
        self.assertFalse(any("require a todo" in m for m in messages), messages)


class NoEmptyLists(Validator):
    """An optional list is absent or non-empty; [] would be a second spelling."""

    def test_empty_optional_lists(self):
        cases = [
            ("aliases", soc(aliases=[])), ("not_triggers", soc(not_triggers=[])),
            ("variants", board(variants=[])), ("assumptions", soc(assumptions=[])),
            ("notices", soc(notices=[])), ("chip instances", chip(instances=[])),
            ("overlay instances", overlay(instances=[])),
            ("documents", soc(resources={"documents": []})),
            ("repos", soc(resources={"repos": []})),
            ("series", soc(resources={"series": []})),
            ("tools", soc(resources={"tools": []})),
        ]
        for label, data in cases:
            with self.subTest(label):
                self.assert_invalid(data, "should be non-empty")
        self.assert_invalid(marker(roots=[]), "should be non-empty", name="board-specs.yaml")
        self.assert_invalid(record({"f1": verdict(readers=[])}), "should be non-empty",
                            name="w.verify.yaml")

    def test_required_lists_may_be_empty(self):
        self.assert_valid(soc(instances=[]))
        self.assert_valid(soc(instances=[instance(clocks=[])]))
        self.assert_valid(marker(accepts=[]), name="board-specs.yaml")
        self.assert_valid(soc(facts=[]))


class ClosedRecords(Validator):
    """Claude S5: every closed record refuses an unknown key (kills additionalProperties: true)."""

    def test_unknown_key_in_each_record(self):
        src = READ["src"]["anchors"][0]
        rtl = READ["rtl"]
        spec_cases = [
            ("relation", soc(facts=[fact(relates=[{"fact": "#f2", "relation": "refines",
                                                   "zz": 1}])])),
            ("decided", soc(facts=[fact(conflicts=[{
                "reading": "r", "support": [READ["doc"]], "resolution": "x",
                "decided": {"by": "u", "date": "2026-10-08", "zz": 1}}])])),
            ("irq", soc(instances=[instance(irq={"kind": "SPI", "number": 1, "zz": 1})])),
            ("notice", soc(notices=[{"repo": "linux", "path": "a.c", "text": "t", "zz": 1}])),
            ("stale", soc(facts=[fact(support=[{"class": "src", "anchors": [
                dict(src, stale={"was": COMMIT, "zz": 1})]}])])),
            ("rtl anchor", soc(facts=[fact(support=[dict(rtl, anchors=[
                dict(rtl["anchors"][0], zz=1)])])])),
            ("retrieval", with_document(retrieval=[{"url": "https://example.invalid/x",
                                                    "zz": 1}])),
            ("repos file", with_repo(files=[{"path": "a.c", "license_from": "notice",
                                             "zz": 1}])),
            ("tool", soc(resources={"tools": [{"kind": "b", "name": "b", "via": "skill:x",
                                               "zz": 1}]})),
            ("todo", soc(facts=[fact(todo=dict(TODO, zz=1))])),
            ("scope", soc(facts=[fact(scope={"boards": ["b"], "zz": ["x"]})])),
            ("locator", soc(facts=[fact(support=[dict(READ["databook"], at=[
                {"section": "1", "zz": "x"}])])])),
            ("premise", soc(facts=[fact(support=[dict(READ["inference"], premises=[
                {"fact": "#f0", "zz": 1}])], todo=TODO)])),
            ("assumption", soc(assumptions=[{"id": "a", "text": "t", "zz": 1}])),
            ("series", soc(resources={"series": [{"title": "t", "url":
                                                  "https://example.invalid/s", "zz": 1}]})),
            ("DT anchor", soc(facts=[fact(support=[{"class": "DT", "anchors": [
                dict(READ["DT"]["anchors"][0], zz=1)]}])])),
            ("src anchor", soc(facts=[fact(support=[{"class": "src", "anchors": [
                dict(src, zz=1)]}])])),
        ]
        for label, data in spec_cases:
            with self.subTest(label):
                self.assert_invalid(data, "unknown key 'zz'")
        readings = [{"verifier": "a", "verdict": "PASS", "reasoning": "r", "zz": 1}]
        verify_cases = [
            ("record", record(zz=1)),
            ("source", record(sources=[{"name": "linux", "commit": COMMIT, "zz": 1}])),
            ("summary", record(summary={"pass": 1, "fail": 0, "unverifiable": 0, "gap": 0,
                                        "adjudicate": 0, "zz": 1})),
            ("verdict", record({"f1": verdict(zz=1)})),
            ("reader", record({"f1": verdict(readers=[{"verifier": "v", "verdict": "PASS",
                                                       "zz": 1}])})),
            ("reading", record({"f1": verdict(verdict="ADJUDICATE", readings=readings)})),
            ("adjudication", record({"f1": verdict(readings=readings[:1] and [
                {"verifier": "a", "verdict": "PASS", "reasoning": "r"}],
                adjudication={"decision": "d", "by": "u", "date": "2026-10-08", "rule": "r",
                              "zz": 1})})),
            ("carried_from", record({"f1": verdict(carried_from={
                "repo": "r", "commit": COMMIT, "path": "a", "key": "k", "format": 1,
                "zz": 1})})),
        ]
        for label, data in verify_cases:
            with self.subTest(label):
                self.assert_invalid(data, "unknown key 'zz'", name="w.verify.yaml")
        self.assert_invalid(marker(zz=1), "unknown key 'zz'", name="board-specs.yaml")
        self.assert_invalid(marker(extensions=[{"class": "source-observed",
                                                "schema": "x.json", "zz": 1}]),
                            "unknown key 'zz'", name="board-specs.yaml")


class Reporting(Validator):
    def findings(self, data, name="w.spec.yaml"):
        code, result = self.validate(data, name=name)
        self.assertEqual(code, 1)
        return [f["message"] for f in result["findings"]]

    def test_nested_unknown_key_reports_only_itself(self):
        """Claude S3: a nested unknown key used to report five valid top-level keys."""
        self.assertEqual(self.findings(soc(instances=[instance(bogus=1)])),
                         ["instances[0].bogus: unknown key 'bogus' here"])
        self.assertEqual(self.findings(soc(instances=[instance(irq={
            "kind": "SPI", "number": 1, "foo": 1})])),
            ["instances[0].irq.foo: unknown key 'foo' here"])
        self.assertEqual(self.findings(board(variants=[{
            "id": "lite", "name": "Lite", "triggers": ["lite"], "shares": ["soc"],
            "differs": "less", "support": [READ["doc"]], "colour": "red"}])),
            ["variants[0].colour: unknown key 'colour' here"])

    def test_undeclared_key_is_always_reported(self):
        messages = self.findings(soc(zz=1, instances=[instance(bogus=1)]))
        self.assertIn("zz: unknown key 'zz' here", messages)
        self.assertIn("instances[0].bogus: unknown key 'bogus' here", messages)

    def test_bad_verdict_key_points_at_the_key(self):
        """Codex 8: a refused key is reported at its own line."""
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "w.verify.yaml"
            text = dump(record({"f1": verdict(), "Bad Fact": verdict()}))
            path.write_text(text, encoding="utf-8")
            code, result = run(["validate", "--json", str(path)])
        line = text.splitlines().index("  Bad Fact:") + 1
        self.assertEqual(code, 1)
        self.assertEqual([(f["line"], f["column"]) for f in result["findings"]], [(line, 3)])
        self.assertIn("key 'Bad Fact'", result["findings"][0]["message"])


class FragmentFiles(Validator):
    def run_with(self, fragment_text: str):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            (tmp / "frag.json").write_text(fragment_text, encoding="utf-8")
            (tmp / "board-specs.yaml").write_text(dump(marker(extensions=[
                {"class": "source-observed", "schema": "frag.json"}])), encoding="utf-8")
            return run(["validate", "--json", str(tmp / "board-specs.yaml")])

    def test_strict_json(self):
        for label, text, expected in [
            ("duplicate key", '{"type": "object", "type": "object", "properties": {}}',
             "duplicate key"),
            ("NaN", '{"type": "object", "properties": {"a": {"const": NaN}}}', "NaN is not JSON"),
            ("not JSON", "{", "Expecting"),
        ]:
            with self.subTest(label):
                code, result = self.run_with(text)
                self.assertEqual(code, 1)
                self.assertIn(expected, result["findings"][0]["message"])


class RoundTwo(Validator):
    """Round-2 review fixes and the orchestrator's decisions of 2026-10-08."""

    def test_option_like_identifiers(self):
        """Claude S1: each guard on ref and node has an input only it refuses."""
        for ref in ["-x", "a..b", "a//b", "main@{1}", "/main", "+main", COMMIT, "a" * 64]:
            with self.subTest(ref=ref):
                self.assert_invalid(with_repo(commit=DROP, ref=ref), "does not match")
        for ref in ["main", "refs/heads/main", "release/2026.10", "rpi-6.12.y", "a" * 39]:
            with self.subTest(ref=ref):
                self.assert_valid(with_repo(commit=DROP, ref=ref))
        self.assert_invalid(soc(facts=[fact(support=[{"class": "DT", "anchors": [
            {"repo": "linux", "path": "fw/b.dtb", "node": "-x"}]}])]), "does not match")

    def test_symbols_cite_cpp_and_assembler(self):
        src = READ["src"]["anchors"][0]
        def entry(symbol):
            return soc(facts=[fact(support=[{"class": "src", "anchors": [
                dict(src, symbol=symbol)]}])])
        for good in ["~Foo", "operator<<", "operator()", "Foo<T>", "foo()",
                     "ns::Class::method", "$label", "struct gic_chip_data", "X;rm"]:
            with self.subTest(good):
                self.assert_valid(entry(good))
        for bad in ["-x", "--help", " x", "x ", "a  b", "a\nb"]:
            with self.subTest(repr(bad)):
                self.assert_invalid(entry(bad), "does not match")

    def test_fetch_methods_are_prose(self):
        for good in ["curl (manual)", "Arm's documentation service", "git clone"]:
            with self.subTest(good):
                self.assert_valid(with_repo(fetch_via=good))
        for bad in ["a;b", "a | b", "$(id)", "-x", "a\\b"]:
            with self.subTest(bad):
                self.assert_invalid(with_repo(fetch_via=bad), "does not match")

    def test_ports(self):
        for port in ["1", "443", "65535"]:
            self.assert_valid(with_repo(url=f"https://example.invalid:{port}/x"))
        for port in ["0", "65536", "99999", "080", "123456"]:
            with self.subTest(port):
                self.assert_invalid(with_repo(url=f"https://example.invalid:{port}/x"),
                                    "does not match")

    def test_resources_absent_or_non_empty(self):
        self.assert_invalid(board(resources={}), "should be non-empty")
        self.assert_invalid(ip(resources={}), "should be non-empty")
        self.assert_valid(board())

    def test_accepts_is_required(self):
        self.assert_invalid(marker(accepts=DROP), "'accepts' is a required",
                            name="board-specs.yaml")
        self.assert_valid(marker(accepts=[]), name="board-specs.yaml")

    def test_shared_path_rules_on_spec_file_and_extension(self):
        for bad in ["~/x.spec.yaml", ".git/config.spec.yaml", "a/.git/x.spec.yaml", "-x.spec.yaml"]:
            with self.subTest(bad):
                self.assert_invalid(record(spec_file=bad), "does not match",
                                    name="w.verify.yaml")
        self.assert_valid(record(spec_file="sub/w.spec.yaml"), name="w.verify.yaml")
        for bad in [".git/f.json", "~/f.json", "a/../f.json"]:
            with self.subTest(bad):
                self.assert_invalid(marker(extensions=[{"class": "source-observed",
                                                        "schema": bad}]),
                                    "does not match", name="board-specs.yaml")

    def test_duplicate_readers(self):
        reader = {"verifier": "v", "verdict": "PASS"}
        self.assert_invalid(record({"f1": verdict(readers=[reader, reader])}),
                            "has non-unique elements", name="w.verify.yaml")

    def test_fragment_names_and_patterns(self):
        def entry(field):
            return soc(facts=[fact(support=[{"class": "source-observed", field: "x"}],
                                   todo=TODO)])
        cases = [
            ("field name with a newline", {"type": "object", "properties": {
                "observer\n": {"type": "string"}}, "required": ["observer\n"]},
             "field name 'observer\\n' not allowed", "observer\n"),
            ("class with a newline", {"type": "object", "properties": {
                "class\n": {"type": "string"}}}, "field name 'class\\n' not allowed", "class\n"),
            ("pattern with $", {"type": "object", "properties": {
                "observer": {"type": "string", "pattern": "^x$"}}}, "uses $", "observer"),
            ("pattern property with $", {"type": "object", "properties": {
                "observer": {"type": "object", "patternProperties": {"^a$": {}}}}},
             "uses $", "observer"),
            ("legacy dependencies", {"type": "object", "properties": {
                "observer": {"dependencies": {"t": {"$ref": "https://example.invalid/o"}}}}},
             "dependencies at properties/observer/dependencies is not a draft 2020-12 keyword",
             "observer"),
            ("a typo", {"type": "object", "properties": {"observer": {"maxLenght": 3}}},
             "maxLenght at properties/observer/maxLenght is not a draft 2020-12 keyword",
             "observer"),
            ("escaped bidi in a description", {"type": "object", "description": "a‮b",
                                               "properties": {"observer": {"type": "string"}}},
             "U+202E", "observer"),
        ]
        for label, frag, expected, field in cases:
            with self.subTest(label):
                code, result = self.validate(entry(field), fragment=frag)
                messages = [f["message"] for f in result["findings"]]
                self.assertEqual(code, 1)
                self.assertTrue(any(expected in m for m in messages), messages)
        self.assert_valid(entry("observer"), fragment={"type": "object", "properties": {
            "observer": {"type": "string", "pattern": "^[a-z$]+(?![\\s\\S])"}}})

    def test_raw_bidi_in_fragment_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            (tmp / "frag.json").write_text(
                '{"type": "object", "description": "a‮b",'
                ' "properties": {"observer": {"type": "string"}}}', encoding="utf-8")
            (tmp / "board-specs.yaml").write_text(dump(marker(extensions=[
                {"class": "source-observed", "schema": "frag.json"}])), encoding="utf-8")
            code, result = run(["validate", "--json", str(tmp / "board-specs.yaml")])
        self.assertEqual(code, 1)
        self.assertIn("frag.json:1:", result["findings"][0]["message"])
        self.assertIn("U+202E", result["findings"][0]["message"])

    def test_unknown_key_declared_in_another_branch_is_reported(self):
        """Codex 2: the filter keeps only keys of the branch that applies."""
        code, result = self.validate(soc(facts=[fact(todo={"check": "bogus", "text": "t",
                                                           "url": "https://example.invalid/"})]))
        messages = [f["message"] for f in result["findings"]]
        self.assertEqual(code, 1)
        self.assertIn("facts[0].todo.url: unknown key 'url' here", messages)
        code, result = self.validate(soc(parts=["x"], instances=[instance(bogus=1)]))
        messages = [f["message"] for f in result["findings"]]
        self.assertEqual(sorted(messages), ["instances[0].bogus: unknown key 'bogus' here",
                                            "parts: unknown key 'parts' here"])
        code, result = self.validate(soc(facts=[fact(support=[dict(READ["src"], doc="trm",
                                                                    anchors=[{"repo": "linux",
                                                                              "path": "x.c"}])])]))
        messages = [f["message"] for f in result["findings"]]
        self.assertIn("facts[0].support[0].doc: unknown key 'doc' here", messages)
        self.assertNotIn("facts[0].support[0].anchors: unknown key 'anchors' here", messages)


class RoundThree(Validator):
    """Round-3 review fixes."""

    def test_fragment_regex_constructs(self):
        """Codex 1 and Claude: a comment cannot hide a $; \Z is Python-only."""
        def frag(pattern):
            return {"type": "object", "properties": {
                "observer": {"type": "string", "pattern": pattern}}}
        entry = soc(facts=[fact(support=[{"class": "source-observed", "observer": "x"}],
                                todo=TODO)])
        for pattern, expected in [("(?# [)^x$", "(?#...) comment"), ("^x\\Z", "\\Z"),
                                  ("[a]$", "uses $"), ("[^]]$", "uses $")]:
            with self.subTest(pattern):
                code, result = self.validate(entry, fragment=frag(pattern))
                messages = [f["message"] for f in result["findings"]]
                self.assertEqual(code, 1)
                self.assertTrue(any(expected in m for m in messages), messages)
        for pattern, value in [("[]$]", "$"), ("[^]$]", "x"), ("^x\\$(?![\\s\\S])", "x$"),
                               ("[$]", "$"), ("^x(?![\\s\\S])", "x")]:
            with self.subTest(pattern):
                self.assert_valid(soc(facts=[fact(support=[{
                    "class": "source-observed", "observer": value}], todo=TODO)]),
                    fragment=frag(pattern))

    def test_unknown_key_under_alternatives(self):
        """Codex 2 (SF2-1): a fragment's anyOf/oneOf could admit keys no check sees. Since the
        SF2-2 round-2 user decision a fragment uses plain properties only, so it is refused."""
        for combinator in ["anyOf", "oneOf"]:
            observer = {
                "type": "object",
                "properties": {"n": {"type": "integer"}},
                combinator: [
                    {"properties": {"kind": {"const": "a"}, "a": {}}, "required": ["kind"]},
                    {"properties": {"kind": {"const": "b"}, "b": {}}, "required": ["kind"]},
                ],
                "unevaluatedProperties": False,
            }
            frag = {"type": "object", "properties": {"observer": observer}}
            entry = soc(facts=[fact(support=[{"class": "source-observed", "observer": {
                "kind": "a", "b": 1, "n": "bad"}}], todo=TODO)])
            with self.subTest(combinator):
                self.assert_invalid(entry, f"{combinator} at properties/observer/{combinator} "
                                           f"not allowed", fragment=frag)

    def test_commit_spelled_as_ref_in_either_case(self):
        for ref in ["A" * 40, "Ab" * 32, COMMIT.upper()]:
            with self.subTest(ref):
                self.assert_invalid(with_repo(commit=DROP, ref=ref), "does not match")

    def test_fetch_methods_refuse_angle_brackets(self):
        for bad in ["a<b", "a>b", "x a<b"]:
            with self.subTest(bad):
                self.assert_invalid(with_repo(fetch_via=bad), "does not match")


if __name__ == "__main__":
    unittest.main()
