#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Check source licenses against a spec root's accepts list, before citing a source.

    license_gate.py --root DIR [LICENSE ...]
    license_gate.py --root DIR --facts FILE.facts.yaml

Prints the root's name, license and accepts list, then one line per license given:
``accepted: <expression>`` or ``refused: <expression> (<reason>)``.  A license is an SPDX
expression (``MIT``, ``GPL-2.0-only OR MIT``); quote it.  The rule is the one
``spec.py check`` applies to a finished spec: ``A OR B`` is accepted when either
side is, ``A AND B`` only when both are, ``X WITH <exception>`` when ``X`` is, and
``GPL-2.0`` means ``GPL-2.0-only``.  This script runs earlier, so a source can be refused
before anyone reads it for evidence.

A format 2 marker is required; ``accepts: []`` accepts nothing. Invalid markers fail
before any license expression can be accepted.

``--facts`` delegates to format 2's hash-pinned ``spec.py check FILE --root DIR
--require-license``. It checks the structured citations and every declared repository entry.
The expression-only preflight remains available before reading source evidence.

Needs sibling spec-format scripts and their hash-pinned requirements, plus board-expert's
shared ``spdx.py`` parser.

Exit status: 0 every license accepted (or none given), 1 a license refused or an invalid
format 2 marker, 2 usage error (not a spec root), 3 missing format 2 dependency or schema.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def load_tools():
    """Load the format 2 API and its shared SPDX parser, with pinned dependencies."""
    path = str(Path(__file__).resolve().parents[2] / "spec-format" / "scripts")
    if path not in sys.path:
        sys.path.insert(0, path)
    try:
        import spec
        problems = spec.check_dependencies()
        if problems:
            raise spec.Precondition("; ".join(problems))
        import speccheck
        return spec, speccheck, speccheck.load_spdx()
    except ImportError as exc:
        print(f"missing precondition: {exc}", file=sys.stderr)
        return None
    except spec.Precondition as exc:
        print(f"missing precondition: {exc}", file=sys.stderr)
        return None
    except speccheck.PreconditionError as exc:
        print(f"missing precondition: {exc}", file=sys.stderr)
        return None


def read_marker(root: str, api, checker_module, spdx):
    """Use the same strict loader, schema and SPDX policy as spec.py check.

    Read only the marker: this preflight runs before source evidence is selected.
    The finished facts file still needs the complete semantic and citation gate.
    """
    path = Path(root)
    if not (path / "board-specs.yaml").is_file():
        raise api.Usage(f"--root {root}: no board-specs.yaml (not a spec root)")
    checker = checker_module.Checker(api, spdx)
    marker_root = checker_module.Root(given=path, real=path.resolve(), context=False, order=0)
    checker.read_marker(marker_root, api.load_schemas())
    return marker_root, checker.findings


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", metavar="DIR", required=True,
                    help="the target spec root (a directory with board-specs.yaml)")
    ap.add_argument("licenses", nargs="*", metavar="LICENSE",
                    help="an SPDX expression to check (quote it)")
    ap.add_argument("--facts", type=Path, help="check a format 2 facts file against this target root")
    args = ap.parse_args(argv)

    if args.facts is not None:
        if args.licenses:
            ap.error("--facts checks file citations; do not also give license expressions")
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "spec-format" / "scripts"))
        import spec

        return spec.main(["check", str(args.facts), "--root", args.root, "--require-license"])

    tools = load_tools()
    if tools is None:
        return 3
    api, checker_module, spdx = tools
    try:
        root, found = read_marker(args.root, api, checker_module, spdx)
    except api.Usage as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except api.Precondition as exc:
        print(f"missing precondition: {exc}", file=sys.stderr)
        return 3
    marker = root.marker.data if root.marker is not None else {}
    name = marker.get("name", "(unnamed)")
    print(f"root: {args.root} ({name})")
    print(f"license: {marker.get('license', '(none declared)')}")
    for finding in found:
        print(finding)
    if any(f.level == "error" for f in found) or root.accepts is None:
        print("refused: invalid format 2 root marker; no source may be cited through it")
        return 1
    accepts = marker["accepts"]
    listed = ", ".join(accepts) or "none"
    print(f"accepts: {listed}")

    status = 0
    for expr in args.licenses:
        try:
            ok, shown = spdx.check(expr, accepts)
        except spdx.SpdxError as exc:
            print(f"refused: {expr} (not an SPDX expression: {exc}; root {name} accepts: "
                  f"{listed})")
            status = 1
            continue
        if ok:
            print(f"accepted: {shown}")
        else:
            print(f"refused: {shown} (not accepted by root {name}; accepts: {listed})")
            status = 1
    return status


if __name__ == "__main__":
    sys.exit(main())
