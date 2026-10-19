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

    def test_docs_profile_with_context_root_passes_cross_root_overlay_self_test(self):
        result = self.invoke("docs", contexts=[self.roots[1]])
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("overlay with the second root", result.stdout)
        self.assertIn("self-test: passed", result.stdout)

    def test_check_step_runs_stubs_from_and_stubgen_check(self):
        repo_dir = self.root / "docs"
        spec_text = (FIXTURES / "board" / "widgetchip.spec.yaml").read_text(
            encoding="utf-8"
        )
        spec_text = spec_text[: spec_text.index("facts:\n")] + "facts: []\n"
        (repo_dir / "specs" / "widgetchip.spec.yaml").write_text(
            spec_text, encoding="utf-8"
        )
        domains = repo_dir / "domains.yaml"
        domains.write_text(
            "# SPDX-FileCopyrightText: 2026 contributors\n"
            "# SPDX-License-Identifier: CC-BY-4.0\n"
            "format: 2\n"
            "board: widgetchip\n"
            "copyright: 2026 contributors\n"
            "license: CC-BY-4.0\n"
            "domains:\n"
            "  - name: widgetchip-usb-expert\n"
            "    title: WidgetChip USB\n"
            "    description: USB host questions on WidgetChip\n"
            "    entry: [widgetchip]\n"
            "    preload: [board-expert]\n",
            encoding="utf-8",
        )
        stubgen = REPO / "skills/board-spec-scaffold/scripts/stubgen.py"
        gen = subprocess.run(
            [sys.executable, "-I", str(stubgen), str(domains), "--out", str(repo_dir / "skills")],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(gen.returncode, 0, gen.stderr)

        result = self.invoke("docs", step="check")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("--stubs-from skills", result.stdout)
        self.assertIn("== stubgen domains.yaml --out skills --check", result.stdout)

        stub_file = repo_dir / "skills/widgetchip-usb-expert/SKILL.md"
        stub_file.write_text(stub_file.read_text(encoding="utf-8") + "\ndrift\n", encoding="utf-8")
        drifted = self.invoke("docs", step="check")
        self.assertEqual(drifted.returncode, 1, drifted.stdout)
        self.assertIn("stale", drifted.stdout)

    def test_resolve_step_auto_binds_valid_cache_repo_and_skips_partial_or_missing(self):
        self.set_mktemp(
            'if [ "${1:-}" = "-d" ]; then mkdir -p "$FIXTURE_TEMP"; fi\n'
            'printf "%s\\n" "$FIXTURE_TEMP"\n'
        )
        repo_dir = self.root / "permissive"
        cache_repo = repo_dir / "cache" / "tools"
        cache_repo.mkdir(parents=True)
        git_env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@users.noreply.github.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@users.noreply.github.com",
        }
        subprocess.run(["git", "init", "-q", str(cache_repo)], env=git_env, check=True)
        src_file = cache_repo / "driver.c"
        src_file.write_text(
            "// SPDX-License-Identifier: BSD-3-Clause\n"
            "int stub_magic(void) { return 42; }\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "-C", str(cache_repo), "add", "driver.c"], env=git_env, check=True)
        subprocess.run(
            ["git", "-C", str(cache_repo), "commit", "-q", "-m", "init"],
            env=git_env,
            check=True,
        )
        commit = subprocess.run(
            ["git", "-C", str(cache_repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        shutil.copyfile(
            FIXTURES / "board" / "widgetchip.spec.yaml",
            repo_dir / "specs" / "widgetchip.spec.yaml",
        )
        overlay = (FIXTURES / "board" / "widgetchip-src-overlay.spec.yaml").read_text(
            encoding="utf-8"
        )
        overlay = re.sub(r'commit: "[0-9a-f]{40}"', f'commit: "{commit}"', overlay)
        overlay = overlay.replace("license_from: notice", "license_from: spdx-line")
        overlay = overlay.replace("path: armstubs/armstub8.S", "path: driver.c")
        overlay = overlay.replace("lines: [30, 30]", "lines: [2, 2]")
        (repo_dir / "specs" / "widgetchip-src-overlay.spec.yaml").write_text(
            overlay, encoding="utf-8"
        )

        result = self.invoke("permissive", step="resolve", resolve="1")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("--repo tools=cache/tools", result.stdout)
        self.assertIn("1 anchor(s) resolved, 0 skipped", result.stdout)

        subprocess.run(
            ["git", "-C", str(cache_repo), "config", "extensions.partialClone", "origin"],
            check=True,
        )
        partial_res = self.invoke("permissive", step="resolve", resolve="1")
        self.assertIn("resolve: skipping cache/tools (partial clone)", partial_res.stdout)
        self.assertNotIn("--repo tools=cache/tools", partial_res.stdout)
        subprocess.run(
            ["git", "-C", str(cache_repo), "config", "--unset", "extensions.partialClone"],
            check=True,
        )

        absent_commit = "f" * 40
        (repo_dir / "specs" / "widgetchip-src-overlay.spec.yaml").write_text(
            overlay.replace(f'commit: "{commit}"', f'commit: "{absent_commit}"'),
            encoding="utf-8",
        )
        missing_res = self.invoke("permissive", step="resolve", resolve="1")
        self.assertIn(
            f"resolve: skipping cache/tools (missing commit {absent_commit})",
            missing_res.stdout,
        )
        self.assertNotIn("--repo tools=cache/tools", missing_res.stdout)

    def test_publish_workflow_uses_repo_checkout_path_and_pinned_shas(self):
        workflow = yaml.safe_load((CI / "publish.yml").read_text(encoding="utf-8"))
        for job_name in ("build", "deploy"):
            steps = workflow["jobs"][job_name]["steps"]
            for step in steps:
                if "uses" in step:
                    self.assertRegex(step["uses"], r"@[0-9a-f]{40}$")
            repo_checkout = next(
                step for step in steps if step.get("with", {}).get("path") == "repo"
            )
            self.assertFalse(repo_checkout["with"]["persist-credentials"])
        build_step = next(
            step
            for step in workflow["jobs"]["build"]["steps"]
            if "SOURCE_COMMIT" in step.get("env", {})
        )
        self.assertEqual(build_step["env"]["SOURCE_COMMIT"], "${{ github.sha }}")
        self.assertIn('--source-commit "repo/specs=$SOURCE_COMMIT"', build_step["run"])
        self.assertIn("repo/specs", build_step["run"])

    def test_release_workflow_builds_four_targets_with_tool_commit(self):
        workflow = yaml.safe_load(
            (REPO / ".github/workflows/release.yml").read_text(encoding="utf-8")
        )
        build_job = workflow["jobs"]["build"]
        targets = [inc["target"] for inc in build_job["strategy"]["matrix"]["include"]]
        self.assertEqual(
            targets,
            [
                "x86_64-unknown-linux-gnu",
                "aarch64-unknown-linux-gnu",
                "x86_64-apple-darwin",
                "aarch64-apple-darwin",
            ],
        )
        for job in workflow["jobs"].values():
            for step in job["steps"]:
                if "uses" in step:
                    self.assertRegex(step["uses"], r"@[0-9a-f]{40}$")
        self.assertEqual(
            build_job["env"]["DRIVER_LAB_TOOL_COMMIT"], "${{ github.sha }}"
        )


if __name__ == "__main__":
    unittest.main()
