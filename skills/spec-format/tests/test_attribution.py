#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for source copyright attribution (issue #101): scan, compare, summary, cell."""

import pathlib
import sys
import tempfile
import types
import unittest

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import attribution  # noqa: E402
from test_check import chip, inference, marker, repo, src_fact  # noqa: E402
from test_render_md import checked  # noqa: E402


def scan(*lines):
    return attribution.scan(list(lines))


class Scan(unittest.TestCase):
    def test_spdx_file_copyright_text(self):
        got = scan("// SPDX-FileCopyrightText: 2026 Example Corp",
                   "// SPDX-License-Identifier: MIT")
        self.assertEqual(got["status"], "recorded")
        self.assertEqual(got["names"], ["Example Corp"])
        self.assertEqual(got["evidence"], [{"line": 1, "text":
                                            "SPDX-FileCopyrightText: 2026 Example Corp"}])
        self.assertEqual(got["lines"], 2)

    def test_years_symbol_and_email(self):
        got = scan("/* Copyright (C) 2007-2009 Jane Smith <jane@example.invalid> */")
        self.assertEqual(got["names"], ["Jane Smith"])
        self.assertEqual(scan("# (c) 2001, 2003 Bob Roe")["names"], ["Bob Roe"])
        self.assertEqual(scan("# © 2001-present Bob Roe")["names"], ["Bob Roe"])
        self.assertEqual(scan("# COPYRIGHT (C) 2001 Bob Roe")["names"], ["Bob Roe"])

    def test_all_rights_reserved_and_collective_holder(self):
        got = scan("// Copyright 2016 The Fuchsia Authors. All rights reserved.")
        self.assertEqual(got["names"], ["The Fuchsia Authors"])
        got = scan("// Copyright 2016 Foo Bar, All Rights Reserved")
        self.assertEqual(got["names"], ["Foo Bar"])

    def test_abbreviation_keeps_its_period(self):
        self.assertEqual(scan("// Copyright 2020 Example Inc.")["names"], ["Example Inc."])
        self.assertEqual(scan("// Copyright 2020 Example Inc. All rights reserved.")["names"],
                         ["Example Inc."])
        self.assertEqual(scan("// Copyright 2020 Example Corp.")["names"], ["Example Corp."])
        self.assertEqual(scan("// Copyright 2020 Example Group.")["names"], ["Example Group"])

    def test_one_name_per_notice_never_split(self):
        got = scan("// Copyright 2020 Jane Smith and John Doe, Example Corp")
        self.assertEqual(got["names"], ["Jane Smith and John Doe, Example Corp"])

    def test_multiple_notices_and_duplicates(self):
        got = scan("// Copyright 2010 ABC Corp", "// Copyright 2012 Jane Smith",
                   "// Copyright 2015 ABC Corp", "int x;")
        self.assertEqual(got["status"], "recorded")
        self.assertEqual(got["names"], ["ABC Corp", "Jane Smith"])
        self.assertEqual([e["line"] for e in got["evidence"]], [1, 2, 3])

    def test_bsd_boilerplate_is_not_a_candidate(self):
        got = scan(
            " * Redistributions of source code must retain the above copyright",
            " * IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY",
            " * COPYRIGHT HOLDERS AND CONTRIBUTORS \"AS IS\"",
            "the copyright is held by someone")
        self.assertEqual(got["status"], "none-found")
        self.assertEqual(got["evidence"], [])
        self.assertEqual(got["names"], [])

    def test_two_line_notice_is_ambiguous(self):
        got = scan("/*", " * Copyright (C) 2010", " *     Jane Smith", " */")
        self.assertEqual(got["status"], "ambiguous")
        self.assertEqual(got["evidence"], [{"line": 2, "text": "Copyright (C) 2010"}])
        self.assertEqual(got["names"], [])

    def test_bare_copyright_word_is_ambiguous(self):
        self.assertEqual(scan("// Copyright notice goes here")["status"], "ambiguous")

    def test_one_unrecognized_candidate_makes_the_file_ambiguous(self):
        got = scan("// Copyright 2010 ABC Corp", "// Copyright notice")
        self.assertEqual(got["status"], "ambiguous")
        self.assertEqual(got["names"], ["ABC Corp"])
        self.assertEqual(len(got["evidence"]), 2)

    def test_none_found(self):
        got = scan("int main(void) { return 0; }", "")
        self.assertEqual(got, {"status": "none-found", "names": [], "evidence": [],
                               "lines": 2})
        self.assertEqual(attribution.scan([])["status"], "none-found")

    def test_bom_on_line_one_only(self):
        self.assertEqual(scan("\ufeff// Copyright 2020 Example Corp")["names"],
                         ["Example Corp"])
        self.assertEqual(scan("x", "\ufeff// Copyright 2020 Example Corp")["status"],
                         "ambiguous")

    def test_comment_leaders(self):
        for line in ("# Copyright 2020 Example Corp", "// Copyright 2020 Example Corp",
                     "/// Copyright 2020 Example Corp", " * Copyright 2020 Example Corp",
                     "/* Copyright 2020 Example Corp", "/* Copyright 2020 Example Corp */",
                     "<!-- Copyright 2020 Example Corp -->", "; Copyright 2020 Example Corp",
                     "-- Copyright 2020 Example Corp", "% Copyright 2020 Example Corp",
                     "   Copyright 2020 Example Corp", "\tCopyright   2020  Example Corp\r"):
            with self.subTest(line):
                got = scan(line)
                self.assertEqual(got["names"], ["Example Corp"])
                self.assertEqual(got["evidence"][0]["text"], "Copyright 2020 Example Corp")

    def test_more_leaders_and_case_and_symbol_first_forms(self):
        for line, name in (
                ("@ Copyright (C) 2005 ARM Ltd.", "ARM Ltd."),
                ("! Copyright (C) 2005 Foo", "Foo"),
                (" * copyright (c) 2010 Foo", "Foo"),
                (" * (C) Copyright IBM Corp. 2006", "IBM Corp."),
                (" *  (c) Copyright 2010 Foo", "Foo"),
                (" * (C) Copyright 2010 Foo", "Foo"),
                (" * © Copyright 2010 Foo", "Foo"),
                (" * Copyright (C) 1995-97 Simon Foo", "Simon Foo"),
                (" * Copyright 2010-11 Foo", "Foo"),
                (" * Copyright (C) 2000 by Jane Smith", "Jane Smith"),
                (" * Copyright 2000 BY Jane Smith", "Jane Smith"),
                (" * Copyright (C) 2005 Jane <jane@example.invalid>.", "Jane")):
            with self.subTest(line):
                got = scan(line)
                self.assertEqual((got["status"], got["names"]), ("recorded", [name]))

    def test_trailing_years_and_digit_led_holders(self):
        for line, name in (
                ("Copyright (C) IBM Corporation, 2005", "IBM Corporation"),
                ("Copyright (c) Intel Corporation 2010", "Intel Corporation"),
                ("(C) Copyright IBM Corp. 2006. All rights reserved.", "IBM Corp."),
                ("Copyright 2010, 12 Monkeys Ltd", "12 Monkeys Ltd"),
                ("Copyright 2010-12 Foo", "Foo"),
                ("Copyright 2010, 2012 Foo", "Foo")):
            with self.subTest(line):
                got = scan(line)
                self.assertEqual((got["status"], got["names"]), ("recorded", [name]))

    def test_empty_or_by_only_holder_is_ambiguous(self):
        for line in ("Copyright 2010", "Copyright 2010 by", "Copyright (C) 2010 by ,"):
            with self.subTest(line):
                self.assertEqual(scan(line)["status"], "ambiguous")

    def test_mid_line_notices_are_ambiguous_never_none_found(self):
        for line in (" * Portions Copyright (C) 2001 Foo", " * Based on code Copyright (C) 2001 Foo",
                     " * foo.c -- Copyright (C) 2003 Bar", "x = 1; // see Copyright 2020 Foo",
                     " * Derived from (C) 2004 Foo"):
            with self.subTest(line):
                got = scan(line)
                self.assertEqual((got["status"], got["names"]), ("ambiguous", []))
                self.assertEqual(len(got["evidence"]), 1)

    def test_boilerplate_and_function_calls_stay_out(self):
        got = scan(" * retain the above copyright notice, this list", "  copyright notice, this",
                   " * COPYRIGHT HOLDERS AND CONTRIBUTORS", "foo(c) = 1", "int Copyrighted;")
        self.assertEqual(got["status"], "none-found", got)

    def test_template_placeholders_are_ambiguous(self):
        got = scan("Copyright (C) <year>  <name of author>")
        self.assertEqual((got["status"], got["names"]), ("ambiguous", []))
        got = scan("Copyright (C) 2010 <name of author>")
        self.assertEqual((got["status"], got["names"]), ("ambiguous", []))

    def test_record_is_schema_shaped(self):
        self.assertEqual(attribution.record(scan("int x;")), {"status": "none-found"})
        self.assertEqual(attribution.record(scan("Copyright (C) 2010"))["status"], "ambiguous")
        self.assertNotIn("names", attribution.record(scan("Copyright (C) 2010")))
        self.assertEqual(sorted(attribution.record(scan("Copyright 2010 Foo"))),
                         ["evidence", "names", "status"])


