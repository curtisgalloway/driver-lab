#!/bin/sh
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
#
# Install a pinned driver-lab release binary (or build from source at a pinned git revision)
# and verify its embedded DRIVER_LAB_TOOL_COMMIT handshake (ENV-6).
#
# Usage:
#   ./install.sh --version <vX.Y.Z> [--commit <40-hex-sha>] [--sha256 <64-hex>]
#                [--install-dir <dir>] [--repo <owner/repo>] [--base-url <url>]
#   ./install.sh --from-source --rev <40-hex-sha> [--install-dir <dir>] [--repo <owner/repo>]
#
# Environment overrides:
#   DRIVER_LAB_VERSION      default release tag when --version is omitted
#   DRIVER_LAB_TOOL_COMMIT  expected 40-hex tool commit when --commit / --rev is omitted
#   DRIVER_LAB_SHA256       caller-pinned 64-hex SHA-256 of the release tarball
#   DRIVER_LAB_INSTALL_DIR  target bin directory (default: $HOME/.local/bin)
#   DRIVER_LAB_REPO         GitHub owner/repo (default: curtisgalloway/driver-lab)
#   DRIVER_LAB_BASE_URL     release asset base URL override (for mirrors or offline tests)
#
# Exit codes: 0 installed and verified, 2 usage error, 3 missing precondition or verification failure.

set -eu

usage() {
  cat >&2 <<'EOF'
usage: install.sh --version <vX.Y.Z> [--commit <40-hex-sha>] [--sha256 <64-hex>] [--install-dir <dir>] [--repo <owner/repo>] [--base-url <url>]
       install.sh --from-source --rev <40-hex-sha> [--install-dir <dir>] [--repo <owner/repo>]
EOF
  exit 2
}

is_hex40() {
  case "$1" in
    [0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F])
      [ "${#1}" -eq 40 ]
      ;;
    *)
      return 1
      ;;
  esac
}

is_hex64() {
  case "$1" in
    *[!0-9a-fA-F]* | "") return 1 ;;
    *) [ "${#1}" -eq 64 ] ;;
  esac
}

compute_sha256() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print tolower($1)}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print tolower($1)}'
  else
    echo "missing precondition: neither sha256sum nor shasum is installed" >&2
    exit 3
  fi
}

detect_target() {
  if [ -n "${DRIVER_LAB_TARGET:-}" ]; then
    printf '%s\n' "$DRIVER_LAB_TARGET"
    return 0
  fi
  os_name=$(uname -s 2>/dev/null || echo unknown)
  arch_name=$(uname -m 2>/dev/null || echo unknown)
  case "$os_name:$arch_name" in
    Linux:x86_64 | Linux:amd64)
      printf 'x86_64-unknown-linux-gnu\n'
      ;;
    Linux:aarch64 | Linux:arm64)
      printf 'aarch64-unknown-linux-gnu\n'
      ;;
    Darwin:x86_64)
      printf 'x86_64-apple-darwin\n'
      ;;
    Darwin:arm64 | Darwin:aarch64)
      printf 'aarch64-apple-darwin\n'
      ;;
    *)
      echo "missing precondition: unsupported platform '$os_name/$arch_name' (supported: Linux/Darwin on x86_64/aarch64)" >&2
      exit 3
      ;;
  esac
}

fetch_url() {
  src_url=$1
  dest_file=$2
  case "$src_url" in
    file://*)
      local_path=${src_url#file://}
      if [ ! -f "$local_path" ]; then
        echo "missing precondition: file not found at $src_url" >&2
        exit 3
      fi
      cp "$local_path" "$dest_file"
      ;;
    https://*)
      if ! command -v curl >/dev/null 2>&1; then
        echo "missing precondition: curl is required to download release artifacts" >&2
        exit 3
      fi
      if ! curl --proto '=https' --tlsv1.2 -fsSL --retry 3 "$src_url" -o "$dest_file"; then
        echo "missing precondition: failed to download $src_url" >&2
        exit 3
      fi
      ;;
    *)
      echo "usage: unsupported URL scheme in '$src_url' (only https:// and file:// are permitted)" >&2
      exit 2
      ;;
  esac
}

version="${DRIVER_LAB_VERSION:-}"
commit="${DRIVER_LAB_TOOL_COMMIT:-}"
sha256="${DRIVER_LAB_SHA256:-}"
install_dir="${DRIVER_LAB_INSTALL_DIR:-${HOME:-/tmp}/.local/bin}"
repo="${DRIVER_LAB_REPO:-curtisgalloway/driver-lab}"
base_url="${DRIVER_LAB_BASE_URL:-}"
from_source=0
source_path=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --version)
      [ "$#" -ge 2 ] || usage
      version=$2
      shift 2
      ;;
    --commit | --rev)
      [ "$#" -ge 2 ] || usage
      commit=$2
      shift 2
      ;;
    --sha256)
      [ "$#" -ge 2 ] || usage
      sha256=$2
      shift 2
      ;;
    --install-dir)
      [ "$#" -ge 2 ] || usage
      install_dir=$2
      shift 2
      ;;
    --repo)
      [ "$#" -ge 2 ] || usage
      repo=$2
      shift 2
      ;;
    --base-url)
      [ "$#" -ge 2 ] || usage
      base_url=$2
      shift 2
      ;;
    --from-source)
      from_source=1
      shift
      ;;
    --path)
      [ "$#" -ge 2 ] || usage
      source_path=$2
      shift 2
      ;;
    -h | --help)
      usage
      ;;
    *)
      usage
      ;;
  esac
