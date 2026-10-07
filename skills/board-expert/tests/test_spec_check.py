#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""
Tests for scripts/spec_check.py, run against wholly synthetic fixture roots.

Run:  python3 -m unittest discover -s skills/board-expert/tests -v
  or: python3 skills/board-expert/tests/test_spec_check.py

Every case runs twice, once per parser: with PyYAML if it is importable, and
with --no-pyyaml so the stdlib subset parser is exercised on the same inputs.
CI has no PyYAML, so the fallback is the parser that actually gates a push.
"""

import json
import pathlib
import subprocess
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
CHECKER = HERE.parent / "scripts" / "spec_check.py"
FIX = HERE / "fixtures"
GOOD = FIX / "good_root"
BAD = FIX / "bad_root"
VENDOR = FIX / "vendor_root"
VERIFY = FIX / "verify_root"
STUBS = FIX / "stubs"

sys.path.insert(0, str(CHECKER.parent))
import spec_check  # noqa: E402

PARSER_FLAGS = [["--no-pyyaml"]]
try:
    import yaml  # noqa: F401

    PARSER_FLAGS.append([])
except ImportError:
    pass


def run(*args, flags):
    proc = subprocess.run(
        [sys.executable, str(CHECKER), *flags, "--json", *[str(a) for a in args]],
        capture_output=True,
        text=True,
        check=False,
    )
    data = json.loads(proc.stdout) if proc.stdout.strip() else {"findings": []}
    return proc.returncode, data, proc.stderr


def messages(data):
    return [f["message"] for f in data["findings"]]


# The warnings a root marker without license fields carries (LS-R1). The fixture roots
# predate the fields on purpose: they are what bringup-kit-style markers look like.
LICENSE_ABSENT = ("root marker: no license: field", "root marker: no accepts: field")


def is_license_absent(f):
    return f["level"] == "warning" and f["message"].startswith(LICENSE_ABSENT)


def without_license_absent(data):
    """Findings other than the absent-license-field warnings."""
    return [f for f in data["findings"] if not is_license_absent(f)]


def substantive(data):
    """Findings other than the 'unverified' warning every record-less fixture spec carries,
    and the absent-license-field warnings of the pre-LS2 fixture markers."""
    return [f for f in without_license_absent(data) if not f["message"].startswith("unverified:")]


class SubsetParser(unittest.TestCase):
    def test_parses_the_shapes_the_format_uses(self):
        text = (
            "kind: soc\n"
            "id: x\n"
            "triggers: [a, b c, 'd,e']\n"
            "empty: []\n"
            "hex: 0xfe201000\n"
            "nothing: null\n"
            "flag: true\n"
            "note: >-\n"
            "  folded line one\n"
            "  folded line two\n"
            "instances:\n"
            "  - name: uart0   # trailing comment\n"
            "    ip: pl011\n"
            "    irq: {kind: SPI, number: 121, trigger: level-high, note: shared line}\n"
            "    clocks: [clk]\n"
            "  - name: uart1\n"
            "resources:\n"
            "  repos:\n"
            "    - name: linux\n"
            "      files:\n"
            "        - a/b.c\n"
            "        - d/e.c\n"
            "  docs: []\n"
        )
        data = spec_check.parse_yaml_subset(text)
        self.assertEqual(data["triggers"], ["a", "b c", "d,e"])
        self.assertEqual(data["empty"], [])
        self.assertEqual(data["hex"], 0xFE201000)
        self.assertIsNone(data["nothing"])
        self.assertTrue(data["flag"])
        self.assertEqual(data["note"], "folded line one folded line two")
        self.assertEqual(
            data["instances"][0],
            {
                "name": "uart0",
                "ip": "pl011",
                "irq": {"kind": "SPI", "number": 121, "trigger": "level-high", "note": "shared line"},
                "clocks": ["clk"],
            },
        )
        self.assertEqual(data["instances"][1], {"name": "uart1"})
        self.assertEqual(data["resources"]["repos"][0]["files"], ["a/b.c", "d/e.c"])
        self.assertEqual(data["resources"]["docs"], [])

    def test_rejects_unterminated_flow_collections(self):
        with self.assertRaises(spec_check.YamlError):
            spec_check.parse_yaml_subset("name: [unterminated\n")
        with self.assertRaises(spec_check.YamlError):
            spec_check.parse_yaml_subset("irq: {kind: SPI\n")

    def test_rejects_colon_space_in_plain_scalars_like_pyyaml(self):
        with self.assertRaises(spec_check.YamlError) as ctx:
            spec_check.parse_yaml_subset("note: TODO (verify on hardware): the PMIC\n")
        self.assertIn("'note'", str(ctx.exception))
        with self.assertRaises(spec_check.YamlError):
            spec_check.parse_yaml_subset("irq: {kind: SPI, number: 3, note: shared: yes}\n")
        with self.assertRaises(spec_check.YamlError):
            spec_check.parse_yaml_subset("files:\n  - a: b: c\n")
        self.assertEqual(
            spec_check.parse_yaml_subset('note: "TODO (verify on hardware): quoted"\n'),
            {"note": "TODO (verify on hardware): quoted"},
        )
        self.assertEqual(spec_check.parse_yaml_subset("url: https://x/y\n"), {"url": "https://x/y"})

    def test_quotes_protect_commas_and_colons_inside_flow_mappings(self):
        text = 'irq: {kind: SPI, number: 3, note: "a, b: c"}\n'
        expected = {"irq": {"kind": "SPI", "number": 3, "note": "a, b: c"}}
        self.assertEqual(spec_check.parse_yaml_subset(text), expected)
        try:
            import yaml
        except ImportError:
            return
        self.assertEqual(yaml.safe_load(text), expected)

    def test_agrees_with_pyyaml_on_the_shipped_specs_and_fixtures(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML not installed")
        paths = list((HERE.parent / "specs").rglob("*.spec.md"))
        paths += list((HERE.parent / "specs").rglob("*.verify.md"))
        paths += [p for p in FIX.rglob("*.spec.md") if p.name not in ("broken.spec.md", "colon.spec.md")]
        paths += list(FIX.rglob("*.verify.md"))
        for path in sorted(paths):
            m = spec_check.FRONTMATTER_RE.match(path.read_text())
            self.assertIsNotNone(m, path)
            self.assertEqual(
                spec_check.parse_yaml_subset(m.group(1)),
                spec_check.load_yaml(m.group(1), use_pyyaml=True),
                path,
            )


class TagRules(unittest.TestCase):
    def ok(self, bullet):
        return bool(spec_check.TAIL_RE.search(bullet))

    def test_tail_accepts_the_documented_shapes(self):
        self.assertTrue(self.ok("- Fact. `[DT]`"))
        self.assertTrue(self.ok("- Fact. `[DT]` (node), `[databook]` (DDI 0183)"))
        self.assertTrue(self.ok("- Fact. [DT] (node) [doc] (page)."))
        self.assertTrue(self.ok("- Fact. `[DT]` (a (nested) note). `TODO (verify on hardware)`: the IRQ."))
        self.assertTrue(self.ok("- Fact. `[source-observed]` TODO (verify on hardware)"))

    def test_tail_rejects_tags_in_the_middle(self):
        self.assertFalse(self.ok("- The `[DT]` value is 5, and then prose."))
        self.assertFalse(self.ok("- Fact. `[DT]` (node). See the other spec."))
        self.assertFalse(self.ok("- Fact. `[DT]` (node). TODO (verify on hardware): x. Also `[doc]` (p) more."))

    def test_gap_bullets(self):
        self.assertTrue(spec_check.GAP_RE.match("- **Power.** `TODO (verify on hardware)`: PMIC."))
        self.assertTrue(spec_check.GAP_RE.match("- TODO (verify on hardware): everything."))
        self.assertFalse(spec_check.GAP_RE.match("- **Power.** The PMIC is X. TODO (verify on hardware)"))

    def test_doc_needs_a_parenthetical(self):
        self.assertIsNone(spec_check.DOC_UNNAMED_RE.search("`[doc]` (page)"))
        self.assertIsNone(spec_check.DOC_UNNAMED_RE.search("[doc] (page)"))
        self.assertIsNotNone(spec_check.DOC_UNNAMED_RE.search("`[doc]`"))
        self.assertIsNotNone(spec_check.DOC_UNNAMED_RE.search("`[doc]`, `[DT]` (node)"))

    def test_dt_needs_a_parenthetical(self):
        dt = spec_check.UNNAMED_RES["DT"]
        self.assertIsNone(dt.search("`[DT]` (`bcm2712.dtsi`)"))
        self.assertIsNone(dt.search("[DT] (lga-b0.dtb from a prebuilt tree)"))
        self.assertIsNotNone(dt.search("`[DT]`"))
        self.assertIsNotNone(dt.search("`[DT]`, `[databook]` (DDI 0183)"))

    def test_inference_needs_a_parenthetical(self):
        inf = spec_check.UNNAMED_RES["inference"]
        self.assertIsNone(inf.search("`[inference]` (the driver clears it before reset; ordering follows)"))
        self.assertIsNone(inf.search("[inference] (premises: x; derivation: y)"))
        self.assertIsNotNone(inf.search("`[inference]`"))
        self.assertIsNotNone(inf.search("`[inference]`, `[databook]` (DDI 0183)"))

    def test_inference_is_a_tag_in_the_tail(self):
        self.assertTrue(
            self.ok("- Fact. `[inference]` (premises: the driver does x; so the hardware requires x)"
                    " TODO (verify on hardware)")
        )

    def test_inference_without_todo_is_an_error(self):
        body = (
            "## Gotchas\n\n"
            "- The hardware requires this ordering. `[inference]` (the driver does it every time)\n"
        )
        self.assertIn(
            "[inference] fact without 'TODO (verify on hardware)'",
            "\n".join(self.tags_of(body)),
        )

    def test_inference_without_a_parenthetical_is_an_error(self):
        body = (
            "## Gotchas\n\n"
            "- The hardware requires this ordering. `[inference]` TODO (verify on hardware)\n"
        )
        self.assertIn(
            "[inference] must be followed by a parenthetical naming its premises and derivation",
            "\n".join(self.tags_of(body)),
        )

    def test_rtl_with_a_parenthetical_needs_no_todo(self):
        body = (
            "## Gotchas\n\n"
            "- Bit 3 is write-one-to-clear. `[rtl]` (usb2_wrap r2p1, `ctrl_regs`)\n"
        )
        self.assertEqual(self.tags_of(body), [])

    def test_rtl_without_a_parenthetical_is_an_error(self):
        body = "## Gotchas\n\n- Bit 3 is write-one-to-clear. `[rtl]`\n"
        self.assertIn(
            "[rtl] must be followed by a parenthetical naming the design, its revision, "
            "and the module",
            "\n".join(self.tags_of(body)),
        )

    def test_emulated_needs_a_parenthetical(self):
        emu = spec_check.UNNAMED_RES["emulated"]
        self.assertIsNone(emu.search("`[emulated]` (widget-model 1.0, runs widget-q1-01 and widget-q1-02)"))
        self.assertIsNone(emu.search("[emulated] (widget-model 1.0, run widget-q1-01)"))
        self.assertIsNotNone(emu.search("`[emulated]`"))
        self.assertIsNotNone(emu.search("`[emulated]`, `[databook]` (Widget TRM 4.2)"))

    def test_emulated_beside_another_class_passes(self):
        body = (
            "## Gotchas\n\n"
            "- **Grant bit.** Reads back set at power-on on the model. `[databook]` (Widget TRM 4.2), "
            "`[emulated]` (widget-model 1.0, runs widget-q1-01 and widget-q1-02) "
            "`TODO (verify on hardware)`: read it after power-on.\n"
        )
        self.assertEqual(self.tags_of(body), [])

    def test_emulated_as_an_inference_premise_passes(self):
        body = (
            "## Gotchas\n\n"
            "- **Reset gap.** Leave 10 microseconds. `[inference]` (premises: the databook asks for 1 "
            "`[databook]` (Widget TRM 5.1); 4 to 8 observed `[emulated]` (widget-model 1.0, run "
            "widget-q1-01); a posted write cannot be timed) `TODO (verify on hardware)`: measure it.\n"
        )
        self.assertEqual(self.tags_of(body), [])

    def test_emulated_alone_is_an_error(self):
        body = (
            "## Gotchas\n\n"
            "- Reception pauses for a second after a control write. `[emulated]` (widget-model 1.0, "
            "run widget-q1-01) `TODO (verify on hardware)`: time it on a board.\n"
        )
        msgs = self.tags_of(body)
        self.assertEqual(len(msgs), 1, msgs)
        self.assertIn("[emulated] is never the sole authority for a fact", msgs[0])

    def test_emulated_without_todo_is_an_error(self):
        body = (
            "## Gotchas\n\n"
            "- The transmit ring drains with the link down. `[databook]` (Widget TRM 3), "
            "`[emulated]` (widget-model 1.0, run widget-q1-01)\n"
        )
        self.assertEqual(self.tags_of(body), ["[emulated] fact without 'TODO (verify on hardware)'"])

    def test_emulated_without_a_parenthetical_is_an_error(self):
        body = (
            "## Gotchas\n\n"
            "- Reads back set. `[databook]` (Widget TRM 4.2), `[emulated]` "
            "`TODO (verify on hardware)`: read it on a board.\n"
        )
        self.assertEqual(
            self.tags_of(body),
            ["[emulated] must be followed by a parenthetical naming the device model, its version "
             "and the run IDs"],
        )

    def tags_of(self, body):
        spec = spec_check.Spec(pathlib.Path("x.spec.md"), pathlib.Path("."), "public", {}, body)
        findings = []
        spec_check.check_tags(spec, findings)
        return [f.message for f in findings]

    def test_tag_names_in_prose_are_not_tags(self):
        prose = "## Gotchas\n\n- Every address here is a decompiled-blob `[DT]` fact. `[DT]` (`x.dtb`, prebuilts)\n"
        self.assertEqual(self.tags_of(prose), [])
        bare = "## Gotchas\n\n- Uses a `[doc]` page and a `[press]` claim. `[standard]` (ARM ARM)\n"
        self.assertEqual(self.tags_of(bare), [])
        only_prose = "## Gotchas\n\n- The `[DT]` value is 5, and then more prose.\n"
        self.assertEqual(len(self.tags_of(only_prose)), 1)
        self.assertIn("a tag name in the prose does not count", self.tags_of(only_prose)[0])

    def test_placeholder_scan(self):
        findings = []
        spec_check.check_placeholders(
            "id: <id>\nSee <https://a.b/c> and <x@y.z>; the tuple `<type number flags>` and\n"
            "```\n<in a fence>\n```\nbut <node> here.",
            "f",
            findings,
        )
        tokens = sorted(f.message for f in findings)
        self.assertEqual(
            tokens,
            ["unsubstituted template placeholder '<id>'", "unsubstituted template placeholder '<node>'"],
        )


class GoodRoot(unittest.TestCase):
    def test_clean_root_passes_with_both_parsers(self):
        for flags in PARSER_FLAGS:
            with self.subTest(flags=flags):
                code, data, err = run(GOOD, "--stub", FIX / "stub_good.md", flags=flags)
                self.assertEqual(code, 0, err + json.dumps(data))
                self.assertEqual(substantive(data), [])
                self.assertEqual(data["specs"], 3)
                self.assertEqual(data["verification"], {"unverified": 3})
                expected = "subset" if flags or not spec_check.pyyaml_available() else "pyyaml"
                self.assertEqual(data["parser"], expected)

    def test_human_output_names_the_parser(self):
        proc = subprocess.run(
            [sys.executable, str(CHECKER), "--no-pyyaml", str(GOOD)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("(parser: subset)", proc.stdout)

    def test_shipped_public_root_passes(self):
        for flags in PARSER_FLAGS:
            with self.subTest(flags=flags):
                code, data, err = run(
                    HERE.parent / "specs", "--stubs-from", HERE.parent.parent, flags=flags
                )
                self.assertEqual(code, 0, err + json.dumps(data))

    def test_shipped_public_root_declares_its_license(self):
        """The shipped marker carries license: and accepts: (user's decision, 2026-10-06)."""
        for flags in PARSER_FLAGS:
            with self.subTest(flags=flags):
                code, data, err = run(
                    HERE.parent / "specs", "--require-license", "--stubs-from",
                    HERE.parent.parent, flags=flags,
                )
                self.assertEqual(code, 0, err + json.dumps(data))
                self.assertEqual(data["findings"], [])
        marker = spec_check.load_yaml((HERE.parent / "specs" / "board-specs.yaml").read_text(), False)
        self.assertEqual(marker["license"], "Apache-2.0")
        self.assertEqual(marker["accepts"], ["Apache-2.0", "MIT", "BSD-2-Clause", "BSD-3-Clause"])

    def test_missing_root_marker_is_a_precondition(self):
        code, _, err = run(FIX, flags=["--no-pyyaml"])
        self.assertEqual(code, 3)
        self.assertIn("no board-specs.yaml", err)


def write_root(tmp, marker, specs=None):
    """A root at tmp/root with the given marker text and {filename: text} specs."""
    root = pathlib.Path(tmp) / "root"
    root.mkdir()
    (root / "board-specs.yaml").write_text(marker)
    for name, text in (specs or {}).items():
        (root / name).write_text(text)
    return root


CHIP_WITH_REPO = """\
---
kind: chip
id: lchip
name: License test chip
triggers: [lchip]
resources:
  repos:
    - name: fw
      url: https://example.com/fw
{license_line}---

## Quick-facts

- A fact. `[doc]` (Widget TRM 1.0)
"""


class LegacyMarkers(unittest.TestCase):
    """Characterization: markers written before LS2 (bringup-kit's tests write `layer` only)."""

    def test_layer_only_marker_passes(self):
        import tempfile

        for flags in PARSER_FLAGS:
            for marker in ("layer: public\n", "layer: local\nname: mine\n"):
                with self.subTest(flags=flags, marker=marker), tempfile.TemporaryDirectory() as tmp:
                    root = write_root(tmp, marker, {"c.spec.md": CHIP_WITH_REPO.format(license_line="")})
                    code, data, err = run(root, flags=flags)
                    self.assertEqual(code, 0, err + json.dumps(data))
                    self.assertEqual([f for f in data["findings"] if f["level"] == "error"], [])

    def test_repo_license_is_optional_without_accepts(self):
        import tempfile

        for line in ("", "      license: GPL-2.0-only\n"):
            with self.subTest(line=line), tempfile.TemporaryDirectory() as tmp:
                root = write_root(tmp, "layer: public\n", {"c.spec.md": CHIP_WITH_REPO.format(license_line=line)})
                code, data, err = run(root, flags=["--no-pyyaml"])
                self.assertEqual(code, 0, err + json.dumps(data))


GATE_ROOTS = HERE.parent.parent / "peripheral-spec" / "tests" / "fixtures" / "license-gate" / "roots"
LICENSED = "layer: public\nlicense: Apache-2.0\naccepts: [Apache-2.0, MIT]\n"
GATE_BOARD = GATE_ROOTS.parent / "board"


class RootLicense(unittest.TestCase):
    """Root marker license: and accepts: (LS-R1); repos license: (LS-R2)."""

    def check(self, marker, specs=None, *args, flags=("--no-pyyaml",)):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = write_root(tmp, marker, specs)
            return run(root, *args, flags=list(flags))

    def by_level(self, data):
        return {f["message"]: f["level"] for f in data["findings"]}

    def test_the_three_repo_shaped_roots_pass_with_require_license(self):
        for flags in PARSER_FLAGS:
            for name in ("gpl", "docs", "permissive"):
                with self.subTest(flags=flags, root=name):
                    code, data, err = run(GATE_ROOTS / name, "--require-license", flags=flags)
                    self.assertEqual(code, 0, err + json.dumps(data))
                    self.assertEqual(data["findings"], [])

    def test_absent_fields_warn_and_require_license_makes_them_errors(self):
        for flags in PARSER_FLAGS:
            with self.subTest(flags=flags):
                code, data, err = self.check("layer: public\n", flags=flags)
                self.assertEqual(code, 0, err)
                levels = self.by_level(data)
                self.assertEqual(sorted(levels.values()), ["warning", "warning"])
                self.assertTrue(any(m.startswith("root marker: no license: field") for m in levels))
                self.assertTrue(any(m.startswith("root marker: no accepts: field") for m in levels))
                code, data, err = self.check("layer: public\n", None, "--require-license", flags=flags)
                self.assertEqual(code, 1, err)
                levels = self.by_level(data)
                self.assertEqual(sorted(levels.values()), ["error", "error"])
                self.assertTrue(any(m.startswith("root marker: no license: field") for m in levels))
                self.assertIn("FAIL: 2 error(s)", self.human("layer: public\n", "--require-license"))

    def human(self, marker, *args):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = write_root(tmp, marker)
            proc = subprocess.run(
                [sys.executable, str(CHECKER), "--no-pyyaml", *args, str(root)],
                capture_output=True, text=True, check=False,
            )
            return proc.stderr

    def test_one_field_missing_is_reported_alone(self):
        code, data, _ = self.check("layer: public\nlicense: CC-BY-4.0\n", None, "--require-license")
        self.assertEqual(code, 1)
        self.assertEqual(len(data["findings"]), 1)
        self.assertTrue(data["findings"][0]["message"].startswith("root marker: no accepts: field"))
        code, data, _ = self.check("layer: public\naccepts: []\n", None, "--require-license")
        self.assertEqual(code, 1)
        self.assertEqual(len(data["findings"]), 1)
        self.assertTrue(data["findings"][0]["message"].startswith("root marker: no license: field"))

    def test_invalid_marker_fields_are_errors_naming_the_field(self):
        for marker, expected in (
            ("license: GPL-2\naccepts: []\n",
             "root marker: license: unknown SPDX license identifier 'GPL-2'"),
            ("license: MIT or Apache-2.0\naccepts: []\n",
             "root marker: license: 'or': write the operator in uppercase (OR)"),
            ("license: MIT\naccepts: MIT\n",
             "root marker: accepts: must be a list of SPDX identifiers ([] for none)"),
            ("license: MIT\naccepts: [MIT, GPL-2]\n",
             "root marker: accepts entry 'GPL-2': unknown SPDX license identifier 'GPL-2'"),
            ("license: MIT\naccepts: ['MIT OR ISC']\n",
             "root marker: accepts entry 'MIT OR ISC': 'MIT OR ISC' is an expression"),
        ):
            for flags in PARSER_FLAGS:
                with self.subTest(marker=marker, flags=flags):
                    code, data, err = self.check("layer: public\n" + marker, flags=flags)
                    self.assertEqual(code, 1, err)
                    self.assertTrue(
                        any(m.startswith(expected) for m in messages(data)), messages(data)
                    )

    def test_repo_license_must_be_spdx(self):
        spec = {"c.spec.md": CHIP_WITH_REPO.format(license_line="      license: GPL-2.0 or later\n")}
        for marker in ("layer: public\n", LICENSED):
            with self.subTest(marker=marker):
                code, data, _ = self.check(marker, spec)
                self.assertEqual(code, 1)
                self.assertIn(
                    "repos entry 'fw': license: 'or': write the operator in uppercase (OR)",
                    messages(data),
                )

    def test_repo_license_is_required_where_accepts_is_declared(self):
        missing = {"c.spec.md": CHIP_WITH_REPO.format(license_line="")}
        for marker in (LICENSED, "layer: public\nlicense: CC-BY-4.0\naccepts: []\n"):
            with self.subTest(marker=marker):
                code, data, _ = self.check(marker, missing)
                self.assertEqual(code, 1)
                self.assertIn(
                    "repos entry 'fw': no license: (required in a root whose marker declares accepts:)",
                    messages(data),
                )
        # LS-R2 asks for a valid license, not an accepted one, so without --require-license
        # GPL-2.0-only passes in a root that accepts only Apache-2.0 and MIT. Under
        # --require-license the board-spec gate applies (BoardSpecGate, LS5).
        for lic in ("GPL-2.0 OR MIT", "GPL-2.0-only"):
            with self.subTest(license=lic):
                present = {"c.spec.md": CHIP_WITH_REPO.format(license_line=f"      license: {lic}\n")}
                code, data, err = self.check(LICENSED, present)
                self.assertEqual(code, 0, err + json.dumps(data))
                self.assertEqual(substantive(data), [])


TWO_REPOS = """\
---
kind: chip
id: gchip
name: Gate test chip
triggers: [gchip]
resources:
  repos:
    - name: fw
      url: https://example.com/fw
      license: {fw}
    - name: tools
      url: https://example.com/tools
      license: {tools}
---

## Quick-facts

- A fact. `[doc]` (Widget TRM 1.0)
"""

OVERLAY_WITH_REPO = """\
---
overlays: gchip
resources:
  repos:
    - name: stub
      url: https://example.com/stub
      license: {lic}
---

## Quick-facts

- An added fact. `[doc]` (Widget TRM 1.0)
"""


class BoardSpecGate(unittest.TestCase):
    """--require-license gates resources.repos[].license against accepts: (LS5, user 2026-10-06).

    Four tests characterize behavior that must not change and pass on the pre-LS5 script:
    the three under "characterization" and test_cross_root_overlay_resolves_only_with_the_docs_root.
    The rest describe the gate and fail there.
    """

    def check(self, marker, specs, *args, flags=("--no-pyyaml",)):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = write_root(tmp, marker, specs)
            code, data, err = run(root, *args, flags=list(flags))
            return code, data, err, root

    def gate_errors(self, data):
        return [f for f in data["findings"] if f["message"].startswith("license gate:")]

    # -- characterization: unchanged behavior

    def test_without_require_license_an_unaccepted_repo_license_passes(self):
        spec = {"c.spec.md": TWO_REPOS.format(fw="GPL-2.0-only", tools="MIT")}
        for flags in PARSER_FLAGS:
            with self.subTest(flags=flags):
                code, data, err, _ = self.check(LICENSED, spec, flags=flags)
                self.assertEqual(code, 0, err + json.dumps(data))
                self.assertEqual(substantive(data), [])

    def test_accepted_repo_licenses_pass_under_require_license(self):
        for fw, tools in (("MIT", "Apache-2.0"), ("GPL-2.0 OR MIT", "MIT"),
                          ("(MIT AND Apache-2.0)", "mit")):
            spec = {"c.spec.md": TWO_REPOS.format(fw=fw, tools=tools)}
            for flags in PARSER_FLAGS:
                with self.subTest(fw=fw, flags=flags):
                    code, data, err, _ = self.check(LICENSED, spec, "--require-license", flags=flags)
                    self.assertEqual(code, 0, err + json.dumps(data))
                    self.assertEqual(substantive(data), [])

    def test_invalid_repo_license_is_reported_once_not_also_gated(self):
        spec = {"c.spec.md": TWO_REPOS.format(fw="GPL-2", tools="MIT")}
        code, data, _, _ = self.check(LICENSED, spec, "--require-license")
        self.assertEqual(code, 1)
        errors = [f["message"] for f in data["findings"] if f["level"] == "error"]
        self.assertEqual(len(errors), 1, errors)
        self.assertTrue(
            errors[0].startswith("repos entry 'fw': license: unknown SPDX license identifier 'GPL-2'"),
            errors,
        )

    # -- the gate

    def test_unaccepted_repo_license_fails_naming_spec_repo_license_and_accepts(self):
        spec = {"c.spec.md": TWO_REPOS.format(fw="GPL-2.0-only", tools="MIT")}
        for flags in PARSER_FLAGS:
            with self.subTest(flags=flags):
                code, data, err, root = self.check(LICENSED, spec, "--require-license", flags=flags)
                self.assertEqual(code, 1, err)
                self.assertEqual(
                    [(f["level"], f["path"], f["message"]) for f in data["findings"]
                     if not f["message"].startswith("unverified:")],
                    [("error", str(root / "c.spec.md"),
                      f"license gate: repos entry 'fw' (GPL-2.0-only), which root {root} does not "
                      "accept (accepts: Apache-2.0, MIT); cite it from a root that accepts it, or "
                      "drop it")],
                )

    def test_docs_root_accepts_no_repo(self):
        spec = {"c.spec.md": TWO_REPOS.format(fw="MIT", tools="BSD-3-Clause")}
        code, data, err, root = self.check(
            "layer: public\nlicense: CC-BY-4.0\naccepts: []\n", spec, "--require-license"
        )
        self.assertEqual(code, 1, err)
        self.assertEqual(
            [f["message"] for f in self.gate_errors(data)],
            [f"license gate: repos entry 'fw' (MIT), which root {root} does not accept "
             "(accepts: none); cite it from a root that accepts it, or drop it",
             f"license gate: repos entry 'tools' (BSD-3-Clause), which root {root} does not "
             "accept (accepts: none); cite it from a root that accepts it, or drop it"],
        )

    def test_and_needs_every_part_and_or_any(self):
        for lic, fails in (("GPL-2.0-only AND MIT", True), ("GPL-2.0-only OR MIT", False),
                           ("GPL-2.0+", True), ("Apache-2.0 WITH LLVM-exception", False)):
            spec = {"c.spec.md": TWO_REPOS.format(fw=lic, tools="MIT")}
            with self.subTest(license=lic):
                code, data, err, _ = self.check(LICENSED, spec, "--require-license")
                self.assertEqual(code, int(fails), err + json.dumps(data))
                self.assertEqual(len(self.gate_errors(data)), int(fails))

    def test_the_repo_shaped_roots_gate_board_specs_like_anchors(self):
        """GPL-only repo: GPL root passes, docs and permissive fail; GPL OR MIT: permissive too."""
        import shutil
        import tempfile

        cases = {("GPL-2.0-only", "gpl"): 0, ("GPL-2.0-only", "docs"): 1,
                 ("GPL-2.0-only", "permissive"): 1, ("GPL-2.0 OR MIT", "permissive"): 0,
                 ("BSD-3-Clause", "permissive"): 0, ("BSD-3-Clause", "docs"): 1}
        for (lic, name), want in cases.items():
            with self.subTest(license=lic, root=name), tempfile.TemporaryDirectory() as tmp:
                root = pathlib.Path(tmp) / name
                root.mkdir()
                shutil.copy(GATE_ROOTS / name / "board-specs.yaml", root)
                (root / "c.spec.md").write_text(TWO_REPOS.format(fw=lic, tools=lic))
                code, data, err = run(root, "--require-license", flags=["--no-pyyaml"])
                self.assertEqual(code, want, err + json.dumps(data))
                self.assertEqual(len(self.gate_errors(data)), 2 * want)

    def test_overlays_are_gated_by_their_own_root(self):
        specs = {"c.spec.md": TWO_REPOS.format(fw="MIT", tools="MIT"),
                 "o.spec.md": OVERLAY_WITH_REPO.format(lic="GPL-2.0-only")}
        code, data, err, root = self.check(LICENSED, specs, "--require-license")
        self.assertEqual(code, 1, err)
        self.assertEqual([f["path"] for f in self.gate_errors(data)], [str(root / "o.spec.md")])
        self.assertIn("repos entry 'stub' (GPL-2.0-only)", self.gate_errors(data)[0]["message"])

    def test_board_fixtures_against_the_repo_shaped_roots(self):
        """The board fixtures the spec repositories' self-tests copy (license-gate/board/)."""
        import shutil
        import tempfile

        overlays = {None: {"gpl": 0, "docs": 0, "permissive": 0},
                    "widgetchip-bsd-overlay.spec.md": {"gpl": 0, "docs": 1, "permissive": 0},
                    "widgetchip-gpl3-overlay.spec.md": {"gpl": 1, "docs": 1, "permissive": 1}}
        for overlay, by_root in overlays.items():
            for name, want in by_root.items():
                with self.subTest(overlay=overlay, root=name), tempfile.TemporaryDirectory() as tmp:
                    root = pathlib.Path(tmp) / name
                    root.mkdir()
                    shutil.copy(GATE_ROOTS / name / "board-specs.yaml", root)
                    shutil.copy(GATE_BOARD / "widgetchip.spec.md", root)
                    if overlay:
                        shutil.copy(GATE_BOARD / overlay, root)
                    code, data, err = run(root, "--require-license", flags=["--no-pyyaml"])
                    self.assertEqual(code, want, err + json.dumps(data))
                    errors = [f["message"] for f in data["findings"] if f["level"] == "error"]
                    self.assertEqual(len(errors), want, errors)
                    self.assertTrue(all(m.startswith("license gate: repos entry") for m in errors))

    def test_cross_root_overlay_resolves_only_with_the_docs_root(self):
        """The permissive repository's overlay targets a spec in the docs repository (design risk)."""
        import shutil
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            docs, perm = pathlib.Path(tmp) / "docs", pathlib.Path(tmp) / "permissive"
            docs.mkdir()
            perm.mkdir()
            shutil.copy(GATE_ROOTS / "docs" / "board-specs.yaml", docs)
            shutil.copy(GATE_BOARD / "widgetchip.spec.md", docs)
            shutil.copy(GATE_ROOTS / "permissive" / "board-specs.yaml", perm)
            shutil.copy(GATE_BOARD / "widgetchip-bsd-overlay.spec.md", perm)
            code, data, err = run(perm, "--require-license", flags=["--no-pyyaml"])
            self.assertEqual(code, 1, err)
            self.assertIn("overlays 'widgetchip' resolves to nothing", messages(data))
            code, data, err = run(perm, docs, "--require-license", flags=["--no-pyyaml"])
            self.assertEqual(code, 0, err + json.dumps(data))
            self.assertEqual(substantive(data), [])

    def test_human_output_names_the_spec(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = write_root(tmp, LICENSED, {"c.spec.md": TWO_REPOS.format(fw="GPL-2.0-only", tools="MIT")})
            proc = subprocess.run(
                [sys.executable, str(CHECKER), "--no-pyyaml", "--require-license", str(root)],
                capture_output=True, text=True, check=False,
            )
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertIn(f"error: {root / 'c.spec.md'}: license gate: repos entry 'fw' (GPL-2.0-only)",
                      proc.stderr)


class BadRoot(unittest.TestCase):
    def findings(self, flags):
        code, data, _ = run(BAD, "--stub", FIX / "stub_bad.md", flags=flags)
        self.assertEqual(code, 1)
        return messages(data)

    def test_every_failure_class_is_reported(self):
        for flags in PARSER_FLAGS:
            with self.subTest(flags=flags):
                msgs = "\n".join(self.findings(flags))
                for expected in (
                    "parts entry 'missingsoc' resolves to nothing",
                    "access: internal under a public root",
                    "via 'skill:acme-board-tools' is not a public skill",
                    "fact bullet has no provenance tag",
                    "[source-observed] fact without",
                    "[press] fact without",
                    "[doc] must be followed by a parenthetical",
                    "[DT] must be followed by a parenthetical",
                    "[emulated] fact without",
                    "[emulated] must be followed by a parenthetical",
                    "[emulated] is never the sole authority for a fact",
                    "irq.kind extended requires irq.parent",
                    "irq.parent is only valid for kind extended",
                    "irq.intid is not valid for kind extended",
                    "file 'c/d.dtsi': status must be one of",
                    "files entry must be a path or a mapping with path",
                    "does not end with its tag clause",
                    "ip 'nosuchip' resolves to nothing",
                    "'badboard' is not an ip spec",
                    "reg must be an integer or null",
                    "irq must be null or a mapping",
                    "irq.kind must be one of",
                    "irq.number must be an integer",
                    "duplicate id 'badsoc'",
                    "ip spec has no docs entry with cite: true",
                    "frontmatter does not parse",
                    "unknown kind 'widget'",
                    "missing required key 'cache'",
                    "variant_of 'nosuchbase' resolves to nothing",
                    "variants: entry without a name",
                    "a series is a map, never cite: true",
                    "fetch must be one of",
                    "status must be one of",
                    "stub spec id 'nosuchboard' resolves to nothing",
                    "a tag name in the prose does not count",
                    "id '<chip-id>' is not a normalized id",
                    "aliases entry 'Bad_Alias' is not a normalized id",
                    "not_triggers must be a list of non-empty strings",
                    "tag must be a provenance class, not 'rumor'",
                    "source must be a string",
                    "fetch_via must be a non-empty string",
                    "unsubstituted template placeholder '<chip-id>'",
                    "unsubstituted template placeholder '<bus>'",
                    "unsubstituted template placeholder '<node>'",
                ):
                    self.assertIn(expected, msgs)
                self.assertNotIn("<https://example.com/ok>", msgs)
                self.assertNotIn("<id@example.com>", msgs)
                self.assertNotIn("<type number flags>", msgs)
                self.assertNotIn("'ok-alias'", msgs)
                # fetch: partial is a legal value; only fetch_via was wrong in badvariant
                self.assertNotIn("'Partially readable page': fetch must be", msgs)
                # colon.spec.md fails under both parsers, each in its own words
                if spec_check.parser_name(not flags) == "subset":
                    self.assertIn("contains ': '", msgs)
                else:
                    self.assertIn("mapping values are not allowed here", msgs)

    def test_public_skill_allowlist_silences_via(self):
        code, data, _ = run(BAD, "--public-skill", "acme-board-tools", flags=["--no-pyyaml"])
        self.assertEqual(code, 1)
        self.assertNotIn("is not a public skill", "\n".join(messages(data)))


class Stubs(unittest.TestCase):
    def test_stubs_from_finds_stubs_by_their_sentence(self):
        code, data, _ = run(GOOD, "--stubs-from", STUBS, flags=["--no-pyyaml"])
        self.assertEqual(code, 1)
        # widget-expert, broken-expert, placeholder-expert; not-a-stub ignored
        self.assertEqual(data["stubs"], 3)
        msgs = "\n".join(messages(data))
        self.assertIn("stub spec id 'nosuchboard' resolves to nothing", msgs)
        self.assertIn("unsubstituted template placeholder '<Board display name>'", msgs)
        self.assertNotIn("not-a-stub", msgs)

    def test_stubs_from_needs_a_directory(self):
        code, _, err = run(GOOD, "--stubs-from", FIX / "nowhere", flags=["--no-pyyaml"])
        self.assertEqual(code, 3)
        self.assertIn("is not a directory", err)


class VendorRoot(unittest.TestCase):
    def test_overlays_resolve_across_roots_and_internal_is_allowed(self):
        for flags in PARSER_FLAGS:
            with self.subTest(flags=flags):
                code, data, _ = run(GOOD, VENDOR, flags=flags)
                msgs = messages(data)
                self.assertEqual(code, 1, msgs)
                self.assertIn("overlays 'nosuchboard' resolves to nothing", "\n".join(msgs))
                self.assertNotIn("access: internal", "\n".join(msgs))
                warnings = [f for f in substantive(data) if f["level"] == "warning"]
                self.assertEqual(len(warnings), 2)
                self.assertIn("2 overlays for 'widgetboard' in layer 'product'", warnings[0]["message"])

    def test_vendor_root_alone_cannot_resolve_its_targets(self):
        code, data, _ = run(VENDOR, flags=["--no-pyyaml"])
        self.assertEqual(code, 1)
        self.assertIn("overlays 'widgetboard' resolves to nothing", "\n".join(messages(data)))


class CacheWarning(unittest.TestCase):
    def test_part_cache_mismatch_warns(self):
        import tempfile, shutil

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / "root"
            shutil.copytree(GOOD, root)
            soc = root / "widgetsoc.spec.md"
            soc.write_text(soc.read_text().replace("cache: widget-resources", "cache: other-resources"))
            code, data, _ = run(root, flags=["--no-pyyaml"])
            self.assertEqual(code, 0)
            warnings = [f for f in substantive(data) if f["level"] == "warning"]
            self.assertEqual(len(warnings), 1)
            self.assertIn("names cache 'other-resources'", warnings[0]["message"])


class Verification(unittest.TestCase):
    """Records under <root>/resources/<id>.verify.md, read by frontmatter only."""

    def test_record_hashes_match_the_fixture_specs(self):
        # The records for vok and vfail must carry the hash of the fixture file as committed.
        # If this fails, someone edited the fixture spec: recompute with `shasum -a 256`.
        import hashlib

        for sid in ("vok", "vfail"):
            spec = VERIFY / f"{sid}.spec.md"
            record = (VERIFY / "resources" / f"{sid}.verify.md").read_text()
            digest = hashlib.sha256(spec.read_bytes()).hexdigest()
            self.assertIn(f"spec_sha256: {digest}", record, sid)

    def test_every_status_is_reported(self):
        for flags in PARSER_FLAGS:
            with self.subTest(flags=flags):
                code, data, _ = run(VERIFY, flags=flags)
                self.assertEqual(code, 1)
                self.assertEqual(data["specs"], 6)  # records are not specs
                self.assertEqual(
                    data["verification"],
                    {"verified": 1, "stale": 2, "failing": 1, "unverified": 1, "malformed": 1},
                )
                msgs = "\n".join(messages(data))
                self.assertIn("verification record reports 1 FAIL verdict(s)", msgs)
                self.assertIn("verification stale: resources/vstale.verify.md", msgs)
                self.assertIn("unverified: no record at resources/vnone.verify.md", msgs)
                self.assertIn("verification record: missing key 'summary'", msgs)
                self.assertIn("verified must be an ISO date", msgs)
                self.assertIn("fetch must be one of", msgs)
                self.assertIn("sources entry without a name", msgs)
                by_level = {f["message"]: f["level"] for f in data["findings"]}
                self.assertEqual(by_level["unverified: no record at resources/vnone.verify.md"], "warning")
                self.assertTrue(
                    any(k.startswith("verification stale") and v == "warning" for k, v in by_level.items())
                )

    def test_stale_record_with_fail_verdicts_is_an_error(self):
        import shutil, tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / "root"
            (root / "resources").mkdir(parents=True)
            shutil.copy(VERIFY / "board-specs.yaml", root)
            shutil.copy(VERIFY / "vstalefail.spec.md", root)
            shutil.copy(VERIFY / "resources" / "vstalefail.verify.md", root / "resources")
            for flags in PARSER_FLAGS:
                for require in (False, True):
                    with self.subTest(flags=flags, require=require):
                        args = ["--require-verified"] if require else []
                        code, data, err = run(root, *args, flags=flags)
                        self.assertEqual(code, 1, err + json.dumps(data))
                        self.assertEqual(data["verification"], {"stale": 1})
                        by_level = {f["message"]: f["level"] for f in without_license_absent(data)}
                        self.assertEqual(by_level, {
                            "verification stale: resources/vstalefail.verify.md was written for another version of this file":
                                "error" if require else "warning",
                            "verification record reports 1 FAIL verdict(s); see resources/vstalefail.verify.md":
                                "error",
                        })

    def test_require_verified_upgrades_the_warnings(self):
        code, data, _ = run(VERIFY, "--require-verified", flags=["--no-pyyaml"])
        self.assertEqual(code, 1)
        by_level = {f["message"]: f["level"] for f in data["findings"]}
        self.assertEqual(by_level["unverified: no record at resources/vnone.verify.md"], "error")
        self.assertTrue(
            any(k.startswith("verification stale") and v == "error" for k, v in by_level.items())
        )
        code, data, _ = run(GOOD, "--require-verified", flags=["--no-pyyaml"])
        self.assertEqual(code, 1)
        self.assertEqual(data["verification"], {"unverified": 3})

    def test_a_verified_root_is_clean_under_require_verified(self):
        import shutil, tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / "root"
            (root / "resources").mkdir(parents=True)
            shutil.copy(VERIFY / "board-specs.yaml", root)
            shutil.copy(VERIFY / "vok.spec.md", root)
            shutil.copy(VERIFY / "resources" / "vok.verify.md", root / "resources")
            code, data, err = run(root, "--require-verified", flags=["--no-pyyaml"])
            self.assertEqual(code, 0, err + json.dumps(data))
            self.assertEqual(without_license_absent(data), [])
            self.assertEqual(data["verification"], {"verified": 1})

    def _verified_root(self, tmp, summary_line):
        """A one-spec root whose record carries the given summary line."""
        import shutil

        root = pathlib.Path(tmp) / "root"
        (root / "resources").mkdir(parents=True)
        shutil.copy(VERIFY / "board-specs.yaml", root)
        shutil.copy(VERIFY / "vok.spec.md", root)
        record = (VERIFY / "resources" / "vok.verify.md").read_text()
        old = [ln for ln in record.splitlines() if ln.startswith("summary:")]
        self.assertEqual(len(old), 1, "fixture record should have exactly one summary line")
        record = record.replace(old[0], summary_line)
        (root / "resources" / "vok.verify.md").write_text(record)
        return root

    def test_adjudicate_is_optional_and_never_an_error_on_its_own(self):
        """A disagreement is an adjudication item, not a failure: it must not fail the check."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = self._verified_root(
                tmp, "summary: {pass: 1, fail: 0, unverifiable: 0, gap: 0, adjudicate: 2}"
            )
            code, data, err = run(root, "--require-verified", flags=["--no-pyyaml"])
            self.assertEqual(code, 0, err + json.dumps(data))
            self.assertEqual(without_license_absent(data), [])
            self.assertEqual(data["verification"], {"verified": 1})

    def test_adjudicate_must_be_a_non_negative_integer_when_present(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = self._verified_root(
                tmp, "summary: {pass: 1, fail: 0, unverifiable: 0, gap: 0, adjudicate: -1}"
            )
            code, data, _ = run(root, flags=["--no-pyyaml"])
            self.assertEqual(code, 1)
            self.assertIn(
                "verification record: summary.adjudicate must be a non-negative integer",
                "\n".join(messages(data)),
            )


if __name__ == "__main__":
    unittest.main()
