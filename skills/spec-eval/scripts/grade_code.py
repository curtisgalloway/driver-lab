#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""grade_code.py: self-test an item bank, or grade a sweep of answers against it.

    grade_code.py --bank BANK --self-test [--schema S] [--prelude P] [--jobs N]
    grade_code.py --bank BANK --raw RAW --out graded.jsonl --report report.md
                  --abstain-arms A,B|none [--prelude P] [--jobs N]

Grading compiles each answer and runs the item's unit tests with rustc; no model judges
anything. Exit status: 0 success, 1 self-test findings, 2 usage or environment error.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
# `python3 -I` leaves the script's directory off sys.path.
sys.path.insert(0, str(HERE))
import speceval  # pylint: disable=wrong-import-position

PROBE_PATH = "__eval_probe::__eval_probe_spec_gap"
OUTCOMES = ["correct", "abstain-ok", "abstain-wrong", "test-fail", "compile-error"]
PASSING = {"correct", "abstain-ok"}
# Constructs an answer could use to subvert the harness or the probe, matched with optional
# whitespace because Rust's tokenizer allows it (`macro_rules ! m`, `# ! [attr]`).
REFUSED = (
    ("macro_rules!", re.compile(r"macro_rules\s*!")),
    ("#![", re.compile(r"#\s*!\s*\[")),
    ("process::exit", re.compile(r"process\s*::\s*exit")),
    ("__eval_probe", re.compile(r"__eval_probe")),
)


def probe_module(expr: str) -> str:
    """A test module that passes only when `expr` (a Result<_, SpecGap>) is an Err(SpecGap)."""
    return ("#[cfg(test)] mod __eval_probe { use super::*; #[test] fn __eval_probe_spec_gap() "
            "{ assert!(matches!({ " + expr + " }, Err(SpecGap(_)))); } }\n")


def with_probe(source: str, item: dict) -> str:
    probe = item.get("abstain_probe") or ""
    return source + ("\n" + probe_module(probe) if probe else "")


def own_results(run) -> dict:
    return {n: s for n, s in run.results.items() if n != PROBE_PATH}


def all_own_ok(run) -> bool:
    own = own_results(run)
    return run.complete and bool(own) and all(s == "ok" for s in own.values())


# ------------------------------------------------------------------------------ self-test


def self_test_item(raw: dict, prelude_text: str) -> list[str]:
    """Return the findings for one item (empty when it passes)."""
    item = speceval.normalize(raw)
    preamble = speceval.item_preamble(item, prelude_text)
    has_probe = bool(item.get("abstain_probe"))
    findings: list[str] = []

    ref = speceval.compile_and_run_tests(with_probe(
        preamble + "\n\n" + item["reference_rust"] + "\n\n" + item["test_harness"], item))
    if not ref.compiled:
        findings.append("reference (with harness and probe) does not compile: " +
                        first_line(ref.diagnostics))
    else:
        if not all_own_ok(ref):
            failed = sorted(n for n, s in own_results(ref).items() if s != "ok")
            findings.append("reference fails test_harness" +
                            (": " + ", ".join(failed) if failed else
                             " (no complete passing run)"))
        if has_probe and ref.results.get(PROBE_PATH) == "ok":
            findings.append("abstain_probe fires on the reference: the reference abstains")

    trap = speceval.compile_and_run_tests(
        preamble + "\n\n" + item["trap_rust"] + "\n\n" + item["test_harness"])
    if not trap.compiled:
        findings.append("trap does not compile: " + first_line(trap.diagnostics))
    elif trap.timed_out:
        findings.append("trap times out: it hangs rather than fails")
    elif trap.exit_code == 0:
        findings.append("trap passes test_harness: the harness is too weak")

    stub = speceval.compile_and_run_tests(with_probe(
        preamble + "\n\n" + speceval.signature_stub(item["fn_signature"]) + "\n\n" +
        item["test_harness"], item))
    if not stub.compiled:
        findings.append("harness and probe do not compile against the published signature "
                        "(stub returning Err(SpecGap(..))): " + first_line(stub.diagnostics))
    elif has_probe and stub.results.get(PROBE_PATH) != "ok":
        findings.append("abstain_probe does not detect an abstaining answer")
    return findings


def first_line(diagnostics: str) -> str:
    for line in diagnostics.splitlines():
        if line.startswith("error"):
            return line.strip()
    return (diagnostics.strip().splitlines() or ["no diagnostics"])[0]


