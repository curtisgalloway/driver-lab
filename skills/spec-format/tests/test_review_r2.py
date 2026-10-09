# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Round-two regressions, each failing by assertion on the a77ab0d export."""

import contextlib
import copy
import errno
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from unittest import mock

from test_resolve import GitFixture, SOURCE, cli
import drift
import resolve
import spec
import speccheck
import specload


DTS = (
    "// SPDX-License-Identifier: MIT\n/dts-v1/;\n/ {\n  soc {\n"
    "    uart0: serial@1000 {\n      reg = <0x1000 0x100>;\n    };\n"
    "    i2c1: i2c@3000 {\n      reg = <0x3000 0x100>;\n    };\n"
    "    old: gone@4000 {\n      reg = <0x4000 0x100>;\n    };\n  };\n};\n"
    "&i2c1 {\n  pmic: pmic@32 {\n    reg = <0x32>;\n    regulators {\n"
    "      vdd: buck1 {\n      };\n    };\n  };\n};\n"
    'extra: &uart0 {\n  status = "okay";\n};\n'
    "&{/soc/serial@1000} {\n  serial@1000 {\n  };\n};\n"
    "/delete-node/ &old;\n/ {\n  soc {\n    /delete-node/ gone@4000;\n  };\n};\n"
)


class ReviewRoundTwo(GitFixture):

    def invoke_drift(self, revision, *extra):
        return cli("drift", revision, self.path, "--repo", f"code={self.repo}",
                   "--rewrite", *extra)

    def move(self):
        (self.repo / "code.c").write_text("// inserted\n" + SOURCE)
        return self.commit_all()

    def test_drift_uses_validated_snapshot(self):
        self.anchor["path"] = "code.c"
        second = dict(repo="code", path="dir/code.c", lines=[2, 2], symbol="VALUE")
        self.data["facts"][0]["support"][0]["anchors"].append(second)
        self.entry["files"].append(dict(path="dir/code.c", license_from="spdx-line"))
        self.write()
        original = self.path.read_bytes()
        edited = copy.deepcopy(self.data)
        edited["facts"][0]["support"][0]["anchors"].reverse()
        import yaml

        editor_bytes = yaml.safe_dump(edited, sort_keys=False).encode()
        revision = self.move()
        real_read = Path.read_bytes
        reads = []

        def read(path):
            value = real_read(path)
            if path == self.path:
                reads.append(value)
                if len(reads) == 1:
                    self.path.write_bytes(editor_bytes)
            return value

        with mock.patch.object(Path, "read_bytes", read):
            code, result = self.invoke_drift(revision)
        self.assertEqual(code, 1, result)
        self.assertIn("spec changed during drift", str(result))
        self.assertEqual(self.path.read_bytes(), editor_bytes)
        self.assertEqual(reads, [original, editor_bytes])

    def test_partial_write_retains_original(self):
        self.write()
        original = self.path.read_bytes()
        revision = self.move()
        real_open, real_fdopen = Path.open, os.fdopen

        class Partial:
            def __init__(self, stream):
                self.stream = stream

            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.stream.close()

            def __getattr__(self, name):
                return getattr(self.stream, name)

            def write(self, raw):
                self.stream.write(raw[:32])
                self.stream.flush()
                raise OSError(errno.ENOSPC, "injected partial write")

        def open_path(path, mode="r", *args, **kwargs):
            stream = real_open(path, mode, *args, **kwargs)
            return Partial(stream) if path == self.path and mode == "wb" else stream

        with mock.patch.object(Path, "open", open_path), mock.patch.object(
            os, "fdopen", side_effect=lambda *a, **k: Partial(real_fdopen(*a, **k))
        ):
            code, result = self.invoke_drift(revision)
        self.assertEqual(code, 1, result)
        self.assertIn("injected partial write", str(result))
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list(self.base.glob("spec-rewrite-*")), [])

    def test_atomic_same_directory_exclusive_mode_and_fsync(self):
        self.write()
        self.path.chmod(0o640)
        original = self.path.read_bytes()
        revision = self.move()
        real_replace, real_open = os.replace, os.open
        replacements, creates = [], []

        def open_file(path, flags, *args, **kwargs):
            if str(path).startswith(str(self.base / "spec-rewrite-")):
                creates.append((flags, args[0]))
            return real_open(path, flags, *args, **kwargs)

        def replace(source, target):
            replacements.append(dict(
                parent=Path(source).parent, target=Path(target),
                mode=stat.S_IMODE(Path(source).stat().st_mode),
                original=self.path.read_bytes(),
                commit=specload.load_strict(source)["resources"]["repos"][0]["commit"],
                syncs=sync.call_count,
            ))
            return real_replace(source, target)

        mask = os.umask(0o077)
        try:
            with mock.patch.object(os, "replace", replace), mock.patch.object(os, "open", open_file), mock.patch.object(
                os, "fsync", wraps=os.fsync
            ) as sync:
                code, result = self.invoke_drift(revision)
        finally:
            os.umask(mask)
        self.assertEqual(code, 0, result)
        self.assertEqual(len(replacements), 1)
        self.assertEqual(replacements[0], dict(parent=self.path.parent, target=self.path,
                                             mode=0o640, original=original,
                                             commit=revision, syncs=1))
        self.assertEqual(len(creates), 1)
        self.assertTrue(creates[0][0] & os.O_EXCL)
        self.assertEqual(creates[0][1], 0o640)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o640)
        self.assertEqual(list(self.base.glob("spec-rewrite-*")), [])

    def test_fsync_and_replace_errors_retain_original(self):
        revision = self.move()
        for operation in ("fsync", "replace"):
            with self.subTest(operation=operation):
                self.write()
                original = self.path.read_bytes()
                with mock.patch.object(os, operation, side_effect=OSError("injected " + operation)):
                    code, result = self.invoke_drift(revision)
                self.assertEqual(code, 1, result)
                self.assertIn("injected " + operation, str(result))
                self.assertEqual(self.path.read_bytes(), original)
                self.assertEqual(list(self.base.glob("spec-rewrite-*")), [])

    def test_closed_files_errors_precede_fetch(self):
        self.entry.pop("files")
        self.write()
        with mock.patch.object(resolve, "fetch", side_effect=resolve.LimitExceeded("timeout")) as fetch:
            for command in ("resolve", "show", "drift"):
                with self.subTest(command=command):
                    lead = (command, self.commit) if command == "drift" else (command,)
                    code, result = cli(*lead, self.path)
                    self.assertEqual(code, 1, result)
                    self.assertIn("closed files", str(result))
                    self.assertEqual(result["skipped"], 0)
            fetch.assert_not_called()

    def test_line_order_errors_precede_fetch(self):
        self.anchor["lines"] = [3, 2]
        self.write()
        with mock.patch.object(resolve, "fetch", side_effect=resolve.LimitExceeded("size limit")) as fetch:
            code, result = cli("resolve", self.path)
        self.assertEqual(code, 1, result)
        self.assertIn("ordered", str(result))
        self.assertEqual(result["skipped"], 0)
        fetch.assert_not_called()

    def test_all_spec_only_errors_precede_any_source(self):
        self.write()
        good = self.base / "good.spec.yaml"
        good.write_bytes(self.path.read_bytes())
        self.entry["files"] = [dict(path="empty.c", license_from="notice")]
        self.write()
        with mock.patch.object(resolve, "fetch", side_effect=resolve.LimitExceeded("timeout")) as fetch:
            code, result = cli("resolve", good, self.path)
        self.assertEqual(code, 1, result)
        fetch.assert_not_called()

    def test_entry_license_errors_precede_fetch(self):
        self.entry["license"] = "not-a-real-license"
        self.write()
        with mock.patch.object(resolve, "fetch", side_effect=resolve.LimitExceeded("timeout")) as fetch:
            code, result = cli("resolve", self.path)
        self.assertEqual(code, 1, result)
        self.assertIn("invalid SPDX expression", str(result))
        self.assertEqual(result["skipped"], 0)
        fetch.assert_not_called()

    def test_spdx_five_lines_all_syntaxes_and_modes(self):
        templates = [
            "// SPDX-License-Identifier: {license}\n",
            "/*\n * SPDX-License-Identifier: {license}\n */\n",
            "# SPDX-License-Identifier: {license}\n",
            "#!/bin/sh\n# SPDX-License-Identifier: {license}\n",
            ".. SPDX-License-Identifier: {license}\n",
            "-- SPDX-License-Identifier: {license}\n",
            "\ufeff// SPDX-License-Identifier: {license}\n",
            "int before;\n/*\n * SPDX-License-Identifier: {license}\n */\n",
        ]
        for template in templates:
            for mode in ("spdx-line", "notice", "license-file"):
                for license, expected in (("MIT", 0), ("BSD-2-Clause", 1)):
                    with self.subTest(template=template, mode=mode, license=license):
                        source = template.format(license=license) + "int VALUE;\n"
                        (self.repo / "code.c").write_text(source)
                        self.git("add", "code.c")
                        self.git("commit", "-qm", "fixture", "--allow-empty")
                        self.entry["commit"] = self.git("rev-parse", "HEAD")
                        self.entry["files"][0]["license_from"] = mode
                        last = source.count("\n")
                        self.anchor["lines"] = [last, last]
                        code, result = self.run_cli()
                        self.assertEqual(code, expected, result)
                        if expected:
                            self.assertIn("differs", str(result))
        for mode, expected in (("spdx-line", 1), ("notice", 0), ("license-file", 0)):
            source = "// header\n" * 5 + "// SPDX-License-Identifier: BSD-2-Clause\nint VALUE;\n"
            (self.repo / "code.c").write_text(source)
            self.git("add", "code.c")
            self.git("commit", "-qm", "fixture", "--allow-empty")
            self.entry["commit"] = self.git("rev-parse", "HEAD")
            self.entry["files"][0]["license_from"] = mode
            self.anchor["lines"] = [7, 7]
            code, result = self.run_cli()
            self.assertEqual(code, expected, result)

    def test_spdx_suffix_and_first_tag_rules(self):
        cases = [
            ('#define LIC "SPDX-License-Identifier: MIT"\n', 0),
            ("int before; // SPDX-License-Identifier: MIT\n", 0),
            ("<!-- SPDX-License-Identifier: MIT -->   \n", 0),
            ("/* SPDX-License-Identifier: MIT */   \n", 0),
            ("-- SPDX-License-Identifier: MIT\n// SPDX-License-Identifier: BSD-2-Clause\n", 0),
            ("/* SPDX-License-Identifier: MIT */ int a;\n", 1),
            ('const char *s = "SPDX-License-Identifier: MIT";\n', 1),
        ]
        for head, expected in cases:
            with self.subTest(head=head):
                source = head + "int VALUE;\n"
                (self.repo / "code.c").write_text(source)
                self.entry["commit"] = self.commit_all()
                last = source.count("\n")
                self.anchor["lines"] = [last, last]
                code, result = self.run_cli()
                self.assertEqual(code, expected, result)

    def test_parent_directory_replaced_by_file_is_stale(self):
        self.anchor["path"] = "dir/code.c"
        self.entry["files"][0]["path"] = "dir/code.c"
        self.write()
        (self.repo / "dir" / "code.c").unlink()
        (self.repo / "dir").rmdir()
        (self.repo / "dir").write_text("directory became a file\n")
        self.git("add", "--all", "dir")
        self.git("commit", "-qm", "fixture")
        revision = self.git("rev-parse", "HEAD")
        code, result = self.invoke_drift(revision)
        self.assertEqual(code, 1, result)
        self.assertEqual(len(result["changes"]), 1, result)
        self.assertEqual(result["changes"][0]["status"], "stale")
        loaded = specload.load_strict(self.path)
        self.assertEqual(loaded["resources"]["repos"][0]["commit"], revision)
        self.assertEqual(loaded["facts"][0]["support"][0]["anchors"][0]["stale"], {"was": self.commit})

    def test_missing_spdx_parser_is_precondition(self):
        self.write()
        for command in ("resolve", "show", "drift"):
            with self.subTest(command=command):
                out, err = io.StringIO(), io.StringIO()
                lead = [command, self.commit] if command == "drift" else [command]
                with mock.patch.object(speccheck, "SPDX_PY", self.base / "absent.py"), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    code = spec.main([*lead, str(self.path), "--repo", f"code={self.repo}", "--json"])
                self.assertEqual(code, 3, out.getvalue() + err.getvalue())
                self.assertEqual(json.loads(out.getvalue())["error"], "precondition")
                self.assertNotIn("Traceback", err.getvalue())
        with mock.patch.object(speccheck, "SPDX_PY", self.base / "absent.py"), mock.patch.object(
            resolve, "fetch", side_effect=resolve.LimitExceeded("timeout")
        ) as fetch:
            code, result = cli("resolve", self.path)
        self.assertEqual(code, 3, result)
        fetch.assert_not_called()

    def test_override_definitions_and_children_a03(self):
        lines = DTS.splitlines()
        for name, span in (("pmic", [17, 23]), ("pmic@32", [17, 23]),
                           ("vdd", [20, 21]), ("buck1", [20, 21]), ("regulators", [19, 22])):
            with self.subTest(name=name):
                try:
                    actual = resolve.node_range(lines, name)
                except resolve.ResolutionError as exc:
                    self.fail(f"definition inside override must resolve: {exc}")
                self.assertEqual(actual, span)
        self.assertEqual(resolve.node_range(lines, "uart0"), [5, 7])
        self.assertEqual(resolve.node_range(lines, "/soc/serial@1000"), [5, 7])
        for name in ("extra", "serial@1000", "soc", "/soc/i2c@3000/pmic@32",
                     "/&i2c1/pmic@32", "/&i2c1/pmic@32/regulators/buck1"):
            with self.subTest(name=name), self.assertRaises(resolve.ContentError):
                resolve.node_range(lines, name)
        self.assertEqual(resolve.node_range(lines, "old"), [11, 13])

    def test_display_escapes_every_unicode_class_and_invalid_byte(self):
        for char, escaped in (("\x00", "\\x00"), ("\x7f", "\\x7f"),
                              ("\x9b", "\\x9b"), ("\u202e", "\\u202e"),
                              ("\u2028", "\\u2028"), ("\u2029", "\\u2029"),
                              ("\ue000", "\\ue000"), ("\ud800", "\\ud800"),
                              ("\u0378", "\\u0378"), ("\U000f0000", "\\uf0000"),
                              ("\r", "\\x0d"), ("\n", "\\x0a")):
            with self.subTest(char=repr(char)):
                self.assertEqual(resolve.display_line(char), escaped)
        try:
            displayed = resolve.display_line(b"ok\xff\xfe\x9b")
        except (TypeError, AttributeError) as exc:
            self.fail(f"invalid source bytes must display as escapes: {exc}")
        self.assertEqual(displayed, "ok\\xff\\xfe\\x9b")
        self.assertEqual(resolve.display_line("ok\t café"), "ok\t café")

    def test_show_source_and_spec_text_escape_without_changing_json(self):
        unsafe = "\x9b\u202e\u2028\u2029\ue000\u0378"
        (self.repo / "code.c").write_text(SOURCE.replace("0x10;", "0x10; " + unsafe))
        self.entry["commit"] = self.commit_all()
        citation = dict(repo="code", path="code.c", status="resolved", search="scope " + unsafe)
        fact = dict(id="value", claim="VALUE " + unsafe, citations=[citation])
        code, result = resolve.result_object([self.path], [], [citation], [fact])
        self.assertEqual(code, 0, result)
        text = "".join(result["_text"])
        for char in unsafe:
            self.assertNotIn(char, text)
            self.assertIn(resolve.display_line(char), text)
        self.assertEqual(result["facts"][0]["claim"], "VALUE " + unsafe)
        self.assertEqual(result["anchors"][0]["search"], "scope " + unsafe)
        self.write()
        code, result = cli("show", self.path, "--repo", f"code={self.repo}")
        self.assertEqual(code, 0, result)
        self.assertIn(unsafe, result["anchors"][0]["source"][0][1])
        proc = subprocess.run([sys.executable, str(spec.HERE / "spec.py"), "show", str(self.path),
                               "--repo", f"code={self.repo}"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        for char in unsafe:
            self.assertNotIn(char, proc.stdout)

    def test_text_findings_escape_fields_and_invalid_utf8(self):
        unsafe = "\x9b\u202e\u2028\u2029\ue000\ud800\u0378"
        finding = dict(path=unsafe, line=1, column=1, level="error", message=unsafe)
        code, result = resolve.result_object([Path(unsafe)], [finding], [], [])
        self.assertEqual(code, 1)
        self.assertEqual(result["findings"][0]["message"], unsafe)
        for char in unsafe:
            self.assertNotIn(char, "".join(result["_text"]))
        (self.repo / "code.c").write_bytes(b"// SPDX-License-Identifier: MIT\nint VALUE; \xff\n")
        self.entry["commit"] = self.commit_all()
        self.write()
        proc = subprocess.run([sys.executable, str(spec.HERE / "spec.py"), "show", str(self.path),
                               "--repo", f"code={self.repo}"], capture_output=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn(b"\\xff", proc.stdout)
        absent = self.base / "absent\x9b\u202e.spec.yaml"
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = spec.main(["show", str(absent)])
        self.assertEqual(code, 2)
        self.assertIn("\\x9b\\u202e", err.getvalue())
        self.assertNotIn("\x9b", err.getvalue())
        self.assertNotIn("\u202e", err.getvalue())

    def test_trailing_comma_gets_one_space(self):
        for tail in (", ", ",", ",   "):
            source = f"commit: '{self.commit}'\na: {{path: code.c{tail}}}\n"
            out = drift.rewrite(source, ("commit",), "a" * 40, [(("a",), "stale", None)], self.commit)
            self.assertIn("code.c, stale:", out)
            self.assertNotIn("code.c,  ", out)
