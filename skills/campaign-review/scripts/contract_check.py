#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Check a deployment and captured source/fixture outputs without executing plugins.

Exit status: 0 contract satisfied, 1 findings, 2 usage, 3 missing input/PyYAML.
Use || true if findings should not stop a shell. --json emits one object.
A valid FAIL or ERROR is a valid contract, not a successful driver test.
"""

from collections import Counter
import json
from pathlib import Path
import sys

import deployment
from cli import Parser
import index_check as check
import source_registry

# JSON booleans must be actual booleans, not integer lookalikes.
# pylint: disable=unidiomatic-typecheck

VERDICTS = {"PASS", "FAIL", "ERROR"}
AUXILIARY_GROUPS = {"trace", "capture"}
ERROR_GROUPS = {"boot", "between scenarios"}
SKILL = """---
name: campaign-contract-check
description: Check source identities and isolated fixture output contracts locally.
---
# Contract checker version 1
Run contract_check.py [--deployment MANIFEST] [--target-spec SPEC]
[--source-json JSON] [--run-dir DIRECTORY] [--json]. Requires PyYAML.
With neither output option, validate just the deployment manifest. The manifest
defaults to the deployment user setting, then the repository reference manifest.
Commands are declarations only: invoke plugins separately under their skill's
authorization rules. This command reads supplied artifacts and launches nothing.
Source JSON is a C8 identity or the pinned-file adapter's result envelope.
A run directory holds identities.json and verdicts.json, one isolated run only.
Native QEMU output and the neutral contract in INDEX-FORMAT.md are accepted.
Blocked/unknown identities and FAIL/ERROR test verdicts can satisfy the contract;
they never prove source availability or driver acceptance. JSON has version, ok,
checks and findings. Missing inputs exit 3, findings 1, usage 2, clean 0.
Use || true for nonfatal findings. No artifacts, config or source bytes are written.
"""


def read_json(path):
    """Reject ambiguous duplicate JSON fields, just as the YAML loader does."""

    def unique(pairs):
        result = {}
        for key, value in pairs:
            check.require(key not in result, "duplicate JSON field")
            result[key] = value
        return result

    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=unique)


def source_output(document):
    """Check the adapter's metadata, never return its content or private locators."""
    check.require(isinstance(document, dict), "source output must be a mapping")
    if "result" in document:
        check.mapping(document, {"ok", "result", "updated", "would_update", "findings"})
        for field in ("ok", "updated", "would_update"):
            check.require(type(document[field]) is bool, f"{field} must be boolean")
        check.strings(document["findings"])
        document = document["result"]
    check.mapping(
        document,
        {"id", "version", "sha256", "status", "checked", "provenance"},
        {"matches_pin"},
    )
    source_registry.validate_identity(document)
    if "matches_pin" in document:
        check.require(
            document["matches_pin"] is None or type(document["matches_pin"]) is bool,
            "matches_pin must be boolean or null",
        )
    return {"status": document["status"]}


def required_fields(document, fields):
    """Allow additional private run metadata but require each named field."""
    check.require(isinstance(document, dict), "expected a mapping")
    for field in fields:
        check.require(field in document, f"missing fixture field: {field}")


def fixture_identity(identity):
    """Validate neutral identities or the existing l02harness native record."""
    check.require(isinstance(identity, dict), "identities must be a mapping")
    if any(
        key in identity
        for key in (
            "fixture",
            "harness_sha256",
            "kernel_sha256",
            "image_sha256",
            "conditions",
        )
    ):
        required_fields(
            identity,
            (
                "fixture",
                "harness_sha256",
                "kernel_sha256",
                "image_sha256",
                "conditions",
            ),
        )
        required_fields(identity["fixture"], ("name", "version", "sha256"))
        check.string(identity["fixture"]["name"])
        check.string(identity["fixture"]["version"])
        check.sha(identity["fixture"]["sha256"], nullable=False)
        for field in ("harness_sha256", "kernel_sha256", "image_sha256"):
            check.sha(identity[field], nullable=False)
        check.require(
            isinstance(identity["conditions"], dict) and bool(identity["conditions"]),
            "conditions must be a nonempty mapping",
        )
        required_fields(identity["conditions"], ("scenarios",))
        scenarios = identity["conditions"]["scenarios"]
    else:
        required_fields(
            identity,
            (
                "qemu_version",
                "sha256",
                "driver",
                "accel",
                "scenarios",
                "dut_mem",
                "host_kernel",
                "python",
            ),
        )
        for field in (
            "qemu_version",
            "driver",
            "accel",
            "dut_mem",
            "host_kernel",
            "python",
        ):
            check.string(identity[field])
        check.strings(identity["scenarios"], nonempty=True)
        scenarios = identity["scenarios"]
        hashes = identity["sha256"]
        required_fields(
            hashes,
            (
                "qemu",
                "harness:l02harness.py",
                "harness:guest-init.sh",
                "kernel",
                "initramfs",
                "busybox",
            ),
        )
        for value in hashes.values():
            check.sha(value, nullable=False)
    check.strings(scenarios, nonempty=True)
    check.require(len(scenarios) == 1, "expected one scenario per isolated run")
    check.require(
        not set(scenarios) & (AUXILIARY_GROUPS | ERROR_GROUPS),
        "requested scenario uses a reserved result-group name",
    )


def verdict(value):
    """Reject malformed verdicts without leaking them into an error message."""
    check.string(value)
    check.require(value in VERDICTS, "expected PASS, FAIL or ERROR")


