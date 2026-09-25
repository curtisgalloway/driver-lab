<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Moving driver-porting to its own repository

Written 2026-09-24, when the user decided to move this work out of `public-skills`. It is the
starting point for whoever sets up the new repository, person or agent: what moves, what it
leans on that stays behind, where the work stands, and what to do first.

## Terms

- **Workstream** — everything under `plugins/driver-porting/`: the skills, the design and
  plan documents, the evaluation material, and the evidence of each milestone.
- **Skill** — a packaged set of agent instructions (a `SKILL.md` and supporting files).
  **Plugin** — a bundle of skills installable from a marketplace listing.
- **Milestone / unit** — a session-sized piece of the [implementation plan](IMPLEMENTATION-PLAN.md)
  (`L01`, `L02a` … `L02g`, and the deferred `M01`–`M17`), each closed with an evidence file.
- **Evidence file** — `evidence/<unit>.md`, the verdict record of a unit.
  **Notebook** — `notebook/`, append-only notes per unit (see the `lab-notebook` skill).
- **Private run store** — per-run directories outside any repository, holding raw sessions,
  traces, captures, source under other licenses and reviewer reports. Its location and the
  test host's name are in the operator's private notes, never in this repository.
- **Test host** — the x86-64 Linux machine that runs QEMU for the L02 units.
- **Operator** — the coordinating agent session that runs a unit.

See the [glossary](../../GLOSSARY.md) for the rest; it moves with the workstream (below).

## What moves

The whole `plugins/driver-porting/` directory: 2.7 MB, 84 commits of history, self-contained
apart from the items in the next section.

| Path | What it is |
| --- | --- |
| `skills/` | Twelve skills: the clean-room pipeline (`os-investigator`, `cleanroom-spec`, `cleanroom-implementer`), `anchored-peripheral-spec`, `reference-driver-review`, `spec-verifier`, `board-expert` with `board-spec-scaffold`, and the board experts for the Raspberry Pi 5 and 4, the Indiedroid Nova (RK3588) and the Pixel 10 |
| `README.md` | The plugin's user guide: which skill to use when, installation, tests |
| `DESIGN.md` | The evidence model: evidence classes and what each can be trusted for |
| `DRIVER-QUALITY.md`, `EVAL-PLAN.md`, `RECONSTRUCTION.md`, `VALIDATION-PROPOSAL.md`, `VALIDATION-REVIEW.md` | Earlier design and evaluation proposals; context for the deferred experimental plan |
| `QEMU-DIFFERENTIAL.md` | The approved L02 design: an Intel e1000 driver written from a spec, tested against the reference in QEMU |
| `IMPLEMENTATION-PLAN.md` | The plan: status of every unit, conventions, and a "Next session" section |
| `evidence/`, `notebook/`, `PROCESS-NOTES.md` | Verdict records, working notes, and the process log |
| `evals/enc28j60/` | The ENC28J60 benchmark: corpus, frozen ledger, scoring scripts and tests |
| `evals/e1000/` | The e1000 blind requirement list, recall table, and the QEMU harness with its tests |
| `.claude-plugin/plugin.json` | The plugin manifest (repository URL points at `public-skills`; update it) |

**Recommended way to move it:** keep the history. `git filter-repo --path plugins/driver-porting
--path GLOSSARY.md --path-rename plugins/driver-porting/:` in a fresh clone gives a repository
with the workstream at its root and the glossary beside it. Then fix the relative links
(next section) and the CI paths. Moving the files without history loses the record of which
commit each evidence file certifies.

## What it leans on that stays behind

| Dependency | Where it lives now | What to do |
| --- | --- | --- |
| The glossary | `GLOSSARY.md` at the repository root; 35 files link to it with `../../`-style paths. Rows added for this work include Blind requirement list, Operator, Lab notebook, Process log, Planted defect, Phase, Deferred check | Take a copy (the filter-repo command above does), trim rows that are only for other plugins, and rewrite the links for the new layout |
| CI | 8 steps in `.github/workflows/checks.yml` run the workstream's tests: `os-investigator`, `cleanroom-implementer` and `board-expert` unit tests, the board spec checker, the ENC28J60 eval tests and author-manifest check (with `pyyaml`), and the e1000 harness tests | Copy those steps into the new repository's workflow; remove them here when the plugin is removed |
| Marketplace listing | `.claude-plugin/marketplace.json` lists `driver-porting`, and the "everything" plugin includes `./plugins/driver-porting/skills` | Give the new repository its own listing, then drop both entries here |
| Repository README | Plugin table row, `/plugin install` and `codex plugin add` lines, an Antigravity symlink example, and a "Related" note that `fuchsia-skills` hands off to driver-porting skills by name | Update when the plugin leaves; the skill names must not change or `fuchsia-skills` breaks |
| Skills from other plugins | The plan and briefs use `review-swarm` (dev-tools), and `consult`, `project-plan`, `lab-notebook`, `learn` and `handoff` (agent-workflow) | They stay in `public-skills`; install them alongside. Nothing is vendored |

