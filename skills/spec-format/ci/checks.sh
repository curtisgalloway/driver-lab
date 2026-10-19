#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
#
# The checks CI runs (.github/workflows/checks.yml), runnable locally from the top of the
# repository. specs/ is a spec format root; the contract is driver-lab's
# skills/spec-format/SKILL.md and the tool is driver-lab (or skills/spec-format/scripts/spec.py).
#
#   scripts/checks.sh [--mode pr|main] <step> <driver-lab checkout> [<further root>...]
#
# Steps:
#   check      check specs (further roots as --context-root, --stubs-from when STUBS_DIR or
#              skills/*/SKILL.md is present) --require-license --require-verified <mode>:
#              nothing lands unverified or with a stale record; when DOMAINS_MANIFEST or
#              domains.yaml is present, also runs stubgen --check; with REQUIRE_CORPUS=1, also
#              runs corpus specs: the root must keep a corpus ledger (specs/corpus.yaml), every
#              document and block with a disposition
#   resolve    resolve on every spec under specs/, auto-binding cache/<name> when it is a
#              non-partial git clone containing the pinned commit (BF-GW-23), so each pinned
#              repository a spec cites is checked (RESOLVE_SRC=1 only, below); specs without
#              repos entries resolve nothing
#   render     render, Markdown view and viewer (--format md and html), each file's own
#              view and, when further roots are given, the merged views; a view that cannot be
#              built fails the step
#   self-test  prove the license gate with this repository's root marker on driver-lab's
#              the spec format fixtures (below)
#   all        the four in order
#
# --mode is the verification policy (design D19). pr (the default): every fact must be current,
# and a fact staled through a reference into a further root is an error. main: such an
# upstream-stale fact is a warning, so an upstream merge never turns this repository's main red;
# the next pull request here must re-verify it. CI passes pr on pull requests, main otherwise.
#
# A further root is another spec root read beside specs/ so that overlays and references
# resolve. It is context only: its findings are not reported here as such, but its own errors
# make the root untrusted, and a reference into an untrusted root then fails here. hardware-specs-docs passes none; hardware-specs-permissive requires one,
# hardware-specs-docs' specs/; hardware-specs-gpl requires two, hardware-specs-docs' specs/ then
# hardware-specs-permissive's specs/.
#
# RESOLVE_SRC=1 (CI sets it) makes the resolve step fetch each cited repository at its pinned
# commit over HTTPS (unless already bound from a valid full clone in cache/<name>). An entry
# whose fetch exceeds SRC_FETCH_LIMIT_MB (default 50) or the fetch timeout is skipped and
# counted in the summary; any other failure (a commit, file or symbol that does not exist, a
# license line that disagrees) fails the step. The limit bounds what is kept, not what is
# transferred. Unset, resolve fetches nothing and says so.
#
# Needs bash 3.2 or later and either DRIVER_LAB_BIN or a Python with driver-lab's
# skills/spec-format/requirements.txt installed with pip's --require-hashes:
#   python3 -m venv .venv-spec
#   .venv-spec/bin/pip install --require-hashes -r <driver-lab>/skills/spec-format/requirements.txt
#   CHECKS_PYTHON=.venv-spec/bin/python scripts/checks.sh all <driver-lab>
#
# Exit codes: 0 passed, 1 a check failed, 2 usage error, 3 missing precondition.
set -euo pipefail

# Copy to scripts/checks.sh; configure this block using ci/README.md.
REPO=hardware-specs-docs
# This repository's self-test fixtures, from driver-lab's
# skills/spec-format/tests/fixtures/license-gate/ (its README lists the matrix). Specs for the
# gate, each alone in a root under this repository's marker:
FIT=docs-named.spec.yaml
MISFIT=gpl-only.spec.yaml
# Board-spec overlays, each placed beside board/widgetchip.spec.yaml (an empty BOARD_FIT
# checks widgetchip.spec.yaml alone):
BOARD_FIT=
BOARD_MISFIT=widgetchip-bsd-overlay.spec.yaml
# Further licenses this marker accepts, proved with bsd.spec.yaml's BSD-3-Clause replaced:
EXTRA_FIT_LICENSES=
# How many further roots every step needs (the first is always the docs repository's specs/),
# so the cross-repository overlay check never silently skips.
REQUIRE_FURTHER=0
# widgetchip-src-overlay.spec.yaml (a src fact read from BSD-3-Clause source) beside
# widgetchip.spec.yaml: 1 when this repository's marker accepts it, 0 when it must fail the gate.
SRC_FIT=0