class Compare(unittest.TestCase):
    LINES = ["// Copyright 2020 Example Corp", "int x;", "// Copyright 2010", "// Jane Smith"]

    def recorded(self, **changes):
        base = {"status": "recorded", "names": ["Example Corp"],
                "evidence": [{"line": 1, "text": "Copyright 2020 Example Corp"}]}
        base.update(changes)
        return base

    def check(self, recorded, lines=None):
        lines = self.LINES[:1] + self.LINES[1:2] if lines is None else lines
        return attribution.compare(recorded, attribution.scan(lines), lines)

    def test_match(self):
        self.assertEqual(self.check(self.recorded()), [])
        self.assertEqual(self.check({"status": "none-found"}, ["int x;"]), [])

    def test_status_mismatch(self):
        got = self.check({"status": "none-found"})
        self.assertEqual(got, ["attribution status 'none-found' but the source scan "
                               "finds 'recorded'"])

    def test_names_mismatch(self):
        got = self.check(self.recorded(names=["Other Corp"]))
        self.assertEqual(got, ["names differ: recorded ['Other Corp'], scan finds "
                               "['Example Corp']"])

    def test_names_order_matters(self):
        lines = ["// Copyright 2001 ABC Corp", "// Copyright 2002 Jane Smith"]
        scanned = attribution.scan(lines)
        recorded = {"status": "recorded", "names": ["Jane Smith", "ABC Corp"],
                    "evidence": scanned["evidence"]}
        self.assertEqual(len(attribution.compare(recorded, scanned, lines)), 1)

    def test_evidence_mismatch(self):
        got = self.check(self.recorded(evidence=[{"line": 1, "text": "Copyright 2020 X"}]))
        self.assertEqual(got, ["evidence line 1: recorded 'Copyright 2020 X', source has "
                               "'Copyright 2020 Example Corp'"])

    def test_evidence_missing_and_extra_and_moved(self):
        lines = ["// Copyright 2001 ABC Corp", "// Copyright 2002 Jane Smith"]
        scanned = attribution.scan(lines)
        recorded = {"status": "recorded", "names": ["ABC Corp", "Jane Smith"],
                    "evidence": scanned["evidence"][:1]}
        self.assertEqual(attribution.compare(recorded, scanned, lines),
                         ["missing evidence line 2"])
        recorded["evidence"] = scanned["evidence"] + [{"line": 3, "text": "Copyright 2003 X"}]
        self.assertEqual(len(attribution.compare(recorded, scanned, lines)), 1)
        recorded["evidence"] = scanned["evidence"][1:]
        self.assertEqual(attribution.compare(recorded, scanned, lines),
                         ["missing evidence line 1"])

    def test_ambiguous_with_a_hand_resolved_extra_line(self):
        recorded = {"status": "ambiguous", "names": ["Jane Smith"], "evidence": [
            {"line": 3, "text": "Copyright 2010"}, {"line": 4, "text": "Jane Smith"}]}
        lines = ["x", "y"] + self.LINES[2:]
        recorded["evidence"] = [{"line": 3, "text": "Copyright 2010"},
                                {"line": 4, "text": "Jane Smith"}]
        self.assertEqual(attribution.compare(recorded, attribution.scan(lines), lines), [])

    def test_ambiguous_extra_line_text_differs(self):
        lines = ["x", "y"] + self.LINES[2:]
        recorded = {"status": "ambiguous", "evidence": [
            {"line": 3, "text": "Copyright 2010"}, {"line": 4, "text": "Jane Smyth"}]}
        got = attribution.compare(recorded, attribution.scan(lines), lines)
        self.assertEqual(got, ["evidence line 4: recorded 'Jane Smyth', source has "
                               "'Jane Smith'"])

    def test_ambiguous_extra_line_beyond_the_file(self):
        lines = ["x", "y"] + self.LINES[2:]
        recorded = {"status": "ambiguous", "evidence": [
            {"line": 3, "text": "Copyright 2010"}, {"line": 9, "text": "Jane Smith"}]}
        got = attribution.compare(recorded, attribution.scan(lines), lines)
        self.assertEqual(got, ["evidence line 9 does not exist (the file has 4 lines)"])

    def test_ambiguous_must_keep_every_scanned_item(self):
        lines = ["x", "y"] + self.LINES[2:]
        recorded = {"status": "ambiguous", "evidence": [{"line": 4, "text": "Jane Smith"}]}
        got = attribution.compare(recorded, attribution.scan(lines), lines)
        self.assertEqual(got, ["missing evidence line 3"])

    def test_ambiguous_name_not_in_evidence(self):
        lines = self.LINES[2:]
        recorded = {"status": "ambiguous", "names": ["John Doe"], "evidence": [
            {"line": 1, "text": "Copyright 2010"}]}
        got = attribution.compare(recorded, attribution.scan(lines), lines)
        self.assertEqual(got, ["name 'John Doe' occurs in no evidence text"])


