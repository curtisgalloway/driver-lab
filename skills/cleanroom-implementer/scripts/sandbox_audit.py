#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Curtis Galloway
# SPDX-License-Identifier: Apache-2.0
"""Audit the strace log of a cleanroom_sandbox.sh run.

Reports, for every process inside the sandbox (bubblewrap's own setup processes, which
touch host paths while building the sandbox, are excluded):

- the workspace files they read and wrote (under /work), and every other path they
  read successfully (libraries, /etc and so on), listed so reads outside the workspace
  are visible even where the sandbox allows them;
- every program executed;
- every network endpoint contacted: IP addresses given to connect, sendto or sendmsg
  (recorded as bare addresses, not host names), and UNIX sockets connected to.

A successful access outside the allowed roots is a finding: the sandbox should have
made it impossible, so one means the sandbox was misconfigured. Failed accesses are
listed as attempts but are not findings, since the path did not exist in the sandbox.

`--expect-read PATH` asserts that the log records a successful open of PATH (open,
openat or openat2; a stat does not count). Use it with a canary file the agent is asked
to read, to show the log covers the agent's reads before relying on it (the check the
L02f2 plan requires).

Limits: the verdict does not judge network endpoints (egress is shared by design; a
reviewer reads the list), and a relative path whose process's working directory is
unknown (cwd is tracked only through chdir in the same process) is listed under
unresolved_relative_paths rather than judged.

Exit codes: 0 clean; 1 findings, or an expected read missing, or no sandboxed process
found in the log; 2 usage error or unreadable log.
"""

import argparse
import collections
import json
import posixpath
import re
import sys

DEFAULT_ROOTS = (
    "/work", "/agent-home", "/opt/agent", "/usr", "/etc", "/proc", "/dev", "/tmp",
    "/run/systemd/resolve", "/bin", "/lib", "/lib64", "/sbin",
)
# Top-level directories that exist in the sandbox as empty tmpfs mounts or as mount
# points; stat-ing them (not their contents) is harmless.
MOUNT_POINTS = frozenset([
    "/", "/home", "/root", "/opt", "/srv", "/mnt", "/media", "/run", "/sys",
    "/usr/src", "/usr/lib/modules",
])
# Hidden under an allowed root (empty tmpfs in the sandbox): anything below them is
# outside the allowed roots.
HIDDEN = ("/usr/src", "/usr/lib/modules")

LINE_RE = re.compile(r"^(\d+) (?:<\.\.\. (\w+) resumed>|(\w+)\()(.*)$")
STRING_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')
FD_PATH_RE = re.compile(r"^(?:AT_FDCWD|\d+)<([^>]*)>")
RESULT_RE = re.compile(r"\)\s+=\s+(-?\d+|\?)")
UNIX_RE = re.compile(r'sa_family=AF_UNIX, sun_path=(@?)"((?:[^"\\]|\\.)*)"')
INET_RE = re.compile(
    r"sa_family=AF_INET6?, sin6?_port=htons\((\d+)\).*?"
    r"(?:inet_addr\(\"([^\"]+)\"\)|inet_pton\(AF_INET6, \"([^\"]+)\")"
)

# Syscalls whose first argument is a directory fd and whose path is the second.
AT_CALLS = frozenset([
    "openat", "openat2", "newfstatat", "fstatat64", "statx", "faccessat", "faccessat2",
    "readlinkat", "mkdirat", "unlinkat", "fchmodat", "fchownat", "utimensat",
    "mknodat", "name_to_handle_at", "execveat", "inotify_add_watch",
])
# Syscalls that only write, create or remove: recorded as writes, not reads.
WRITE_CALLS = frozenset([
    "mkdir", "mkdirat", "unlink", "unlinkat", "rmdir", "rename", "renameat",
    "renameat2", "symlink", "symlinkat", "link", "linkat", "creat", "truncate",
    "chmod", "fchmodat", "utimensat",
])
# Syscalls with no path argument worth auditing.
# Calls that carry a destination address.
ADDRESS_CALLS = frozenset(["connect", "sendto", "sendmsg", "sendmmsg"])
SKIP_CALLS = frozenset([
    "clone", "clone3", "fork", "vfork", "wait4", "exit", "exit_group", "kill",
    "tgkill", "socket", "socketpair", "bind", "listen", "accept", "accept4",
    "getsockname", "getpeername", "setsockopt", "getsockopt", "recvfrom",
    "recvmsg", "recvmmsg", "shutdown", "fchdir", "fstatfs",
    "fchmod", "fchown", "arch_prctl", "prctl", "pidfd_open", "pidfd_send_signal",
])


