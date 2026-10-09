# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Run Codex as a milestone implementer in one fixed form; Codex returns a patch.

Usage:
  python3 -I <repo>/utilities/codex-implement.py BASE RUN_DIR BRIEF [--dry-run]

The interpreter must run isolated (-I): otherwise caller-controlled PYTHONPATH, PYTHONSTARTUP or
a user site directory could run code (a sitecustomize.py, say) before any check here. Without -I
the script exits 2 at once; the permission rule allows only the -I form.

BASE     A full 40-hex commit of this repository (the one holding this script).
RUN_DIR  An existing directory directly inside the run store named by `run_store` in
         <home>/.config/driver-lab/config.toml. The home directory comes from the password
         database; HOME, XDG_CONFIG_HOME and DRIVER_LAB_RUNS are ignored. `run_store` must be an
         absolute path (no `~`, not relative).
BRIEF    A file directly inside RUN_DIR; Codex is told to read it and carry it out.

The same config file names the Codex binary as `codex = "<absolute path>"`. It is never looked up
on PATH; without it the script exits 3.

Threat model. The caller is an agent whose permission rule allows only this script, and Codex
is an agent that may be steered by anything it reads, including fetched web content. Neither may
leave anything behind that a later agent, git or the user's tools would load or follow: git hooks
or config, `.git` redirects, `.claude/` settings, `.mcp.json`, agent instruction files, symlinks
pointing out of the tree, or files planted in a place the caller chose. So nothing ever runs in
the tree Codex wrote, and no tree Codex wrote outlives the script:

  1. The script exports BASE itself (`git archive`, run in this repository with a fixed
     environment: no inherited GIT_* variables, no global or system git config, hooks disabled,
     replace objects ignored) and checks the export against `git ls-tree` blob by blob.
  2. The export goes into a fresh 0700 directory made with mkdtemp under the fixed parent
     <home>/.cache/driver-lab-codex/ (created 0700; refused if it is a symlink, not owned by the
     user, or open to group or others). TMPDIR, TEMP and TMP of the caller are never consulted.
     The export has no `.git`. Codex gets it as its working directory, plus a sibling scratch
     TMPDIR; the sandbox may write only those two (`writable_roots=[]`, /tmp excluded). The run
     store may not overlap the scratch parent, so RUN_DIR stays outside the sandbox.
  3. Codex starts with an environment built from scratch (HOME and CODEX_HOME from the password
     database, a fixed PATH, the scratch TMPDIR) and with user config, rules, hooks, MCP servers,
     plugins and sub-agents switched off, so neither the caller's environment nor a planted
     config file can widen the sandbox.
  4. When Codex exits, the script compares the export with BASE in Python, walking both with
     lstat/scandir and never following a link, and never running git or any other program in
     Codex's tree. Any error while walking or reading is fatal and no patch is written.
     Accepted: regular files added, modified or deleted, and the executable bit, under paths
     whose every component matches [A-Za-z0-9][A-Za-z0-9._-]* (no dotfiles or dot-directories
     anywhere, no leading `-`). Refused and left out of the patch: symlinks, devices, FIFOs,
     sockets, hard links, any path with a dot or otherwise unsafe component, binary (NUL or
     non-UTF-8) files, files over 2 MiB, and any change to AGENTS.md, AGENTS.override.md,
     CLAUDE.md, CLAUDE.local.md or GEMINI.md (any case), which needs a human; the refused report
     shows those files' diffs.
  5. Codex's whole process group is killed and its leader reaped before anything else, even
     on an interrupt. Then the scratch root is deleted through directory descriptors, never
     following a link, iteratively however deep it is. A failed cleanup is an error (exit 4).
  6. The inspection walk is iterative and capped at 64 directory levels and 200,000 entries;
     past either cap the run fails (exit 4, no patch) and the tree is still deleted. A file over
     2 MiB is accepted only when it is byte-for-byte unchanged from BASE.
  7. Codex's final message is staged inside the scratch root, in a directory the sandbox cannot
     write, and the script itself publishes it and every other output into RUN_DIR through a
     descriptor opened O_DIRECTORY|O_NOFOLLOW, with O_EXCL|O_NOFOLLOW, so a symlink planted in
     RUN_DIR while Codex runs is refused rather than written through.

Codex's sandbox can still read the whole filesystem, and network access is on, so fetched content
could steer it to send local files out; run it only where that is acceptable.

