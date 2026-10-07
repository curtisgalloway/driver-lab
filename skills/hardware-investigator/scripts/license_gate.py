#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Check source licenses against a spec root's accepts list, before citing a source.

    license_gate.py --root DIR [LICENSE ...]

Prints the root's name, license and accepts list, then one line per license given:
``accepted: <expression>`` or ``refused: <expression> (<reason>)``.  A license is an SPDX
expression (``MIT``, ``GPL-2.0-only OR MIT``); quote it.  The rule is the one
``anchor_check.py --root`` applies to a finished spec: ``A OR B`` is accepted when either
side is, ``A AND B`` only when both are, ``X WITH <exception>`` when ``X`` is, and
``GPL-2.0`` means ``GPL-2.0-only``.  This script runs earlier, so a source can be refused
before anyone reads it for evidence.

A root with no ``accepts:`` refuses everything; ``accepts: []`` accepts nothing.

Needs board-expert's scripts (``spdx.py``, ``spec_check.py``) beside this skill's directory.
Stdlib only.

Exit status: 0 every license accepted (or none given), 1 a license refused, the root
declares no accepts list, or its marker has an invalid license: or accepts: entry, 2 usage error (not a spec root, unreadable marker, board-expert
missing).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def load_tools():
    """Import board-expert's spdx and spec_check, which sit beside this skill."""
    path = str(Path(__file__).resolve().parent.parent.parent / "board-expert" / "scripts")
    if path not in sys.path:
        sys.path.insert(0, path)
    try:
        import spdx  # noqa: PLC0415
        import spec_check  # noqa: PLC0415
    except ImportError:
        return None
    return spdx, spec_check


def read_marker(root: str, spec_check) -> dict:
    marker_path = Path(root) / "board-specs.yaml"
    if not marker_path.is_file():
        raise SystemExit(f"error: --root {root}: no board-specs.yaml (not a spec root)")
    try:
        marker = spec_check.load_yaml(marker_path.read_text(), spec_check.pyyaml_available())
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"error: --root {root}: cannot parse board-specs.yaml: {exc}")
    if not isinstance(marker, dict):
        raise SystemExit(f"error: --root {root}: board-specs.yaml is not a mapping")
    return marker


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", metavar="DIR", required=True,
                    help="the target spec root (a directory with board-specs.yaml)")
    ap.add_argument("licenses", nargs="*", metavar="LICENSE",
                    help="an SPDX expression to check (quote it)")
    args = ap.parse_args(argv)

    tools = load_tools()
    if tools is None:
        print("error: board-expert's spdx.py and spec_check.py were not found beside this "
              "skill", file=sys.stderr)
        return 2
    spdx, spec_check = tools
    try:
        marker = read_marker(args.root, spec_check)
    except SystemExit as exc:
        print(exc.code, file=sys.stderr)
        return 2

    found: list = []
    accepts = spec_check.check_root_license(marker, args.root, False, found)
    name = marker.get("name", "(unnamed)")
    print(f"root: {args.root} ({name})")
    print(f"license: {marker.get('license', '(none declared)')}")
    marker_errors = False
    for f in found:
        if f.level == "error":
            print(f"error: {f.message}")
            marker_errors = True
    if accepts is None:
        print("accepts: (none declared)")
        print("refused: this root declares no accepts: list, so no source may be cited "
              f"through it (root {name})")
        return 1
    listed = ", ".join(accepts) or "none"
    print(f"accepts: {listed}")

    status = 1 if marker_errors else 0
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
