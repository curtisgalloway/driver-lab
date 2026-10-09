#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for `spec.py check` (SF2-2): composition, references and the license gate.

Fixtures (all synthetic):
- fixtures/license-gate: the format 1 license-gate matrix rewritten in format 2 (its README);
- fixtures/references/<case>/<root>: one directory of roots per reference case (plan step 4);
- fixtures/check/good_root, bad_root, vendor_root, stubs: board-expert's fixtures in format 2,
  each bad file keeping one defect;
- fixtures/worked-example: the design's three slices, with markers shaped like the repositories.
Other inputs are built in temporary roots, one rule each.

Run in the pinned environment:
  .venv-sf2/bin/python -m unittest discover -s skills/spec-format/tests -v
"""

import contextlib
import io
import json
import os
import pathlib
import shutil
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "spec.py"
FIX = HERE / "fixtures"
GATE = FIX / "license-gate"
REFS = FIX / "references"
CHECK = FIX / "check"
WORKED = FIX / "worked-example"
sys.path.insert(0, str(SCRIPT.parent))
import spec as spec_cli  # noqa: E402

HDR = "# SPDX-FileCopyrightText: 2026 contributors\n# SPDX-License-Identifier: Apache-2.0\n"


def check(*argv):
    """(exit code, JSON result) of `spec.py check --json ...`."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = spec_cli.main(["check", "--json", *[str(a) for a in argv]])
    return code, json.loads(out.getvalue())


def errors(result, path=None):
    return [f for f in result["findings"] if f["level"] == "error"
            and (path is None or f["path"].endswith(str(path)))]


def need(found):
    """The findings, asserting there is at least one (a removed guard fails, never crashes)."""
    if not found:
        raise AssertionError("expected a finding, found none")
    return found


def only(found):
    """The one finding, asserting there is exactly one."""
    if len(found) != 1:
        raise AssertionError(f"expected one finding, found {len(found)}: {found}")
    return found[0]


def warnings(result):
    return [f for f in result["findings"] if f["level"] == "warning"]


def marker(name="r", layer="public", accepts="[]", lic="CC-BY-4.0", extra=""):
    return (HDR + f"format: 2\nlayer: {layer}\nname: {name}\nlicense: {lic}\naccepts: {accepts}\n"
            + extra)


def chip(sid="widgetchip", facts=None, repos="", docs=None, head=""):
    docs = docs if docs is not None else (
        '    - {name: trm, class: databook, title: Widget TRM, '
        'url: "https://example.invalid/trm.pdf", pages: 80}\n')
    facts = facts if facts is not None else fact("reset")
    text = (HDR + f"format: 2\nkind: chip\nid: {sid}\nname: Widget\ntriggers: [{sid}]\n" + head
            + "resources:\n  documents:\n" + docs)
    if repos:
        text += "  repos:\n" + repos
    return text + "facts:\n" + facts


def fact(fid, extra=""):
    return (f"  - id: {fid}\n    section: quick-facts\n    title: T {fid}\n    claim: C {fid}.\n"
            '    support: [{class: databook, doc: trm, at: [{section: "1"}]}]\n' + extra)


def inference(fid, *refs, extra=""):
    out = (f"  - id: {fid}\n    section: quick-facts\n    title: T {fid}\n    claim: C {fid}.\n"
           "    support:\n      - class: inference\n        premises:\n")
    out += "".join(f'          - fact: "{r}"\n' for r in refs)
    return out + ("        derivation: it follows\n"
                  "    todo: {check: hardware, text: check it.}\n" + extra)


def repo(name="linux", lic="GPL-2.0-only", path="drivers/w.c"):
    return (f"    - name: {name}\n      url: https://example.invalid/{name}\n"
            '      commit: "1a2b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d"\n'
            f"      license: {lic}\n      files: [{{path: {path}, license_from: spdx-line}}]\n")


def src_fact(fid, name="linux", path="drivers/w.c"):
    return (f"  - id: {fid}\n    section: quick-facts\n    title: T {fid}\n    claim: C {fid}.\n"
            "    support:\n      - class: src\n"
            f"        anchors: [{{repo: {name}, path: {path}, lines: [1, 2], symbol: S}}]\n")


def overlay(target="widgetchip", facts="", repos="", head=""):
    text = HDR + f"format: 2\nkind: overlay\noverlays: {target}\n" + head
    if repos:
        text += "resources:\n  repos:\n" + repos
    return text + "facts:\n" + (facts or "  []\n")


class TempRoots(unittest.TestCase):
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

    def copy_root(self, name, src: pathlib.Path, *specs: pathlib.Path) -> pathlib.Path:
        d = self.tmp / name
        d.mkdir(parents=True)
        shutil.copy(src / "board-specs.yaml", d)
        for s in specs:
            shutil.copy(s, d)
        return d


class LicenseGateMatrix(TempRoots):
    """The format 1 matrix in format 2, row for row (fixtures/license-gate/README.md)."""

    def matrix(self, flags):
        expected = json.loads((GATE / "expected.json").read_text(encoding="utf-8"))
        deltas = {} if flags else expected["without_require_license"]
        got, want = {}, {}
        for spec in sorted((GATE / "specs").glob("*.spec.yaml")):
            for r in ("gpl", "docs", "permissive"):
                root = self.copy_root(f"{spec.stem}-{r}-{len(flags)}", GATE / "roots" / r, spec)
                code, result = check(root, *flags)
                got[(spec.name, r)] = code
                want[(spec.name, r)] = deltas.get(spec.name, {}).get(r, expected[spec.name][r])
                if code == 1:
                    for f in errors(result):
                        self.assertRegex(f["message"], r"is not accepted by root|not an SPDX"
                                         r"|resolves to nothing|which is not in this file|"
                                         r"license.*(unknown|required)", f)
        self.assertEqual(got, want)

    def test_matrix_with_require_license(self):
        self.matrix(["--require-license"])

    def test_matrix_without_require_license(self):
        self.matrix([])

    def test_expected_lists_exactly_the_specs(self):
        expected = json.loads((GATE / "expected.json").read_text(encoding="utf-8"))
        rows = {k for k in expected if k.endswith(".spec.yaml")}
        self.assertEqual(rows, {p.name for p in (GATE / "specs").glob("*.spec.yaml")})
        self.assertTrue(set(expected["without_require_license"]) <= rows)

    def test_codes_match_format_1(self):
        v1 = json.loads((HERE.parents[1] / "peripheral-spec" / "tests" / "fixtures"
                         / "license-gate" / "expected.json").read_text(encoding="utf-8"))
        v2 = json.loads((GATE / "expected.json").read_text(encoding="utf-8"))
        for name, codes in v1.items():
            if name.endswith("-spec.md"):
                self.assertEqual(v2[name.replace("-spec.md", ".spec.yaml")], codes, name)


class BoardOverlays(TempRoots):
    def run_pair(self, root_dir, *overlays, flags=("--require-license",)):
        board = GATE / "board"
        root = self.copy_root(f"{root_dir}-{len(os.listdir(self.tmp))}", GATE / "roots" / root_dir,
                              board / "widgetchip.spec.yaml",
                              *[board / f"widgetchip-{o}-overlay.spec.yaml" for o in overlays])
        return check(root, *flags)

    def test_fit_and_misfit_per_repository(self):
        cases = [("gpl", (), 0), ("gpl", ("bsd",), 0), ("gpl", ("gpl3",), 1),
                 ("docs", (), 0), ("docs", ("bsd",), 1), ("docs", ("gpl3",), 1),
                 ("permissive", ("bsd",), 0), ("permissive", ("gpl3",), 1)]
        for root, overlays, want in cases:
            code, result = self.run_pair(root, *overlays)
            self.assertEqual(code, want, (root, overlays, result["findings"]))

    def test_src_overlay(self):
        for flags in (("--require-license",), ()):
            for root, want in (("gpl", 0), ("permissive", 0), ("docs", 1)):
                code, result = self.run_pair(root, "src", flags=flags)
                self.assertEqual(code, want, (root, flags, result["findings"]))
                if want:
                    f = only(errors(result))
                    self.assertIn("fact 'stub-magic': an anchor names repos entry 'tools': "
                                  "BSD-3-Clause is not accepted by root hardware-specs-docs",
                                  f["message"])

    def test_overlay_across_roots(self):
        board = GATE / "board"
        docs = self.copy_root("docs", GATE / "roots" / "docs", board / "widgetchip.spec.yaml")
        perm = self.copy_root("perm", GATE / "roots" / "permissive",
                              board / "widgetchip-bsd-overlay.spec.yaml")
        code, result = check(perm, "--require-license")
        self.assertEqual(code, 1)
        self.assertIn("overlays 'widgetchip' resolves to no spec", need(errors(result))[0]["message"])
        self.assertEqual(check(docs, perm, "--require-license")[0], 0)
        self.assertEqual(check(perm, "--context-root", docs, "--require-license")[0], 0)


