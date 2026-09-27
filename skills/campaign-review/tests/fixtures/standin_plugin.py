# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Self-contained invented plugins; no source, hardware or reference backend access."""

import argparse
import hashlib
import json
from pathlib import Path


def main():
    """Emit captured metadata or a canned neutral run, with no reference imports."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=("source", "fixture"))
    parser.add_argument("path", type=Path)
    parser.add_argument("identity", nargs="?")
    args = parser.parse_args()
    if args.kind == "source":
        print(args.path.read_text(), end="")
        return
    if not args.identity:
        parser.error("fixture identity is required")
    args.path.mkdir(parents=True, exist_ok=False)
    checksum = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    identity = dict(
        fixture=dict(name=args.identity, version="1", sha256=checksum),
        harness_sha256=checksum,
        kernel_sha256=checksum,
        image_sha256=checksum,
        conditions=dict(scenarios=["invented"], execution="canned; no guest or driver"),
    )
    verdicts = dict(
        overall="PASS",
        results=[
            dict(
                scenario="invented",
                verdict="PASS",
                checks=[dict(check="canned metadata", verdict="PASS")],
            )
        ],
    )
    for name, value in (("identities", identity), ("verdicts", verdicts)):
        (args.path / (name + ".json")).write_text(json.dumps(value) + "\n")
    print(json.dumps({"run_dir": str(args.path)}))


if __name__ == "__main__":
    main()