def result_groups(identity, results):
    """Separate the requested scenario from documented postprocessing/error groups."""
    native = "fixture" not in identity
    declared = set(
        identity["scenarios"] if native else identity["conditions"]["scenarios"]
    )
    groups = {row["scenario"]: row for row in results}
    names = set(groups)
    check.require(
        names <= declared | AUXILIARY_GROUPS | ERROR_GROUPS,
        "undeclared scenario in verdicts",
    )
    for name in names & ERROR_GROUPS:
        check.require(
            groups[name]["verdict"] == "ERROR" and not groups[name]["checks"],
            "error group must be ERROR with no completed checks",
        )
    if "boot" in names:
        check.require(
            not names & (declared | {"between scenarios"}),
            "boot error cannot accompany executed scenarios",
        )
    check.require(
        declared <= names or bool(names & ERROR_GROUPS),
        "declared scenario missing without a startup or collection error",
    )
    if "trace" in names and not declared <= names:
        check.require(
            groups["trace"]["verdict"] == "ERROR",
            "trace without an executed scenario must be ERROR",
        )
    if "capture" in names:
        check.require(
            declared <= names and (not native or "smoke" in declared),
            "capture requires an executed scenario (smoke for native QEMU)",
        )


def fixture_output(directory):
    """Validate one directory; preserve native check names and scenario errors."""
    directory = Path(directory)
    identity = read_json(directory / "identities.json")
    fixture_identity(identity)
    document = read_json(directory / "verdicts.json")
    required_fields(document, ("overall", "results"))
    verdict(document["overall"])
    results = document["results"]
    check.require(
        isinstance(results, list) and bool(results), "results must be a nonempty list"
    )
    names, counts, scenario_verdicts = set(), Counter(), set()
    for result in results:
        required_fields(result, ("scenario", "verdict", "checks"))
        check.string(result["scenario"])
        check.require(
            result["scenario"] not in names,
            "duplicate scenario: expected one isolated run",
        )
        names.add(result["scenario"])
        verdict(result["verdict"])
        scenario_verdicts.add(result["verdict"])
        checks = result["checks"]
        check.require(isinstance(checks, list), "checks must be a list")
        check.require(
            bool(checks) or result["verdict"] in {"FAIL", "ERROR"},
            "PASS scenario needs named checks",
        )
        seen, outcomes = set(), set()
        for row in checks:
            required_fields(row, ("check",))
            check.string(row["check"])
            check.require(row["check"] not in seen, "duplicate check in scenario")
            seen.add(row["check"])
            check.require(
                ("ok" in row) != ("verdict" in row),
                "check needs exactly one of ok or verdict",
            )
            if "ok" in row:
                check.require(type(row["ok"]) is bool, "check ok must be boolean")
                outcome = "PASS" if row["ok"] else "FAIL"
            else:
                verdict(row["verdict"])
                outcome = row["verdict"]
            outcomes.add(outcome)
            counts[outcome] += 1
        check.require(
            result["verdict"] != "PASS" or outcomes == {"PASS"},
            "PASS scenario contradicts check verdicts",
        )
        check.require(
            "ERROR" not in outcomes or result["verdict"] == "ERROR",
            "ERROR check needs ERROR scenario",
        )
    expected = (
        "ERROR"
        if "ERROR" in scenario_verdicts
        else "FAIL"
        if "FAIL" in scenario_verdicts
        else "PASS"
    )
    check.require(
        document["overall"] == expected, "overall contradicts scenario verdicts"
    )
    result_groups(identity, results)
    return {
        "overall": document["overall"],
        "scenarios": len(results),
        "verdicts": dict(sorted(counts.items())),
    }


def main(argv=None):
    """Check only explicit captured outputs; manifest commands are never run."""
    parser = Parser(description=__doc__, error_fields={"version": 1, "checks": {}})
    parser.add_argument("--deployment", type=Path)
    parser.add_argument("--target-spec", type=Path)
    parser.add_argument("--source-json", type=Path)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--skill", action="store_true")
    args = parser.parse_args(argv)
    if args.skill:
        print(SKILL)
        return 0
    report = {"version": 1, "ok": False, "checks": {}, "findings": []}
    code = 0
    if check.yaml is None:
        report["findings"], code = ["PyYAML is required; use uv run --with pyyaml"], 3
    else:
        operations = [
            (
                "deployment",
                lambda: {"roles": deployment.load(args.deployment, args.target_spec)},
            )
        ]
        if args.source_json:
            operations.append(
                ("source", lambda: source_output(read_json(args.source_json)))
            )
        if args.run_dir:
            operations.append(("fixture", lambda: fixture_output(args.run_dir)))
        for name, operation in operations:
            try:
                report["checks"][name] = operation()
            except OSError:
                report["findings"].append(f"{name}: cannot read required input")
                code = 3
            except (check.Invalid, ValueError, check.yaml.YAMLError) as exc:
                detail = (
                    str(exc)
                    if isinstance(exc, check.Invalid)
                    else "invalid input encoding or syntax"
                )
                report["findings"].append(f"{name}: {detail}")
                code = max(code, 1)
    report["ok"] = code == 0
    if args.json:
        print(json.dumps(report, sort_keys=True))
    else:
        print(
            ("OK" if report["ok"] else "FAIL")
            + ": "
            + json.dumps(report, sort_keys=True)
        )
    return code


if __name__ == "__main__":
    sys.exit(main())
