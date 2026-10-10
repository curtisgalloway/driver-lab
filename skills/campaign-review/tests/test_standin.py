# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""CR7: unchanged commands in a generated, separate, stub-only deployment."""

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from standin import GENERATED_IDS, ROOT, SCRIPTS, Standin, digest, id_hits, public_id_hits


class StandinTests(unittest.TestCase):
    """Check invalidation, source denial, config routing and handoff inputs."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.deployment = Standin(Path(self.temp.name) / "standin")

    @classmethod
    def tearDownClass(cls):
        hits = public_id_hits(GENERATED_IDS)
        if hits:
            raise AssertionError(f"stand-in IDs leaked: {hits}")

    def sweep(self, code=0):
        proc = self.deployment.command("sweep.py", self.deployment.campaign, "--json")
        self.assertEqual(proc.returncode, code, proc.stdout + proc.stderr)
        self.assertEqual(proc.stderr, "")
        return json.loads(proc.stdout)

    def assert_affected(self, report, *keys):
        self.assertEqual(
            {row["id"] for row in report["entries"]},
            {self.deployment.ids[key] for key in keys},
        )
        for row in report["entries"]:
            self.assertEqual(row["state"], "stale")
            self.assertNotIn(row["id"], report["eligible"])

    def test_separate_root_config_contracts_and_baseline(self):
        dep = self.deployment
        self.assertTrue(self.sweep()["stopping"]["sufficient"])
        proc = dep.command("index_check.py", dep.campaign, "--root", dep.root, "--json")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        proc = subprocess.run(
            [sys.executable, str(ROOT / "utilities/run-store.py")],
            env=dep.env(),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), str(dep.runs))
        for source in dep.registry["sources"]:
            self.assertEqual(source["file"]["root"], "run_store")
            self.assertFalse(Path(source["file"]["path"]).is_absolute())
        for plugin in dep.manifest["plugins"]:
            self.assertEqual(plugin["via"], "skill:" + dep.ids["plugin-skill"])
        source = {
            key: dep.registry["sources"][0][key]
            for key in ("id", "version", "sha256", "status", "checked", "provenance")
        }
        capture = dep.directory / "source-input.json"
        capture.write_text(json.dumps(source))
        plugins = {p["kind"]: p for p in dep.manifest["plugins"]}
        proc = subprocess.run(
            plugins["source"]["command"] + [str(capture)],
            cwd=dep.root,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout), source)
        output = dep.directory / "source-output.json"
        output.write_text(proc.stdout)
        run = dep.runs / "fixture-output"
        proc = subprocess.run(
            plugins["fixture"]["command"] + [str(run), dep.ids["fixture"]],
            cwd=dep.root,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        proc = dep.command(
            "contract_check.py", "--source-json", output, "--run-dir", run, "--json"
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertTrue(json.loads(proc.stdout)["ok"])

    def test_document_change_queues_exact_live_unit_without_writing_index(self):
        dep = self.deployment
        before = (dep.campaign / "status.yaml").read_bytes()
        dep.change_document()
        report = self.sweep(1)
        self.assert_affected(report, "reading")
        self.assertIn(dep.ids["other-reading"], report["eligible"])
        queue = report["stopping"]["queue"]
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0]["kind"], "re-verification")
        self.assertEqual(queue[0]["tier"], 1)
        self.assertEqual(queue[0]["entries"], [dep.ids["reading"]])
        self.assertEqual(queue[0]["state"], "ready")
        self.assertEqual(queue[0]["model"], dep.reader)
        self.assertEqual(report["stopping"]["batch"], [queue[0]["id"]])
        self.assertEqual(self.sweep(1), report)
        self.assertEqual((dep.campaign / "status.yaml").read_bytes(), before)

    def test_version_and_hash_changes_with_source_access_denied(self):
        dep = self.deployment
        original = copy.deepcopy(dep.registry)
        launcher = """import os, runpy, sys
from pathlib import Path
denied = Path(sys.argv.pop(1)).resolve()
attempts = []
spawns = []
SPAWN_EVENTS = ('subprocess.Popen', 'os.system', 'os.exec', 'os.posix_spawn',
                'os.spawn', 'os.fork', 'os.forkpty', 'pty.spawn')
def audit(event, args):
    if event == 'open' and isinstance(args[0], (str, bytes, os.PathLike)):
        path = Path(os.fsdecode(args[0])).resolve()
        if path.is_relative_to(denied):
            attempts.append(str(path))
            raise PermissionError('invented sources unavailable to sweep')
    elif event in SPAWN_EVENTS:
        # A child process escapes this hook, so no child may start at all.
        spawns.append(event)
        raise PermissionError('child processes unavailable to sweep')
sys.addaudithook(audit)
try:
    (denied / 'denial-control').read_bytes()
except PermissionError:
    pass
else:
    raise AssertionError('source denial did not engage')
assert len(attempts) == 1
attempts.clear()
import subprocess
try:
    subprocess.run([sys.executable, '-c', 'pass'], check=False)
except PermissionError:
    pass
else:
    raise AssertionError('child-process denial did not engage')
assert spawns == ['subprocess.Popen'], spawns
spawns.clear()
sys.path.insert(0, str(Path(sys.argv[1]).parent))
sys.argv = sys.argv[1:]
try:
    runpy.run_path(sys.argv[0], run_name='__main__')
finally:
    assert not attempts, 'sweep attempted to read registered source content'
    assert not spawns, 'sweep started a child process that could read sources'
