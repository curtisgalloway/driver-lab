#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Refuse a clean-room mention outside driver-lab's frozen archive.

The license split (docs/LICENSE-SPLIT.md, requirement LS-R20) made driver-lab the open side:
the clean-room skills, their design text and their instructions moved to a separate repository,
and driver-lab mentions that method at most once, in one README line pointing to it. Everything
written before the split stays as a frozen archive. This check keeps the rule from eroding: a
tracked file outside the allowlist that names a clean-room term fails it.

Terms (case-insensitive; TERMS below):

  * clean-room, cleanroom, clean room (and every cleanroom-* skill or script name)
  * os-investigator (the clean-room investigator's name before the split)
  * "the wall", "licensing wall"
  * "research subagent"
  * "dirty side", "clean side"
  * leak_scan, sandbox_audit, session_audit (scripts of the moved skills)
  * encumbered, attractant, provenance ledger, transfer review (the method's own vocabulary)

Allowlist (ARCHIVE_DIRS, ARCHIVE_FILES below): the frozen archive the design lists, the license-split
design and plan (they describe the split), the campaign-review fixture copied from the frozen CR5
deployment, three history records, and this checker with its tests. README.md may carry one
matching line, the pointer, which must name cleanroom-skills; any other fails. evidence/LS8.md justifies each entry.

Scope is tracked files only. Exit 0 clean / 1 findings / 2 usage or environment error.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

TERMS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (name, re.compile(pattern, re.IGNORECASE))
    for name, pattern in (
        ("clean-room", r"clean[-_ ]?room"),
        ("os-investigator", r"\bos-investigator\b"),
        ("the wall", r"\bthe wall\b"),
        ("licensing wall", r"\blicensing wall\b"),
        ("research subagent", r"\bresearch subagent\b"),
        ("dirty/clean side", r"\b(?:dirty|clean)[- ]side\b"),
        ("moved script", r"\b(?:leak_scan|sandbox_audit|session_audit)\b"),
        ("method term", r"\b(?:encumbered|attractants?|provenance ledger|transfer review)\b"),
    )
)

# The frozen archive (LS-R20): kept as history, with a header pointing to the new home.
ARCHIVE_DIRS = ("evals/", "evidence/", "notebook/", "history/")
ARCHIVE_FILES = frozenset(
    {
        # Frozen archive documents named by LS-R20.
        "RECONSTRUCTION.md",
        "QEMU-DIFFERENTIAL.md",
        "EVAL-PLAN.md",
        "VALIDATION-PROPOSAL.md",
        "VALIDATION-REVIEW.md",
        "IMPLEMENTATION-PLAN.md",
        "DEFERRED-PLAN.md",
        # The design and plan of the split itself.
        "docs/LICENSE-SPLIT.md",
        "docs/LICENSE-SPLIT-PLAN.md",
        # A copy of the frozen CR5 deployment manifest, pinned by test_sweep.py (LS7).
        "skills/campaign-review/tests/fixtures/deployment-cr5.yaml",
        # History records: the process log, the 2026-09-25 move, the project timeline.
        "PROCESS-NOTES.md",
        "TRANSITION.md",
        "docs/STORY.md",
        # This checker names the terms it looks for; its tests plant them.
        "utilities/check-open-side.py",
        "utilities/tests/test_check_open_side.py",
    }
)
POINTER_FILE = "README.md"
POINTER_LINES = 1
POINTER_TARGET = "cleanroom-skills"
SKIP_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".pdf", ".ico", ".zip", ".gz", ".stl")


def allowlisted(path: str) -> bool:
    return path in ARCHIVE_FILES or path.startswith(ARCHIVE_DIRS)


def tracked_files(root: str) -> list[str]:
    out = subprocess.run(
        ["git", "-C", root, "ls-files", "-z"], capture_output=True, text=True, check=True
    ).stdout
    return [p for p in out.split("\0") if p and not p.endswith(SKIP_SUFFIXES)]


def matching_lines(text: str) -> list[tuple[int, str, str]]:
    """(line number, term name, line) for each line naming a term; one entry per line."""
    hits = []
    for n, line in enumerate(text.splitlines(), 1):
        for name, pattern in TERMS:
            if pattern.search(line):
                hits.append((n, name, line.strip()))
                break
    return hits


def scan(root: str, paths: list[str]) -> list[tuple[str, int, str, str]]:
    findings = []
    for path in paths:
        if allowlisted(path):
            continue
        try:
            with open(os.path.join(root, path), encoding="utf-8", errors="strict") as fh:
                text = fh.read()
        except (UnicodeDecodeError, OSError):
            continue  # binary or unreadable: not prose this check can judge
        hits = matching_lines(text)
        if path == POINTER_FILE:
            pointers = [h for h in hits if POINTER_TARGET in h[2]][:POINTER_LINES]
            hits = [h for h in hits if h not in pointers]
        findings.extend((path, n, name, line) for n, name, line in hits)
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--root", default=".", help="repository to check (default: the current directory)"
    )
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 0 if exc.code == 0 else 2

    try:
        paths = tracked_files(args.root)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"check-open-side: cannot list tracked files in {args.root}: {exc}", file=sys.stderr)
        return 2

    findings = scan(args.root, paths)
    for path, n, name, line in findings:
        print(f"{path}:{n}: [{name}] {line[:160]}")
    if findings:
        print(
            f"FAIL: {len(findings)} clean-room mention(s) outside the frozen archive "
            "(see utilities/check-open-side.py for the allowlist)",
            file=sys.stderr,
        )
        return 1
    print(f"OK: {len(paths)} tracked files, no clean-room mention outside the allowlist")
    return 0


if __name__ == "__main__":
    sys.exit(main())
