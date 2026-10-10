# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Round-three rewrite verification and preflight regressions."""

import contextlib
import copy
import io
import os
import stat
from unittest import mock

import yaml

from test_resolve import GitFixture, HEADER, SOURCE, cli
import drift
import resolve
import spec
import specload


ANCHOR_AT = ("facts", 0, "support", 0, "anchors", 0)


class ReviewRoundThree(GitFixture):

    def revision(self, changed=False):
        source = SOURCE.replace("0x10", "0x30") if changed else "// inserted\n" + SOURCE
        (self.repo / "code.c").write_text(source)
        tree = (
            "// SPDX-License-Identifier: MIT\n/ {\n  soc {\n    uart: uart@0 {\n"
            "      reg = <0x10>;\n    };\n  };\n};\n"
        )
        (self.repo / "tree.dts").write_text(
            tree.replace("0x10", "0x30") if changed else "// inserted\n" + tree
        )
        return self.commit_all()

    def invoke(self, revision, *extra):
        return cli("drift", revision, self.path, "--rewrite", "--repo",
                   f"code={self.repo}", *extra)

    def anchor_text(self, text, support_class="src"):
        data = copy.deepcopy(self.data)
        del data["facts"]
        lines = text.splitlines(keepends=True)
        anchor = "    - " + lines[0] + "".join("      " + line for line in lines[1:])
        return HEADER + yaml.safe_dump(data, sort_keys=False) + (
            "facts:\n- id: value\n  section: quick-facts\n  title: Value\n"
            "  claim: VALUE is 0x10.\n  support:\n  - class: " + support_class +
            "\n    anchors:\n" + anchor
        )

    def test_explicit_repo_folded_symbol_refused_unchanged(self):
        source = self.anchor_text(
            "? repo\n: code\npath: code.c\nlines: [2, 2]\nsymbol: >-\n  VALUE\n"
        )
        self.path.write_text(source)
        original = self.path.read_bytes()
        revision = self.revision(changed=True)
        with mock.patch.object(drift, "replace_snapshot", wraps=drift.replace_snapshot) as replace:
            code, result = self.invoke(revision)
        self.assertEqual(code, 1, result)
        self.assertIn("differs at $['facts'][0]['support'][0]['anchors'][0]['symbol']", str(result))
        self.assertEqual(self.path.read_bytes(), original)
        replace.assert_not_called()

    def test_only_intended_data_changes_can_land(self):
        self.data["cache"] = "source-cache"
        self.data["triggers"].append("second")
        self.write()
        original = self.path.read_bytes()
        moved, stale = self.revision(), self.revision(changed=True)
        real_rewrite = drift.rewrite

        def anchor(data):
            return data["facts"][0]["support"][0]["anchors"][0]

        def remove_stale(data):
            anchor(data).pop("stale")

        cases = [
            (moved, "commit", lambda d: d["resources"]["repos"][0].update(commit=self.commit)),
            (moved, "lines", lambda d: anchor(d).update(lines=[2, 2])),
            (moved, "lines", lambda d: anchor(d).update(lines=[0, 0])),
            (stale, "stale", remove_stale),
            (stale, "was", lambda d: anchor(d)["stale"].update(was=stale)),
            (moved, "symbol", lambda d: anchor(d).update(symbol="other")),
            (moved, "cache", lambda d: d.pop("cache")),
            (moved, "name", lambda d: d.update(name="Other chip")),
            (moved, "triggers", lambda d: d["triggers"].reverse()),
            (moved, "triggers", lambda d: d["triggers"].append("third")),
            (moved, "triggers", lambda d: d["triggers"].pop()),
        ]
        for revision, path, corrupt in cases:
            def rewrite(*args):
                parsed = specload.load_strict_marked(self.path, real_rewrite(*args).encode()).data
                corrupt(parsed)
                return HEADER + yaml.safe_dump(parsed, sort_keys=False)

            with self.subTest(path=path, revision=revision), mock.patch.object(
                drift, "rewrite", side_effect=rewrite
            ), mock.patch.object(drift, "replace_snapshot", wraps=drift.replace_snapshot) as replace:
                self.path.write_bytes(original)
                code, result = self.invoke(revision)
                self.assertEqual(code, 1, result)
                self.assertIn("differs at", str(result))
                self.assertIn(path, str(result))
                self.assertEqual(self.path.read_bytes(), original)
                replace.assert_not_called()

        self.data.pop("cache")
        self.write()
        original = self.path.read_bytes()

        def extra_key(*args):
            return real_rewrite(*args) + "cache: unexpected\n"

        with mock.patch.object(drift, "rewrite", side_effect=extra_key):
            code, result = self.invoke(moved)
        self.assertEqual(code, 1, result)
        self.assertIn("differs at $['cache']", str(result))
        self.assertEqual(self.path.read_bytes(), original)

    def test_structural_comparison_distinguishes_types_and_keys(self):
        compare = getattr(drift, "first_difference", lambda *_: None)
        for expected, actual, path in [
            ({"x": True}, {"x": 1}, ("x",)),
            ({"x": 1}, {"x": 1.0}, ("x",)),
            ({"x": [1]}, {"x": (1,)}, ("x",)),
            ({"x": {}}, {"x": []}, ("x",)),
            ({"x": None}, {"x": "null"}, ("x",)),
            ({"x": {}}, {"x": {"new": 1}}, ("x", "new")),
            ({"x": {"old": 1}}, {"x": {}}, ("x", "old")),
            ([1, 2], [1, 3], (1,)),
            ([1], [1, 2], (1,)),
            ([1, 2], [1], (1,)),
        ]:
            with self.subTest(expected=expected, actual=actual):
                self.assertEqual(compare(expected, actual), path)
        self.assertIsNone(compare({"x": [1, "a"], "y": None}, {"y": None, "x": [1, "a"]}))

    def test_comment_and_header_byte_checks(self):
        self.write()
        original = self.path.read_bytes() + b"# ordinary comment\n"
        revision = self.revision()
        real_rewrite = drift.rewrite
        for old, new, message in [
            ("# ordinary comment", "# changed comment", "comment bytes"),
            ("# SPDX-License-Identifier: Apache-2.0", "# SPDX-License-Identifier: MIT", "comment bytes"),
            (HEADER, HEADER.replace("\n", "\r\n"), "comment bytes"),
            (HEADER, "\n" + HEADER, "SPDX header bytes"),
        ]:
            with self.subTest(old=old), mock.patch.object(
                drift, "rewrite", side_effect=lambda *args: real_rewrite(*args).replace(old, new)
            ):
                self.path.write_bytes(original)
                code, result = self.invoke(revision)
                self.assertEqual(code, 1, result)
                self.assertIn(message, str(result))
                self.assertEqual(self.path.read_bytes(), original)

    def test_layouts_rewrite_verified_or_refuse_unchanged(self):
        block = "repo: code\npath: code.c\nlines: [2, 2]\nsymbol: VALUE\n"
        layouts = [
            ("block", block),
            ("flow", "{repo: code, path: code.c, lines: [2, 2], symbol: VALUE}\n"),
            ("multiline flow", "{repo: code,\n path: code.c, lines: [2, 2],\n symbol: VALUE}\n"),
            ("trailing comma", "{repo: code,\n path: code.c, lines: [2, 2],\n symbol: VALUE,\n }\n"),
            ("explicit keys", "? repo\n: code\npath: code.c\nlines: [2, 2]\nsymbol: >-\n  VALUE\n"),
            ("explicit symbol", "repo: code\npath: code.c\nlines: [2, 2]\n? symbol\n: VALUE\n"),
            ("crlf", block), ("no final newline", block),
        ]
        for field, value in (("repo", "code"), ("path", "code.c"), ("symbol", "VALUE")):
            for style in ("plain", "single", "double", "|-", "|", "|+", ">-", ">", ">+"):
                scalar = self.scalar(value, style)
                layouts.append((f"{field} {style}", block.replace(f"{field}: {value}\n", f"{field}: {scalar}\n")))
        for field, value in (("comment", "true"), ("lines", "2")):
            for style in ("plain", "single", "double", "|-", "|", "|+", ">-", ">", ">+"):
                scalar = self.scalar(value, style)
                text = block + f"comment: {scalar}\n" if field == "comment" else (
                    block.replace("lines: [2, 2]\n", f"lines:\n  - {scalar.replace(chr(10), chr(10) + '  ')}\n  - 2\n")
                )
                layouts.append((f"{field} {style}", text))
        for style in ("plain", "single", "double", "|-", "|", "|+", ">-", ">", ">+"):
            scalar = self.scalar(self.commit, style).replace("\n", "\n  ")
            layouts.append((f"stale.was {style}", block + f"stale:\n  was: {scalar}\n"))
        revisions = [self.revision(), self.revision(changed=True)]
        for name, text in layouts:
            source = self.anchor_text(text)
            if name == "crlf":
                source = source.replace("\n", "\r\n")
            if name == "no final newline":
                source = source.rstrip("\n")
            for revision in revisions:
                with self.subTest(layout=name, revision=revision):
                    self.assert_verified_or_refused(source, revision)

        for field, value in (("node", "uart"), ("search", "only this node")):
            for style in ("plain", "single", "double", "|-", "|", "|+", ">-", ">", ">+"):
                text = "repo: code\npath: tree.dts\n" + f"{field}: {self.scalar(value, style)}\n"
                self.entry["files"] = [dict(path="tree.dts", license_from="spdx-line")]
                source = self.anchor_text(text, "DT" if field == "node" else "src")
                for revision in ([self.commit, *revisions] if field == "search" else revisions):
                    with self.subTest(field=field, style=style, revision=revision):
                        self.assert_verified_or_refused(source, revision)

    @staticmethod
    def scalar(value, style):
        if style == "plain":
            return value
        if style == "single":
            return "'" + value + "'"
        if style == "double":
            return '"' + value + '"'
        return style + "\n  " + value

    def assert_verified_or_refused(self, source, revision):
        original = source.encode()
        self.path.write_bytes(original)
        before = specload.load_strict(self.path)
        code, result = self.invoke(revision)
        after = self.path.read_bytes()
        if after == original and code == 1:
            self.assertEqual(code, 1, result)
            return
        self.assertIn(code, (0, 1), result)
        self.assertEqual(cli("validate", self.path)[0], 0, result)
        expected = copy.deepcopy(before)
        expected["resources"]["repos"][0]["commit"] = revision
        anchor = expected["facts"][0]["support"][0]["anchors"][0]
        for change in result["changes"]:
            if change["status"] == "moved":
                anchor["lines"] = change["lines"]
            elif change["status"] == "stale":
                anchor["stale"] = {"was": self.commit}
        self.assertEqual(specload.load_strict(self.path), expected, result)
        self.assertEqual(code, int(any(c["status"] == "stale" for c in result["changes"])), result)
        self.assertTrue(after.startswith(HEADER.replace("\n", "\r\n").encode()) if "\r\n" in source else after.startswith(HEADER.encode()))

    def assert_file_refusal(self, message):
        original = self.path.read_bytes()
        mode = stat.S_IMODE(self.path.lstat().st_mode)
        with mock.patch.object(resolve, "git", wraps=resolve.git) as git:
            code, result = self.invoke(self.commit)
        self.assertEqual(code, 1, result)
        self.assertIn(message, str(result))
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(stat.S_IMODE(self.path.lstat().st_mode), mode)
        git.assert_not_called()
        self.assertEqual(list(self.base.glob("spec-rewrite-*")), [])

    def test_symlink_refused_before_source(self):
        self.write()
        target = self.base / "real.spec.yaml"
        self.path.rename(target)
        self.path.symlink_to(target)
        self.assert_file_refusal("symbolic link")
        self.assertTrue(self.path.is_symlink())

    def test_hard_links_refused_before_source(self):
        self.write()
        target = self.base / "twin.spec.yaml"
        os.link(self.path, target)
        self.assert_file_refusal("hard link")
        self.assertEqual(self.path.stat().st_ino, target.stat().st_ino)

    def test_hard_link_created_during_compare_refused(self):
        self.write()
        original = self.path.read_bytes()
        target = self.base / "twin.spec.yaml"
        revision = self.revision()
        compare = drift.compare

        def link(*args):
            os.link(self.path, target)
            return compare(*args)

        with mock.patch.object(drift, "compare", side_effect=link):
            code, result = self.invoke(revision)
        self.assertEqual(code, 1, result)
        self.assertIn("hard link", str(result))
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(self.path.stat().st_ino, target.stat().st_ino)

    def test_read_only_refused_before_source(self):
        self.write()
        self.path.chmod(0o444)
        # Privileged access must not make an explicitly read-only file replaceable.
        with mock.patch.object(os, "access", return_value=True):
            self.assert_file_refusal("not writable")

    def test_user_access_refused_before_source(self):
        self.write()
        with mock.patch.object(os, "access", return_value=False):
            self.assert_file_refusal("not writable")

    def test_setuid_refused_before_source(self):
        self.write()
        self.path.chmod(0o4755)
        self.assert_file_refusal("setuid or setgid")

    def test_setgid_refused_before_source(self):
        self.write()
        self.path.chmod(0o2755)
        self.assert_file_refusal("setuid or setgid")

    def test_other_pin_stale_does_not_block_or_change(self):
        other = copy.deepcopy(self.entry)
        other["name"] = "other"
        self.data["resources"]["repos"].append(other)
        second = dict(copy.deepcopy(self.anchor), repo="other", stale={"was": self.commit})
        self.data["facts"][0]["support"][0]["anchors"].append(second)
        # Other source-independent errors must not be checked either.
        second["lines"] = [9, 2]
        other["files"][0]["path"] = "absent.c"
        self.write()
        revision = self.revision()
        code, result = self.invoke(revision, "--pin", "code")
        self.assertEqual(code, 0, result)
        loaded = specload.load_strict(self.path)
        self.assertEqual(loaded["resources"]["repos"][1], other)
        self.assertEqual(loaded["facts"][0]["support"][0]["anchors"][1], second)
        self.assertEqual(len(result["changes"]), 1)

    def test_unrelated_duplicate_is_file_error_before_source(self):
        duplicate = dict(copy.deepcopy(self.entry), name="dupe")
        self.data["resources"]["repos"].extend([duplicate, copy.deepcopy(duplicate)])
        for cited in (False, True):
            if cited:
                self.data["facts"][0]["support"][0]["anchors"].append(dict(copy.deepcopy(self.anchor), repo="dupe"))
            self.write()
            original = self.path.read_bytes()
            with self.subTest(cited=cited), mock.patch.object(resolve, "git", wraps=resolve.git) as git:
                code, result = self.invoke(self.commit, "--pin", "code")
                self.assertEqual(code, 1, result)
                self.assertIn("duplicate repos entry name: dupe", str(result))
                self.assertNotIn("usage", str(result))
                self.assertEqual(self.path.read_bytes(), original)
                git.assert_not_called()

    def test_preflight_finding_shape_and_fact_prefix(self):
        self.anchor["stale"] = {"was": self.commit}
        self.write()
        for command in ("resolve", "show", "drift"):
            args = (self.commit, self.path) if command == "drift" else (self.path,)
            with self.subTest(command=command), mock.patch.object(resolve, "git") as git:
                code, result = cli(command, *args)
                self.assertEqual(code, 1, result)
                finding = result["findings"][0]
                self.assertEqual(finding.get("level"), "error")
                self.assertTrue(finding["message"].startswith("value: "), finding)
                self.assertEqual(set(finding), {"path", "line", "column", "level", "message"})
                git.assert_not_called()

    def test_validate_usage_escapes_control_characters(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = spec.main(["validate", "bad\x1b[31m.spec.yaml"])
        self.assertEqual(code, 2)
        self.assertNotIn("\x1b", err.getvalue())
        self.assertIn("\\x1b", err.getvalue())
