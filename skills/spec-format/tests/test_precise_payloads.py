# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Precise payloads, units 1 and 2.

Unit 1: IP-XACT field properties, registries, arrays, register files. Unit 2: layout fields
with bits, byte order and bit numbering, and enumerated values on them.

Schema refusals, one checker test per rule of the design's "Checks" paragraph, and the
basis: registry entries a record names join its basis, and a record that names none keeps
the basis it had before registries existed. Every refusal asserts an exit code and a message.
"""

import contextlib
import copy
import io
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import peripheral
import records
import render_html
import render_md
import spec
import specload
from test_schema import dump

FIX = HERE / "fixtures" / "precise-payloads"


def run(*args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = spec.main([*map(str, args), "--json"])
    return code, json.loads(out.getvalue())


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="precise-payloads-test-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "root"
        self.root.mkdir()
        shutil.copy(FIX / "board-specs.yaml", self.root)
        self.file = self.root / "gadget.spec.yaml"
        self.data = specload.load_strict(FIX / "gadget.spec.yaml")

    def write(self):
        self.file.write_text(dump(self.data), encoding="utf-8")

    def fact(self, fid):
        return next(f for f in self.data["facts"] if f["id"] == fid)

    def field(self, fid, name):
        return next(x for x in self.fact(fid)["data"]["fields"] if x["id"] == name)

    def entry(self, group, name):
        return next(e for e in self.data[group] if e["name"] == name)

    def check(self):
        self.write()
        return run("check", self.root)

    def invalid(self, text, schema=False):
        """The mutated file is refused (exit 1) with a finding that holds text."""
        self.write()
        code, result = run("validate", self.file) if schema else run("check", self.root)
        self.assertEqual(code, 1, result)
        self.assertTrue(any(text in f["message"] and f.get("level", "error") == "error"
                            for f in result["findings"]), result)

    def accepted(self):
        """No error; the only warnings left are the 'unverified' ones every file without a
        verification record gets."""
        code, result = self.check()
        self.assertEqual(code, 0, result)
        self.assertEqual([f for f in result["findings"] if "unverified:" not in f["message"]],
                         [], result)

    def bases(self):
        self.write()
        code, result = run("status", self.root)
        self.assertEqual(code, 0, result)
        return {r["key"]: r for s in result["specs"] for r in s["facts"]}


PLAIN = {
    "id": "reg-plain", "section": "registers", "title": "PLAIN",
    "data": {"register": {"name": "PLAIN", "offset": "0x20", "width": 32,
                          "access": "read-write"},
             "fields": [{"id": "x", "name": "X", "bits": [0, 0], "meaning": "a bit",
                         "access": "read-write"}]},
    "support": [{"class": "databook", "doc": "trm", "at": [{"page": "40"}]}],
}


class Clean(Fixture):
    def test_the_fixture_checks_clean(self):
        self.accepted()
        code, result = self.check()
        self.assertEqual([f["level"] for f in result["findings"]], ["warning"] * 5)


class Schema(Fixture):
    def test_a_policy_and_its_own_access(self):
        self.field("reg-status", "err")["access"] = "read-write"
        self.invalid("may not also set access", schema=True)

    def test_a_policy_and_its_own_unaffected_by(self):
        self.field("reg-status", "err")["unaffectedBy"] = ["hot"]
        self.invalid("may not also set", schema=True)

    def test_a_table_and_a_definition_ref(self):
        self.field("reg-status", "mode")["enumerationDefinitionRef"] = "link-width"
        self.invalid("not both", schema=True)

    def test_a_constraint_mixing_shapes(self):
        self.field("reg-status", "rsvdz")["writeValueConstraint"] = {
            "writeAsRead": True, "minimum": "0x0", "maximum": "0x0"}
        self.invalid("exactly one of", schema=True)

    def test_a_constraint_with_only_a_minimum(self):
        self.field("reg-status", "rsvdz")["writeValueConstraint"] = {"minimum": "0x0"}
        self.invalid("exactly one of", schema=True)

    def test_a_short_access_on_a_field(self):
        self.field("reg-status", "mode")["access"] = "rw"
        self.invalid("'rw' is not one of", schema=True)

    def test_modified_write_value_beside_a_legacy_register_access(self):
        self.fact("reg-status")["data"]["register"].update(
            access="rw", modifiedWriteValue="oneToClear")
        self.invalid("legacy short access", schema=True)

    def test_read_action_beside_a_legacy_register_access(self):
        self.fact("reg-cap")["data"]["register"].update(access="ro", readAction="clear")
        self.invalid("legacy short access", schema=True)

    def test_a_registry_key_on_a_soc_or_board(self):
        for kind in ("soc", "board"):
            with self.subTest(kind=kind):
                self.data["kind"] = kind
                self.invalid("belong to a peripheral", schema=True)

    def test_an_unknown_key_in_an_entry(self):
        self.entry("resetTypes", "hot")["color"] = "red"
        self.invalid("unknown key", schema=True)

    def test_an_entry_without_support_or_todo(self):
        del self.entry("resetTypes", "hot")["support"]
        self.invalid("a gap (no support) must carry a todo", schema=True)

    def test_an_empty_registry(self):
        self.data["registerFiles"] = []
        self.invalid("should be non-empty", schema=True)

    def test_a_lock_needs_both_keys(self):
        self.field("reg-cap", "en")["lockedBy"] = {"field": "#reg-lock.wen"}
        self.invalid("lockedValue", schema=True)

    def test_a_field_reference_has_a_fact_and_a_field(self):
        self.field("reg-cap", "err-mirror")["aliasOf"] = "#reg-status"
        self.invalid("does not match", schema=True)

    def test_initialized_by_takes_hardware_or_firmware(self):
        self.field("reg-cap", "lanes")["initializedBy"] = "strap"
        self.invalid("is not one of", schema=True)


class Checker(Fixture):
    # 1. registries
    def test_a_registry_name_listed_twice(self):
        for group in peripheral.REGISTRIES:
            with self.subTest(group=group):
                data = copy.deepcopy(self.data)
                self.data[group].append(copy.deepcopy(self.data[group][0]))
                self.invalid(f"{group} entry {self.data[group][0]['name']!r} is listed twice")
                self.data = data

    def test_an_entry_cites_a_document_the_file_lacks(self):
        self.entry("resetTypes", "hot")["support"][0]["doc"] = "nope"
        self.invalid("document 'nope' is not in this file's resources.documents")

    def test_an_entry_cites_a_page_outside_the_document(self):
        self.entry("enumerationDefinitions", "link-width")["support"][0]["at"] = [
            {"page": "999"}]
        self.invalid("is outside the 80 pages")

    def test_an_entry_anchor_needs_a_repos_entry(self):
        self.entry("registerFiles", "queue")["support"] = [
            {"class": "src", "anchors": [{"repo": "linux", "path": "a.c", "lines": [1, 2], "symbol": "A"}]}]
        self.invalid("names repos entry 'linux', which is not in this file's resources.repos")

    def test_an_entry_anchor_is_license_gated(self):
        self.data["resources"]["repos"] = [{
            "name": "linux", "url": "https://example.invalid/linux",
            "commit": "1" * 40, "license": "GPL-2.0-only", "role": "source",
            "files": [{"path": "a.c", "license_from": "spdx-line"}]}]
        self.entry("registerFiles", "queue")["support"] = [
            {"class": "src", "anchors": [{"repo": "linux", "path": "a.c", "lines": [1, 2], "symbol": "A"}]}]
        self.invalid("is not accepted by root")

    def test_an_entry_cannot_rest_on_facts(self):
        self.entry("resetTypes", "hot")["support"] = [{
            "class": "inference", "premises": [{"fact": "#reg-lock"}],
            "derivation": "it follows"}]
        self.entry("resetTypes", "hot")["todo"] = {"check": "hardware", "text": "check it."}
        self.invalid("inference support names facts")

    def test_a_rejected_entry_citation_makes_a_referencing_basis_unknown(self):
        before = self.bases()
        self.assertNotEqual(before["reg-status"]["status"], "unknown")
        self.entry("resetTypes", "power-on")["support"][0]["at"] = [{"page": "999"}]
        self.write()
        code, result = run("status", self.root)
        self.assertEqual(code, 1, result)
        rows = {r["key"]: r for s in result["specs"] for r in s["facts"]}
        for key in ("reg-status", "reg-cap", "reg-lock"):
            self.assertEqual((rows[key]["status"], rows[key]["basis"]), ("unknown", None), key)
            self.assertIn("failed the check", rows[key]["reason"])
        self.assertEqual(rows["reg-qhead"]["status"], "unverified")

    # 2. references resolve
    def test_a_reset_type_ref_that_names_nothing(self):
        self.field("reg-status", "err")["resets"][0]["resetTypeRef"] = "nope"
        self.invalid("resetTypeRef 'nope' names no resetTypes entry")

    def test_an_unaffected_by_that_names_nothing(self):
        self.field("reg-cap", "en")["unaffectedBy"] = ["nope"]
        self.invalid("unaffectedBy 'nope' names no resetTypes entry")

    def test_a_policy_unaffected_by_that_names_nothing(self):
        self.entry("fieldAccessPolicyDefinitions", "RW1CS")["unaffectedBy"] = ["nope"]
        self.invalid("unaffectedBy 'nope' names no resetTypes entry")

    def test_an_enumeration_ref_that_names_nothing(self):
        self.field("reg-status", "width")["enumerationDefinitionRef"] = "nope"
        self.invalid("enumerationDefinitionRef 'nope' names no enumerationDefinitions entry")

    def test_a_policy_ref_that_names_nothing(self):
        self.field("reg-status", "err")["fieldAccessPolicyDefinitionRef"] = "nope"
        self.invalid("fieldAccessPolicyDefinitionRef 'nope' names no "
                     "fieldAccessPolicyDefinitions entry")

    def test_a_register_file_that_names_nothing(self):
        self.fact("reg-qhead")["data"]["register"]["registerFile"] = "nope"
        self.invalid("registerFile 'nope' names no registerFiles entry")

    def test_an_alias_of_a_field_that_does_not_exist(self):
        self.field("reg-cap", "err-mirror")["aliasOf"] = "#reg-status.nope"
        self.invalid("aliasOf '#reg-status.nope' names no field of this file")
        self.field("reg-cap", "err-mirror")["aliasOf"] = "#nope.err"
        self.invalid("aliasOf '#nope.err' names no field of this file")

    def test_an_alias_of_itself(self):
        self.field("reg-cap", "err-mirror")["aliasOf"] = "#reg-cap.err-mirror"
        self.invalid("is an alias of itself")

    def test_a_lock_on_a_field_that_does_not_exist(self):
        self.field("reg-cap", "en")["lockedBy"]["field"] = "#reg-lock.nope"
        self.invalid("lockedBy field '#reg-lock.nope' names no field of this file")

    # 3. values fit
    def test_an_enumerated_value_wider_than_the_field(self):
        self.field("reg-status", "mode")["enumeratedValues"][2]["value"] = "0x8"
        self.invalid("enumerated value 0x8 (x4) does not fit the 3-bit field")

    def test_a_shared_table_value_wider_than_the_field(self):
        self.field("reg-status", "width")["bits"] = [4, 4]
        self.invalid("enumeration 'link-width' value 0x2 (x4) does not fit the 1-bit field")

    def test_a_reset_value_wider_than_the_field(self):
        self.field("reg-status", "err")["resets"][0]["value"] = "0x2"
        self.invalid("reset value 0x2 does not fit the 1-bit field")

    def test_a_reset_mask_wider_than_the_field(self):
        self.field("reg-lock", "wen")["resets"][0]["mask"] = "0x3"
        self.invalid("reset mask 0x3 does not fit the 1-bit field")

    def test_a_constraint_bound_wider_than_the_field(self):
        self.field("reg-status", "rsvdz")["writeValueConstraint"]["maximum"] = "0x100"
        self.invalid("maximum 0x100 does not fit the 8-bit field")

    def test_a_policy_constraint_wider_than_the_field(self):
        self.entry("fieldAccessPolicyDefinitions", "RW1CS")["writeValueConstraint"] = {
            "minimum": "0x0", "maximum": "0x2"}
        self.invalid("maximum 0x2 does not fit the 1-bit field")

    def test_a_minimum_above_the_maximum(self):
        self.field("reg-status", "rsvdz")["writeValueConstraint"] = {
            "minimum": "0x2", "maximum": "0x1"}
        self.invalid("minimum 0x2 is above maximum 0x1")

    def test_a_policy_minimum_above_the_maximum(self):
        self.entry("fieldAccessPolicyDefinitions", "RW1CS")["writeValueConstraint"] = {
            "minimum": "0x2", "maximum": "0x1"}
        self.invalid("minimum 0x2 is above maximum 0x1")

    def test_a_locked_value_wider_than_the_locking_field(self):
        self.field("reg-cap", "en")["lockedBy"]["lockedValue"] = "0x2"
        self.invalid("lockedValue 0x2 does not fit the 1-bit field '#reg-lock.wen'")

    # 4. tables
    def test_a_table_name_listed_twice(self):
        self.field("reg-status", "mode")["enumeratedValues"][1]["name"] = "off"
        self.invalid("value name 'off' is listed twice")

    def test_a_definition_name_listed_twice(self):
        self.entry("enumerationDefinitions", "link-width")["enumeratedValues"][1]["name"] = "off"
        self.invalid("enumeration 'link-width': value name 'off' is listed twice")

    def test_a_table_value_listed_twice(self):
        self.field("reg-status", "mode")["enumeratedValues"][2]["value"] = "0x1"
        self.invalid("value 0x1 is listed twice for 'x1' and 'x4'")

    def test_a_read_and_a_write_meaning_for_one_value(self):
        mode = self.field("reg-status", "mode")
        mode["enumeratedValues"] = [
            {"name": "idle", "value": "0x0", "usage": "read"},
            {"name": "start", "value": "0x0", "usage": "write"}]
        self.accepted()
        mode["enumeratedValues"][1]["usage"] = "read-write"
        self.invalid("value 0x0 is listed twice for 'idle' and 'start'")

    # 5. useEnumeratedValues
    def test_use_enumerated_values_without_a_table(self):
        del self.field("reg-status", "mode")["enumeratedValues"]
        self.invalid("useEnumeratedValues needs enumeratedValues or an "
                     "enumerationDefinitionRef")

    def test_use_enumerated_values_with_a_shared_table(self):
        mode = self.field("reg-status", "mode")
        del mode["enumeratedValues"]
        mode["enumerationDefinitionRef"] = "link-width"
        self.accepted()

    def test_use_enumerated_values_from_a_policy_needs_a_table_on_each_field(self):
        self.entry("fieldAccessPolicyDefinitions", "RW1CS")["writeValueConstraint"] = {
            "useEnumeratedValues": True}
        self.invalid("useEnumeratedValues needs enumeratedValues or an "
                     "enumerationDefinitionRef")
        err = self.field("reg-status", "err")
        err["enumeratedValues"] = [{"name": "off", "value": "0x0"}]
        self.accepted()

    # 6. resets
    def test_two_resets_for_one_type(self):
        self.field("reg-status", "err")["resets"].append({"value": "0x1",
                                                          "resetTypeRef": "power-on"})
        self.invalid("reset type 'power-on' has two resets entries")

    def test_two_default_resets(self):
        self.field("reg-status", "cnt")["resets"].append({"value": "0x1"})
        self.invalid("the default reset type has two resets entries")

    def test_a_reset_type_in_resets_and_unaffected_by(self):
        self.field("reg-cap", "en")["resets"][0]["resetTypeRef"] = "hot"
        self.invalid("reset type 'hot' is in both resets and unaffectedBy of field 'en'")

    def test_a_reset_type_in_resets_and_the_policys_unaffected_by(self):
        self.field("reg-status", "err")["resets"] = [{"value": "0x0", "resetTypeRef": "hot"}]
        self.invalid("reset type 'hot' is in both resets and unaffectedBy of field 'err'")

    # 7. arrays
    def test_field_array_elements_that_overlap(self):
        self.field("reg-status", "mode")["array"] = {"dim": [2], "bitStride": 2}
        self.invalid("bitStride 2 is below the 3-bit field, so the elements overlap")

    def test_field_array_that_leaves_the_register(self):
        self.field("reg-cap", "en")["array"]["dim"] = [30]
        self.invalid("the last element ends at bit 37, outside the 32-bit register")

    def test_field_array_one_bit_past_the_register(self):
        self.field("reg-cap", "en")["array"]["dim"] = [25]
        self.invalid("the last element ends at bit 32, outside the 32-bit register")

    def test_field_array_that_fits_to_the_last_bit(self):
        self.field("reg-cap", "en")["array"]["dim"] = [24]
        self.accepted()

    def test_register_array_elements_that_overlap(self):
        self.fact("reg-status")["data"]["register"]["array"] = {"dim": [2], "stride": "0x2"}
        self.invalid("register array stride 0x2 is below the register's 4 bytes")

    def test_register_beyond_its_register_file(self):
        self.fact("reg-qhead")["data"]["register"]["array"]["dim"] = [5]
        self.invalid("register ends at byte 0x14 of register file 'queue', whose range "
                     "is 0x10")
        self.fact("reg-qhead")["data"]["register"]["array"]["dim"] = [4]
        self.accepted()

    def test_register_file_array_elements_that_overlap(self):
        self.entry("registerFiles", "queue")["array"]["stride"] = "0x8"
        self.invalid("array stride 0x8 is below the range 0x10")

    # 8. legacy access
    def test_legacy_register_access_is_a_warning_with_the_ipxact_form(self):
        for old, form in (("ro", "access: read-only"), ("wo", "access: write-only"),
                          ("rw", "access: read-write"),
                          ("w1c", "access: read-write, modifiedWriteValue: oneToClear"),
                          ("w1s", "access: read-write, modifiedWriteValue: oneToSet"),
                          ("rc", "access: read-only, readAction: clear")):
            with self.subTest(old=old):
                self.fact("reg-status")["data"]["register"]["access"] = old
                code, result = self.check()
                self.assertEqual(code, 0, result)
                found = [f for f in result["findings"] if "legacy" in f["message"]]
                self.assertEqual(len(found), 1, result)
                self.assertEqual(found[0]["level"], "warning")
                self.assertEqual(found[0]["message"], f"register access {old!r} is a legacy "
                                 f"value: write {form} (IP-XACT)")

    def test_the_legacy_table_names_every_short_value(self):
        self.assertEqual(sorted(peripheral.LEGACY_ACCESS),
                         ["rc", "ro", "rw", "w1c", "w1s", "wo"])


class Basis(Fixture):
    def setUp(self):
        super().setUp()
        self.data["facts"].append(copy.deepcopy(PLAIN))

    def changed(self, mutate):
        before = {k: r["basis"] for k, r in self.bases().items()}
        mutate()
        after = {k: r["basis"] for k, r in self.bases().items()}
        return sorted(k for k in before if before[k] != after[k])

    def test_a_fact_with_no_registry_name_keeps_its_old_basis(self):
        """The part is appended only when non-empty: the text is the three parts it always
        was, and the basis is what hashing those three parts gives."""
        fact = {k: v for k, v in self.fact("reg-plain").items() if k != "section"}
        docs = {"trm": self.data["resources"]["documents"][0]}
        text = (records.canonical(fact) + "\n"
                + records.canonical({"documents": docs, "repos": {}}) + "\n"
                + records.canonical({}))
        self.assertEqual(text.count("\n"), 2)
        self.assertEqual(self.bases()["reg-plain"]["basis"],
                         records.sha256("fact-v1\n" + text + "\n"))

    def test_a_named_entry_adds_a_fourth_part(self):
        self.write()
        checker = spec._run_check(_args(self.root))
        rec = checker.files[0].records["reg-lock"]
        text, why = records.local_part(rec)
        self.assertIsNone(why)
        self.assertEqual(text.count("\n"), 3)
        part = json.loads(text.split("\n")[3])
        self.assertEqual(list(part), ["resetTypes"])
        self.assertEqual(list(part["resetTypes"]), ["power-on"])
        self.assertEqual(part["resetTypes"]["power-on"]["description"], "fundamental reset")

    def test_a_referenced_entry_changes_the_basis_of_what_names_it(self):
        def edit():
            self.entry("resetTypes", "power-on")["description"] = "cold reset"
        self.assertEqual(self.changed(edit), ["reg-cap", "reg-lock", "reg-status"])

    def test_a_policys_reset_types_count(self):
        def edit():
            self.entry("resetTypes", "hot")["description"] = "warm reset"
        self.assertEqual(self.changed(edit), ["reg-cap", "reg-status"])

    def test_a_referenced_enumeration_and_policy(self):
        def edit_table():
            self.entry("enumerationDefinitions", "link-width")["enumeratedValues"][1]["name"] = "one"
        self.assertEqual(self.changed(edit_table), ["reg-status"])

        def edit_policy():
            self.entry("fieldAccessPolicyDefinitions", "RW1CS")["description"] = "sticky"
        self.assertEqual(self.changed(edit_policy), ["reg-status"])

    def test_an_entry_citation_changes_the_basis(self):
        def edit():
            self.entry("registerFiles", "queue")["support"][0]["at"] = [{"page": "21"}]
        self.assertEqual(self.changed(edit), ["reg-qhead"])

    def test_a_cited_document_of_an_entry_changes_the_basis(self):
        self.data["resources"]["documents"].append({
            "name": "errata", "class": "databook", "title": "Gadget errata",
            "url": "https://example.invalid/errata.pdf", "sha256": "3" * 64, "pages": 9})
        self.entry("registerFiles", "queue")["support"][0]["doc"] = "errata"
        self.entry("registerFiles", "queue")["support"][0]["at"] = [{"page": "2"}]

        def edit():
            self.data["resources"]["documents"][1]["title"] = "Gadget errata, revised"
        self.assertEqual(self.changed(edit), ["reg-qhead"])

    def test_a_note_changes_nothing(self):
        def add_note():
            self.entry("resetTypes", "power-on")["note"] = "first"
        self.assertEqual(self.changed(add_note), [])

        def edit_note():
            self.entry("resetTypes", "power-on")["note"] = "second"
        self.assertEqual(self.changed(edit_note), [])

    def test_an_unreferenced_entry_changes_nothing(self):
        self.data["resetTypes"].append({
            "name": "function", "description": "function-level reset",
            "support": [{"class": "databook", "doc": "trm", "at": [{"page": "10"}]}]})

        def edit():
            self.entry("resetTypes", "function")["description"] = "FLR"
        self.assertEqual(self.changed(edit), [])

    def test_a_supported_fields_parent_holds_the_register_file(self):
        def edit_file():
            self.entry("registerFiles", "queue")["description"] = "per-queue block"
        self.assertEqual(self.changed(edit_file), ["reg-qhead"])

        def edit_field():
            self.field("reg-qhead", "ptr")["meaning"] = "head pointer"
        self.assertEqual(self.changed(edit_field), ["reg-qhead.ptr"])

    def test_a_name_the_file_lacks_makes_the_basis_unknown(self):
        self.field("reg-status", "err")["fieldAccessPolicyDefinitionRef"] = "nope"
        self.write()
        code, result = run("status", self.root)
        rows = {r["key"]: r for s in result["specs"] for r in s["facts"]}
        self.assertEqual((rows["reg-status"]["status"], rows["reg-status"]["basis"]),
                         ("unknown", None))
        self.assertIn("access policy 'nope' is not in its file's fieldAccessPolicyDefinitions",
                      rows["reg-status"]["reason"])

    def test_a_name_declared_twice_makes_the_basis_unknown(self):
        self.data["resetTypes"].append(copy.deepcopy(self.data["resetTypes"][0]))
        self.write()
        code, result = run("status", self.root)
        rows = {r["key"]: r for s in result["specs"] for r in s["facts"]}
        for key in ("reg-status", "reg-cap", "reg-lock"):
            self.assertEqual((rows[key]["status"], rows[key]["basis"]), ("unknown", None), key)
            self.assertIn("reset type 'power-on' is listed twice in its file",
                          rows[key]["reason"])
        self.assertEqual(rows["reg-plain"]["status"], "unverified")


class LayoutFixture(Fixture):
    """The synthetic packet protocol: layouts with bits, byte order and enumerations."""

    def setUp(self):
        super().setUp()
        self.file = self.root / "packet.spec.yaml"
        self.data = specload.load_strict(FIX / "packet.spec.yaml")

    def layout(self, fid="layout-credit-update"):
        return self.fact(fid)["data"]["layout"]

    def lfield(self, fid, name):
        return next(x for x in self.layout(fid)["fields"] if x["id"] == name)

    def warnings(self, text):
        code, result = self.check()
        self.assertEqual(code, 0, result)
        return [f for f in result["findings"] if text in f["message"]]


class LayoutClean(LayoutFixture):
    def test_the_packet_fixture_checks_clean(self):
        self.accepted()


class LayoutSchema(LayoutFixture):
    def test_an_unknown_byte_order(self):
        self.layout()["byteOrder"] = "middleEndian"
        self.invalid("byteOrder", schema=True)

    def test_an_unknown_bit_numbering(self):
        self.layout()["bitNumbering"] = "msb1"
        self.invalid("bitNumbering", schema=True)

    def test_bits_with_one_item(self):
        self.lfield("layout-credit-update", "vc")["bits"] = [28]
        self.invalid("bits", schema=True)

    def test_a_table_and_a_definition_ref(self):
        self.lfield("layout-credit-update", "indicator")[
            "enumerationDefinitionRef"] = "message-kind"
        self.invalid("a layout field has its own", schema=True)

    def test_no_bit_numbering_is_not_filled_in(self):
        del self.layout()["bitNumbering"]
        self.accepted()
        self.assertNotIn("bitNumbering", self.layout())


class LayoutChecker(LayoutFixture):
    def test_reversed_bits(self):
        self.lfield("layout-credit-update", "vc")["bits"] = [30, 28]
        self.invalid("must be ordered and inside the field's 4 bytes (32 bits)")

    def test_a_one_byte_container_is_named_in_the_singular(self):
        self.lfield("layout-message-header", "kind")["bits"] = [0, 8]
        self.invalid("bits [0, 8] must be ordered and inside the field's 1 byte (8 bits)")

    def test_bits_one_past_the_container(self):
        self.lfield("layout-credit-update", "vc")["bits"] = [28, 32]
        self.invalid("bits [28, 32] must be ordered and inside the field's 4 bytes")

    def test_bits_to_the_last_bit_of_the_container(self):
        self.lfield("layout-credit-update", "vc")["bits"] = [28, 31]
        self.lfield("layout-credit-update", "indicator")["bits"] = [27, 27]
        self.lfield("layout-credit-update", "posted-data")["bits"] = [12, 26]
        self.accepted()

    def test_multi_byte_bits_without_a_byte_order(self):
        del self.layout()["byteOrder"]
        self.invalid("layout 'CREDIT_UPDATE' has no byteOrder, but field 'indicator' has bits "
                     "in a 4-byte container; say bigEndian or littleEndian")

    def test_single_byte_bits_without_a_byte_order(self):
        layout = self.layout("layout-message-header")
        del layout["byteOrder"]
        layout["fields"] = [f for f in layout["fields"] if f["id"] != "function-mask"]
        self.accepted()

    def test_an_enumerated_value_wider_than_the_bits(self):
        self.lfield("layout-credit-update", "indicator")["enumeratedValues"][1][
            "value"] = "0x2"
        self.invalid("enumerated value 0x2 (other) does not fit the 1-bit field")

    def test_a_value_that_fits_the_container_without_bits(self):
        field = self.lfield("layout-message-header", "length")
        field["enumeratedValues"] = [{"name": "max", "value": "0xff"}]
        self.accepted()

    def test_a_value_wider_than_the_container_without_bits(self):
        field = self.lfield("layout-message-header", "length")
        field["enumeratedValues"] = [{"name": "big", "value": "0x100"}]
        self.invalid("enumerated value 0x100 (big) does not fit the 8-bit field")

    def test_a_value_name_listed_twice(self):
        self.lfield("layout-message-header", "function-mask")["enumeratedValues"][1][
            "name"] = "endpoint"
        self.invalid("layout field 'function-mask': value name 'endpoint' is listed twice")

    def test_an_enumeration_ref_that_names_nothing(self):
        self.lfield("layout-message-header", "kind")["enumerationDefinitionRef"] = "nope"
        self.invalid("enumerationDefinitionRef 'nope' names no enumerationDefinitions entry")

    def test_a_shared_value_wider_than_the_layout_field(self):
        self.lfield("layout-message-header", "kind")["bits"] = [0, 0]
        self.invalid("enumeration 'message-kind' value 0x2 (ack) does not fit the 1-bit field")

    def test_overlap_in_one_container_warns(self):
        self.lfield("layout-credit-update", "vc")["bits"] = [27, 29]
        found = self.warnings("overlap")
        self.assertEqual(len(found), 1, found)
        self.assertEqual(found[0]["level"], "warning")
        self.assertIn("field 'posted-data' bits [12, 27] overlap field 'vc' in the same "
                      "container; fine for a union, otherwise a mistake", found[0]["message"])

    def test_each_later_field_warns_once(self):
        fields = self.layout()["fields"]
        for f in fields:
            f["bits"] = [0, 3]
            f.pop("enumeratedValues", None)
        found = self.warnings("overlap")
        self.assertEqual(len(found), 3, found)
        self.assertTrue(all("overlap field 'indicator'" in f["message"] for f in found), found)

    def test_the_same_bits_in_different_containers_do_not_warn(self):
        fields = self.layout()["fields"]
        for k, f in enumerate(fields):
            f["bits"] = [0, 3]
            f["offset"] = hex(k * 4)
            f.pop("enumeratedValues", None)
        self.layout()["size"] = 16
        self.assertEqual(self.warnings("overlap"), [])

    def test_fields_without_bits_do_not_warn(self):
        for f in self.layout()["fields"]:
            f.pop("bits")
            f.pop("enumeratedValues", None)
        self.assertEqual(self.warnings("overlap"), [])

    def test_bits_do_not_break_the_commands(self):
        self.write()
        for command in (("check",), ("status",), ("render", "--format", "md"),
                        ("render", "--format", "html")):
            code, result = run(*command[:1], self.root, *command[1:])
            self.assertEqual(code, 0, (command, result))


class LayoutBasis(LayoutFixture):
    def basis(self, fid, code=0):
        self.write()
        got, result = run("status", self.root)
        self.assertEqual(got, code, result)
        rows = {r["key"]: r for s in result["specs"] for r in s["facts"]}
        return rows[fid]["basis"]

    def test_a_named_enumeration_joins_the_basis(self):
        before = self.basis("layout-message-header")
        self.assertIsNotNone(before)
        self.entry("enumerationDefinitions", "message-kind")["enumeratedValues"][1][
            "name"] = "reply"
        self.assertNotEqual(self.basis("layout-message-header"), before)

    def test_a_layout_naming_no_entry_is_unaffected(self):
        before = self.basis("layout-credit-update")
        self.entry("enumerationDefinitions", "message-kind")["enumeratedValues"][1][
            "name"] = "reply"
        self.assertEqual(self.basis("layout-credit-update"), before)

    def test_a_name_the_file_lacks_makes_the_basis_unknown(self):
        self.lfield("layout-message-header", "kind")["enumerationDefinitionRef"] = "nope"
        self.assertIsNone(self.basis("layout-message-header", code=1))


class Render(Fixture):
    """Both reading views show the new properties exactly, and escape every author string."""

    def views(self, root=None):
        self.write()
        checker = spec._run_check(_args(root or self.root))
        self.assertTrue(checker.files, checker.findings)
        file = checker.files[0]
        md = render_md.View()
        render_md._generated(md, file, checker)
        md_all = render_md.render(checker)
        html_all = render_html.render(checker)
        return checker, file, "\n".join(md), md_all, html_all

    def md_section(self, text, heading):
        return text.split(heading + "\n", 1)[1].split("\n#", 1)[0]

    def test_the_field_table_in_both_views(self):
        from test_spec_format_7b import Tables

        _, file, _, md, html = self.views()
        rows = peripheral.field_rows(peripheral.generated(file))
        by_field = {r["field"]: {k: v for k, v in r.items() if v != ""} for r in rows}
        self.assertEqual(by_field["reg-status.err"], {
            "field": "reg-status.err", "name": "ERR", "bits": [0, 0],
            "policy": "RW1CS", "resets": "0x0 (power-on)"})
        self.assertEqual(by_field["reg-status.mode"], {
            "field": "reg-status.mode", "name": "MODE", "bits": [1, 3],
            "access": "read-write", "values": "0x0 off; 0x1 x1; 0x2 x4",
            "writeValueConstraint": "useEnumeratedValues"})
        self.assertEqual(by_field["reg-cap.en"], {
            "field": "reg-cap.en", "name": "EN", "bits": [8, 8], "access": "read-write",
            "resets": "0x0 (power-on)", "unaffectedBy": "hot",
            "lockedBy": "#reg-lock.wen = 0x0", "array": "dim 8, bitStride 1"})
        self.assertEqual(by_field["reg-lock.wen"]["resets"], "0x1 (power-on) mask 0x1")
        self.assertEqual(by_field["reg-status.rsvdz"]["writeValueConstraint"], "0x0..0x0")
        self.assertEqual(by_field["reg-status.width"]["values"], "see link-width")
        self.assertEqual([r["field"] for r in rows], [
            "reg-status.err", "reg-status.mode", "reg-status.width", "reg-status.cnt",
            "reg-status.rsvd", "reg-status.rsvdz", "reg-cap.lanes", "reg-cap.en",
            "reg-cap.err-mirror", "reg-lock.wen", "reg-qhead.ptr"])
        keys = list(peripheral.FIELD_COLUMNS[:0]) + [
            k for k in peripheral.FIELD_COLUMNS if any(k in r for r in rows)]
        self.assertTrue(all(list(r) == keys for r in rows))
        lines = [line for line in self.md_section(md, "### Register fields \\(generated\\)")
                 .splitlines() if line.startswith("| ")]
        self.assertEqual(lines[2:], [
            "| " + " | ".join(render_md.escape(render_md._value(r.get(k, ""))).replace("|", "\\|")
                              for k in keys) + " |" for r in rows])
        self.assertIn("| reg\\-status\\.err | ERR | `[0, 0]` |  |  |  | RW1CS | "
                      "0x0 \\(power\\-on\\) |", md)
        self.assertIn("\nRegister `QHEAD` at `0x0` in register file `queue`, 32 bits, "
                      "read\\-write, array dim 2, stride `0x4`.\n", md)
        self.assertIn("\nRegister `CAP` at `0x8`, 32 bits, read\\-write.\n", md)
        table = Tables(html).tables["Register fields (generated)"][0]
        self.assertEqual(table[0], keys)
        self.assertEqual(table[1:], [[render_md._value(r.get(k, "")) for k in keys]
                                     for r in rows])

    def test_definitions_with_their_provenance(self):
        _, _, _, md, html = self.views()
        self.assertIn("## Definitions (generated): precise\\-payloads\n", md)
        for heading in ("Reset types", "Field access policies", "Enumerations",
                        "Register files"):
            self.assertIn("### " + heading + "\n", md)
            self.assertIn("<h3>" + heading + "</h3>", html)
        policy = self.md_section(md, "### Field access policies")
        self.assertIn("Definition entry `RW1CS`:", policy)
        self.assertIn("- modifiedWriteValue: oneToClear", policy)
        self.assertIn("- databook: Gadget TRM; p\\. 11\\, table 2\\-1", policy)
        self.assertNotIn("- support", policy)
        files = self.md_section(md, "### Register files")
        self.assertIn("- array: `{\"dim\": [4], \"stride\": \"0x10\"}`", files)
        self.assertIn("- databook: Gadget TRM; p\\. 20", files)
        rw1cs = html.split("<h3>Field access policies</h3>", 1)[1].split("<h3>", 1)[0]
        self.assertIn("<td>RW1CS</td>", rw1cs)
        self.assertIn("Gadget TRM</a>; p. 11, table 2-1", rw1cs)
        self.assertIn("badge class-databook", rw1cs)

    def test_a_todo_and_a_note_on_a_definition(self):
        self.entry("resetTypes", "hot").update(
            todo={"check": "hardware", "text": "Confirm the hot reset"},
            note="Entry **note**.")
        del self.entry("resetTypes", "hot")["support"]
        _, _, _, md, html = self.views()
        reset = self.md_section(md, "### Reset types")
        self.assertIn("- TODO (verify on hardware): Confirm the hot reset", reset)
        self.assertIn("Definition note (author text):", md)
        self.assertIn("Entry **note**.", md)
        self.assertIn("Confirm the hot reset", html)
        self.assertIn("Entry <strong>note</strong>.", html)

    def test_enumerated_values_and_resets_are_not_json(self):
        _, _, _, md, html = self.views()
        for text in ('[{"name"', '"enumeratedValues": [', "[{&quot;name&quot;",
                     "&quot;enumeratedValues&quot;", "&quot;resets&quot;"):
            self.assertNotIn(text, md)
            self.assertNotIn(text, html)
        self.assertIn("- enumeratedValues:\n  - `0x0` off: no link\n  - `0x1` x1\n"
                      "  - `0x2` x4 (read\\-write)\n", md)
        self.assertIn("- resets:\n  - `0x1` mask `0x1` (power\\-on)\n", md)
        self.assertIn("- enumeratedValues:\n  - `0x0` off: link down\n", md)
        self.assertIn("<p>enumeratedValues</p><table><thead><tr><th>value</th><th>name</th>"
                      "<th>description</th><th>usage</th></tr></thead><tbody>"
                      "<tr><td>0x0</td><td>off</td><td>no link</td><td></td></tr>"
                      "<tr><td>0x1</td><td>x1</td><td></td><td></td></tr>"
                      "<tr><td>0x2</td><td>x4</td><td></td><td>read-write</td></tr>"
                      "</tbody></table>", html)
        self.assertIn("<p>resets</p><table><thead><tr><th>value</th><th>mask</th>"
                      "<th>resetTypeRef</th></tr></thead><tbody>"
                      "<tr><td>0x1</td><td>0x1</td><td>power-on</td></tr>", html)

    def test_the_register_table_shows_an_array_as_json(self):
        _, _, _, md, html = self.views()
        self.assertIn("<td>{&quot;dim&quot;: [2], &quot;stride&quot;: &quot;0x4&quot;}</td>",
                      html)
        self.assertNotIn("{'dim'", html)
        rows = {r["fact"]: r for r in peripheral.register_rows(
            peripheral.generated(spec._run_check(_args(self.root)).files[0]))}
        self.assertEqual(rows["reg-qhead"]["registerFile"], "queue")
        self.assertEqual(rows["reg-qhead"]["array"], {"dim": [2], "stride": "0x4"})
        self.assertNotIn("array", rows["reg-status"])

    def test_author_strings_are_escaped_in_both_views(self):
        bad = "<script>alert(1)</script> *emphasis*"
        self.field("reg-status", "mode")["enumeratedValues"][0]["description"] = bad
        self.entry("resetTypes", "hot")["description"] = bad
        self.entry("enumerationDefinitions", "link-width")["enumeratedValues"][0][
            "description"] = bad
        _, _, _, md, html = self.views()
        self.assertEqual(md.count("<script>"), md.count("`" + bad + "`"))
        self.assertEqual(md.count("<script>"), 3)
        self.assertNotIn("<script>", html)
        self.assertEqual(html.count("&lt;script&gt;"), 3)
        self.assertIn("  - `0x0` off: `" + bad + "`\n", md)
        self.assertIn("- description: `" + bad + "`\n", md)
        self.assertIn("<td>&lt;script&gt;alert(1)&lt;/script&gt; *emphasis*</td>", html)
        self.assertNotIn("<em>", html)

    def test_a_spec_without_the_new_properties_is_unchanged(self):
        root = Path(self.tmp.name) / "plain"
        shutil.copytree(HERE / "fixtures" / "peripheral", root)
        checker = spec._run_check(_args(root))
        self.assertTrue(checker.files, checker.findings)
        file = checker.files[0]
        summary = peripheral.generated(file)
        self.assertEqual(summary["definitions"], {})
        rows = peripheral.register_rows(summary)
        self.assertEqual(rows[0], {
            "fact": "reg-ctrl", "offset": "0x0", "name": "WIDGET_CTRL", "width": 32,
            "access": "read-write", "reset": "0x0",
            "fields": [{"id": "en", "name": "WIDGET_CTRL_EN", "bits": [0, 0],
                        "meaning": "block enable"}]})
        for row in rows:
            self.assertEqual(set(row), {"fact", "offset", "name", "width", "access", "reset",
                                        "fields"})
        for view in (render_md.render(checker), render_html.render(checker)):
            self.assertIn("Register map", view)
            self.assertNotIn("Register fields", view)
            self.assertNotIn("Definitions (generated)", view)
            self.assertNotIn("Layout fields", view)
        self.assertEqual(summary["layouts"][0]["fact"], "frame")
        self.assertIn("\nLayout `widget_frame`: 4 bytes.\n", render_md.render(checker))
        self.assertNotIn("bit numbering", render_md.render(checker))


class LayoutRender(LayoutFixture):
    """Layout fields in both views, with every author string escaped."""

    def views(self):
        self.write()
        checker = spec._run_check(_args(self.root))
        self.assertTrue(checker.files, checker.findings)
        return (checker.files[0], render_md.render(checker), render_html.render(checker))

    def test_the_layout_field_table_in_both_views(self):
        from test_spec_format_7b import Tables

        file, md, html = self.views()
        rows = peripheral.layout_field_rows(peripheral.generated(file))
        self.assertEqual(rows[0], {
            "field": "layout-credit-update.indicator", "layout": "CREDIT_UPDATE",
            "offset": "0x0", "size": 4, "bits": [31, 31], "byteOrder": "bigEndian",
            "bitNumbering": "lsb0", "values": "0x0 update; 0x1 other"})
        self.assertEqual(rows[4], {
            "field": "layout-message-header.kind", "layout": "MESSAGE_HEADER",
            "offset": "0x0", "size": 1, "bits": [0, 1], "byteOrder": "littleEndian",
            "bitNumbering": "msb0", "values": "see message-kind"})
        self.assertEqual(rows[6], {
            "field": "layout-message-header.length", "layout": "MESSAGE_HEADER",
            "offset": "0x1", "size": 1, "bits": "", "byteOrder": "littleEndian",
            "bitNumbering": "msb0", "values": ""})
        self.assertEqual([r["field"] for r in rows], [
            "layout-credit-update.indicator", "layout-credit-update.vc",
            "layout-credit-update.posted-data", "layout-credit-update.nonposted-data",
            "layout-message-header.kind", "layout-message-header.function-mask",
            "layout-message-header.length"])
        keys = list(peripheral.LAYOUT_COLUMNS)
        self.assertTrue(all(list(r) == keys for r in rows))
        lines = [line for line in md.split("### Layout fields \\(generated\\)\n", 1)[1]
                 .split("\n#", 1)[0].splitlines() if line.startswith("| ")]
        self.assertEqual(lines[2:], [
            "| " + " | ".join(render_md.escape(render_md._value(r[k])).replace("|", "\\|")
                              for k in keys) + " |" for r in rows])
        self.assertIn("| layout\\-message\\-header\\.kind | `MESSAGE_HEADER` | 0x0 | 1 | "
                      "`[0, 1]` | littleEndian | msb0 | see message\\-kind |", md)
        table = Tables(html).tables["Layout fields (generated)"][0]
        self.assertEqual(table[0], keys)
        self.assertEqual(table[1:], [[render_md._value(r[k]) for k in keys] for r in rows])

    def test_the_headline_names_byte_order_and_bit_numbering(self):
        _, md, html = self.views()
        self.assertIn("\nLayout `CREDIT_UPDATE`: 4 bytes, `bigEndian`, bit numbering `lsb0`.\n",
                      md)
        self.assertIn("\nLayout `MESSAGE_HEADER`: 4 bytes, `littleEndian`, bit numbering "
                      "`msb0`.\n", md)
        self.assertIn("<td>CREDIT_UPDATE</td><td>4</td><td>bigEndian</td><td>lsb0</td>", html)
        self.assertIn("<td>littleEndian</td><td>msb0</td>", html)

    def test_the_headline_names_only_the_parts_present(self):
        del self.layout()["bitNumbering"]
        del self.layout("layout-message-header")["byteOrder"]
        del self.layout("layout-message-header")["bitNumbering"]
        _, md, _ = self.views()
        self.assertIn("\nLayout `CREDIT_UPDATE`: 4 bytes, `bigEndian`.\n", md)
        self.assertIn("\nLayout `MESSAGE_HEADER`: 4 bytes.\n", md)

    def test_enumerated_values_of_a_layout_field(self):
        _, md, html = self.views()
        self.assertIn("- enumeratedValues:\n  - `0x0` update: credit update\n  - `0x1` other\n",
                      md)
        self.assertIn("- enumerationDefinitionRef: message\\-kind\n", md)
        self.assertIn("- bits: `[31, 31]`\n", md)
        self.assertNotIn('"enumeratedValues": [', md)
        self.assertIn("<p>enumeratedValues</p><table><thead><tr><th>value</th><th>name</th>"
                      "<th>description</th><th>usage</th></tr></thead><tbody>"
                      "<tr><td>0x0</td><td>update</td><td>credit update</td><td></td></tr>"
                      "<tr><td>0x1</td><td>other</td><td></td><td></td></tr></tbody></table>",
                      html)

    def test_author_strings_are_escaped_in_both_views(self):
        bad = "<script>alert(1)</script>"
        field = self.lfield("layout-credit-update", "indicator")
        field["name"] = bad
        field["meaning"] = bad
        field["enumeratedValues"][0]["name"] = bad
        field["enumeratedValues"][0]["description"] = bad
        _, md, html = self.views()
        self.assertNotIn("<script>", html)
        self.assertGreaterEqual(html.count("&lt;script&gt;"), 4)
        self.assertGreaterEqual(md.count("<script>"), 4)
        self.assertNotIn("<script>", re.sub(r"`[^`]*`", "", md))


def _args(root):
    import types

    return types.SimpleNamespace(roots=[root], context_root=[], require_license=False,
                                 public_skill=[])


if __name__ == "__main__":
    unittest.main()