Outputs, all created exclusively (none may exist beforehand) and printed:
  RUN_DIR/codex-<stamp>.log            Codex's stdout and stderr, written by this script
  RUN_DIR/last-message-<stamp>.md      Codex's final message (its ledger content), staged by the
                                       Codex CLI and published by this script
  RUN_DIR/codex-<stamp>.patch          a `git apply` unified diff of the accepted changes
  RUN_DIR/codex-<stamp>.refused.txt    each refused path and why

The orchestrator reads the patch text and the refused list before running `git apply` in a
milestone worktree cut from BASE; nothing Codex produced runs before that review.

Every path argument must be absolute, already resolved (no symlink component, no `.` or `..`),
and spelled with [A-Za-z0-9._/-] only. With --dry-run the script validates, prints the command
and environment, and neither exports nor runs anything.

Exit codes: 0 Codex exited 0 and the patch was written; 1 Codex exited non-zero (the patch is
still written when the walk succeeds); 2 usage or validation error; 3 codex missing or
misconfigured; 4 an export, walk, read or cleanup failure.
"""

import sys

if __name__ == "__main__" and not sys.flags.isolated:
  print("codex-implement: run me with an isolated interpreter: python3 -I "
        "<repo>/utilities/codex-implement.py BASE RUN_DIR BRIEF", file=sys.stderr)
  sys.exit(2)

# pylint: disable=wrong-import-position
import datetime
import difflib
import errno
import hashlib
import io
import os
import pwd
import re
import shutil
import signal
import stat
import subprocess
import tarfile
import tempfile
import tomllib

SAFE = re.compile(r"/[A-Za-z0-9._/-]+")
COMMIT = re.compile(r"[0-9a-f]{40}")
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
SYSTEM_PATH = "/usr/local/bin:/usr/bin:/bin"
MAX_BYTES = 2 * 1024 * 1024
MAX_DEPTH = 64
MAX_ENTRIES = 200_000
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
AGENT_FILES = frozenset(n.lower() for n in (
    "AGENTS.md", "AGENTS.override.md", "CLAUDE.md", "CLAUDE.local.md", "GEMINI.md"))
REPO = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
PROMPT = (
    "You are working in {work}, an export of commit {base} of the driver-lab repository. It is "
    "not a git checkout: there is no .git directory and you cannot commit. Read {brief} and carry "
    "it out completely in this tree. When you finish, your changes are turned into a patch that "
    "keeps only regular text files with ordinary names: do not create or edit dotfiles or "
    "dot-directories, symlinks, or agent instruction files (AGENTS.md, AGENTS.override.md, "
    "CLAUDE.md, CLAUDE.local.md, GEMINI.md), and keep files under 2 MiB and free of binary "
    "content, because anything else is dropped. Use $TMPDIR for scratch files. You cannot write "
    "the run directory: put what belongs in its ledger into your final message, which is your "
    "report to the orchestrator.")


class Failure(Exception):
  """An export, walk, read or cleanup failure (exit 4)."""


def fail(msg, code=2):
  print(f"codex-implement: {msg}", file=sys.stderr)
  sys.exit(code)


def home():
  return pwd.getpwuid(os.getuid()).pw_dir


def stamp():
  return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def scratch_parent():
  return os.path.join(home(), ".cache", "driver-lab-codex")


def under(path, root):
  return path == root or path.startswith(root.rstrip("/") + "/")


def clean_path(arg, what):
  """Return arg if it is absolute, resolved and safely spelled; exit 2 otherwise."""
  if not SAFE.fullmatch(arg) or "//" in arg:
    fail(f"{what} must be an absolute path of [A-Za-z0-9._/-]: {arg!r}")
  parts = arg.split("/")
  if "." in parts or ".." in parts:
    fail(f"{what} may not contain . or .. components: {arg}")
  if os.path.realpath(arg) != arg.rstrip("/"):
    fail(f"{what} passes through a symlink or is not resolved: {arg}")
  return arg.rstrip("/")


def read_config():
  cfg = os.path.join(home(), ".config", "driver-lab", "config.toml")
  try:
    with open(cfg, "rb") as stream:
      return cfg, tomllib.load(stream)
  except (OSError, tomllib.TOMLDecodeError) as exc:
    fail(f"cannot read {cfg}: {exc}")


def run_store(cfg, data):
  value = data.get("run_store")
  if not isinstance(value, str) or not value:
    fail(f"run_store is not set in {cfg}")
  if not value.startswith("/"):
    fail(f"run_store in {cfg} must be an absolute path (no ~, not relative): {value!r}")
  store = os.path.realpath(value)
  if not os.path.isdir(store):
    fail(f"run store is not a directory: {store}")
  parent = os.path.realpath(scratch_parent())
  if under(store, parent) or under(parent, store):
    fail(f"run store {store} overlaps the Codex scratch parent {parent}")
  return store


def codex_binary(cfg, data):
  """The resolved Codex executable named by `codex` in the config file; exit 3 otherwise."""
  value = data.get("codex")
  if not isinstance(value, str) or not value:
    fail(f"codex is not set in {cfg}; add codex = \"<absolute path to the codex binary>\"", 3)
  if not value.startswith("/"):
    fail(f"codex in {cfg} must be an absolute path: {value!r}", 3)
  path = os.path.realpath(value)
  try:
    st = os.stat(path)
  except OSError as exc:
    fail(f"codex binary {path} is missing: {exc}", 3)
  if not stat.S_ISREG(st.st_mode) or not os.access(path, os.X_OK):
    fail(f"codex binary {path} is not an executable file", 3)
  if st.st_uid not in (os.getuid(), 0):
    fail(f"codex binary {path} is owned by neither you nor root", 3)
  if st.st_mode & 0o022:
    fail(f"codex binary {path} is writable by group or others", 3)
  return path


def git_env():
  return {"PATH": SYSTEM_PATH, "HOME": home(), "LANG": "C.UTF-8", "GIT_CONFIG_NOSYSTEM": "1",
          "GIT_CONFIG_GLOBAL": os.devnull, "GIT_NO_REPLACE_OBJECTS": "1"}


def git(*args):
  exe = shutil.which("git", path=SYSTEM_PATH)
  if exe is None:
    raise Failure(f"git not found on {SYSTEM_PATH}")
  cmd = [exe, "--no-replace-objects", "-c", "core.hooksPath=/dev/null",
         "-c", "core.fsmonitor=false", "-C", REPO, *args]
  return subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, env=git_env(),
                        cwd=REPO, check=False)


def check_base(base):
  if not COMMIT.fullmatch(base):
    fail(f"BASE must be a full 40-hex commit: {base!r}")
  try:
    proc = git("rev-parse", "--verify", "--quiet", f"{base}^{{commit}}")
  except Failure as exc:
    fail(str(exc))
  if proc.returncode != 0 or proc.stdout.decode().strip() != base:
    fail(f"BASE is not a commit of {REPO}: {base}")


def blob_id(data):
  return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def export(base):
  """BASE as {path: ("file", exec, bytes) | ("link", target)}, checked against ls-tree."""
  listing = git("ls-tree", "-r", "-z", "--full-tree", base)
  if listing.returncode != 0:
    raise Failure(f"git ls-tree failed: {listing.stderr.decode(errors='replace').strip()}")
  expected = {}
  for record in listing.stdout.split(b"\0"):
    if not record:
      continue
    meta, path = record.split(b"\t", 1)
    mode, kind, sha = meta.decode().split(" ")
    if kind != "blob":
      raise Failure(f"BASE has a {kind} entry, which the export does not support: {path!r}")
    expected[path.decode("utf-8", "surrogateescape")] = (mode, sha)
  archive = git("archive", "--format=tar", base)
  if archive.returncode != 0:
    raise Failure(f"git archive failed: {archive.stderr.decode(errors='replace').strip()}")
  entries, seen = {}, {}
  with tarfile.open(fileobj=io.BytesIO(archive.stdout), mode="r:") as tar:
    for member in tar:
      name = member.name.rstrip("/")
      if member.isdir():
        continue
      parts = name.split("/")
      if name.startswith("/") or any(p in ("", ".", "..") for p in parts):
        raise Failure(f"unsafe path in the export: {name!r}")
      if member.isreg():
        data = tar.extractfile(member).read()
        executable = bool(member.mode & 0o100)
        entries[name] = ("file", executable, data)
        seen[name] = ("100755" if executable else "100644", blob_id(data))
      elif member.issym():
        entries[name] = ("link", member.linkname)
        seen[name] = ("120000", blob_id(member.linkname.encode("utf-8", "surrogateescape")))
      else:
        raise Failure(f"unexpected entry in the export: {name!r}")
  if seen != expected:
    raise Failure("git archive output does not match git ls-tree for BASE")
  return entries


def extract(entries, work):
  for rel in sorted(entries):
    path = os.path.join(work, rel)
    os.makedirs(os.path.dirname(path), mode=0o755, exist_ok=True)
    entry = entries[rel]
    if entry[0] == "link":
      os.symlink(entry[1], path)
      continue
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as out:
      out.write(entry[2])
      os.fchmod(out.fileno(), 0o755 if entry[1] else 0o644)


def known_dirs(entries):
  dirs = set()
  for rel in entries:
    parts = rel.split("/")
    for i in range(1, len(parts)):
      dirs.add("/".join(parts[:i]))
  return dirs


def safe_name(rel):
  return all(NAME.fullmatch(part) for part in rel.split("/"))


def kind_of(mode):
  for test, name in ((stat.S_ISFIFO, "FIFO"), (stat.S_ISSOCK, "socket"),
                     (stat.S_ISCHR, "character device"), (stat.S_ISBLK, "block device")):
    if test(mode):
      return name
  return "special file"


def read_regular(path, st, base_entry):
  """Read a regular file without following links.

  New content over MAX_BYTES is ("big", size) whatever the baseline's size; a file over the
  limit is accepted only when it is byte-for-byte the baseline, which is checked by streaming
  it against the baseline rather than reading it into memory.
  """
  base_data = base_entry[2] if base_entry and base_entry[0] == "file" else None
  oversized = st.st_size > MAX_BYTES
  if oversized and (base_data is None or len(base_data) != st.st_size):
    return ("big", st.st_size)
  try:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
  except OSError as exc:
    raise Failure(f"cannot open {path}: {exc}") from exc
  try:
    fst = os.fstat(fd)
    if (fst.st_dev, fst.st_ino) != (st.st_dev, st.st_ino) or not stat.S_ISREG(fst.st_mode):
      raise Failure(f"{path} changed while it was being read")
    executable = bool(fst.st_mode & 0o100)
    chunks, size = [], 0
    while True:
      chunk = os.read(fd, 1 << 16)
      if not chunk:
        break
      if oversized:
        if base_data[size:size + len(chunk)] != chunk:
          return ("big", st.st_size)
      else:
        chunks.append(chunk)
      size += len(chunk)
      if size > (len(base_data) if oversized else MAX_BYTES):
        return ("big", size)
  except OSError as exc:
    raise Failure(f"cannot read {path}: {exc}") from exc
  finally:
    os.close(fd)
  if oversized:
    if size != len(base_data):
      return ("big", size)
    entry = ("file", executable, base_data)
  else:
    entry = ("file", executable, b"".join(chunks))
  if st.st_nlink > 1 and entry != base_entry:
    return ("hardlink", st.st_nlink)
  return entry


def walk(root, base):
  """Codex's tree as {path: entry}, plus new directories skipped for their names.

  Iterative, with an explicit stack; deeper than MAX_DEPTH or more than MAX_ENTRIES entries is
  a Failure.
  """
  dirs, found, skipped = known_dirs(base), {}, []
  stack, count = [""], 0
  while stack:
    rel_dir = stack.pop()
    top = os.path.join(root, rel_dir) if rel_dir else root
    try:
      with os.scandir(top) as it:
        names = sorted(entry.name for entry in it)
    except OSError as exc:
      raise Failure(f"cannot list {top}: {exc}") from exc
    count += len(names)
    if count > MAX_ENTRIES:
      raise Failure(f"Codex's tree has more than {MAX_ENTRIES} entries")
    for name in names:
      rel = f"{rel_dir}/{name}" if rel_dir else name
      path = os.path.join(top, name)
      try:
        st = os.lstat(path)
      except OSError as exc:
        raise Failure(f"cannot lstat {path}: {exc}") from exc
      if stat.S_ISDIR(st.st_mode):
        if not (rel in dirs or safe_name(rel)):
          skipped.append(rel)
        elif rel.count("/") + 1 >= MAX_DEPTH:
          raise Failure(f"Codex's tree is deeper than {MAX_DEPTH} directories: {rel[:200]}")
        else:
          stack.append(rel)
      elif stat.S_ISLNK(st.st_mode):
        try:
          found[rel] = ("link", os.readlink(path))
        except OSError as exc:
          raise Failure(f"cannot read link {path}: {exc}") from exc
      elif stat.S_ISREG(st.st_mode):
        found[rel] = read_regular(path, st, base.get(rel))
      else:
        found[rel] = ("other", kind_of(st.st_mode))
  return found, skipped


def text_of(entry):
  """The entry's content as text, or None when it is binary (NUL or not UTF-8)."""
  if entry is None:
    return ""
  data = entry[2]
  if b"\0" in data:
    return None
  try:
    return data.decode("utf-8")
  except UnicodeDecodeError:
    return None