def _unescape(s):
    return s.encode("latin-1", "backslashreplace").decode("unicode_escape")


class Audit:
    """Accumulates the audit from strace lines."""

    def __init__(self, roots=DEFAULT_ROOTS, setup_pids=None, bwrap_pid=None):
        self.roots = tuple(r.rstrip("/") for r in roots)
        # Preset by audit_lines() from a first pass, so the result does not depend on
        # whether strace logs bubblewrap's clone result before or after the child's
        # first calls.
        self.setup_pids = set(setup_pids or ())
        self.bwrap_pid = bwrap_pid
        self.pending = {}  # pid -> (syscall, args) of an unfinished call
        self.cwd = {}
        self.accesses = collections.OrderedDict()  # (path, kind) -> [ok, failed]
        self.execs = collections.Counter()
        self.endpoints = collections.Counter()
        self.opened = set()
        self.unresolved = collections.Counter()
        self.inside_lines = 0

    def allowed(self, path):
        if path in MOUNT_POINTS:
            return True
        if any(path.startswith(h + "/") for h in HIDDEN):
            return False
        return any(path == r or path.startswith(r + "/") for r in self.roots)

    def feed(self, line):
        line = line.rstrip("\n")
        if line.endswith("<unfinished ...>"):
            m = LINE_RE.match(line)
            if m and m.group(3):
                self.pending[m.group(1)] = (m.group(3), m.group(4))
            return
        m = LINE_RE.match(line)
        if not m:
            return
        pid, resumed, call, rest = m.groups()
        if resumed:
            call = resumed
            start = self.pending.pop(pid, (call, ""))[1]
            rest = start + rest
        result = RESULT_RE.search(rest)
        ok = bool(result) and result.group(1) not in ("?",) and not result.group(
            1).startswith("-")
        self._record(pid, call, rest, ok, result.group(1) if result else None)

    def _record(self, pid, call, args, ok, ret):
        if self.bwrap_pid is None and call == "execve" and '"bwrap"' in args[:200]:
            self.bwrap_pid = pid
            self.setup_pids.add(pid)
            return
        if pid in self.setup_pids:
            # bubblewrap's direct children are its setup/init processes; their clone
            # return values are host pids because the new pid namespace applies to
            # the child. Grandchildren's are namespace pids and are not tracked.
            if pid == self.bwrap_pid and call in ("clone", "clone3") and ok:
                self.setup_pids.add(ret)
            return
        self.inside_lines += 1
        if call in SKIP_CALLS:
            return
        if call in ADDRESS_CALLS:
            m = INET_RE.search(args)
            if m:
                self.endpoints[(m.group(2) or m.group(3), f"port {m.group(1)}")] += 1
            u = UNIX_RE.search(args)
            if u and call == "connect":
                where = u.group(1) + _unescape(u.group(2))
                self.endpoints[("unix", where if ok else where + " (failed)")] += 1
            return
        strings = STRING_RE.findall(args)
        if not strings:
            return
        if call == "execve":
            path = self._resolve(pid, None, _unescape(strings[0]))
            if path is None:
                return
            if ok:
                self.execs[path] += 1
            self._access(path, "exec", ok)
            return
        dirbase = None
        if call in AT_CALLS or call in ("renameat", "renameat2", "linkat", "symlinkat"):
            fd = FD_PATH_RE.match(args)
            dirbase = fd.group(1) if fd else ""
        paths = [strings[0]]
        if call in ("rename", "renameat", "renameat2", "link", "linkat"):
            paths = strings[:2]
        elif call in ("symlink", "symlinkat"):
            paths = strings[1:2]
        elif call in ("readlink", "getcwd"):
            paths = strings[:1] if call == "readlink" else []
        kind = "write" if call in WRITE_CALLS else "read"
        if call in ("openat", "open", "openat2") and re.search(r"O_(WRONLY|RDWR|CREAT)", args):
            kind = "write"
        for raw in paths:
            path = self._resolve(pid, dirbase, _unescape(raw))
            if path is None:
                continue
            if call == "chdir" and ok:
                self.cwd[pid] = path
            if ok and call in ("open", "openat", "openat2"):
                self.opened.add(path)
            self._access(path, kind, ok)

    def _resolve(self, pid, dirbase, path):
        if path == "" and not dirbase:
            return None
        if path.startswith("/"):
            return posixpath.normpath(path)
        if dirbase and not dirbase.startswith("/"):
            # Relative to a pipe, socket or anonymous fd (fstat with AT_EMPTY_PATH):
            # not a file-system path.
            return None
        base = dirbase if dirbase else self.cwd.get(pid)
        if not base:
            self.unresolved[path] += 1
            return None
        return posixpath.normpath(posixpath.join(base, path))

    def _access(self, path, kind, ok):
        slot = self.accesses.setdefault((path, kind), [0, 0])
        slot[0 if ok else 1] += 1

    def report(self, expect_reads=()):
        workspace_reads = sorted(
            p for (p, k), (okc, _) in self.accesses.items()
            if k == "read" and okc and (p == "/work" or p.startswith("/work/"))
        )
        findings = sorted(
            {p for (p, _), (okc, _) in self.accesses.items() if okc and not self.allowed(p)}
        )
        attempts = sorted(
            {p for (p, _), (okc, bad) in self.accesses.items()
             if bad and not okc and not self.allowed(p)}
        )
        missing = [p for p in expect_reads if p not in self.opened]
        other_reads = sorted(
            p for (p, k), (okc, _) in self.accesses.items()
            if k == "read" and okc and p != "/work" and not p.startswith("/work/")
        )
        return {
            "sandboxed_process_lines": self.inside_lines,
            "workspace_reads": workspace_reads,
            "workspace_writes": sorted(
                p for (p, k), (okc, _) in self.accesses.items()
                if k == "write" and okc and p.startswith("/work/")
            ),
            "execs": dict(sorted(self.execs.items())),
            "other_reads": other_reads,
            "endpoints": [f"{h} {p}" for (h, p) in sorted(self.endpoints)],
            "outside_allowed_roots_succeeded": findings,
            "outside_allowed_roots_attempted": attempts,
            "unresolved_relative_paths": sorted(self.unresolved),
            "expected_reads_missing": missing,
        }


