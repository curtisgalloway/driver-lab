#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Emit invented source metadata or a canned isolated run, optionally incomplete."""

import argparse
import copy
import json
from pathlib import Path
import uuid

HERE = Path(__file__).resolve().parent
SOURCE_FIELDS = (
    "id",
    "version",
    "sha256",
    "status",
    "checked",
    "provenance",
    "provenance.adapter",
    "provenance.version",
    "provenance.version_method",
)
FIXTURE_FIELDS = (
    "fixture",
    "fixture.name",
    "fixture.version",
    "fixture.sha256",
    "harness_sha256",
    "kernel_sha256",
    "image_sha256",
    "conditions",
    "conditions.scenarios",
)


def source():
    """Invent IDs at runtime; public files name only reference plugins."""
    return dict(
        id=uuid.uuid4().hex,
        version="1",
        sha256="a" * 64,
        status="ok",
        checked="2026-09-26",
        provenance=dict(adapter="pinned-file", version="1", version_method="test pin"),
    )


def identity():
    """Express the reduced reference run through the neutral backend contract."""
    native = json.loads((HERE / "qemu-run/identities.json").read_text())
    hashes = native["sha256"]
    return dict(
        fixture=dict(
            name="QEMU", version=native["qemu_version"], sha256=hashes["qemu"]
        ),
        harness_sha256=hashes["harness:l02harness.py"],
        kernel_sha256=hashes["kernel"],
        image_sha256=hashes["initramfs"],
        conditions={
            key: native[key]
            for key in (
                "driver",
                "accel",
                "scenarios",
                "dut_mem",
                "host_kernel",
                "python",
            )
        },
    )


def omit(document, field):
    """One stub variant per removed required provenance field."""
    result = copy.deepcopy(document)
    parts = field.split(".")
    parent = result
    for part in parts[:-1]:
        parent = parent[part]
    del parent[parts[-1]]
    return result


def write_run(directory, missing=None):
    """Write only the caller's new test directory, never a supplied existing run."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    data = identity()
    if missing:
        data = omit(data, missing)
    (directory / "identities.json").write_text(json.dumps(data) + "\n")
    verdicts = json.loads((HERE / "qemu-run/verdicts.json").read_text())
    for result in verdicts["results"]:
        for row in result["checks"]:
            row["verdict"] = "PASS" if row.pop("ok") else "FAIL"
    (directory / "verdicts.json").write_text(json.dumps(verdicts) + "\n")
    return directory


def main():
    """A source prints JSON; a backend prints a JSON run-directory locator."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--omit")
    args = parser.parse_args()
    if args.run_dir:
        print(json.dumps({"run_dir": str(write_run(args.run_dir, args.omit))}))
    else:
        data = source()
        print(json.dumps(omit(data, args.omit) if args.omit else data))


if __name__ == "__main__":
    main()
