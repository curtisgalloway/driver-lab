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

    def test_restored_license_fixture_claims_and_support(self):
        base = HERE / "fixtures" / "license-gate" / "specs"
        data = specload.load_strict(base / "bsd-target.spec.yaml")
        fact = next((f for f in data["facts"] if f.get("claim") == "The driver binds by compatible string."), None)
        self.assertIsNotNone(fact)
        self.assertEqual(fact["section"], "target")
        self.assertEqual(fact["support"], [{"class": "src", "anchors": [
            {"repo": "os", "path": "drivers/widget/widget.cc", "search": "compatible"}]}])
        self.assertIn("[tgt: drivers/widget/widget.cc:12]", fact["note"])
        data = specload.load_strict(base / "docs-only.spec.yaml")
        self.assertEqual([f["claim"] for f in data["facts"]],
                         ["The block resets in 10 us.", "The FIFO is 64 entries deep."])
        self.assertEqual([f["support"] for f in data["facts"]], [
            [{"class": "databook", "doc": "widget-trm", "at": [{"section": section}]}]
            for section in ("4.2", "5.1")])

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
        for name in ("name", "offset"):
            self.data = copy.deepcopy(base)
            del self.data["facts"][0]["data"]["register"][name]
            self.invalid("required property", schema=True)
        for name, values in (("name", ["", " ", "-CTRL", "CTRL\n"]),
                             ("offset", [0, "0x00", "0X1", "0xA", "0x0\n"]),
                             ("width", [0, -1, "32", True]), ("access", ["", "read-write"]),
                             ("reset", [None, 1, "0x00"])):
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

    def test_subkey_basis_excludes_parent_cited_resources(self):
        self.data["facts"][0]["support"] = copy.deepcopy(self.data["facts"][4]["support"])
        checker = self.checker()
        file = checker.files[0]
        self.assertIn("reg-ctrl.en", file.records)
        before = records.Freshness(checker).basis(file.records["reg-ctrl.en"])[0]
        file.documents["trm"][0]["sha256"] = "2" * 64
        after = records.Freshness(checker).basis(file.records["reg-ctrl.en"])[0]
        self.assertEqual(before, after)

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
                                                                  "write WIDGET_LCR_8N1 to LCR", "set WIDGET_CTRL_EN in CTRL"), 1)] +
                         [{"fact": "baud-latch-test", "text": self.data["facts"][-1]["claim"]}])
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
                         ["reg-baud", "seq-init.s1", "seq-init.s3", "seq-init.s4", "seq-init.s2->s3", "baud-latch-test"])
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


    def test_unknown_register_width_and_access_are_absent(self):
        reg = self.data["facts"][0]["data"]["register"]
        reg.pop("reset")
        reg.pop("width")
        reg.pop("access")
        self.assertEqual(self.check()[0], 0)
        view = render_md.render(self.checker())
        self.assertIn("Register `WIDGET_CTRL` at `0x0`.", view)
        self.assertNotIn("None", view)

    def test_field_requirement_override_fixes_inherited_hw_required(self):
        self.data["facts"][0]["requirement"] = "hw-required"
        self.data["facts"][0]["support"] = copy.deepcopy(self.data["facts"][4]["support"])
        self.invalid("hw-required needs document-class support")
        self.data["facts"][0]["data"]["fields"][0]["requirement"] = "as-implemented"
        self.assertEqual(self.check()[0], 0)
        got = peripheral.generated(self.checker().files[0])
        self.assertIn({"fact": "reg-ctrl.en", "text": "block enable"}, got["verify"])

    def test_payloadless_overlay_hardware_todo_is_generated(self):
        overlay = Path(self.tmp.name) / "overlay"
        overlay.mkdir()
        (overlay / "board-specs.yaml").write_text("format: 2\nlayer: local\nname: local\nlicense: Apache-2.0\naccepts: [GPL-2.0-only]\n")
        (overlay / "widget-overlay.spec.yaml").write_text(dump({"format": 2, "kind": "overlay",
            "overlays": "widget", "facts": [{"id": "observe", "section": "identity",
            "title": "Clock", "claim": "Observe the clock.", "todo": {"check": "hardware", "text": "Measure it."}}]}))
        for flags in ((), ("--merged",)):
            code, result = run("render", self.root, overlay, "--format", "md", *flags)
            self.assertEqual(code, 0, result)
            self.assertEqual(result["markdown"].count("- `observe`: " + render_md.escape("Observe the clock.")), 1)

    def test_layout_support_does_not_make_a_verdict_subkey(self):
        row = self.data["facts"][4]["data"]["layout"]["fields"][0]
        row["support"] = copy.deepcopy(self.data["facts"][4]["support"])
        checker = self.checker()
        self.assertNotIn("frame.type", checker.files[0].records)

    def test_duplicated_subkey_verdict_is_refused_as_a_key(self):
        self.record(self.checker(), "reg-ctrl.en")
        fields = self.data["facts"][0]["data"]["fields"]
        fields.append(copy.deepcopy(fields[0]))
        checker = self.checker()
        self.assertTrue(any("verdict key 'reg-ctrl.en'" in f.message and "has no field or step" in f.message
                            for f in checker.findings), checker.findings)
        self.assertNotIn("reg-ctrl.en", checker.files[0].verdicts)

    def test_nested_citation_is_checked_once(self):
        self.data["facts"][0]["data"]["fields"][0]["support"][0]["anchors"][0]["path"] = "missing.c"
        checker = self.checker()
        hits = [f for f in checker.findings if f.level == "error" and "is not in the files" in f.message]
        self.assertEqual(len(hits), 1, checker.findings)

    def bases(self):
        checker = self.checker()
        fresh = records.Freshness(checker)
        return {key: fresh.basis(rec)[0] for key, rec in checker.files[0].records.items()}

    def test_d16_field_anchor_stales_only_its_subkey(self):
        before = self.bases()
        self.data["facts"][0]["data"]["fields"][0]["support"][0]["anchors"][0]["lines"] = [4, 5]
        after = self.bases()
        self.assertEqual({key for key in before if before[key] != after[key]}, {"reg-ctrl.en"})
        before = after
        self.data["facts"][0]["data"]["register"]["offset"] = "0x10"
        after = self.bases()
        self.assertEqual({key for key in before if before[key] != after[key]}, {"reg-ctrl", "reg-ctrl.en"})

    def test_d16_step_edit_and_step_order(self):
        steps = self.data["facts"][3]["data"]["sequence"]["steps"]
        steps[3]["support"] = copy.deepcopy(steps[0]["support"])
        before = self.bases()
        steps[3]["action"] = "Set the enable bit twice."
        after = self.bases()
        self.assertEqual({key for key in before if before[key] != after[key]}, {"seq-init.s4"})
        before = after
        steps[2], steps[3] = steps[3], steps[2]
        after = self.bases()
        self.assertEqual({key for key in before if before[key] != after[key]},
                         {"seq-init", "seq-init.s1", "seq-init.s4"})

    def test_d16_parent_edit_does_not_stale_children(self):
        before = self.bases()
        self.data["facts"][0]["support"][0]["anchors"][0]["lines"] = [4, 5]
        after = self.bases()
        self.assertEqual({key for key in before if before[key] != after[key]}, {"reg-ctrl"})
        before = after
        self.data["facts"][3]["data"]["sequence"]["steps"][1]["action"] = "Write a new divisor."
        after = self.bases()
        self.assertEqual({key for key in before if before[key] != after[key]}, {"seq-init"})

    def test_d16_effective_requirement_stales_inheriting_children(self):
        for fact_index, key in ((0, "reg-ctrl.en"), (3, "seq-init.s1")):
            with self.subTest(key=key):
                parent = self.data["facts"][fact_index]
                group = (parent["data"]["fields"] if fact_index == 0 else
                         parent["data"]["sequence"]["steps"])
                child = group[0]
                child.pop("requirement", None)
                parent["requirement"] = "as-implemented"
                self.record(self.checker(), key)
                parent["requirement"] = "driver-choice"
                checker = self.checker()
                self.assertFalse(any(f.level == "error" for f in checker.findings), checker.findings)
                row = next(r for r in checker.status[0]["rows"] if r["key"] == key)
                self.assertEqual(row["status"], "stale")
                child["requirement"] = "as-implemented"
                before = self.bases()[key]
                parent["requirement"] = "as-implemented"
                self.assertEqual(before, self.bases()[key])
                child["requirement"] = "driver-choice"
                self.assertNotEqual(before, self.bases()[key])

    def test_d16_new_inherited_requirement_changes_child_basis(self):
        parent = self.data["facts"][0]
        parent.pop("requirement", None)
        parent["data"]["fields"][0].pop("requirement", None)
        bases = self.bases()
        self.assertIn("reg-ctrl.en", bases)
        before = bases["reg-ctrl.en"]
        parent["requirement"] = "as-implemented"
        self.assertNotEqual(before, self.bases()["reg-ctrl.en"])

    def test_facts_symlink_is_usage_error(self):
        self.write()
        dest = Path(self.tmp.name) / "answer.facts.yaml"
        data = {"format": 2, "kind": "facts", "facts": [], "resources": self.data["resources"]}
        target = Path(self.tmp.name) / "regular.facts.yaml"
        target.write_text(dump(data))
        dest.symlink_to(target)
        code, result = run("check", dest, "--root", self.root)
        self.assertEqual(code, 2, result)
        self.assertIn("regular *.facts.yaml", result["findings"][0]["message"])


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


    def commit_header(self, text, relative="drivers/tty/serial/widget.c"):
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        subprocess.run(["git", "-C", str(self.repo), "add", relative], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(self.repo), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                        "-c", "commit.gpgsign=false", "commit", "-q", "-m", "header fixture"], check=True, capture_output=True)
        self.data["resources"]["repos"][0]["commit"] = subprocess.run(
            ["git", "-C", str(self.repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()

    def test_inventory_header_license_must_match(self):
        source = self.repo / "drivers/tty/serial/widget.c"
        self.commit_header(source.read_text().replace("GPL-2.0-only", "MIT"))
        code, result = self.inventory()
        self.assertEqual(code, 1, result)
        self.assertIn("SPDX line 'MIT' differs from entry license", result["findings"][0]["message"])

    def test_inventory_unknown_never_passes_even_when_covered(self):
        source = self.repo / "drivers/tty/serial/widget.c"
        self.commit_header(source.read_text() + "\n#define WIDGET_CTRL 0x10\n")
        code, result = self.inventory()
        self.assertEqual(code, 1, result)
        self.assertEqual(result["unknown"], ["WIDGET_CTRL"])
        self.assertIn("ambiguous", result["unknown_reasons"]["WIDGET_CTRL"])

    def test_cross_header_conflict_is_unknown_with_reason(self):
        self.commit_header("// SPDX-License-Identifier: GPL-2.0-only\n#define WIDGET_CTRL 0x10\n", "other.h")
        self.data["resources"]["repos"][0]["files"].append({"path": "other.h", "license_from": "spdx-line"})
        code, result = self.inventory("--headers", "drivers/tty/serial/widget.c", "other.h")
        self.assertEqual(code, 1, result)
        self.assertIn("unknown", result, result)
        self.assertEqual(result["unknown"], ["WIDGET_CTRL"])
        self.assertIn("ambiguous", result["unknown_reasons"]["WIDGET_CTRL"])
        self.commit_header("// SPDX-License-Identifier: GPL-2.0-only\n#define WIDGET_CTRL 0\n", "other.h")
        code, result = self.inventory("--headers", "drivers/tty/serial/widget.c", "other.h")
        self.assertEqual(code, 1, result)
        self.assertEqual(result["unknown"], ["WIDGET_CTRL"])
        self.assertIn("multiple definitions", result["unknown_reasons"]["WIDGET_CTRL"])

    def test_comments_preserve_the_whole_expression(self):
        values, _ = inventory.extract("#define CTRL 0x10 /* base */ + 4\n#define MASK 0x1 /* c */ | 0x2 // rest\n")
        self.assertEqual(values, {"CTRL": 20, "MASK": 3})
        self.assertEqual(inventory.integer("1 /* multiline\ncomment */ + 2", {}), 3)

    def test_duplicate_and_conditional_definitions_are_outside_subset(self):
        text = ("#define CTRL 1\n#define CTRL 2\n#define SAME 3\n#define SAME (1 + 2)\n"
            "#ifdef CONFIG_A\n#define ALT 4\n#else\n#define ALT 8\n#endif\n"
            "#if CONFIG_B\n#define EQUAL 4\n#else\n#define EQUAL (2 + 2)\n#endif\n"
            "#if CONFIG_C\n#define MAYBE 7\n#endif\n")
        values, _ = inventory.extract(text)
        self.assertEqual(values, {"CTRL": None, "SAME": None, "ALT": None, "EQUAL": None, "MAYBE": None})
        reasons = {}
        inventory.extract(text, reasons)
        self.assertEqual(set(reasons), {"CTRL", "SAME", "ALT", "EQUAL", "MAYBE"})
        self.assertIn("ambiguous", reasons["ALT"])
        self.assertIn("conditional", reasons["MAYBE"])

    def test_object_macros_expand_textually_before_evaluation(self):
        values, _ = inventory.extract("#define BASE 1 + 2\n#define CTRL BASE * 4\n#define GROUP (BASE) * 4\n"
                                      "#define INDIRECT CTRL + 1\n#define RECURSE RECURSE\n")
        self.assertEqual(values, {"BASE": 3, "CTRL": 9, "GROUP": 12, "INDIRECT": 10, "RECURSE": None})
        values, _ = inventory.extract("#define BASE 1 + 2\n#define BASE 3\n#define CTRL BASE * 4\n")
        self.assertEqual(values, {"BASE": None, "CTRL": None})

    def test_directive_in_enum_initializer_refuses_whole_enum(self):
        reasons = {}
        values, _ = inventory.extract("enum { REG =\n#if A\n0x28\n#else\n+4\n#endif\n, NEXT };\n"
                                      "#define INDIRECT REG + 1\n", reasons)
        self.assertEqual(values, {"REG": None, "NEXT": None, "INDIRECT": None})
        self.assertTrue(all("directive in enum body" in reason for reason in reasons.values()))
        values, _ = inventory.extract("enum { REG =\n#if A\nVALUE_A\n#else\nVALUE_B\n#endif\n};")
        self.assertEqual(values, {"REG": None})

    def test_directed_enum_lists_members_from_every_branch(self):
        reasons = {}
        values, kinds = inventory.extract("enum {\n#if A\nREG_A=0x28\n#else\nREG_B=0x2c\n#endif\n};", reasons)
        self.assertEqual(values, {"REG_A": None, "REG_B": None})
        self.assertEqual(kinds, {"REG_A": "enum", "REG_B": "enum"})
        self.assertEqual(set(reasons), set(values))
        for directive in ("#define LOCAL 1", "#pragma example", "#define CLOSE }",
                          "#define FAKE enum { INVENTED = 4 }"):
            values, _ = inventory.extract(f"enum {{ FIRST = 1,\n{directive}\nLAST = 2 }};")
            self.assertIsNone(values["FIRST"])
            self.assertIsNone(values["LAST"])
            self.assertNotIn("INVENTED", values)
        values, _ = inventory.extract("enum {\n#if A\n#if B\nREG_A=1\n#else\nREG_B=2\n#endif\n"
                                      "#elif C\nREG_C=3\n#else\nREG_D=4\n#endif\n, LAST };\n")
        self.assertEqual(values, dict.fromkeys(("REG_A", "REG_B", "REG_C", "REG_D", "LAST")))

    def test_enum_macro_collision_and_dependents_are_unknown(self):
        reasons = {}
        values, _ = inventory.extract("enum { BASE = 5 };\n#define BASE 2 + 3\n#define REG BASE * 8", reasons)
        self.assertEqual(values, {"BASE": None, "REG": None})
        self.assertTrue(all("enum member and a macro" in reason for reason in reasons.values()))
        values, _, _ = inventory.extract_headers([
            ("first.h", "enum { BASE = 5 };"), ("second.h", "#define BASE 2 + 3\n#define REG BASE * 8")])
        self.assertEqual(values, {"BASE": None, "REG": None})

    def test_conditional_dependencies_and_enums_are_unknown(self):
        reasons = {}
        values, _ = inventory.extract("#ifdef A\n#define BASE 5\nenum { ENUM_BASE=8, NEXT };\n#endif\n"
                                      "#define REG BASE * 8\n#define INDIRECT ENUM_BASE + 4\n", reasons)
        self.assertEqual(values, dict.fromkeys(("BASE", "ENUM_BASE", "NEXT", "REG", "INDIRECT")))
        self.assertTrue(all("conditional" in reason for reason in reasons.values()))
        values, _, _ = inventory.extract_headers([
            ("one.h", "#if A\n#define BASE 1\n#endif"),
            ("two.h", "#define REG BASE + 4")])
        self.assertEqual(values, {"BASE": None, "REG": None})

    def test_empty_builtin_guard_still_suppresses_builtin_meaning(self):
        for name, call in (("BIT", "BIT(5)"), ("BIT_ULL", "BIT_ULL(5)"),
                           ("GENMASK", "GENMASK(5, 2)"), ("GENMASK_ULL", "GENMASK_ULL(5, 2)")):
            with self.subTest(name=name):
                reasons = {}
                values, _ = inventory.extract(f"#ifndef {name}\n#define {name}\n#define REG {call}\n#endif", reasons)
                self.assertIsNone(values["REG"])
                self.assertIn("unsupported", reasons["REG"])
                values, _, _ = inventory.extract_headers([
                    ("guard.h", f"#ifndef {name}\n#define {name}\n#endif"),
                    ("reg.h", f"#define REG {call}")])
                self.assertIsNone(values["REG"])
                self.assertIsNotNone(inventory.extract(f"#define REG {call}")[0]["REG"])

    def test_include_guard_must_wrap_whole_file_without_alternative(self):
        for text in ("#ifndef HEADER\n#define HEADER\n#define REG 5\n#endif\n#define OUTSIDE 8\n",
                     "#ifndef HEADER\n#define HEADER\n#define REG 5\n#else\n#define OTHER 6\n#endif\n",
                     "#ifndef HEADER\n#define HEADER\n#define REG 5\n"):
            reasons = {}
            values, _ = inventory.extract(text, reasons)
            self.assertIsNone(values["REG"])
            self.assertIn("conditional", reasons["REG"])
        values, _ = inventory.extract("#ifndef HEADER\n#define HEADER\nenum { REG=5, NEXT };\n"
                                      "#if A\n#define COND 8\n#endif\n#define INDIRECT COND + 1\n#endif")
        self.assertEqual(values, {"REG": 5, "NEXT": 6, "COND": None, "INDIRECT": None})

    def test_directed_enum_unknowns_still_count_for_omissions(self):
        self.commit_header("// SPDX-License-Identifier: GPL-2.0-only\nenum {\n#if A\nREG_A=0x28\n"
                           "#else\nREG_B=0x2c\n#endif\n};\n")
        code, result = self.inventory()
        self.assertEqual(code, 1, result)
        self.assertEqual(result["unknown"], ["REG_A", "REG_B"])
        self.assertEqual({row["name"] for row in result["omissions"]}, {"REG_A", "REG_B"})

    def test_function_macros_and_all_enum_members_are_reported(self):
        text = ("#define CTRL(n) (0x10 + (n))\n"
            "enum regs { FIRST, NEXT, EXPLICIT = 8, LAST };\n"
            "enum bad { BAD = OTHER(1), AFTER, RECOVER = 9, RECOVER_NEXT };\n")
        values, kinds = inventory.extract(text)
        self.assertEqual(values, {"CTRL": None, "FIRST": 0, "NEXT": 1, "EXPLICIT": 8, "LAST": 9,
                                  "BAD": None, "AFTER": None, "RECOVER": 9, "RECOVER_NEXT": None})
        self.assertEqual(kinds["CTRL"], "define")
        self.assertEqual(kinds["NEXT"], "enum")
        reasons = {}
        inventory.extract(text, reasons)
        self.assertEqual(set(reasons), {"CTRL", "BAD", "AFTER", "RECOVER_NEXT"})

    def test_header_defined_builtins_never_use_assumed_meanings(self):
        values, _ = inventory.extract("#define BIT(n) (1 << ((n) + 1))\n#define CTRL BIT(0)\n"
                                      "#define GENMASK(h,l) 0xff\n#define MASK GENMASK(2, 1)\n")
        self.assertEqual(values, {"BIT": None, "CTRL": None, "GENMASK": None, "MASK": None})
        values, _ = inventory.extract("#define BIT 8\n#define CTRL BIT + 1\n#define MASK BIT(2)\n")
        self.assertEqual(values, {"BIT": 8, "CTRL": 9, "MASK": None})

    def test_guards_are_pairs_and_register_spelling_never_filters(self):
        values, _ = inventory.extract("#ifndef DEVICE_HEADER\n#define DEVICE_HEADER\n"
                                      "#define STATUS_H 0x10\n#define _CTRL 0x14\n#define __MASK 3\n#endif\n")
        self.assertEqual(values, {"STATUS_H": 16, "_CTRL": 20, "__MASK": 3})
        values, _ = inventory.extract("#define UNPAIRED_H\n#define VALID_H 4\n")
        self.assertEqual(values, {"UNPAIRED_H": None, "VALID_H": 4})

    def test_shift_bound_and_genmask_order_have_independent_controls(self):
        self.assertEqual(inventory.integer("1 << 2", {}), 4)
        self.assertIsNone(inventory.integer("0 >> 4097", {}))
        self.assertIsNone(inventory.integer("GENMASK(2, 3)", {}))
        self.assertEqual(inventory.integer("GENMASK(3, 2)", {}), 12)


if __name__ == "__main__":
    unittest.main()
