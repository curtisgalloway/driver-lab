#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Hash opaque pinned files; optionally update their registry observations.

Exit status: 0 matched, 1 drift/findings, 2 usage, 3 missing precondition.
Use || true when findings should not stop a shell pipeline. --json is one object.
"""

import argparse
import datetime
import importlib.util
import json
from pathlib import Path
import sys

import index_check as check
import source_registry

# Named formats avoid nested quote conventions and work before Python 3.12.
# pylint: disable=consider-using-f-string

ROOT = Path(__file__).resolve().parents[3]
SKILL = """---
name: pinned-file-adapter
description: Hash a local source without returning its content.
---
# Pinned-file adapter version 1
Run pinned_file_adapter.py REGISTRY ID [--root REPOSITORY] [--run-store STORE]
[--json] [--write [--dry-run]]. With no --run-store, use run-store.py's config.
Only files named relative to repository or run_store are opened. Symlink escapes
are blocked. A version is operator-declared, never guessed from content. Drift
does not adopt an edition or replace expected_sha256. --write updates observed
sha256/status/date/provenance and discards obsolete hash-bound change maps.
No file: unknown; missing/unreadable file: blocked. No content is printed.
Exits: 0 matched, 1 drift/findings, 2 usage, 3 missing precondition. Use || true
if negative findings should not terminate a shell. JSON is one object.
"""


def module_at(name, path):
    """Load an existing method helper by its explicit path."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def inspect(source, root, run_store=None):
    """Return a C8 identity and pin comparison, never source content."""
    result = {key: source[key] for key in ("id", "version")}
    result.update(
        sha256=None,
        status="unknown",
        checked=datetime.date.today().isoformat(),
        provenance={
            "adapter": "pinned-file",
            "version": "1",
            "version_method": "operator-declared registry version",
        },
        matches_pin=None,
    )
    location = source["file"]
    if location is None:
        return result
    if location["root"] == "run_store" and run_store is None:
        run_store, _ = module_at(
            "run_store", ROOT / "utilities/run-store.py"
        ).run_store()
    base = root if location["root"] == "repository" else run_store
    if base is None:
        result["status"] = "blocked"
        return result
    base = Path(base).resolve()
    path = (base / location["path"]).resolve()
    if not path.is_relative_to(base):
        result["status"] = "blocked"
        return result
    try:
        pin = module_at("corpus_check", ROOT / "evals/enc28j60/corpus_check.py")
        comparison = pin.check_blob(path.read_bytes(), source["expected_sha256"])
    except OSError:
        result["status"] = "blocked"
    else:
        result.update(
            sha256=comparison["actual"],
            status="ok",
            matches_pin=(comparison["status"] == "ok")
            if source["expected_sha256"] is not None
            else None,
        )
    return result


def main(argv=None):
    """Run a local adapter observation and optional explicit registry write."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("registry", nargs="?", type=Path)
    parser.add_argument("id", nargs="?")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--run-store", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skill", action="store_true")
    args = parser.parse_args(argv)
    if args.skill:
        print(SKILL)
        return 0
    if args.registry is None or args.id is None:
        parser.error("registry and source ID are required")
    result, findings, code, updated = None, [], 0, False
    if check.yaml is None:
        findings, code = ["PyYAML is required; use uv run --with pyyaml"], 3
    else:
        try:
            registry = check.read_yaml(args.registry)
            source_registry.validate(registry)
            sources = {s["id"]: s for s in registry["sources"]}
            check.require(args.id in sources, "source ID is not registered")
            source = sources[args.id]
            result = inspect(source, args.root, args.run_store)
            code = (
                3
                if result["status"] != "ok"
                else 1
                if result["matches_pin"] is False
                else 0
            )
            if args.write:
                if result["sha256"] != source["sha256"]:
                    source.pop("changes", None)
                for key in ("sha256", "status", "checked", "provenance"):
                    source[key] = result[key]
                source_registry.validate(registry)
                if not args.dry_run:
                    header = (
                        "# SPDX-FileCopyrightText: 2026 contributors\n"
                        "# SPDX-License-Identifier: Apache-2.0\n"
                    )
                    args.registry.write_text(
                        header + check.yaml.safe_dump(registry, sort_keys=False),
                        encoding="utf-8",
                    )
                    updated = True
        except OSError:
            findings, code = ["Cannot read or write a required file"], 3
        except (check.Invalid, check.yaml.YAMLError, UnicodeError) as exc:
            findings, code = [str(exc)], 1
    payload = dict(
        ok=code == 0,
        result=result,
        updated=updated,
        would_update=bool(args.write and args.dry_run),
        findings=findings,
    )
    if args.json:
        print(json.dumps(payload))
    elif result:
        print(
            (
                "{id}: {status}, sha256={sha256}, matches_pin={matches_pin}, "
                "updated={updated}"
            ).format(**result, updated=updated)
        )
    else:
        print("\n".join(findings))
    return code


if __name__ == "__main__":
    sys.exit(main())