Also in `public-skills` but not tracked: `HANDOFF-eval-proposal.md` at the repository root
(the 2026-09-18 evaluation consensus) belongs to this work; move it if it is still wanted.

## Where the work stands

| Unit | Status | Record |
| --- | --- | --- |
| M01, M02a (ENC28J60 trial preparation, source export, reference build) | Complete for their scope; the rest of M02–M17 and P01 is **deferred**, not waived | [evidence](evidence/) |
| L01 — ENC28J60 Linux driver from a spec | First unit complete 2026-09-22; **second unit blocked** on the ENC28J60 module being wired to a Raspberry Pi 4 | [L01](evidence/L01.md) |
| L02a — pin sources, blind requirement list | Complete 2026-09-23 | [L02a](evidence/L02a.md) |
| L02b — author the e1000 spec | Complete 2026-09-23 | [L02b](evidence/L02b.md) |
| L02c — verify the spec, measure recall | Complete 2026-09-24 (63 of 66 rows covered, 3 partial) | [L02c](evidence/L02c.md) |
| L02e — candidate driver from the spec | Complete 2026-09-24; built and reviewed, never run | [L02e](evidence/L02e.md) |
| L02d1 — QEMU harness, boot and capture | Complete 2026-09-24 | [L02d1](evidence/L02d1.md) |
| **L02d2 — scenarios and planted defects** | **In progress**, stopped early 2026-09-24: built, run, reviewed; review fixes applied and unit-tested but not yet run on the test host or reviewed | [L02d2](evidence/L02d2.md#status) |
| L02f — differential run of the candidate | Pending; needs L02d2 | plan |
| L02g — final check against the design | Pending | plan |

**First work in the new repository:** finish L02d2's four remaining steps (its evidence
file's Status section), then L02f. Spec revision 5 (set PSCON bit 11, per L02e) is due
before L02f's feedback. The plan's "Next session" section says the same.

## Branches and uncommitted state

- `driver-porting/l02d2` — local only, not pushed: L02d2's early-stop checkpoint and this
  document, on top of `origin/main` at `d63e3f1`. Push it or carry it into the new
  repository's history; either way, its commits are the only copy of this session's work.
- `driver-porting/pixel10-spec`, `-v2`, `-v3` — kept on purpose (user decision 2026-09-24);
  do not prune them in a branch cleanup.
- No open pull requests for this work at the time of writing.

## What does not move with git

Record these before the move; none of them is in any repository.

- **The private run store**, one directory per run ID (`e1000-l02a-…` through
  `e1000-l02d2-…`, `enc28j60-…`): the Intel manual, the Linux e1000 source (GPL, evaluator
  side only), the frozen blind list's author files, spec revisions, the candidate driver, every
  harness run, the planted-defect edit script (it quotes GPL source), and reviewer reports.
  Public evidence files cite these by run ID only.
- **The operator's private notes** alongside the run store: the test host's SSH alias,
  paths on it, and the history of the plan's private constraints.
- **Working directories on the test host** for L02d, L02d2 and L02e: the v6.12 kernel build
  (gcc-14; GCC 15 cannot build v6.12), the reference and planted-defect modules, the synced
  harness.
- **Agent memory** for this project directory: the framing of the work, the run store's
  location, and working rules. A new repository gets a new memory directory; copy what is
  still true.

## Rules the work runs under

Carry these into the new repository's instruction file (`AGENTS.md`):

- One unit per session: implement, verify, review, then a checkpoint commit named
  `driver-porting: <unit> — <title>`; stop for inspection. Review happens **before** the
  checkpoint and must leave an artifact (a run directory or reviewer report).
- Reviews: `review-swarm` for code, plus a fresh reviewer that reads **run artifacts** for
  harness work (this unit's code review missed three claims that could not fail; the
  artifact reviewer found them). `spec-verifier` for specs.
- Implementers are fresh subagents whose model the user selects (Claude Opus 5.5 lately; the
  Codex quota was exhausted, so `consult` reviews were unavailable).
- Isolation: the operator reads the reference driver and QEMU; implementers never do. The
  blind requirement list stays private until its recall is measured.
- Privacy: public files name the test host and other machines by role only; no addresses,
  host names, user names or home paths. Source under other licenses stays in the run store.
- Git: a topic branch and a PR per unit; push or open a PR only on the user's explicit
  "push"; merge only when told. Record subagent transcript paths in the run's ledger; do not
  copy transcripts.

## Open decisions for the new repository

- Its name, and whether it is public (this plugin is Apache-2.0 today; keep the SPDX headers).
- Whether `driver-porting` remains installable from the `curtisg-skills` marketplace (a
  pointer) or only from the new one.
- Whether the deferred experimental plan (M02–M17, P01) moves as live plan or as archive.