def audit_lines(lines, roots=DEFAULT_ROOTS):
    """Audits a log given as a re-iterable sequence of lines, in two passes.

    The first pass only finds bubblewrap's setup processes; the second audits every
    other process with that set fixed from the start.
    """
    scan = Audit(roots)
    for line in lines:
        scan.feed(line)
    audit = Audit(roots, setup_pids=scan.setup_pids, bwrap_pid=scan.bwrap_pid)
    for line in lines:
        audit.feed(line)
    return audit


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("log", help="strace log written by cleanroom_sandbox.sh --log")
    ap.add_argument("--expect-read", action="append", default=[], metavar="PATH",
                    help="sandbox path that must appear as a successful read")
    ap.add_argument("--root", action="append", default=[], metavar="PATH",
                    help="extra allowed root (sandbox path)")
    ap.add_argument("--json", action="store_true", help="print the full report as JSON")
    args = ap.parse_args(argv)
    try:
        with open(args.log, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError as e:
        print(f"cannot read log: {e}", file=sys.stderr)
        return 2
    audit = audit_lines(lines, DEFAULT_ROOTS + tuple(args.root))
    rep = audit.report(args.expect_read)
    failed = bool(
        rep["outside_allowed_roots_succeeded"] or rep["expected_reads_missing"]
        or not rep["sandboxed_process_lines"]
    )
    rep["verdict"] = "FAIL" if failed else "PASS"
    if args.json:
        print(json.dumps(rep, indent=2))
    else:
        print(f"verdict: {rep['verdict']}")
        print(f"sandboxed process lines: {rep['sandboxed_process_lines']}")
        print(f"workspace files read: {len(rep['workspace_reads'])}")
        print(f"workspace files written: {len(rep['workspace_writes'])}")
        print(f"other files read: {len(rep['other_reads'])}")
        print(f"programs executed: {len(rep['execs'])}")
        for name in ("endpoints", "outside_allowed_roots_succeeded",
                     "outside_allowed_roots_attempted", "expected_reads_missing",
                     "unresolved_relative_paths"):
            print(f"{name}: {len(rep[name])}")
            for item in rep[name][:50]:
                print(f"  {item}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