def run_self_test(args, document, prelude_text: str) -> int:
    try:
        schema = speceval.load_schema(args.schema)
    except (OSError, ValueError) as exc:
        print(f"grade_code: cannot read schema: {exc}", file=sys.stderr)
        return 2
    errors = speceval.bank_findings(document, schema)
    if errors:
        print("Bank does not validate:")
        for error in errors:
            print("  " + error)
        print("FAIL: schema errors; compiles skipped")
        return 1
    items = speceval.items_of(document)
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        results = list(pool.map(lambda it: self_test_item(it, prelude_text), items))
    failed = 0
    for item, findings in zip(items, results):
        if findings:
            failed += 1
            print(f"FAIL {item['id']}: " + "; ".join(findings))
        else:
            print(f"PASS {item['id']}")
    print(f"{len(items) - failed} of {len(items)} items pass")
    return 1 if failed else 0


# ------------------------------------------------------------------------------ grading


def classify(stratum: str, arm, abstain_arms: set[str], abstained: bool, test_ok: bool) -> str:
    if stratum == "out-of-spec" and arm in abstain_arms:
        return "abstain-ok" if abstained else "test-fail"
    if abstained:
        return "abstain-wrong"
    return "correct" if test_ok else "test-fail"


def grade_record(rec: dict, item: dict, prelude_text: str, abstain_arms: set[str]) -> dict:
    item = speceval.normalize(item)
    code = rec.get("rust_code") or ""
    graded = {
        "item_id": item["id"], "model": rec.get("model"), "arm": rec.get("arm"),
        "stratum": item["stratum"], "archetype": item.get("archetype"),
        "outcome": None, "test_ok": False, "abstained": False,
        "timed_out": False, "failed_tests": [],
    }
    if rec.get("abstained") and not code.strip():
        graded["abstained"] = True
        graded["outcome"] = classify(item["stratum"], rec.get("arm"), abstain_arms, True, False)
        return graded
    for needle, pattern in REFUSED:
        if pattern.search(code):
            graded["outcome"] = "compile-error"
            graded["diagnostics"] = f"refused: the answer contains {needle!r}"
            return graded
    source = (speceval.item_preamble(item, prelude_text) + "\n\n" + code + "\n\n" +
              item["test_harness"] + "\n")
    run = speceval.compile_and_run_tests(with_probe(source, item))
    graded["timed_out"] = run.timed_out
    if not run.compiled:
        graded["outcome"] = "compile-error"
        graded["diagnostics"] = run.diagnostics[:2000]
        return graded
    own = own_results(run)
    graded["failed_tests"] = sorted(n for n, s in own.items() if s != "ok")
    graded["test_ok"] = all_own_ok(run)
    graded["abstained"] = bool(rec.get("abstained")) or run.results.get(PROBE_PATH) == "ok"
    graded["outcome"] = classify(item["stratum"], rec.get("arm"), abstain_arms,
                                 graded["abstained"], graded["test_ok"])
    return graded


