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
- A **line-start candidate** is a line that, after one comment leader (`//`, `#`, ` * `, `/*`,
  `<!--`, `@`, `!`, ...) and surrounding white space are removed, starts with
  `SPDX-FileCopyrightText:`, `Copyright`, the word `copyright` in any case followed by `(C)`, the
  copyright sign or a year, `(C)` followed by a year or the word, or the copyright sign. BSD
  boilerplate such as "COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE" or "retain the above
  copyright" is not a candidate.
- A **mid-line candidate** is any other line that contains the word `copyright` followed by
  `(C)`, the copyright sign or a year, or `(C)`/the sign followed by the word or a year ("Portions
  Copyright (C) 2001 ..."). It is never recognized, so the file is `ambiguous` and a human reads
  it: a notice must not silently become `none-found`.
- A line-start candidate is **recognized** when it parses as one notice: `Copyright`, `(C)` and
  years in the usual orders (also `(C) Copyright <holder> <years>`), a holder, and no template
  placeholder. A leading `by` and a trailing "All rights reserved" are dropped, and so is a
  trailing `<address>` that contains `@`. The holder is kept verbatim as one name: never split on
  "and" or commas, and a collective such as "The Fuchsia Authors" is never expanded.
- A notice split across lines with no holder on its first line, a notice in another form, a
  placeholder such as `<name of author>`, or any other unparsable candidate is **not
  recognized**, and one such candidate makes the whole file `ambiguous` for a reviewer to resolve
  by hand. An ambiguous record's `names` stay a reviewer's reading that `compare` bounds (they
  must cover every recognized name and occur, as whole words, in the evidence read as one text)
  but cannot prove.
- Notices inside embedded license text (the GPL's own "Copyright (C) 1989, 1991 Free Software
  Foundation, Inc.") count as the file's notices. A `Copyright` identifier in code makes the file
  `ambiguous` (it fails safe).
- Nothing is inferred from git history, and an absent notice is `none-found`, not "no owner".
"""

from __future__ import annotations

import re

import speccheck

STATUSES = ("none-found", "ambiguous", "recorded")
EXTRA_REACH = 3  # a hand-added evidence line lies this close after a scanned candidate

LEADER = re.compile(r"(?:/\*+!?|\*+|//+[!/]?|#+|;+|--|<!--|%+|@+|!+)\s*")
TRAILER = re.compile(r"\s*(?:\*/|-->)\s*$")
CANDIDATE = re.compile(
    r"(?:SPDX-FileCopyrightText:|Copyright\b"
    r"|(?i:copyright)(?=\s*(?:\([Cc]\)|©|\d{4}))"
    r"|\([Cc]\)(?=\s*(?:\d{4}|(?i:copyright)\b))|©)"
)
MIDLINE = re.compile(
    r"\bcopyright\b\s*(?:\(c\)|©|\d{4})|(?<!\w)(?:\(c\)|©)\s*(?:copyright\b|\d{4})",
    re.IGNORECASE,
)
SPDX_PREFIX = "SPDX-FileCopyrightText:"
WORD = re.compile(r"copyright\b\s*", re.IGNORECASE)
SYMBOL = re.compile(r"(?:\([Cc]\)|©)\s*")
YEAR_LIST = (r"\d{4}(?:\s*[-–]\s*(?:\d{4}|\d{2}(?!\d)|present)"
             r"|\s*,\s*(?:\d{4}|present))*")
YEARS = re.compile(YEAR_LIST + r"\s*,?\s*")
TRAILING_YEARS = re.compile(r"\s*,?\s*" + YEAR_LIST + r"\.?$")
BY = re.compile(r"by\s+", re.IGNORECASE)
RESERVED = re.compile(r"([.,]?)\s*All [Rr]ights [Rr]eserved\.?\s*$")
EMAIL = re.compile(r"\s*<[^<>@]*@[^<>]*>\s*$")
YEARS_ONLY = re.compile(r"[\d\s,\-–]*(?:present)?[\d\s,\-–]*$")
ABBREVIATIONS = frozenset(
    "Inc. Ltd. Co. Corp. L.L.C. S.A. B.V. N.V. Pty. Jr. Sr.".split()
)


def notice_text(line: str, first: bool = False) -> str:
    """The line as the scan reads it: leader, trailer and extra white space removed."""
    if first:
        line = line.removeprefix("\ufeff")
    text = line.replace("\r", "").lstrip()
    match = LEADER.match(text)
    if match:
        text = text[match.end():]
    text = TRAILER.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def _holder(text: str) -> str | None:
    """The holder of one line-start candidate, or None when it does not parse as a notice."""
    spdx = text.startswith(SPDX_PREFIX)
    if spdx:
        text = text[len(SPDX_PREFIX):].lstrip()
    marked = False
    word_first = False
    match = WORD.match(text)
    if match:
        word_first = True
        text = text[match.end():]
    symbol = SYMBOL.match(text)
    if symbol:
        marked = True
        text = text[symbol.end():]
        if not word_first:
            match = WORD.match(text)
            if match:
                text = text[match.end():]
    years = YEARS.match(text)
    if years:
        marked = True
        text = text[years.end():]
    if not spdx and not marked:
        return None
    holder = BY.sub("", text.strip(), count=1) if years else text.strip()
    reserved = RESERVED.search(holder)
    if reserved:
        holder = holder[:reserved.start()]
        words = holder.split()
        if reserved.group(1) == "." and words and words[-1] + "." in ABBREVIATIONS:
            holder += "."
    holder = re.sub(r">\.$", ">", holder.strip())
    holder = EMAIL.sub("", holder)
    trailing = TRAILING_YEARS.search(holder)
    if trailing:
        holder = holder[:trailing.start()]
    holder = re.sub(r",\s*$", "", holder).strip()
    words = holder.split()
    if holder.endswith(".") and not (words and words[-1] in ABBREVIATIONS):
        holder = holder[:-1]
    holder = holder.strip()
    if "<" in holder or ">" in holder or holder.lower() == "by":
        return None
    return holder if any(c.isalpha() for c in holder) else None


def scan(lines) -> dict:
    """Scan the whole file: status, recognized names, evidence for every candidate, line count."""
    evidence, names, ambiguous = [], [], False
    for number, line in enumerate(lines, 1):
        text = notice_text(line, first=number == 1)
        if CANDIDATE.match(text):
            holder = _holder(text)
        elif MIDLINE.search(text):
            holder = None
        else:
            continue
        evidence.append({"line": number, "text": text})
        if holder is None:
            ambiguous = True
        elif holder not in names:
            names.append(holder)
    status = "none-found" if not evidence else "ambiguous" if ambiguous else "recorded"
    return {"status": status, "names": names, "evidence": evidence, "lines": len(lines)}


def record(scanned: dict) -> dict:
    """The scan as a schema-shaped `attribution` mapping: empty lists and `lines` left out."""
    result = {"status": scanned["status"]}
    for key in ("names", "evidence"):
        if scanned[key]:
            result[key] = scanned[key]
    return result


def _shown(value) -> str:
    return f"'{value}'"


def _compare_recorded(recorded, scanned):
    have, want = recorded.get("evidence", []), scanned["evidence"]
    messages = []
    for i in range(max(len(have), len(want))):
        if i >= len(want):
            messages.append(f"evidence line {have[i]['line']}: recorded "
                            f"{_shown(have[i]['text'])}, the source scan finds no such notice")
        elif i >= len(have) or have[i]["line"] > want[i]["line"]:
            messages.append(f"missing evidence line {want[i]['line']}")
        elif have[i]["line"] < want[i]["line"]:
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
    return messages


def _occurs(name: str, text: str) -> bool:
    """Whether NAME occurs in TEXT bounded by non-word characters or the text's ends."""
    return re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", text) is not None


def _compare_ambiguous(recorded, scanned, lines):
    have, want = recorded.get("evidence", []), scanned["evidence"]
    messages = []
    previous = 0
    for item in have:
        if item["line"] <= previous:
            messages.append(f"evidence line {item['line']}: lines must increase, "
                            f"without repeats")
        previous = max(previous, item["line"])
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
        elif not any(c["line"] < number <= c["line"] + EXTRA_REACH for c in want):
            messages.append(f"evidence line {number}: not within {EXTRA_REACH} lines after a "
                            f"notice the source scan finds")
    names = recorded.get("names", [])
    for name in scanned["names"]:
        if not any(_occurs(name, recorded_name) for recorded_name in names):
            messages.append(f"names omit {_shown(name)}, which the source scan recognizes")
    joined = " ".join(item["text"] for item in sorted(have, key=lambda i: i["line"]))
    for name in names:
        if name.lower() == "copyright" or YEARS_ONLY.match(name):
            messages.append(f"name {_shown(name)} is not a holder")
        elif not _occurs(name, joined):
            messages.append(f"name {_shown(name)} occurs in no evidence text")
    return messages


def compare(recorded: dict, scanned: dict, lines) -> list[str]:
    """Messages where the recorded attribution disagrees with the scan; empty means agreement."""
    if recorded["status"] != scanned["status"]:
        return [f"attribution status '{recorded['status']}' but the source scan finds "
                f"'{scanned['status']}'"]
    if recorded["status"] == "recorded":
        return _compare_recorded(recorded, scanned)
    if recorded["status"] == "ambiguous":
        return _compare_ambiguous(recorded, scanned, lines)
    return []


def fact_files(file, data: dict) -> list[tuple[str, str, dict | None, tuple]]:
    """(repo name, path, attribution or None, (url, commit)) for each file a fact cites.

    A contrary reading's support (`conflicts`) is not the fact's support, and a directory
    citation records a search, not a text with a notice. Inference premises are not followed
    here; `premise_files` does that.
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
        result.append((*key, listed[0].get("attribution") if listed else None,
                       (entry.get("url"), entry.get("commit"))))
    return result


def premise_files(checker, rec):
    """The facts `rec` rests on through inference premises, and the files they cite.

    Follows `premises[].fact` of the support entries (stated premises' nested support
    included, `conflicts` excluded), recursively and depth-first in citation order. It never
    follows `relates`, an emulated entry's `observation`, or assumptions. Returns the reached
    facts' full ids and their `fact_files` items, de-duplicated by (url, commit, path).
    """
    visited, ids, items, seen = {rec.full}, [], [], set()

    def walk(current):
        for entry, at in speccheck.supports(current.data, ()):
            if "conflicts" in at or entry.get("class") != "inference":
                continue
            for premise in entry.get("premises", []):
                if "fact" not in premise:
                    continue
                reached, why = checker.resolve(current.file, premise["fact"])
                if why:
                    # a premise that does not resolve is one file nobody recorded
                    key = (None, premise["fact"], None)
                    if key not in seen:
                        seen.add(key)
                        ids.append(premise["fact"])
                        items.append((None, premise["fact"], None, (None, None)))
                    continue
                if reached.full in visited:
                    continue
                visited.add(reached.full)
                ids.append(reached.full)
                for item in fact_files(reached.file, reached.data):
                    key = (*item[3], item[1])
                    if key not in seen:
                        seen.add(key)
                        items.append(item)
                walk(reached)

    walk(rec)
    return ids, items


def summary(items, always: bool = False) -> str | None:
    """One line over the files a fact cites, or None when no file carries attribution.

    With `always`, a non-empty list of files without attribution still gives the incomplete
    clause."""
    records = [item[2] for item in items]
    if not any(records) and not (always and records):
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