class References(TempRoots):
    """Plan step 4: each case's result, with a message naming the fact."""

    def case(self, name, *roots):
        return check(*[REFS / name / r for r in roots])

    def test_gpl_inference_on_a_docs_fact_passes(self):
        code, result = self.case("gpl-cites-docs", "docs", "gpl")
        self.assertEqual((code, result["findings"]), (0, []))

    def test_docs_inference_on_a_gpl_fact_fails_the_transitive_gate(self):
        code, result = self.case("docs-cites-gpl", "docs", "gpl")
        self.assertEqual(code, 1)
        f = only(errors(result))
        self.assertTrue(f["path"].endswith("docs/widgetchip.spec.yaml"))
        self.assertIn("fact 'mode': reference 'widgetchip@ref-gpl#tree-ranges' reaches repos "
                      "entry 'linux'", f["message"])
        self.assertIn("GPL-2.0-only is not accepted by root ref-docs", f["message"])
        self.assertEqual((f["line"], f["column"]), (26, 19))  # the reference's value

    def test_unqualified_cross_root_reference_fails(self):
        code, result = self.case("unqualified", "docs", "gpl")
        self.assertEqual(code, 1)
        f = only(errors(result))
        self.assertIn("fact 'low-mode': reference 'widgetchip#addressing' resolves to nothing",
                      f["message"])
        self.assertIn("widgetchip@ref-docs#addressing", f["message"])

    def test_same_id_in_two_roots_passes(self):
        code, result = self.case("same-id", "docs", "gpl")
        self.assertEqual((code, result["findings"]), (0, []))

    def test_premise_cycle_fails(self):
        code, result = self.case("cycle", "docs")
        self.assertEqual(code, 1)
        messages = sorted(f["message"] for f in errors(result))
        self.assertEqual(len(messages), 2)
        self.assertIn("fact 'mode-a': its inference premises form a cycle", messages[0])
        self.assertIn("fact 'mode-b': its inference premises form a cycle", messages[1])

    def test_reference_into_a_later_layer_fails(self):
        code, result = self.case("later-layer", "docs", "vendor")
        self.assertEqual(code, 1)
        f = only(errors(result))
        self.assertIn("fact 'mode': 'widgetchip@ref-vendor#errata' names a fact in layer "
                      "product", f["message"])

    def test_renamed_root_reports_every_dangling_reference(self):
        code, result = self.case("renamed-root", "docs", "gpl")
        self.assertEqual(code, 1)
        found = errors(result)
        self.assertEqual(len(found), 2)
        self.assertEqual(len({(f["line"], f["column"]) for f in found}), 2)
        for f in found:
            self.assertIn("fact 'low-mode': reference 'widgetchip@ref-docs#addressing' "
                          "resolves to nothing: no root named 'ref-docs'", f["message"])

    def test_a_context_root_cannot_downgrade_a_checked_roots_finding(self):
        # The cause lies in the context root (its GPL fact); the finding is the checked file's.
        code, result = check(REFS / "docs-cites-gpl" / "docs", "--context-root",
                             REFS / "docs-cites-gpl" / "gpl")
        self.assertEqual(code, 1)
        f = only(errors(result))
        self.assertTrue(f["path"].endswith("docs/widgetchip.spec.yaml"))
        self.assertNotIn("context root", f["message"])

    def test_a_context_roots_own_finding_is_a_warning(self):
        code, result = check(REFS / "docs-cites-gpl" / "gpl", "--context-root",
                             REFS / "docs-cites-gpl" / "docs")
        self.assertEqual(code, 0)
        w = only(warnings(result))
        self.assertTrue(w["message"].startswith("context root: fact 'mode'"))

    def test_gate_follows_chains_relates_and_observations(self):
        gpl = self.root("gpl", {
            "board-specs.yaml": marker("g", accepts="[GPL-2.0-only]", lic="GPL-2.0-only"),
            "widgetchip.spec.yaml": overlay(facts=src_fact("tree"), repos=repo())})
        docs_facts = (fact("base")
                      + inference("hop1", "#base", "widgetchip@g#tree")
                      + inference("hop2", "#hop1")
                      + fact("rel", '    relates: [{fact: "widgetchip@g#tree", relation: '
                                    'qualifies}]\n')
                      + "  - id: obs\n    section: quick-facts\n    title: Obs\n    claim: Seen.\n"
                        "    support:\n      - {class: databook, doc: trm, at: [{section: \"1\"}]}\n"
                        '      - {class: emulated, model: m, version: "1", observation: '
                        '"widgetchip@g#tree"}\n'
                        "    todo: {check: hardware, text: check it.}\n")
        docs = self.root("docs", {"board-specs.yaml": marker("d"),
                                  "widgetchip.spec.yaml": chip(facts=docs_facts)})
        code, result = check(docs, gpl)
        self.assertEqual(code, 1)
        failing = {f["message"].split(":")[0] for f in errors(result)}
        self.assertEqual(failing, {"fact 'hop1'", "fact 'hop2'", "fact 'rel'", "fact 'obs'"})
        hop2 = [f["message"] for f in errors(result) if f["message"].startswith("fact 'hop2'")]
        self.assertIn("through widgetchip@g#tree", hop2[0])

    def test_reach_into_an_anchor_naming_no_repos_entry(self):
        # In another root the target's root is untrusted (below); within the citing root the
        # gate itself must refuse an anchor whose repos entry is not listed.
        root = self.root("r", {
            "board-specs.yaml": marker("k"),
            "widgetchip.spec.yaml": chip(facts=src_fact("t", name="ghost")),
            "other.spec.yaml": chip("other", facts=inference("a", "widgetchip#t"))})
        code, result = check(root)
        self.assertEqual(code, 1)
        f = only(errors(result, "other.spec.yaml"))
        self.assertIn("reaches an anchor of widgetchip@k#t naming repos entry 'ghost', which "
                      "its file does not list (its license is unknown)", f["message"])
        ctx = self.root("ctx", {"board-specs.yaml": marker("c"),
                                "widgetchip.spec.yaml": chip(facts=src_fact("t", name="ghost"))})
        docs = self.root("docs", {"board-specs.yaml": marker("d"),
                                  "other.spec.yaml": chip("other", facts=inference(
                                      "a", "widgetchip@c#t"))})
        code, result = check(docs, "--context-root", ctx)
        self.assertEqual(code, 1)
        f = only(errors(result))
        self.assertIn("reference 'widgetchip@c#t' cannot be resolved: root c, which is "
                      "untrusted", f["message"])

    def test_same_file_duplicate_id_is_ambiguous(self):
        facts = fact("a") + fact("a").replace("C a.", "Another a.") + inference("b", "#a")
        root = self.root("r", {"board-specs.yaml": marker(),
                               "widgetchip.spec.yaml": chip(facts=facts)})
        code, result = check(root)
        self.assertEqual(code, 1)
        self.assertTrue(any("reference '#a' is ambiguous: this file declares fact 'a' twice"
                            in f["message"] for f in errors(result)), result["findings"])

    def test_self_premise_is_a_cycle(self):
        root = self.root("r", {"board-specs.yaml": marker(),
                               "widgetchip.spec.yaml": chip(facts=inference("loop", "#loop"))})
        code, result = check(root)
        self.assertEqual(code, 1)
        self.assertIn("its inference premises form a cycle", need(errors(result))[0]["message"])

    def test_three_reference_forms_resolve(self):
        facts = (fact("a") + inference("b", "#a", "widgetchip#a", "widgetchip@r#a")
                 + inference("c", "#a", extra='    relates: [{fact: "#a", relation: refines},'
                                               ' {fact: "#a", relation: qualifies}]\n'))
        root = self.root("r", {"board-specs.yaml": marker(),
                               "widgetchip.spec.yaml": chip(facts=facts)})
        code, result = check(root)
        # Three spellings of one premise: two findings; two relations to one fact are fine.
        self.assertEqual(code, 1)
        self.assertEqual(len(errors(result)), 2)
        for f in errors(result):
            self.assertIn("names widgetchip@r#a, as '#a' already does in this premise list",
                          f["message"])

    def test_reference_to_an_overlay_fact_in_the_same_root(self):
        root = self.root("r", {"board-specs.yaml": marker(),
                               "widgetchip.spec.yaml": chip(facts=inference("b", "widgetchip#o")),
                               "over.spec.yaml": overlay(facts=fact("o").replace("trm", "trm"))})
        code, result = check(root)
        # the overlay's fact cites trm, which only the base lists: the name rule is per file
        self.assertIn("document 'trm' is not in this file's resources.documents",
                      need(errors(result))[0]["message"])
        self.assertEqual(len(errors(result)), 1)

    def test_reference_into_an_invalid_root_dangles(self):
        bad = self.root("bad", {"board-specs.yaml": marker("b", extra="bogus: 1\n"),
                                "widgetchip.spec.yaml": chip()})
        good = self.root("good", {"board-specs.yaml": marker("g"),
                                  "other.spec.yaml": chip("other", facts=inference(
                                      "x", "widgetchip@b#reset"))})
        code, result = check(good, "--context-root", bad)
        self.assertEqual(code, 1)
        self.assertIn("reference 'widgetchip@b#reset' cannot be resolved: the marker",
                      need(errors(result, "other.spec.yaml"))[0]["message"])
        self.assertTrue(warnings(result))  # the context root's marker finding