def refusal(rel, old, new):
  if not safe_name(rel):
    return "dot or unsafe path component"
  if rel.rsplit("/", 1)[-1].lower() in AGENT_FILES:
    return "agent instruction file: needs a human"
  if new is not None:
    if new[0] == "link":
      return "symlink"
    if new[0] == "other":
      return new[1]
    if new[0] == "hardlink":
      return "hard link"
    if new[0] == "big":
      return f"larger than {MAX_BYTES} bytes"
  if old is not None and old[0] == "link":
    return "replaces or deletes a symlink"
  if text_of(old) is None or text_of(new) is None:
    return "binary file"
  return None


def split_lines(text):
  parts = text.split("\n")
  out = [part + "\n" for part in parts[:-1]]
  if parts[-1]:
    out.append(parts[-1])
  return out


def hunks(old_text, new_text, old_name, new_name):
  out = []
  for line in difflib.unified_diff(split_lines(old_text), split_lines(new_text), old_name,
                                   new_name, n=3):
    out.append(line)
    if not line.endswith("\n"):
      out.append("\n\\ No newline at end of file\n")
  return out


def file_diff(rel, old, new):
  def mode(entry):
    return "100755" if entry[1] else "100644"

  out = [f"diff --git a/{rel} b/{rel}\n"]
  if old is None:
    out.append(f"new file mode {mode(new)}\n")
  elif new is None:
    out.append(f"deleted file mode {mode(old)}\n")
  elif old[1] != new[1]:
    out += [f"old mode {mode(old)}\n", f"new mode {mode(new)}\n"]
  old_text, new_text = text_of(old), text_of(new)
  if old_text != new_text:
    out += hunks(old_text, new_text, f"a/{rel}" if old else "/dev/null",
                 f"b/{rel}" if new else "/dev/null")
  return "".join(out)