usage() {
  echo "usage: scripts/checks.sh [--mode pr|main] check|resolve|render|self-test|all" \
    "<driver-lab checkout> [<further root>...]" >&2
  exit 2
}

mode=pr
if [ "${1:-}" = --mode ]; then
  [ "$#" -ge 2 ] || usage
  mode=$2
  shift 2
fi
case "$mode" in
  pr | main) ;;
  *) usage ;;
esac
[ "$#" -ge 2 ] || usage
step=$1
dl=$2
shift 2
further=("$@")
case "$step" in
  check | resolve | render | self-test | all) ;;
  *) usage ;;
esac
if [ "${#further[@]}" -lt "$REQUIRE_FURTHER" ]; then
  echo "usage: $REPO needs $REQUIRE_FURTHER further root(s), in the order the header lists" >&2
  exit 2
fi

SPEC=$dl/skills/spec-format/scripts/spec.py
STUBGEN=$dl/skills/board-spec-scaffold/scripts/stubgen.py
REQUIREMENTS=$dl/skills/spec-format/requirements.txt
FIXTURES=$dl/skills/spec-format/tests/fixtures/license-gate

needed=("$FIXTURES/specs/$FIT" "$FIXTURES/specs/$MISFIT"
  "$FIXTURES/specs/bsd.spec.yaml" "$FIXTURES/board/widgetchip.spec.yaml"
  "$FIXTURES/board/$BOARD_MISFIT" "$FIXTURES/board/widgetchip-src-overlay.spec.yaml"
  "$FIXTURES/board/widgetchip-bsd-overlay.spec.yaml")
if [ -n "$BOARD_FIT" ]; then
  needed+=("$FIXTURES/board/$BOARD_FIT")
fi

PY=("${CHECKS_PYTHON:-python3}")
if [ -n "${DRIVER_LAB_BIN:-}" ]; then
  if [ ! -x "$DRIVER_LAB_BIN" ]; then
    echo "missing precondition: $DRIVER_LAB_BIN is not an executable file" >&2
    exit 3
  fi
  SPEC_CMD=("$DRIVER_LAB_BIN")
  STUBGEN_CMD=("$DRIVER_LAB_BIN" stubgen)
else
  needed+=("$SPEC" "$REQUIREMENTS")
  SPEC_CMD=("${PY[@]}" "$SPEC")
  STUBGEN_CMD=("${PY[@]}" -I "$STUBGEN")
fi

for f in "${needed[@]}"; do
  if [ ! -f "$f" ]; then
    echo "missing precondition: $f (is $dl a driver-lab checkout at the pinned commit?)" >&2
    exit 3
  fi
done

if [ -z "${DRIVER_LAB_BIN:-}" ]; then
  # spec.py's own dependency check: the versions requirements.txt pins, imported from the pin.
  if ! deps=$("${PY[@]}" -I -c '
import sys
sys.path.insert(0, sys.argv[1])
import spec
problems = spec.check_dependencies()
print("; ".join(problems))
sys.exit(1 if problems else 0)
' "$dl/skills/spec-format/scripts" 2>&1); then
    echo "missing dependency: ${deps:-spec.py cannot be imported by ${PY[*]}} (create a" \
      "virtualenv with pip install --require-hashes -r $REQUIREMENTS and set CHECKS_PYTHON)" >&2
    exit 3
  fi
fi

if [ ! -f specs/board-specs.yaml ]; then
  echo "missing precondition: specs/board-specs.yaml (run from the top of the repository)" >&2
  exit 3
fi
# ${further[@]+...} keeps an empty array from tripping set -u on bash before 4.4.
own=$(cd specs && pwd -P)
ctx=()
for r in ${further[@]+"${further[@]}"}; do
  if [ ! -f "$r/board-specs.yaml" ]; then
    echo "missing precondition: $r/board-specs.yaml (a further root must be a spec root)" >&2
    exit 3
  fi
  if [ "$(cd "$r" && pwd -P)" = "$own" ]; then
    echo "usage: $r is this repository's own specs/; a further root is another repository's" >&2
    exit 2
  fi
  ctx+=(--context-root "$r")
done

# Runs driver-lab / spec.py and keeps the exit-code contract: 0, 1 and 3 pass through;
# anything else (2, a usage error in this script's call, or 100, an internal error) is a failed check.
spec() {
  local rc=0
  "${SPEC_CMD[@]}" "$@" || rc=$?
  case "$rc" in
    0 | 1 | 3) return "$rc" ;;
    *)
      echo "error: spec.py $1 exited $rc (usage or internal error; nothing was judged)"
      return 1
      ;;
  esac
}

