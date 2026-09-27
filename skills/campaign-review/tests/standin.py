# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Generate an entirely invented deployment outside the method repository.

This is test scaffolding, also used to prepare CR7's live reader workspace.
It never invokes a model or records an automated fixture as a live reading.
"""

import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

import yaml

# Nested f-string keys support Python versions before 3.12.
# pylint: disable=inconsistent-quotes

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills/campaign-review/scripts"
HEADER = (
    "# SPDX-FileCopyrightText: 2026 contributors\n"
    "# SPDX-License-Identifier: Apache-2.0\n"
)
MARKDOWN_HEADER = "<!--\n" + HEADER.replace("# ", "") + "-->\n"
GENERATED_IDS = set()


def digest(path):
    """Hash a declared input during preparation, never during a sweep."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_yaml(path, document):
    """Write an owned fixture with the repository's license header."""
    Path(path).write_text(
        HEADER + yaml.safe_dump(document, sort_keys=False), encoding="utf-8"
    )


def public_id_hits(identities):
    """Scan tracked and publishable untracked paths and bytes, including binaries."""
    proc = subprocess.run(
        [
            "git",
            "-C",
            str(ROOT),
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "-z",
        ],
        capture_output=True,
        check=True,
    )
    names = set(proc.stdout.decode().split("\0")) - {""}
    return id_hits(ROOT, names, identities)


def id_hits(root, names, identities):
    """Find identities in path names, symlink texts (as Git stores them) and bytes."""
    needles = {identity: identity.encode() for identity in identities}
    hits = set()
    for name in names:
        path = Path(root) / name
        if path.is_symlink():
            content = os.fsencode(os.readlink(path))
        elif path.is_file():
            content = path.read_bytes()
        else:
            content = b""
        for identity, needle in needles.items():
            if identity in name or needle in content:
                hits.add((name, identity))
    return sorted(hits)