class AmbiguousCompare(unittest.TestCase):
    LINES = ["// Copyright 2010 ABC Corp", "/* Copyright (C) 2011", " * Jane Smith */",
             "int x;", "", "", "y"]

    def check(self, **changes):
        scanned = attribution.scan(self.LINES)
        recorded = {"status": "ambiguous", "names": ["ABC Corp", "Jane Smith"],
                    "evidence": scanned["evidence"] + [{"line": 3, "text": "Jane Smith"}]}
        recorded.update(changes)
        return attribution.compare(recorded, scanned, self.LINES)

    def test_good_record(self):
        self.assertEqual(self.check(), [])

    def test_recognized_names_cannot_be_dropped(self):
        self.assertEqual(self.check(names=["Jane Smith"]),
                         ["names omit 'ABC Corp', which the source scan recognizes"])

    def test_names_are_token_bounded_and_real(self):
        self.assertEqual(self.check(names=["ABC Corp", "Jane"])[0:1],
                         [])  # whole word "Jane" in "Jane Smith" is bounded
        self.assertEqual(len(self.check(names=["ABC Corp", "Ja"])), 1)
        self.assertEqual(len(self.check(names=["ABC Corp", "Copyright"])), 1)
        self.assertEqual(len(self.check(names=["ABC Corp", "2011"])), 1)

    def test_extra_line_must_be_near_a_candidate(self):
        scanned = attribution.scan(self.LINES)
        far = {"line": 7, "text": "y"}
        recorded = {"status": "ambiguous", "evidence": scanned["evidence"] + [far],
                    "names": ["ABC Corp"]}
        got = attribution.compare(recorded, scanned, self.LINES)
        self.assertEqual(got, ["evidence line 7: not within 3 lines after a notice the "
                               "source scan finds"])

    def test_lines_must_increase(self):
        scanned = attribution.scan(self.LINES)
        dup = scanned["evidence"] + [scanned["evidence"][0]]
        self.assertTrue(self.check(evidence=dup))
        rev = list(reversed(scanned["evidence"]))
        self.assertTrue(self.check(evidence=rev))


