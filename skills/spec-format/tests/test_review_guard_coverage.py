# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Previously working guards missed by the original mutation tests."""

import subprocess
import os
from unittest import mock

from test_resolve import GitFixture, SOURCE, cli
import drift
import resolve


class SurvivingMutantCoverage(GitFixture):

    def test_spdx_tag_on_line_five_is_checked(self):
        for license_id in ("MIT", "BSD-2-Clause"):
            (self.repo / "code.c").write_text(
                "int VALUE = 0x10;\n// second\n// third\n// fourth\n"
                f"// SPDX-License-Identifier: {license_id}\n"
            )
            self.entry["commit"] = self.commit_all()
            self.anchor["lines"] = [1, 1]
            code, result = self.run_cli()
            self.assertEqual(code, int(license_id != "MIT"), result)
            if code:
                self.assertIn("differs", str(result))

    def test_absolute_dt_override_is_one_token(self):
        lines = ["/ { soc { uart: uart@0 {}; }; };",
                 "&{/soc/uart@0} { new: child@1 {}; };"]
        self.assertEqual(resolve.node_range(lines, "new"), [2, 2])
        self.assertEqual(resolve.node_range(lines, "child@1"), [2, 2])
        self.assertEqual(resolve.node_range(lines, "/soc/uart@0"), [1, 1])
        try:
            root = resolve.node_range(lines, "/")
        except resolve.ContentError as exc:
            root = str(exc)
        self.assertEqual(root, [1, 1], "an absolute override must not create phantom roots")
        with self.assertRaises(resolve.ContentError):
            resolve.node_range(lines, "/child@1")

    def test_git_hooks_prompt_and_system_config(self):
        with mock.patch.dict(os.environ, {"GIT_CONFIG_COUNT": "0"}), mock.patch.object(resolve.subprocess, "run", wraps=subprocess.run) as run:
            resolve.git(self.repo, ["rev-parse", "--show-toplevel"], 30, 1 << 20)
        call = run.call_args
        self.assertIn("core.hooksPath=/dev/null", call.args[0])
        self.assertEqual(call.kwargs.get("env", {}).get("GIT_TERMINAL_PROMPT"), "0")
        self.assertEqual(call.kwargs.get("env", {}).get("GIT_CONFIG_NOSYSTEM"), "1")
        self.assertEqual(call.kwargs.get("env", {}).get("GIT_CONFIG_GLOBAL"), os.devnull)
        self.assertEqual(call.kwargs.get("env", {}).get("GIT_ALLOW_PROTOCOL"), "https")
        self.assertNotIn("GIT_CONFIG_COUNT", call.kwargs.get("env", {}))

    def test_spdx_comment_close_is_removed(self):
        for header in ("/* SPDX-License-Identifier: MIT */", "<!-- SPDX-License-Identifier: MIT -->"):
            (self.repo / "code.c").write_text(header + "\nint VALUE = 0x10;\n")
            self.entry["commit"] = self.commit_all()
            code, result = self.run_cli()
            self.assertEqual(code, 0, result)

    def test_blank_line_cannot_be_relocated(self):
        old, new = mock.Mock(), mock.Mock()
        old.lines.return_value = ["header", "", "tail"]
        new.lines.return_value = ["header", "tail", ""]
        self.assertEqual(drift.compare(old, new, dict(path="code.c", lines=[2, 2])), ("stale", None))

    def test_stale_insertion_preserves_crlf(self):
        source = f"commit: '{self.commit}'\r\na:\r\n  repo: code\r\n  lines: [2, 2]\r\n"
        expected = source.replace(self.commit, "a" * 40) + f"  stale: {{was: '{self.commit}'}}\r\n"
        self.assertEqual(drift.rewrite(source, ("commit",), "a" * 40,
                                      [(("a",), "stale", None)], self.commit), expected)

    def test_stale_insertion_without_final_newline(self):
        source = f"commit: '{self.commit}'\na:\n  repo: code\n  lines: [2, 2]"
        expected = source.replace(self.commit, "a" * 40) + f"\n  stale: {{was: '{self.commit}'}}\n"
        self.assertEqual(drift.rewrite(source, ("commit",), "a" * 40,
                                      [(("a",), "stale", None)], self.commit), expected)

    def test_same_position_wins_over_other_matches(self):
        old, new = mock.Mock(), mock.Mock()
        old.lines.return_value = ["head", "cited"]
        new.lines.return_value = ["head", "cited", "cited"]
        self.assertEqual(drift.compare(old, new, dict(path="code.c", lines=[2, 2])), ("same", [2, 2]))

    def test_moved_candidate_revalidates_symbol(self):
        old, new = mock.Mock(), mock.Mock()
        old.lines.return_value = ["VALUE", "cited"]
        new.lines.return_value = ["VALUE", *(["gap"] * 210), "cited"]
        self.assertEqual(drift.compare(old, new, dict(path="code.c", lines=[2, 2], symbol="VALUE")), ("stale", None))

    def test_old_pin_license_mismatch_keeps_original(self):
        (self.repo / "code.c").write_text(SOURCE.replace("MIT", "BSD-2-Clause"))
        self.entry["commit"] = self.commit_all()
        self.write()
        original = self.path.read_bytes()
        (self.repo / "code.c").write_text(SOURCE)
        revision = self.commit_all()
        code, result = cli("drift", revision, self.path, "--repo", f"code={self.repo}", "--rewrite")
        self.assertEqual(code, 1, result)
        self.assertIn("differs", str(result))
        self.assertEqual(self.path.read_bytes(), original)