class Standin:
    """Own one temporary root, run store, configuration and stub-only manifest."""

    def __init__(self, directory, reader=None):
        self.directory = Path(directory).resolve()
        if self.directory.is_relative_to(ROOT):
            raise ValueError("stand-in must be outside the public repository")
        self.directory.mkdir(parents=True, exist_ok=False)
        self.ids = {}
        for key in (
            "campaign",
            "spec",
            "document",
            "other-document",
            "adapter",
            "fixture",
            "producer",
            "plugin-skill",
            "claim",
            "qualification",
            "reading",
            "other-reading",
            "basis",
            "other-basis",
            "run",
            "next-model",
        ):
            self.ids[key] = "invented-" + uuid.uuid4().hex
        GENERATED_IDS.update(self.ids.values())
        if public_id_hits(self.ids.values()):
            raise ValueError("invented ID collision in public repository")
        if os.environ.get("CR7_ID_LOG"):
            with Path(os.environ["CR7_ID_LOG"]).open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(list(self.ids.values())) + "\n")
        self.root = self.directory / "root"
        self.runs = self.directory / "runs"
        self.campaign = self.root / "campaign"
        self.config = self.directory / "config/driver-lab"
        self.workspace = self.runs / self.ids["run"] / "workspace"
        for path in (
            self.campaign,
            self.config,
            self.workspace / "sources",
            self.workspace / "specs/resources",
            self.root / "plugins",
        ):
            path.mkdir(parents=True)
        self.reader = reader or {"name": self.ids["next-model"], "version": "1"}
        self.documents = [
            self.workspace / "sources" / (self.ids[key] + ".md")
            for key in ("document", "other-document")
        ]
        self.documents[0].write_text(
            "# Invented device handbook\n\n## 1\n"
            "The event counter is 12 bits wide. Reading it leaves the value intact.\n"
            "\n## 2\nThe counter stops at 4095 until reset.\n"
        )
        self.documents[1].write_text(
            "# Invented storage note\n\n## 1\n"
            "Power removal erases the event count. It is not retained.\n"
        )
        self.spec = self.workspace / "specs" / (self.ids["spec"] + ".spec.md")
        meta = dict(
            kind="chip",
            id=self.ids["spec"],
            name="Invented event counter",
            triggers=[self.ids["spec"]],
            instances=[],
            resources={
                "docs": [
                    dict(
                        title=self.ids[key],
                        path="../sources/" + path.name,
                        access="internal",
                        cite=True,
                    )
                    for key, path in zip(("document", "other-document"), self.documents)
                ]
            },
        )
        self.spec.write_text(
            "---\n"
            + yaml.safe_dump(meta, sort_keys=False)
            + "---\n"
            + MARKDOWN_HEADER
            + "\n# Invented event counter\n\n## Orientation\n"
            "A fictional component for testing the review method only.\n"
            "\n## Quick-facts\n"
            "- **Width** — The count occupies 12 bits. "
            f"[databook] ({self.ids['document']} §1)\n"
            "- **Read effect** — A read does not clear the count. "
            f"[databook] ({self.ids['document']} §1)\n"
            "- **Saturation** — Counting saturates at 4095 until reset. "
            f"[databook] ({self.ids['document']} §2)\n"
            "\n## Gotchas\n"
            "- **Retention** — Loss of power discards the count. "
            f"[databook] ({self.ids['other-document']} §1)\n"
        )
        save_yaml(self.spec.parent / "board-specs.yaml", dict(layer="local"))
        self._plugins()
        self._metadata()
        self.save()

    def _plugins(self):
        """Declare owned stubs; no pinned-file adapter or real backend is used."""
        shutil.copyfile(
            Path(__file__).parent / "fixtures/standin_plugin.py",
            self.root / "plugins/stub.py",
        )
        skill = self.root / "plugins" / self.ids["plugin-skill"]
        skill.mkdir()
        (skill / "SKILL.md").write_text(
            "---\nname: "
            + self.ids["plugin-skill"]
            + "\ndescription: Invented metadata and fixture stubs for CR7.\n---\n"
            + MARKDOWN_HEADER
            + "\nRun commands from this deployment root. The source command takes a\n"
            "captured identity JSON path and prints it without opening sources.\n"
            "The fixture command takes a new run directory and a fixture ID; it\n"
            "writes canned metadata only. It operates no hardware. Producer and\n"
            "agent roles are declarations, with no automatic execution.\n"
        )
        via = "skill:" + self.ids["plugin-skill"]
        self.manifest = dict(
            version=1,
            plugins=[
                dict(
                    id=self.ids["adapter"],
                    kind="source",
                    via=via,
                    command=[sys.executable, "plugins/stub.py", "source"],
                ),
                dict(
                    id=self.ids["fixture"],
                    kind="fixture",
                    via=via,
                    command=[sys.executable, "plugins/stub.py", "fixture"],
                ),
                dict(
                    id=self.ids["producer"],
                    kind="producer",
                    via=via,
                    **{"class": "emulated"},
                ),
            ]
            + [
                dict(
                    id=role,
                    kind="role",
                    via=via,
                    agent="test stub; no execution",
                    model=dict(self.reader),
                )
                for role in ("reader", "implementer", "reviewer")
            ],
        )
        self.manifest_path = self.config / "selected.yaml"
        (self.config / "config.toml").write_text(
            "run_store = "
            + json.dumps(str(self.runs))
            + '\ndeployment = "selected.yaml"\n'
        )

    def _metadata(self):
        """Create explicitly synthetic prior readings, never an actual verdict."""
        evidence = ["campaign/evidence.md"]
        (self.campaign / "evidence.md").write_text(
            MARKDOWN_HEADER + "\n# Invented baseline\n\n"
            "All initial index entries are canned test data, not model readings.\n"
            "The optional claim has not been qualified or run against a driver.\n"
            "Sections 1 and 2 map to Quick-facts and Gotchas respectively.\n"
        )
        shutil.copyfile(
            Path(__file__).parent / "fixtures/harness.py", self.root / "harness.py"
        )
        self.claims = dict(
            version=1,
            campaign=self.ids["campaign"],
            harness="harness.py",
            claims=[
                dict(
                    id=self.ids["claim"],
                    title="Invented optional check",
                    mandatory=False,
                    cites=["1"],
                    checks=["packet arrived"],
                    scenarios=["smoke"],
                    scope="Canned method test only.",
                    defects=[],
                    evidence=evidence,
                )
            ],
        )
        basis = dict(
            spec_revision=1,
            spec_sha256=digest(self.spec),
            sections_read=[],
            dependencies=[],
            source_pins=[],
            harness_sha256=digest(self.root / "harness.py"),
            guest_init_sha256=None,
            emulator=None,
            guest=None,
            reference_module_sha256=None,
            candidate_module_sha256=None,
            toolchain=None,
            model=dict(role="reader", **self.reader),
            missing=["No driver or hardware execution in this stand-in."],
        )
        self.registry = dict(
            version=1,
            campaign=self.ids["campaign"],
            sources=[],
            citations={},
            premises={},
            contradictions=[],
        )
        self.status = dict(
            version=1,
            campaign=self.ids["campaign"],
            revision_range=[1, 1],
            revisions={
                "1": dict(
                    spec_sha256=digest(self.spec),
                    drafts={},
                    requirement_change=False,
                    changed_sections=["1", "2"],
                    items=[],
                    evidence=evidence,
                    run_ids=[self.ids["run"]],
                )
            },
            bases={},
            entries=[],
            scope=dict(
                claims=[self.ids["claim"]],
                accepted_classes={self.ids["claim"]: ["emulated"]},
                target="Invented metadata scope; no device acceptance.",
                rules=dict(
                    qualification="standin",
                    result="standin",
                    verification="standin",
                    observation="standin",
                ),
                reader=dict(self.reader),
                evidence=evidence,
            ),
        )
        common = dict(
            rule="standin",
            status=dict(
                state="current", reason="Canned test baseline.", stale_since=None
            ),
            supersedes=[],
            run_ids=[self.ids["run"]],
            evidence=evidence,
        )
        for number, (doc_key, basis_key, reading_key) in enumerate(
            (
                ("document", "basis", "reading"),
                ("other-document", "other-basis", "other-reading"),
            ),
            1,
        ):
            document = self.documents[number - 1]
            source = dict(
                id=self.ids[doc_key],
                kind="document",
                version="1",
                sha256=digest(document),
                expected_sha256=digest(document),
                status="ok",
                checked="2026-09-26",
                provenance=dict(
                    adapter=self.ids["adapter"],
                    version="1",
                    version_method="invented edition label",
                ),
                file=dict(root="run_store", path=str(document.relative_to(self.runs))),
            )
            self.registry["sources"].append(source)
            reading_basis = copy.deepcopy(basis)
            reading_basis.update(
                sections_read=[str(number)],
                source_pins=[{key: source[key] for key in ("id", "version", "sha256")}],
            )
            self.status["bases"][self.ids[basis_key]] = reading_basis
            self.status["entries"].append(
                dict(
                    copy.deepcopy(common),
                    id=self.ids[reading_key],
                    kind="verification",
                    basis=self.ids[basis_key],
                    verdict="Canned baseline; not a live reading",
                    reading_id=self.ids[reading_key],
                    text="landed",
                    sections=[str(number)],
                    evidence_classes=["databook"],
                    verifier="Invented prior reader",
                    round=str(number),
                    independence="independent",
                    purpose="accuracy",
                    covers_revisions=[1],
                    scope="Canned section coverage only.",
                    sequence=number,
                    assessment=dict(accuracy_failures=0, r_items=[], evidence=evidence),
                )
            )
            self.registry["citations"][self.ids[reading_key]] = {
                source["id"]: ["1"] if number == 2 else ["1", "2"]
            }
        self.status["entries"].append(
            dict(
                copy.deepcopy(common),
                id=self.ids["qualification"],
                kind="qualification",
                basis=self.ids["basis"],
                verdict="unqualified",
                claim=self.ids["claim"],
                validated_harness_sha256=basis["harness_sha256"],
            )
        )

    def save(self):
        """Persist only owned deployment metadata."""
        for name, value in (
            ("claims", self.claims),
            ("status", self.status),
            ("sources", self.registry),
        ):
            save_yaml(self.campaign / (name + ".yaml"), value)
        save_yaml(self.manifest_path, self.manifest)
        (self.directory / "ids.json").write_text(json.dumps(self.ids, indent=2) + "\n")

    def env(self):
        """Exclude the operator's run-store override and select isolated config."""
        env = dict(os.environ, XDG_CONFIG_HOME=str(self.config.parent))
        env.pop("DRIVER_LAB_RUNS", None)
        return env

    def change_document(self):
        """An invented editorial edition changes bytes, not the spec's facts."""
        document = self.documents[0]
        document.write_text(
            document.read_text() + "\nEdition 2: editorial index added.\n"
        )
        self.registry["sources"][0].update(version="2", sha256=digest(document))
        self.save()

    def command(self, script, *args):
        """Run unchanged public machinery from the separate deployment root."""
        return subprocess.run(
            [sys.executable, str(SCRIPTS / script), *map(str, args)],
            cwd=self.root,
            env=self.env(),
            text=True,
            capture_output=True,
            check=False,
        )

    def prepare_reading(self):
        """Freeze a queued reader handoff; leave the actual record absent."""
        proc = self.command("sweep.py", self.campaign, "--json")
        if proc.returncode != 1:
            raise ValueError("expected queued re-verification: " + proc.stdout)
        report = json.loads(proc.stdout)
        units = [
            u
            for u in report["stopping"]["queue"]
            if u["kind"] == "re-verification" and u["state"] == "ready"
        ]
        if len(units) != 1 or units[0]["id"] not in report["stopping"]["batch"]:
            raise ValueError("expected one ready re-verification in the batch")
        unit = units[0]
        instructions = self.workspace / "instructions"
        instructions.mkdir()
        for name, source in (
            ("spec-verifier.md", "skills/spec-verifier/SKILL.md"),
            ("os-investigator.md", "skills/os-investigator/SKILL.md"),
            ("SPEC-FORMAT.md", "skills/board-expert/SPEC-FORMAT.md"),
        ):
            shutil.copyfile(ROOT / source, instructions / name)
        inputs = {
            str(p.relative_to(self.workspace)): digest(p)
            for p in sorted(self.workspace.rglob("*"))
            if p.is_file()
        }
        (self.directory / "input-hashes.json").write_text(
            json.dumps(inputs, indent=2) + "\n"
        )
        (self.directory / "queued-sweep.json").write_text(proc.stdout)
        brief = self.directory / "reader-brief.md"
        brief.write_text(
            MARKDOWN_HEADER + "\n# CR7 live tier-1 re-verification\n\n"
            f"Model: {unit['model']['name']}; version: {unit['model']['version']}.\n"
            f"Workspace: {self.workspace}\n"
            f"Spec: specs/{self.spec.name}\n\n"
            "You are a fresh spec-verifier reader. Read\n"
            "instructions/spec-verifier.md,\n"
            "instructions/os-investigator.md and instructions/SPEC-FORMAT.md.\n"
            "The input is a local-layer chip spec using the board-spec format.\n"
            "All device facts and sources are invented for this test. Their supplied\n"
            "local documents are the authorities. Use no outside knowledge\n"
            "or network.\n\n"
            "Read only this workspace and this brief. Do not read the public\n"
            "repository, campaign index, test generator, earlier records, sibling\n"
            "run artifacts or conversation. Do not run a sweep or edit any input.\n"
            "The orchestrator has mechanically checked the spec and hashes.\n\n"
            "Scope: every fact, keyed Quick-facts/1, Quick-facts/2, Quick-facts/3,\n"
            "Gotchas/1. The first three are the re-verification scope; include the\n"
            "last as the full small spec's dependency check. Numeric campaign\n"
            "sections 1 and 2 mean Quick-facts and Gotchas. There are no other\n"
            "dependencies, register maps, init sequences or bring-up-critical facts\n"
            "requiring a second reader under the chip-spec procedure.\n\n"
            "Open both sources named by resources.docs.path, relative to the spec\n"
            "directory, and verify each claim against its cited section. Report a\n"
            "verdict per fact, including discrepancies and proposed corrections.\n"
            "Do not edit the spec. Return only the complete verification record as\n"
            "your final answer, with YAML frontmatter and per-claim verdict lines.\n"
            f"Set spec to {self.ids['spec']}, spec_file to {self.spec.name},\n"
            f"and spec_sha256 to {digest(self.spec)}. Record your actual model,\n"
            "harness and date; list both source IDs, local relative paths, edition\n"
            "and SHA-256, fetch status and summary counts. Compute hashes yourself.\n"
            "No source code or long source quotations in the record.\n\n"
            "The orchestrator saves your final answer under specs/resources/ as\n"
            f"{self.ids['spec']}.verify.md, checks it and records session provenance.\n"
        )
        handoff = dict(
            state="awaiting orchestrator reader; no reading performed",
            unit=unit,
            workspace=str(self.workspace),
            brief=str(brief),
            input_hashes=str(self.directory / "input-hashes.json"),
            brief_sha256=digest(brief),
            record=str(
                self.spec.parent / "resources" / (self.ids["spec"] + ".verify.md")
            ),
            scope={"1": "Quick-facts", "2": "Gotchas"},
            limitations=[
                "Prior index readings are canned metadata, not live readers.",
                "No driver, reference implementation or hardware run.",
            ],
        )
        (self.directory / "handoff.json").write_text(
            json.dumps(handoff, indent=2) + "\n"
        )
        return handoff
