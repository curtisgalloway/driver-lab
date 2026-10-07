# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for utilities/check-open-side.py.

Each test builds a throwaway git repository, plants files in it and runs the checker as CI does,
so the exit code and the reported location are what is asserted, not only the scan function.
"""

from __future__ import annotations

import importlib.util
import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "check-open-side.py"
_spec = importlib.util.spec_from_file_location("check_open_side", SCRIPT)
check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check)


class Repo:
    """A temporary git repository with tracked files."""

    def __init__(self, files: dict[str, str], untracked: dict[str, str] | None = None):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        subprocess.run(["git", "init", "-q", self.root], check=True)
        for rel, text in files.items():
            self._write(rel, text)
        if files:
            subprocess.run(["git", "-C", self.root, "add", "--", *files], check=True)
        for rel, text in (untracked or {}).items():
            self._write(rel, text)

    def _write(self, rel: str, text: str) -> None:
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)

    def run(self, *extra: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = check.main(["--root", self.root, *extra])
        return code, out.getvalue(), err.getvalue()

    def close(self) -> None:
        self._tmp.cleanup()


class CheckOpenSideTest(unittest.TestCase):
    def make(self, files, untracked=None) -> Repo:
        repo = Repo(files, untracked)
        self.addCleanup(repo.close)
        return repo

    def test_clean_repository_passes(self):
        repo = self.make({"DESIGN.md": "# Design\n\nAnchored specs cite their sources.\n"})
        code, out, _ = repo.run()
        self.assertEqual(code, 0)
        self.assertIn("OK: 1 tracked files", out)

    def test_planted_mention_fails_with_its_location(self):
        repo = self.make(
            {
                "DESIGN.md": "# Design\n\nline two\nUse the clean-room route here.\n",
                "skills/x/SKILL.md": "fine\n",
            }
        )
        code, out, err = repo.run()
        self.assertEqual(code, 1)
        self.assertIn("DESIGN.md:4: [clean-room] Use the clean-room route here.", out)
        self.assertNotIn("SKILL.md", out)
        self.assertIn("FAIL: 1 clean-room mention", err)

    def test_every_term_is_detected(self):
        planted = {
            "clean-room": ["a clean-room spec", "the Cleanroom pipeline", "a clean room",
                           "cleanroom-implementer", "cleanroom_sandbox.sh", "cleanroom-skills"],
            "os-investigator": ["load os-investigator first"],
            "the wall": ["behind the wall"],
            "licensing wall": ["what crosses the licensing wall"],
            "research subagent": ["ask a research subagent"],
            "dirty/clean side": ["the dirty side reads", "a clean-side artifact"],
            "moved script": ["run leak_scan.py", "sandbox_audit.py reads it",
                             "session_audit.py"],
            "method term": ["encumbered source", "an attractant", "the provenance ledger",
                            "a transfer review"],
        }
        for name, lines in planted.items():
            for line in lines:
                with self.subTest(line=line):
                    hits = check.matching_lines(f"ok\n{line}\n")
                    self.assertEqual(hits, [(2, name, line)])

    def test_near_misses_are_not_mentions(self):
        text = "the walls of the enclosure\na clean build\nroom for growth\nside effects\n"
        self.assertEqual(check.matching_lines(text), [])

    def test_allowlisted_paths_pass(self):
        mention = "Ran under cleanroom_sandbox.sh with os-investigator behind the wall.\n"
        allowed = [
            "evals/e1000/README.md",
            "evidence/L02f2.md",
            "notebook/L01.md",
            "history/notes.txt",
            "RECONSTRUCTION.md",
            "QEMU-DIFFERENTIAL.md",
            "EVAL-PLAN.md",
            "VALIDATION-PROPOSAL.md",
            "VALIDATION-REVIEW.md",
            "IMPLEMENTATION-PLAN.md",
            "DEFERRED-PLAN.md",
            "docs/LICENSE-SPLIT.md",
            "docs/LICENSE-SPLIT-PLAN.md",
            "skills/campaign-review/tests/fixtures/deployment-cr5.yaml",
            "PROCESS-NOTES.md",
            "TRANSITION.md",
            "docs/STORY.md",
        ]
        repo = self.make({path: mention for path in allowed})
        code, out, _ = repo.run()
        self.assertEqual(code, 0, out)

    def test_allowlist_matches_whole_paths_only(self):
        mention = "a clean-room note\n"
        repo = self.make(
            {
                "evals-notes.md": mention,
                "docs/evals/x.md": mention,
                "skills/campaign-review/tests/fixtures/deployment-cr6.yaml": mention,
                "sub/IMPLEMENTATION-PLAN.md": mention,
            }
        )
        code, out, _ = repo.run()
        self.assertEqual(code, 1)
        for path in ("evals-notes.md", "docs/evals/x.md", "deployment-cr6.yaml",
                     "sub/IMPLEMENTATION-PLAN.md"):
            self.assertIn(path, out)

    def test_readme_may_carry_one_pointer_line(self):
        repo = self.make({"README.md": "# x\n\nThe clean-room skills live in cleanroom-skills.\n"})
        code, out, _ = repo.run()
        self.assertEqual(code, 0, out)

    def test_a_second_readme_mention_fails(self):
        repo = self.make(
            {"README.md": "# x\n\nPointer: cleanroom-skills.\n\nAlso os-investigator here.\n"}
        )
        code, out, _ = repo.run()
        self.assertEqual(code, 1)
        self.assertIn("README.md:5: [os-investigator]", out)
        self.assertNotIn("README.md:3:", out)

    def test_a_readme_mention_that_is_not_the_pointer_fails(self):
        repo = self.make({"README.md": "# x\n\nWe ship a clean-room pipeline.\n"})
        code, out, _ = repo.run()
        self.assertEqual(code, 1)
        self.assertIn("README.md:3: [clean-room]", out)

    def test_untracked_files_are_not_scanned(self):
        repo = self.make({"a.md": "fine\n"}, untracked={"scratch.md": "clean-room notes\n"})
        code, _, _ = repo.run()
        self.assertEqual(code, 0)

    def test_not_a_repository_is_a_usage_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = check.main(["--root", os.path.join(tmp, "missing")])
        self.assertEqual(code, 2)
        self.assertIn("cannot list tracked files", err.getvalue())

    def test_unknown_option_is_a_usage_error(self):
        err = io.StringIO()
        with redirect_stderr(err):
            code = check.main(["--no-such-option"])
        self.assertEqual(code, 2)

    def test_script_runs_as_ci_does(self):
        repo = self.make({"GLOSSARY.md": "| Dirty side | reads source |\n"})
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", repo.root],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 1)
        self.assertIn("GLOSSARY.md:1: [dirty/clean side]", proc.stdout)


if __name__ == "__main__":
    unittest.main()
