#!/bin/bash
# SPDX-FileCopyrightText: 2026 Curtis Galloway
# SPDX-License-Identifier: Apache-2.0
#
# Run an implementer agent in a Linux read-isolation sandbox, with every file and
# process syscall logged. Tier 1 of cleanroom-implementer (see SKILL.md, "Tier 1 on
# Linux").
#
#   cleanroom_sandbox.sh --workspace DIR --home DIR --tool-dir DIR --log FILE \
#       [--env NAME=VALUE]... -- COMMAND [ARG]...
#
# Inside the sandbox the process sees only:
#   /work        the workspace, read-write (and the working directory)
#   /agent-home  the agent's own state (credentials, config, sessions), read-write
#   /opt/agent   the agent's executables, read-only, first on PATH
#   /usr, /etc and the resolver directory, read-only, with /usr/src and
#   /usr/lib/modules hidden
# /home, /root, /tmp, /opt, /srv, /mnt and /media are empty. The environment is
# cleared; HOME is /agent-home, and --env adds more (for Codex: CODEX_HOME=/agent-home).
# --env values appear on bubblewrap's command line (visible to `ps`) and in the log, so
# never pass a secret that way: credentials go in the agent home. The sandbox runs in
# a new session, so it cannot inject input into the operator's terminal.
# The network is shared, because the agent must reach its model API: egress is
# audited from the log (connect and send calls), not blocked.
#
# The log is strace output for the whole process tree; audit it with
# sandbox_audit.py. The script refuses to overwrite an existing log, so each attempt
# keeps its own. Exits 2 when bubblewrap or strace is missing, an argument is wrong,
# or the log exists; otherwise exits with the command's status.
set -u

usage() {
  sed -n '9,10p' "$0" >&2
  exit 2
}

workspace= home= tooldir= log=
envs=()
while [ $# -gt 0 ]; do
  case "$1" in
    --workspace|--home|--tool-dir|--log|--env) [ $# -ge 2 ] || usage ;;
  esac
  case "$1" in
    --workspace) workspace="${2:-}"; shift 2 ;;
    --home) home="${2:-}"; shift 2 ;;
    --tool-dir) tooldir="${2:-}"; shift 2 ;;
    --log) log="${2:-}"; shift 2 ;;
    --env)
      case "${2:-}" in *=*) ;; *) echo "--env needs NAME=VALUE" >&2; exit 2 ;; esac
      envs+=(--setenv "${2%%=*}" "${2#*=}"); shift 2 ;;
    --) shift; break ;;
    *) usage ;;
  esac
done
[ $# -gt 0 ] || usage
for d in "$workspace" "$home" "$tooldir"; do
  [ -n "$d" ] && [ -d "$d" ] || { echo "not a directory: '$d'" >&2; exit 2; }
done
[ -n "$log" ] || usage
[ -e "$log" ] && { echo "log exists, refusing to overwrite: '$log'" >&2; exit 2; }
for tool in bwrap strace; do
  command -v "$tool" >/dev/null || { echo "$tool not found" >&2; exit 2; }
done

resolver=()
[ -d /run/systemd/resolve ] && resolver=(--ro-bind /run/systemd/resolve /run/systemd/resolve)

exec strace -f -qq -y -e trace=%file,%process,%network -o "$log" \
  bwrap --die-with-parent --new-session --clearenv --unshare-pid --unshare-ipc --unshare-uts \
    --ro-bind /usr /usr --tmpfs /usr/src --tmpfs /usr/lib/modules \
    --symlink usr/bin /bin --symlink usr/lib /lib --symlink usr/lib64 /lib64 \
    --symlink usr/sbin /sbin \
    --ro-bind /etc /etc "${resolver[@]}" \
    --proc /proc --dev /dev --tmpfs /tmp --tmpfs /home --tmpfs /root --tmpfs /opt \
    --tmpfs /srv --tmpfs /mnt --tmpfs /media \
    --ro-bind "$tooldir" /opt/agent \
    --bind "$workspace" /work --bind "$home" /agent-home \
    --setenv HOME /agent-home --setenv PATH /opt/agent:/usr/bin:/usr/sbin \
    --setenv TERM dumb --setenv LANG C.UTF-8 "${envs[@]}" \
    --chdir /work \
    "$@"
