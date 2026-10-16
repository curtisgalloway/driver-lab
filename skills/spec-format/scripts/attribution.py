# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Source copyright attribution for a cited source file (issue #101).

A files item of a repos entry may carry `attribution`: what the file's own notices, at the
pinned commit, say about who holds the copyright. It is a summary of declared notices, never a
conclusion about authorship or ownership. `scan` reads the notices; `compare` checks a recorded
attribution against that scan (`spec.py resolve` calls both); `fact_files`, `summary` and `cell`
feed the rendered views.

What the scan covers, and what it does not:

- It reads the **whole file** at the pinned commit, not only the cited lines.
- A **candidate** is a line that, after one comment leader (`//`, `#`, ` * `, `/*`, `<!--`, ...)
  and surrounding white space are removed, starts with `SPDX-FileCopyrightText:`, `Copyright`,
  `COPYRIGHT (C)` or `COPYRIGHT 2020`, `(C) 2020` or the copyright sign. Notices in running text,
  or inside a longer line, are not candidates, and BSD boilerplate such as "COPYRIGHT OWNER OR
  CONTRIBUTORS BE LIABLE" is not either.
- A candidate is **recognized** when it parses as one notice: optional years, optional symbol,
  then a holder. The holder is kept verbatim as one name: never split on "and" or commas, and a
  collective such as "The Fuchsia Authors" is never expanded.
- A notice split across lines with no holder on its first line, a notice in another form, or
  any other unparsable candidate is **not recognized**, and one such candidate makes the whole
  file `ambiguous` for a reviewer to resolve by hand.