FAIL = REFS / "fail-closed"


class FailClosed(unittest.TestCase):
    """The gate fails closed: a hop it cannot establish is an error on the checked citing file
    (fixtures/references/fail-closed: docs -> context perm -> fc-gpl's gfact)."""

    def chain(self, *context):
        args = [FAIL / "docs", "--context-root", FAIL / "perm"]
        for c in context:
            args += ["--context-root", FAIL / c]
        return check(*args)

    def assert_closed(self, result, text):
        f = only(errors(result, "docs/dchip.spec.yaml"))
        self.assertEqual((f["line"], f["column"]), (20, 19))
        self.assertIn("fact 'a': reference 'pchip@fc-perm#p' reaches pchip@fc-perm#p, whose "
                      "reference 'gchip@fc-gpl#gfact'", f["message"])
        self.assertIn(text, f["message"])
        self.assertIn("the license gate fails closed", f["message"])

    def test_the_gpl_chain_fails_the_gate(self):
        code, result = self.chain("gpl")
        self.assertEqual(code, 1)
        self.assertIn("GPL-2.0-only is not accepted by root fc-docs", need(errors(result))[0]["message"])

    def test_target_root_not_given(self):
        code, result = self.chain()
        self.assertEqual(code, 1)
        self.assertEqual(len(errors(result)), 1)  # only the checked file's: perm's is a warning
        self.assert_closed(result, "resolves to nothing: no root named 'fc-gpl'")

    def test_target_spec_fails_the_schema(self):
        code, result = self.chain("gpl-schema-failed")
        self.assertEqual(code, 1)
        self.assert_closed(result, "root fc-gpl, which is untrusted")
        self.assert_closed(result, "unknown key 'bogus'")

    def test_target_marker_invalid(self):
        code, result = self.chain("gpl-bad-marker")
        self.assertEqual(code, 1)
        # An unreadable marker makes its root's name unknown: every root-qualified reference
        # fails closed, the first hop included (user decision, round 2).
        f = only(errors(result, "docs/dchip.spec.yaml"))
        self.assertIn("reference 'pchip@fc-perm#p' cannot be resolved: the marker", f["message"])
        self.assertIn("could not be read, so that root's name is unknown and could be "
                      "'fc-perm'; every root-qualified reference fails closed", f["message"])

    def test_duplicate_fact_id_in_the_target_root(self):
        code, result = self.chain("gpl-dup-id")
        self.assertEqual(code, 1)
        self.assert_closed(result, "root fc-gpl, which is untrusted")
        self.assert_closed(result, "fact id 'gfact' is also used by")

    def test_two_roots_with_one_name_either_order(self):
        for order in (("gpl-clean-twin", "gpl"), ("gpl", "gpl-clean-twin")):
            code, result = self.chain(*order)
            self.assertEqual(code, 1, order)
            closed = [f for f in errors(result) if f["path"].endswith("docs/dchip.spec.yaml")]
            self.assertEqual(len(closed), 1, order)
            self.assertIn("is ambiguous: 2 roots read are named 'fc-gpl'", closed[0]["message"])

    def test_the_clean_twin_alone_passes(self):
        code, result = self.chain("gpl-clean-twin")
        self.assertEqual((code, errors(result)), (0, []))

    def test_direct_reference_into_an_unreadable_target(self):
        # the first hop itself: reported as the reference's own failure, an error
        code, result = check(FAIL / "perm", "--context-root", FAIL / "gpl-schema-failed")
        self.assertEqual(code, 1)
        self.assertIn("reference 'gchip@fc-gpl#gfact' cannot be resolved",
                      need(errors(result))[0]["message"])

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root reads any directory")
    def test_a_directory_that_cannot_be_listed(self):
        with tempfile.TemporaryDirectory() as tmp:
            for ctx in (False, True):
                gpl = pathlib.Path(tmp) / f"gpl{ctx}"
                shutil.copytree(FAIL / "gpl", gpl)
                hidden = gpl / "sub"
                hidden.mkdir()
                shutil.move(gpl / "gchip.spec.yaml", hidden / "gchip.spec.yaml")
                hidden.chmod(0)
                try:
                    if ctx:
                        code, result = self.chain_with(gpl)
                    else:
                        code, result = check(gpl)
                finally:
                    hidden.chmod(0o755)
                self.assertEqual(code, 1, ctx)
                listing = [f for f in errors(result) if "cannot list this directory" in f["message"]
                           and not f["path"].endswith("dchip.spec.yaml")]
                self.assertEqual(len(listing), 1, (ctx, result["findings"]))
                if ctx:
                    self.assert_closed(result, "root fc-gpl, which is untrusted")

    def chain_with(self, gpl):
        return check(FAIL / "docs", "--context-root", FAIL / "perm", "--context-root", gpl)


UNTRUSTED = REFS / "untrusted"