def compare(base, tree, skipped):
  """(patch text, refused report text, accepted count, refused count)."""
  patch, refused, diffs = [], [], []
  for rel in sorted(set(base) | set(tree)):
    old, new = base.get(rel), tree.get(rel)
    if old == new:
      continue
    reason = refusal(rel, old, new)
    if reason is None:
      patch.append(file_diff(rel, old, new))
      continue
    refused.append(f"{rel}\t{reason}\n")
    if reason.startswith("agent instruction"):
      plain = all(e is None or (e[0] == "file" and text_of(e) is not None) for e in (old, new))
      diffs.append(f"=== {rel} ===\n" + (file_diff(rel, old, new) if plain else
                                         "(not a plain text file; inspect by hand)\n"))
  for rel in sorted(skipped):
    refused.append(f"{rel}/\tnew directory with a dot or unsafe name (contents not read)\n")
  report = [f"refused: {len(refused)}\n", *refused]
  if diffs:
    report += ["\nDiffs of refused agent instruction files:\n", *diffs]
  return "".join(patch), "".join(report), len(patch), len(refused)




class LaunchError(Exception):
  """Codex could not be started (exit 3)."""


def publish(dir_fd, name, data):
  """Create name in the pinned directory dir_fd exclusively, never through a link."""
  fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=dir_fd)
  with os.fdopen(fd, "wb") as out:
    out.write(data)


