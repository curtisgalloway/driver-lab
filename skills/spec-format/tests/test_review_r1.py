# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Round-one bug regressions; each test fails against the original export."""

import copy
import json
from pathlib import Path
import subprocess
import sys
from unittest import mock

from test_resolve import GitFixture, SOURCE, cli
import drift
import resolve
import spec
import specload


class ReviewFixes(GitFixture):

    def script(self, *args, isolated=False):
        return subprocess.run(
            [sys.executable, *(["-I"] if isolated else []), str(spec.HERE / "spec.py"),
             *map(str, args)], capture_output=True, text=True, check=False,
        )

    def test_script_usage_errors(self):
        self.write()
        absent = self.base / "absent"
        bad_file = self.base / "wrong.yaml"
        bad_file.write_text(self.path.read_text())
        options = [
            ["--timeout", "0"], ["--limit-mb", "0"],
            ["--docs-dir", absent], ["--repo", "bad"],
            ["--root", absent], ["--root", self.base],
            ["--repo", "code="], ["--repo", "=somewhere"],
            ["--repo", f"code={self.repo}", "--repo", f"code={self.repo}"],
            ["--repo", f"code={absent}"], ["--repo", f"absent={self.repo}"],
        ]
        cases = []
        for command in ("resolve", "show", "drift"):
            lead = [command, self.commit] if command == "drift" else [command]
            cases.extend([*lead, self.path, *opts] for opts in options)
            cases.extend([*lead, path] for path in (absent, self.base, bad_file))
        cases.extend([
            ["drift", "HEAD", self.path],
            ["drift", self.commit, self.path, self.path],
            ["drift", self.commit, self.path, "--pin", "absent"],
        ])
        duplicate = copy.deepcopy(self.data)
        duplicate["resources"]["repos"].append(copy.deepcopy(self.entry))
        import yaml

        dup_path = self.base / "duplicate.spec.yaml"
        dup_path.write_text(yaml.safe_dump(duplicate, sort_keys=False))
        cases.append(["drift", self.commit, dup_path])
        multiple = copy.deepcopy(self.data)
        second = dict(copy.deepcopy(self.entry), name="second")
        multiple["resources"]["repos"].append(second)
        multiple["facts"][0]["support"][0]["anchors"].append(
            dict(copy.deepcopy(self.anchor), repo="second")
        )
        multi_path = self.base / "multiple.spec.yaml"
        multi_path.write_text(yaml.safe_dump(multiple, sort_keys=False))
        cases.append(["drift", self.commit, multi_path])
        for args in cases:
            for json_out in (False, True):
                with self.subTest(args=args, json=json_out):
                    proc = self.script(*args, *(["--json"] if json_out else []))
                    self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
                    self.assertNotIn("Traceback", proc.stderr)
                    if f"code={absent}" in args:
                        self.assertIn("not a directory", proc.stdout + proc.stderr)
                    if json_out:
                        self.assertEqual(json.loads(proc.stdout)["error"], "usage")

    def test_isolated_check_imports(self):
        proc = self.script("check", self.base / "absent", isolated=True)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)

    def test_git_replace_cannot_change_pin(self):
        (self.repo / "code.c").write_text(SOURCE.replace("0x10", "0x99"))
        other = self.commit_all()
        self.git("replace", self.commit, other)
        code, result = self.run_cli("show")
        self.assertEqual(code, 0, result)
        self.assertEqual(result["anchors"][0]["source"], [[2, "int VALUE = 0x10;"]])

    def test_bindings_require_checkout_top(self):
        self.write()
        bare = self.base / "bare"
        subprocess.run(["git", "init", "--bare", "-q", str(bare)], check=True)
        for path in (self.repo / "dir", self.repo / ".git", self.base, bare):
            with self.subTest(path=path):
                proc = self.script("resolve", self.path, "--repo", f"code={path}", "--json")
                self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
                self.assertIn("top level of a checkout", proc.stdout)

    def test_dt_overrides_and_multiple_labels(self):
        lines = ["/ {", " soc {", "  uart: serial@0 {", "  };",
                 "  l1: l2: spi@2000 {};", " };", "};",
                 "&uart { child {}; };", "&{/soc/serial@0} { child {}; };"]
        try:
            uart = resolve.node_range(lines, "uart")
        except resolve.ResolutionError as exc:
            self.fail(f"a label definition must resolve despite overrides: {exc}")
        self.assertEqual(uart, [3, 4])
        for label in ("l1", "l2"):
            try:
                actual = resolve.node_range(lines, label)
            except resolve.ResolutionError as exc:
                self.fail(f"each label in a multiple-label definition must resolve: {exc}")
            self.assertEqual(actual, [5, 5])
        self.assertEqual(resolve.node_range(lines, "/soc/serial@0"), [3, 4])
        try:
            child = resolve.node_range(lines[:8], "child")
        except resolve.ResolutionError as exc:
            self.fail(f"a child defined in an override must resolve: {exc}")
        self.assertEqual(child, [8, 8])
        with self.assertRaises(resolve.ResolutionError):
            resolve.node_range(lines, "child")
        for name in ("/uart", "/uart/child"):
            with self.subTest(name=name), self.assertRaises(resolve.ResolutionError):
                resolve.node_range(lines, name)

    def test_operational_blob_failure_never_rewrites(self):
        self.write()
        original = self.path.read_bytes()
        revision = "a" * 40
        real = resolve.Repository.lines

        def failed(repo, path):
            if repo.commit == revision:
                raise resolve.ResolutionError("git cat-file failed: authentication failed")
            return real(repo, path)

        old = resolve.Repository(self.repo, self.commit)
        new = resolve.Repository(self.repo, self.commit)
        new.commit = revision
        with mock.patch.object(resolve, "Repository", side_effect=[old, new]), mock.patch.object(
            type(old), "lines", failed
        ):
            code, result = cli("drift", revision, self.path, "--repo", f"code={self.repo}", "--rewrite")
        self.assertEqual(code, 1, result)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertIn("authentication failed", str(result))
        self.assertNotIn("stale", str(result["changes"]))

    def test_operational_search_failure_propagates(self):
        repo = resolve.Repository(self.repo, self.commit)
        with mock.patch.object(repo, "entry", side_effect=[
            ("040000", "tree", "a" * 40), ("040000", "tree", "a" * 40),
            resolve.ResolutionError("network failure")
        ]):
            with self.assertRaisesRegex(resolve.ResolutionError, "network failure"):
                drift.compare(repo, repo, dict(path="dir/", search="scope"))

    def test_cumulative_blob_budget_and_cache(self):
        raw = SOURCE.encode() + b"x" * 1000
        (self.repo / "code.c").write_bytes(raw)
        (self.repo / "dir/code.c").write_bytes(raw)
        repo = resolve.Repository(self.repo, self.commit_all())
        repo.limit = len(raw) * 2 - 1
        self.assertEqual(repo.blob("code.c"), raw)
        self.assertEqual(repo.blob("code.c"), raw)
        with mock.patch.object(repo, "run", wraps=repo.run) as run:
            with self.assertRaisesRegex(resolve.LimitExceeded, "cumulative"):
                repo.blob("dir/code.c")
        self.assertFalse(any(call.args[:2] == ("cat-file", "blob") for call in run.call_args_list))
        self.assertNotIn("dir/code.c", repo._blobs)
        real_run = repo.run

        def underestimated(*args):
            if args[:2] == ("cat-file", "-s"):
                return b"0"
            return real_run(*args)

        with mock.patch.object(repo, "run", side_effect=underestimated):
            with self.assertRaisesRegex(resolve.LimitExceeded, "cumulative"):
                repo.blob("dir/code.c")
        self.assertNotIn("dir/code.c", repo._blobs)

    def test_lazy_objects_budget(self):
        repo = resolve.Repository(self.repo, self.commit)
        repo.fetched = True
        repo.limit = 1 << 20
        run = repo.run

        def grow(*args):
            result = run(*args)
            if args[:2] == ("cat-file", "blob"):
                (self.repo / ".git" / "lazy-transfer").write_bytes(b"a" * (repo.limit + 1))
            return result

        with mock.patch.object(repo, "run", side_effect=grow):
            with self.assertRaisesRegex(resolve.LimitExceeded, "fetched objects"):
                repo.blob("code.c")
        self.assertNotIn("code.c", repo._blobs)

    def test_block_commit_headers_and_boundaries(self):
        for style in ("|-", ">-", "|2-", ">2-"):
            for newline in ("\n", "\r\n"):
                for tail in ("", "\nnext: value\n", "\n# tail\n"):
                    source = f"commit: {style} # KEEP\n  {self.commit}" + tail
                    source = source.replace("\n", newline)
                    with self.subTest(style=style, newline=newline, tail=tail):
                        rewritten = drift.rewrite(source, ("commit",), "a" * 40, [], self.commit)
                        self.assertEqual(rewritten, source.replace(self.commit, "a" * 40))
                        self.path.write_text(rewritten)
                        self.assertEqual(specload.load_strict(self.path)["commit"], "a" * 40)

    def test_folded_multiline_refusal_explains_reason(self):
        source = "commit: >- # KEEP\n  " + self.commit[:20] + "\n  " + self.commit[20:] + "\n"
        with self.assertRaisesRegex(resolve.ResolutionError, "folded multi-line"):
            drift.rewrite(source, ("commit",), "a" * 40, [], self.commit)
        source = f"commit: | # KEEP\n  {self.commit}\n"
        with self.assertRaisesRegex(resolve.ResolutionError, "strip its final newline"):
            drift.rewrite(source, ("commit",), "a" * 40, [], self.commit)

    def test_flow_trailing_comma_rewrite(self):
        for tail in (",", ", ", ", # KEEP\n "):
            source = f"commit: '{self.commit}'\na: {{repo: code, path: code.c{tail}}}\n"
            rewritten = drift.rewrite(source, ("commit",), "a" * 40,
                                      [(("a",), "stale", None)], self.commit)
            self.path.write_text(rewritten)
            try:
                loaded = specload.load_strict(self.path)
            except Exception as exc:
                self.fail(f"trailing comma rewrite must load: {exc}")
            self.assertEqual(loaded["a"]["stale"], {"was": self.commit})
            self.assertIn(tail, rewritten)

    def test_spdx_only_first_leading_comment(self):
        sources = [
            "// SPDX-License-Identifier: MIT\n// SPDX-License-Identifier: BSD-2-Clause\nint VALUE;\n",
            SOURCE + 'const char *s = "SPDX-License-Identifier: %s";\n',
            SOURCE + "// SPDX-License-Identifier: BSD-2-Clause\n",
            "/* SPDX-License-Identifier: MIT */\nint VALUE;\n// SPDX-License-Identifier: BSD-2-Clause\n",
        ]
        for source in sources:
            with self.subTest(source=source):
                (self.repo / "code.c").write_text(source)
                self.entry["commit"] = self.commit_all()
                self.anchor["lines"] = [len(source.splitlines()), len(source.splitlines())]
                self.assertEqual(self.run_cli()[0], 0)

    def test_spdx_invalid_suffix_and_line_six(self):
        for source, message in (
            ('const char *s = "SPDX-License-Identifier: MIT";\nint VALUE;\n', "invalid SPDX"),
            ("// header\n" * 5 + "// SPDX-License-Identifier: MIT\nint VALUE;\n", "no SPDX"),
        ):
            with self.subTest(source=source):
                (self.repo / "code.c").write_text(source)
                self.entry["commit"] = self.commit_all()
                self.anchor["lines"] = [len(source.splitlines()), len(source.splitlines())]
                code, result = self.run_cli()
                self.assertEqual(code, 1, result)
                self.assertIn(message, str(result))

    def test_show_escapes_controls_and_cr(self):
        controls = "".join(chr(i) for i in [*range(0x20), 0x7f] if i not in (9, 10, 13))
        (self.repo / "code.c").write_bytes(("// SPDX-License-Identifier: MIT\r\nint VALUE;\t" + controls + "\r\n").encode())
        self.entry["commit"] = self.commit_all()
        self.write()
        proc = self.script("show", self.path, "--repo", f"code={self.repo}")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        for char in controls:
            self.assertNotIn(char, proc.stdout)
            self.assertIn(f"\\x{ord(char):02x}", proc.stdout)
        self.assertIn("int VALUE;\t", proc.stdout)
        code, result = cli("show", self.path, "--repo", f"code={self.repo}")
        self.assertEqual(code, 0, result)
        self.assertFalse(result["anchors"][0]["source"][0][1].endswith("\r"))
        text = resolve.result_object([self.path], [], result["anchors"], result["facts"])[1]["_text"]
        self.assertNotIn("\r", "\n".join(text))

    def test_skill_documents_all_three_commands(self):
        proc = self.script("--skill")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        for command in ("resolve", "show", "drift"):
            self.assertIn("spec.py " + command, proc.stdout)
        for option in ("--repo", "--docs-dir", "--pin", "--rewrite", "--limit-mb"):
            self.assertIn(option, proc.stdout)