class Untrusted(unittest.TestCase):
    """User decision (round 2): a reference may only rest on a root that checks clean. Every
    round-2 input from both reviewers, at the GPL end of the fail-closed chain (or as a second
    root named fc-gpl beside the clean twin): each fails on the checked docs file alone."""

    UNTRUSTED_ROOT = {  # case: text from the root's own first error, quoted in the message
        "misnamed-yml": "not read as a spec", "misnamed-upper": "not read as a spec",
        "misnamed-mixed": "not read as a spec", "backup-bak": "not read as a spec",
        "backup-tilde": "not read as a spec", "format1-md": "a format 1 spec",
        "overlays-newline": "b.spec.yaml", "overlays-case": "b.spec.yaml",
        "id-only": "b.spec.yaml", "no-identity": "b.spec.yaml", "id-list": "b.spec.yaml",
        "id-empty": "b.spec.yaml", "dup-repos": "listed twice",
    }
    UNREADABLE_MARKER = ["fragment", "second-unparseable", "second-name-int",
                         "second-name-newline", "second-dup-name-key", "second-bogus-key"]

    def run_case(self, case):
        args = [FAIL / "docs", "--context-root", FAIL / "perm"]
        if case.startswith("second-"):
            args += ["--context-root", FAIL / "gpl-clean-twin"]
        return check(*args, "--context-root", UNTRUSTED / case, "--require-license")

    def test_every_case_is_a_fixture(self):
        self.assertEqual({p.name for p in UNTRUSTED.iterdir()},
                         set(self.UNTRUSTED_ROOT) | set(self.UNREADABLE_MARKER) | {"warning-only"})

    def test_untrusted_roots(self):
        for case, first in self.UNTRUSTED_ROOT.items():
            with self.subTest(case):
                code, result = self.run_case(case)
                self.assertEqual(code, 1)
                f = only(errors(result))
                self.assertTrue(f["path"].endswith("docs/dchip.spec.yaml"), f)
                self.assertIn("whose reference 'gchip@fc-gpl#gfact' cannot be resolved: root "
                              "fc-gpl, which is untrusted", f["message"])
                self.assertIn(first, f["message"])
                self.assertIn("a reference may only rest on a root that checks clean",
                              f["message"])

    def test_unreadable_markers(self):
        for case in self.UNREADABLE_MARKER:
            with self.subTest(case):
                code, result = self.run_case(case)
                self.assertEqual(code, 1)
                f = only(errors(result))
                self.assertTrue(f["path"].endswith("docs/dchip.spec.yaml"), f)
                self.assertIn(f"untrusted/{case}/board-specs.yaml could not be read, so that "
                              f"root's name is unknown", f["message"])

    def test_a_clean_context_root_resolves_normally(self):
        code, result = self.run_case("warning-only")
        self.assertEqual((code, errors(result)), (0, []))
        self.assertEqual(len(warnings(result)), 2)  # the two overlays: a warning keeps trust
        code, result = check(FAIL / "perm", "--context-root", FAIL / "gpl-clean-twin")
        self.assertEqual((code, result["findings"]), (0, []))

    def test_untrust_propagates_to_the_citing_root(self):
        # perm rests on an untrusted root, so perm is untrusted in turn: docs' reference to a
        # perm fact that itself reaches nothing untrusted still fails.
        with tempfile.TemporaryDirectory() as tmp:
            perm = pathlib.Path(tmp) / "perm"
            shutil.copytree(FAIL / "perm", perm)
            (perm / "qchip.spec.yaml").write_text(chip("qchip", facts=fact("q")).replace(
                "trm", "trm"), encoding="utf-8")
            docs = pathlib.Path(tmp) / "docs"
            shutil.copytree(FAIL / "docs", docs)
            (docs / "dchip.spec.yaml").write_text(chip("dchip", facts=inference(
                "a", "qchip@fc-perm#q")), encoding="utf-8")
            code, result = check(docs, "--context-root", perm, "--context-root",
                                 UNTRUSTED / "dup-repos")
            self.assertEqual(code, 1)
            f = only(errors(result))
            self.assertIn("reference 'qchip@fc-perm#q' rests on root fc-perm, which is "
                          "untrusted", f["message"])
            code, result = check(docs, "--context-root", perm, "--context-root", FAIL / "gpl")
            self.assertEqual(code, 1)  # perm's own reference fails the gate: untrusted too


class TrustOrder(TempRoots):
    def test_untrust_found_late_reaches_earlier_citations(self):
        """Roots in the order docs, A, B, C; C is untrusted from the start. Each citation rests
        on a clean fact whose root has a sibling fact that is not clean, so no reach crosses
        an untrusted root on its own: B becomes untrusted in the reference pass (its fact p
        rests on C), after A's reference to B's clean q resolved; A becomes untrusted in the
        trust pass; and docs' reference to A's clean s fails only on the pass after that (a
        fixed point, not one sweep)."""
        b = self.root("b", {"board-specs.yaml": marker("rb"),
                            "bchip.spec.yaml": chip("bchip", facts=fact("q") + inference(
                                "p", "gchip@fc-gpl#gfact"))})
        a = self.root("a", {"board-specs.yaml": marker("ra"),
                            "achip.spec.yaml": chip("achip", facts=fact("s") + inference(
                                "t", "bchip@rb#q"))})
        docs = self.root("docs", {"board-specs.yaml": marker("rd"),
                                  "dchip.spec.yaml": chip("dchip", facts=inference(
                                      "x", "achip@ra#s"))})
        code, result = check(docs, "--context-root", a, "--context-root", b,
                             "--context-root", UNTRUSTED / "dup-repos")
        self.assertEqual(code, 1)
        f = only(errors(result))
        self.assertIn("reference 'achip@ra#s' rests on root ra, which is untrusted",
                      f["message"])

    def test_duplicate_fact_id_in_the_own_root_is_ambiguous(self):
        base = chip(facts=fact("a"))
        over = overlay(facts=fact("a"), head="resources:\n  documents:\n"
                       '    - {name: trm, class: databook, title: TRM, url: "https://example.invalid/t"}\n')
        other = chip("other", facts=inference("b", "widgetchip#a"))
        root = self.root("r", {"board-specs.yaml": marker(), "w.spec.yaml": base,
                               "o.spec.yaml": over, "other.spec.yaml": other})
        code, result = check(root)
        self.assertEqual(code, 1)
        f = only(errors(result, "other.spec.yaml"))
        self.assertIn("reference 'widgetchip#a' is ambiguous: spec 'widgetchip' declares fact "
                      "'a' more than once", f["message"])


