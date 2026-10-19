#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Generate domain-scoped expert stubs from a manifest (#156).

    python3 skills/board-spec-scaffold/scripts/stubgen.py <domains.yaml> --out <skills dir>
        [--check]

Large SoCs push toward several domain experts (USB, storage, display, power, security) beside
the board expert. Written by hand, their prompts pick up hardware facts no checker reads. This
writes one `<out>/<name>/SKILL.md` per manifest domain from templates/domain-stub-SKILL.md:
the domain's spec ids and instance rows as `spec:` and `instance:` lines, its split from the
other experts as a `split:` line, the skills to preload and an optional output profile. The
stubs hold procedure and pointers only, and stay consistent because one manifest makes them.

The manifest is read with spec-format's strict loader. A field holding a hex literal or a
register-style name is refused (spec-format/scripts/prosefacts.py), as is a domain name used
twice. `--check` writes nothing and exits 1 when a stub on disk differs from what the manifest
makes. Then run `spec.py check <roots>... --stubs-from <out>`: it resolves the spec and instance
lines, lints the prose and warns when two stubs share an entry spec with no stated split.

Exit 0 written or current / 1 a refusal or a stale stub / 2 usage.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE.parent / "templates" / "domain-stub-SKILL.md"
SPEC_FORMAT = HERE.parents[1] / "spec-format" / "scripts"
NAME = re.compile(r"[a-z0-9][a-z0-9-]*")
INSTANCE = re.compile(r"([a-z0-9][a-z0-9-]*)#([a-z0-9][a-z0-9-]*)")
FIELDS = {"name", "title", "description", "entry", "instances", "preload", "split", "profile"}
TOP = {"format", "board", "copyright", "license", "domains"}


class Refused(Exception):
    pass


def load(path: Path) -> dict:
    sys.path.insert(0, str(SPEC_FORMAT))
    import specload

    try:
        data = specload.load_strict(path)
    except specload.LoadError as exc:
        raise Refused(f"{path}:{exc.line}:{exc.column}: {exc.problem}") from None
    return data


def one_line(where: str, value) -> str:
    if not isinstance(value, str) or not value.strip() or "\n" in value or "`" in value:
        raise Refused(f"{where}: a single line of text without backticks")
    return " ".join(value.split())


def render(manifest: dict) -> dict[str, str]:
    """name -> SKILL.md text for every domain; Refused on the first problem."""
    import prosefacts

    if not isinstance(manifest, dict) or set(manifest) - TOP or manifest.get("format") != 2:
        raise Refused(f"the manifest is a mapping with format: 2 and only {sorted(TOP)}")
    board = manifest.get("board")
    if not isinstance(board, str) or not NAME.fullmatch(board):
        raise Refused("board: a spec id")
    copyright_ = one_line("copyright", manifest.get("copyright"))
    license_ = one_line("license", manifest.get("license"))
    domains = manifest.get("domains")
    if not isinstance(domains, list) or not domains:
        raise Refused("domains: a non-empty list")
    template = TEMPLATE.read_text(encoding="utf-8")
    out: dict[str, str] = {}
    for i, d in enumerate(domains):
        where = f"domains[{i}]"
        if not isinstance(d, dict) or set(d) - FIELDS or not {"name", "title", "description",
                                                               "entry"} <= set(d):
            raise Refused(f"{where}: name, title, description and entry, and only "
                          f"{sorted(FIELDS)}")
        name = d["name"]
        if not isinstance(name, str) or not NAME.fullmatch(name):
            raise Refused(f"{where}.name: lower-case letters, digits and hyphens")
        if name in out:
            raise Refused(f"{where}.name: {name!r} is used twice; installed names must differ")
        entry = d["entry"]
        if (not isinstance(entry, list) or not entry
                or not all(isinstance(e, str) and NAME.fullmatch(e) for e in entry)):
            raise Refused(f"{where}.entry: a non-empty list of spec ids")
        instances = d.get("instances", [])
        if not isinstance(instances, list) or not all(
                isinstance(x, str) and INSTANCE.fullmatch(x) for x in instances):
            raise Refused(f"{where}.instances: a list of <spec>#<instance row> ids")
        preload = d.get("preload", ["board-expert"])
        if (not isinstance(preload, list) or not preload
                or not all(isinstance(p, str) and NAME.fullmatch(p) for p in preload)):
            raise Refused(f"{where}.preload: a non-empty list of skill names")
        text = {k: one_line(f"{where}.{k}", d[k]) for k in ("title", "description", "split",
                                                            "profile") if k in d}
        for key, value in text.items():
            found = prosefacts.findings(value)
            if found:
                raise Refused(f"{where}.{key}: {prosefacts.message(found[0][2])}")
        lines = [f"`spec: {e}`" for e in dict.fromkeys(entry)]
        lines += [f"`instance: {x}`" for x in dict.fromkeys(instances)]
        if "split" in text:
            lines.append(f"`split: {text['split']}`")
        fill = {
            "name": name, "title": text["title"], "description": text["description"].rstrip("."),
            "entry-ids": ", ".join(f"`{e}`" for e in dict.fromkeys(entry)),
            "copyright-year> <copyright-holder": copyright_, "file-license": license_,
            "board": board,
            "entry-lines": "\n".join(lines),
            "preload": ", ".join(f"`{p}`" for p in preload),
            "profile-line": (f"\nOutput profile: {text['profile'].rstrip('.')}.\n"
                             if "profile" in text else ""),
        }
        # one pass: a manifest value that looks like a placeholder stays as written
        pattern = re.compile("<(" + "|".join(re.escape(k) for k in fill) + ")>")
        out[name] = pattern.sub(lambda m: fill[m.group(1)], template)
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--out", type=Path, required=True, help="the skills directory")
    parser.add_argument("--check", action="store_true", help="write nothing; exit 1 if stale")
    args = parser.parse_args(argv)
    try:
        stubs = render(load(args.manifest))
    except Refused as exc:
        print(f"{args.manifest}: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"{args.manifest}: {exc.strerror or exc}", file=sys.stderr)
        return 2
    stale = 0
    for name, text in stubs.items():
        path = args.out / name / "SKILL.md"
        current = path.read_text(encoding="utf-8") if path.is_file() else None
        if current == text:
            print(f"{path}: current")
            continue
        if args.check:
            print(f"{path}: {'stale' if current is not None else 'missing'}")
            stale += 1
            continue
        if path.is_symlink() or path.parent.is_symlink():
            print(f"{path}: a symbolic link; not written", file=sys.stderr)
            return 1
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(f"{path}: written")
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main())