stubgen() {
  local rc=0
  "${STUBGEN_CMD[@]}" "$@" || rc=$?
  case "$rc" in
    0 | 1 | 3) return "$rc" ;;
    *)
      echo "error: stubgen exited $rc (usage or internal error; nothing was judged)"
      return 1
      ;;
  esac
}

check_specs() {
  local stubs_dir="${STUBS_DIR:-}" domains_manifest="${DOMAINS_MANIFEST:-}" stub_args=()
  if [ -z "$domains_manifest" ] && [ -f domains.yaml ]; then
    domains_manifest=domains.yaml
  fi
  if [ -z "$stubs_dir" ] && [ -d skills ] && compgen -G "skills/*/SKILL.md" >/dev/null; then
    stubs_dir=skills
  fi
  if [ -n "$stubs_dir" ]; then
    stub_args=(--stubs-from "$stubs_dir")
  fi
  echo "== spec.py check specs ${ctx[*]+${ctx[*]} }${stub_args[*]+${stub_args[*]} }--require-license --require-verified $mode"
  spec check specs ${ctx[@]+"${ctx[@]}"} ${stub_args[@]+"${stub_args[@]}"} \
    --require-license --require-verified "$mode" || return
  if [ -n "$domains_manifest" ]; then
    echo "== stubgen $domains_manifest --out ${stubs_dir:-skills} --check"
    stubgen "$domains_manifest" --out "${stubs_dir:-skills}" --check || return
  fi
  if [ "${REQUIRE_CORPUS:-0}" = 1 ]; then
    echo "== spec.py corpus specs ${ctx[*]+${ctx[*]} }--require-license"
    spec corpus specs ${ctx[@]+"${ctx[@]}"} --require-license
  fi
}

# Print "name<TAB>commit" lines for every repos entry with a commit in the given spec files.
discover_repo_pins() {
  "${PY[@]}" - "$@" <<'PYEOF'
import sys

try:
    import yaml
except ImportError:
    yaml = None

seen = []
for path in sys.argv[1:]:
    try:
        text = open(path, encoding="utf-8").read()
    except OSError:
        continue
    if yaml is not None:
        try:
            data = yaml.safe_load(text)
        except Exception:
            data = None
        if isinstance(data, dict):
            repos = (data.get("resources") or {}).get("repos") or []
            if isinstance(repos, list):
                for entry in repos:
                    if isinstance(entry, dict):
                        name = entry.get("name")
                        commit = entry.get("commit")
                        if isinstance(name, str) and isinstance(commit, str) and name and commit:
                            pair = (name, commit)
                            if pair not in seen:
                                seen.append(pair)
            continue
for name, commit in seen:
    print(f"{name}\t{commit}")
PYEOF
}

