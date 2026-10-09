# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Network-free source resolution; opt in to the real fetch with RESOLVE_SRC=1."""

import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import resolve
import spec
import yaml

HEADER = "# SPDX-FileCopyrightText: 2026 contributors\n# SPDX-License-Identifier: Apache-2.0\n"
SOURCE = "// SPDX-License-Identifier: MIT\nint VALUE = 0x10;\nint other = 0x20;\n"


def cli(*args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = spec.main([str(a) for a in args] + ["--json"])
    result = json.loads(out.getvalue())
    if code == 100:
        raise AssertionError(f"internal error, not a verdict: {err.getvalue()}")
    return code, result


class GitFixture(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.repo = self.base / "source"
        self.repo.mkdir()
        self.git("init", "-q")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        (self.repo / "code.c").write_text(SOURCE)
        (self.repo / "empty.c").write_text("")
        (self.repo / "dir").mkdir()
        (self.repo / "dir" / "code.c").write_text(SOURCE)
        (self.repo / "tree.dts").write_text(
            "// SPDX-License-Identifier: MIT\n/ {\n  soc {\n    uart: uart@0 {\n      reg = <0x10>;\n    };\n  };\n};\n"
        )
        (self.repo / "link.c").symlink_to("code.c")
        self.commit = self.commit_all()
        self.path = self.base / "chip.spec.yaml"
        self.data = dict(
            format=2,
            kind="chip",
            id="chip",
            name="Chip",
            triggers=["chip"],
            resources={
                "repos": [
                    dict(
                        name="code",
                        url="https://example.invalid/source",
                        commit=self.commit,
                        license="MIT",
                        files=[dict(path="code.c", license_from="spdx-line")],
                    )
                ]
            },
            facts=[
                dict(
                    id="value",
                    section="quick-facts",
                    title="Value",
                    claim="VALUE is 0x10.",
                    support=[
                        dict(
                            **{"class": "src"},
                            anchors=[
                                dict(
                                    repo="code",
                                    path="code.c",
                                    lines=[2, 2],
                                    symbol="VALUE",
                                )
                            ],
                        )
                    ],
                )
            ],
        )

    def git(self, *args):
        return subprocess.run(
            ["git", "-C", str(self.repo), *args],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def commit_all(self):
        self.git("add", "code.c", "empty.c", "dir/code.c", "tree.dts", "link.c")
        self.git("commit", "-qm", "fixture")
        return self.git("rev-parse", "HEAD")

    @property
    def anchor(self):
        return self.data["facts"][0]["support"][0]["anchors"][0]

    @property
    def entry(self):
        return self.data["resources"]["repos"][0]

    def write(self):
        self.path.write_text(HEADER + yaml.safe_dump(self.data, sort_keys=False))

    def run_cli(self, command="resolve", *extra):
        self.write()
        return cli(command, self.path, "--repo", f"code={self.repo}", *extra)

    def assert_bad(self, phrase):
        code, result = self.run_cli()
        self.assertEqual(code, 1, result)
        self.assertTrue(any(phrase in f["message"] for f in result["findings"]), result)
        return result


class ResolveTests(GitFixture):

    def test_resolve_and_show(self):
        code, result = self.run_cli()
        self.assertEqual(
            (code, result["resolved"], result["skipped"]), (0, 1, 0), result
        )
        self.assertEqual(result["anchors"][0]["source"], [[2, "int VALUE = 0x10;"]])
        code, shown = self.run_cli("show")
        self.assertEqual(code, 0, shown)
        self.assertEqual(shown["facts"][0]["claim"], "VALUE is 0x10.")
        self.assertEqual(
            shown["facts"][0]["citations"][0]["source"], result["anchors"][0]["source"]
        )
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = spec.main(["show", str(self.path), "--repo", f"code={self.repo}"])
        self.assertEqual(code, 0)
        self.assertIn("2: int VALUE = 0x10;", out.getvalue())

    def test_pin_not_worktree(self):
        (self.repo / "code.c").write_text("wrong worktree content\n")
        code, result = self.run_cli()
        self.assertEqual((code, result["resolved"]), (0, 1), result)

    def test_line_ranges(self):
        for span in ([0, 1], [3, 2], [4, 4], [1, 99]):
            with self.subTest(span):
                self.anchor["lines"] = span
                self.assertEqual(self.run_cli()[0], 1)
        self.anchor.update(path="empty.c", lines=[1, 1])
        self.entry["files"][0]["path"] = "empty.c"
        self.entry["files"][0]["license_from"] = "notice"
        self.assert_bad("0 lines")

    def test_symbol_near_range_and_boundaries(self):
        for symbol in ("value", "VALU", "ALUE", "missing", "VALUE; touch marker"):
            with self.subTest(symbol):
                self.anchor["symbol"] = symbol
                self.assert_bad("not near")
        (self.repo / "code.c").write_text(SOURCE + "\n" * 201 + "int tail;\n")
        self.entry["commit"] = self.commit_all()
        self.anchor.update(symbol="VALUE", lines=[205, 205])
        self.assert_bad("not near")
        self.anchor["lines"] = [202, 202]
        self.assertEqual(self.run_cli()[0], 0)

    def test_shell_symbols_are_literals(self):
        symbols = [
            "~Foo",
            "operator<<",
            "Foo<T>",
            "$label",
            "struct gic_chip_data",
            "$(touch marker)",
            "`touch marker`",
        ]
        for symbol in symbols:
            with self.subTest(symbol):
                (self.repo / "code.c").write_text(
                    "// SPDX-License-Identifier: MIT\n" + symbol + "\n"
                )
                self.entry["commit"] = self.commit_all()
                self.anchor["symbol"] = symbol
                self.assertEqual(self.run_cli()[0], 0)
        self.assertFalse((self.repo / "marker").exists())

    def test_missing_path_directory_and_symlink(self):
        for path in ("missing.c", "dir", "link.c"):
            with self.subTest(path):
                self.anchor["path"] = path
                self.entry["files"][0]["path"] = path
                self.assertEqual(self.run_cli()[0], 1)

    def test_search_file_and_directory(self):
        self.data["facts"][0]["support"][0]["anchors"] = [
            dict(repo="code", path="dir/", search="no other code; never execute this")
        ]
        self.entry["files"][0].update(path="dir/", license_from="notice")
        code, result = self.run_cli("show")
        self.assertEqual((code, result["resolved"]), (0, 1), result)
        self.assertIn(
            "Search scope",
            "\n".join(
                resolve.result_object(
                    [self.path], [], result["anchors"], result["facts"]
                )[1]["_text"]
            ),
        )
        self.anchor["path"] = "code.c"
        self.entry["files"][0]["path"] = "code.c"
        self.assertEqual(self.run_cli()[0], 0)
        self.anchor["path"] = "dir"
        self.entry["files"][0]["path"] = "dir"
        self.assert_bad("search path kind")
        self.anchor["path"] = "missing/"
        self.entry["files"][0]["path"] = "missing/"
        self.assert_bad("does not exist")

    def test_closed_files_and_repo_names(self):
        self.entry["files"][0]["path"] = "other.c"
        self.assert_bad("closed files")
        self.entry["files"][0]["path"] = "code.c"
        self.anchor["repo"] = "absent"
        self.assert_bad("exactly one")
        self.anchor["repo"] = "code"
        self.data["resources"]["repos"].append(
            dict(copy.deepcopy(self.entry), role="source")
        )
        self.assert_bad("exactly one")

    def test_stale_fails(self):
        self.anchor["stale"] = {"was": self.commit}
        self.assert_bad("stale anchor")

    def test_license_mismatch_and_aliases(self):
        self.entry["license"] = "GPL-2.0-only"
        self.assert_bad("SPDX line")
        (self.repo / "code.c").write_text(SOURCE.replace("MIT", "GPL-2.0"))
        self.entry["commit"] = self.commit_all()
        self.assertEqual(self.run_cli()[0], 0)
        self.entry["license"] = "GPL-2.0-or-later"
        self.assert_bad("differs")
        self.entry["license"] = "GPL-2.0-only WITH Linux-syscall-note"
        self.assert_bad("differs")

    def test_missing_invalid_multiple_spdx(self):
        for source, phrase in [
            (SOURCE.replace("SPDX-License-Identifier:", "License:"), "no SPDX"),
            (SOURCE.replace("MIT", "Wut"), "invalid SPDX"),
            (SOURCE + "// SPDX-License-Identifier: BSD-2-Clause\n", "differs"),
        ]:
            with self.subTest(source):
                (self.repo / "code.c").write_text(source)
                self.entry["commit"] = self.commit_all()
                self.assert_bad(phrase)
        self.entry["files"][0]["license_from"] = "notice"
        self.assert_bad("differs")
        (self.repo / "code.c").write_text("int VALUE = 0x10;\n")
        self.entry["commit"] = self.commit_all()
        self.anchor["lines"] = [1, 1]
        self.assertEqual(self.run_cli()[0], 0)

    def test_license_expression_order_and_grouping(self):
        for source, entry in [
            ("MIT OR BSD-2-Clause", "BSD-2-Clause OR MIT"),
            (
                "MIT AND (BSD-2-Clause AND Apache-2.0)",
                "(Apache-2.0 AND MIT) AND BSD-2-Clause",
            ),
        ]:
            (self.repo / "code.c").write_text(SOURCE.replace("MIT", source))
            self.entry["commit"] = self.commit_all()
            self.entry["license"] = entry
            self.assertEqual(self.run_cli()[0], 0)
        self.entry["license"] = "MIT OR BSD-2-Clause"
        self.assert_bad("differs")

    def test_hex_warning_per_missing_value(self):
        self.data["facts"][0]["claim"] = "0x0010 plus 0x20 plus 0xFF."
        code, result = self.run_cli()
        self.assertEqual(code, 0)
        self.assertTrue(
            any(
                f.get("level") == "warning" and "0x20, 0xff" in f["message"]
                for f in result["findings"]
            ),
            result,
        )
        self.anchor["lines"] = [2, 3]
        self.data["facts"][0]["claim"] = "0x0010 plus 0x20."
        self.assertEqual(self.run_cli()[1]["findings"], [])

    def test_dt_and_rtl(self):
        self.data["facts"][0]["support"][0].update(
            {"class": "rtl", "design": "Widget", "revision": "1", "module": "w"}
        )
        self.assertEqual(self.run_cli()[0], 0)
        self.data["facts"][0]["support"][0]["class"] = "DT"
        for field in ("design", "revision", "module"):
            self.data["facts"][0]["support"][0].pop(field, None)
        self.anchor.update(path="tree.dts", lines=[5, 5], node="/soc/uart@0")
        self.anchor.pop("symbol")
        self.entry["files"][0]["path"] = "tree.dts"
        self.assertEqual(self.run_cli()[0], 0)
        for node in ("uart@0", "uart", "/soc/uart@0"):
            self.anchor["node"] = node
            self.assertEqual(self.run_cli()[0], 0)
        for node in ("uart@", "/bad/uart@0", "//soc/uart@0", "///"):
            self.anchor["node"] = node
            self.assertEqual(self.run_cli()[0], 1)
        self.anchor["node"] = "/soc/uart@0"
        self.anchor["lines"] = [2, 2]
        self.assert_bad("outside the DT node")

    def test_node_only_decompiled_text(self):
        (self.repo / "code.c").write_text((self.repo / "tree.dts").read_text())
        self.entry["commit"] = self.commit_all()
        self.data["facts"][0]["support"][0]["class"] = "DT"
        self.anchor.pop("symbol")
        self.anchor.pop("lines")
        self.anchor["node"] = "/soc/uart@0"
        code, result = self.run_cli()
        self.assertEqual((code, result["resolved"]), (0, 1), result)
        self.assertEqual(result["anchors"][0]["source"][0][0], 4)

    def test_nested_premises_and_conflicts_resolve(self):
        original = copy.deepcopy(self.data["facts"][0]["support"])
        self.data["facts"][0]["support"] = [
            {
                "class": "inference",
                "premises": [dict(states="C", support=original)],
                "derivation": "Follows",
            }
        ]
        self.data["facts"][0]["todo"] = dict(check="hardware", text="Measure it")
        self.data["facts"][0]["conflicts"] = [
            dict(reading="Contrary.", support=copy.deepcopy(original))
        ]
        code, result = self.run_cli()
        self.assertEqual((code, result["resolved"]), (0, 2), result)

    def test_document_hashes(self):
        docs = self.base / "docs"
        docs.mkdir()
        (docs / "manual").write_bytes(b"document bytes")
        self.data["resources"]["documents"] = [
            dict(
                name="manual",
                **{"class": "doc"},
                title="Manual",
                url="https://example.invalid/manual",
                sha256=hashlib.sha256(b"document bytes").hexdigest(),
            )
        ]
        self.assertEqual(self.run_cli("resolve", "--docs-dir", docs)[0], 0)
        (docs / "manual").write_bytes(b"changed")
        code, result = self.run_cli("resolve", "--docs-dir", docs)
        self.assertEqual(code, 1)
        self.assertIn("sha256 mismatch", str(result))
        (docs / "manual").unlink()
        self.assertEqual(self.run_cli("resolve", "--docs-dir", docs)[0], 1)
        (docs / "manual").symlink_to(self.repo / "code.c")
        self.assertEqual(self.run_cli("resolve", "--docs-dir", docs)[0], 1)

    def test_empty_whitespace_separators_aliases(self):
        for value in ("", " ", "---", "---\n---", "a: &a {}\nb: *a\n"):
            with self.subTest(value):
                self.path.write_text(value)
                with mock.patch.object(resolve, "git") as git:
                    self.assertEqual(cli("resolve", self.path)[0], 1)
                    git.assert_not_called()
        for path in (
            "",
            " ",
            "/",
            "//",
            "./code.c",
            "dir/../code.c",
            "dir//code.c",
            ".git/config",
            "-x",
        ):
            self.anchor["path"] = path
            with self.subTest(path), mock.patch.object(resolve, "git") as git:
                self.assertEqual(self.run_cli()[0], 1)
                git.assert_not_called()

    def test_bad_urls_never_reach_git(self):
        for url in (
            "-x",
            "file:///tmp/source",
            "ext::bad",
            "",
            " ",
            "://",
            "HTTPS://example.invalid/a",
            "https:///x",
            "https://x\\y",
        ):
            self.entry["url"] = url
            with self.subTest(url), mock.patch.object(resolve, "git") as git:
                self.assertEqual(self.run_cli()[0], 1)
                with self.assertRaises(resolve.ResolutionError):
                    resolve.fetch(self.entry, self.base / "fetch")
                git.assert_not_called()

    def test_bad_commits_never_reach_git(self):
        for commit in ("", " ", "/", "HEAD", "-x", "A" * 40):
            self.entry["commit"] = commit
            with self.subTest(commit), mock.patch.object(resolve, "git") as git:
                self.assertEqual(self.run_cli()[0], 1)
                with self.assertRaises(resolve.ResolutionError):
                    resolve.fetch(self.entry, self.base / "fetch")
                git.assert_not_called()

    def test_missing_commit_is_failure(self):
        self.entry["commit"] = "a" * 40
        self.assert_bad("git cat-file failed")

    def test_limits_and_definite_failures(self):
        for exc, expected, status in [
            (resolve.LimitExceeded("time limit"), 0, "skipped"),
            (resolve.LimitExceeded("size limit"), 0, "skipped"),
            (resolve.ResolutionError("missing repository"), 1, "failed"),
        ]:
            self.write()
            with mock.patch.object(resolve, "fetch", side_effect=exc):
                code, result = cli("resolve", self.path)
                self.assertEqual(code, expected, result)
                self.assertEqual(result["resolved"], 0)
                self.assertEqual(result["anchors"][0]["status"], status)
                self.assertTrue(result["findings"])

    def test_blob_limit_is_a_skip(self):
        (self.repo / "code.c").write_text(SOURCE + "x" * (2 << 20))
        self.entry["commit"] = self.commit_all()
        code, result = self.run_cli("resolve", "--limit-mb", "1")
        self.assertEqual(
            (code, result["resolved"], result["skipped"]), (0, 0, 1), result
        )

    def test_usage(self):
        self.write()
        for args in [
            ("--repo", ""),
            ("--repo", "="),
            ("--repo", "code= "),
            ("--repo", "other=."),
            ("--repo", "code=.", "--repo", "code=."),
            ("--limit-mb", "0"),
            ("--timeout", "-1"),
            ("--docs-dir", "missing"),
        ]:
            with self.subTest(args):
                self.assertEqual(cli("resolve", self.path, *args)[0], 2)


class FetchTests(unittest.TestCase):

    def test_subprocess_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(
                subprocess, "run", return_value=subprocess.CompletedProcess([], 0)
            ) as run:
                resolve.git(Path(tmp), ["cat-file", "-t", "--", "a" * 40], 1, 20)
                args, kwargs = run.call_args
                self.assertNotIn("shell", kwargs)
                self.assertEqual(args[0][-2:], ["--", "a" * 40])
                self.assertEqual(kwargs["env"]["GIT_ALLOW_PROTOCOL"], "https")
                self.assertIn("protocol.allow=never", args[0])
                self.assertIn("http.followRedirects=false", args[0])

    def test_git_failures_timeout_and_output_limit(self):
        with mock.patch.object(
            subprocess, "run", return_value=subprocess.CompletedProcess([], 128)
        ):
            with self.assertRaises(resolve.ResolutionError) as ctx:
                resolve.git(".", ["fetch"], 1, 10)
            self.assertNotIsInstance(ctx.exception, resolve.LimitExceeded)
        with mock.patch.object(
            subprocess, "run", side_effect=subprocess.TimeoutExpired("git", 1)
        ):
            with self.assertRaises(resolve.LimitExceeded):
                resolve.git(".", ["fetch"], 1, 10)
        with mock.patch.object(subprocess, "run", side_effect=FileNotFoundError()):
            with self.assertRaises(resolve.ResolutionError) as ctx:
                resolve.git(".", ["fetch"], 1, 10)
            self.assertNotIsInstance(ctx.exception, resolve.LimitExceeded)

        def oversized(*args, **kwargs):
            kwargs["stdout"].write(b"x" * 11)
            return subprocess.CompletedProcess([], 0)

        with mock.patch.object(subprocess, "run", side_effect=oversized):
            with self.assertRaises(resolve.LimitExceeded):
                resolve.git(".", ["cat-file"], 1, 10)

    def test_fetch_flags_size_and_sha256(self):
        entry = dict(url="https://example.invalid/repo", commit="a" * 64)
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "fetch"
            with mock.patch.object(
                resolve, "git", return_value=b""
            ) as git, mock.patch.object(resolve, "Repository"):
                resolve.fetch(entry, dest)
                self.assertEqual(
                    git.call_args_list[0].args[1],
                    ["init", "-q", "--object-format=sha256"],
                )
                self.assertEqual(
                    git.call_args_list[1].args[1],
                    [
                        "fetch",
                        "-q",
                        "--depth",
                        "1",
                        "--filter=blob:none",
                        "--",
                        entry["url"],
                        entry["commit"],
                    ],
                )
            (dest / ".git").mkdir()
            (dest / ".git" / "pack").write_bytes(b"x" * 100)
            with mock.patch.object(resolve, "git", return_value=b""), mock.patch.object(
                resolve, "Repository"
            ):
                with self.assertRaises(resolve.LimitExceeded):
                    resolve.fetch(entry, dest, limit=10)

    def test_git_config_environment_removed(self):
        with mock.patch.dict(
            os.environ,
            GIT_CONFIG_COUNT="1",
            GIT_CONFIG_KEY_0="url.file:.insteadOf",
            GIT_CONFIG_VALUE_0="https:",
            GIT_DIR="unrelated",
        ):
            env = resolve.git_env()
        for key in (
            "GIT_CONFIG_COUNT",
            "GIT_CONFIG_KEY_0",
            "GIT_CONFIG_VALUE_0",
            "GIT_DIR",
        ):
            self.assertNotIn(key, env)
        self.assertEqual(env["GIT_CONFIG_GLOBAL"], os.devnull)

    @unittest.skipUnless(
        os.environ.get("RESOLVE_SRC") == "1", "set RESOLVE_SRC=1 for real HTTPS fetch"
    )
    def test_real_fetch_good_and_bad_anchor(self):
        entry = dict(
            url="https://github.com/raspberrypi/tools",
            commit="439b6198a9b340de5998dd14a26a0d9d38a6bcac",
        )
        with tempfile.TemporaryDirectory() as tmp:
            repo = resolve.fetch(entry, Path(tmp) / "repo")
            anchor = dict(path="armstubs/armstub8.S", lines=[53, 57], symbol="OSC_FREQ")
            span, lines = resolve.cited_lines(repo, anchor)
            self.assertEqual(span, [53, 57])
            self.assertTrue(lines, "self-test must actually resolve, never skip")
            with self.assertRaises(resolve.ResolutionError):
                resolve.cited_lines(
                    repo, dict(anchor, symbol="DELIBERATELY_ABSENT_SYMBOL")
                )


class BoundaryTests(GitFixture):

    def test_path_boundary_before_subprocess(self):
        repo = resolve.Repository(self.repo, self.commit)
        for path in (
            "",
            " ",
            "/",
            "//",
            "-x",
            "./code.c",
            "dir/../code.c",
            ".git/config",
        ):
            with self.subTest(path), mock.patch.object(
                repo, "run", return_value=b""
            ) as run:
                with self.assertRaises(resolve.ResolutionError):
                    repo.entry(path)
                if path != " ":
                    run.assert_not_called()

    def test_non_commit_object(self):
        blob = self.git("hash-object", "code.c")
        with self.assertRaises(resolve.ResolutionError) as caught:
            resolve.Repository(self.repo, blob)
        self.assertIn("does not identify a commit", str(caught.exception))

    def test_search_kind_boundary(self):
        repo = resolve.Repository(self.repo, self.commit)
        with self.assertRaises(resolve.ResolutionError) as caught:
            resolve.cited_lines(repo, dict(path="dir", search="no claim"))
        self.assertIn("search path kind", str(caught.exception))

    def test_node_comments_strings_duplicates_and_braces(self):
        self.assertEqual(
            resolve.node_range(["/ {", '/* fake { */ n { p = "}"; };', "};"], "n"),
            [2, 2],
        )
        for text, node in [
            ("/ { n {}; n {}; };", "n"),
            ("} n {};", "n"),
            ("/ { n {};", "n"),
            ("/ { n {}; };", "///"),
        ]:
            with self.subTest(text=text, node=node), self.assertRaises(
                resolve.ResolutionError
            ):
                resolve.node_range(text.splitlines(), node)

    def test_utf8_failure(self):
        (self.repo / "code.c").write_bytes(b"\xff")
        self.entry["commit"] = self.commit_all()
        self.assert_bad("not UTF-8")

    def test_no_final_newline_is_a_real_line(self):
        (self.repo / "code.c").write_text(SOURCE.rstrip("\n"))
        self.entry["commit"] = self.commit_all()
        self.anchor.update(lines=[3, 3], symbol="other")
        self.assertEqual(self.run_cli()[0], 0)

    def test_stale_rejected_even_if_fetch_would_skip(self):
        self.anchor["stale"] = {"was": self.commit}
        self.write()
        with mock.patch.object(
            resolve, "fetch", side_effect=resolve.LimitExceeded("time")
        ) as fetch:
            code, result = cli("resolve", self.path)
            self.assertEqual(code, 1, result)
            fetch.assert_not_called()

    def test_read_limits_and_no_spdx_for_notice(self):
        repo = resolve.Repository(self.repo, self.commit)
        repo.limit = 1
        with mock.patch.object(
            repo, "entry", return_value=("100644", "blob", "a" * 40)
        ), mock.patch.object(repo, "run", return_value=b"2") as run:
            with self.assertRaises(resolve.LimitExceeded):
                repo.blob("code.c")
            self.assertEqual(run.call_count, 1)

    def test_cli_usage_file_and_binding(self):
        self.write()
        for args in [
            ("resolve", self.base / "absent.spec.yaml"),
            ("resolve", self.base),
            ("resolve", self.path, "--repo", "code=absent"),
        ]:
            self.assertEqual(cli(*args)[0], 2)


class MutationRegressions(GitFixture):

    def test_duplicate_repo_without_missing_repo_case(self):
        self.data["resources"]["repos"].append(
            dict(copy.deepcopy(self.entry), role="source")
        )
        self.assert_bad("exactly one")

    def test_symlink_mode_guard(self):
        self.anchor["path"] = "link.c"
        self.entry["files"][0]["path"] = "link.c"
        self.assert_bad("symlinks and submodules")

    def test_directory_blob_guard(self):
        repo = resolve.Repository(self.repo, self.commit)
        with self.assertRaises(resolve.ResolutionError) as caught:
            repo.blob("dir")
        self.assertIn("expected a file", str(caught.exception))

    def test_missing_path_rejection(self):
        repo = resolve.Repository(self.repo, self.commit)
        with self.assertRaises(resolve.ResolutionError):
            repo.entry("absent.c")

    def test_matching_document_symlink_still_refused(self):
        docs = self.base / "docs"
        docs.mkdir()
        (docs / "manual").symlink_to(self.repo / "code.c")
        self.data["resources"]["documents"] = [
            dict(
                name="manual",
                **{"class": "doc"},
                title="Manual",
                url="https://example.invalid/manual",
                sha256=hashlib.sha256(SOURCE.encode()).hexdigest(),
            )
        ]
        code, result = self.run_cli("resolve", "--docs-dir", docs)
        self.assertEqual(code, 1, result)
        self.assertIn("missing regular file", str(result))

    def test_all_inputs_validate_before_source_access(self):
        self.write()
        bad = self.base / "bad.spec.yaml"
        bad.write_text("format: 2\nkind: broken\n")
        with mock.patch.object(
            resolve, "fetch", side_effect=resolve.ResolutionError("fetch called")
        ) as fetch:
            code, _ = cli("resolve", bad, self.path)
            self.assertEqual(code, 1)
            fetch.assert_not_called()


class FailureClassificationTests(GitFixture):

    def test_timeout_is_explicit_skip(self):
        self.write()
        with mock.patch.object(
            subprocess, "run", side_effect=subprocess.TimeoutExpired("git", 1)
        ):
            code, result = cli("resolve", self.path)
        self.assertEqual(
            (code, result["resolved"], result["skipped"]), (0, 0, 1), result
        )

    def test_missing_executable_is_definite_failure(self):
        self.write()
        with mock.patch.object(
            subprocess, "run", side_effect=FileNotFoundError("missing git")
        ):
            code, result = cli("resolve", self.path)
        self.assertEqual(
            (code, result["resolved"], result["skipped"]), (1, 0, 0), result
        )


class LocalFetchIntegrationTests(GitFixture):

    def test_actual_git_fetch_good_missing_commit_and_missing_repository(self):
        real_git = resolve.git
        remote = self.repo

        def local_transport(directory, args, timeout, limit):
            if args[0] != "fetch":
                return real_git(directory, args, timeout, limit)
            command = [
                "git",
                "-c",
                "protocol.file.allow=always",
                "-C",
                str(directory),
                *args[:-2],
                str(remote),
                args[-1],
            ]
            proc = subprocess.run(
                command, capture_output=True, timeout=timeout, check=False
            )
            if proc.returncode:
                raise resolve.ResolutionError(
                    "git fetch failed: " + proc.stderr.decode()
                )
            return proc.stdout

        self.write()
        with mock.patch.object(resolve, "git", side_effect=local_transport):
            code, result = cli("resolve", self.path)
        self.assertEqual(
            (code, result["resolved"], result["skipped"]), (0, 1, 0), result
        )
        for missing in ("commit", "repository"):
            with self.subTest(missing):
                self.entry["commit"] = "f" * 40 if missing == "commit" else self.commit
                remote = self.repo if missing == "commit" else self.base / "absent"
                self.write()
                with mock.patch.object(resolve, "git", side_effect=local_transport):
                    code, result = cli("resolve", self.path)
                self.assertEqual(
                    (code, result["resolved"], result["skipped"]), (1, 0, 0), result
                )
                self.assertIn("git fetch failed", str(result))


if __name__ == "__main__":
    unittest.main()
