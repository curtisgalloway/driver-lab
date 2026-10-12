# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Exercise copied check templates with real fixtures and a symlinked temp path."""

import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
CI = HERE.parent / "ci"
FIXTURES = HERE / "fixtures/license-gate"
PROFILES = {
    "docs": ("docs-named", "gpl-only", "", "widgetchip-bsd-overlay", "", 0, 0),
    "permissive": (
        "bsd",
        "gpl-only",
        "widgetchip-bsd-overlay",
        "widgetchip-gpl3-overlay",
        "ISC 0BSD",
        1,
        1,
    ),
    "gpl": (
        "gpl-only",
        "gpl3-only",
        "widgetchip-bsd-overlay",
        "widgetchip-gpl3-overlay",
        "ISC 0BSD",
        2,
        1,
    ),
}


class CheckTemplates(unittest.TestCase):
    """Good fixtures must pass and bad fixtures must fail for the intended reason."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        physical = self.root / "physical temp"
        physical.mkdir()
        alias = self.root / "temp alias"
        alias.symlink_to(physical, target_is_directory=True)
        self.fixture_temp = alias / "fixtures"
        self.set_mktemp('mkdir -p "$FIXTURE_TEMP"\nprintf "%s\\n" "$FIXTURE_TEMP"\n')
        self.roots = []
        for profile in PROFILES:
            root = self.root / profile / "specs"
            root.mkdir(parents=True)
            shutil.copyfile(
                FIXTURES / "roots" / profile / "board-specs.yaml",
                root / "board-specs.yaml",
            )
            self.roots.append(root)

    def set_mktemp(self, body):
        """Return a controlled symlink path on Linux as well as macOS."""
        path = self.bin / "mktemp"
        path.write_text("#!/usr/bin/env bash\nset -eu\n" + body, encoding="utf-8")
        path.chmod(0o755)

    def invoke(self, profile, step="self-test", contexts=None, ci="", resolve="0"):
        """Copy and configure the template, then execute the real checker."""
        script = self.root / profile / "scripts/checks.sh"
        script.parent.mkdir(exist_ok=True)
        text = (CI / "checks.sh").read_text(encoding="utf-8")
        values = list(PROFILES[profile])
        values[:4] = [value + ".spec.yaml" if value else "" for value in values[:4]]
        keys = (
            "FIT",
            "MISFIT",
            "BOARD_FIT",
            "BOARD_MISFIT",
            "EXTRA_FIT_LICENSES",
            "REQUIRE_FURTHER",
            "SRC_FIT",
        )
        for key, value in [("REPO", "hardware-specs-" + profile), *zip(keys, values)]:
            text, count = re.subn(rf"(?m)^{key}=.*$", f'{key}="{value}"', text)
            self.assertEqual(count, 1)
        script.write_text(text, encoding="utf-8")
        if contexts is None:
            contexts = self.roots[: PROFILES[profile][5]]
        return subprocess.run(
            ["bash", str(script), "--mode", "pr", step, str(REPO), *map(str, contexts)],
            cwd=script.parent.parent,
            env={
                **os.environ,
                "PATH": str(self.bin) + os.pathsep + os.environ["PATH"],
                "FIXTURE_TEMP": str(self.fixture_temp),
                "CHECKS_PYTHON": sys.executable,
                "RESOLVE_SRC": resolve,
                "CI": ci,
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=60,
            check=False,
        )

    def test_all_profiles_through_symlinked_temp_directory(self):
        for profile in PROFILES:
            with self.subTest(profile=profile):
                result = self.invoke(profile)
                self.assertEqual(result.returncode, 0, result.stdout)
                self.assertIn("self-test: passed", result.stdout)
                self.assertIn("is not accepted by root", result.stdout)
                self.assertNotIn("reached through, a symbolic link", result.stdout)
                self.assertFalse(self.fixture_temp.exists(), "temporary root leaked")

    def test_required_context_cannot_be_omitted(self):
        for profile in ("permissive", "gpl"):
            with self.subTest(profile=profile):
                result = self.invoke(profile, contexts=[])
                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertIn("further root(s)", result.stdout)

    def test_ci_requires_resolution(self):
        result = self.invoke("docs", ci="true")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("running in CI without RESOLVE_SRC=1", result.stdout)

    def test_mktemp_failure_stops_before_creating_fixtures(self):
        self.set_mktemp("exit 1\n")
        result = self.invoke("docs")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertNotIn("fit docs-named.spec.yaml", result.stdout)
        self.assertFalse(self.fixture_temp.exists())

    def test_canonicalization_failure_stops_before_creating_fixtures(self):
        self.set_mktemp('printf "%s\\n" "$FIXTURE_TEMP"\n')
        result = self.invoke("docs")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertNotIn("fit docs-named.spec.yaml", result.stdout)
        self.assertFalse(self.fixture_temp.exists())

    def test_discovery_failure_cannot_report_success(self):
        self.set_mktemp('printf "%s\\n" "$FIXTURE_TEMP"\n')
        find = self.bin / "find"
        find.write_text("#!/usr/bin/env bash\nexit 1\n", encoding="utf-8")
        find.chmod(0o755)
        result = self.invoke("docs", step="resolve", resolve="1")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("error: cannot discover spec files", result.stdout)
        self.assertNotIn("resolve: no specs", result.stdout)
        self.assertFalse(self.fixture_temp.exists(), "discovery file leaked")

    def test_workflow_runs_all_checks_on_both_platforms(self):
        workflow = yaml.safe_load((CI / "checks.yml").read_text(encoding="utf-8"))
        job = workflow["jobs"]["checks"]
        self.assertEqual(
            job["strategy"]["matrix"]["os"], ["ubuntu-latest", "macos-latest"]
        )
        self.assertFalse(job["strategy"]["fail-fast"])
        self.assertEqual(job["runs-on"], "${{ matrix.os }}")
        self.assertEqual(workflow["permissions"], {"contents": "read"})
        self.assertEqual(workflow["env"]["TOOL_COMMIT"], "0" * 40)
        steps = job["steps"]
        self.assertIn('test "$TOOL_COMMIT" != ' + "0" * 40, steps[0]["run"])
        checks = [
            step
            for step in steps
            if step.get("run", "").startswith("scripts/checks.sh")
        ]
        self.assertEqual(len(checks), 4)
        for command, step in zip(("check", "resolve", "render", "self-test"), checks):
            self.assertIn(command + " .driver-lab", step["run"])
            if command in ("resolve", "self-test"):
                self.assertEqual(step["env"]["RESOLVE_SRC"], 1)
        self.assertIn('--mode "$CHECKS_MODE"', checks[0]["run"])
        for step in steps:
            if "uses" in step:
                self.assertRegex(step["uses"], r"@[0-9a-f]{40}$")
        tool = next(
            step for step in steps if step.get("with", {}).get("path") == ".driver-lab"
        )
        self.assertEqual(tool["with"]["ref"], "${{ env.TOOL_COMMIT }}")
        self.assertFalse(tool["with"]["persist-credentials"])


if __name__ == "__main__":
    unittest.main()
