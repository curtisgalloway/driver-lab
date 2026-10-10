# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""SF2-7a: typed payloads, exact inventories, generated lists and facts-file gates.

Every refusal asserts an exit code and a diagnostic; source commands use local fixtures.
"""

import contextlib
import copy
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import inventory
import peripheral
import records
import render_md
import spec
import specload
from test_schema import dump

FIX = HERE / "fixtures" / "peripheral"
SOURCE = HERE.parents[1] / "hardware-investigator" / "examples" / "sources" / "widget-linux"


def run(*args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = spec.main([*map(str, args), "--json"])
    return code, json.loads(out.getvalue())


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="sf2-7a-test-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "root"
        self.root.mkdir()
        shutil.copy(FIX / "board-specs.yaml", self.root)
        self.file = self.root / "widget.spec.yaml"
        self.data = specload.load_strict(FIX / "widget.spec.yaml")
        self.write()

    def write(self):
        self.file.write_text(dump(self.data), encoding="utf-8")

    def check(self):
        self.write()
        return run("check", self.root)

    def invalid(self, text, schema=False):
        self.write()
        code, result = run("validate", self.file) if schema else run("check", self.root)
        self.assertEqual(code, 1, result)
        self.assertTrue(any(text in f["message"] for f in result["findings"]), result)

    def checker(self):
        self.write()
        return spec._run_check(types.SimpleNamespace(
            roots=[self.root], context_root=[], require_license=False, public_skill=[]))


class Peripheral(Fixture):

    def test_widget_validates_and_renders_register_sequence_and_layout(self):
        self.assertEqual(run("validate", self.file)[0], 0)
        self.assertEqual(self.check()[0], 0)
        code, result = run("render", self.root, "--format", "md", "--with-status")
        self.assertEqual(code, 0, result)
        view = result["markdown"]
        for text in (render_md.escape("Register map (generated)"), "WIDGET_CTRL", "0x0", "write 0 to CTRL",
                     "seq-init.s1", "reg-ctrl.en", "widget_frame", "4 bytes", "frame_payload"):
            self.assertIn(text, view)
        self.assertIn("Register `WIDGET_CTRL` at `0x0`, 32 bits, rw.", view)

    def test_closed_payloads_and_no_citation_aliases(self):
        base = copy.deepcopy(self.data)
        cases = [(lambda d: d["facts"][0]["data"]["register"].update(alias="CTRL"), "alias"),
                 (lambda d: d["facts"][0]["data"]["fields"][0].update(unknown=True), "unknown"),
                 (lambda d: d["facts"][3]["data"]["sequence"]["steps"][0].update(unknown=True), "unknown"),
                 (lambda d: d["facts"][3]["data"]["sequence"]["order"][0].update(unknown=True), "unknown"),
                 (lambda d: d["facts"][4]["data"]["layout"].update(unknown=True), "unknown"),
                 (lambda d: d["facts"][4]["data"]["layout"]["fields"][0].update(unknown=True), "unknown"),
                 (lambda d: d["facts"][0]["support"][0].update(**{"class": "impl"}), "is not one of"),
                 (lambda d: d["facts"][0]["support"][0].update(**{"class": "ref"}), "is not one of"),
                 (lambda d: d["facts"][0].update(assessment="bug"), "assessment")]
        for change, message in cases:
            self.data = copy.deepcopy(base)
            change(self.data)
            with self.subTest(message=message):
                self.invalid(message, schema=True)

    def test_register_required_shape_and_canonical_scalars(self):
        base = copy.deepcopy(self.data)
        for name in ("name", "offset", "width", "access"):
            self.data = copy.deepcopy(base)
            del self.data["facts"][0]["data"]["register"][name]
            self.invalid("required property", schema=True)
        for name, values in (("name", ["", " ", "-CTRL", "CTRL\n"]),
                             ("offset", [0, "0x00", "0X1", "0xA", "0x0\n"]),
                             ("width", [0, -1, "32", True]), ("access", ["", "read-write"]),
                             ("reset", [1, "0x00"])):
            for value in values:
                self.data = copy.deepcopy(base)
                self.data["facts"][0]["data"]["register"][name] = value
                self.write()
                self.assertEqual(run("validate", self.file)[0], 1, (name, value))

    def test_child_schema_shapes(self):
        base = copy.deepcopy(self.data)
        entries = [(0, ("fields", 0), ("id", "name", "bits", "meaning")),
                   (3, ("sequence", "steps", 0), ("id", "action")),
                   (3, ("sequence", "order", 0), ("before", "after")),
                   (4, ("layout", "fields", 0), ("id", "name", "offset", "size", "meaning"))]
        for index, path, names in entries:
            for name in names:
                self.data = copy.deepcopy(base)
                entry = self.data["facts"][index]["data"]
                for part in path:
                    entry = entry[part]
                del entry[name]
                self.invalid("required property", schema=True)
        for value in ([], [0], [0, 1, 2], [-1, 1], [True, 1], ["0", 1]):
            self.data = copy.deepcopy(base)
            self.data["facts"][0]["data"]["fields"][0]["bits"] = value
            self.write()
            self.assertEqual(run("validate", self.file)[0], 1, value)
        for name in ("name", "size", "fields"):
            self.data = copy.deepcopy(base)
            del self.data["facts"][4]["data"]["layout"][name]
            self.invalid("required property", schema=True)

    def test_nested_support_rules_apply_to_every_payload_row(self):
        base = copy.deepcopy(self.data)
        for index, path in ((0, ("fields", 0)), (3, ("sequence", "steps", 0)),
                            (3, ("sequence", "order", 0)), (4, ("layout", "fields", 0))):
            self.data = copy.deepcopy(base)
            row = self.data["facts"][index]["data"]
            for part in path:
                row = row[part]
            row["support"] = [{"class": "inference", "premises": [{"fact": "#reg-baud"}],
                                "derivation": "So."}]
            self.invalid("require a todo", schema=True)

    def test_board_kinds_keep_payloads_and_requirements_out(self):
        for name in ("widgetboard", "widget-soc", "widget-pmic", "widget-uart"):
            data = specload.load_strict(HERE / "fixtures" / "valid" / (name + ".spec.yaml"))
            self.file.write_text(dump(data))
            marker = HERE / "fixtures" / "valid"
            self.assertEqual(run("validate", self.file, "--root", marker)[0], 0)
            fact = data["facts"][0]
            fact["data"] = {"register": self.data["facts"][0]["data"]["register"]}
            self.file.write_text(dump(data))
            code, result = run("validate", self.file, "--root", marker)
            self.assertEqual(code, 1, result)
            fact.pop("data")
            fact["requirement"] = "as-implemented"
            self.file.write_text(dump(data))
            code, result = run("validate", self.file, "--root", marker)
            self.assertEqual(code, 1, result)

    def test_optional_payload_lists_are_nonempty(self):
        base = copy.deepcopy(self.data)
        for index, path in ((0, ("fields",)), (3, ("sequence", "steps")),
                            (3, ("sequence", "order")), (4, ("layout", "fields"))):
            self.data = copy.deepcopy(base)
            entry = self.data["facts"][index]["data"]
            for part in path[:-1]:
                entry = entry[part]
            entry[path[-1]] = []
            self.invalid("non-empty", schema=True)
        self.data = copy.deepcopy(base)
        self.data["areas"] = []
        self.invalid("non-empty", schema=True)

    def test_layout_sizes_are_positive_integers(self):
        base = copy.deepcopy(self.data)
        for value in (0, -1, True, "4"):
            for field in (False, True):
                self.data = copy.deepcopy(base)
                row = self.data["facts"][4]["data"]["layout"]
                if field:
                    row = row["fields"][0]
                row["size"] = value
                self.write()
                self.assertEqual(run("validate", self.file)[0], 1, (field, value))

    def test_payload_exclusive_and_section_required_types(self):
        base = copy.deepcopy(self.data)
        for index, expected in ((0, "register"), (3, "sequence"), (4, "layout")):
            self.data = copy.deepcopy(base)
            self.data["facts"][index]["claim"] = "Claim."
            del self.data["facts"][index]["data"]
            self.invalid("required property", schema=True)
        self.data = copy.deepcopy(base)
        self.data["facts"][0]["section"] = "identity"
        self.data["facts"][0]["data"]["layout"] = copy.deepcopy(base["facts"][4]["data"]["layout"])
        self.invalid("valid under each", schema=True)
        self.data = copy.deepcopy(base)
        self.data["facts"][0]["data"] = {"fields": base["facts"][0]["data"]["fields"]}
        self.invalid("register", schema=True)
        self.data = copy.deepcopy(base)
        self.data["facts"][4]["data"]["fields"] = base["facts"][0]["data"]["fields"]
        self.invalid("register", schema=True)

    def test_kind_identity_and_sections(self):
        base = copy.deepcopy(self.data)
        for key in ("id", "name", "resources"):
            self.data = copy.deepcopy(base)
            del self.data[key]
            self.invalid("required property", schema=True)
        for section in ("quick-facts", "findings", "", "registers\n"):
            self.data = copy.deepcopy(base)
            self.data["facts"][0]["section"] = section
            self.invalid("is not one of", schema=True)
        self.data = copy.deepcopy(base)
        self.data["facts"][3].pop("claim")
        self.invalid("claim", schema=True)

    def test_hw_required_needs_own_document_support(self):
        self.data["facts"][0]["requirement"] = "hw-required"
        self.invalid("hw-required needs document-class support")

    def test_comment_explained_needs_real_comment_anchor(self):
        self.data["facts"][0]["requirement"] = "comment-explained"
        self.invalid("comment-explained needs a comment anchor")

    def test_inherited_requirements_on_steps_and_order(self):
        sequence = self.data["facts"][3]
        sequence["requirement"] = "hw-required"
        sequence["support"] = [{"class": "databook", "doc": "trm", "at": [{"page": "4"}]}]
        self.invalid("hw-required needs document-class support")
        sequence["data"]["sequence"]["steps"][0]["requirement"] = "driver-choice"
        self.assertEqual(self.check()[0], 0)
        sequence["data"]["sequence"]["order"][0]["support"][0]["anchors"][0].pop("comment")
        self.invalid("comment-explained needs a comment anchor")

    def test_requirement_enum_and_roles(self):
        base = copy.deepcopy(self.data)
        for value in ("", "hw", "hw-required\n", "suspect"):
            self.data = copy.deepcopy(base)
            self.data["facts"][3]["requirement"] = value
            self.invalid("is not one of", schema=True)
        for role in ("source", "target", "impl", "ref"):
            self.data = copy.deepcopy(base)
            self.data["resources"]["repos"][0]["role"] = role
            self.write()
            self.assertEqual(run("validate", self.file)[0], 0)
        self.data["resources"]["repos"][0]["role"] = "implementation"
        self.invalid("is not one of", schema=True)

    def test_field_bits_order_and_width(self):
        for bits in ([2, 1], [0, 32]):
            self.data["facts"][0]["data"]["fields"][0]["bits"] = bits
            self.invalid("bits must be ordered and inside register width")

    def test_reset_width(self):
        self.data["facts"][0]["data"]["register"]["reset"] = "0x100000000"
        self.invalid("reset exceeds register width")

    def test_layout_field_bounds(self):
        self.data["facts"][4]["data"]["layout"]["fields"][0]["offset"] = "0x4"
        self.invalid("field exceeds layout size")

    def test_ids_duplicate_without_subkeys(self):
        field = copy.deepcopy(self.data["facts"][2]["data"]["fields"][0])
        self.data["facts"][2]["data"]["fields"].append(field)
        self.invalid("field or step id is listed twice")

    def test_order_unknown_step(self):
        self.data["facts"][3]["data"]["sequence"]["order"][0]["before"] = "missing"
        self.invalid("order names an unknown step")

    def test_order_self(self):
        self.data["facts"][3]["data"]["sequence"]["order"][0]["before"] = "s3"
        self.invalid("order cannot name the same step twice")

    def test_order_duplicate(self):
        order = self.data["facts"][3]["data"]["sequence"]["order"]
        order.append(copy.deepcopy(order[0]))
        self.invalid("ordering constraint is listed twice")

    def test_order_cycle(self):
        order = self.data["facts"][3]["data"]["sequence"]["order"]
        order.extend([{"before": "s3", "after": "s4"}, {"before": "s4", "after": "s2"}])
        self.invalid("ordering constraints form a cycle")

    def test_areas_shape_and_duplicates(self):
        self.data["areas"][0]["level"] = "uncertain"
        self.invalid("is not one of", schema=True)
        self.data["areas"][0]["level"] = "inferred"
        self.data["areas"].append(copy.deepcopy(self.data["areas"][0]))
        self.invalid("area is listed twice")

    def test_areas_required_and_closed(self):
        base = copy.deepcopy(self.data)
        for key in ("area", "level", "note"):
            self.data = copy.deepcopy(base)
            self.data["areas"][0].pop(key)
            self.invalid("required property", schema=True)
        self.data = copy.deepcopy(base)
        self.data["areas"][0]["extra"] = "Unknown"
        self.invalid("unknown key", schema=True)

    def test_open_questions_are_gaps(self):
        self.data["facts"][-1]["support"] = copy.deepcopy(self.data["facts"][4]["support"])
        self.invalid("should not be valid", schema=True)

    def test_target_mapping_role(self):
        fact = copy.deepcopy(self.data["facts"][0])
        fact.update(id="mapping", section="target", claim="The target uses CTRL.")
        fact.pop("data")
        self.data["facts"].append(fact)
        self.invalid("target facts need a repos entry with role: target")
        self.data["resources"]["repos"][0]["role"] = "target"
        self.assertEqual(self.check()[0], 0)

    def test_nested_support_citations_are_gated_and_checked(self):
        source = copy.deepcopy(self.data["resources"]["repos"][0])
        source.update(name="other", license="GPL-3.0-only")
        self.data["resources"]["repos"].append(source)
        child = self.data["facts"][0]["data"]["fields"][0]
        child["support"][0]["anchors"][0]["repo"] = "other"
        self.invalid("GPL-3.0-only is not accepted")
        source["license"] = "MIT"
        child["support"][0]["anchors"][0]["path"] = "unlisted.c"
        self.invalid("is not in the files")

    def test_nested_support_rules_and_references(self):
        child = self.data["facts"][0]["data"]["fields"][0]
        child["support"] = [{"class": "inference", "premises": [{"fact": "#missing"}],
                             "derivation": "So."}]
        self.invalid("require a todo", schema=True)
        child["todo"] = {"check": "hardware", "text": "Check the field."}
        self.invalid("resolves to nothing")
        child["support"][0]["premises"][0]["fact"] = "#reg-baud"
        self.assertEqual(self.check()[0], 0)

    def test_separate_steps_may_cite_the_same_premise(self):
        steps = self.data["facts"][3]["data"]["sequence"]["steps"]
        for step in steps[:2]:
            step["support"] = [{"class": "inference", "premises": [{"fact": "#reg-baud"}],
                                "derivation": "So."}]
            step["todo"] = {"check": "hardware", "text": "Check it."}
        self.assertEqual(self.check()[0], 0)
        steps[0]["support"][0]["premises"].append({"fact": "widget#reg-baud"})
        self.invalid("already does in this premise list")

    def test_subkeys_exist_only_for_supported_fields_and_steps(self):
        checker = self.checker()
        file = checker.files[0]
        self.assertEqual(set(file.records), {"reg-ctrl", "reg-baud", "reg-lcr", "seq-init", "frame",
                                             "baud-latch-test", "reg-ctrl.en", "seq-init.s1"})
        fresh = records.Freshness(checker)
        before = fresh.basis(file.records["reg-ctrl.en"])[0]
        file.records["reg-ctrl"].data["data"]["register"]["offset"] = "0x4"
        after = records.Freshness(checker).basis(file.records["reg-ctrl.en"])[0]
        self.assertNotEqual(before, after)

    def test_subkey_basis_tracks_parent_cited_resources(self):
        self.data["facts"][0]["support"] = copy.deepcopy(self.data["facts"][4]["support"])
        checker = self.checker()
        file = checker.files[0]
        self.assertIn("reg-ctrl.en", file.records)
        before = records.Freshness(checker).basis(file.records["reg-ctrl.en"])[0]
        file.documents["trm"][0]["sha256"] = "2" * 64
        after = records.Freshness(checker).basis(file.records["reg-ctrl.en"])[0]
        self.assertNotEqual(before, after)

    def test_subkey_duplicate_ids_are_refused(self):
        fields = self.data["facts"][0]["data"]["fields"]
        fields.append(copy.deepcopy(fields[0]))
        self.invalid("sub-key 'reg-ctrl.en' is used twice")

    def record(self, checker, key):
        file = checker.files[0]
        record = {"format": 2, "spec": "widget", "spec_file": "widget.spec.yaml",
                  "spec_sha256": "0" * 64, "canonical": "fact-v1",
                  "sources": [{"name": "linux", "commit": "1" * 40, "fetch": "ok"}],
                  "summary": {"pass": 1, "fail": 0, "gap": 0, "unverifiable": 0, "adjudicate": 0},
                  "verdicts": {key: {"verdict": "PASS", "date": "2026-10-09", "verifier": "reader A",
                                     "contrary_evidence": "none-found", "citation_precision": "exact",
                                     "basis": records.Freshness(checker).basis(file.records.get(key,
                                                                      file.records["reg-ctrl"]))[0]}}}
        dest = self.root / "resources"
        dest.mkdir(exist_ok=True)
        (dest / "widget.verify.yaml").write_text(dump(record))

    def test_subkey_record_current_and_wrong_subkey_refused(self):
        for key in ("reg-ctrl.en", "seq-init.s1"):
            self.record(self.checker(), key)
            checker = self.checker()
            self.assertFalse(any(f.level == "error" for f in checker.findings), checker.findings)
            row = next(r for r in checker.status[0]["rows"] if r["key"] == key)
            self.assertEqual((row["status"], row["verdict"]), ("current", "PASS"))
        for key in ("reg-lcr.format", "seq-init.s2", "frame.type", "reg-ctrl.missing"):
            self.record(self.checker(), key)
            self.invalid("has no field or step")

    def test_subkey_critical_inherits_second_reader_requirement(self):
        self.data["facts"][0]["critical"] = True
        self.record(self.checker(), "reg-ctrl.en")
        checker = self.checker()
        row = next((r for r in checker.status[0]["rows"] if r["key"] == "reg-ctrl.en"), None)
        self.assertIsNotNone(row)
        self.assertEqual(row["second_reader"], "missing")

    def test_generated_projections_equal_facts(self):
        file = self.checker().files[0]
        got = peripheral.generated(file)
        self.assertEqual(got["registers"], [dict(f["data"]["register"], fact=f["id"],
                                                fields=f["data"].get("fields", []))
                                              for f in self.data["facts"][:3]])
        self.assertEqual(got["verify"], [{"fact": "seq-init.s" + str(i), "text": text}
                                         for i, text in enumerate(("write 0 to CTRL", "write the divisor to BAUD",
                                                                  "write WIDGET_LCR_8N1 to LCR", "set WIDGET_CTRL_EN in CTRL"), 1)])
        self.assertEqual(got["questions"], [{"fact": "baud-latch-test", **self.data["facts"][-1]["todo"]}])
        self.assertEqual(got["references"], [{"type": "documents", **self.data["resources"]["documents"][0]},
                                             {"type": "repos", **self.data["resources"]["repos"][0]}])
        self.assertEqual(got["classes"], ["databook", "src"])

    def test_rendered_lists_equal_generated_data(self):
        checker = self.checker()
        got = peripheral.generated(checker.files[0])
        view = render_md.render(checker)
        self.assertTrue(got["questions"])
        for row in got["verify"]:
            self.assertEqual(view.count("- " + render_md.code(row["fact"]) + ": " + render_md.escape(row["text"])), 1)
        self.assertIn("| reg\\-ctrl | 0x0 | `WIDGET_CTRL` | 32 | rw | 0x0 |", view)
        self.assertIn("| reg\\-baud | 0x4 | `WIDGET_BAUD` | 32 | rw |  |", view)
        self.assertIn("| reg\\-lcr | 0x8 | `WIDGET_LCR` | 32 | rw |  |", view)
        self.assertIn("| baud\\-latch\\-test | hardware | " + render_md.escape(got["questions"][0]["text"]) + " |", view)
        self.assertIn("Support classes: `databook`, `src`.", view)
        for row in got["references"]:
            self.assertIn(render_md.escape(row["url"]), view)

    def test_nested_todos_and_requirement_overrides_in_lists(self):
        sequence = self.data["facts"][3]["data"]["sequence"]
        sequence["steps"][1]["requirement"] = "driver-choice"
        sequence["steps"][0]["todo"] = {"check": "hardware", "text": "Observe CTRL."}
        sequence["order"][0]["requirement"] = "as-implemented"
        self.data["facts"][1]["requirement"] = "as-implemented"
        got = peripheral.generated(self.checker().files[0])
        self.assertEqual([r["fact"] for r in got["verify"]],
                         ["reg-baud", "seq-init.s1", "seq-init.s3", "seq-init.s4", "seq-init.s2->s3"])
        self.assertEqual(got["questions"][0], {"fact": "seq-init.s1", "check": "hardware", "text": "Observe CTRL."})

    def test_facts_file_check_against_target_marker(self):
        facts = Path(self.tmp.name) / "answer.facts.yaml"
        data = copy.deepcopy(self.data)
        for key in ("id", "name", "areas"):
            data.pop(key)
        data["kind"] = "facts"
        for fact in data["facts"]:
            fact["section"] = "facts"
        facts.write_text(dump(data))
        code, result = run("check", facts, "--root", self.root, "--require-license")
        self.assertEqual((code, result["findings"]), (0, []))
        self.assertEqual(result["specs"], 1)
        (self.root / "board-specs.yaml").write_text("format: 2\nlayer: public\nname: docs\nlicense: CC-BY-4.0\naccepts: []\n")
        code, result = run("check", facts, "--root", self.root)
        self.assertEqual(code, 1)
        self.assertTrue(any("GPL-2.0-only is not accepted" in f["message"] for f in result["findings"]))

    def test_facts_checks_keep_resource_name_and_document_class_rules(self):
        data = {"format": 2, "kind": "facts", "resources": self.data["resources"],
                "facts": [dict(self.data["facts"][4], section="facts")]}
        file = Path(self.tmp.name) / "answer.facts.yaml"
        data["facts"][0]["support"][0]["doc"] = "missing"
        file.write_text(dump(data))
        code, result = run("check", file, "--root", self.root)
        self.assertEqual(code, 1)
        self.assertTrue(any("document 'missing'" in f["message"] for f in result["findings"]))

    def test_facts_mode_usage_errors(self):
        code, result = run("check", self.file, "--root", self.root)
        self.assertEqual(code, 2, result)
        code, result = run("check", self.file, "--root", self.root, "--require-verified", "pr")
        self.assertEqual(code, 2, result)


class Inventory(Fixture):
    def setUp(self):
        super().setUp()
        self.repo = Path(self.tmp.name) / "source"
        shutil.copytree(SOURCE, self.repo)
        for args in (("init", "-q"), ("add", "."), ("commit", "-q", "-m", "fixture")):
            subprocess.run(["git", "-C", str(self.repo), "-c", "user.name=Fixture",
                            "-c", "user.email=fixture@example.invalid", "-c", "commit.gpgsign=false", *args],
                           check=True, capture_output=True)
        self.commit = subprocess.run(["git", "-C", str(self.repo), "rev-parse", "HEAD"],
                                     check=True, capture_output=True, text=True).stdout.strip()
        self.data["resources"]["repos"][0]["commit"] = self.commit

    def inventory(self, *args):
        self.write()
        return run("inventory", self.file, "--repo", "linux=" + str(self.repo),
                   "--headers", "drivers/tty/serial/widget.c", *args)

    def test_exact_inventory_clean(self):
        code, result = self.inventory("--strict")
        self.assertEqual(code, 0, result)
        self.assertEqual({k: result[k] for k in ("names", "covered", "unknown", "absent", "omissions", "mismatches", "conflicts")},
                         {"names": 5, "covered": 5, "unknown": [], "absent": [], "omissions": [], "mismatches": [], "conflicts": []})

    def test_omitted_register_exact_report(self):
        del self.data["facts"][1]
        code, result = self.inventory("--strict")
        self.assertEqual(code, 1, result)
        self.assertEqual(result["omissions"], [{"name": "WIDGET_BAUD", "kind": "define", "path": "drivers/tty/serial/widget.c"}])
        self.assertEqual(result["mismatches"], [])
        self.assertEqual(self.inventory()[0], 0)

    def test_register_value_mismatch_exact_report(self):
        self.data["facts"][0]["data"]["register"]["offset"] = "0x10"
        code, result = self.inventory()
        self.assertEqual(code, 1, result)
        self.assertEqual(result["mismatches"], [{"name": "WIDGET_CTRL", "expected": "0x0", "actual": "0x10",
                                                "fact": "reg-ctrl", "path": "drivers/tty/serial/widget.c"}])

    def test_field_mask_mismatch_exact_report(self):
        self.data["facts"][0]["data"]["fields"][0]["bits"] = [1, 1]
        code, result = self.inventory()
        self.assertEqual(code, 1, result)
        self.assertEqual(result["mismatches"], [{"name": "WIDGET_CTRL_EN", "expected": "0x1", "actual": "0x2",
                                                "fact": "reg-ctrl.en", "path": "drivers/tty/serial/widget.c"}])

    def test_inventory_reads_pin_ignores_worktree_and_prose(self):
        source = self.repo / "drivers/tty/serial/widget.c"
        source.write_text(source.read_text().replace("0x04", "0x14"))
        subprocess.run(["git", "-C", str(self.repo), "add", "drivers/tty/serial/widget.c"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "-c", "user.name=Fixture",
                        "-c", "user.email=fixture@example.invalid", "-c", "commit.gpgsign=false",
                        "commit", "-q", "-m", "newer fixture"], check=True)
        source.write_text(source.read_text().replace("0x14", "0x24"))
        self.data["facts"][1]["claim"] = "BAUD at 0xff. WIDGET_BAUD is mentioned here."
        self.assertEqual(self.inventory("--strict")[0], 0)
        del self.data["facts"][1]["data"]
        self.data["facts"][1]["section"] = "identity"
        self.assertEqual(self.inventory("--strict")[0], 1)

    def test_inventory_missing_header_and_closed_path_fail(self):
        self.write()
        with mock.patch.object(inventory.resolve, "Repository", wraps=inventory.resolve.Repository) as reader:
            code, result = run("inventory", self.file, "--repo", "linux=" + str(self.repo), "--headers", "unlisted.h")
            reader.assert_not_called()
        self.assertEqual(code, 1, result)
        self.assertIn("closed files list", result["findings"][0]["message"])
        self.data["resources"]["repos"][0]["files"].append({"path": "missing.h", "license_from": "notice"})
        self.write()
        code, result = run("inventory", self.file, "--repo", "linux=" + str(self.repo), "--headers", "missing.h")
        self.assertEqual(code, 1, result)
        self.assertIn("path does not exist", result["findings"][0]["message"])

    def test_inventory_multiple_pins_need_selection(self):
        other = copy.deepcopy(self.data["resources"]["repos"][0])
        other["name"] = "other"
        self.data["resources"]["repos"].append(other)
        self.assertEqual(self.inventory()[0], 2)
        self.assertEqual(self.inventory("--pin", "linux")[0], 0)

    def test_inventory_map_only_pin_is_usage_error(self):
        entry = self.data["resources"]["repos"][0]
        entry.pop("commit")
        entry["ref"] = "main"
        self.data["facts"] = []
        code, result = self.inventory()
        self.assertEqual(code, 2, result)
        self.assertIn("immutable source pin", result["findings"][0]["message"])

    def test_inventory_conflict_and_absent_names(self):
        extra = copy.deepcopy(self.data["facts"][0])
        extra["id"] = "other-ctrl"
        extra["data"]["register"]["offset"] = "0x4"
        self.data["facts"].append(extra)
        code, result = self.inventory()
        self.assertEqual(code, 1, result)
        self.assertEqual(result["conflicts"], [{"name": "WIDGET_CTRL", "facts": ["reg-ctrl", "other-ctrl"],
                                               "values": ["0x0", "0x4"]}])
        extra["data"]["register"]["name"] = "ABSENT"
        code, result = self.inventory()
        self.assertEqual(code, 1, result)
        self.assertEqual(result["absent"], ["ABSENT"])

    def test_inventory_text_report_is_exact(self):
        del self.data["facts"][1]
        self.data["facts"][0]["data"]["register"]["offset"] = "0x10"
        self.write()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = spec.main(["inventory", str(self.file), "--repo", "linux=" + str(self.repo),
                              "--headers", "drivers/tty/serial/widget.c", "--strict"])
        self.assertEqual(code, 1)
        self.assertEqual(out.getvalue().splitlines(), ["inventory: 5 names; 4 covered; 0 unknown values",
            "MISMATCH WIDGET_CTRL: header 0x0, spec 0x10 at reg-ctrl (drivers/tty/serial/widget.c)",
            "omitted WIDGET_BAUD (define, drivers/tty/serial/widget.c)", "result: FAIL"])

    def test_nested_anchors_resolve_at_pin(self):
        self.write()
        code, result = run("resolve", self.file, "--repo", "linux=" + str(self.repo))
        self.assertEqual(code, 0, result)
        self.assertEqual((result["resolved"], result["skipped"]), (7, 0))
        self.data["facts"][0]["data"]["fields"][0]["support"][0]["anchors"][0]["symbol"] = "MISSING"
        self.write()
        code, result = run("resolve", self.file, "--repo", "linux=" + str(self.repo))
        self.assertEqual(code, 1, result)
        self.assertTrue(any("MISSING" in f["message"] for f in result["findings"]))

    def test_constant_parser_bounds_and_unknowns(self):
        values, kinds = inventory.extract("#define CTRL 0x10UL\n#define MASK GENMASK(5, 2)\n#define ENABLE BIT(1)\n#define NEXT (CTRL + 4)\n#define UNKNOWN SOME_CALL(2)\n#define TOO_BIG (1 << 1000000)\n")
        self.assertEqual(values, {"CTRL": 16, "MASK": 60, "ENABLE": 2, "NEXT": 20, "UNKNOWN": None, "TOO_BIG": None})
        self.assertEqual(inventory.integer("CTRL", values), 16)
        self.assertIsNone(inventory.integer("__import__('os').system('false')", {}))
        self.assertIsNone(inventory.integer("-1", {}))
        self.assertIsNone(inventory.integer("1 + " * 100 + "1", {}))
        self.assertIsNone(inventory.integer("1" * 4097, {}))


if __name__ == "__main__":
    unittest.main()
