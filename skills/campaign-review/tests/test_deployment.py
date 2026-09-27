# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Manifest validation, config resolution, role routing and comparison triggers."""

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import uuid

from test_sweep import BASELINE_DEPLOYMENT, ROOT, SCRIPTS, check, inputs, sweep
from test_stopping import complete_readings, entry
import deployment


class DeploymentTests(unittest.TestCase):
    """Exercise the public interface with isolated user configuration."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.root)})
        self.env.start()
        self.addCleanup(self.env.stop)
        # Manifests built here start from CR5's reference, whose reader matches
        # the frozen index's adopted scope.reader.
        self.document = check.read_yaml(BASELINE_DEPLOYMENT)

    def save(self, document=None, name="deployment.yaml"):
        path = self.root / name
        path.write_text(check.yaml.safe_dump(document or self.document))
        return path

    def test_reference_and_default(self):
        reference = check.read_yaml(deployment.REFERENCE)
        reader = next(p for p in reference["plugins"] if p["id"] == "reader")
        self.assertEqual(deployment.load(), deployment.validate(reference))
        self.assertEqual(deployment.load()["reader"], reader["model"])

    def test_user_config_and_explicit_override_preserve_run_store(self):
        settings = deployment.module_at(
            "settings_test", ROOT / "utilities/run-store.py"
        )
        cfg = self.root / "driver-lab"
        cfg.mkdir()
        self.document["plugins"][3]["model"]["name"] = uuid.uuid4().hex
        (cfg / "selected.yaml").write_text(check.yaml.safe_dump(self.document))
        (cfg / "config.toml").write_text(
            'run_store = "runs"\ndeployment = "selected.yaml"\n'
        )
        self.assertEqual(deployment.load(), deployment.validate(self.document))
        self.assertEqual(
            deployment.load(deployment.REFERENCE),
            deployment.validate(check.read_yaml(deployment.REFERENCE)),
        )
        with mock.patch.dict(os.environ, {"DRIVER_LAB_RUNS": ""}):
            self.assertEqual(settings.run_store()[0], Path("runs"))
        (cfg / "config.toml").write_text('deployment = "absent.yaml"\n')
        with self.assertRaises(OSError):
            deployment.load()

    def test_bad_manifest_fields(self):
        mutations = [
            (lambda d: d.update(version=True)),
            (lambda d: d.update(plugins={})),
            (lambda d: d["plugins"].append(copy.deepcopy(d["plugins"][0]))),
            (lambda d: d["plugins"][0].update(kind=[])),
            (lambda d: d["plugins"][0].update(via="shell:command")),
            (lambda d: d["plugins"][0].update(command="python3 tool.py")),
            (lambda d: d["plugins"][0].pop("command")),
            (lambda d: d["plugins"][2].update({"class": "unregistered"})),
            (lambda d: d["plugins"][2].update({"class": []})),
            (lambda d: d["plugins"][3].update(model={"name": "x"})),
            (lambda d: d["plugins"].pop()),
        ]
        for number, mutate in enumerate(mutations):
            with self.subTest(case=number):
                document = copy.deepcopy(self.document)
                mutate(document)
                with self.assertRaises(check.Invalid):
                    deployment.validate(document)

    def test_producer_class_requires_definition_not_mention(self):
        self.document["plugins"][2]["class"] = "kernel"
        spec = self.root / "spec.md"
        spec.write_text("Mentioning `[kernel]` is not a definition.\n")
        with self.assertRaisesRegex(check.Invalid, "unknown producer class"):
            deployment.validate(self.document, spec)
        spec.write_text(
            "| Tag | Meaning |\n| --- | --- |\n| `[kernel]` | Kernel interface. |\n"
        )
        deployment.validate(self.document, spec)

    def test_reader_changes_queue_even_when_sufficient_and_never_verdicts(self):
        claims, status, registry = inputs()
        complete_readings(status)
        for eid in ("AF-1-reading-coverage", "SR-8-independent-reading"):
            entry(status, eid)["impact"] = dict(claims=[], changes_status=False)
        before = copy.deepcopy(status)
        original = sweep.sweep(
            claims, status, registry, roles=deployment.load(BASELINE_DEPLOYMENT)
        )
        self.assertTrue(original["stopping"]["sufficient"])
        model = {"name": uuid.uuid4().hex, "version": "2"}
        self.document["plugins"][3]["model"] = model
        roles = deployment.load(self.save())
        changed = sweep.sweep(claims, status, registry, roles=roles)
        units = [
            u for u in changed["stopping"]["queue"] if u["kind"] == "comparison-reading"
        ]
        self.assertEqual(len(units), 1)
        self.assertEqual(units[0]["model"], model)
        self.assertEqual(units[0]["role"], "reader")
        self.assertEqual(original["entries"], changed["entries"])
        self.assertEqual(status, before)

    def test_cli_routes_models_from_config_without_code_changes(self):
        for plugin in self.document["plugins"]:
            if plugin["kind"] == "role":
                plugin["model"]["name"] = uuid.uuid4().hex
        manifest = self.save()
        cfg = self.root / "driver-lab"
        cfg.mkdir()
        (cfg / "config.toml").write_text(
            "deployment = " + json.dumps(str(manifest)) + "\n"
        )
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "sweep.py"),
                str(ROOT / "evals/e1000"),
                "--json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 1, proc.stderr)
        queue = json.loads(proc.stdout)["stopping"]["queue"]
        roles = deployment.load(manifest)
        for unit in queue:
            self.assertEqual(unit["model"], roles[unit["role"]])
        self.assertTrue(any(u["role"] == "reviewer" for u in queue))

    def test_cli_without_deployment_key_names_reference_models(self):
        """CR-G cross-milestone check: no config key means the reference roles."""
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "sweep.py"),
                str(ROOT / "evals/e1000"),
                "--json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertIn(proc.returncode, (0, 1), proc.stderr)
        queue = json.loads(proc.stdout)["stopping"]["queue"]
        roles = deployment.validate(check.read_yaml(deployment.REFERENCE))
        for unit in queue:
            self.assertEqual(unit["model"], roles[unit["role"]])

    def test_implementer_role_does_not_bypass_authorization(self):
        claims, status, registry = inputs()
        item = entry(status, "A-RR-4")
        item["action"] = "implementation"
        item.pop("decision", None)
        self.document["plugins"][4]["model"]["name"] = uuid.uuid4().hex
        roles = deployment.load(self.save())
        report = sweep.sweep(claims, status, registry, roles=roles)["stopping"]
        unit = next(u for u in report["queue"] if "A-RR-4" in u["entries"])
        self.assertEqual(unit["model"], roles["implementer"])
        self.assertEqual(unit["role"], "implementer")
        self.assertEqual(unit["state"], "awaiting decision")
        self.assertNotIn(unit["id"], report["batch"])


if __name__ == "__main__":
    unittest.main()
