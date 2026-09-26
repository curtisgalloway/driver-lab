<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# driver-lab

Instructions for coding agents working in this repository. The user guide is the
[README](README.md); borrowed and coined terms are in the [glossary](GLOSSARY.md).

## What this is

The `driver-porting` skills (under `skills/`) and the work that tests them: the design and
[implementation plan](IMPLEMENTATION-PLAN.md), the evaluations under `evals/`, and a record of
each milestone under `evidence/` and `notebook/`. It was split out of
[public-skills](https://github.com/curtisgalloway/public-skills) on 2026-09-25 with its history.
[TRANSITION.md](TRANSITION.md) records the move.

**Commit hashes cited in files here are public-skills hashes.** Prose citations link to the
commit on GitHub. Bare hashes in machine-read fields (`ledger.lock`, `*.verify.md` front matter,
reconstruction inputs) translate to this repository's copies through
[history/public-skills-commit-map.txt](history/public-skills-commit-map.txt). New citations name
this repository's commits.

**Skill names are an interface.** `fuchsia-skills` hands off to these skills by name; renaming
one breaks it.

## Checks

CI (`.github/workflows/checks.yml`) runs the full list below on every pull request. Before a
checkpoint commit, run locally the tests for the surface you changed plus the privacy check
(`check-no-private-paths.py`); run the full list locally at the final checkpoint of a
campaign (for L02, L02f3's acceptance stage). (Revised 2026-09-25, user approved.) The full
list:

```bash
python3 utilities/check-no-private-paths.py
python3 -m unittest discover -s skills/os-investigator/tests
python3 -m unittest discover -s skills/cleanroom-implementer/tests
python3 -m unittest discover -s skills/board-expert/tests
python3 skills/board-expert/scripts/spec_check.py skills/board-expert/specs --stubs-from skills
uv run --with pyyaml python3 -m unittest discover -s evals/enc28j60/tests
uv run --with pyyaml python3 evals/enc28j60/author_manifest.py --check evals/enc28j60/author-manifest.yaml
python3 -m unittest discover -s evals/e1000/harness/tests
python3 <public-skills>/plugins/agent-workflow/skills/agent-agnostic-skills/scripts/portability_scan.py \
  skills/cleanroom-implementer/scripts
```

The last one needs a public-skills checkout; CI pins the scanner to one of its commits.

## Rules the work runs under

- **One unit per session**: implement, verify, review, then a checkpoint commit named
  `driver-porting: <unit> — <title>`; stop for inspection. Review happens **before** the
  checkpoint and must leave an artifact (a run directory or reviewer report). In orchestrated
  mode, one fresh subagent runs each unit and the orchestrator lands it as one pull request.
- **Reviews** (default from 2026-09-25, user approved): for harness work, one independent
  reviewer that reads the diff and the **run artifacts** (L02d2's code review missed three
  claims that could not fail; the artifact reviewer found them). For spec work,
  `spec-verifier` on the changed claims and their dependencies. `review-swarm` only when
  shared execution machinery, access controls or several scenarios change, or whenever the
  reviewer asks for broader review.
- **Records, one job each**: the private run ledger holds identities, commands, artifacts,
  attempts and reviewer references; the public evidence file holds conclusions, the acceptance
  table, limitations, and consequential findings with their resolutions; the notebook holds
  short chronological discoveries and dead ends; the plan and the notebook index hold status
  and links. Do not repeat findings tables or conclusions across them.
- **Implementers** are fresh subagents whose model the user selects.
- **Isolation**: the operator reads the reference driver and QEMU; implementers never do. The
  blind requirement list stays private until its recall is measured. An implementer launched as
  a separate CLI (Codex) on the test host, which also holds the reference source, runs under
  `skills/cleanroom-implementer/scripts/cleanroom_sandbox.sh` with a fresh agent home, and its
  strace log is checked with `sandbox_audit.py`, after a canary pilot, before its output is used
  (cleanroom-implementer, "Tier 1 on Linux"). Copying the operator's agent credential into that
  home and bypassing the agent's own sandbox inside bubblewrap are expected; the user approved
  both on 2026-09-25.
- **Privacy**: this repository is public. Files name the test host and other machines by role
  only: no addresses, host names, user names or home paths. Source under other licenses stays in
  the private run store, which files cite by run ID only. The rule covers this project's own
  machines and network, not third-party facts their owner already published: a vendor code name
  from a public mailing-list post or a published device tree stays in a spec.
- **Run store location**: each user chooses where their run store lives; the path is never
  written into this repository and has no default. Set it as `run_store = "<path>"` in
  `~/.config/driver-lab/config.toml` (under `$XDG_CONFIG_HOME` when that is set);
  `DRIVER_LAB_RUNS` overrides it. `python3 utilities/run-store.py [<run ID>]` prints the store,
  or a run's directory in it, and exits 1 when nothing is configured: then ask the user for the
  location rather than searching the filesystem.
- **Git**: a topic branch and a pull request per unit, and a separate branch for any unrelated
  change. Fetch first and cut the branch from `origin/main`, not a local `main` that may be
  stale. Push or open a pull request only on the user's explicit "push", and "push" never means
  pushing `main`: branch protection exempts admins, so a direct push succeeds silently. Merge
  only when told; deleting the merged branch, local and remote, is part of merging. Worktrees go
  under `.claude/worktrees/<name>`; another session may be using the main checkout, so check
  `git status` and `git reflog -3` before switching branches there.
- **Transcripts**: record each subagent's transcript path in the run's ledger. Do not copy,
  read or hash transcripts from the shell: they live in the harness's protected state
  directory, and touching it stops an unattended run at a permission prompt.

## Presenting the work

The core test is rebuilding a Linux driver from the spec and running it differentially against
the original (L01, L02). Lead with that result when explaining or reporting the work, not with
reviewer pass counts. Human review of every spec costs about as much as writing the driver with
AI help, so the design aims at automated checks with people handling exceptions
([DRIVER-QUALITY.md](DRIVER-QUALITY.md)). Every current target has a working reference driver,
which makes this the easy case; hardware with no existing driver is the open question
([DESIGN.md](DESIGN.md#when-there-is-no-existing-driver)).

## Skills this work uses from elsewhere

The plan and briefs use `review-swarm` (dev-tools), and `consult`, `project-plan`,
`lab-notebook`, `learn` and `handoff` (agent-workflow), all from public-skills. Install them
alongside; nothing is vendored.