class AmbiguousNames(unittest.TestCase):
    def check(self, lines, names):
        scanned = attribution.scan(lines)
        recorded = {"status": "ambiguous", "names": names,
                    "evidence": scanned["evidence"] + [
                        {"line": n, "text": attribution.notice_text(lines[n - 1])}
                        for n in (3,)]}
        return attribution.compare(recorded, scanned, lines)

    LINES = ["// Copyright (C) 2010", "// Copyright 2011 Broadcom", "// Corporation"]

    def test_scanned_name_covered_by_a_longer_recorded_name(self):
        self.assertEqual(self.check(self.LINES, ["Broadcom Corporation"]), [])

    def test_split_record_still_passes(self):
        self.assertEqual(self.check(self.LINES, ["Broadcom", "Corporation"]), [])

    def test_name_across_lines_must_be_in_the_joined_evidence(self):
        self.assertEqual(self.check(self.LINES, ["Broadcom Corporate"])[0:1],
                         ["name 'Broadcom Corporate' occurs in no evidence text"])

    def test_uncovered_scanned_name_is_reported(self):
        got = self.check(self.LINES, ["Corporation"])
        self.assertEqual(got, ["names omit 'Broadcom', which the source scan recognizes"])


class PremiseUnresolved(unittest.TestCase):
    def test_an_unresolved_premise_counts_as_unrecorded(self):
        rec = types.SimpleNamespace(
            full="s@r#x", file=None, data={"support": [
                {"class": "inference", "premises": [{"fact": "#gone"}], "derivation": "d"}]})
        checker = types.SimpleNamespace(resolve=lambda f, r: (None, "no such fact"))
        ids, items = attribution.premise_files(checker, rec)
        self.assertEqual(ids, ["#gone"])
        self.assertEqual(attribution.summary(items, always=True),
                         None if False else "attribution incomplete (1 unrecorded)")


