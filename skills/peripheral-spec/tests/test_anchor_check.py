#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""
Tests for scripts/anchor_check.py, against synthetic git repositories built per run.

Run:  python3 -m unittest discover -s skills/peripheral-spec/tests -v

The first class pins down the behavior the checker had before several named pins
(characterization); the second covers the named-pin grammar.
"""

import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

HERE = pathlib.Path(__file__).resolve().parent
CHECKER = HERE.parent / "scripts" / "anchor_check.py"

DRV_C = "\n".join([
    "/* widget driver */",                      # 1
    "#define WIDGET_CTRL 0x10",                 # 2
    "#define WIDGET_STAT 0x14",                 # 3
    "",                                         # 4
    "static int widget_reset(void)",            # 5
    "{",                                        # 6
    "    writel(1, base + WIDGET_CTRL);",       # 7
    "    udelay(10);",                          # 8
    "    return 0;",                            # 9
    "}",                                        # 10
]) + "\n"

FW_C = "\n".join([
    "/* firmware stub */",                      # 1
    "#define STUB_MAGIC 0x5afe570b",            # 2
    "void stub_entry(void) {}",                 # 3
]) + "\n"


def git(repo, *args):
    """Run git in repo with a fixed identity; return stdout."""
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com",
         "-c", "commit.gpgsign=false", *args],
        check=True, capture_output=True, text=True).stdout.strip()


def make_repo(root, name, files):
    """Create a git repo with one commit holding files; return (path, full rev)."""
    path = pathlib.Path(root) / name
    path.mkdir()
    git(path, "init", "-q")
    for rel, text in files.items():
        f = path / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text)
    git(path, "add", ".")
    git(path, "commit", "-q", "-m", "init")
    return path, git(path, "rev-parse", "HEAD")


def commit(path, files, msg="change"):
    for rel, text in files.items():
        (path / rel).write_text(text)
    git(path, "add", ".")
    git(path, "commit", "-q", "-m", msg)
    return git(path, "rev-parse", "HEAD")


class CheckerCase(unittest.TestCase):
    """Shared temp dir with a `linux` repo (drv.c) and a `fw` repo (stub.c)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="anchor-check-test-")
        cls.linux, cls.linux_rev = make_repo(cls.tmp, "linux", {"drivers/drv.c": DRV_C})
        cls.fw, cls.fw_rev = make_repo(cls.tmp, "fw", {"stub.c": FW_C})

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def spec(self, body):
        """Write a spec file with body (dedented) and return its path."""
        f = tempfile.NamedTemporaryFile("w", suffix=".md", dir=self.tmp, delete=False)
        f.write(textwrap.dedent(body))
        f.close()
        return f.name

    def run_check(self, *args):
        """Run the checker; return (rc, stdout+stderr)."""
        proc = subprocess.run([sys.executable, str(CHECKER), *map(str, args)],
                              capture_output=True, text=True)
        return proc.returncode, proc.stdout + proc.stderr

    def run_json(self, *args):
        """Run with --json; return (rc, report dict)."""
        proc = subprocess.run([sys.executable, str(CHECKER), *map(str, args), "--json"],
                              capture_output=True, text=True)
        self.assertIn(proc.returncode, (0, 1), proc.stderr)
        return proc.returncode, json.loads(proc.stdout)

    def messages(self, report, level=None):
        return [f["message"] for f in report["findings"]
                if level is None or f["level"] == level]


class TestCharacterization(CheckerCase):
    """Behavior with one pin per side, as before named pins."""

    def test_good_anchor_passes(self):
        s = self.spec(f"""\
            Source pin: linux@{self.linux_rev}

            The control register is at 0x10. [src: drivers/drv.c:2 (WIDGET_CTRL)]
            """)
        rc, out = self.run_check(s, "--repo", self.linux)
        self.assertEqual(rc, 0, out)
        self.assertIn("result: PASS", out)

    def test_missing_path_fails(self):
        s = self.spec(f"""\
            Source pin: linux@{self.linux_rev}

            Fact. [src: drivers/nope.c:1]
            """)
        rc, report = self.run_json(s, "--repo", self.linux)
        self.assertEqual(rc, 1)
        self.assertTrue(any("does not exist" in m for m in self.messages(report, "error")))

    def test_line_past_end_fails(self):
        s = self.spec(f"""\
            Source pin: linux@{self.linux_rev}

            Fact. [src: drivers/drv.c:10-11]
            """)
        rc, report = self.run_json(s, "--repo", self.linux)
        self.assertEqual(rc, 1)
        self.assertTrue(any("has 10 lines" in m for m in self.messages(report, "error")))

    def test_symbol_absent_fails_and_far_symbol_warns(self):
        s = self.spec(f"""\
            Source pin: linux@{self.linux_rev}

            Fact one. [src: drivers/drv.c:2 (no_such_symbol)]
            Fact two. [src: drivers/drv.c:2 (widget_reset)]
            """)
        rc, report = self.run_json(s, "--repo", self.linux)
        self.assertEqual(rc, 1)
        self.assertTrue(any("is not in" in m for m in self.messages(report, "error")))
        self.assertTrue(any("first appears at line 5" in m for m in self.messages(report, "warn")))

    def test_malformed_and_inverted_anchors(self):
        s = self.spec(f"""\
            Source pin: linux@{self.linux_rev}

            Fact one. [src: drivers/drv.c]
            Fact two. [src: drivers/drv.c:8-7]
            """)
        rc, report = self.run_json(s, "--repo", self.linux)
        self.assertEqual(rc, 1)
        errors = self.messages(report, "error")
        self.assertTrue(any("malformed src anchor" in m for m in errors))
        self.assertTrue(any("inverted line range" in m for m in errors))

    def test_several_anchors_in_one_tag(self):
        s = self.spec(f"""\
            Source pin: linux@{self.linux_rev}

            Reset writes CTRL then waits. [src: drivers/drv.c:7; drivers/drv.c:8]
            """)
        rc, report = self.run_json(s, "--repo", self.linux)
        self.assertEqual(rc, 0, report)
        self.assertEqual(report["anchors"], 2)

    def test_doc_tags(self):
        s = self.spec("""\
            Fact one. [doc: Widget TRM §4.3]
            Fact two. [doc: Widget TRM, the reset chapter]
            Fact three. [doc: ]
            """)
        rc, report = self.run_json(s)
        self.assertEqual(rc, 1)
        self.assertEqual(report["doc_tags"], 3)
        self.assertTrue(any("empty [doc:] tag" in m for m in self.messages(report, "error")))
        self.assertTrue(any("cites no section" in m for m in self.messages(report, "warn")))

    def test_stale_marker_fails(self):
        s = self.spec("Fact. [src: drivers/drv.c:2] [stale: was abc]\n")
        rc, report = self.run_json(s)
        self.assertEqual(rc, 1)
        self.assertTrue(any("marked stale" in m for m in self.messages(report, "error")))

    def test_untagged_fact_warns_and_strict_errors(self):
        body = "| Register | Offset |\n|---|---|\n| CTRL | 0x10 |\n"
        rc, report = self.run_json(self.spec(body))
        self.assertEqual(rc, 0)
        self.assertTrue(any("carries no" in m for m in self.messages(report, "warn")))
        rc, report = self.run_json(self.spec(body), "--strict")
        self.assertEqual(rc, 1)

    def test_block_anchor_covers_following_table(self):
        s = self.spec(f"""\
            Source pin: linux@{self.linux_rev}

            [src: drivers/drv.c:2-3]

            | Register | Offset |
            |---|---|
            | CTRL | 0x10 |
            | STAT | 0x14 |
            """)
        rc, report = self.run_json(s, "--repo", self.linux)
        self.assertEqual(rc, 0, report)
        self.assertFalse(any("carries no" in m for m in self.messages(report)))

    def test_hex_not_in_cited_lines_warns(self):
        s = self.spec(f"""\
            Source pin: linux@{self.linux_rev}

            The control register is at 0x99. [src: drivers/drv.c:2]
            """)
        rc, report = self.run_json(s, "--repo", self.linux)
        self.assertEqual(rc, 0)
        self.assertTrue(any("hex literals" in m for m in self.messages(report, "warn")))

    def test_no_repo_given_warns_unresolved(self):
        s = self.spec("Fact. [src: drivers/drv.c:2]\n")
        rc, report = self.run_json(s)
        self.assertEqual(rc, 0)
        self.assertTrue(any("not resolved" in m for m in self.messages(report, "warn")))

    def test_repo_without_rev_and_no_pin_is_usage_error(self):
        s = self.spec("Fact. [src: drivers/drv.c:2]\n")
        rc, out = self.run_check(s, "--repo", self.linux)
        self.assertEqual(rc, 2, out)

    def test_repo_with_explicit_rev_needs_no_pin(self):
        s = self.spec("Fact. [src: drivers/drv.c:2]\n")
        rc, out = self.run_check(s, "--repo", f"{self.linux}@{self.linux_rev}")
        self.assertEqual(rc, 0, out)

    def test_pins_reported(self):
        s = self.spec(f"""\
            Source pin: linux@{self.linux_rev}
            Target pin: fw@{self.fw_rev}
            """)
        rc, report = self.run_json(s)
        self.assertEqual(report["pins"]["source"]["rev"], self.linux_rev)
        self.assertEqual(report["pins"]["target"]["name"], "fw")

    def test_impl_and_ref_aliases(self):
        s = self.spec(f"""\
            Impl pin: linux@{self.linux_rev}
            Ref pin: fw@{self.fw_rev}

            Fact. [impl: drivers/drv.c:2]
            Fact. [ref: stub.c:2 (STUB_MAGIC)]
            """)
        rc, out = self.run_check(s, "--impl-repo", self.linux, "--ref-repo", self.fw)
        self.assertEqual(rc, 0, out)

    def test_missing_spec_is_usage_error(self):
        rc, out = self.run_check(pathlib.Path(self.tmp) / "absent.md")
        self.assertEqual(rc, 2, out)


