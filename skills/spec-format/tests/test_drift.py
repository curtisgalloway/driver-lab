# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Pin movement, conservative stale detection and byte-preserving YAML patches."""

import copy
from pathlib import Path
import sys
from unittest import mock
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import drift
import resolve
import specload
from test_resolve import GitFixture, HEADER, SOURCE, cli


class DriftTests(GitFixture):

    def move(self, source):
        (self.repo / "code.c").write_text(source)
        return self.commit_all()

    def drift_cli(self, revision, *extra):
        return cli("drift", revision, self.path, "--repo", f"code={self.repo}", *extra)

    def test_moved_lines_comments_header_and_crlf(self):
        self.write()
        original = (
            self.path.read_bytes()
            .replace(b"commit:", b"commit:")
            .replace(b"      - 2\n", b"      - 2 # range endpoint\n")
        )
        original = original.replace(b"\n", b"\r\n")
        self.path.write_bytes(original)
        revision = self.move("// inserted\n" + SOURCE)
        code, result = self.drift_cli(revision)
        self.assertEqual(code, 0, result)
        self.assertEqual(result["changes"][0]["status"], "moved")
        self.assertEqual(self.path.read_bytes(), original)
        code, result = self.drift_cli(revision, "--rewrite")
        self.assertEqual(code, 0, result)
        rewritten = self.path.read_bytes()
        expected = original.replace(self.commit.encode(), revision.encode()).replace(
            b"- 2 # range endpoint", b"- 3 # range endpoint"
        )
        self.assertEqual(rewritten, expected)
        self.assertTrue(rewritten.startswith(HEADER.replace("\n", "\r\n").encode()))
        self.assertEqual(cli("validate", self.path)[0], 0)
        self.assertEqual(cli("resolve", self.path, "--repo", f"code={self.repo}")[0], 0)

    def test_changed_anchor_stale_and_still_schema_valid(self):
        self.write()
        revision = self.move(SOURCE.replace("0x10", "0x30"))
        code, result = self.drift_cli(revision, "--rewrite")
        self.assertEqual(code, 1, result)
        self.assertEqual(result["changes"][0]["status"], "stale")
        data = specload.load_strict(self.path)
        self.assertEqual(data["resources"]["repos"][0]["commit"], revision)
        self.assertEqual(
            data["facts"][0]["support"][0]["anchors"][0]["stale"], {"was": self.commit}
        )
        self.assertEqual(cli("validate", self.path)[0], 0)
        self.assertEqual(cli("resolve", self.path, "--repo", f"code={self.repo}")[0], 1)
        self.assertEqual(self.path.read_bytes()[: len(HEADER)], HEADER.encode())

    def test_flow_rewrite_preserves_every_other_byte(self):
        source = (
            HEADER
            + "commit: '"
            + self.commit
            + "' # pin\nanchors: [{repo: code, lines: [2, 2], symbol: VALUE}] # keep\n"
        )
        revision = "a" * 40
        out = drift.rewrite(
            source,
            ("commit",),
            revision,
            [(("anchors", 0), "stale", None)],
            self.commit,
        )
        expected = source.replace(self.commit, revision).replace(
            "symbol: VALUE}", "symbol: VALUE, stale: {was: '" + self.commit + "'}}"
        )
        self.assertEqual(out, expected)
        moved = drift.rewrite(
            source,
            ("commit",),
            revision,
            [(("anchors", 0), "moved", [5, 5])],
            self.commit,
        )
        self.assertEqual(
            moved, source.replace(self.commit, revision).replace("[2, 2]", "[5, 5]")
        )

    def test_block_no_final_newline_and_trailing_comments(self):
        for tail in ("", "\n", "\n# final comment\n", "\nnext: value\n"):
            source = (
                HEADER
                + 'commit: "'
                + self.commit
                + '"\na:\n  repo: code\n  lines: [2, 2] # endpoint'
                + tail
            )
            out = drift.rewrite(
                source, ("commit",), "a" * 40, [(("a",), "stale", None)], self.commit
            )
            self.assertIn("  lines: [2, 2] # endpoint", out)
            self.assertIn("  stale: {was: '" + self.commit + "'}", out)
            self.path.write_text(out)
            self.assertEqual(
                specload.load_strict(self.path)["a"]["stale"], {"was": self.commit}
            )

    def test_ambiguous_movement_is_stale(self):
        self.write()
        revision = self.move(
            "// SPDX-License-Identifier: MIT\n\nint VALUE = 0x10;\nint VALUE = 0x10;\n"
        )
        code, result = self.drift_cli(revision, "--rewrite")
        self.assertEqual(code, 1, result)
        self.assertEqual(result["changes"][0]["status"], "stale")

    def test_same_range_and_other_file_changes(self):
        self.write()
        revision = self.move(SOURCE + "// new tail\n")
        code, result = self.drift_cli(revision, "--rewrite")
        self.assertEqual(code, 0, result)
        self.assertEqual(result["changes"][0]["status"], "same")
        self.assertNotIn("stale:", self.path.read_text())
        self.assertEqual(
            specload.load_strict(self.path)["resources"]["repos"][0]["commit"], revision
        )

    def test_missing_file_becomes_stale(self):
        self.write()
        self.git("rm", "code.c")
        self.git("commit", "-qm", "removed source")
        revision = self.git("rev-parse", "HEAD")
        code, result = self.drift_cli(revision, "--rewrite")
        self.assertEqual(code, 1, result)
        self.assertEqual(result["changes"][0]["status"], "stale")
        self.assertIn("stale:", self.path.read_text())

    def test_existing_stale_and_invalid_old_ranges_never_rewrite(self):
        revision = self.move("// inserted\n" + SOURCE)
        for anchor in (
            dict(self.anchor, stale={"was": self.commit}),
            dict(self.anchor, lines=[9, 9]),
        ):
            self.data["facts"][0]["support"][0]["anchors"][0] = anchor
            self.write()
            original = self.path.read_bytes()
            self.assertEqual(self.drift_cli(revision, "--rewrite")[0], 1)
            self.assertEqual(self.path.read_bytes(), original)

    def test_search_changed_blocks_whole_rewrite(self):
        self.data["facts"][0]["support"][0]["anchors"].append(
            dict(repo="code", path="code.c", search="only this definition")
        )
        self.write()
        original = self.path.read_bytes()
        revision = self.move("// inserted\n" + SOURCE)
        code, result = self.drift_cli(revision, "--rewrite")
        self.assertEqual(code, 1, result)
        self.assertIn("search scope changed", str(result))
        self.assertEqual(self.path.read_bytes(), original)

    def test_search_unchanged(self):
        self.data["facts"][0]["support"][0]["anchors"][0] = dict(
            repo="code", path="dir/", search="only this file"
        )
        self.entry["files"][0].update(path="dir/", license_from="notice")
        self.write()
        revision = self.move("// inserted\n" + SOURCE)
        self.assertEqual(self.drift_cli(revision, "--rewrite")[0], 0)
        self.assertEqual(cli("validate", self.path)[0], 0)

    def test_several_repos_only_selected_pin_changes(self):
        second = copy.deepcopy(self.entry)
        second["name"] = "second"
        self.data["resources"]["repos"].append(second)
        second_anchor = dict(copy.deepcopy(self.anchor), repo="second")
        self.data["facts"][0]["support"][0]["anchors"].append(second_anchor)
        self.write()
        revision = self.move("// inserted\n" + SOURCE)
        self.assertEqual(self.drift_cli(revision)[0], 2)
        code, result = self.drift_cli(revision, "--rewrite", "--pin", "code")
        self.assertEqual(code, 0, result)
        data = specload.load_strict(self.path)
        self.assertEqual(data["resources"]["repos"][1]["commit"], self.commit)
        self.assertEqual(data["facts"][0]["support"][0]["anchors"][1]["lines"], [2, 2])

    def test_fetch_failure_and_limits_never_rewrite(self):
        self.write()
        original = self.path.read_bytes()
        for exc in (
            resolve.ResolutionError("not found"),
            resolve.LimitExceeded("time limit"),
        ):
            with mock.patch.object(resolve, "fetch", side_effect=exc):
                code, result = cli("drift", "a" * 40, self.path, "--rewrite")
                self.assertEqual(code, 1, result)
                self.assertEqual(self.path.read_bytes(), original)

    def test_invalid_revisions_never_reach_git(self):
        self.write()
        for rev in ("", " ", "/", "---", "HEAD", "A" * 40):
            with self.subTest(rev), mock.patch.object(resolve, "git") as git:
                self.assertEqual(self.drift_cli(rev)[0], 2)
                git.assert_not_called()