class Summary(unittest.TestCase):
    ABC = {"status": "recorded", "names": ["ABC Corp"],
           "evidence": [{"line": 1, "text": "Copyright 2020 ABC Corp"}]}
    NONE = {"status": "none-found"}

    def items(self, *attributions):
        return [("r", f"f{i}.c", a) for i, a in enumerate(attributions)]

    def test_single_name(self):
        self.assertEqual(attribution.summary(self.items(self.ABC, self.ABC)), "ABC Corp")

    def test_two_names(self):
        jane = dict(self.ABC, names=["Jane Smith"])
        self.assertEqual(attribution.summary(self.items(self.ABC, jane)),
                         "ABC Corp; Jane Smith")

    def test_collective(self):
        fuchsia = dict(self.ABC, names=["The Fuchsia Authors"])
        self.assertEqual(attribution.summary(self.items(fuchsia)), "The Fuchsia Authors")

    def test_incomplete(self):
        self.assertEqual(attribution.summary(self.items(self.ABC, self.NONE, None)),
                         "ABC Corp; attribution incomplete (1 unrecorded, 1 no notice found)")

    def test_all_none_found(self):
        self.assertEqual(attribution.summary(self.items(self.NONE, self.NONE)),
                         "attribution incomplete (2 no notice found)")

    def test_ambiguous_counts_and_names(self):
        amb = {"status": "ambiguous", "names": ["Jane Smith"], "evidence": [
            {"line": 1, "text": "Jane Smith"}]}
        self.assertEqual(attribution.summary(self.items(self.ABC, amb)),
                         "ABC Corp; Jane Smith; attribution incomplete (1 ambiguous)")

    def test_nothing_recorded_gives_none(self):
        self.assertIsNone(attribution.summary(self.items(None, None)))
        self.assertIsNone(attribution.summary([]))


