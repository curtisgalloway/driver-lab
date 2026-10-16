#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for source copyright attribution (issue #101): scan, compare, summary, cell."""

import pathlib
import sys
import types
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import attribution  # noqa: E402


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
        self.assertEqual(scan("﻿// Copyright 2020 Example Corp")["names"],
                         ["Example Corp"])
        self.assertEqual(scan("x", "﻿// Copyright 2020 Example Corp")["status"],
                         "none-found")

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

    def test_notice_in_running_text_is_not_a_candidate(self):
        self.assertEqual(scan("// see the Copyright 2020 Example Corp notice")["status"],
                         "none-found")


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
        recorded["evidence"] = [{"line": 5, "text": "Copyright 2001 ABC Corp"},
                                scanned["evidence"][1]]
        self.assertIn("line 1", attribution.compare(recorded, scanned, lines)[0])

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
            ("linux", "a.c", abc), ("linux", "b.c", None), ("linux", "unlisted.c", None)])


if __name__ == "__main__":
    unittest.main()