"""
        for field, value in (("version", "2"), ("sha256", "b" * 64)):
            with self.subTest(field=field):
                dep.registry = copy.deepcopy(original)
                dep.registry["sources"][0][field] = value
                dep.save()
                proc = subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        launcher,
                        str(dep.workspace / "sources"),
                        str(SCRIPTS / "sweep.py"),
                        str(dep.campaign),
                        "--json",
                    ],
                    env=dep.env(),
                    cwd=dep.root,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
                self.assertEqual(proc.stderr, "")
                report = json.loads(proc.stdout)
                self.assert_affected(report, "reading")
                self.assertEqual(report["unavailable"], [])

    def test_id_scan_finds_names_symlink_texts_and_bytes(self):
        needle = "invented-scan-control"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "bytes.txt").write_text("x " + needle, encoding="utf-8")
            (root / f"{needle}.txt").write_text("clean", encoding="utf-8")
            (root / "clean.txt").write_text("clean", encoding="utf-8")
            (root / "dangling").symlink_to(root / needle)
            (root / "dir-link").symlink_to(root / needle, target_is_directory=True)
            (root / "file-link").symlink_to(root / "clean.txt")
            names = [
                "bytes.txt",
                f"{needle}.txt",
                "clean.txt",
                "dangling",
                "dir-link",
                "file-link",
                "missing.txt",
            ]
            hits = [name for name, _ in id_hits(root, names, [needle])]
        self.assertEqual(hits, ["bytes.txt", "dangling", "dir-link", f"{needle}.txt"])

    def test_document_narrowing_and_unreviewed_widening(self):
        dep = self.deployment
        old = dep.registry["sources"][0]["sha256"]
        dep.change_document()
        source = dep.registry["sources"][0]
        source["changes"] = [
            dict(
                from_sha256=old,
                to_sha256=source["sha256"],
                since="edition-update",
                reviewed=True,
                sections=["3"],
                checks=None,
                scenarios=None,
                evidence=["invented complete editorial change map"],
            )
        ]
        dep.save()
        self.assert_affected(self.sweep())
        source["changes"][0]["sections"] = ["2"]
        dep.save()
        self.assert_affected(self.sweep(1), "reading")
        source["changes"][0].update(sections=["3"], reviewed=False)
        dep.save()
        self.assert_affected(self.sweep(1), "reading")

    def test_spec_change_follows_dependencies_and_unknown_widens(self):
        dep = self.deployment
        source = copy.deepcopy(dep.registry["sources"][0])
        source.update(
            id=dep.ids["spec"],
            kind="spec",
            revision=2,
            sha256="b" * 64,
            requirement_change=False,
            file=None,
            changes=[
                dict(
                    from_sha256=dep.status["revisions"]["1"]["spec_sha256"],
                    to_sha256="b" * 64,
                    since="revision-two",
                    reviewed=True,
                    sections=["1"],
                    checks=None,
                    scenarios=None,
                    evidence=["invented spec change map"],
                )
            ],
        )
        dep.registry["sources"].append(source)
        dep.save()
        self.assert_affected(self.sweep(1), "reading", "qualification")
        for dependencies in (["1"], None):
            with self.subTest(dependencies=dependencies):
                dep.status["bases"][dep.ids["other-basis"]][
                    "dependencies"
                ] = dependencies
                dep.save()
                self.assert_affected(
                    self.sweep(1), "reading", "other-reading", "qualification"
                )

    def test_role_change_changes_queued_model_only_through_config(self):
        dep = self.deployment
        dep.change_document()
        before = self.sweep(1)
        index = (dep.campaign / "status.yaml").read_bytes()
        model = dict(name=dep.ids["next-model"], version="2")
        next(p for p in dep.manifest["plugins"] if p["id"] == "reader")["model"] = model
        dep.save()
        after = self.sweep(1)
        self.assertEqual(before["entries"], after["entries"])
        self.assertEqual(before["eligible"], after["eligible"])
        self.assertEqual(
            [u["kind"] for u in after["stopping"]["queue"]],
            ["comparison-reading", "re-verification"],
        )
        self.assertTrue(all(u["model"] == model for u in after["stopping"]["queue"]))
        self.assertEqual((dep.campaign / "status.yaml").read_bytes(), index)
        dep.manifest_path.unlink()
        proc = dep.command("sweep.py", dep.campaign, "--json")
        self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)
        self.assertNotIn("stopping", json.loads(proc.stdout))

    def test_invented_spec_mechanical_check(self):
        dep = self.deployment
        proc = subprocess.run(
            [
                sys.executable,
                str(ROOT / "skills/spec-format/scripts/spec.py"),
                "check",
                str(dep.spec.parent),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_handoff_freezes_inputs_without_fabricating_a_reading(self):
        dep = self.deployment
        dep.change_document()
        handoff = dep.prepare_reading()
        self.assertEqual(handoff["unit"]["model"], dep.reader)
        self.assertEqual(handoff["unit"]["tier"], 1)
        self.assertFalse(Path(handoff["record"]).exists())
        hashes = json.loads(Path(handoff["input_hashes"]).read_text(encoding="utf-8"))
        # Seven before LS7, when the brief stopped copying the investigator skill's file.
        self.assertEqual(len(hashes), 6)
        for relative, checksum in hashes.items():
            self.assertEqual(digest(dep.workspace / relative), checksum)
        self.assertFalse(list(dep.workspace.rglob("status.yaml")))
        self.assertFalse(list(dep.workspace.rglob("evidence.md")))
        self.assertFalse(list(dep.workspace.rglob("*.verify.yaml")))


if __name__ == "__main__":
    unittest.main()