class Roots(TempRoots):
    def test_usage_errors(self):
        a = self.root("a", {"board-specs.yaml": marker("a")})
        inner = self.root("a/inner", {"board-specs.yaml": marker("i")})
        b = self.root("b", {"board-specs.yaml": marker("b")})
        cases = [
            ([a, "--context-root", a], "same root"),
            ([a, a], "same root"),
            ([a, pathlib.Path(str(a) + "/.")], "same root"),
            ([a, "--context-root", inner], "sits inside"),
            ([inner, "--context-root", a], "sits inside"),
            ([a, inner], "sits inside"),
            ([self.tmp / "nothing"], "not a directory"),
        ]
        for argv, text in cases:
            code, result = check(*argv)
            self.assertEqual((code, result.get("error")), (2, "usage"), argv)
            self.assertIn(text, result["findings"][0]["message"])
        code, result = check(a, b)  # separate roots run; a holds inner's marker, a finding
        self.assertEqual(code, 1)
        self.assertIn("nested board-specs.yaml", need(errors(result))[0]["message"])

    def test_root_without_marker_is_exit_3(self):
        d = self.tmp / "empty"
        d.mkdir()
        code, result = check(d)
        self.assertEqual((code, result.get("error")), (3, "precondition"))
        self.assertEqual(set(result), {"ok", "error", "roots", "specs", "stubs", "findings"})

    def test_symbolic_links(self):
        a = self.root("a", {"board-specs.yaml": marker("a"), "x.spec.yaml": chip("x")})
        (a / "link.spec.yaml").symlink_to(a / "x.spec.yaml")
        code, result = check(a)
        self.assertEqual(code, 1)
        self.assertIn("symbolic link in a spec root", need(errors(result))[0]["message"])
        b = self.root("b", {"board-specs.yaml": marker("b")})
        code, result = check(b, "--context-root", a)
        self.assertEqual(code, 2)
        via = self.tmp / "via"
        via.symlink_to(b)
        code, result = check(via)
        self.assertEqual(code, 1)
        self.assertIn("reached through, a symbolic link", need(errors(result))[0]["message"])
        c = self.root("c", {"board-specs.yaml": marker("c")})
        self.assertEqual(check(c, "--context-root", via)[0], 2)

    def test_duplicate_root_names(self):
        a = self.root("a", {"board-specs.yaml": marker("same")})
        b = self.root("b", {"board-specs.yaml": marker("same")})
        c = self.root("c", {"board-specs.yaml": marker("c")})
        code, result = check(a, "--context-root", b)
        self.assertEqual(code, 1)
        self.assertEqual(len(errors(result)), 2)  # never downgraded: it decides resolution
        self.assertIn("root name 'same' is also the name of", need(errors(result))[0]["message"])
        self.assertEqual(need(errors(result))[0]["line"], 5)  # at the name
        code, result = check(c, "--context-root", a, "--context-root", b)  # both context
        self.assertEqual((code, len(errors(result))), (1, 2))

    def test_marker_spdx(self):
        cases = {
            "[GPL-2.0]": "write it as 'GPL-2.0-only'",
            "[gpl-2.0-only]": "write it as 'GPL-2.0-only'",
            "[GPL-2.0+]": "write it as 'GPL-2.0-or-later'",
            "[GPL-2.0-only, GPL-2.0]": "accepts lists GPL-2.0-only twice",
            "[Nonesuch-1.0]": "unknown SPDX license identifier",
        }
        for i, (accepts, text) in enumerate(cases.items()):
            r = self.root(f"m{i}", {"board-specs.yaml": marker(accepts=accepts)})
            code, result = check(r)
            self.assertEqual(code, 1, accepts)
            self.assertTrue(any(text in f["message"] for f in errors(result)), (accepts, result))
        r = self.root("lic", {"board-specs.yaml": marker(lic="mainline")})
        self.assertEqual([f["message"][:22] for f in errors(check(r)[1])],
                         ["license: unknown SPDX "])
        r = self.root("dupspell", {"board-specs.yaml": marker(accepts="[GPL-2.0-only, GPL-2.0]")})
        self.assertEqual(len(errors(check(r)[1])), 2)  # the second spelling, and the repeat

    def test_degenerate_markers(self):
        for i, text in enumerate([marker(name='""'), marker(name="' '"), marker(name="'a\\n'"),
                                  marker(layer="vendor"), HDR + "format: 2\n",
                                  marker().replace("license: CC-BY-4.0\n", ""),
                                  marker(accepts="[' ']"), marker(accepts="['']")]):
            r = self.root(f"d{i}", {"board-specs.yaml": text.replace("'a\\n'", '"a\\n"'),
                                    "x.spec.yaml": chip("x")})
            code, result = check(r)
            self.assertEqual(code, 1, text)
            self.assertEqual(result["specs"], 0)  # an invalid marker's specs are not read

    def test_empty_root_passes(self):
        r = self.root("e", {"board-specs.yaml": marker()})
        code, result = check(r)
        self.assertEqual((code, result["specs"], result["findings"]), (0, 0, []))

    def test_files_discovery_would_pass_over(self):
        r = self.root("r", {"board-specs.yaml": marker(), "sub/board-specs.yaml": marker("n"),
                            "A.SPEC.YAML": "x", "b.spec.yml": "x", "c.facts.yaml": "x",
                            "d.spec.md": "x", "notes.yaml": "ignored", "e.spec.yaml": ""})
        code, result = check(r)
        self.assertEqual(code, 1)
        by_file = {pathlib.Path(f["path"]).name: f["message"] for f in errors(result)}
        self.assertIn("nested board-specs.yaml", by_file["board-specs.yaml"])
        self.assertIn("name it *.spec.yaml", by_file["A.SPEC.YAML"])
        self.assertIn("name it *.spec.yaml", by_file["b.spec.yml"])
        self.assertIn("a facts file does not belong", by_file["c.facts.yaml"])
        self.assertIn("a format 1 spec", by_file["d.spec.md"])
        self.assertIn("an empty file", by_file["e.spec.yaml"])
        self.assertNotIn("notes.yaml", by_file)


class BoardFixtures(unittest.TestCase):
    """board-expert's good, bad and vendor roots in format 2."""

    BAD = {
        "alias-clash.spec.yaml": ["alias 'fineip' is the id of another spec"],
        # the declaration the alias collides with is in conflict too (round 1, item 6)
        "fineip.spec.yaml": ["spec id 'fineip' is also an alias in bad:alias-clash.spec.yaml"],
        "assumption-unresolved.spec.yaml": ["assumption 'same-silicon' is not in this file"],
        "cyc-a.spec.yaml": ["parts form a cycle: cyc-a -> cyc-b -> cyc-a"],
        "cyc-b.spec.yaml": ["parts form a cycle: cyc-a -> cyc-b -> cyc-a"],
        "doc-class.spec.yaml": ["a doc citation names document 'widget-trm' of class databook"],
        "doc-unresolved.spec.yaml": ["document 'nosuchdoc' is not in this file"],
        "dup-a.spec.yaml": ["spec id 'dupchip' is also declared by bad:dup-b.spec.yaml"],
        "dup-b.spec.yaml": ["spec id 'dupchip' is also declared by bad:dup-a.spec.yaml",
                            "fact id 'reset-time' is also used by bad:dup-a.spec.yaml"],
        "dup-doc-name.spec.yaml": ["documents entry 'widget-trm' is listed twice"],
        "dup-fact-id.spec.yaml": ["fact id 'reset-time' is used twice in this file"],
        "dup-premise.spec.yaml": ["'dup-premise#reset-time' names dup-premise@bad#reset-time, "
                                  "as '#reset-time' already does"],
        "format1.spec.md": ["a format 1 spec in a format 2 root"],
        "instance-not-ip.spec.yaml": ["instance 'uart1': 'fineboard' is not an ip spec"],
        "internal-doc.spec.yaml": ["documents entry 'secret-trm': access: internal under a "
                                   "public root"],
        "irq-mismatch.spec.yaml": ["intid 150 does not agree with SPI 121 (INTID 153)"],
        "lines-backwards.spec.yaml": ["lines [9, 4] run backwards"],
        "misnamed.spec.yml": ["name it *.spec.yaml"],
        "notice-repo.spec.yaml": ["a notice names repos entry 'linux', which is not in this "
                                  "file"],
        "overlay-fact-clash.spec.yaml": ["fact id 'reset-time' is also used by "
                                         "bad:finechip.spec.yaml"],
        "overlay-instances.spec.yaml": ["the target 'fineboard' is of kind board, which has "
                                        "no instances"],
        "overlay-section.spec.yaml": ["section 'quick-facts' is not a section of the target, "
                                      "kind ip"],
        "page-bounds.spec.yaml": ["page '92' is outside the 80 pages of document 'widget-trm'"],
        "page-zeros.spec.yaml": ["page '040': write '40'"],
        "paged-standard.spec.yaml": ["document 'arm-arm' is paged, so a standard locator needs"],
        "pages-backwards.spec.yaml": ["pages ['9', '4'] run backwards"],
        "parts-dangling.spec.yaml": ["parts entry 'missingsoc' resolves to no spec"],
        "path-unlisted.spec.yaml": ["'drivers/other.c' is not in the files of repos entry "
                                    "'linux'"],
        "placeholder.spec.yaml": ["name: unsubstituted template placeholder '<Chip name>'"],
        "private-tool.spec.yaml": ["via 'skill:acme-board-tools' is not a public skill"],
        "repo-ref.spec.yaml": ["which pins a ref, not a commit"],
        "self-relates.spec.yaml": ["'#reset-time' names the fact itself"],
        "series-target.spec.yaml": ["series target 'linux' names no repos entry"],
        "uncitable-doc.spec.yaml": ["document 'widget-trm' is marked cite: false"],
        "unknownkind.spec.yaml": ["'widget' is not one of", "unknown key 'id'",
                                  "unknown key 'name'"],
        "variant-of-dangling.spec.yaml": ["variant_of 'nosuchbase' resolves to no spec"],
        "variant-of-ip.spec.yaml": ["variant_of 'fineip' is not a board spec (kind ip)"],
    }

    def test_bad_root_each_file_has_its_defect_and_no_other(self):
        code, result = check(CHECK / "bad_root")
        self.assertEqual(code, 1)
        self.assertEqual(warnings(result), [])
        got: dict = {}
        for f in errors(result):
            got.setdefault(pathlib.Path(f["path"]).name, []).append(f["message"])
        self.assertEqual(set(got), set(self.BAD))
        for name, wanted in self.BAD.items():
            self.assertEqual(len(got[name]), len(wanted), (name, got[name]))
            for text in wanted:
                self.assertTrue(any(text in m for m in got[name]), (name, text, got[name]))
        present = {p.name for p in (CHECK / "bad_root").iterdir()} - {"board-specs.yaml"}
        self.assertEqual(present - set(self.BAD), {"finechip.spec.yaml", "fineboard.spec.yaml"})

    def test_load_failures_block_references_into_their_root(self):
        code, result = check(CHECK / "bad_load_root")
        self.assertEqual(code, 1)
        got = {(pathlib.Path(f["path"]).name, f["message"].split(":")[0]) for f in errors(result)}
        self.assertEqual({n for n, _ in got}, {"broken.spec.yaml", "colon.spec.yaml",
                                              "refers.spec.yaml"})
        f = only(errors(result, "refers.spec.yaml"))
        self.assertIn("reference 'broken#anything' resolves to nothing", f["message"])
        msgs = {pathlib.Path(f["path"]).name: f["message"] for f in errors(result)}
        self.assertIn("expected ',' or ']'", msgs["broken.spec.yaml"])
        self.assertIn("mapping values are not allowed here", msgs["colon.spec.yaml"])

    def test_findings_point_at_the_value(self):
        _, result = check(CHECK / "bad_root")
        at = {pathlib.Path(f["path"]).name: (f["line"], f["column"]) for f in errors(result)}
        self.assertEqual(at["page-bounds.spec.yaml"], (17, 62))   # the "92"
        self.assertEqual(at["irq-mismatch.spec.yaml"], (14, 42))  # the intid value
        self.assertEqual(at["placeholder.spec.yaml"], (7, 7))     # the name value
        self.assertEqual(at["parts-dangling.spec.yaml"], (9, 9))  # the parts entry

    def test_good_root(self):
        good = CHECK / "good_root"
        code, result = check(good, "--public-skill", "widget-board-tools", "--require-license")
        self.assertEqual((code, result["findings"], result["specs"]), (0, [], 3))
        code, result = check(good)
        self.assertEqual(code, 1)
        f = only(errors(result))
        self.assertIn("via 'skill:widget-board-tools' is not a public skill", f["message"])

    def test_vendor_root(self):
        vendor, good = CHECK / "vendor_root", CHECK / "good_root"
        code, result = check(vendor, "--context-root", good, "--public-skill",
                             "widget-board-tools")
        self.assertEqual(code, 1)
        f = only(errors(result))
        self.assertIn("overlays 'nosuchboard' resolves to no spec", f["message"])
        self.assertEqual(len(warnings(result)), 2)
        for w in warnings(result):
            self.assertIn("2 overlays of 'widgetboard' in root acme", w["message"])
        code, result = check(vendor)
        self.assertEqual(len(errors(result)), 3)  # without the base, every overlay dangles

    def test_stubs(self):
        code, result = check(CHECK / "good_root", "--public-skill", "widget-board-tools",
                             "--stubs-from", CHECK / "stubs", "--stub", CHECK / "stub_good.md",
                             "--stub", CHECK / "stub_bad.md")
        self.assertEqual(code, 1)
        self.assertEqual(result["stubs"], 5)  # three stubs found, not-a-stub ignored, two named
        got = sorted((pathlib.Path(f["path"]).parent.name + "/" + pathlib.Path(f["path"]).name,
                      f["message"]) for f in errors(result))
        self.assertEqual(got, [
            ("broken-expert/SKILL.md", "stub spec id 'nosuchboard' resolves to no spec"),
            ("check/stub_bad.md", "stub spec id 'nosuchboard' resolves to no spec"),
            ("placeholder-expert/SKILL.md",
             "unsubstituted template placeholder '<Board display name>'"),
        ])
        at = {pathlib.Path(f["path"]).parent.name: (f["line"], f["column"])
              for f in errors(result)}
        self.assertEqual(at["broken-expert"], (6, 33))       # the `spec: nosuchboard` span
        self.assertEqual(at["placeholder-expert"], (3, 35))  # the placeholder
        code, result = check(CHECK / "good_root", "--stubs-from", CHECK / "nothing-here")
        self.assertEqual(code, 3)
        code, result = check(CHECK / "good_root", "--public-skill", "widget-board-tools",
                             "--stub", CHECK / "missing.md")
        self.assertIn("stub file not found", need(errors(result))[0]["message"])