class Cell(unittest.TestCase):
    def test_cells(self):
        self.assertEqual(attribution.cell(None), "")
        self.assertEqual(attribution.cell({"status": "recorded", "names": ["A", "B"]}),
                         "recorded: A; B")
        self.assertEqual(attribution.cell({"status": "ambiguous"}), "ambiguous")
        self.assertEqual(attribution.cell({"status": "ambiguous", "names": ["A"]}),
                         "ambiguous: A")
        self.assertEqual(attribution.cell({"status": "none-found"}), "no notice found")


class FactFiles(unittest.TestCase):
    def test_own_support_only_deduplicated_without_directories(self):
        abc = {"status": "none-found"}
        file = types.SimpleNamespace(repos={"linux": ({"files": [
            {"path": "a.c", "license_from": "notice", "attribution": abc},
            {"path": "b.c", "license_from": "notice"},
            {"path": "d/", "license_from": "notice"}]}, ())})

        def anchor(path):
            return {"repo": "linux", "path": path}

        data = {"support": [
            {"class": "src", "anchors": [anchor("a.c"), anchor("b.c"), anchor("a.c"),
                                         anchor("d/"), anchor("unlisted.c")]}],
                "conflicts": [{"reading": "r", "support": [
                    {"class": "src", "anchors": [anchor("c.c")]}]}]}
        self.assertEqual(attribution.fact_files(file, data), [
            ("linux", "a.c", abc, (None, None)), ("linux", "b.c", None, (None, None)),
            ("linux", "unlisted.c", None, (None, None))])


class PremiseFiles(unittest.TestCase):
    """Attribution reached through inference premises only (issue #101, unit 2)."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        (self.root / "board-specs.yaml").write_text(
            marker("root_name", accepts="[GPL-2.0-only]"))
        self.data = yaml.safe_load(chip(
            repos=repo(),
            facts=src_fact("a") + src_fact("b", path="drivers/x.c")
            + inference("d", "#a") + inference("e", "#d", "#b") + inference("f", "#a")))
        files = self.data["resources"]["repos"][0]["files"]
        files.append({"path": "drivers/x.c", "license_from": "spdx-line"})
        files[0]["attribution"] = {
            "status": "recorded", "names": ["Example Corp"],
            "evidence": [{"line": 2, "text": "Copyright 2020 Example Corp"}]}

    def reached(self, fid):
        (self.root / "widget_chip.spec.yaml").write_text(
            yaml.safe_dump(self.data, sort_keys=False))
        checker = checked(self.root)
        self.assertEqual([f for f in checker.findings if f.level == "error"], [])
        rec = next(r for f in checker.files for r in f.records.values() if r.id == fid)
        ids, items = attribution.premise_files(checker, rec)
        return ids, [(i[1], i[2] and i[2]["status"]) for i in items]

    def test_a_premise_brings_its_files(self):
        self.assertEqual(self.reached("d"), (["widgetchip@root_name#a"],
                                             [("drivers/w.c", "recorded")]))

    def test_two_level_chain_in_citation_order(self):
        ids, items = self.reached("e")
        self.assertEqual(ids, ["widgetchip@root_name#d", "widgetchip@root_name#a",
                               "widgetchip@root_name#b"])
        self.assertEqual(items, [("drivers/w.c", "recorded"), ("drivers/x.c", None)])

    def test_a_fact_without_premises_reaches_nothing(self):
        self.assertEqual(self.reached("a"), ([], []))

    def test_relates_cycle_terminates_and_is_not_followed(self):
        facts = {f["id"]: f for f in self.data["facts"]}
        facts["a"]["relates"] = [{"relation": "same-as", "fact": "#b"}]
        facts["b"]["relates"] = [{"relation": "same-as", "fact": "#a"}]
        self.assertEqual(self.reached("f"), (["widgetchip@root_name#a"],
                                             [("drivers/w.c", "recorded")]))
        self.assertEqual(self.reached("a"), ([], []))


if __name__ == "__main__":
    unittest.main()
