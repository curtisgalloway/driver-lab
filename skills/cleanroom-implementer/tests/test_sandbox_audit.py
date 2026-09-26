#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Curtis Galloway
# SPDX-License-Identifier: Apache-2.0
"""
Tests for scripts/sandbox_audit.py.

Run:  python3 -m unittest discover -s skills/cleanroom-implementer/tests -v

The log below has the shapes strace -f -y writes for a cleanroom_sandbox.sh run:
bubblewrap's own setup processes touching host paths (which must be ignored), then
the sandboxed command's processes, including split unfinished/resumed calls and paths
relative to a directory fd. A test with a real sandbox runs when bwrap and strace are
installed.
"""

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import sandbox_audit  # noqa: E402  pylint: disable=wrong-import-position

LOG = """\
100 execve("/usr/bin/bwrap", ["bwrap", "--die-with-parent"], 0x7ffc /* 47 vars */) = 0
100 openat(AT_FDCWD</srv/host>, "/srv/host/runs/ws", O_RDONLY|O_PATH) = 3</srv/host/runs/ws>
100 clone(child_stack=NULL, flags=CLONE_NEWNS|CLONE_NEWPID|SIGCHLD) = 101
101 mount("/srv/host/runs/ws", "/newroot/work", NULL, MS_BIND, NULL) = 0
101 chdir("/work") = 0
101 clone(child_stack=NULL, flags=SIGCHLD, child_tidptr=0x7) = 2
102 execve("/opt/agent/agent", ["agent", "--json"], 0x5a /* 5 vars */ <unfinished ...>
101 wait4(-1 <unfinished ...>
102 <... execve resumed>) = 0
102 openat(AT_FDCWD</work>, "spec/spec.md", O_RDONLY|O_CLOEXEC) = 3</work/spec/spec.md>
102 openat(3</work/kernel>, "include", O_RDONLY|O_DIRECTORY) = 4</work/kernel/include>
102 openat(AT_FDCWD</work>, "cand/drv.c", O_WRONLY|O_CREAT|O_TRUNC, 0644) = 5</work/cand/drv.c>
102 newfstatat(AT_FDCWD</work>, "/srv/other", 0x7ff, 0) = -1 ENOENT (No such file or directory)
102 openat(AT_FDCWD</work>, "/agent-home/auth.json", O_RDONLY <unfinished ...>
103 execve("/usr/bin/cat", ["cat", "/usr/src/linux/e1000.c"], 0x6 /* 8 vars */) = 0
103 openat(AT_FDCWD</work>, "/usr/src/linux/e1000.c", O_RDONLY) = -1 ENOENT (No such file or directory)
102 <... openat resumed>) = 6</agent-home/auth.json>
102 connect(7<socket:[1]>, {sa_family=AF_INET, sin_port=htons(443), sin_addr=inet_addr("192.0.2.10")}, 16) = -1 EINPROGRESS (Operation now in progress)
102 connect(8<socket:[2]>, {sa_family=AF_INET6, sin6_port=htons(443), sin6_flowinfo=htonl(0), inet_pton(AF_INET6, "2001:db8::1", &sin6_addr), sin6_scope_id=0}, 28) = 0
102 statx(1<pipe:[586594]>, "", AT_STATX_SYNC_AS_STAT|AT_EMPTY_PATH, STATX_ALL, {stx_mode=S_IFIFO|0600, ...}) = 0
102 newfstatat(3</work/spec/spec.md>, "", {st_mode=S_IFREG|0644, ...}, AT_EMPTY_PATH) = 0
102 +++ exited with 0 +++
"""


def audit_of(text, **kw):
    return sandbox_audit.audit_lines(text.splitlines(True), **kw)


