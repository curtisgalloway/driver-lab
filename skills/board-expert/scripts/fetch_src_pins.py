#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Fetch the pinned repositories a board spec's [src:] anchors cite, below a size limit.

    fetch_src_pins.py <spec> <cache dir> [--limit-mb N] [--timeout S]

For each ``resources.repos`` entry that a ``[src:<name>: ...]`` anchor in the spec's body
names, and whose ``ref`` is a full commit id, this makes a shallow, blob-less partial clone
of that one commit under the cache directory (``git fetch --depth 1 --filter=blob:none``):
commits and trees only. ``anchor_check.py`` then reads each cited file with ``git show``,
which fetches just that file's blob from the same URL. The size limit applies to the
initial fetch: an entry whose fetch exceeds ``--limit-mb`` (default 50), takes longer than
``--timeout`` seconds (default 300), or fails, is skipped with a notice and its anchors stay
checked for form and license only.

Prints one ``<name>=<checkout>`` line per fetched entry on stdout, the form
``anchor_check.py --repo`` takes; notices go to stderr. Measured 2026-10-07 for the initial
fetch: raspberrypi/tools at one commit 0.5 MB, torvalds/linux at one commit 3.3 MB.

Exit codes: 0 done (entries may have been skipped), 2 usage error, 3 the spec has no front
matter or cannot be read.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

import spec_check  # same directory

SRC_NAME_RE = re.compile(r"\[src:([A-Za-z0-9][A-Za-z0-9._-]*):\s")


def tree_size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def fetch(url: str, ref: str, dest: Path, limit: int, timeout: int) -> str | None:
    """Shallow, blob-less fetch of one commit into dest; return why it was skipped, or None."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    git = ["git", "-C", str(dest)]
    try:
        subprocess.run(git + ["init", "-q"], check=True, capture_output=True)
        proc = subprocess.run(
            git + ["fetch", "-q", "--depth", "1", "--filter=blob:none", url, ref],
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return f"fetch took longer than {timeout} s"
    except (OSError, subprocess.CalledProcessError) as exc:
        return f"git failed: {exc}"
    if proc.returncode != 0:
        return f"fetch failed: {proc.stderr.strip()[:200]}"
    size = tree_size(dest / ".git")
    if size > limit:
        return f"initial fetch is {size // (1 << 20)} MB, over the {limit // (1 << 20)} MB limit"
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("spec", type=Path)
    ap.add_argument("cache", type=Path)
    ap.add_argument("--limit-mb", type=int, default=50)
    ap.add_argument("--timeout", type=int, default=300)
    args = ap.parse_args(argv)
    try:
        text = args.spec.read_text()
    except OSError as exc:
        print(f"missing precondition: {exc}", file=sys.stderr)
        return 3
    m = spec_check.FRONTMATTER_RE.match(text)
    if not m:
        print(f"missing precondition: {args.spec} has no front matter", file=sys.stderr)
        return 3
    meta = spec_check.load_yaml(m.group(1), spec_check.pyyaml_available()) or {}
    cited = set(SRC_NAME_RE.findall(m.group(2)))
    for group, entry in spec_check.iter_resources(meta):
        name = entry.get("name")
        if group != "repos" or name not in cited:
            continue
        url, ref = entry.get("url"), entry.get("ref")
        if not isinstance(url, str) or not isinstance(ref, str) or not spec_check.COMMIT_RE.match(ref):
            print(f"note: {args.spec}: repos entry {name!r} has no url or full commit ref; "
                  "its anchors are checked for form and license only", file=sys.stderr)
            continue
        dest = args.cache / f"{name}-{ref[:12]}"
        why = fetch(url, ref, dest, args.limit_mb << 20, args.timeout)
        if why:
            shutil.rmtree(dest, ignore_errors=True)
            print(f"note: {args.spec}: repos entry {name!r} not fetched ({why}); its anchors "
                  "are checked for form and license only", file=sys.stderr)
            continue
        print(f"{name}={dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
