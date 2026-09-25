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

CI (`.github/workflows/checks.yml`) runs these; run them before every checkpoint commit:

```bash
python3 utilities/check-no-private-paths.py
python3 -m unittest discover -s skills/os-investigator/tests
python3 -m unittest discover -s skills/cleanroom-implementer/tests
python3 -m unittest discover -s skills/board-expert/tests
python3 skills/board-expert/scripts/spec_check.py skills/board-expert/specs --stubs-from skills
uv run --with pyyaml python3 -m unittest discover -s evals/enc28j60/tests
uv run --with pyyaml python3 evals/enc28j60/author_manifest.py --check evals/enc28j60/author-manifest.yaml
python3 -m unittest discover -s evals/e1000/harness/tests
```

## Rules the work runs under

- **One unit per session**: implement, verify, review, then a checkpoint commit named
  `driver-porting: <unit> — <title>`; stop for inspection. Review happens **before** the
  checkpoint and must leave an artifact (a run directory or reviewer report).
- **Reviews**: `review-swarm` for code, plus a fresh reviewer that reads **run artifacts** for
  harness work (L02d2's code review missed three claims that could not fail; the artifact
  reviewer found them). `spec-verifier` for specs.
- **Implementers** are fresh subagents whose model the user selects.
- **Isolation**: the operator reads the reference driver and QEMU; implementers never do. The
  blind requirement list stays private until its recall is measured.
- **Privacy**: this repository is public. Files name the test host and other machines by role
  only: no addresses, host names, user names or home paths. Source under other licenses stays in
  the private run store, which files cite by run ID only.
- **Git**: a topic branch and a pull request per unit; push or open a pull request only on the
  user's explicit "push"; merge only when told. Record subagent transcript paths in the run's
  ledger; do not copy transcripts.

## Skills this work uses from elsewhere

The plan and briefs use `review-swarm` (dev-tools), and `consult`, `project-plan`,
`lab-notebook`, `learn` and `handoff` (agent-workflow), all from public-skills. Install them
alongside; nothing is vendored.