class ReportTest(unittest.TestCase):
    def setUp(self):
        self.rep = audit_of(LOG).report(["/work/spec/spec.md"])

    def test_setup_processes_are_ignored(self):
        everything = str(self.rep)
        self.assertNotIn("/srv/host", everything)
        self.assertNotIn("/newroot", everything)

    def test_workspace_reads_resolve_relative_and_fd_paths(self):
        self.assertEqual(
            self.rep["workspace_reads"], ["/work/kernel/include", "/work/spec/spec.md"]
        )

    def test_writes_are_not_reads(self):
        self.assertEqual(self.rep["workspace_writes"], ["/work/cand/drv.c"])
        self.assertNotIn("/work/cand/drv.c", self.rep["workspace_reads"])

    def test_execs_and_endpoints(self):
        self.assertEqual(list(self.rep["execs"]), ["/opt/agent/agent", "/usr/bin/cat"])
        self.assertEqual(
            self.rep["endpoints"], ["192.0.2.10 port 443", "2001:db8::1 port 443"]
        )

    def test_failed_attempts_are_listed_not_findings(self):
        self.assertEqual(
            self.rep["outside_allowed_roots_attempted"],
            ["/srv/other", "/usr/src/linux/e1000.c"],
        )
        self.assertEqual(self.rep["outside_allowed_roots_succeeded"], [])

    def test_fd_relative_to_a_pipe_is_not_a_path(self):
        self.assertNotIn("pipe", str(self.rep))
        self.assertEqual(self.rep["unresolved_relative_paths"], [])

    def test_relative_exec_with_unknown_cwd_does_not_crash(self):
        log = LOG + '104 execve("./configure", ["./configure"], 0x1 /* 3 vars */) = 0\n'
        rep = audit_of(log).report()
        self.assertIn("./configure", rep["unresolved_relative_paths"])
        self.assertNotIn(None, rep["execs"])

    def test_setup_child_logged_before_clone_result_is_ignored(self):
        log = (
            '100 execve("/usr/bin/bwrap", ["bwrap"], 0x7 /* 4 vars */) = 0\n'
            '100 clone(child_stack=NULL, flags=CLONE_NEWPID|SIGCHLD <unfinished ...>\n'
            '101 openat(AT_FDCWD</srv/host>, "/srv/host/secret", O_RDONLY) = 3\n'
            '100 <... clone resumed>) = 101\n'
            '102 openat(AT_FDCWD</work>, "a.txt", O_RDONLY) = 3</work/a.txt>\n'
        )
        rep = audit_of(log).report()
        self.assertEqual(rep["outside_allowed_roots_succeeded"], [])
        self.assertEqual(rep["workspace_reads"], ["/work/a.txt"])

    def test_send_destinations_and_unix_sockets_are_endpoints(self):
        log = LOG + (
            '102 sendto(9<socket:[3]>, "x", 1, 0, {sa_family=AF_INET, sin_port=htons(53), '
            'sin_addr=inet_addr("198.51.100.7")}, 16) = 1\n'
            '102 connect(10<socket:[4]>, {sa_family=AF_UNIX, sun_path=@"/tmp/.X11-unix/X0"}, 20)'
            ' = 0\n'
        )
        eps = audit_of(log).report()["endpoints"]
        self.assertIn("198.51.100.7 port 53", eps)
        self.assertIn("unix @/tmp/.X11-unix/X0", eps)

    def test_reads_outside_the_workspace_are_listed(self):
        self.assertIn("/agent-home/auth.json", self.rep["other_reads"])

    def test_a_stat_of_the_canary_is_not_an_open(self):
        log = LOG + '102 newfstatat(AT_FDCWD</work>, "canary", {st_mode=S_IFREG}, 0) = 0\n'
        rep = audit_of(log).report(["/work/canary"])
        self.assertEqual(rep["expected_reads_missing"], ["/work/canary"])

    def test_expected_read_found(self):
        self.assertEqual(self.rep["expected_reads_missing"], [])

    def test_expected_read_missing(self):
        rep = audit_of(LOG).report(["/work/canary.txt"])
        self.assertEqual(rep["expected_reads_missing"], ["/work/canary.txt"])

    def test_successful_access_outside_roots_is_a_finding(self):
        bad = LOG + '102 openat(AT_FDCWD</work>, "/srv/ref/e1000_main.c", O_RDONLY) = 9\n'
        rep = audit_of(bad).report()
        self.assertEqual(rep["outside_allowed_roots_succeeded"], ["/srv/ref/e1000_main.c"])

    def test_hidden_dir_contents_are_outside(self):
        bad = LOG + '102 openat(AT_FDCWD</work>, "/usr/src/k/Makefile", O_RDONLY) = 9\n'
        rep = audit_of(bad).report()
        self.assertEqual(rep["outside_allowed_roots_succeeded"], ["/usr/src/k/Makefile"])