class TestNamedPins(CheckerCase):
    """Several named pins per side (LS-R3)."""

    def two_pin_spec(self, extra=""):
        return self.spec(f"""\
            Source pin: linux@{self.linux_rev} GPL-2.0-only
            Source pin: fw@{self.fw_rev} BSD-3-Clause

            Control at 0x10. [src:linux: drivers/drv.c:2 (WIDGET_CTRL)]
            Magic 0x5afe570b. [src:fw: stub.c:2 (STUB_MAGIC)]
            """ + extra)

    def test_each_anchor_resolves_against_its_own_pin(self):
        rc, out = self.run_check(self.two_pin_spec(), "--repo", f"linux={self.linux}",
                                 "--repo", f"fw={self.fw}")
        self.assertEqual(rc, 0, out)
        self.assertIn("source pin: linux@", out)
        self.assertIn("(BSD-3-Clause)", out)

    def test_wrong_line_names_the_pin(self):
        s = self.two_pin_spec("Entry. [src:fw: stub.c:9]\n")
        rc, report = self.run_json(s, "--repo", f"linux={self.linux}", "--repo", f"fw={self.fw}")
        self.assertEqual(rc, 1)
        self.assertTrue(any(m.startswith("pin fw: stub.c has 3 lines")
                            for m in self.messages(report, "error")), report)

    def test_licenses_recorded_and_first_pin_kept(self):
        rc, report = self.run_json(self.two_pin_spec())
        names = [(p["name"], p["license"]) for p in report["pin_list"]["source"]]
        self.assertEqual(names, [("linux", "GPL-2.0-only"), ("fw", "BSD-3-Clause")])
        # Before named pins, the second pin silently replaced the first.
        self.assertEqual(report["pins"]["source"]["name"], "linux")

    def test_license_expression_with_spaces(self):
        s = self.spec(f"Source pin: linux@{self.linux_rev} GPL-2.0 OR MIT\n")
        rc, report = self.run_json(s)
        self.assertEqual(report["pin_list"]["source"][0]["license"], "GPL-2.0 OR MIT")

    def test_trailing_text_after_rev_is_not_a_pin(self):
        # Not SPDX-shaped: the line is not a pin, as before named pins.
        s = self.spec(f"Source pin: linux@{self.linux_rev} (v6.1 tag)\n")
        rc, report = self.run_json(s)
        self.assertEqual(report["pin_list"], {})

    def test_parenthesized_license_expression(self):
        s = self.spec(f"Source pin: linux@{self.linux_rev} (GPL-2.0-only OR MIT) AND BSD-3-Clause\n")
        rc, report = self.run_json(s)
        self.assertEqual(report["pin_list"]["source"][0]["license"],
                         "(GPL-2.0-only OR MIT) AND BSD-3-Clause")

    def test_named_target_pins(self):
        s = self.spec(f"""\
            Ref pin: linux@{self.linux_rev}
            Ref pin: fw@{self.fw_rev}

            Fact. [ref:linux: drivers/drv.c:2]
            Fact. [ref:fw: stub.c:9]
            """)
        rc, report = self.run_json(s, "--ref-repo", f"linux={self.linux}",
                                   "--ref-repo", f"fw={self.fw}")
        self.assertEqual(rc, 1)
        self.assertEqual([m for m in self.messages(report, "error")],
                         ["pin fw: stub.c has 3 lines; anchor cites 9-9"])
        rc, out = self.run_check(s, "--ref-repo", self.linux)
        self.assertEqual(rc, 2, out)
        self.assertIn("2 target pins", out)

    def test_repo_path_containing_equals_sign(self):
        weird, rev = make_repo(self.tmp, "a=b", {"x.c": "one\n"})
        s = self.spec(f"Source pin: linux@{rev}\n\nFact. [src: x.c:1]\n")
        rc, out = self.run_check(s, "--repo", str(weird))
        self.assertEqual(rc, 0, out)
        rc, out = self.run_check(s, "--repo", f"{weird}@{rev}")
        self.assertEqual(rc, 0, out)

    def test_duplicate_pin_name_fails(self):
        s = self.spec(f"""\
            Source pin: linux@{self.linux_rev}
            Source pin: linux@{self.fw_rev}
            """)
        rc, report = self.run_json(s)
        self.assertEqual(rc, 1)
        self.assertTrue(any("duplicate source pin name" in m for m in self.messages(report)))

    def test_unnamed_anchor_with_several_pins_fails(self):
        rc, report = self.run_json(self.two_pin_spec("Fact. [src: drivers/drv.c:3]\n"))
        self.assertEqual(rc, 1)
        self.assertTrue(any("names no pin" in m for m in self.messages(report, "error")))

    def test_anchor_naming_unknown_pin_fails(self):
        rc, report = self.run_json(self.two_pin_spec("Fact. [src:uboot: a.c:1]\n"))
        self.assertEqual(rc, 1)
        self.assertTrue(any("names pin 'uboot'" in m for m in self.messages(report, "error")))

    def test_bare_repo_with_several_pins_is_usage_error(self):
        rc, out = self.run_check(self.two_pin_spec(), "--repo", self.linux)
        self.assertEqual(rc, 2, out)
        self.assertIn("name one", out)

    def test_repo_naming_unknown_pin_is_usage_error(self):
        rc, out = self.run_check(self.two_pin_spec(), "--repo", f"uboot={self.linux}")
        self.assertEqual(rc, 2, out)
        self.assertIn("names pin 'uboot'", out)

    def test_repo_given_twice_for_one_pin_is_usage_error(self):
        rc, out = self.run_check(self.two_pin_spec(), "--repo", f"fw={self.fw}",
                                 "--repo", f"fw={self.fw}")
        self.assertEqual(rc, 2, out)
        self.assertIn("given twice for pin 'fw'", out)

    def test_named_anchor_with_single_pin_and_bare_repo(self):
        s = self.spec(f"""\
            Source pin: linux@{self.linux_rev}

            Fact at 0x10. [src:linux: drivers/drv.c:2]
            Same fact. [src: drivers/drv.c:2]
            """)
        rc, out = self.run_check(s, "--repo", self.linux)
        self.assertEqual(rc, 0, out)

    def test_one_pin_given_leaves_the_other_unresolved(self):
        rc, report = self.run_json(self.two_pin_spec(), "--repo", f"linux={self.linux}")
        self.assertEqual(rc, 0)
        self.assertTrue(any("1 [src:] anchors not resolved" in m for m in self.messages(report)))