class Rules(TempRoots):
    """One rule each, in temporary roots."""

    def one(self, files, *flags, root_marker=None):
        r = self.root(f"r{len(os.listdir(self.tmp))}",
                      {"board-specs.yaml": root_marker or marker(accepts="[GPL-2.0-only]"),
                       **files})
        return check(r, *flags)

    def test_placeholders(self):
        flagged = {
            "url": chip(docs='    - {name: trm, class: databook, title: TRM, '
                             'url: "https://example.invalid/<board>/trm.pdf"}\n'),
            "title": chip(facts=fact("a").replace("title: T a", "title: The <Board name> UART")),
            "html in claim": chip(facts=fact("a").replace("claim: C a.", "claim: Reached over <bus>.")),
            "escaped": chip(facts=fact("a").replace("claim: C a.", "claim: Over \\<bus\\>.")),
        }
        for what, text in flagged.items():
            code, result = self.one({"x.spec.yaml": text})
            self.assertEqual(code, 1, what)
            self.assertIn("unsubstituted template placeholder", need(errors(result))[0]["message"])
        clean = chip(repos=repo(), facts=src_fact("a").replace("symbol: S", "symbol: Foo<T>")
                     + fact("b").replace("claim: C b.", "claim: \"`<type number flags>`, "
                                                        "<https://example.invalid/x>, a <0 0 0>\"")
                     + "notices:\n  - {repo: linux, path: drivers/w.c, text: "
                       "\"Copyright <Some Author>\"}\n")
        code, result = self.one({"x.spec.yaml": clean})
        self.assertEqual((code, result["findings"]), (0, []))

    def test_placeholder_shapes(self):
        def claim(text):
            return chip(facts=fact("a").replace("claim: C a.", "claim: " + json.dumps(text)))

        flagged = ["Use <board *name*>.", "Use ![<board name>](https://example.invalid/x).",
                   "Over <soc-id> and more.", "A <SPDX identifier> here.",
                   "Over [the <bus>](https://example.invalid/b)."]
        clean = ["Include <linux/of.h> first.", "Mail <a@b.example>.",
                 "See <https://example.invalid/x>.", "Code `<board name>`.",
                 "Split <board `x` name>.", "A tuple <0 0 0>.", "```\n<board name>\n```"]
        for text in flagged:
            code, result = self.one({"x.spec.yaml": claim(text)})
            self.assertEqual(code, 1, text)
            self.assertIn("unsubstituted template placeholder", need(errors(result))[0]["message"])
        for text in clean:
            code, result = self.one({"x.spec.yaml": claim(text)})
            self.assertEqual((code, result["findings"]), (0, []), text)

    def test_stub_placeholder_position(self):
        stub = self.tmp / "stub" / "SKILL.md"
        stub.parent.mkdir()
        stub.write_text("---\nname: s\ndescription: A stub over x.\n---\n\nNot `<Board name>`.\n"
                        "\nCode `<Board name>` and then <Board name>.\n\nGive it `spec: x`.\n",
                        encoding="utf-8")
        code, result = self.one({"x.spec.yaml": chip("x")}, "--stub", stub)
        f = only(errors(result))
        self.assertIn("'<Board name>'", f["message"])
        self.assertEqual((f["line"], f["column"]), (8, 30))

    def test_long_page_numbers(self):
        long = "9" * 4400
        cases = [('{page: "%s"}' % long, "is outside the 80 pages"),
                 ('{page: "0%s"}' % long, "(no leading zeros)"),
                 ('{pages: ["%s", "1"]}' % long, "run backwards")]
        for at, want in cases:
            text = chip(facts="  - id: c\n    section: quick-facts\n    title: C\n    claim: C.\n"
                              f"    support: [{{class: databook, doc: trm, at: [{at}]}}]\n")
            code, result = self.one({"x.spec.yaml": text})
            self.assertEqual(code, 1, want)
            self.assertTrue(any(want in f["message"] for f in errors(result)), result)
            self.assertTrue(all(len(f["message"]) < 400 for f in result["findings"]))

    def test_context_alias_colliding_with_a_checked_id(self):
        checked = self.root("checked", {"board-specs.yaml": marker("c"),
                                        "x.spec.yaml": chip("x")})
        context = self.root("context", {"board-specs.yaml": marker("k"),
                                        "y.spec.yaml": chip("y", head="aliases: [x]\n")})
        code, result = check(checked, "--context-root", context)
        self.assertEqual(code, 1)
        f = only(errors(result))
        self.assertTrue(f["path"].endswith("checked/x.spec.yaml"))
        self.assertIn("spec id 'x' is also an alias in k:y.spec.yaml", f["message"])

    def test_anchor_rules(self):
        cases = {
            "dt-commit": (chip(repos=repo().replace('commit: "1a2b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d"',
                                                    "ref: main"),
                               facts="  - id: d\n    section: quick-facts\n    title: D\n    claim: D.\n"
                                     "    support:\n      - class: DT\n        anchors: [{repo: linux, "
                                     "path: drivers/w.c, node: soc}]\n"),
                          "pins a ref, not a commit"),
            "rtl-gate": (chip(repos=repo(lic="GPL-3.0-only"),
                              facts="  - id: r\n    section: quick-facts\n    title: R\n    claim: R.\n"
                                    "    support:\n      - class: rtl\n        design: d\n"
                                    "        revision: r1\n        module: m\n        anchors: "
                                    "[{repo: linux, path: drivers/w.c, lines: [1, 1]}]\n"),
                         "GPL-3.0-only is not accepted"),
            "premise-support-gate": (chip(repos=repo(lic="GPL-3.0-only"), facts=(
                "  - id: i\n    section: quick-facts\n    title: I\n    claim: I.\n"
                "    support:\n      - class: inference\n        premises:\n"
                "          - states: it is so\n            support:\n              - class: src\n"
                "                anchors: [{repo: linux, path: drivers/w.c, lines: [1, 1], symbol: S}]\n"
                "        derivation: so\n    todo: {check: hardware, text: check.}\n")),
                "GPL-3.0-only is not accepted"),
            "conflict-gate": (chip(repos=repo(lic="GPL-3.0-only"), facts=fact("c", (
                "    conflicts:\n      - reading: another reading\n        support:\n"
                "          - class: src\n            anchors: [{repo: linux, path: drivers/w.c, "
                "lines: [1, 1], symbol: S}]\n"))), "GPL-3.0-only is not accepted"),
            "instance-gate": (chip(repos=repo(lic="GPL-3.0-only"), head=(
                "instances:\n  - id: u\n    name: u\n    ip: widgetchip\n    reg: null\n    irq: null\n"
                "    clocks: []\n    todo: {check: document, text: find it.}\n    support:\n"
                "      - class: src\n        anchors: [{repo: linux, path: drivers/w.c, lines: [1, 1], "
                "symbol: S}]\n")), "GPL-3.0-only is not accepted"),
            "notice-gate": (chip(repos=repo(lic="GPL-3.0-only"), facts=fact("n") +
                                 "notices:\n  - {repo: linux, path: drivers/w.c, text: c}\n"),
                            "a notice names repos entry 'linux': GPL-3.0-only is not accepted"),
            "lines-equal-ok": (chip(repos=repo(), facts=src_fact("s").replace("[1, 2]", "[2, 2]")), None),
            "search-dir": (chip(repos=repo(path="drivers/"), facts=(
                "  - id: s\n    section: quick-facts\n    title: S\n    claim: S.\n"
                "    support:\n      - class: src\n        anchors: [{repo: linux, path: drivers/, "
                "search: nothing else}]\n")), None),
            "search-dir-unlisted": (chip(repos=repo(), facts=(
                "  - id: s\n    section: quick-facts\n    title: S\n    claim: S.\n"
                "    support:\n      - class: src\n        anchors: [{repo: linux, path: drivers/, "
                "search: nothing else}]\n")), "'drivers/' is not in the files"),
            "dup-files": (chip(repos=repo().replace("files: [{path: drivers/w.c, license_from: spdx-line}]",
                                                    "files: [{path: drivers/w.c, license_from: spdx-line}, "
                                                    "{path: drivers/w.c, license_from: notice}]")),
                          "lists 'drivers/w.c' twice in files"),
            "repos-license-bad": (chip(repos=repo(lic="GPL-2.0-only AND")), "license: "),
        }
        for what, (text, want) in cases.items():
            # instances need an ip spec; the chip names itself, which is not an ip spec
            code, result = self.one({"x.spec.yaml": text})
            msgs = [f["message"] for f in errors(result) if "not an ip spec" not in f["message"]]
            if want is None:
                self.assertEqual(msgs, [], what)
            else:
                self.assertTrue(any(want in m for m in msgs), (what, msgs))

    def test_require_license_gates_uncited_entries_once(self):
        text = chip(repos=repo(lic="GPL-3.0-only") + repo("other", "GPL-3.0-only"),
                    facts=src_fact("a"))
        code, result = self.one({"x.spec.yaml": text}, "--require-license")
        msgs = [f["message"] for f in errors(result)]
        self.assertEqual(len(msgs), 2, msgs)  # the anchor of 'linux'; 'other' as uncited
        self.assertTrue(any("repos entry 'other'" in m and "cited or not" in m for m in msgs))
        code, result = self.one({"x.spec.yaml": text})
        self.assertEqual(len(errors(result)), 1)

    def test_locators(self):
        def doc(pages="pages: 80", cls="databook"):
            return ('    - {name: trm, class: ' + cls + ', title: TRM, '
                    'url: "https://example.invalid/t.pdf"' + (", " + pages if pages else "") + "}\n")

        def cited(cls, at):
            return ("  - id: c\n    section: quick-facts\n    title: C\n    claim: C.\n"
                    f"    support: [{{class: {cls}, doc: trm, at: [{at}]}}]\n")

        ok = [(doc(), cited("databook", '{page: "80"}')), (doc(), cited("databook", '{page: "1"}')),
              (doc(), cited("databook", '{page: "D2-14"}')),
              (doc(), cited("databook", '{pages: ["4", "4a"]}')),
              (doc(None), cited("databook", '{page: "900"}')),
              (doc(None, "standard"), cited("standard", "{heading: Booting}")),
              (doc("pages: 9", "standard"), cited("standard", '{clause: "4.1"}')),
              (doc("pages: 9", "doc"), cited("doc", "{heading: Boot}"))]
        bad = [(doc(), cited("databook", '{page: "0"}'), "outside the 80 pages"),
               (doc(), cited("databook", '{page: "81"}'), "outside the 80 pages"),
               (doc(), cited("databook", '{pages: ["79", "81"]}'), "outside the 80 pages"),
               (doc(), cited("databook", '{page: "00"}'), "no leading zeros"),
               (doc("pages: 9", "standard"), cited("standard", "{heading: Boot}"),
                "standard locator needs"),
               (doc(cls="standard"), cited("databook", '{page: "1"}'),
                "a databook citation names document 'trm' of class standard"),
               (doc(), cited("standard", '{page: "1"}'),
                "a standard citation names document 'trm' of class databook")]
        for docs, facts in ok:
            code, result = self.one({"x.spec.yaml": chip(docs=docs, facts=facts)})
            self.assertEqual((code, result["findings"]), (0, []), facts)
        for docs, facts, want in bad:
            code, result = self.one({"x.spec.yaml": chip(docs=docs, facts=facts)})
            self.assertTrue(any(want in f["message"] for f in errors(result)), (facts, result))

    def test_rtl_doc_any_class_but_cite_false(self):
        rtl = ("  - id: r\n    section: quick-facts\n    title: R\n    claim: R.\n"
               "    support:\n      - {class: rtl, design: d, revision: r1, module: m, doc: trm, "
               "at: [{heading: FIFO}]}\n")
        code, result = self.one({"x.spec.yaml": chip(facts=rtl)})
        self.assertEqual((code, result["findings"]), (0, []))
        uncitable = chip(docs='    - {name: trm, class: doc, title: T, '
                              'url: "https://example.invalid/t", cite: false}\n', facts=rtl)
        code, result = self.one({"x.spec.yaml": uncitable})
        self.assertIn("cite: false", need(errors(result))[0]["message"])

    def test_ids_per_spec_id_per_root(self):
        base = chip(facts=fact("a"))
        over = overlay(facts=fact("a").replace("doc: trm", "doc: trm"), head="resources:\n  documents:\n"
                       '    - {name: trm, class: databook, title: TRM, url: "https://example.invalid/t"}\n')
        code, result = self.one({"w.spec.yaml": base, "o.spec.yaml": over})
        self.assertIn("fact id 'a' is also used by", need(errors(result))[0]["message"])
        # the same id in an instance row and a fact of one file: one record namespace
        same = chip(head="instances:\n  - id: a\n    name: a\n    ip: ipx\n    reg: null\n"
                         "    irq: null\n    clocks: []\n    todo: {check: document, text: t.}\n",
                    facts=fact("a"))
        ipx = (HDR + "format: 2\nkind: ip\nid: ipx\nname: X\ntriggers: [ipx]\nresources:\n"
               "  documents:\n    - {name: t, class: doc, title: T, url: \"https://example.invalid/t\"}\n"
               "facts: []\n")
        code, result = self.one({"w.spec.yaml": same, "ipx.spec.yaml": ipx})
        self.assertIn("fact id 'a' is used twice in this file", need(errors(result))[0]["message"])

    def test_assumption_rules(self):
        reg = "assumptions:\n  - {id: s, text: t}\n  - {id: s, text: u}\n"
        code, result = self.one({"x.spec.yaml": chip(head=reg)})
        self.assertIn("assumption id 's' is used twice", need(errors(result))[0]["message"])
        premise = ("  - id: i\n    section: quick-facts\n    title: I\n    claim: I.\n"
                   "    support:\n      - class: inference\n        premises:\n"
                   "          - assumption: nope\n        derivation: so\n"
                   "    todo: {check: hardware, text: check.}\n")
        code, result = self.one({"x.spec.yaml": chip(facts=premise)})
        self.assertIn("assumption 'nope' is not in this file", need(errors(result))[0]["message"])

    def test_composition_rules(self):
        board = (HDR + "format: 2\nkind: board\nid: b\nname: B\ntriggers: [b]\nparts: [b]\n"
                 "cache: c1\nresources:\n  documents:\n    - {name: trm, class: databook, "
                 "title: T, url: \"https://example.invalid/t\"}\nfacts: []\n")
        code, result = self.one({"b.spec.yaml": board})
        self.assertIn("parts form a cycle: b -> b", need(errors(result))[0]["message"])
        variant = board.replace("parts: [b]", "parts: [x]\nvariant_of: b").replace("id: b", "id: v")
        code, result = self.one({"b.spec.yaml": board.replace("parts: [b]", "parts: [x]"),
                                 "v.spec.yaml": variant,
                                 "x.spec.yaml": chip("x", head="cache: c2\n")})
        msgs = [f["message"] for f in result["findings"]]
        self.assertEqual(code, 0, msgs)
        self.assertEqual(sum("names cache 'c2'" in m for m in msgs), 2)  # warnings, both boards
        selfv = board.replace("parts: [b]", "parts: [x]\nvariant_of: b")
        code, result = self.one({"b.spec.yaml": selfv, "x.spec.yaml": chip("x")})
        self.assertIn("variant_of names the spec itself", need(errors(result))[0]["message"])
        alias = chip("y", head="aliases: [shared]\n")
        code, result = self.one({"y.spec.yaml": alias,
                                 "z.spec.yaml": chip("z", head="aliases: [shared]\n")})
        self.assertEqual(len(errors(result)), 2)
        self.assertIn("also an alias of another spec", need(errors(result))[0]["message"])

    def test_overlay_layer_order(self):
        vendor = self.root("vendor", {"board-specs.yaml": marker("v", layer="product"),
                                      "widgetchip.spec.yaml": chip()})
        public = self.root("public", {"board-specs.yaml": marker("p"),
                                      "o.spec.yaml": overlay()})
        code, result = check(public, vendor)
        self.assertEqual(code, 1)
        self.assertIn("an overlay merges after its target", need(errors(result))[0]["message"])
        code, result = check(vendor, public.parent / "public")  # same layer order either way
        self.assertEqual(code, 1)

    def test_public_privacy_only_under_public(self):
        files = {"x.spec.yaml": chip(docs='    - {name: trm, class: databook, title: T, '
                                          'url: "https://example.invalid/t", access: internal}\n')}
        self.assertEqual(self.one(files)[0], 1)
        self.assertEqual(self.one(files, root_marker=marker(layer="local"))[0], 0)

    def test_degenerate_references(self):
        for ref in ("#", "", " ", "#a\n", "x@#a", "@r#a", "#A", "x@r#"):
            text = chip(facts=fact("a") + inference("b", "#a").replace('"#a"', json.dumps(ref)))
            code, result = self.one({"x.spec.yaml": text})
            self.assertEqual(code, 1, ref)
            self.assertEqual(result["specs"], 0, ref)  # refused by the schema, before any check