check_resolve() {
  local files=() f listing repo_args=() pins_out line name commit partial promisor ok
  local seen_names=() n commits_for_name
  if [ "${RESOLVE_SRC:-0}" != 1 ]; then
    echo "resolve: not run (RESOLVE_SRC is not 1, so no pinned repository is fetched)"
    return 0
  fi
  listing=$(mktemp) || return 1
  if ! find specs -name '*.spec.yaml' -print0 | sort -z > "$listing"; then
    echo "error: cannot discover spec files"
    rm -f "$listing"
    return 1
  fi
  while IFS= read -r -d '' f; do
    files+=("$f")
  done < "$listing"
  rm -f "$listing" || return 1
  if [ "${#files[@]}" -eq 0 ]; then
    echo "resolve: no specs under specs/"
    return 0
  fi
  if [ -d cache ]; then
    pins_out=$(discover_repo_pins "${files[@]}" 2>/dev/null || true)
    while IFS=$'\t' read -r name commit; do
      [ -n "${name:-}" ] || continue
      already=0
      for n in ${seen_names[@]+"${seen_names[@]}"}; do
        if [ "$n" = "$name" ]; then
          already=1
          break
        fi
      done
      [ "$already" -eq 0 ] || continue
      seen_names+=("$name")
      if [ ! -d "cache/$name/.git" ] && [ ! -f "cache/$name/.git" ]; then
        continue
      fi
      partial=$(git -C "cache/$name" config --get extensions.partialClone 2>/dev/null || true)
      promisor=$(git -C "cache/$name" config --get-regexp '^remote\..*\.promisor$' 2>/dev/null || true)
      if [ -n "$partial" ] || [ -n "$promisor" ]; then
        echo "resolve: skipping cache/$name (partial clone); falling back to remote fetch"
        continue
      fi
      ok=1
      while IFS=$'\t' read -r rname rcommit; do
        [ "${rname:-}" = "$name" ] || continue
        if ! git -C "cache/$name" cat-file -e "${rcommit}^{commit}" 2>/dev/null; then
          echo "resolve: skipping cache/$name (missing commit $rcommit); falling back to remote fetch"
          ok=0
          break
        fi
      done <<< "$pins_out"
      if [ "$ok" -eq 1 ]; then
        repo_args+=(--repo "$name=cache/$name")
      fi
    done <<< "$pins_out"
  fi
  echo "== spec.py resolve ${files[*]} ${repo_args[*]+${repo_args[*]} }--root specs --limit-mb ${SRC_FETCH_LIMIT_MB:-50}"
  spec resolve "${files[@]}" ${repo_args[@]+"${repo_args[@]}"} --root specs --limit-mb "${SRC_FETCH_LIMIT_MB:-50}"
}

check_render() {
  local out format merged rc=0
  out=$(mktemp -d)
  for merged in "" --merged; do
    if [ -n "$merged" ] && [ "${#further[@]}" -eq 0 ]; then
      continue
    fi
    for format in md html; do
      echo "== spec.py render specs ${ctx[*]+${ctx[*]} }--require-license --with-status" \
        "${merged:+$merged }--format $format"
      if spec render specs ${ctx[@]+"${ctx[@]}"} --require-license --with-status \
          ${merged:+"$merged"} --format "$format" > "$out/view.$format"; then
        echo "render: $(wc -c < "$out/view.$format" | tr -d ' ') bytes"
        if [ ! -s "$out/view.$format" ]; then
          echo "error: render produced an empty view"
          rc=1
        fi
      else
        rc=$?
        break 2
      fi
    done
  done
  rm -rf "$out"
  return "$rc"
}

# expect <exit code> <required output line, an extended regex, or ""> <label> <command>...
expect() {
  local want=$1 needle=$2 label=$3 out rc=0
  shift 3
  out=$("$@" 2>&1) || rc=$?
  printf '%s\n' "$out" | sed 's/^/    | /'
  if [ "$rc" -ne "$want" ]; then
    echo "self-test FAILED: $label exited $rc, expected $want"
    return 1
  fi
  if [ -n "$needle" ]; then
    if ! grep -qE -- "$needle" <<<"$out"; then
      echo "self-test FAILED: $label exited $rc but no output line matches '$needle'"
      return 1
    fi
    echo "self-test: $label exited $rc as required, with:"
    grep -E -- "$needle" <<<"$out" | sed 's/^/    /'
  else
    echo "self-test: $label passed (exit $rc)"
  fi
}

# A temporary root holding a copy of a marker and the given fixture files.
make_root() {
  local dir=$1 marker=$2
  shift 2
  mkdir -p "$dir"
  cp "$marker" "$dir/board-specs.yaml"
  local f
  for f in "$@"; do
    if [ -n "$f" ]; then
      cp "$f" "$dir/"
    fi
  done
}