class TestDrift(CheckerCase):
    """--drift and --rewrite, each test with its own source repo."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(dir=self.tmp)
        self.repo, self.rev = make_repo(self.dir, "src", {"drv.c": DRV_C})

    def test_moved_text_is_rewritten_and_changed_text_marked_stale(self):
        lines = DRV_C.split("\n")
        moved = "\n".join(["/* new header line */"] + lines)          # everything moves down 1
        moved = moved.replace("udelay(10)", "udelay(20)")              # line 8 text changes
        new_rev = commit(self.repo, {"drv.c": moved})
        s = self.spec(f"""\
            Source pin: src@{self.rev}

            Control at 0x10. [src: drv.c:2 (WIDGET_CTRL)]
            Waits 10 us. [src: drv.c:8]
            """)
        rc, out = self.run_check(s, "--repo", self.repo, "--drift", new_rev)
        self.assertEqual(rc, 1, out)
        self.assertIn("cited text moved", out)
        self.assertIn("cited text changed", out)
        rc, out = self.run_check(s, "--repo", self.repo, "--drift", new_rev, "--rewrite")
        text = pathlib.Path(s).read_text()
        self.assertIn(f"Source pin: src@{new_rev}", text)
        self.assertIn("[src: drv.c:3 (WIDGET_CTRL)]", text)
        self.assertIn(f"[src: drv.c:8] [stale: was {self.rev}]", text)

    def test_drift_with_several_pins_rewrites_only_the_chosen_pin(self):
        lines = DRV_C.split("\n")
        new_rev = commit(self.repo, {"drv.c": "\n".join(["/* new */"] + lines)})
        s = self.spec(f"""\
            Source pin: src@{self.rev} GPL-2.0-only
            Source pin: fw@{self.fw_rev} BSD-3-Clause

            Control at 0x10. [src:src: drv.c:2 (WIDGET_CTRL)]
            Magic 0x5afe570b. [src:fw: stub.c:2]
            """)
        repos = ["--repo", f"src={self.repo}", "--repo", f"fw={self.fw}"]
        rc, out = self.run_check(s, *repos, "--drift", new_rev)
        self.assertEqual(rc, 2, out)
        self.assertIn("--drift-pin", out)
        rc, out = self.run_check(s, *repos, "--drift", new_rev, "--drift-pin", "src", "--rewrite")
        text = pathlib.Path(s).read_text()
        self.assertIn(f"Source pin: src@{new_rev} GPL-2.0-only", text)
        self.assertIn(f"Source pin: fw@{self.fw_rev} BSD-3-Clause", text)
        self.assertIn("[src:src: drv.c:3 (WIDGET_CTRL)]", text)
        self.assertIn("[src:fw: stub.c:2]", text)

    def test_drift_pin_errors(self):
        s = self.spec(f"Source pin: src@{self.rev}\n")
        rc, out = self.run_check(s, "--repo", f"src={self.repo}", "--drift", self.rev,
                                 "--drift-pin", "nope")
        self.assertEqual(rc, 2, out)
        self.assertIn("--drift-pin 'nope' has no --repo", out)
        rc, out = self.run_check(s, "--repo", self.repo, "--drift-pin", "src")
        self.assertEqual(rc, 2, out)
        self.assertIn("--drift-pin needs --drift", out)

    def test_rewrite_needs_drift(self):
        s = self.spec(f"Source pin: src@{self.rev}\n")
        rc, out = self.run_check(s, "--repo", self.repo, "--rewrite")
        self.assertEqual(rc, 2, out)


GATE = HERE / "fixtures" / "license-gate"
PERMISSIVE_LIST = "Apache-2.0, MIT, BSD-2-Clause, BSD-3-Clause, ISC, 0BSD, X11, Zlib"


class TestLicenseGate(CheckerCase):
    """--root: the license gate (LS-R4), and SPDX validation of pin licenses."""

    def gate(self, spec_name, root_name, *extra):
        return self.run_json(GATE / "specs" / spec_name, "--root", GATE / "roots" / root_name, *extra)

    def gate_errors(self, report):
        return [m for m in self.messages(report, "error") if m.startswith("license gate:")]

    def test_fixture_matrix(self):
        """Every fixture spec against every repo-shaped root, as expected.json records."""
        expected = json.loads((GATE / "expected.json").read_text())
        expected.pop("comment")
        self.assertEqual(sorted(expected), sorted(p.name for p in (GATE / "specs").glob("*.md")))
        for spec_name, by_root in expected.items():
            for root_name, want in by_root.items():
                with self.subTest(spec=spec_name, root=root_name):
                    rc, report = self.gate(spec_name, root_name)
                    self.assertEqual(rc, want, self.messages(report))
                    errors = self.messages(report, "error")
                    if want:
                        self.assertTrue(any(m.startswith("license gate:") or
                                            "is not an SPDX expression" in m for m in errors), errors)
                    else:
                        self.assertEqual(errors, [])
                    self.assertEqual(report["license_gate"]["root"],
                                     str(GATE / "roots" / root_name))

    def test_message_names_anchor_pin_license_and_accepts(self):
        rc, report = self.gate("gpl-only-spec.md", "permissive")
        self.assertEqual(rc, 1)
        root = GATE / "roots" / "permissive"
        self.assertEqual(self.gate_errors(report), [
            "license gate: [src: drivers/widget.c:2 (WIDGET_CTRL)] cites source pin 'linux' "
            f"(GPL-2.0-only), which root {root} does not accept (accepts: {PERMISSIVE_LIST})"])
        rc, report = self.gate("gpl-only-spec.md", "docs")
        self.assertTrue(self.gate_errors(report)[0].endswith("(accepts: none)"), report)

    def test_or_passes_when_either_side_is_accepted(self):
        rc, report = self.gate("dual-gpl-mit-spec.md", "permissive")
        self.assertEqual(rc, 0, self.messages(report))
        rc, report = self.gate("dual-gpl-mit-spec.md", "docs")
        self.assertEqual(rc, 1)
        self.assertIn("(GPL-2.0 OR MIT), which root", self.gate_errors(report)[0])

    def test_and_needs_every_side_accepted(self):
        rc, report = self.gate("gpl-and-mit-spec.md", "permissive")
        self.assertEqual(rc, 1)
        self.assertIn("cites source pin 'mixed' (GPL-2.0-only AND MIT)", self.gate_errors(report)[0])
        rc, report = self.gate("gpl-and-mit-spec.md", "gpl")
        self.assertEqual(rc, 0, self.messages(report))

    def test_pin_without_license_fails(self):
        rc, report = self.gate("unlicensed-pin-spec.md", "gpl")
        self.assertEqual(rc, 1)
        self.assertIn("cites source pin 'tools', which states no license", self.gate_errors(report)[0])

    def test_anchor_without_pin_fails(self):
        rc, report = self.gate("no-pin-spec.md", "gpl")
        self.assertEqual(rc, 1)
        self.assertIn("[src: drivers/widget.c:2] has no source pin, so its source license is "
                      "unknown", self.gate_errors(report)[0])

    def test_only_the_unaccepted_pin_of_two_fails(self):
        rc, report = self.gate("two-pins-spec.md", "permissive")
        self.assertEqual(rc, 1)
        errors = self.gate_errors(report)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("[src:linux: drivers/widget.c:2] cites source pin 'linux' (GPL-2.0-only)",
                      errors[0])

    def test_uncited_pin_is_gated_too(self):
        rc, report = self.gate("uncited-gpl-pin-spec.md", "docs")
        self.assertEqual(rc, 1)
        self.assertIn("license gate: source pin 'linux' (GPL-2.0-only), which root", self.gate_errors(report)[0])
        self.assertIn("no anchor cites it", self.gate_errors(report)[0])

    def test_target_side_is_gated(self):
        rc, report = self.gate("bsd-target-spec.md", "docs")
        self.assertEqual(rc, 1)
        self.assertIn("[tgt: drivers/widget/widget.cc:12] cites target pin 'os' (BSD-3-Clause)",
                      self.gate_errors(report)[0])

    def test_impl_alias_is_gated(self):
        s = self.spec("Impl pin: linux@1111111 GPL-2.0-only\n\nFact. [impl: drivers/widget.c:2]\n")
        rc, report = self.run_json(s, "--root", GATE / "roots" / "permissive")
        self.assertEqual(rc, 1)
        self.assertIn("cites source pin 'linux' (GPL-2.0-only)", self.gate_errors(report)[0])

    def make_root(self, marker):
        root = pathlib.Path(tempfile.mkdtemp(dir=self.tmp))
        (root / "board-specs.yaml").write_text(marker)
        return root

    def test_root_without_accepts_fails_closed(self):
        root = self.make_root("layer: public\nlicense: Apache-2.0\n")
        rc, report = self.run_json(GATE / "specs" / "docs-only-spec.md", "--root", root)
        self.assertEqual(rc, 1)
        self.assertIn(f"license gate: root {root} declares no accepts: list, so the gate cannot run",
                      self.messages(report, "error")[0])

    def test_malformed_accepts_fails(self):
        root = self.make_root("layer: public\nlicense: Apache-2.0\naccepts: [MIT, GPL-2]\n")
        rc, report = self.run_json(GATE / "specs" / "docs-only-spec.md", "--root", root)
        self.assertEqual(rc, 1)
        self.assertIn(f"--root {root}: root marker: accepts entry 'GPL-2': unknown SPDX license "
                      "identifier 'GPL-2'", self.messages(report, "error")[0])
        root = self.make_root("layer: public\nlicense: Apache-2.0\naccepts: MIT\n")
        rc, report = self.run_json(GATE / "specs" / "bsd-spec.md", "--root", root)
        self.assertEqual(rc, 1)
        self.assertIn("accepts: must be a list", "\n".join(self.messages(report, "error")))
        self.assertTrue(self.gate_errors(report), report)

    def test_root_without_marker_is_usage_error(self):
        rc, out = self.run_check(GATE / "specs" / "docs-only-spec.md", "--root", self.tmp)
        self.assertEqual(rc, 2, out)
        self.assertIn(f"--root {self.tmp}: no board-specs.yaml", out)

    def test_invalid_pin_license_fails_without_root(self):
        rc, report = self.run_json(GATE / "specs" / "invalid-license-spec.md")
        self.assertEqual(rc, 1)
        self.assertEqual(self.messages(report, "error"), [
            "source pin 'linux': license 'mainline' is not an SPDX expression: unknown SPDX "
            "license identifier 'mainline' (the known identifiers are listed in "
            "board-expert/scripts/spdx.py; write LicenseRef-<name> for a license SPDX does not list)"])

    def test_no_gate_without_root(self):
        rc, report = self.run_json(GATE / "specs" / "gpl-only-spec.md")
        self.assertEqual(rc, 0, self.messages(report))
        self.assertEqual(report["license_gate"], {})

    def test_gate_with_anchors_resolved(self):
        s = self.spec(f"""\
            Source pin: linux@{self.linux_rev} GPL-2.0-only

            Control at 0x10. [src: drivers/drv.c:2 (WIDGET_CTRL)]
            """)
        rc, report = self.run_json(s, "--repo", self.linux, "--root", GATE / "roots" / "gpl")
        self.assertEqual(rc, 0, self.messages(report))
        rc, report = self.run_json(s, "--repo", self.linux, "--root", GATE / "roots" / "permissive")
        self.assertEqual(rc, 1)
        self.assertEqual(len(self.messages(report, "error")), 1, report)
        self.assertEqual(len(self.gate_errors(report)), 1, report)

    def test_human_report_states_the_gate(self):
        rc, out = self.run_check(GATE / "specs" / "bsd-spec.md", "--root", GATE / "roots" / "docs")
        self.assertEqual(rc, 1, out)
        self.assertIn(f"license gate: root {GATE / 'roots' / 'docs'} accepts: none", out)
        self.assertIn("result: FAIL", out)


    def test_lowercase_operator_is_read_and_rejected(self):
        s = self.spec("Source pin: linux@1111111 GPL-2.0 or MIT\n\nFact. [src: drivers/widget.c:2]\n")
        rc, report = self.run_json(s)
        self.assertEqual(rc, 1)
        self.assertIn("license 'GPL-2.0 or MIT' is not an SPDX expression: 'or': write the "
                      "operator in uppercase (OR)", self.messages(report, "error")[0])

    def test_document_ref_license_is_read(self):
        s = self.spec("Source pin: fw@1111111 DocumentRef-spdx-tools:LicenseRef-blob\n\n"
                      "Fact. [src: stub.c:2]\n")
        rc, report = self.run_json(s, "--root", GATE / "roots" / "permissive")
        self.assertEqual(report["pin_list"]["source"][0]["license"],
                         "DocumentRef-spdx-tools:LicenseRef-blob")
        self.assertEqual(rc, 1)
        self.assertIn("cites source pin 'fw' (DocumentRef-spdx-tools:LicenseRef-blob), which root",
                      self.gate_errors(report)[0])

    def test_unread_pin_line_warns_and_fails_the_gate(self):
        """A dropped pin line must not let unnamed anchors bind to the other pin (a false accept)."""
        s = self.spec("Source pin: fw@439b619 BSD-3-Clause\n"
                      "Source pin: linux@1111111 ( GPL-2.0-only )\n\n"
                      "Fact. [src: drivers/widget.c:2]\n")
        rc, report = self.run_json(s)
        self.assertEqual(rc, 0, self.messages(report))
        self.assertIn("line starts like a pin but is not read as one: 'Source pin: linux@1111111 "
                      "( GPL-2.0-only )'", self.messages(report, "warn")[0])
        rc, report = self.run_json(s, "--root", GATE / "roots" / "permissive")
        self.assertEqual(rc, 1)
        self.assertTrue(any(m.startswith("line starts like a pin but is not read as one")
                            for m in self.messages(report, "error")), report)

    def test_license_unverifiable_without_board_expert_is_an_error(self):
        alone = pathlib.Path(tempfile.mkdtemp(dir=self.tmp)) / "a" / "b" / "scripts"
        alone.mkdir(parents=True)
        shutil.copy(CHECKER, alone / "anchor_check.py")
        shutil.copy(CHECKER.parent / "mdtokens.py", alone / "mdtokens.py")
        proc = subprocess.run([sys.executable, str(alone / "anchor_check.py"),
                               str(GATE / "specs" / "invalid-license-spec.md")],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("pin licenses cannot be validated: board-expert's spdx.py was not found",
                      proc.stdout)
        proc = subprocess.run([sys.executable, str(alone / "anchor_check.py"),
                               str(GATE / "specs" / "docs-only-spec.md")],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


class TestDocTagCharacterization(CheckerCase):
    """Unnamed [doc: …] tags as they behaved before named doc anchors (LS3); these pass on
    LS2's checker and must keep passing."""

    def test_unnamed_forms_count_and_warn_as_before(self):
        s = self.spec("""\
            ---
            # SPDX-License-Identifier: CC-BY-4.0
            ---

            # Widget

            - Resets in 10 us. [doc: Widget TRM v1.0 §4.2]
            - FIFO depth 64. [doc: Widget TRM v1.0 p. 88; Widget DS table 3]
            - Clock gating. [doc: Widget TRM, the clocks chapter]
            - One word. [doc: trm p.12]
            """)
        rc, report = self.run_json(s)
        self.assertEqual(rc, 0, self.messages(report))
        self.assertEqual(report["doc_tags"], 4)
        self.assertEqual(report["anchors"], 0)
        self.assertEqual(self.messages(report), [
            "[doc:] cites no section/chapter/table number: 'Widget TRM, the clocks chapter'"])

    def test_empty_doc_tag_errors_with_or_without_space(self):
        s = self.spec("Fact one. [doc: ]\nFact two. [doc:]\n")
        rc, report = self.run_json(s)
        self.assertEqual(rc, 1)
        self.assertEqual(self.messages(report, "error"), ["empty [doc:] tag", "empty [doc:] tag"])

    def test_unnamed_doc_tags_pass_every_gate_root(self):
        for root in ("docs", "permissive", "gpl"):
            with self.subTest(root=root):
                rc, report = self.gate_run(root)
                self.assertEqual(rc, 0, self.messages(report))
                self.assertEqual(self.messages(report, "error"), [])

    def gate_run(self, root):
        return self.run_json(GATE / "specs" / "docs-only-spec.md", "--root", GATE / "roots" / root)

    def test_human_report_for_a_doc_only_spec(self):
        s = self.spec("- Resets in 10 us. [doc: Widget TRM v1.0 §4.2]\n")
        rc, out = self.run_check(s)
        self.assertEqual(rc, 0, out)
        self.assertEqual(out, f"spec: {s}\nanchors: 0  doc tags: 1\nresult: PASS (0 errors, "
                              "0 warnings)\n")

    def test_hw_required_needs_a_doc_tag_on_the_line(self):
        s = self.spec("- Must wait 10 us [hw-required]. [doc: Widget TRM §4.2]\n"
                      "- Must wait 20 us [hw-required].\n")
        rc, report = self.run_json(s)
        self.assertEqual(rc, 0)
        self.assertEqual([(f["spec_line"], f["message"]) for f in report["findings"]], [
            (2, "[hw-required] with no [doc:] on the line — if no document backs it, label it "
                "[as-implemented]")])