- Nothing is inferred from git history, and an absent notice is `none-found`, not "no owner".
"""

from __future__ import annotations

import re

import speccheck

STATUSES = ("none-found", "ambiguous", "recorded")

LEADER = re.compile(r"(?:/\*+!?|\*+|//+[!/]?|#+|;+|--|<!--|%+)\s*")
TRAILER = re.compile(r"\s*(?:\*/|-->)\s*$")
CANDIDATE = re.compile(
    r"(?:SPDX-FileCopyrightText:|Copyright\b"
    r"|COPYRIGHT(?=\s*(?:\([Cc]\)|©|\d{4}))|\([Cc]\)(?=\s*\d{4})|©)"
)
SPDX_PREFIX = "SPDX-FileCopyrightText:"
WORD = re.compile(r"(?:Copyright|COPYRIGHT)\b\s*")
SYMBOL = re.compile(r"(?:\([Cc]\)|©)\s*")
YEARS = re.compile(r"\d{4}(?:\s*[-–,]\s*(?:\d{4}|present))*\s*,?\s*")
RESERVED = re.compile(r"([.,]?)\s*All [Rr]ights [Rr]eserved\.?\s*$")
EMAIL = re.compile(r"\s*<[^<>]*>\s*$")
ABBREVIATIONS = frozenset(
    "Inc. Ltd. Co. Corp. L.L.C. S.A. B.V. N.V. Pty. Jr. Sr.".split()
)


def notice_text(line: str, first: bool = False) -> str:
    """The line as the scan reads it: leader, trailer and extra white space removed."""
    if first:
        line = line.removeprefix("﻿")
    text = line.replace("\r", "").lstrip()
    match = LEADER.match(text)
    if match:
        text = text[match.end():]
    text = TRAILER.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def _holder(text: str) -> str | None:
    """The holder of one candidate notice, or None when it does not parse as a notice."""
    spdx = text.startswith(SPDX_PREFIX)
    if spdx:
        text = text[len(SPDX_PREFIX):].lstrip()
    marked = False
    for pattern in (WORD, SYMBOL, YEARS):
        match = pattern.match(text)
        if match:
            if pattern is not WORD:
                marked = True
            text = text[match.end():]
    if not spdx and not marked:
        return None
    holder = text.strip()
    reserved = RESERVED.search(holder)
    if reserved:
        holder = holder[:reserved.start()]
        words = holder.split()
        if reserved.group(1) == "." and words and words[-1] + "." in ABBREVIATIONS:
            holder += "."
    holder = EMAIL.sub("", holder.strip())
    holder = re.sub(r",\s*$", "", holder).strip()
    words = holder.split()
    if holder.endswith(".") and not (words and words[-1] in ABBREVIATIONS):
        holder = holder[:-1]
    holder = holder.strip()
    return holder if any(c.isalpha() for c in holder) else None


def scan(lines) -> dict:
    """Scan the whole file: status, recognized names, evidence for every candidate, line count."""
    evidence, names, ambiguous = [], [], False
    for number, line in enumerate(lines, 1):
        text = notice_text(line, first=number == 1)
        if not CANDIDATE.match(text):
            continue
        evidence.append({"line": number, "text": text})
        holder = _holder(text)
        if holder is None:
            ambiguous = True
        elif holder not in names:
            names.append(holder)
    status = "none-found" if not evidence else "ambiguous" if ambiguous else "recorded"
    return {"status": status, "names": names, "evidence": evidence, "lines": len(lines)}


def _shown(value) -> str:
    return f"'{value}'"


def compare(recorded: dict, scanned: dict, lines) -> list[str]:
    """Messages where the recorded attribution disagrees with the scan; empty means agreement."""
    if recorded["status"] != scanned["status"]:
        return [f"attribution status '{recorded['status']}' but the source scan finds "
                f"'{scanned['status']}'"]
    status = recorded["status"]
    have = recorded.get("evidence", [])
    want = scanned["evidence"]
    messages = []
    if status == "recorded":
        for i in range(max(len(have), len(want))):
            if i >= len(want):
                messages.append(f"evidence line {have[i]['line']}: recorded "
                                f"{_shown(have[i]['text'])}, the source scan finds no such notice")
            elif i >= len(have):
                messages.append(f"missing evidence line {want[i]['line']}")
            elif have[i]["line"] != want[i]["line"]:
                messages.append(f"evidence line {have[i]['line']}: the source scan finds the "
                                f"next notice at line {want[i]['line']}")
            elif have[i]["text"] != want[i]["text"]:
                messages.append(f"evidence line {have[i]['line']}: recorded "
                                f"{_shown(have[i]['text'])}, source has {_shown(want[i]['text'])}")
            else:
                continue
            break
        names = recorded.get("names", [])
        if names != scanned["names"]:
            messages.append(f"names differ: recorded {names}, scan finds {scanned['names']}")
    elif status == "ambiguous":
        for item in want:
            if item not in have:
                messages.append(f"missing evidence line {item['line']}")
        for item in have:
            if item in want:
                continue
            number = item["line"]
            if not 1 <= number <= len(lines):
                messages.append(f"evidence line {number} does not exist "
                                f"(the file has {len(lines)} lines)")
                continue
            actual = notice_text(lines[number - 1], first=number == 1)
            if item["text"] != actual:
                messages.append(f"evidence line {number}: recorded {_shown(item['text'])}, "
                                f"source has {_shown(actual)}")
        for name in recorded.get("names", []):
            if not any(name in item["text"] for item in have):
                messages.append(f"name {_shown(name)} occurs in no evidence text")
    return messages


def fact_files(file, data: dict) -> list[tuple[str, str, dict | None]]:
    """(repo name, path, attribution or None) for each file a fact's own support cites.

    A contrary reading's support (`conflicts`) is not the fact's support, and a directory
    citation records a search, not a text with a notice. Inference premises are not followed
    here; a later option can add them.
    """
    seen, result = set(), []
    for anchor, at in speccheck.anchors(data, ()):
        if "conflicts" in at or anchor["path"].endswith("/"):
            continue
        key = (anchor["repo"], anchor["path"])
        if key in seen:
            continue
        seen.add(key)
        entry = file.repos.get(anchor["repo"], ({},))[0]
        listed = [i for i in entry.get("files", []) if i["path"] == anchor["path"]]
        result.append((*key, listed[0].get("attribution") if listed else None))
    return result


def summary(items) -> str | None:
    """One line over the files a fact cites, or None when no file carries attribution."""
    records = [attribution for _, _, attribution in items]
    if not any(records):
        return None
    names = []
    for attribution in records:
        if attribution and attribution["status"] in ("recorded", "ambiguous"):
            names.extend(n for n in attribution.get("names", []) if n not in names)
    counts = (
        ("unrecorded", sum(a is None for a in records)),
        ("no notice found", sum(bool(a) and a["status"] == "none-found" for a in records)),
        ("ambiguous", sum(bool(a) and a["status"] == "ambiguous" for a in records)),
    )
    parts = [f"{k} {label}" for label, k in counts if k]
    pieces = ["; ".join(names)] if names else []
    if parts:
        pieces.append("attribution incomplete (" + ", ".join(parts) + ")")
    return "; ".join(pieces)


def cell(attribution) -> str:
    """The files-table cell for one files item's attribution."""
    if not attribution:
        return ""
    status = attribution["status"]
    names = "; ".join(attribution.get("names", []))
    if status == "none-found":
        return "no notice found"
    return f"{status}: {names}" if names else status
