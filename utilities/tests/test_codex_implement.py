# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for utilities/codex-implement.py: validation, environment, the patch and its refusals.

Hermetic: the module's home directory and REPO are patched to a temporary tree, BASE is a commit
of a real tiny git repository made here, and `codex` is a fake shell script named by absolute
path in a test config.toml. The fake dumps its environment, then runs a per-test body inside the
export it was given.
"""

import contextlib
import importlib.util
import io
import os
import resource
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))),
                      "codex-implement.py")
STAMP = "20261009T000000Z"
FAKE = """#!/bin/sh
work=
last=
while [ $# -gt 0 ]; do
  case "$1" in
    --cd) work="$2"; shift ;;
    --output-last-message) last="$2"; shift ;;
  esac
  shift
done
env > '{env_dump}'
printf '%s' "$last" > '{env_dump}.last'
cd "$work" || exit 99
{body}
echo 'final message' > "$last"
exit {code}
"""


def alive(pid):
  try:
    with open(f"/proc/{pid}/stat", encoding="utf-8") as f:
      return f.read().rsplit(")", 1)[1].split()[0] != "Z"
  except (FileNotFoundError, ProcessLookupError):
    # A process reaped between open() and read() makes the read fail with ESRCH.
    return False


def load():
  spec = importlib.util.spec_from_file_location("codex_implement", SCRIPT)
  module = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(module)
  return module


class CodexImplementTest(unittest.TestCase):

  def setUp(self):
    self.tmp = os.path.realpath(tempfile.mkdtemp())
    self.addCleanup(self.force_remove, self.tmp)
    self.mod = load()
    self.home = os.path.join(self.tmp, "home")
    self.store = os.path.join(self.tmp, "store")
    self.run_dir = os.path.join(self.store, "unit-20261009-01")
    os.makedirs(self.run_dir)
    self.brief = os.path.join(self.run_dir, "brief.md")
    self.write(self.brief, "brief\n")
    self.codex = os.path.join(self.tmp, "bin", "codex")
    self.env_dump = os.path.join(self.tmp, "env.txt")
    self.fake_codex("true")
    self.config(f'run_store = "{self.store}"\ncodex = "{self.codex}"\n')
    self.repo = os.path.join(self.tmp, "repo")
    self.base = self.make_repo()
    self.mod.REPO = self.repo
    for name, value in (("home", self.home), ("stamp", STAMP)):
      patcher = mock.patch.object(self.mod, name, return_value=value)
      patcher.start()
      self.addCleanup(patcher.stop)
    self.parent = os.path.join(self.home, ".cache", "driver-lab-codex")

  @staticmethod
  def force_remove(path):
    for top, dirs, _ in os.walk(path):
      for name in dirs:
        full = os.path.join(top, name)
        if not os.path.islink(full):
          os.chmod(full, 0o700)
    shutil.rmtree(path)

  def write(self, path, text, mode=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
      f.write(text)
    if mode is not None:
      os.chmod(path, mode)

  def config(self, text):
    self.write(os.path.join(self.home, ".config", "driver-lab", "config.toml"), text)

  def git(self, *args, cwd=None):
    env = {"PATH": os.environ["PATH"], "HOME": self.home, "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_CONFIG_GLOBAL": os.devnull, "LANG": "C.UTF-8"}
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com",
                           "-c", "init.defaultBranch=main", *args],
                          cwd=cwd or self.repo, env=env, check=True, capture_output=True,
                          text=True).stdout.strip()

  def make_repo(self):
    os.makedirs(self.repo)
    files = {"README.md": "hello\nworld\n", "data.txt": "delete me\n", "lib/mod.py": "x = 1\n",
             "AGENTS.md": "rules\n", ".github/ci.yml": "on: push\n"}
    for rel, text in files.items():
      self.write(os.path.join(self.repo, rel), text)
    self.write(os.path.join(self.repo, "tool.sh"), "#!/bin/sh\necho hi\n", 0o755)
    os.symlink("README.md", os.path.join(self.repo, "readme-link"))
    self.git("init", "-q")
    self.git("add", "-A")
    self.git("commit", "-q", "-m", "base")
    return self.git("rev-parse", "HEAD")

  def fake_codex(self, body, code=0):
    self.write(self.codex, FAKE.format(env_dump=self.env_dump, body=body, code=code), 0o755)

  def main(self, *args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
      try:
        code = self.mod.main(list(args))
      except SystemExit as exc:
        code = exc.code
    return code, out.getvalue(), err.getvalue()

  def run_codex(self):
    return self.main(self.base, self.run_dir, self.brief)

  def output(self, kind):
    names = {"log": f"codex-{STAMP}.log", "last": f"last-message-{STAMP}.md",
             "patch": f"codex-{STAMP}.patch", "refused": f"codex-{STAMP}.refused.txt"}
    return os.path.join(self.run_dir, names[kind])

  def read(self, path):
    with open(path, encoding="utf-8") as f:
      return f.read()

  def assert_code(self, expected, *args):
    code, _, err = self.main(*args)
    self.assertEqual(code, expected, (args, err))

  # Validation.

  def test_wrong_argument_count(self):
    self.assert_code(2, self.base, self.run_dir)
    self.assert_code(2, self.base, self.run_dir, self.brief, "--sandbox=danger-full-access")

  def test_base_must_be_a_full_commit_of_the_repo(self):
    tree = self.git("rev-parse", "HEAD^{tree}")
    for bad in ("abc", self.base[:12], self.base.upper(), "0" * 40, tree, "-" + self.base[1:]):
      with self.subTest(bad=bad):
        self.assert_code(2, bad, self.run_dir, self.brief)

  def test_run_dir_must_be_directly_inside_the_store(self):
    self.assert_code(2, self.base, self.store, os.path.join(self.store, "x"))
    nested = os.path.join(self.run_dir, "nested")
    self.write(os.path.join(nested, "brief.md"), "brief\n")
    self.assert_code(2, self.base, nested, os.path.join(nested, "brief.md"))
    self.assert_code(2, self.base, os.path.join(self.store, "missing"), self.brief)
    elsewhere = os.path.join(self.tmp, "elsewhere")
    self.write(os.path.join(elsewhere, "brief.md"), "brief\n")
    self.assert_code(2, self.base, elsewhere, os.path.join(elsewhere, "brief.md"))

  def test_brief_must_be_a_file_in_the_run_dir(self):
    outside = os.path.join(self.store, "brief.md")
    self.write(outside, "brief\n")
    self.assert_code(2, self.base, self.run_dir, outside)
    self.assert_code(2, self.base, self.run_dir, os.path.join(self.run_dir, "missing.md"))

  def test_unsafe_spellings_and_symlinked_paths_are_refused(self):
    for bad in (self.run_dir + "/.", self.run_dir + "/../x", "relative/path",
                self.run_dir + " -s", self.run_dir.replace("/", "//", 1)):
      with self.subTest(bad=bad):
        self.assert_code(2, self.base, bad, self.brief)
    link = os.path.join(self.store, "link")
    os.symlink(self.run_dir, link)
    self.assert_code(2, self.base, link, os.path.join(link, "brief.md"))

  def test_run_store_must_be_set_absolute_and_apart_from_scratch(self):
    os.makedirs(os.path.join(self.parent, "runs"))
    os.chmod(self.parent, 0o700)
    os.symlink(self.tmp, os.path.join(self.tmp, "~"))
    for value in (None, "~/store", "store", os.path.join(self.parent, "runs"),
                  os.path.join(self.home, ".cache")):
      with self.subTest(value=value):
        line = "" if value is None else f'run_store = "{value}"\n'
        self.config(line + f'codex = "{self.codex}"\n')
        with contextlib.chdir(self.tmp):
          self.assert_code(2, self.base, self.run_dir, self.brief)

  def test_run_store_ignores_the_environment(self):
    hostile = {"DRIVER_LAB_RUNS": self.tmp, "XDG_CONFIG_HOME": self.tmp, "HOME": self.tmp}
    elsewhere = os.path.join(self.tmp, "elsewhere")
    self.write(os.path.join(elsewhere, "brief.md"), "brief\n")
    with mock.patch.dict(os.environ, hostile):
      self.assert_code(2, self.base, elsewhere, os.path.join(elsewhere, "brief.md"))
      self.assert_code(0, self.base, self.run_dir, self.brief, "--dry-run")

  def test_codex_must_be_configured_absolute_and_trustworthy(self):
    missing = os.path.join(self.tmp, "bin", "nothing")
    plain = os.path.join(self.tmp, "bin", "plain")
    self.write(plain, "#!/bin/sh\n", 0o644)
    open_to_group = os.path.join(self.tmp, "bin", "loose")
    self.write(open_to_group, "#!/bin/sh\n", 0o775)
    for value in (None, "codex", "bin/codex", missing, plain, open_to_group):
      with self.subTest(value=value):
        line = "" if value is None else f'codex = "{value}"\n'
        self.config(f'run_store = "{self.store}"\n' + line)
        with contextlib.chdir(self.tmp):
          self.assert_code(3, self.base, self.run_dir, self.brief)

  def test_existing_output_paths_are_refused(self):
    for kind in ("log", "last", "patch", "refused"):
      with self.subTest(kind=kind):
        os.symlink(self.home, self.output(kind))
        self.assert_code(2, self.base, self.run_dir, self.brief)
        os.remove(self.output(kind))
    self.assertFalse(os.path.exists(self.env_dump))

  def test_scratch_parent_must_be_private_and_not_a_symlink(self):
    os.makedirs(os.path.dirname(self.parent))
    os.symlink(self.tmp, self.parent)
    self.assert_code(2, self.base, self.run_dir, self.brief)
    os.remove(self.parent)
    os.mkdir(self.parent, 0o755)
    os.chmod(self.parent, 0o755)
    self.assert_code(2, self.base, self.run_dir, self.brief)
    self.assertFalse(os.path.exists(self.env_dump))

  def test_dry_run_prints_command_and_env_and_runs_nothing(self):
    code, out, _ = self.main(self.base, self.run_dir, self.brief, "--dry-run")
    self.assertEqual(code, 0)
    self.assertIn("'--ignore-user-config'", out)
    self.assertIn("'CODEX_HOME'", out)
    self.assertFalse(os.path.exists(self.env_dump))
    self.assertFalse(os.path.exists(self.parent))
    self.assertEqual(os.listdir(self.run_dir), ["brief.md"])

  def test_fixed_command(self):
    cmd = self.mod.command(self.codex, self.base, "/w", self.brief, "/r/last.md")
    self.assertEqual(cmd[0], self.codex)
    exec_at = cmd.index("exec")
    for flag in (["-a", "never"], ["-s", "workspace-write"], ["-c", "mcp_servers={}"],
                 ["-c", "plugins={}"], ["--disable", "hooks"], ["--disable", "multi_agent"],
                 ["--disable", "enable_mcp_apps"]):
      at = next(i for i in range(exec_at) if cmd[i:i + 2] == flag)
      self.assertLess(at, exec_at, flag)
    for flag in ("--ignore-user-config", "--ignore-rules", "--skip-git-repo-check",
                 "--ephemeral", "sandbox_workspace_write.writable_roots=[]",
                 "sandbox_workspace_write.network_access=true",
                 "sandbox_workspace_write.exclude_slash_tmp=true", "model_reasoning_effort=high"):
      self.assertIn(flag, cmd[exec_at:])
    self.assertEqual(cmd[cmd.index("--cd") + 1], "/w")
    self.assertEqual(cmd[cmd.index("--output-last-message") + 1], "/r/last.md")
    self.assertNotIn("--add-dir", cmd)
    self.assertIn(self.base, cmd[-1])
    self.assertIn(self.brief, cmd[-1])
    self.assertIn("not a git checkout", cmd[-1])

  # Environment.

  def test_hostile_parent_environment_does_not_reach_codex_or_git(self):
    hostile_bin = os.path.join(self.tmp, "hostile-bin")
    marker = os.path.join(self.tmp, "hostile-ran")
    self.write(os.path.join(hostile_bin, "codex"), f"#!/bin/sh\ntouch '{marker}'\n", 0o755)
    self.write(os.path.join(hostile_bin, "git"), f"#!/bin/sh\ntouch '{marker}'\n", 0o755)
    hostile_tmp = os.path.join(self.tmp, "hostile-tmp")
    os.mkdir(hostile_tmp)
    hostile = {
        "PATH": hostile_bin + os.pathsep + os.environ["PATH"],
        "CODEX_HOME": os.path.join(self.tmp, "hostile-codex"),
        "TMPDIR": hostile_tmp, "TEMP": hostile_tmp, "TMP": hostile_tmp,
        "HOME": os.path.join(self.tmp, "hostile-home"),
        "GIT_DIR": os.path.join(self.tmp, "nowhere"), "GIT_WORK_TREE": self.tmp,
        "GIT_CONFIG_PARAMETERS": "'core.hooksPath'='/nowhere'", "GIT_INDEX_FILE": "/nowhere",
        "OPENAI_API_KEY": "leak", "SECRET": "leak",
    }
    self.fake_codex("echo hi > fine.txt")
    with mock.patch.dict(os.environ, hostile):
      code, _, err = self.run_codex()
    self.assertEqual(code, 0, err)
    self.assertFalse(os.path.exists(marker))
    self.assertEqual(os.listdir(hostile_tmp), [])
    env = dict(line.split("=", 1) for line in self.read(self.env_dump).splitlines()
               if "=" in line)
    for name in ("PWD", "SHLVL", "_", "OLDPWD"):
      env.pop(name, None)
    tmp = env["TMPDIR"]
    self.assertTrue(tmp.startswith(os.path.realpath(self.parent) + "/run-"), tmp)
    self.assertEqual(env, {
        "HOME": self.home, "CODEX_HOME": os.path.join(self.home, ".codex"),
        "PATH": "/usr/local/bin:/usr/bin:/bin:" + os.path.dirname(self.codex),
        "TMPDIR": tmp, "TEMP": tmp, "TMP": tmp, "LANG": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1", "UV_CACHE_DIR": os.path.join(tmp, "uv-cache"),
    })
    self.assertIn("fine.txt", self.read(self.output("patch")))
    last = self.read(self.env_dump + ".last")
    run_root = os.path.dirname(tmp)
    self.assertEqual(last, os.path.join(run_root, "out", "last-message.md"))
    self.assertEqual(self.read(self.output("last")), "final message\n")

  def test_without_isolated_interpreter_exits_before_doing_anything(self):
    site = os.path.join(self.tmp, "site")
    marker = os.path.join(self.tmp, "sitecustomize-ran")
    self.write(os.path.join(site, "sitecustomize.py"),
               f"open({marker!r}, 'w').close()\n")
    env = dict(os.environ, PYTHONPATH=site)
    plain = subprocess.run([sys.executable, SCRIPT, self.base, self.run_dir, self.brief],
                           env=env, capture_output=True, text=True, check=False)
    self.assertEqual(plain.returncode, 2)
    self.assertIn("python3 -I", plain.stderr)
    self.assertEqual(plain.stdout, "")
    self.assertEqual(os.listdir(self.run_dir), ["brief.md"])
    self.assertTrue(os.path.exists(marker), "the hostile sitecustomize should run without -I")
    os.remove(marker)
    isolated = subprocess.run([sys.executable, "-I", SCRIPT], env=env, capture_output=True,
                              text=True, check=False)
    self.assertEqual(isolated.returncode, 2)
    self.assertIn("usage", isolated.stderr)
    self.assertFalse(os.path.exists(marker))

  # The patch.

  def test_patch_applies_to_a_fresh_checkout_of_base(self):
    snap = os.path.join(self.tmp, "snap")
    self.fake_codex("\n".join((
        "printf 'hello\\nthere\\nworld\\n' > README.md",
        "rm data.txt",
        "chmod +x lib/mod.py",
        "chmod -x tool.sh",
        "mkdir -p lib/sub && printf 'no newline' > lib/sub/new.py",
        "printf 'two\\nlines\\n' > notes.txt",
        f"cp -a \"$PWD\" '{snap}'",
    )))
    code, out, err = self.run_codex()
    self.assertEqual(code, 0, err)
    patch = self.read(self.output("patch"))
    self.assertIn(self.output("patch"), out)
    self.assertIn("deleted file mode 100644", patch)
    self.assertIn("new file mode 100644", patch)
    self.assertIn("old mode 100644\nnew mode 100755", patch)
    self.assertIn("old mode 100755\nnew mode 100644", patch)
    self.assertIn("\\ No newline at end of file", patch)
    self.assertNotIn("readme-link", patch)
    self.assertEqual(self.read(self.output("refused")), "refused: 0\n")
    fresh = os.path.join(self.tmp, "fresh")
    self.git("clone", "-q", self.repo, fresh, cwd=self.tmp)
    self.git("checkout", "-q", self.base, cwd=fresh)
    self.git("apply", "--check", self.output("patch"), cwd=fresh)
    self.git("apply", self.output("patch"), cwd=fresh)
    for rel in ("README.md", "lib/mod.py", "lib/sub/new.py", "notes.txt", "tool.sh"):
      with self.subTest(rel=rel):
        self.assertEqual(self.read(os.path.join(fresh, rel)), self.read(os.path.join(snap, rel)))
        self.assertEqual(os.stat(os.path.join(fresh, rel)).st_mode & 0o100,
                         os.stat(os.path.join(snap, rel)).st_mode & 0o100)
    self.assertFalse(os.path.exists(os.path.join(fresh, "data.txt")))
    self.assertEqual(self.git("status", "--porcelain", "--", "README.md", cwd=fresh),
                     "M README.md")

  def test_no_changes_gives_an_empty_patch(self):
    code, _, err = self.run_codex()
    self.assertEqual(code, 0, err)
    self.assertEqual(self.read(self.output("patch")), "")
    self.assertEqual(self.read(self.output("last")), "final message\n")

  def test_codex_failure_exits_one_and_still_writes_the_patch(self):
    self.fake_codex("echo hi > fine.txt", code=7)
    code, _, _ = self.run_codex()
    self.assertEqual(code, 1)
    self.assertIn("fine.txt", self.read(self.output("patch")))

  def test_each_refusal_kind(self):
    self.fake_codex("\n".join((
        "ln -s /etc/passwd evil.md",
        "rm readme-link && ln -s /etc/passwd readme-link",
        "printf x > .newrc",
        "mkdir .claude && printf '{}' > .claude/settings.json",
        "printf '{}' > .mcp.json",
        "printf 'edit\\n' > .github/ci.yml",
        "printf 'more rules\\n' >> AGENTS.md",
        "mkdir -p sub && printf 'x\\n' > sub/claude.md",
        "head -c 2097153 /dev/zero | tr '\\000' a > big.txt",
        "mkfifo pipe",
        "printf 'a\\000b' > bin.dat",
        "ln README.md hard.md",
        "mkdir __pycache__ && touch __pycache__/x.pyc",
        "printf x > -dash.txt",
        "printf 'ok\\n' > fine.txt",
    )))
    code, _, err = self.run_codex()
    self.assertEqual(code, 0, err)
    refused = dict(line.split("\t", 1) for line in
                   self.read(self.output("refused")).split("\n\n")[0].splitlines()[1:])
    expected = {
        "evil.md": "symlink", "readme-link": "symlink", ".newrc": "dot or unsafe",
        ".claude/": "dot or unsafe", ".mcp.json": "dot or unsafe",
        ".github/ci.yml": "dot or unsafe", "AGENTS.md": "agent instruction",
        "sub/claude.md": "agent instruction", "big.txt": "larger than", "pipe": "FIFO",
        "bin.dat": "binary", "hard.md": "hard link", "__pycache__/": "dot or unsafe",
        "-dash.txt": "dot or unsafe",
    }
    self.assertEqual(set(refused), set(expected))
    for rel, reason in expected.items():
      self.assertIn(reason, refused[rel], rel)
    report = self.read(self.output("refused"))
    self.assertIn("=== AGENTS.md ===", report)
    self.assertIn("+more rules", report)
    patch = self.read(self.output("patch"))
    self.assertEqual([l for l in patch.splitlines() if l.startswith("diff --git")],
                     ["diff --git a/fine.txt b/fine.txt"])

  # Failures.

  @unittest.skipIf(os.geteuid() == 0, "root reads unreadable directories")
  def test_walk_error_is_fatal_and_cleanup_still_runs(self):
    self.fake_codex("mkdir locked && echo x > locked/f && chmod 000 locked")
    code, _, err = self.run_codex()
    self.assertEqual(code, 4)
    self.assertIn("cannot list", err)
    self.assertFalse(os.path.exists(self.output("patch")))
    self.assertFalse(os.path.exists(self.output("refused")))
    self.assertEqual(os.listdir(self.parent), [])

  def test_scratch_root_is_private_and_removed(self):
    seen = os.path.join(self.tmp, "seen")
    self.fake_codex(f"stat -c %a .. > '{seen}'; ls -a .. >> '{seen}'; ls -a . >> '{seen}'")
    code, _, err = self.run_codex()
    self.assertEqual(code, 0, err)
    lines = self.read(seen).split()
    self.assertEqual(lines[0], "700")
    self.assertIn("tmp", lines)
    self.assertNotIn(".git", lines)
    self.assertEqual(os.listdir(self.parent), [])
    self.assertEqual(stat.S_IMODE(os.stat(self.parent).st_mode), 0o700)

  def test_symlink_planted_at_the_final_message_path_is_not_written_through(self):
    target = os.path.join(self.tmp, "victim.md")
    self.write(target, "original\n")
    self.fake_codex(f"ln -s '{target}' '{self.output('last')}'")
    code, _, err = self.run_codex()
    self.assertEqual(code, 4, err)
    self.assertEqual(self.read(target), "original\n")
    self.assertTrue(os.path.islink(self.output("last")))
    self.assertEqual(os.listdir(self.parent), [])

  def test_non_utf8_filename_is_refused_escaped_and_both_outputs_exist(self):
    self.fake_codex("printf x > \"$(printf 'bad\\377name')\"\n"
                    "printf x > \"$(printf 'tab\\tname')\"\n"
                    "printf 'ok\\n' > fine.txt")
    code, _, err = self.run_codex()
    self.assertEqual(code, 0, err)
    report = self.read(self.output("refused"))
    self.assertIn("bad\\xffname\tdot or unsafe", report)
    self.assertIn("tab\\x09name\tdot or unsafe", report)
    patch = self.read(self.output("patch"))
    self.assertEqual([l for l in patch.splitlines() if l.startswith("diff --git")],
                     ["diff --git a/fine.txt b/fine.txt"])
    self.assertEqual(os.listdir(self.parent), [])

  def test_oversized_file_is_accepted_only_when_unchanged(self):
    big = "a" * (2 * 1024 * 1024 + 1)
    self.write(os.path.join(self.repo, "big1.txt"), big)
    self.write(os.path.join(self.repo, "big2.txt"), big)
    self.git("add", "big1.txt", "big2.txt")
    self.git("commit", "-q", "-m", "big")
    self.base = self.git("rev-parse", "HEAD")
    self.fake_codex("printf b | dd of=big1.txt bs=1 count=1 conv=notrunc 2>/dev/null")
    code, _, err = self.run_codex()
    self.assertEqual(code, 0, err)
    report = self.read(self.output("refused"))
    self.assertIn("big1.txt\tlarger than", report)
    self.assertNotIn("big2.txt", report)
    self.assertEqual(self.read(self.output("patch")), "")

  def test_interrupted_wait_kills_the_group_before_cleanup(self):
    child_file = os.path.join(self.tmp, "child")
    self.fake_codex(f"sleep 300 &\necho $! > '{child_file}'\nsleep 1")
    real_remove = self.mod.remove_tree
    seen = {}

    def interrupted(*args):
      del args
      deadline = time.monotonic() + 10
      while not os.path.exists(child_file) and time.monotonic() < deadline:
        time.sleep(0.01)
      raise KeyboardInterrupt

    def remove(root):
      pid = int(self.read(child_file))
      deadline = time.monotonic() + 2
      while alive(pid) and time.monotonic() < deadline:
        time.sleep(0.01)
      seen["alive"] = alive(pid)
      real_remove(root)

    with mock.patch.object(self.mod.os, "waitid", side_effect=interrupted), \
         mock.patch.object(self.mod, "remove_tree", side_effect=remove), \
         contextlib.redirect_stdout(io.StringIO()):
      with self.assertRaises(KeyboardInterrupt):
        self.mod.main([self.base, self.run_dir, self.brief])
    self.assertIs(seen.get("alive"), False)
    self.assertEqual(os.listdir(self.parent), [])

  def test_directory_swapped_for_outward_symlink_during_cleanup_changes_nothing(self):
    outside = os.path.join(self.tmp, "outside")
    self.write(os.path.join(outside, "keep.txt"), "keep\n")
    os.chmod(outside, 0o750)
    self.fake_codex("mkdir victim && echo x > victim/f")
    real_open_dir = self.mod.open_dir

    def swapping(name, dir_fd):
      if name == "victim":
        os.unlink("f", dir_fd=real_open_dir(name, dir_fd))
        os.rmdir(name, dir_fd=dir_fd)
        os.symlink(outside, name, dir_fd=dir_fd)
      return real_open_dir(name, dir_fd)

    with mock.patch.object(self.mod, "open_dir", side_effect=swapping):
      code, _, err = self.run_codex()
    self.assertEqual(code, 0, err)
    self.assertEqual(stat.S_IMODE(os.stat(outside).st_mode), 0o750)
    self.assertEqual(os.listdir(outside), ["keep.txt"])
    self.assertEqual(os.listdir(self.parent), [])

  def test_deep_tree_fails_the_walk_and_is_still_removed(self):
    self.fake_codex('p=deep; i=0\nwhile [ $i -lt 1100 ]; do p="$p/d"; i=$((i+1)); done\n'
                    'mkdir -p "$p" && echo x > "$p/f"')
    code, _, err = self.run_codex()
    self.assertEqual(code, 4, err)
    self.assertIn("deeper than 64", err)
    self.assertFalse(os.path.exists(self.output("patch")))
    self.assertEqual(os.listdir(self.parent), [])

  def test_remove_tree_handles_trees_deeper_than_path_max(self):
    root = os.path.join(self.tmp, "deep-root")
    os.mkdir(root)
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    for _ in range(1500):
      os.mkdir("dd", dir_fd=fd)
      child = os.open("dd", os.O_RDONLY | os.O_DIRECTORY, dir_fd=fd)
      os.close(fd)
      fd = child
    os.close(os.open("f", os.O_WRONLY | os.O_CREAT, 0o600, dir_fd=fd))
    os.fchmod(fd, 0)
    os.close(fd)
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    resource.setrlimit(resource.RLIMIT_NOFILE, (min(256, hard), hard))
    try:
      self.mod.remove_tree(root)
    finally:
      resource.setrlimit(resource.RLIMIT_NOFILE, (soft, hard))
    self.assertFalse(os.path.lexists(root))

  def test_cleanup_failure_exits_four(self):
    self.fake_codex("echo hi > fine.txt")
    with mock.patch.object(self.mod, "remove_tree", side_effect=OSError("boom")):
      code, _, err = self.run_codex()
    self.assertEqual(code, 4)
    self.assertIn("cannot remove scratch root", err)


if __name__ == "__main__":
  unittest.main()
