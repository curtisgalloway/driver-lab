# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Round-2 regressions; every method fails by assertion on export 2447a9d."""

import contextlib
import copy
import io
import json
import re
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

import yaml

from test_check import chip, fact, inference, marker, repo, src_fact
from test_render_md import HERE, PARSER, checked, run
import test_render_md as render_tests
import render_md
import spec
import specmd
import speccheck


class ReviewRound2(unittest.TestCase):
    setUp = render_tests.Views.setUp
    write = render_tests.Views.write
    def assert_fenced(self, out, value):
        tokens = PARSER.parse(out)
        expected = value + ("\n" if value and not value.endswith("\n") else "")
        fences = [t for t in tokens if t.type == "fence" and t.content == expected]
        self.assertEqual(len(fences), 1, value)
        self.assertEqual((fences[0].level, fences[0].info), (0, ""))
        self.assertFalse(any(c.type in ("link_open", "image", "html_inline")
                             for t in tokens for c in t.children or []))
        return tokens

    def test_author_fields_are_inert_and_notes_stay_in_order(self):
        data = yaml.safe_load(chip(facts=fact("a") + inference("b", "#a")))
        values = {key: key + " [link](https://example.invalid) `tick`\n- item"
                  for key in ("claim", "fact", "support", "conflict", "resource", "orientation", "states")}
        data["orientation"] = values["orientation"]
        data["resources"]["documents"][0]["note"] = values["resource"]
        entry = data["facts"][1]
        entry["claim"], entry["note"] = values["claim"], values["fact"]
        support = entry["support"][0]
        support["premises"].append({"states": values["states"],
                                    "support": copy.deepcopy(data["facts"][0]["support"])})
        support["premises"][-1]["support"][0]["note"] = values["support"]
        entry["conflicts"] = [{"reading": "other", "support": [
            {"class": "databook", "doc": "trm", "at": [{"section": "2"}],
             "note": values["conflict"]}]}]
        self.write(data)
        for flags in ((), ("--with-status",)):
            code, out, err = run(self.root, "--format", "md", *flags)
            self.assertEqual((code, err), (0, ""))
            for value in values.values():
                self.assert_fenced(out, value)
            for key in ("support", "conflict", "states"):
                self.assertLess(out.index(values[key]), out.index(values["fact"]))
                self.assertLess(out.index("`widgetchip@root_name#b`"), out.index(values[key]))

    def test_author_fence_lengths_content_and_offsets(self):
        for value in ("", " ", "\n", "  \n\n", "```", "a\n`````\nend\n",
                      "[normal](https://example.invalid)", "![image](https://example.invalid/a)"):
            with self.subTest(value=value):
                out = render_md.View()
                out.extend(["Generated preface", ""])
                out.author(value)
                text = "\n".join(out)
                tokens = self.assert_fenced(text, value)
                fence = next(t for t in tokens if t.type == "fence")
                self.assertGreater(len(fence.markup), max((len(s) for s in re.findall(r"`+", value)), default=0))
                self.assertGreaterEqual(len(fence.markup), 3)
                try:
                    specmd.check_view(text, out.expected)
                except ValueError as exc:
                    self.fail(str(exc))
                with self.assertRaisesRegex(ValueError, "containment"):
                    specmd.check_view("\n" + text, out.expected)

    def test_deep_block_and_inline_nesting_rejected(self):
        deep = "".join("  " * i + "- l\n" for i in range(10))
        payload = "\n<script>alert(1)</script>\n\n[x](javascript:alert(1))\n\n# Injected\n"
        images = "![a" * 21 + "](javascript:alert(1))" * 21
        for value in (deep + payload, images, "> " * 200 + "deep", "> " * 2000 + "deep"):
            with self.subTest(value=value):
                found = specmd.findings(value)
                self.assertTrue(any(f.message == "nesting deeper than 16" for f in found))
                data = yaml.safe_load(chip())
                data["facts"][0]["claim"] = value
                self.write(data)
                code, out, err = run(self.root, "--format", "md", "--json")
                self.assertEqual((code, err), (1, ""))
                self.assertIsNone(json.loads(out)["markdown"])
        self.assertEqual(specmd.findings("> " * 15 + "shallow"), [])

    def test_footnotes_in_fields_including_code(self):
        for value in ("Claim[^x]", "[^x]: definition", "> Claim[^x]", "- [^x]: definition"):
            with self.subTest(value=value):
                self.assertTrue(any(f.kind == "footnote" for f in specmd.findings(value)))
                data = yaml.safe_load(chip())
                data["facts"][0]["claim"] = "Claim[^x]"
                data["facts"][0]["note"] = "[^x]: resolves in another field"
                self.write(data)
                code, out, err = run(self.root, "--format", "md", "--json")
                self.assertEqual((code, err), (1, ""))
                self.assertIsNone(json.loads(out)["markdown"])
        for value in ("`[^x]`", "```\n[^x]: text\n```", "    [^x]: text"):
            self.assertTrue(any(f.kind == "footnote" for f in specmd.findings(value)))

    def test_fence_and_table_review_payloads(self):
        data = yaml.safe_load(chip())
        data["facts"][0]["claim"] = "ordinary text\n```"
        self.write(data)
        code, out, err = run(self.root, "--format", "md", "--json")
        self.assertEqual((code, err), (1, ""))
        self.assertIn("unclosed code fence", out)
        for payload in ("[click](javascript:alert(1))", "<img src=x onerror=alert(1)>"):
            value = "a | b\n---|---\n`a|" + payload + "`"
            data["facts"][0]["claim"] = value
            self.write(data)
            code, out, err = run(self.root, "--format", "md")
            self.assertEqual((code, err), (0, ""))
            self.assert_fenced(out, value)

    def test_generated_autolinks_and_syntax_are_code_spans(self):
        for value in ("https://example.invalid", "a@example.invalid", "www.example.invalid", "a:b",
                      "a|b", "*star*", "under_score", "a``b", "<tag>", "[x]"):
            with self.subTest(value=value):
                tokens = PARSER.parse(render_md.escape(value))
                self.assertEqual([t.type for t in tokens[1].children], ["code_inline"])
                self.assertEqual(tokens[1].children[0].content, value)
        self.assertEqual(render_md.escape("ordinary words"), "ordinary words")

    def test_view_rejects_inline_html_and_unexpected_fences(self):
        signatures = specmd.constructs("a <b>x</b>")
        self.assertEqual(sum(n for (_, kind, _), n in signatures.items()
                             if kind == "html_inline"), 2)
        for text in ("generated <b>x</b>", "a <https://example.invalid>",
                     "[x](https://example.invalid)", "```\nunplaced\n```", "- ```\nx\n  ```",
                     "* * *", "> blockquote", "**emphasis**"):
            with self.subTest(text=text), patch.object(render_md, "_citation", return_value=text):
                code, out, err = run(self.root, "--format", "md", "--json")
                self.assertEqual((code, err), (1, ""))
                self.assertIsNone(json.loads(out)["markdown"])
                self.assertIn("assembled Markdown containment", out)
        data = yaml.safe_load(chip(repos=repo(), facts=src_fact("a")))
        (self.root / "board-specs.yaml").write_text(marker("root_name", accepts="[GPL-2.0-only]"))
        data["notices"] = [{"repo": "linux", "path": "drivers/w.c", "text": "# Notice"}]
        self.write(data)
        code, out, err = run(self.root, "--format", "md")
        self.assertEqual((code, err), (0, ""))
        self.assert_fenced(out, "# Notice")

    def test_text_diagnostics_encode_all_unsafe_filename_characters(self):
        for name in ("bad\x1b]52;c;Zg==\x07", "bad\u202e", "bad\u2066", "bad\x7f"):
            with self.subTest(name=name):
                self.assertNotIn(name, str(speccheck.Finding(name, 1, 1, name)))
                self.assertNotIn(name, str(spec.Finding(name, 1, 1, name)))
                out = io.StringIO()
                with patch.object(spec, "cmd_status", return_value=(1, {"_text": [name]})), contextlib.redirect_stdout(out):
                    code = spec.main(["status", str(self.root)])
                self.assertEqual(code, 1)
                self.assertNotIn(name, out.getvalue())
                target = self.root / (name + ".spec.yaml")
                self.path.rename(target)
                try:
                    for command, args in (("check", [str(self.root)]), ("render", [str(self.root), "--format", "md"]),
                                          ("validate", [str(target)]), ("status", [str(self.root)])):
                        out, err = io.StringIO(), io.StringIO()
                        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                            code = spec.main([command, *args])
                        self.assertEqual(code, 1)
                        result = out.getvalue() + err.getvalue()
                        self.assertNotIn(name, result)
                        self.assertIn("\\u", result)
                finally:
                    target.rename(self.path)
                resources = self.root / "resources"
                resources.mkdir(exist_ok=True)
                orphan = resources / (name + ".verify.yaml")
                orphan.write_text("invalid record")
                try:
                    out, err = io.StringIO(), io.StringIO()
                    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                        code = spec.main(["check", str(self.root)])
                    self.assertEqual(code, 1)
                    self.assertNotIn(name, out.getvalue() + err.getvalue())
                    self.assertIn("no spec file named", out.getvalue())
                finally:
                    orphan.unlink()

    def test_render_prechecks_nonclaim_fields_and_states(self):
        checker = checked(self.root)
        file = checker.files[0]
        for key in ("note", "title", "orientation", "milestones", "notes"):
            with self.subTest(key=key):
                target = file.data if key in ("orientation", "milestones", "notes") else file.data["facts"][0]
                previous = target.get(key)
                target[key] = "Claim[^x]"
                with self.assertRaisesRegex(ValueError, "footnote"):
                    render_md.render(checker)
                if previous is None:
                    target.pop(key)
                else:
                    target[key] = previous
        data = yaml.safe_load(chip(facts=fact("a") + inference("b", "#a")))
        data["facts"][1]["support"][0]["premises"].append({"states": "Claim[^x]", "support": []})
        file.data = data
        with self.assertRaisesRegex(ValueError, "footnote"):
            render_md.render(checker)

    def test_prose_and_record_notes_are_displayed_in_fences(self):
        checker = checked(self.root)
        file = checker.files[0]
        file.data["milestones"], file.data["notes"] = "Milestone *one*", "General _note_"
        status = checker.status[0]["rows"][0]
        status["verdict"] = "PASS"
        file.verdicts[status["key"]] = ({"date": "2026-10-09", "note": "Record *note*"}, ())
        try:
            out = render_md.render(checker, with_status=True)
        except ValueError as exc:
            self.fail(str(exc))
        for text in ("Milestone *one*", "General _note_", "Record *note*"):
            self.assert_fenced(out, text)

    def test_per_root_commits_in_three_root_worked_example(self):
        copied = self.root / "worked"
        shutil.copytree(HERE / "fixtures/worked-example", copied)
        docs, perm, gpl = (copied / n for n in ("docs", "permissive", "gpl"))
        path = perm / "bcm2711.spec.yaml"
        data = yaml.safe_load(path.read_text())
        base = yaml.safe_load((docs / "bcm2711.spec.yaml").read_text())
        data["resources"]["documents"].extend(d for d in base["resources"]["documents"]
                                               if d["name"] in ("rpi-docs-legacy-boot", "bcm2711-peripherals"))
        for name, cls in (("tfa-rpi4", "doc"), ("gic400-trm", "databook")):
            data["resources"]["documents"].append({"name": name, "class": cls,
                "title": "Synthetic omitted " + name, "url": "https://example.invalid/" + name})
        data["facts"].append({"id": "patch-words", "section": "quick-facts", "title": "Synthetic omitted premise",
            "claim": "Placeholder.", "support": [{"class": "hardware", "board": "synthetic", "method": "fixture", "date": "2026-10-08"}]})
        path.write_text(yaml.safe_dump(data, sort_keys=False))
        args = (docs, perm, gpl, "--spec", "bcm2711", "--merged", "--format", "md")
        code, out, err = run(*args, "--source-commit", "1" * 40, "--json")
        self.assertEqual((code, err), (2, ""))
        self.assertIsNone(json.loads(out)["markdown"])
        code, out, err = run(*args, "--source-commit", str(docs) + "=" + "1" * 40,
                             "--source-commit", str(perm) + "=" + "2" * 40)
        self.assertEqual((code, err), (0, ""))
        lines = [s for s in out.splitlines() if s.startswith("Source ")]
        self.assertEqual(len(lines), 3)
        for label, sha in (("hardware-specs-docs", "1" * 40), ("hardware-specs-permissive", "2" * 40),
                           ("hardware-specs-gpl", "unavailable")):
            self.assertTrue(any(label in s and "commit " + sha in s for s in lines))
        for values in ((str(docs) + "=" + "1" * 40, str(docs) + "=" + "2" * 40),
                       (str(self.root) + "=" + "1" * 40,), ("1" * 40, str(docs) + "=" + "1" * 40)):
            flags = [part for value in values for part in ("--source-commit", value)]
            code, out, err = run(*args, *flags, "--json")
            self.assertEqual((code, err), (2, ""))


if __name__ == "__main__":
    unittest.main()