class CliTest(unittest.TestCase):
    def run_cli(self, text, *args):
        with tempfile.NamedTemporaryFile("w", suffix=".strace", delete=False) as f:
            f.write(text)
        try:
            return subprocess.run(
                [sys.executable, str(SCRIPTS / "sandbox_audit.py"), f.name, *args],
                capture_output=True, text=True, check=False,
            )
        finally:
            os.unlink(f.name)

    def test_clean_log_exits_0(self):
        self.assertEqual(self.run_cli(LOG, "--expect-read", "/work/spec/spec.md").returncode, 0)

    def test_missing_expected_read_exits_1(self):
        self.assertEqual(self.run_cli(LOG, "--expect-read", "/work/nope").returncode, 1)

    def test_log_with_no_sandboxed_process_exits_1(self):
        self.assertEqual(self.run_cli(LOG.splitlines(True)[0]).returncode, 1)

    def test_sandbox_refuses_trailing_option_and_existing_log(self):
        script = str(SCRIPTS / "cleanroom_sandbox.sh")
        r = subprocess.run([script, "--log"], capture_output=True, text=True,
                           check=False, timeout=10)
        self.assertEqual(r.returncode, 2)
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "old.strace")
            with open(log, "w", encoding="utf-8") as f:
                f.write("kept\n")
            r = subprocess.run(
                [script, "--workspace", d, "--home", d, "--tool-dir", d, "--log", log,
                 "--", "true"], capture_output=True, text=True, check=False, timeout=10)
            self.assertEqual(r.returncode, 2)
            with open(log, encoding="utf-8") as f:
                self.assertEqual(f.read(), "kept\n")

    def test_unreadable_log_exits_2(self):
        r = subprocess.run(
            [sys.executable, str(SCRIPTS / "sandbox_audit.py"), "/nonexistent/log"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(r.returncode, 2)


@unittest.skipUnless(shutil.which("bwrap") and shutil.which("strace"),
                     "needs bubblewrap and strace")
class RealSandboxTest(unittest.TestCase):
    def test_host_files_invisible_and_reads_logged(self):
        with tempfile.TemporaryDirectory() as d:
            ws, home, tools = (os.path.join(d, n) for n in ("ws", "home", "tools"))
            for p in (ws, home, tools):
                os.mkdir(p)
            with open(os.path.join(ws, "canary.txt"), "w", encoding="utf-8") as f:
                f.write("canary\n")
            secret = os.path.join(d, "outside.txt")
            with open(secret, "w", encoding="utf-8") as f:
                f.write("must not be visible\n")
            log = os.path.join(d, "t.strace")
            r = subprocess.run(
                [str(SCRIPTS / "cleanroom_sandbox.sh"), "--workspace", ws, "--home", home,
                 "--tool-dir", tools, "--log", log, "--",
                 "sh", "-c", f"cat canary.txt; cat {secret}; ls -A /home; exit 0"],
                capture_output=True, text=True, check=False,
            )
            if r.returncode == 2 or "Operation not permitted" in r.stderr:
                self.skipTest(f"sandbox unavailable here: {r.stderr.strip()[:200]}")
            # A host file outside the workspace does not exist in the sandbox, and the
            # host's /home is an empty directory there.
            self.assertEqual(r.stdout, "canary\n")
            with open(log, encoding="utf-8") as f:
                rep = audit_of(f.read()).report(["/work/canary.txt"])
            self.assertEqual(rep["expected_reads_missing"], [])
            self.assertEqual(rep["outside_allowed_roots_succeeded"], [])


if __name__ == "__main__":
    unittest.main()
