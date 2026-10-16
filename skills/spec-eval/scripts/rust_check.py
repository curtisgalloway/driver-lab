#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""rust_check.py: compile an answer against an item's preamble, or export the preambles.

    rust_check.py --export-preambles BANK -o OUT [--prelude P]
    rust_check.py ITEM_ID [--code STR | --file PATH] [--preambles PATH]

The export holds only the preamble, signature, tier and prelude flag of each item, so the
file can be handed to a contestant without the reference, the harness or the spec facts.
Exit status: 0 compiled (or export written), 1 compile error, 2 usage or environment error.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# `python3 -I` leaves the script's directory off sys.path.
sys.path.insert(0, str(HERE))
import speceval  # pylint: disable=wrong-import-position


def export_preambles(bank: str, out: str, prelude: str | None, schema: str | None) -> int:
    try:
        document = speceval.load_document(bank)
        prelude_text = speceval.read_prelude(prelude)
        errors = speceval.bank_findings(document, speceval.load_schema(schema))
    except (OSError, ValueError) as exc:
        print(f"rust_check: {exc}", file=sys.stderr)
        return 2
    if errors:
        print("rust_check: the bank does not validate; nothing exported:", file=sys.stderr)
        for error in errors:
            print("  " + error, file=sys.stderr)
        return 1
    items = speceval.items_of(document)
    exported = {}
    for raw in items:
        item = speceval.normalize(raw)
        exported[item["id"]] = {
            "preamble": speceval.item_preamble(item, prelude_text),
            "signature": item["fn_signature"],
            "tier": item["tier"],
            "use_hw_prelude": item["use_hw_prelude"],
        }
    Path(out).write_text(json.dumps(exported, indent=2) + "\n", encoding="utf-8")
    return 0


def check_code(args: argparse.Namespace) -> int:
    path = args.preambles or os.environ.get("SPEC_EVAL_PREAMBLES") or "code_preambles.json"
    try:
        table = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"rust_check: cannot read preambles {path}: {exc}", file=sys.stderr)
        return 2
    entry = table.get(args.item_id) if isinstance(table, dict) else None
    if not isinstance(table, dict):
        print(f"rust_check: preambles file {path} is not a JSON object", file=sys.stderr)
        return 2
    if not isinstance(entry, dict) or "preamble" not in entry:
        print(f"rust_check: unknown item id {args.item_id!r}", file=sys.stderr)
        return 2
    if args.code is not None:
        code = args.code
    elif args.file is not None:
        try:
            code = Path(args.file).read_text(encoding="utf-8")
        except OSError as exc:
            print(f"rust_check: {exc}", file=sys.stderr)
            return 2
    else:
        code = sys.stdin.read()
    if not speceval.have_rustc():
        print("rust_check: rustc is not installed", file=sys.stderr)
        return 2
    ok, diagnostics = speceval.compile_lib(entry["preamble"] + "\n\n" + code)
    if ok:
        print("COMPILE_OK")
        return 0
    print("COMPILE_ERROR")
    print(diagnostics)
    return 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("item_id", nargs="?")
    parser.add_argument("--export-preambles", metavar="BANK")
    parser.add_argument("-o", "--output")
    parser.add_argument("--prelude")
    parser.add_argument("--schema")
    parser.add_argument("--code")
    parser.add_argument("--file")
    parser.add_argument("--preambles")
    args = parser.parse_args(argv)
    if args.export_preambles:
        if not args.output:
            parser.error("--export-preambles needs -o OUT")
        return export_preambles(args.export_preambles, args.output, args.prelude,
                                args.schema)
    if not args.item_id:
        parser.error("give an ITEM_ID or --export-preambles")
    return check_code(args)


if __name__ == "__main__":
    sys.exit(main())