class DriftBoundaryTests(GitFixture):

    def test_stale_fails_check(self):
        self.anchor["stale"] = {"was": self.commit}
        root = self.base / "root"
        root.mkdir()
        (root / "board-specs.yaml").write_text(
            HEADER
            + "format: 2\nname: test\nlayer: public\nlicense: MIT\naccepts: [MIT]\n"
        )
        self.path = root / "chip.spec.yaml"
        self.write()
        code, result = cli("check", root)
        self.assertEqual(code, 1, result)
        self.assertIn("stale anchor", str(result))

    def test_rewrite_validation_refusal_keeps_original(self):
        self.write()
        original = self.path.read_bytes()
        with mock.patch.object(drift, "rewrite", return_value="format: broken\n"):
            code, result = cli(
                "drift",
                self.commit,
                self.path,
                "--repo",
                f"code={self.repo}",
                "--rewrite",
            )
        self.assertEqual(code, 1, result)
        self.assertIn("failed validation", str(result))
        self.assertEqual(self.path.read_bytes(), original)

    def test_concurrent_edit_keeps_editor_bytes(self):
        self.write()
        original = self.path.read_bytes()
        real = drift.compare

        def edit(*args):
            self.path.write_bytes(original + b"\n# concurrent edit\n")
            return real(*args)

        with mock.patch.object(drift, "compare", side_effect=edit):
            code, result = cli(
                "drift",
                self.commit,
                self.path,
                "--repo",
                f"code={self.repo}",
                "--rewrite",
            )
        self.assertEqual(code, 1, result)
        self.assertIn("spec changed", str(result))
        self.assertEqual(self.path.read_bytes(), original + b"\n# concurrent edit\n")

    def test_multiple_inputs_and_duplicate_entry(self):
        self.write()
        self.assertEqual(cli("drift", self.commit, self.path, self.path)[0], 2)
        self.data["resources"]["repos"].append(
            dict(copy.deepcopy(self.entry), role="source")
        )
        self.write()
        self.assertEqual(cli("drift", self.commit, self.path)[0], 2)

    def test_unchanged_citation_new_license_stales(self):
        self.write()
        (self.repo / "code.c").write_text(SOURCE.replace("MIT", "BSD-2-Clause"))
        revision = self.commit_all()
        code, result = cli(
            "drift", revision, self.path, "--repo", f"code={self.repo}", "--rewrite"
        )
        self.assertEqual(code, 1, result)
        self.assertEqual(result["changes"][0]["status"], "stale")

    def test_all_digit_commit_quoted(self):
        out = drift.rewrite(
            "commit: " + self.commit + "\n", ("commit",), "1" * 40, [], self.commit
        )
        self.path.write_text(out)
        self.assertEqual(specload.load_strict(self.path)["commit"], "1" * 40)

    def test_node_only_drift_and_limits(self):
        (self.repo / "code.c").write_text((self.repo / "tree.dts").read_text())
        old_commit = self.commit_all()
        old = resolve.Repository(self.repo, old_commit)
        (self.repo / "code.c").write_text(
            (self.repo / "tree.dts").read_text().replace("0x10", "0x20")
        )
        new = resolve.Repository(self.repo, self.commit_all())
        anchor = dict(path="code.c", node="/soc/uart@0")
        self.assertEqual(drift.compare(old, new, anchor)[0], "stale")
        self.assertEqual(drift.compare(old, old, anchor)[0], "same")
        with mock.patch.object(new, "lines", side_effect=resolve.LimitExceeded("size")):
            with self.assertRaises(resolve.LimitExceeded):
                drift.compare(old, new, anchor)
        with mock.patch.object(new, "entry", side_effect=resolve.LimitExceeded("size")):
            with self.assertRaises(resolve.LimitExceeded):
                drift.compare(old, new, dict(path="dir/", search="scope"))


class DriftMutationRegressions(GitFixture):

    def test_unknown_pin_rejected_before_entry_selection(self):
        self.write()
        code, result = cli("drift", self.commit, self.path, "--pin", "absent")
        self.assertEqual(code, 2, result)
        self.assertIn("select one cited repos entry", str(result))


class DriftValidationBarrierTests(GitFixture):

    def test_bad_root_prevents_rewrite_of_valid_file(self):
        root = self.base / "context"
        root.mkdir()
        (root / "board-specs.yaml").write_text("format: 2\n")
        self.write()
        original = self.path.read_bytes()
        (self.repo / "code.c").write_text("// inserted\n" + SOURCE)
        revision = self.commit_all()
        with mock.patch.object(
            resolve, "Repository", wraps=resolve.Repository
        ) as repository:
            code, result = cli(
                "drift",
                revision,
                self.path,
                "--repo",
                f"code={self.repo}",
                "--root",
                root,
                "--rewrite",
            )
            repository.assert_not_called()
        self.assertEqual(code, 1, result)
        self.assertEqual(self.path.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