def read_staged(path):
  """The final message Codex staged in the private out directory, or None if there is none."""
  try:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
  except FileNotFoundError:
    return None
  with os.fdopen(fd, "rb") as staged:
    if not stat.S_ISREG(os.fstat(staged.fileno()).st_mode):
      raise Failure(f"staged final message is not a regular file: {path}")
    return staged.read()


def open_dir(name, dir_fd):
  """Open a subdirectory of dir_fd for removal, making it readable first; never follow a link.

  chmod with follow_symlinks=False refuses a symlink rather than following it, and the open uses
  O_NOFOLLOW, so a directory swapped for a link fails here instead of reaching outside.
  """
  try:
    os.chmod(name, 0o700, dir_fd=dir_fd, follow_symlinks=False)
  except (OSError, ValueError, NotImplementedError):
    pass
  return os.open(name, DIR_FLAGS, dir_fd=dir_fd)


def remove_tree(root):
  """Delete root through directory descriptors, iteratively, never following a link.

  Each frame is [parent fd, name, fd, remaining names]. Below MAX_DEPTH a directory is renamed
  up into root before it is entered, so the stack and the open descriptors stay bounded however
  deep the tree is. Raises OSError on failure.
  """
  parent_fd = os.open(os.path.dirname(root), DIR_FLAGS)
  stack, flattened = [], 0
  try:
    stack.append([parent_fd, os.path.basename(root), open_dir(os.path.basename(root), parent_fd),
                  None])
    while stack:
      frame = stack[-1]
      parent, name, fd, names = frame
      if names is None:
        names = frame[3] = os.listdir(fd)
      if not names:
        stack.pop()
        os.close(fd)
        os.rmdir(name, dir_fd=parent)
        continue
      child = names.pop()
      st = os.stat(child, dir_fd=fd, follow_symlinks=False)
      if not stat.S_ISDIR(st.st_mode):
        os.unlink(child, dir_fd=fd)
        continue
      if len(stack) >= MAX_DEPTH:
        flattened += 1
        moved = f"flattened-{flattened}"
        os.rename(child, moved, src_dir_fd=fd, dst_dir_fd=stack[0][2])
        stack[0][3].append(moved)
        continue
      try:
        child_fd = open_dir(child, fd)
      except OSError as exc:
        if exc.errno not in (errno.ELOOP, errno.ENOTDIR):
          raise
        os.unlink(child, dir_fd=fd)
        continue
      stack.append([fd, child, child_fd, None])
  finally:
    for frame in stack:
      os.close(frame[2])
    os.close(parent_fd)


