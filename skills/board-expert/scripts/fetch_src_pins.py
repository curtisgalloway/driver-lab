#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Fetch the pinned repositories a board spec's [src:] anchors cite, below a size limit.

    fetch_src_pins.py <spec> <cache dir> [--limit-mb N] [--timeout S]

For each ``resources.repos`` entry that a ``[src:<name>: ...]`` anchor in the spec's body
names (found with peripheral-spec's ``anchor_check.py`` parser, so every form it accepts
counts), and whose ``ref`` is a full commit id, this makes a shallow, blob-less partial clone
of that one commit under the cache directory (``git fetch --depth 1 --filter=blob:none``):
commits and trees only. ``anchor_check.py`` then reads each cited file with ``git show``,
which fetches just that file's blob from the same URL.

Only ``https://`` URLs are fetched, with git's other transports turned off and the URL
placed after ``--``, so a spec's ``url:`` can never be read as a git option. Nothing runs
through a shell. A repository already fetched into the cache at the same commit (by an
earlier spec in the same run) is reused.

Outcomes, per entry:

  * fetched: one ``<name>=<checkout>`` line on stdout, the form ``anchor_check.py --repo``
    takes;
  * skipped, with a ``note:`` on stderr naming the reason, when the transfer takes longer
    than ``--timeout`` seconds (default 300; the timeout bounds the transfer) or the fetched
    objects exceed ``--limit-mb`` (default 50; measured after the fetch, so the limit bounds
    what is kept, not what is transferred). Its anchors stay checked for form and license only;
  * failed, with an ``error:`` on stderr, for any other outcome: a URL that is not https, a
    ref that is not a full commit id, or a fetch git refuses (repository not found, commit
    not found, host unreachable). The run continues with the other entries and exits 1.

Measured 2026-10-07 for the initial fetch: raspberrypi/tools at one commit 0.5 MB,
torvalds/linux at one commit 3.3 MB.

Exit codes: 0 every cited entry fetched or skipped, 1 an entry failed, 2 usage error, 3 the
spec has no front matter, cannot be read, or anchor_check.py is not installed beside this
skill.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

import spec_check  # same directory

# Every transport off except https (--allow-local adds file, for tests only).
GIT_SAFE = ["-c", "protocol.allow=never", "-c", "protocol.https.allow=always"]


def tree_size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def cited_repos(body: str, ac) -> set[str]:
    """Names of the repos entries the body's [src:] anchors cite, by anchor_check's parser."""
    report = ac.Report(spec="")
    anchors = ac.parse_spec(body, report, False, 0, True)
    return {a.pin for a in anchors if a.kind == "src" and a.pin}


def has_commit(dest: Path, ref: str) -> bool:
    proc = subprocess.run(
        ["git", "-C", str(dest), "cat-file", "-e", f"{ref}^{{commit}}"], capture_output=True
    )
    return proc.returncode == 0


def fetch(url: str, ref: str, dest: Path, limit: int, timeout: int, safe: list[str]):
    """Shallow, blob-less fetch of one commit into dest.

    Returns (kind, why): (None, None) when fetched, ("skip", why) for timeout or size,
    ("fail", why) for anything else.
    """
    if dest.exists() and has_commit(dest, ref):
        return None, None
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    git = ["git", *safe, "-C", str(dest)]
    try:
        subprocess.run(git + ["init", "-q"], check=True, capture_output=True)
        proc = subprocess.run(
            git + ["fetch", "-q", "--depth", "1", "--filter=blob:none", "--", url, ref],
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return "skip", f"timeout: the transfer took longer than {timeout} s"
    except (OSError, subprocess.CalledProcessError) as exc:
        return "fail", f"git could not run: {exc}"
    if proc.returncode != 0:
        return "fail", f"git fetch failed: {proc.stderr.strip()[:300]}"
    size = tree_size(dest / ".git")
    if size > limit:
        return "skip", (f"size: the fetched objects are {size // (1 << 20)} MB, over the "
                        f"{limit // (1 << 20)} MB limit")
    return None, None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("spec", type=Path)
    ap.add_argument("cache", type=Path)
    ap.add_argument("--limit-mb", type=int, default=50)
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--allow-local", action="store_true", help=argparse.SUPPRESS)
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
    ac = spec_check.load_anchor_check()
    if ac is None:
        print("missing precondition: peripheral-spec's anchor_check.py is not installed beside "
              "board-expert", file=sys.stderr)
        return 3
    try:
        spec_check.mdtokens.require()
    except spec_check.mdtokens.MissingDependency as exc:
        print(exc, file=sys.stderr)
        return 3
    meta = spec_check.load_yaml(m.group(1), spec_check.pyyaml_available()) or {}
    cited = cited_repos(m.group(2), ac)
    schemes = ("https://", "file://") if args.allow_local else ("https://",)
    safe = GIT_SAFE + (["-c", "protocol.file.allow=always"] if args.allow_local else [])
    failed = 0
    for group, entry in spec_check.iter_resources(meta):
        name = entry.get("name")
        if group != "repos" or not isinstance(name, str) or name not in cited:
            continue
        url, ref = entry.get("url"), entry.get("ref")
        if not isinstance(url, str) or not url.startswith(schemes):
            print(f"error: {args.spec}: repos entry {name!r}: url {url!r} is not an https:// "
                  "URL; not fetched", file=sys.stderr)
            failed += 1
            continue
        if not isinstance(ref, str) or not spec_check.COMMIT_RE.match(ref):
            print(f"error: {args.spec}: repos entry {name!r}: ref {ref!r} is not a full commit "
                  "id; not fetched", file=sys.stderr)
            failed += 1
            continue
        key = hashlib.sha256(url.encode()).hexdigest()[:12]
        dest = args.cache / f"{key}-{ref[:12]}"
        kind, why = fetch(url, ref, dest, args.limit_mb << 20, args.timeout, safe)
        if kind == "skip":
            shutil.rmtree(dest, ignore_errors=True)
            print(f"note: {args.spec}: repos entry {name!r} skipped ({why}); its anchors are "
                  "checked for form and license only", file=sys.stderr)
            continue
        if kind == "fail":
            shutil.rmtree(dest, ignore_errors=True)
            print(f"error: {args.spec}: repos entry {name!r}: {why}", file=sys.stderr)
            failed += 1
            continue
        print(f"{name}={dest}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