class WorkedExample(unittest.TestCase):
    def test_only_the_slice_elisions_remain(self):
        code, result = check(WORKED / "docs", WORKED / "permissive", WORKED / "gpl",
                             "--require-license")
        self.assertEqual(code, 1)
        got = sorted(f["message"] for f in result["findings"])
        # The permissive slice elides four documents ("also rpi-docs-legacy-boot, tfa-rpi4,
        # bcm2711-peripherals and gic400-trm, as in the base") and the fact patch-words.
        self.assertEqual(len(got), 5, got)
        for name in ("rpi-docs-legacy-boot", "tfa-rpi4", "bcm2711-peripherals", "gic400-trm"):
            self.assertTrue(any(f"document '{name}' is not in this file" in m for m in got), name)
        self.assertTrue(any("reference '#patch-words' resolves to nothing" in m for m in got))
        for f in result["findings"]:
            self.assertTrue(f["path"].endswith("permissive/bcm2711.spec.yaml"))

    def test_the_gpl_overlay_cannot_sit_in_the_docs_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs = pathlib.Path(tmp) / "docs"
            shutil.copytree(WORKED / "docs", docs)
            shutil.copy(WORKED / "gpl" / "bcm2711.spec.yaml", docs / "bcm2711-gpl.spec.yaml")
            code, result = check(docs)
            self.assertEqual(code, 1)
            messages = [f["message"] for f in errors(result)]
            self.assertTrue(any("GPL-2.0-only is not accepted by root hardware-specs-docs" in m
                                for m in messages))
            # the GPL inference names the docs root, which is this root: it resolves here
            self.assertFalse(any("resolves to nothing" in m for m in messages))