def stop(proc):
  """Kill Codex's whole process group, then reap the leader, even if interrupted again."""
  try:
    os.killpg(proc.pid, signal.SIGKILL)
  except (ProcessLookupError, PermissionError):
    pass
  while True:
    try:
      proc.wait()
      return
    except KeyboardInterrupt:
      continue


def child_env(codex, tmp):
  h = home()
  return {
      "HOME": h, "CODEX_HOME": os.path.join(h, ".codex"),
      "PATH": SYSTEM_PATH + ":" + os.path.dirname(codex),
      "TMPDIR": tmp, "TEMP": tmp, "TMP": tmp, "LANG": "C.UTF-8",
      "PYTHONDONTWRITEBYTECODE": "1", "UV_CACHE_DIR": os.path.join(tmp, "uv-cache"),
  }


def command(codex, base, work, brief, last):
  return [
      codex, "-a", "never", "-s", "workspace-write",
      "-c", "mcp_servers={}", "-c", "plugins={}",
      "--disable", "hooks", "--disable", "multi_agent", "--disable", "enable_mcp_apps",
      "exec", "--ignore-user-config", "--ignore-rules", "--skip-git-repo-check", "--ephemeral",
      "-c", "sandbox_workspace_write.writable_roots=[]",
      "-c", "sandbox_workspace_write.network_access=true",
      "-c", "sandbox_workspace_write.exclude_slash_tmp=true",
      "-c", "sandbox_workspace_write.exclude_tmpdir_env_var=false",
      "-c", "model_reasoning_effort=high",
      "--cd", work, "--output-last-message", last,
      PROMPT.format(work=work, base=base, brief=brief),
  ]


def check_parent(create_it):
  parent = scratch_parent()
  if create_it:
    os.makedirs(os.path.dirname(parent), mode=0o700, exist_ok=True)
    try:
      os.mkdir(parent, 0o700)
    except FileExistsError:
      pass
  try:
    st = os.lstat(parent)
  except FileNotFoundError:
    return parent
  if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
    fail(f"scratch parent {parent} is a symlink or not a directory")
  if st.st_uid != os.getuid():
    fail(f"scratch parent {parent} is not owned by you")
  if st.st_mode & 0o077:
    fail(f"scratch parent {parent} is open to group or others")
  return parent