# The self-test checks synthetic fixtures for the license gate and resolution; its check runs
# leave out --require-verified on purpose (exempt: the fixtures carry no verification records,
# and verification is not what these runs test). Every expect ends in "|| return 1": the step
# runs in a context where set -e does not stop at a failed function call.
self_test() {
  local board_fit="" gate lic kind symbol physical_tmp overlay_fixture
  # GitHub Actions sets CI=true: there the self-test must prove resolution, so a workflow
  # that forgets RESOLVE_SRC=1 on this step fails instead of skipping it silently.
  if [ "${CI:-}" = true ] && [ "${RESOLVE_SRC:-0}" != 1 ]; then
    echo "self-test FAILED: running in CI without RESOLVE_SRC=1, so resolution would go unproved"
    return 1
  fi
  tmp=$(mktemp -d) || return 1
  trap 'rm -rf "$tmp"' EXIT
  # BSD mktemp can return a path through /var, a symlink on macOS. The checker
  # requires a physical root; resolve only the temporary directory we just made.
  physical_tmp=$(cd "$tmp" && pwd -P) || return 1
  tmp="$physical_tmp"
  if [ -n "$BOARD_FIT" ]; then
    board_fit=$FIXTURES/board/$BOARD_FIT
  fi
  gate="^.+:[0-9]+:[0-9]+: error: .* is not accepted by root $REPO \\(accepts: "

  echo "== self-test: license gate, this repository's marker with $FIT (fit) and $MISFIT (misfit)"
  make_root "$tmp/fit" specs/board-specs.yaml "$FIXTURES/specs/$FIT"
  expect 0 "" "fit $FIT" "${SPEC_CMD[@]}" check "$tmp/fit" --require-license || return 1
  make_root "$tmp/misfit" specs/board-specs.yaml "$FIXTURES/specs/$MISFIT"
  expect 1 "$gate" "misfit $MISFIT" \
    "${SPEC_CMD[@]}" check "$tmp/misfit" --require-license || return 1

  for lic in $EXTRA_FIT_LICENSES; do
    echo "== self-test: license gate, a $lic source (fit), made from bsd.spec.yaml with the license replaced"
    make_root "$tmp/$lic" specs/board-specs.yaml
    sed "s/BSD-3-Clause/$lic/g" "$FIXTURES/specs/bsd.spec.yaml" > "$tmp/$lic/$lic.spec.yaml"
    expect 0 "" "fit $lic.spec.yaml" \
      "${SPEC_CMD[@]}" check "$tmp/$lic" --require-license || return 1
  done

  echo "== self-test: board-spec gate, widgetchip.spec.yaml with ${BOARD_FIT:-no overlay} (fit) and $BOARD_MISFIT (misfit)"
  make_root "$tmp/board-fit" specs/board-specs.yaml "$FIXTURES/board/widgetchip.spec.yaml" \
    "$board_fit"
  expect 0 "" "fit widgetchip.spec.yaml ${BOARD_FIT}" \
    "${SPEC_CMD[@]}" check "$tmp/board-fit" --require-license || return 1
  make_root "$tmp/board-misfit" specs/board-specs.yaml "$FIXTURES/board/widgetchip.spec.yaml" \
    "$FIXTURES/board/$BOARD_MISFIT"
  expect 1 "$gate" "misfit $BOARD_MISFIT" \
    "${SPEC_CMD[@]}" check "$tmp/board-misfit" --require-license || return 1

  echo "== self-test: a src fact read from BSD-3-Clause source (widgetchip-src-overlay.spec.yaml), $([ "$SRC_FIT" = 1 ] && echo fit || echo misfit)"
  make_root "$tmp/src" specs/board-specs.yaml "$FIXTURES/board/widgetchip.spec.yaml" \
    "$FIXTURES/board/widgetchip-src-overlay.spec.yaml"
  if [ "$SRC_FIT" = 1 ]; then
    expect 0 "" "fit widgetchip-src-overlay.spec.yaml" \
      "${SPEC_CMD[@]}" check "$tmp/src" --require-license || return 1
  else
    expect 1 "^.+:[0-9]+:[0-9]+: error: fact 'stub-magic': an anchor names repos entry 'tools': BSD-3-Clause is not accepted by root $REPO " \
      "misfit widgetchip-src-overlay.spec.yaml" \
      "${SPEC_CMD[@]}" check "$tmp/src" --require-license || return 1
  fi

  if [ "${RESOLVE_SRC:-0}" = 1 ]; then
    # Proves resolution ran: a real pinned repository (raspberrypi/tools) is fetched, a good
    # anchor must resolve and a bad one fail. The specs are widgetchip-src-overlay.spec.yaml
    # pointed at that repository, under a temporary marker that accepts BSD-3-Clause, so the
    # fixture's license does not decide the result in any repository.
    echo "== self-test: src anchors resolve against the fetched pin (RESOLVE_SRC=1)"
    mkdir -p "$tmp/resolve"
    printf 'format: 2\nlayer: public\nname: resolve-self-test\nlicense: Apache-2.0\naccepts: [BSD-3-Clause]\n' \
      > "$tmp/resolve/board-specs.yaml"
    for kind in good bad; do
      symbol=OSC_FREQ
      [ "$kind" = good ] || symbol=DELIBERATELY_ABSENT_SYMBOL
      sed -e 's#https://example.invalid/tools#https://github.com/raspberrypi/tools#' \
        -e "s#lines: \\[30, 30\\], symbol: stub_magic#lines: [53, 57], symbol: $symbol#" \
        "$FIXTURES/board/widgetchip-src-overlay.spec.yaml" > "$tmp/resolve/resolve-$kind.spec.yaml"
      if ! grep -q "github.com/raspberrypi/tools" "$tmp/resolve/resolve-$kind.spec.yaml" ||
          ! grep -q "symbol: $symbol" "$tmp/resolve/resolve-$kind.spec.yaml"; then
        echo "self-test FAILED: could not build resolve-$kind.spec.yaml from the fixture"
        return 1
      fi
    done
    expect 0 "^1 anchor\\(s\\) resolved, 0 skipped$" "resolve-good (anchor exists at the pin)" \
      "${SPEC_CMD[@]}" resolve "$tmp/resolve/resolve-good.spec.yaml" --root "$tmp/resolve" \
      || return 1
    expect 1 "^.+:[0-9]+:[0-9]+: error: stub-magic: symbol 'DELIBERATELY_ABSENT_SYMBOL' is not near the cited range" \
      "resolve-bad (no such symbol at the pin)" \
      "${SPEC_CMD[@]}" resolve "$tmp/resolve/resolve-bad.spec.yaml" --root "$tmp/resolve" \
      || return 1
  fi

  if [ "${#further[@]}" -gt 0 ]; then
    echo "== self-test: an overlay here resolves against a spec in ${further[0]} only when both roots are read"
    make_root "$tmp/other" "${further[0]}/board-specs.yaml" "$FIXTURES/board/widgetchip.spec.yaml"
    overlay_fixture="$FIXTURES/board/widgetchip-bsd-overlay.spec.yaml"
    if [ "$SRC_FIT" != 1 ] || grep -qE '^accepts:[[:space:]]*\[\][[:space:]]*$' specs/board-specs.yaml; then
      overlay_fixture="$tmp/widgetchip-docs-overlay.spec.yaml"
      awk '/^resources:/{skip=1; next} /^facts:/{skip=0} !skip{print}' \
        "$FIXTURES/board/widgetchip-bsd-overlay.spec.yaml" > "$overlay_fixture"
    fi
    make_root "$tmp/overlay" specs/board-specs.yaml "$overlay_fixture"
    expect 1 "^.+:[0-9]+:[0-9]+: error: overlays 'widgetchip' resolves to no spec$" \
      "overlay without the second root" \
      "${SPEC_CMD[@]}" check "$tmp/overlay" --require-license || return 1
    expect 0 "" "overlay with the second root" \
      "${SPEC_CMD[@]}" check "$tmp/overlay" --context-root "$tmp/other" --require-license \
      || return 1
  fi
  echo "self-test: passed"
}

run_step() {
  case "$1" in
    check) check_specs ;;
    resolve) check_resolve ;;
    render) check_render ;;
    self-test) self_test ;;
  esac
}

rc=0
if [ "$step" = all ]; then
  for s in check resolve render self-test; do
    run_step "$s" || rc=$?
    [ "$rc" -eq 0 ] || break
  done
else
  run_step "$step" || rc=$?
fi
exit "$rc"