def read_raw(path: Path) -> list[dict]:
    files = sorted(path.glob("*.jsonl")) if path.is_dir() else [path]
    if not files:
        raise ValueError(f"{path}: no .jsonl files")
    records = []
    for file in files:
        for number, line in enumerate(file.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip():
                try:
                    records.append(json.loads(line))
                except ValueError as exc:
                    raise ValueError(f"{file}:{number}: {exc}") from exc
    return records


def table(title: str, arms: list[str], graded: list[dict], keep) -> list[str]:
    counts = {arm: [0, 0] for arm in arms}
    for g in graded:
        if keep(g):
            counts[g["arm"]][0] += 1
            counts[g["arm"]][1] += g["outcome"] in PASSING
    lines = [f"## {title}", "", "| | " + " | ".join(arms) + " |",
             "| --- |" + " --- |" * len(arms)]
    lines.append("| n | " + " | ".join(str(counts[a][0]) for a in arms) + " |")
    lines.append("| passed | " + " | ".join(str(counts[a][1]) for a in arms) + " |")
    rates = ["n/a" if counts[a][0] == 0 else f"{counts[a][1] / counts[a][0]:.0%}" for a in arms]
    lines.append("| pass rate | " + " | ".join(rates) + " |")
    return lines + [""]


def build_report(bank: str, graded: list[dict], abstain_arms: set[str]) -> str:
    scored = [g for g in graded if g["outcome"] != "unknown-item"]
    arms = sorted({str(g["arm"]) for g in scored})
    for g in scored:
        g["arm"] = str(g["arm"])
    lines = ["# spec-eval sweep report", "", f"Bank: `{Path(bank).name}`", "",
             f"Records: {len(graded)} ({len(scored)} graded, "
             f"{len(graded) - len(scored)} unknown-item)", "",
             "Abstain arms (an out-of-spec item's right answer is abstention): " +
             (", ".join(sorted(abstain_arms)) or "none"), ""]
    lines += table("Answerable from the spec: every stratum except out-of-spec", arms, scored,
                   lambda g: g["stratum"] != "out-of-spec")
    lines += table("Out-of-spec items", arms, scored, lambda g: g["stratum"] == "out-of-spec")
    lines += table("All items", arms, scored, lambda g: True)
    cells: dict = defaultdict(Counter)
    for g in scored:
        cells[(str(g["model"]), g["arm"])][g["outcome"]] += 1
    lines += ["## Per model and arm", "",
              "| model | arm | n | " + " | ".join(OUTCOMES) + " |",
              "| --- | --- | --- |" + " --- |" * len(OUTCOMES)]
    for (model, arm), counter in sorted(cells.items()):
        lines.append(f"| {model} | {arm} | {sum(counter.values())} | " +
                     " | ".join(str(counter.get(o, 0)) for o in OUTCOMES) + " |")
    if not cells:
        lines.append("| n/a | n/a | 0 |" + " n/a |" * len(OUTCOMES))
    lines += ["", "### Non-passing cells", ""]
    failing = [g for g in scored if g["outcome"] not in PASSING]
    if failing:
        lines += ["| model | arm | item | outcome |", "| --- | --- | --- | --- |"]
        for g in sorted(failing, key=lambda g: (str(g["model"]), g["arm"], g["item_id"])):
            lines.append(f"| {g['model']} | {g['arm']} | {g['item_id']} | {g['outcome']} |")
    else:
        lines.append("None.")
    return "\n".join(lines) + "\n"


def run_grading(args, document, prelude_text: str) -> int:
    items = speceval.items_of(document)
    if not args.out or not args.report:
        print("grade_code: grading needs --out and --report", file=sys.stderr)
        return 2
    has_oos = any(i.get("stratum") == "out-of-spec" for i in items)
    if args.abstain_arms is not None and not args.abstain_arms.strip():
        args.abstain_arms = None
    if args.abstain_arms is None and has_oos:
        print("grade_code: the bank has out-of-spec items; give --abstain-arms A,B "
              "(the arms in which abstaining is right), or --abstain-arms none",
              file=sys.stderr)
        return 2
    spec = args.abstain_arms or "none"
    abstain_arms = set() if spec == "none" else {a for a in spec.split(",") if a}
    try:
        records = read_raw(Path(args.raw))
    except (OSError, ValueError) as exc:
        print(f"grade_code: cannot read --raw: {exc}", file=sys.stderr)
        return 2
    for arm in sorted(abstain_arms - {r.get("arm") for r in records}):
        print(f"grade_code: warning: abstain arm {arm!r} appears in no record",
              file=sys.stderr)
    bank = {i["id"]: i for i in items}

    def grade(rec: dict) -> dict:
        item_id = rec.get("item_id", rec.get("id"))
        if item_id not in bank:
            print(f"grade_code: warning: unknown item id {item_id!r}", file=sys.stderr)
            return {"item_id": item_id, "model": rec.get("model"), "arm": rec.get("arm"),
                    "outcome": "unknown-item"}
        return grade_record(rec, bank[item_id], prelude_text, abstain_arms)

    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        graded = list(pool.map(grade, records))
    Path(args.out).write_text("".join(json.dumps(g) + "\n" for g in graded), encoding="utf-8")
    Path(args.report).write_text(build_report(args.bank, graded, abstain_arms),
                                 encoding="utf-8")
    print(f"graded {len(graded)} records: " +
          ", ".join(f"{o} {n}" for o, n in sorted(Counter(g["outcome"] for g in graded).items())))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--bank", required=True)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--schema")
    parser.add_argument("--prelude")
    parser.add_argument("--raw")
    parser.add_argument("--out")
    parser.add_argument("--report")
    parser.add_argument("--abstain-arms", default=None)
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 1)
    args = parser.parse_args(argv)
    if args.jobs < 1:
        parser.error("--jobs must be at least 1")
    if not args.self_test and not args.raw:
        parser.error("give --self-test or --raw")
    try:
        speceval.run_timeout()
    except ValueError as exc:
        print(f"grade_code: {exc}", file=sys.stderr)
        return 2
    if not speceval.have_rustc():
        print("grade_code: rustc is not installed; install a Rust toolchain", file=sys.stderr)
        return 2
    try:
        document = speceval.load_document(args.bank)
        prelude_text = speceval.read_prelude(args.prelude)
    except (OSError, ValueError) as exc:
        print(f"grade_code: {exc}", file=sys.stderr)
        return 2
    if args.self_test:
        return run_self_test(args, document, prelude_text)
    try:
        errors = speceval.bank_findings(document, speceval.load_schema(args.schema))
    except (OSError, ValueError) as exc:
        print(f"grade_code: {exc}", file=sys.stderr)
        return 2
    if errors:
        print("grade_code: the bank does not validate; run --self-test", file=sys.stderr)
        return 2
    return run_grading(args, document, prelude_text)


if __name__ == "__main__":
    sys.exit(main())