def prepare(base, run_dir, brief, when):
  if not COMMIT.fullmatch(base):
    fail(f"BASE must be a full 40-hex commit: {base!r}")
  run_dir = clean_path(run_dir, "RUN_DIR")
  brief = clean_path(brief, "BRIEF")
  cfg, data = read_config()
  store = run_store(cfg, data)
  if os.path.dirname(run_dir) != store or not os.path.isdir(run_dir):
    fail(f"RUN_DIR must be an existing directory directly inside {store}: {run_dir}")
  if os.path.dirname(brief) != run_dir or not os.path.isfile(brief):
    fail(f"BRIEF must be a file directly inside RUN_DIR: {brief}")
  outputs = {key: os.path.join(run_dir, name) for key, name in (
      ("log", f"codex-{when}.log"), ("last", f"last-message-{when}.md"),
      ("patch", f"codex-{when}.patch"), ("refused", f"codex-{when}.refused.txt"))}
  for path in outputs.values():
    if os.path.lexists(path):
      fail(f"output path already exists: {path}")
  check_base(base)
  codex = codex_binary(cfg, data)
  return base, brief, codex, outputs


def run(base, brief, codex, outputs):
  parent = check_parent(True)
  run_dir = os.path.dirname(outputs["log"])
  try:
    run_fd = os.open(run_dir, DIR_FLAGS)
  except OSError as exc:
    fail(f"cannot open RUN_DIR without following links: {exc}")
  root = os.path.realpath(tempfile.mkdtemp(prefix="run-", dir=parent))
  work, tmp, out = (os.path.join(root, name) for name in ("work", "tmp", "out"))
  staged = os.path.join(out, "last-message.md")
  name = {key: os.path.basename(path) for key, path in outputs.items()}
  status = 4
  try:
    for path in (work, tmp, out):
      os.mkdir(path, 0o700)
    entries = export(base)
    extract(entries, work)
    print(f"log: {outputs['log']}\nlast message: {outputs['last']}", flush=True)
    log_fd = os.open(name["log"], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600,
                     dir_fd=run_fd)
    with os.fdopen(log_fd, "w", encoding="utf-8") as log:
      try:
        proc = subprocess.Popen(command(codex, base, work, brief, staged),
                                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                env=child_env(codex, tmp), cwd=work, start_new_session=True)
      except OSError as exc:
        raise LaunchError(f"cannot start {codex}: {exc}") from exc
      try:
        os.waitid(os.P_PID, proc.pid, os.WEXITED | os.WNOWAIT)
      finally:
        stop(proc)
    tree, skipped = walk(work, entries)
    patch, report, accepted, refused = compare(entries, tree, skipped)
    publish(run_fd, name["patch"], patch.encode("utf-8"))
    publish(run_fd, name["refused"], report.encode("utf-8"))
    print(f"patch: {outputs['patch']} ({accepted} file(s))\n"
          f"refused: {outputs['refused']} ({refused} path(s))", flush=True)
    message = read_staged(staged)
    if message is None:
      print("codex-implement: Codex left no final message", file=sys.stderr)
    else:
      publish(run_fd, name["last"], message)
    status = 0 if proc.returncode == 0 else 1
  except LaunchError as exc:
    print(f"codex-implement: {exc}", file=sys.stderr)
    status = 3
  except Failure as exc:
    print(f"codex-implement: {exc}; no patch written", file=sys.stderr)
    status = 4
  except OSError as exc:
    print(f"codex-implement: {exc}", file=sys.stderr)
    status = 4
  finally:
    try:
      remove_tree(root)
    except OSError as exc:
      print(f"codex-implement: cannot remove scratch root {root}: {exc}", file=sys.stderr)
      status = 4
    finally:
      os.close(run_fd)
  return status


def main(argv):
  dry = "--dry-run" in argv
  args = [a for a in argv if a != "--dry-run"]
  if len(args) != 3:
    fail("usage: python3 -I codex-implement.py BASE RUN_DIR BRIEF [--dry-run]")
  base, brief, codex, outputs = prepare(*args, stamp())
  if dry:
    check_parent(False)
    print(command(codex, base, "<scratch>/work", brief, "<scratch>/out/last-message.md"))
    print(child_env(codex, "<scratch>/tmp"))
    return 0
  return run(base, brief, codex, outputs)


if __name__ == "__main__":
  sys.exit(main(sys.argv[1:]))
