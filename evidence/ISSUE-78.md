<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Issue 78 — Isolated interpreters in the patch gate

**Terms.** The patch gate (`utilities/patch-gate.py`) checks a Codex patch after it is
applied to a worktree. Isolated mode (`python -I`) keeps the working directory and `PYTHON*`
environment variables off the module path. See the [glossary](../GLOSSARY.md).

The gate built `.venv-sf2` with `python -m venv` and ran the default suites with
`python -m unittest`, each from inside the worktree. `-m` puts the working directory first on
the module path, so a top-level `venv.py` or `unittest.py` added by a patch replaced the
standard library module. A stub `venv.py` skipped the `--require-hashes` install, and the gate
still printed `gate: pass`. Codex's wrapper accepts such a file. Every interpreter the gate
starts now runs with `-I`.

| Acceptance | Evidence |
| --- | --- |
| A planted `venv.py` does not run, and a real venv is built | `test_planted_venv_module_cannot_replace_the_venv_build` |
| A planted `unittest.py` does not replace a default suite's runner | `test_planted_unittest_module_cannot_replace_a_default_suite` |
| Both tests fail without the fix | Reverting `patch-gate.py` alone: 4 failures in those two tests (`revert-tests.log`) |
| Default suites still pass under `-I` | spec-format 673 tests OK; utilities suite unchanged (`spec-format-I.log`, `utilities-I.log`) |

The gate's 24 tests pass. The utilities suite has two `test_codex_review` failures on this
host with or without the change: a stray, empty `.git` directory in the system temporary
directory makes its temporary review directories look like they sit inside a work tree (as
recorded for Issue 107). Privacy and open-side checks pass. Private artifacts: run
`issue-78-20261014`.

Limitations: the original review's text for "control-bypass" never arrived, so this fixes the
bypass found on re-review, not necessarily the one that review meant. `--suite` commands are the
caller's; the docstring and AGENTS.md ask that those starting Python pass `-I` too. A new
top-level module named after a standard-library one is not refused outright. The suites still
run patched code by design, so a patched test can still exit 0 early.