done

if [ -n "$commit" ] && ! is_hex40 "$commit"; then
  echo "usage: --commit / --rev must be a 40-character hexadecimal git commit SHA" >&2
  exit 2
fi

if [ -n "$sha256" ] && ! is_hex64 "$sha256"; then
  echo "usage: --sha256 must be a 64-character hexadecimal SHA-256 digest" >&2
  exit 2
fi

if [ "$from_source" -eq 1 ]; then
  if [ -z "$commit" ]; then
    echo "usage: --from-source requires --rev <40-hex-sha> (or DRIVER_LAB_TOOL_COMMIT)" >&2
    exit 2
  fi
  if ! command -v cargo >/dev/null 2>&1; then
    echo "missing precondition: cargo is required for --from-source" >&2
    exit 3
  fi
  tmp_root=$(mktemp -d)
  trap 'rm -rf "$tmp_root"' EXIT INT TERM
  if [ -n "$source_path" ]; then
    DRIVER_LAB_TOOL_COMMIT="$commit" cargo install --locked --force \
      --path "$source_path" --root "$tmp_root/install"
  else
    DRIVER_LAB_TOOL_COMMIT="$commit" cargo install --locked --force \
      --git "https://github.com/$repo.git" --rev "$commit" --root "$tmp_root/install"
  fi
  mkdir -p "$install_dir"
  cp "$tmp_root/install/bin/driver-lab" "$install_dir/driver-lab.tmp.$$"
  chmod 0755 "$install_dir/driver-lab.tmp.$$"
  mv "$install_dir/driver-lab.tmp.$$" "$install_dir/driver-lab"
else
  if [ -z "$version" ]; then
    echo "usage: --version <vX.Y.Z> is required unless --from-source is used" >&2
    exit 2
  fi
  target=$(detect_target)
  archive_name="driver-lab-${target}.tar.gz"
  if [ -z "$base_url" ]; then
    base_url="https://github.com/${repo}/releases/download/${version}"
  fi
  base_url=${base_url%/}

  tmp_dir=$(mktemp -d)
  trap 'rm -rf "$tmp_dir"' EXIT INT TERM

  archive_path="$tmp_dir/$archive_name"
  fetch_url "${base_url}/${archive_name}" "$archive_path"

  if [ -n "$sha256" ]; then
    expected_sha=$(printf '%s' "$sha256" | tr 'A-F' 'a-f')
  else
    sha_file="$tmp_dir/${archive_name}.sha256"
    fetch_url "${base_url}/${archive_name}.sha256" "$sha_file"
    expected_sha=$(awk '{print tolower($1)}' "$sha_file")
    if ! is_hex64 "$expected_sha"; then
      echo "missing precondition: invalid SHA-256 digest in ${base_url}/${archive_name}.sha256" >&2
      exit 3
    fi
  fi

  actual_sha=$(compute_sha256 "$archive_path")
  if [ "$actual_sha" != "$expected_sha" ]; then
    echo "missing precondition: SHA-256 mismatch for $archive_name (expected $expected_sha, got $actual_sha)" >&2
    exit 3
  fi

  mkdir -p "$tmp_dir/extract"
  tar -xzf "$archive_path" -C "$tmp_dir/extract"
  bin_candidate="$tmp_dir/extract/driver-lab-${target}/driver-lab"
  if [ ! -f "$bin_candidate" ]; then
    bin_candidate="$tmp_dir/extract/driver-lab"
  fi
  if [ ! -f "$bin_candidate" ]; then
    echo "missing precondition: driver-lab binary not found in archive $archive_name" >&2
    exit 3
  fi

  mkdir -p "$install_dir"
  cp "$bin_candidate" "$install_dir/driver-lab.tmp.$$"
  chmod 0755 "$install_dir/driver-lab.tmp.$$"
  mv "$install_dir/driver-lab.tmp.$$" "$install_dir/driver-lab"
fi

installed_bin="$install_dir/driver-lab"
ver_out=$("$installed_bin" --version 2>&1) || {
  echo "missing precondition: installed binary $installed_bin failed --version check" >&2
  exit 3
}

if [ -n "$commit" ]; then
  case "$ver_out" in
    *"($commit)"*) ;;
    *)
      echo "missing precondition: version handshake failed: '$ver_out' does not contain commit ($commit)" >&2
      exit 3
      ;;
  esac
fi

printf '%s\n' "$ver_out"
