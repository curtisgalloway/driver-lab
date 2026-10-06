#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""
Tests for scripts/anchor_check.py, against synthetic git repositories built per run.

Run:  python3 -m unittest discover -s skills/anchored-peripheral-spec/tests -v

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


if __name__ == "__main__":
    unittest.main()