# Small generated documents with pinned hashes (LS3). The tests write them per run.
TRM_BYTES = b"synthetic widget TRM, LS3 fixture\n"
TRM_SHA = "1218036a6a0562504adedd37088e5136036a3099cf8581832e0c7353d7256cbd"
DS_BYTES = b"synthetic widget datasheet, LS3 fixture\n"
DS_SHA = "8e64f02ccae1c95703da9cdb01ddf491a136a9edd784739824a4618a25983768"
REGISTRY = f"""\
---
docs:
  - name: trm
    title: Widget TRM v1.0
    url: https://example.invalid/widget-trm.pdf
    sha256: {TRM_SHA}
    pages: 120
  - name: ds
    title: Widget datasheet
    url: https://example.invalid/widget-ds.pdf
    sha256: "{DS_SHA.upper()}"
    file: sheets/widget-ds.pdf
# SPDX-License-Identifier: CC-BY-4.0
---

"""


class TestNamedDocAnchors(CheckerCase):
    """The docs: registry and named [doc:<name> …] anchors (LS-R5)."""

    def test_pinned_hashes_match_the_generated_bytes(self):
        import hashlib
        self.assertEqual(hashlib.sha256(TRM_BYTES).hexdigest(), TRM_SHA)
        self.assertEqual(hashlib.sha256(DS_BYTES).hexdigest(), DS_SHA)
        rc, report = self.run_json(self.spec(REGISTRY + "- Fact. [doc:trm p.1]\n"))
        self.assertEqual([d["sha256"] for d in report["docs"]], [TRM_SHA, DS_SHA])

    def docs_dir(self, trm=TRM_BYTES, ds=DS_BYTES):
        d = pathlib.Path(tempfile.mkdtemp(dir=self.tmp))
        if trm is not None:
            (d / "trm.pdf").write_bytes(trm)
        if ds is not None:
            (d / "sheets").mkdir()
            (d / "sheets" / "widget-ds.pdf").write_bytes(ds)
        return d

    def test_correct_spec_passes(self):
        # The bullets are dedented on their own: REGISTRY is not indented, so dedenting the
        # whole would leave them as a 12-space indented code block, which holds no anchors.
        s = self.spec(REGISTRY + textwrap.dedent("""\
            - Resets in 10 us. [doc:trm p.12]
            - FIFO depth 64. [doc:trm pp.12-14]
            - Clock gating. [doc:trm §4.3]
            - Last page. [doc:trm §A.1 p.120]
            - Both documents. [doc:trm p.12; ds §3.1]
            - Unnamed beside them. [doc: Widget app note §2]
            """))
        for extra in ((), ("--strict",), ("--docs-dir", self.docs_dir())):
            with self.subTest(extra=extra):
                rc, report = self.run_json(s, *extra)
                self.assertEqual(rc, 0, self.messages(report))
                self.assertEqual(report["findings"], [])
        self.assertEqual(report["doc_tags"], 6)
        self.assertEqual([(a["name"], a["pages"], a["sections"]) for a in report["doc_anchors"]], [
            ("trm", [[12, 12]], []), ("trm", [[12, 14]], []), ("trm", [], ["4.3"]),
            ("trm", [[120, 120]], ["A.1"]), ("trm", [[12, 12]], []), ("ds", [], ["3.1"])])
        self.assertEqual([(d["name"], d["pages"], d["file"]) for d in report["docs"]],
                         [("trm", 120, None), ("ds", None, "sheets/widget-ds.pdf")])
        rc, out = self.run_check(s)
        self.assertIn("doc trm: Widget TRM v1.0, 120 pages\ndoc ds: Widget datasheet\n", out)
        # No network: the checker imports nothing that could fetch the url.
        source = CHECKER.read_text()
        for module in ("urllib", "http", "socket", "requests", "ssl"):
            self.assertNotRegex(source, rf"(?m)^\s*(import|from)\s+{module}\b")

    def test_unknown_document_fails_naming_anchor_and_registry(self):
        s = self.spec(REGISTRY + "- Fact. [doc:tmr p.3]\n")
        rc, report = self.run_json(s)
        self.assertEqual(rc, 1)
        self.assertEqual([(f["spec_line"], f["message"]) for f in report["findings"]], [
            (16, "[doc:tmr p.3] names document 'tmr', but the spec's docs: registry lists: "
                 "trm, ds (for an unnamed citation put a space after 'doc:')")])

    def test_named_anchor_without_registry_fails(self):
        rc, report = self.run_json(self.spec("- Fact. [doc:trm §4.2]\n"))
        self.assertEqual(rc, 1)
        self.assertEqual(self.messages(report), [
            "[doc:trm §4.2] names document 'trm', but the spec's docs: registry lists: none "
            "(for an unnamed citation put a space after 'doc:')"])

    def test_page_out_of_range_fails(self):
        s = self.spec(REGISTRY + "- A. [doc:trm p.121]\n- B. [doc:trm pp.119-122]\n"
                                 "- C. [doc:ds p.900]\n")
        rc, report = self.run_json(s)
        self.assertEqual(rc, 1)
        self.assertEqual(self.messages(report), [
            "[doc:trm p.121] cites page 121, but document 'trm' (Widget TRM v1.0) has 120 pages",
            "[doc:trm pp.119-122] cites pages 119-122, but document 'trm' (Widget TRM v1.0) has "
            "120 pages"])  # ds lists no pages: any page passes

    def test_page_zero_and_inverted_range_fail(self):
        s = self.spec(REGISTRY + "- A. [doc:trm p.0]\n- B. [doc:trm pp.14-12]\n")
        rc, report = self.run_json(s)
        self.assertEqual(rc, 1)
        self.assertEqual(self.messages(report), [
            "[doc:trm p.0] cites page 0; pages count from 1",
            "[doc:trm pp.14-12] has an inverted page range 14-12"])

    def test_malformed_named_anchor_fails(self):
        s = self.spec(REGISTRY + "- A. [doc:trm]\n- B. [doc:trm page 12]\n- C. [doc:trm p12]\n"
                                 "- D. [doc:Widget TRM §4]\n")
        rc, report = self.run_json(s)
        self.assertEqual(rc, 1)
        forms = ("(expected [doc:<name> p.N], [doc:<name> pp.N-M] or [doc:<name> §x.y]; for an "
                 "unnamed citation put a space after 'doc:')")
        self.assertEqual(self.messages(report), [
            f"malformed named doc anchor [doc:{item}] {forms}"
            for item in ("trm", "trm page 12", "trm p12", "Widget TRM §4")])

    def test_malformed_or_missing_sha256_fails(self):
        s = self.spec("""\
            ---
            docs:
              - name: a
                title: A
                url: https://example.invalid/a.pdf
                sha256: 1234abcd
              - name: b
                title: B
                url: https://example.invalid/b.pdf
              - name: c
                title: C
                url: https://example.invalid/c.pdf
                sha256: 1234
            ---
            - Fact. [doc:a p.1; b p.1; c p.1]
            """)
        rc, report = self.run_json(s)
        self.assertEqual(rc, 1)
        self.assertEqual([(f["spec_line"], f["message"]) for f in report["findings"]], [
            (3, "docs: entry 1 ('a'): sha256: '1234abcd' is not 64 hex digits (quote it if it "
                "is all digits)"),
            (7, "docs: entry 2 ('b'): sha256: is required (the document file's SHA-256, 64 hex "
                "digits)"),
            (10, "docs: entry 3 ('c'): sha256: 1234 is not 64 hex digits (quote it if it is all "
                 "digits)")])

    def test_registry_fields_are_validated(self):
        s = self.spec(f"""\
            ---
            docs:
              - name: trm
                url: https://example.invalid/t.pdf
                sha256: {TRM_SHA}
                pages: -3
                edition: 2
              - name: trm
                title: Again
                url: https://example.invalid/t2.pdf
                sha256: {TRM_SHA}
              - name: "bad name"
                title: X
                url: x
                sha256: {TRM_SHA}
              - name: up
                title: Up
                url: https://example.invalid/u.pdf
                sha256: {TRM_SHA}
                file: ../outside.pdf
            ---
            - Fact. [doc:trm p.400]
            """)
        rc, report = self.run_json(s)
        self.assertEqual(rc, 1)
        self.assertEqual(self.messages(report, "error"), [
            "docs: entry 1 ('trm'): title: is required (a non-empty string)",
            "docs: entry 1 ('trm'): pages: -3 is not a positive page count",
            "docs: entry 2 ('trm'): duplicate document name 'trm': each document needs a "
            "distinct name",
            "docs: entry 3 ('bad name'): name: must be a short identifier (letters, digits, '.', "
            "'_', '-'), as in [doc:<name> p.N]",
            "docs: entry 4 ('up'): file: '../outside.pdf' must be a relative path inside "
            "--docs-dir"])
        self.assertEqual(self.messages(report, "warn"), [
            "docs: entry 1 ('trm'): unknown key 'edition' (known: name, title, url, sha256, "
            "pages, file)"])
        s = self.spec("---\ndocs: trm\n---\n- Fact. [doc: TRM §1]\n")
        rc, report = self.run_json(s)
        self.assertEqual(rc, 1)
        self.assertEqual(self.messages(report), [
            "docs: must be a list of documents (name, title, url, sha256, optional pages and "
            "file)"])

    def test_hash_mismatch_fails_only_with_docs_dir(self):
        s = self.spec(REGISTRY + "- Fact. [doc:trm p.2]\n")
        tampered = self.docs_dir(trm=b"a different file\n")
        rc, report = self.run_json(s)
        self.assertEqual(rc, 0, self.messages(report))
        self.assertEqual(report["findings"], [])
        rc, report = self.run_json(s, "--docs-dir", tampered)
        self.assertEqual(rc, 1)
        import hashlib
        actual = hashlib.sha256(b"a different file\n").hexdigest()
        self.assertEqual([(f["spec_line"], f["message"]) for f in report["findings"]], [
            (3, f"document 'trm' (Widget TRM v1.0): {tampered / 'trm.pdf'} has sha256 {actual}, "
                f"but the registry records {TRM_SHA}")])

    def test_explicit_file_is_hashed(self):
        s = self.spec(REGISTRY + "- Fact. [doc:ds §1]\n")
        bad = self.docs_dir(ds=b"not the datasheet\n")
        rc, report = self.run_json(s, "--docs-dir", bad)
        self.assertEqual(rc, 1)
        self.assertIn(f"document 'ds' (Widget datasheet): {bad / 'sheets' / 'widget-ds.pdf'} has "
                      "sha256 ", self.messages(report, "error")[0])
        self.assertTrue(self.messages(report, "error")[0].endswith(f"records {DS_SHA}"))

    def test_missing_file_is_skipped_with_a_note(self):
        s = self.spec(REGISTRY + "- Fact. [doc:trm p.2]\n")
        d = self.docs_dir(trm=None)
        rc, report = self.run_json(s, "--docs-dir", d)
        self.assertEqual(rc, 0, self.messages(report))
        self.assertEqual(self.messages(report), [
            f"document 'trm': {d / 'trm.pdf'} not found; hash not checked"])

    def test_docs_dir_must_be_a_directory(self):
        rc, out = self.run_check(self.spec(REGISTRY), "--docs-dir",
                                 pathlib.Path(self.tmp) / "absent")
        self.assertEqual(rc, 2, out)
        self.assertIn(f"error: --docs-dir {pathlib.Path(self.tmp) / 'absent'} is not a directory",
                      out)

    def test_front_matter_is_not_read_as_spec_lines(self):
        s = self.spec(REGISTRY + "| Register | Offset |\n|---|---|\n| CTRL | 0x10 | [doc:trm p.4]\n")
        rc, report = self.run_json(s, "--strict")
        self.assertEqual(rc, 0, self.messages(report))
        self.assertEqual(report["findings"], [])

    def test_leading_horizontal_rule_block_is_body_text(self):
        """A spec opening with a '---' rule keeps its first section checked (review finding 1)."""
        cases = {
            "list": "---\n- Reg STAT at 0x14.\n- Reg CTRL at 0x10 [src:nosuch.c:abc]\n---\n",
            "mapping": "---\nNote: CTRL at 0x10 [src: nosuch.c:abc]\n---\n",
        }
        for name, body in cases.items():
            with self.subTest(case=name):
                rc, report = self.run_json(self.spec(body))
                self.assertEqual(rc, 1)
                # "Note: ...\n---" is a setext heading in CommonMark: outside the spec
                # Markdown profile, reported on its own line (RG-T1 round 7).
                setext = [f["spec_line"] for f in report["findings"]
                          if f["message"].startswith("a setext heading")]
                self.assertEqual(setext, [] if name == "list" else [2])
                self.assertEqual([(f["spec_line"], f["message"]) for f in report["findings"]
                                  if f["level"] == "error"
                                  and not f["message"].startswith("a setext heading")],
                                 [(3 if name == "list" else 2, "malformed src anchor: "
                                   "'nosuch.c:abc' (expected [pin: ]path:L1[-L2] [(symbol)])")])
        s = self.spec("---\n- Resets. [doc: Widget TRM §4.2]\n---\n")
        rc, report = self.run_json(s)
        self.assertEqual(rc, 0, self.messages(report))
        self.assertEqual((report["findings"], report["doc_tags"]), ([], 1))
        s = self.spec("---\ndocs: [unclosed\n---\n- Fact. [doc: TRM §1]\n")
        rc, report = self.run_json(s)
        self.assertEqual(rc, 1)
        self.assertTrue(self.messages(report)[0].startswith("front matter does not parse: "),
                        report)

    def test_front_matter_without_board_expert_is_an_error(self):
        alone = pathlib.Path(tempfile.mkdtemp(dir=self.tmp)) / "a" / "b" / "scripts"
        alone.mkdir(parents=True)
        shutil.copy(CHECKER, alone / "anchor_check.py")
        shutil.copy(CHECKER.parent / "mdtokens.py", alone / "mdtokens.py")
        proc = subprocess.run([sys.executable, str(alone / "anchor_check.py"),
                               self.spec(REGISTRY + "- Fact. [doc:trm p.2]\n")],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("ERROR L1: spec front matter cannot be read: board-expert's spec_check.py "
                      "was not found", proc.stdout)


class TestRequireNamedDocs(CheckerCase):
    """--require-license: named doc anchors required in a root that accepts no source."""

    UNNAMED = "- Resets in 10 us. [doc: Widget TRM v1.0 §4.2]\n"

    def test_unnamed_doc_fails_in_a_docs_root_under_require_license(self):
        s = self.spec(self.UNNAMED)
        root = GATE / "roots" / "docs"
        rc, report = self.run_json(s, "--root", root)
        self.assertEqual(rc, 0, self.messages(report))
        rc, report = self.run_json(s, "--root", root, "--require-license")
        self.assertEqual(rc, 1)
        self.assertEqual([(f["spec_line"], f["message"]) for f in report["findings"]], [
            (1, f"unnamed [doc: Widget TRM v1.0 §4.2]: root {root} accepts no source, so "
                "documents are its specs' only provenance and --require-license requires named "
                "ones: list the document under docs: in the front matter and cite "
                "[doc:<name> p.N]")])

    def test_named_doc_passes_in_a_docs_root_under_require_license(self):
        s = self.spec(REGISTRY + "- Resets in 10 us. [doc:trm §4.2 p.40]\n")
        rc, report = self.run_json(s, "--root", GATE / "roots" / "docs", "--require-license")
        self.assertEqual(rc, 0, self.messages(report))
        self.assertEqual(report["findings"], [])

    def test_unnamed_doc_passes_in_roots_that_accept_sources(self):
        s = self.spec(self.UNNAMED)
        for root in ("permissive", "gpl"):
            with self.subTest(root=root):
                rc, report = self.run_json(s, "--root", GATE / "roots" / root,
                                           "--require-license")
                self.assertEqual(rc, 0, self.messages(report))
                self.assertEqual(report["findings"], [])

    def test_spec_repository_self_test_pairs(self):
        """The fit and misfit fixtures each spec repository's CI self-test copies (LS5).

        Run as the repositories run them, with --require-license: the fit passes clean and the
        misfit fails with a license-gate error (beside others, such as the docs root's demand
        for named document anchors).
        """
        pairs = {"gpl": ("gpl-only-spec.md", "gpl3-only-spec.md"),
                 "docs": ("docs-named-spec.md", "gpl-only-spec.md"),
                 "permissive": ("bsd-spec.md", "gpl-only-spec.md")}
        for root, (fit, misfit) in pairs.items():
            with self.subTest(root=root):
                rc, report = self.run_json(GATE / "specs" / fit, "--root", GATE / "roots" / root,
                                           "--require-license")
                self.assertEqual(rc, 0, self.messages(report))
                self.assertEqual(self.messages(report, "error"), [])
                rc, report = self.run_json(GATE / "specs" / misfit, "--root",
                                           GATE / "roots" / root, "--require-license")
                self.assertEqual(rc, 1, self.messages(report))
                self.assertTrue(any(m.startswith("license gate:")
                                    for m in self.messages(report, "error")),
                                self.messages(report))

    def test_named_docs_fixture_passes_every_root_under_require_license(self):
        for root in ("gpl", "docs", "permissive"):
            with self.subTest(root=root):
                rc, report = self.run_json(GATE / "specs" / "docs-named-spec.md", "--root",
                                           GATE / "roots" / root, "--require-license")
                self.assertEqual(rc, 0, self.messages(report))
                self.assertEqual(report["findings"], [])
        rc, report = self.run_json(GATE / "specs" / "docs-only-spec.md", "--root",
                                   GATE / "roots" / "docs", "--require-license")
        self.assertEqual(rc, 1, self.messages(report))

    def test_require_license_needs_root(self):
        rc, out = self.run_check(self.spec(self.UNNAMED), "--require-license")
        self.assertEqual(rc, 2, out)
        self.assertIn("error: --require-license needs --root DIR", out)

    def test_require_license_requires_the_marker_license(self):
        root = pathlib.Path(tempfile.mkdtemp(dir=self.tmp))
        (root / "board-specs.yaml").write_text("layer: public\naccepts: [MIT]\n")
        s = self.spec(self.UNNAMED)
        rc, report = self.run_json(s, "--root", root)
        self.assertEqual(rc, 0, self.messages(report))
        rc, report = self.run_json(s, "--root", root, "--require-license")
        self.assertEqual(rc, 1)
        self.assertEqual(self.messages(report), [
            f"--root {root}: root marker: no license: field (the SPDX expression for this "
            "root's own license); --require-license makes this an error"])



class TestBoardSpecPins(CheckerCase):
    """A board spec's resources.repos entries are its Source pins (RG-T1, [src] facts)."""

    def board(self, ref, lic="BSD-3-Clause", body_pin=""):
        return self.spec(f"""\
            ---
            overlays: widgetchip
            resources:
              repos:
                - name: fw
                  url: https://example.invalid/fw
                  ref: {ref}
                  license: {lic}
            ---

            {body_pin}

            ## Quick-facts

            - **Magic.** The stub's magic word is 0x5afe570b. `[src]`
              ([src:fw: stub.c:2 (STUB_MAGIC)])
            """)

    def test_repos_entry_is_a_pin_and_anchors_resolve(self):
        s = self.board(self.fw_rev)
        rc, report = self.run_json(s, "--repo", f"fw={self.fw}")
        self.assertEqual(rc, 0, self.messages(report))
        self.assertEqual([(p["name"], p["rev"], p["license"]) for p in report["pin_list"]["source"]],
                         [("fw", self.fw_rev, "BSD-3-Clause")])
        self.assertEqual(report["anchors"], 1)
        self.assertNotIn("anchors not resolved", "\n".join(self.messages(report)))

    def test_a_wrong_line_fails_against_the_repos_pin(self):
        s = self.board(self.fw_rev)
        path = pathlib.Path(s)
        path.write_text(path.read_text().replace("stub.c:2 (STUB_MAGIC)", "stub.c:9"))
        rc, report = self.run_json(s, "--repo", f"fw={self.fw}")
        self.assertEqual(rc, 1)
        self.assertTrue(any("has 3 lines" in m for m in self.messages(report, "error")))

    def test_license_gate_reads_the_repos_license(self):
        s = self.board(self.fw_rev)
        rc, report = self.run_json(s, "--root", GATE / "roots" / "permissive", "--require-license")
        self.assertEqual(rc, 0, self.messages(report))
        for root in ("docs",):
            rc, report = self.run_json(s, "--root", GATE / "roots" / root, "--require-license")
            self.assertEqual(rc, 1)
            self.assertTrue(any(m.startswith("license gate: [src:fw: stub.c:2 (STUB_MAGIC)] cites "
                                             "source pin 'fw' (BSD-3-Clause)")
                                for m in self.messages(report, "error")), self.messages(report))

    def test_an_agreeing_source_pin_line_is_allowed(self):
        s = self.board(self.fw_rev, body_pin=f"Source pin: fw@{self.fw_rev} BSD-3-Clause")
        rc, report = self.run_json(s, "--repo", f"fw={self.fw}")
        self.assertEqual(rc, 0, self.messages(report))
        self.assertEqual(len(report["pin_list"]["source"]), 1)

    def test_a_disagreeing_source_pin_line_fails(self):
        for line in (f"Source pin: fw@{self.linux_rev} BSD-3-Clause", f"Source pin: fw@{self.fw_rev} MIT",
                     f"Source pin: fw@{self.fw_rev}"):
            with self.subTest(line=line):
                s = self.board(self.fw_rev, body_pin=line)
                rc, report = self.run_json(s)
                self.assertEqual(rc, 1)
                self.assertTrue(any("disagrees with resources.repos entry 'fw'" in m
                                    for m in self.messages(report, "error")), self.messages(report))

    def test_a_peripheral_spec_without_resources_is_unchanged(self):
        s = self.spec(f"""\
            ---
            docs: []
            ---
            Source pin: linux@{self.linux_rev}

            The control register is at 0x10. [src: drivers/drv.c:2 (WIDGET_CTRL)]
            """)
        rc, report = self.run_json(s, "--repo", self.linux)
        self.assertEqual(rc, 0, self.messages(report))
        self.assertEqual([p["name"] for p in report["pin_list"]["source"]], ["linux"])



class TestBoardSpecReviewFixes(CheckerCase):
    """RG-T1 review findings (2026-10-07): each test fails without its fix."""

    def board(self, body, note=""):
        return self._write(body, note)

    def _write(self, body, note):
        head = textwrap.dedent(f"""\
            ---
            overlays: widgetchip
            resources:
              repos:
                - name: fw
                  url: https://example.invalid/fw
                  ref: {self.fw_rev}
                  license: BSD-3-Clause{note}
            ---

            ## Quick-facts

            """)
        f = tempfile.NamedTemporaryFile("w", suffix=".spec.md", dir=self.tmp, delete=False)
        f.write(head + textwrap.dedent(body))
        f.close()
        return f.name

    def test_wrapped_bullet_keeps_its_claim_for_the_hex_check(self):
        body = """\
            - **Magic.** The stub's magic word is 0xdeadbeef and nothing else, as written here.
              `[src]` ([src:fw: stub.c:2 (STUB_MAGIC)])
            """
        rc, report = self.run_json(self.board(body), "--repo", f"fw={self.fw}")
        self.assertTrue(any("none of the claim's hex literals (0xdeadbeef)" in m
                            for m in self.messages(report, "warn")), self.messages(report))

    def test_a_sibling_anchor_holding_the_value_satisfies_the_hex_check(self):
        body = """\
            - **Magic.** The stub's magic word is 0x5afe570b, and the entry point follows it.
              `[src]` ([src:fw: stub.c:2 (STUB_MAGIC)];
              [src:fw: stub.c:3 (stub_entry)])
            """
        rc, report = self.run_json(self.board(body), "--repo", f"fw={self.fw}")
        self.assertEqual(rc, 0, self.messages(report))
        self.assertEqual(self.messages(report, "warn"), [])

    def test_untagged_fact_heuristic_is_off_for_board_specs(self):
        body = """\
            - **Offset.** The register at offset 0x10 resets to zero. `[doc]` (Widget TRM §4)
            """
        rc, report = self.run_json(self.board(body))
        self.assertFalse(any("carries no" in m for m in self.messages(report)), self.messages(report))

    def test_unnamed_anchor_fails_in_a_board_spec(self):
        body = "- **Magic.** Value 0x5afe570b. `[src]` ([src: stub.c:2])\n"
        rc, report = self.run_json(self.board(body), "--repo", f"fw={self.fw}")
        self.assertEqual(rc, 1)
        self.assertTrue(any("in a board spec write [src:<repo>: stub.c:2]" in m
                            for m in self.messages(report, "error")), self.messages(report))

    def test_empty_anchor_fails(self):
        for tag in ("[src:]", "[src: ; ]"):
            with self.subTest(tag=tag):
                rc, report = self.run_json(self.board(f"- **Empty.** A fact. `[src]` ({tag})\n"))
                self.assertEqual(rc, 1)
                self.assertTrue(any("empty [src:] anchor" in m for m in self.messages(report, "error")))

    def test_anchor_in_a_front_matter_note_keeps_the_pins(self):
        note = "\n" + " " * 18 + 'note: "the stub, cited as [src:fw: stub.c:2] below"'
        rc, report = self.run_json(self.board("- **Magic.** Value. `[src]` ([src:fw: stub.c:2])\n", note),
                                   "--repo", f"fw={self.fw}")
        self.assertEqual(rc, 0, self.messages(report))
        self.assertEqual([p["name"] for p in report["pin_list"]["source"]], ["fw"])

    def test_drift_rewrite_moves_the_repos_ref(self):
        repo, rev = make_repo(self.tmp, "fw-drift", {"stub.c": FW_C})
        new_rev = commit(repo, {"stub.c": "/* moved */\n" + FW_C})
        path = self.spec(f"""\
            ---
            overlays: widgetchip
            resources:
              repos:
                - name: fw
                  url: https://example.invalid/fw
                  ref: {rev}
                  license: BSD-3-Clause
            ---

            ## Quick-facts

            - **Magic.** 0x5afe570b. `[src]` ([src:fw: stub.c:2 (STUB_MAGIC)])
            """)
        rc, out = self.run_check(path, "--repo", f"fw={repo}", "--drift", "HEAD", "--rewrite")
        text = pathlib.Path(path).read_text()
        self.assertIn(f"ref: {new_rev}", text, out)
        self.assertNotIn(rev, text)
        self.assertIn("[src:fw: stub.c:3 (STUB_MAGIC)]", text)
        rc, report = self.run_json(path, "--repo", f"fw={repo}")
        self.assertEqual(rc, 0, self.messages(report))


class TestRound2Fixes(CheckerCase):
    """RG-T1 round-2 review findings: each test fails without its fix."""

    board = TestBoardSpecReviewFixes.board
    _write = TestBoardSpecReviewFixes._write

    def test_a_value_at_the_start_of_a_long_item_is_still_checked(self):
        body = ("- **Magic.** The magic word is 0xdeadbeef. " + "word " * 70 + "\n"
                "  `[src]` ([src:fw: stub.c:2 (STUB_MAGIC)])\n")
        rc, report = self.run_json(self.board(body), "--repo", f"fw={self.fw}")
        self.assertTrue(any("none of the claim's hex literals (0xdeadbeef)" in m
                            for m in self.messages(report, "warn")), self.messages(report))

    def test_line_zero_fails(self):
        rc, report = self.run_json(self.board("- **Zero.** A fact. `[src]` ([src:fw: stub.c:0])\n"))
        self.assertEqual(rc, 1)
        self.assertTrue(any("lines count from 1" in m for m in self.messages(report, "error")))

    def test_drift_rewrite_touches_the_repos_entry_not_a_same_named_doc(self):
        repo, rev = make_repo(self.tmp, "fw-drift2", {"stub.c": FW_C})
        new_rev = commit(repo, {"stub.c": "/* moved */\n" + FW_C})
        path = self.spec(f"""\
            ---
            overlays: widgetchip
            resources:
              docs:
                - name: fw
                  title: Firmware manual
                  url: https://example.invalid/fw.pdf
                  ref: manual-v1
              repos:
                - name: fw
                  url: https://example.invalid/fw
                  ref: {rev}
                  license: BSD-3-Clause
            ---

            ## Quick-facts

            - **Magic.** 0x5afe570b. `[src]` ([src:fw: stub.c:2 (STUB_MAGIC)])
            """)
        rc, out = self.run_check(path, "--repo", f"fw={repo}", "--drift", "HEAD", "--rewrite")
        text = pathlib.Path(path).read_text()
        self.assertIn("ref: manual-v1", text, out)
        self.assertIn(f"ref: {new_rev}", text, out)
        self.assertNotIn(rev, text)


class TestRound3Fixes(CheckerCase):
    """RG-T1 round-3 review findings: each test fails without its fix."""

    LAYOUTS = {
        "comment after repos": "  repos: # pinned firmware\n    - name: fw\n      url: https://example.invalid/fw\n      ref: {rev}\n      license: BSD-3-Clause\n",
        "dash at the repos indent": "  repos:\n  - name: fw\n    url: https://example.invalid/fw\n    ref: {rev}  # the pin\n    license: BSD-3-Clause\n",
    }

    def test_drift_rewrite_finds_the_entry_in_valid_layouts(self):
        for label, block in self.LAYOUTS.items():
            with self.subTest(layout=label):
                repo, rev = make_repo(self.tmp, f"fw-l{len(label)}", {"stub.c": FW_C})
                new_rev = commit(repo, {"stub.c": "/* moved */\n" + FW_C})
                f = tempfile.NamedTemporaryFile("w", suffix=".spec.md", dir=self.tmp, delete=False)
                f.write("---\noverlays: widgetchip\nresources:\n" + block.format(rev=rev) +
                        "---\n\n## Quick-facts\n\n- **Magic.** 0x5afe570b. `[src]` "
                        "([src:fw: stub.c:2 (STUB_MAGIC)])\n")
                f.close()
                rc, out = self.run_check(f.name, "--repo", f"fw={repo}", "--drift", "HEAD", "--rewrite")
                text = pathlib.Path(f.name).read_text()
                self.assertIn(new_rev, text, out)
                self.assertNotIn(rev, text)
                self.assertIn("[src:fw: stub.c:3 (STUB_MAGIC)]", text)

    def test_drift_rewrite_writes_nothing_when_the_ref_cannot_be_set(self):
        repo, rev = make_repo(self.tmp, "fw-flow", {"stub.c": FW_C})
        commit(repo, {"stub.c": "/* moved */\n" + FW_C})
        f = tempfile.NamedTemporaryFile("w", suffix=".spec.md", dir=self.tmp, delete=False)
        f.write("---\noverlays: widgetchip\nresources:\n  repos:\n"
                f"    - {{name: fw, url: https://example.invalid/fw, ref: {rev}, license: BSD-3-Clause}}\n"
                "---\n\n## Quick-facts\n\n- **Magic.** 0x5afe570b. `[src]` "
                "([src:fw: stub.c:2 (STUB_MAGIC)])\n")
        f.close()
        before = pathlib.Path(f.name).read_text()
        rc, out = self.run_check(f.name, "--repo", f"fw={repo}", "--drift", "HEAD", "--rewrite")
        self.assertEqual(pathlib.Path(f.name).read_text(), before, out)
        self.assertIn("nothing was written", out)
        self.assertNotIn("pin is now", out)


FETCH = HERE.parent.parent / "board-expert" / "scripts" / "fetch_src_pins.py"


class TestFetchSrcPins(CheckerCase):
    """board-expert's fetch_src_pins.py: the CI path that resolves board-spec anchors.

    Real specs may only name https:// URLs; these tests fetch local repositories through the
    hidden --allow-local flag, which adds file:// and nothing else.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.aux, cls.aux_rev = make_repo(cls.tmp, "aux", {"aux.c": "int aux;\n"})
        for repo in (cls.fw, cls.aux):
            git(repo, "config", "uploadpack.allowFilter", "true")
            git(repo, "config", "uploadpack.allowAnySHA1InWant", "true")

    def spec_for(self, url, ref, anchors="[src:fw: stub.c:2 (STUB_MAGIC)]", extra=""):
        f = tempfile.NamedTemporaryFile("w", suffix=".spec.md", dir=self.tmp, delete=False)
        f.write("---\noverlays: widgetchip\nresources:\n  repos:\n" + extra +
                f"    - name: fw\n      url: {url}\n      ref: {ref}\n      license: BSD-3-Clause\n"
                f"    - name: aux\n      url: file://{self.aux}\n      ref: {self.aux_rev}\n"
                "      license: BSD-3-Clause\n---\n\n## Quick-facts\n\n"
                f"- **Magic.** 0x5afe570b. `[src]` ({anchors})\n")
        f.close()
        return f.name

    def fetch(self, spec, *args, cache=None):
        cache = cache or tempfile.mkdtemp(dir=self.tmp)
        proc = subprocess.run([sys.executable, str(FETCH), spec, cache, *args],
                              capture_output=True, text=True)
        return proc.returncode, proc.stdout.split(), proc.stderr

    def test_fetches_the_pin_and_anchors_resolve(self):
        spec = self.spec_for(f"file://{self.fw}", self.fw_rev)
        rc, repos, err = self.fetch(spec, "--allow-local")
        self.assertEqual(rc, 0, err)
        self.assertEqual(len(repos), 1, err)
        self.assertTrue(repos[0].startswith("fw="))
        rc, report = self.run_json(spec, "--repo", repos[0])
        self.assertEqual(rc, 0, self.messages(report))
        self.assertNotIn("anchors not resolved", "\n".join(self.messages(report)))

    def test_only_https_without_the_test_flag(self):
        rc, repos, err = self.fetch(self.spec_for(f"file://{self.fw}", self.fw_rev))
        self.assertEqual((rc, repos), (1, []))
        self.assertIn("is not an https:// URL", err)

    def test_an_option_shaped_url_never_runs(self):
        probe = pathlib.Path(self.tmp) / "PWNED"
        url = f"--upload-pack=touch {probe}"
        rc, repos, err = self.fetch(self.spec_for(url, self.fw_rev), "--allow-local")
        self.assertEqual(rc, 1)
        self.assertFalse(probe.exists())
        # And the git call itself: the URL sits after "--", so even past the scheme check, and
        # with the local transport allowed (which would otherwise run the upload-pack), it is a
        # repository name, never an option.
        sys.path.insert(0, str(FETCH.parent))
        import fetch_src_pins  # noqa: PLC0415
        local = fetch_src_pins.GIT_SAFE + ["-c", "protocol.file.allow=always"]
        kind, why = fetch_src_pins.fetch(url, str(self.fw), pathlib.Path(tempfile.mkdtemp(dir=self.tmp)),
                                         1 << 30, 60, local)
        self.assertEqual(kind, "fail", why)
        self.assertFalse(probe.exists())

    def test_over_the_limit_is_skipped_with_a_note(self):
        rc, repos, err = self.fetch(self.spec_for(f"file://{self.fw}", self.fw_rev),
                                    "--allow-local", "--limit-mb", "0")
        self.assertEqual((rc, repos), (0, []))
        self.assertIn("skipped (size: the fetched objects are 0 MB, over the 0 MB limit)", err)

    def test_an_unknown_commit_fails(self):
        rc, repos, err = self.fetch(self.spec_for(f"file://{self.fw}", "deadbeef" * 5), "--allow-local")
        self.assertEqual((rc, repos), (1, []))
        self.assertIn("error:", err)
        self.assertIn("git fetch failed", err)

    def test_branch_ref_fails(self):
        rc, repos, err = self.fetch(self.spec_for(f"file://{self.fw}", "main"), "--allow-local")
        self.assertEqual((rc, repos), (1, []))
        self.assertIn("is not a full commit id", err)

    def test_discovery_uses_the_anchor_parser(self):
        for anchors in ("[src: fw: stub.c:2]; [src:aux: aux.c:1]", "[src:fw: stub.c:2; aux: aux.c:1]"):
            with self.subTest(anchors=anchors):
                rc, repos, err = self.fetch(self.spec_for(f"file://{self.fw}", self.fw_rev, anchors),
                                            "--allow-local")
                self.assertEqual(rc, 0, err)
                self.assertEqual(sorted(r.split("=")[0] for r in repos), ["aux", "fw"])

    def test_a_malformed_unused_entry_does_not_crash(self):
        extra = "    - name: [unexpected-list]\n      url: https://example.invalid/x\n"
        rc, repos, err = self.fetch(self.spec_for(f"file://{self.fw}", self.fw_rev, extra=extra),
                                    "--allow-local")
        self.assertEqual(rc, 0, err)
        self.assertEqual([r.split("=")[0] for r in repos], ["fw"])

    def test_a_second_spec_reuses_the_fetch(self):
        cache = tempfile.mkdtemp(dir=self.tmp)
        spec = self.spec_for(f"file://{self.fw}", self.fw_rev)
        rc, first, _ = self.fetch(spec, "--allow-local", cache=cache)
        marker = pathlib.Path(first[0].split("=", 1)[1]) / "reused"
        marker.write_text("x")
        rc, second, err = self.fetch(spec, "--allow-local", cache=cache)
        self.assertEqual((rc, second), (0, first), err)
        self.assertTrue(marker.exists())


class TestOneMarkdownParse(CheckerCase):
    """RG-T1 round 6: code blocks, code spans and list items come from mdtokens, the parse
    spec_check.py reads too (user decision 2026-10-08)."""

    def anchors(self, body):
        rc, report = self.run_json(self.spec(f"Source pin: linux@{self.linux_rev}\n\n" + body))
        return rc, report

    def test_a_code_span_holding_only_an_anchor_is_that_anchor(self):
        rc, report = self.anchors("- Fact. `[src: drivers/nope.c:1]`\n")
        self.assertEqual(report["anchors"], 1)

    def test_an_anchor_in_a_longer_code_span_or_a_fence_is_prose(self):
        rc, report = self.anchors("- Fact. `see [src: drivers/nope.c:1]`\n\n"
                                  "~~~\n[src: drivers/nope.c:2]\n~~~\n")
        self.assertEqual(report["anchors"], 0)

    def test_an_uppercase_anchor_kind_is_an_error(self):
        for anchor in ("[SRC: drivers/drv.c:2]", "[Doc: TRM §1]", "[STALE: was x]"):
            with self.subTest(anchor=anchor):
                rc, report = self.anchors(f"- Fact. {anchor}\n")
                self.assertEqual(rc, 1)
                self.assertTrue(any("is not lowercase" in m
                                    for m in self.messages(report, "error")))

    def test_an_unclosed_fence_is_an_error(self):
        rc, report = self.anchors("```\n- Fact. [src: drivers/drv.c:2]\n")
        self.assertEqual(rc, 1)
        self.assertTrue(any("code fence never closes" in m for m in self.messages(report, "error")))

    def test_list_items_are_the_parse_s_items(self):
        # "2." cannot interrupt a paragraph in CommonMark, so this is paragraph text, not an
        # untagged list item; "* " can, so the next line is an item and its fact is flagged.
        rc, report = self.anchors("Intro text\n2. Delay 0x10 ms\n* Timeout 0x20 ms\n")
        warned = [m for m in self.messages(report, "warn") if "carries no" in m]
        self.assertEqual(len(warned), 1, warned)
        self.assertIn("0x20", warned[0])

    def test_a_nested_item_is_its_own_claim(self):
        # The outer item states 0x10, which the cited line holds; the nested item's own claim
        # (0xbeef) does not appear there, so its anchor warns. Reading the nested item as part
        # of the outer one would borrow 0x10 and hide the mismatch.
        s = self.spec(f"""\
            Source pin: linux@{self.linux_rev}

            - Outer 0x10.
              - Inner 0xbeef. [src: drivers/drv.c:2 (WIDGET_CTRL)]
            """)
        rc, report = self.run_json(s, "--repo", self.linux)
        self.assertTrue(any("0xbeef" in m for m in self.messages(report, "warn")),
                        self.messages(report))


class TestSharedAnchorShape(CheckerCase):
    """RG-T1 round 7 (Codex round 6, blocker 1): a malformed [src: anchor fails anchor_check
    too, in a documents-only root under --require-license."""

    def test_malformed_anchors_fail_in_a_docs_root(self):
        root = pathlib.Path(tempfile.mkdtemp(dir=self.tmp))
        (root / "board-specs.yaml").write_text("layer: public\nlicense: CC-BY-4.0\naccepts: []\n")
        cases = {
            "unterminated at EOF": ("A fact. [src:fw: foo.c:1", "no closing ']'"),
            "split across lines": ("A fact. [src:fw: foo.c:\n1]\n", "broken across lines"),
            "spaced": ("A fact. [s r c:fw: foo.c:1]\n", "broken across lines"),
        }
        for name, (body, want) in cases.items():
            with self.subTest(case=name):
                rc, report = self.run_json(self.spec(body), "--root", root, "--require-license")
                self.assertEqual(rc, 1, self.messages(report))
                self.assertTrue(any(want in m for m in self.messages(report, "error")),
                                self.messages(report))

    def test_an_indented_4_closer_leaves_the_fence_open(self):
        rc, report = self.run_json(self.spec("```\n- Fact. [src: drivers/drv.c:2]\n    ```\n"))
        self.assertTrue(any("code fence never closes" in m for m in self.messages(report, "error")))


class TestNoProfileExceptions(CheckerCase):
    """RG-T1 round 9 (user decision 2026-10-08): no HTML block or block quote anywhere; the
    SPDX header is YAML comments in the front matter."""

    def test_html_and_quotes_fail_anywhere(self):
        for body in ("<!-- SPDX-License-Identifier: CC-BY-4.0 -->\n\nText.\n",
                     "## Source notices\n\n> Copyright Example.\n"):
            with self.subTest(body=body):
                rc, report = self.run_json(self.spec(body))
                self.assertEqual(rc, 1)
                self.assertTrue(any("outside the spec Markdown profile" in m
                                    for m in self.messages(report, "error")))

    def test_a_comment_only_front_matter_is_front_matter(self):
        rc, report = self.run_json(self.spec(
            "---\n# SPDX-FileCopyrightText: 2026 contributors\n# SPDX-License-Identifier: "
            "CC-BY-4.0\n---\n\n# Widget\n\n- Resets. [doc: Widget TRM §4.2]\n"))
        self.assertEqual((rc, report["findings"]), (0, []))
        # The block is front matter, not body: a comment in it is never read as an anchor.
        rc, report = self.run_json(self.spec(
            "---\n# SPDX-License-Identifier: CC-BY-4.0 [src: drivers/nope.c:1]\n---\n\nText.\n"))
        self.assertEqual((rc, report["anchors"]), (0, 0), self.messages(report))

    def test_entities_and_link_metadata(self):
        for body, want in (("- Fact. &#91;src: drivers/drv.c:2&#93;\n", "character reference"),
                           ('- Fact. ([m](https://e.com "[src: drivers/drv.c:2]"))\n',
                            "provenance is read only from link text")):
            with self.subTest(body=body):
                rc, report = self.run_json(self.spec(body))
                self.assertEqual(rc, 1)
                self.assertEqual(report["anchors"], 0)
                self.assertTrue(any(want in m for m in self.messages(report, "error")))

if __name__ == "__main__":
    unittest.main()