class Output(TempRoots):
    def test_json_shape(self):
        code, result = check(CHECK / "good_root", "--public-skill", "widget-board-tools")
        self.assertEqual(set(result), {"ok", "roots", "specs", "stubs", "findings"})
        self.assertEqual(result["roots"], [{"path": str(CHECK / "good_root"), "name": "good",
                                            "layer": "public", "context": False}])
        code, result = check(CHECK / "bad_root")
        for f in result["findings"]:
            self.assertEqual(set(f), {"path", "line", "column", "level", "message"})

    def test_usage_failure_object(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = spec_cli.main(["check", "--json"])
        self.assertEqual(code, 2)
        result = json.loads(out.getvalue())
        self.assertEqual(set(result), {"ok", "error", "roots", "specs", "stubs", "findings"})
        self.assertEqual(result["findings"][0]["level"], "error")

    def test_text_output_and_exit_codes(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = spec_cli.main(["check", str(CHECK / "vendor_root"), "--context-root",
                                  str(CHECK / "good_root")])
        self.assertEqual(code, 1)
        lines = out.getvalue().splitlines()
        self.assertTrue(lines[-1].startswith("2 root(s), 6 spec file(s), 0 stub(s): 1 error(s), 3 "))
        self.assertTrue(any(": error: overlays 'nosuchboard'" in line for line in lines))
        self.assertTrue(any(": warning: context root: tools entry" in line for line in lines))


if __name__ == "__main__":
    unittest.main()
