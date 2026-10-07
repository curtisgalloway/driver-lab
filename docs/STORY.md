<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# driver-lab: a timeline and story outline

> **Frozen archive.** This outline is kept as history of the work before driver-lab's license
> split (2026-10-06) and is no longer updated. The clean-room skills it names now live in
> [cleanroom-skills](https://github.com/curtisgalloway/cleanroom-skills), with their
> [design](https://github.com/curtisgalloway/cleanroom-skills/blob/main/DESIGN.md), and new
> evaluation rounds run from there. Names and paths below are as they were then (`os-investigator`
> is now `cleanroom-investigator`). See the [license-split design](LICENSE-SPLIT.md),
> requirement LS-R20.

*Working material for a later write-up, not the write-up itself. Commit SHAs are this
repository's; commits
before 2026-09-25 were rewritten by `git filter-repo` when the work moved out of
`public-skills`, so evidence files written earlier cite different (public-skills) hashes — see
[history/public-skills-commit-map.txt](../history/public-skills-commit-map.txt).*

## What this project is

driver-lab is a set of agent skills, and a four-week record of testing them, for one question:
can LLM agents write a device-driver *specification* good enough that a separate agent can
implement a working driver from it, without copying source it may not be allowed to copy — and
how would you know? It packages a clean-room pipeline (one agent reads the encumbered Linux
source and writes a spec; another, walled off, writes the driver), board "experts" backed by
per-SoC spec files, and a `spec-verifier` that re-derives every claim from its cited source.
The record runs from board specs for a Pixel 10, through a frozen answer key for the Microchip
ENC28J60 Ethernet chip, to a full differential campaign on the Intel e1000 in QEMU and finally
real hardware on a Raspberry Pi 4 — every unit logged with evidence, planted defects, reviews
and the mistakes along the way ([README.md](../README.md), [DRIVER-QUALITY.md](../DRIVER-QUALITY.md)).

## Terms

Full definitions are in [GLOSSARY.md](../GLOSSARY.md).

- **Clean-room boundary** — the separation between the agent that reads encumbered source and
  the agent that writes the new driver, with a record of what crossed.
- **Spec / spec revision** — a document precise enough to implement a driver from; every change
  makes a new numbered, hashed revision that is verified before use.
- **Evidence class / provenance tag** — the label on every fact saying where it came from
  (`[databook]`, `[source-observed]`, `[inference]`, later `[rtl]` and `[emulated]`).
- **Verification record / reading** — one fresh verifier agent's per-claim verdicts
  (PASS/FAIL/UNVERIFIABLE/GAP) against the cited sources, kept outside the spec.
- **Candidate / reference driver** — the driver written from the spec / the existing upstream
  Linux driver, used as comparison evidence, not truth.
- **Blind requirement list / gold ledger** — requirements written from the manual *before* any
  spec existed, used afterwards to measure what the spec left out (recall).
- **Planted defect / qualified check** — a deliberate bug in a copy of the reference driver; a
  check is qualified only once a planted defect has made it fail.
- **Differential test** — reference and candidate run through the same scenarios; outcomes and
  register traces compared.
- **Fixture** — the prepared hardware: here, the Pi 4 fixture with an ENC28J60 module on SPI.
- **Operator / orchestrator** — the coordinating agent session that briefs and launches other
  agents and writes the evidence; it writes no driver code.
- **Claim map / status index** — per campaign, the data files tying each claim to its checks,
  qualifying runs and current verdict, and marking verdicts stale when their basis changes.

## Timeline

### Phase 0 — Before this history (through 2026-09-02)

- The clean-room pipeline already existed as part of a larger `public-skills` repository; the
  first commit here repackages 26 skills into themed plugins, one of them `driver-porting`
  (`ba91add`, 09-01). What happened before that is not in this repository's history.
- `329eb1a` (09-02): American spellings swept across the repo — a small, early sign of the
  user steering agent-written text.

### Phase 1 — Board experts become data, and a spec format meets a hostile test (09-11 → 09-19)

- **Board experts** added and promoted from private skills (`c116843`, `c1a3704`).
- **Turning point, 09-18:** board knowledge moves from one self-contained skill per board to
  *spec files plus a generic reader* — composable, layered (public / vendor / local), every fact
  tagged (`0da5874`); IP specs, a question catalog and a vendor guide (`01e8a80`); a mechanical
  `spec_check.py` (`5795a10`).
- **The Pixel 10 stress test:** a fresh agent builds a Pixel 10 spec from the scaffold and reports
  every place the format got in its way. Runs 1–3 surface 21, 15 and 18 format defects, each
  batch fixed before a from-scratch rerun (`6667604`, `b7e5db5`, `a5378d1`).
- **`spec-verifier` is born** (`6626ff5`, 09-18): the user asks for a verification phase; a fresh
  verifier re-derives each claim from its cited source and never edits the spec.
- Run 4 dies mid-verification — *out of API credits* (`63d44f6`). Resumed, it is the first
  end-to-end verification: pixel10 13/18 PASS, tensor-g5 41/46 PASS; two independent verifiers
  failed the same bullets for the same reasons, and one genuine disagreement is recorded rather
  than resolved (`fa2c6d8`).
- **Rounds 4–7 (09-19):** the values were right for four rounds; what kept failing was the prose
  about them. The addressing model was rewritten three times and falsified four, until it became
  a decoding procedure plus a table partitioning the device tree. Three verifiers each wrote
  their own device-tree reader and reproduced 2,774 nodes / 645 with registers / ten class
  counts; the arithmetic caught an ordering bug in the fix itself (410/0 instead of 409/1).
  Zero failures after round 7 (`9dd5068`, `75c2b67`, `54a5425`).
- A checker bug found in passing: a stale record that also carried FAILs reported only a
  warning (`35260b7`, fixed `b557dbf`).

### Phase 2 — How would we know? Evaluation design and a frozen answer key (09-18 → 09-20)

- `EVAL-PLAN.md` (`b3ea370`, 09-18); the ENC28J60 chosen as the pilot device.
- **Validation proposal and review** (`35260b7`, `2f5690a`, 09-19): Codex drafted a proposal;
  Claude reviewed it; the two agents consulted and reached a joint recommendation (freeze the
  ledger first, public-only pilot, defer the heavier stages). The proposal was rewritten to that
  consensus ([VALIDATION-PROPOSAL.md](../VALIDATION-PROPOSAL.md),
  [VALIDATION-REVIEW.md](../VALIDATION-REVIEW.md)).
- **Frozen corpus** (`96fa9b7`): every datasheet and errata edition pinned by hash. Surprise:
  errata are *renumbered between editions*, so "issue 12" means different bugs in rev B and rev C,
  and the served errata only claim to accompany an older datasheet revision.
- **Gold ledger, authored blind** (`35951f7`, 09-20): two readers in fresh contexts, 175 and 171
  rows, merged to 205 by a merger forbidden from authoring; one reader refused the corpus's own
  errata table and was right (`1cbe93e`). The Codex reviewer refused the freeze four times and
  agreed on the fifth under a stated stopping rule (`5f774db`). The lock hashes five files; one
  added comment line fails it.
- **First practice run** (`5e4ff1a`, [evals/enc28j60/PRACTICE-RUN.md](../evals/enc28j60/PRACTICE-RUN.md)):
  a Claude-written ENC28J60 spec, 148 of 162 recall rows covered, 1 missing; documentary
  acceptance *blocked*; "no precision ratio is reported" because the computed 1.0 was an artifact
  of readers never agreeing on a FAIL.
- Scaffolding grows: gates on review preparation (`c628505`…`5c84201`), an OS-neutral
  reconstruction protocol (`547b71a`), a 17-milestone plan reviewed by Claude through `consult`
  ([evidence/PLAN-REVIEW.md](../evidence/PLAN-REVIEW.md), `b745600`), M01 and M02a trial preparation
  and a related-controller source audit ([evidence/M01.md](../evidence/M01.md),
  [evidence/M02a.md](../evidence/M02a.md), [evidence/M02a-source-audit.md](../evidence/M02a-source-audit.md)).

### Phase 3 — The pivot: write the driver (evening of 09-20)

- **User decision, 09-20** ([evidence/LINUX-PRIORITY.md](../evidence/LINUX-PRIORITY.md), `15775bc`):
  the user asked an independent agent whether directly writing and testing the Linux driver would
  serve the goal as well as the verification preparation. The assessment distinguished practical
  confidence from causal comparison; the user "selected practical progress first". Exhaustive
  sanitization, paired runs and blinded attribution were deferred, not waived; the practice
  result "stays incomplete".
- Record: one Claude review produced twelve corrections; CLI-reported costs of about $4.0 and
  $4.7 for the review and confirmation are logged.

### Phase 4 — L01: a first real driver, and L02 designed (09-22)

- **Evidence model** in DESIGN.md (`e6ed74f`): a trust table per evidence class, conflicts kept
  beside the claim, and a new `[rtl]` class.
- **L01 first unit** (`2efd57e`, [evidence/L01.md](../evidence/L01.md)): Codex (`gpt-6-astra`),
  given the spec, datasheet, errata and only `include/` + `Documentation/` of the kernel, writes a
  Linux v6.12 ENC28J60 driver. Zero W=1 warnings; 64/64 critical ledger rows implemented; two
  Linux-integration bugs; the reference review found **eight defects in the upstream reference
  driver** the candidate avoids. One repair round. Never run on hardware yet (no fixture wired).
- **L02 designed** (`7c7398a`, [QEMU-DIFFERENTIAL.md](../QEMU-DIFFERENTIAL.md)): L01 left two
  questions — does it hold for a harder device (DMA rings, PCI), and can the comparison run
  without a bench? Answer: the Intel e1000 (82540EM) in QEMU. Key rule: the QEMU model is kept
  *out* of the spec's sources so the harness stays independent; expectations come from the
  manual, not the reference; a planted defect must fail before a test is trusted.

### Phase 5 — L02, spec and candidate (09-23 → 09-24)

- **L02a** blind list: 67 rows (66 active) from the Intel manual before any spec
  ([evidence/L02a.md](../evidence/L02a.md), [evals/e1000/](../evals/e1000/)).
- **L02b** spec, three revisions ([evidence/L02b.md](../evidence/L02b.md)): transfer review 2 FAILed
  a reset-quiesce order tagged `[databook]` that the manual never prescribes — revision 1 had it
  too and review 1 missed it; all 24 ordered sequences swept.
- **L02c** two independent readings: 555 and 554 verdicts; recall 95.5% (63 of 66, 3 partial,
  none missing) ([evidence/L02c.md](../evidence/L02c.md)).
- **L02e** candidate ([evidence/L02e.md](../evidence/L02e.md), [notebook/L02e.md](../notebook/L02e.md)):
  the Codex quota was exhausted for a day, so a fresh Claude Opus 5.5 subagent implemented it.
  GCC 15 cannot build Linux v6.12 (gcc-14 used). The reference review found a **spec error both
  L02c readings passed**: PSCON bit 11 should be set. The session auditor flagged a clean session;
  its eight findings were traced by hand.
- **L02d1/L02d2** QEMU harness ([notebook/L02d1.md](../notebook/L02d1.md),
  [notebook/L02d2.md](../notebook/L02d2.md)): the reference reads its EEPROM by bit-banging (~6,700
  accesses); busybox `nc` has no UDP; `ping -i 0` hangs the guest; QEMU's e1000 pushes back
  instead of overrunning. L02d2 **stopped early** when the SSH agent refused to sign (`d9ddf68`);
  its open finding C9: most checks had never been shown able to fail.
- **User decision, 09-24:** move the work to its own repository ([TRANSITION.md](../TRANSITION.md)).

### Phase 6 — New repo, and L02 run end to end (09-25)

- **The move** (`bdb5149`, `bc64299`, `9fd5884`): history kept with filter-repo, commit map
  kept, privacy check added to CI, working rules moved out of agent memory into
  [AGENTS.md](../AGENTS.md).
- **Plan revision after a Claude–Codex consultation** (`572f54e`, user-approved): new unit L02d3
  to qualify checks *before* any candidate result is seen; L02f split into run, repair and
  feedback. **Design criterion A6 amended** (`98518b6`): "every planted defect detected" was
  unmeetable because m1 is an equivalent mutation the manual permits.
- **L02d3** ([notebook/L02d3.md](../notebook/L02d3.md)): 26 claims, 22 qualified, 4 not; the 1 µs
  reset rule cannot be failed this way (removing the wait still leaves 13 µs gaps).
- **L02f1** ([notebook/L02f1.md](../notebook/L02f1.md)): reference 10/10; **candidate fails every
  scenario at probe**, one cause — QEMU hard-wires EECD.EE_GNT = 1 and the candidate, following
  the manual, waited for a grant and aborted. Labeled a model limitation plus a spec gap (no bound
  or fallback).
- **L02f2** ([notebook/L02f2.md](../notebook/L02f2.md)): user chose Codex `gpt-6-astra` and a
  three-round repair budget (`9d5a2d9`). The implementer now runs under bubblewrap with a fresh
  home, strace auditing every read; the sandbox is codified in `cleanroom-implementer`. One
  round: 9/10. The tenth fails 3 of 6 at random — QEMU holds reception for 1 s after any RCTL
  write, releasing ~30 leftover flood frames just ahead of the ping reply: harness, not driver
  (H1). The operator's machine crashed twice; entries were reconstructed and a lost review rerun.
- **L02s** spec revision 5 ([notebook/L02s.md](../notebook/L02s.md)): the manual never says "set bit
  11"; the spec argues it as an `[inference]`, and the manual contradicts itself on TNCRS.
- **User decision: lighter process** (`522064d`, [evidence/PLAN-2026-09-25.md](../evidence/PLAN-2026-09-25.md)):
  plan cut from 938 to 533 lines; one independent reviewer by default; records one job each.
- **L02f2b / L02f3** ([evidence/L02f3.md](../evidence/L02f3.md)): settling interval fixes H1; the
  acceptance set — 40 isolated runs, 928 checks, 0 failed — finished in 81 s, before the spec
  edits were done. Revision 6 records seven QEMU departures from the manual as `[emulated]`
  EM1–EM7. L02 closes with explicit shortfalls (Q18, Q24–Q26) instead of extending.
- Side quest: a 3D-printed Pi 4 tray for the ENC28J60 module (`49a4299`), test-fit before commit.

### Phase 7 — Overnight follow-ons: closing the gaps L02 left (09-25 20:30 → 09-26 13:10)

The user said to run all follow-ons the same way as milestones; the order was the
orchestrator's (`e30ef6a`). Commit timestamps run through midnight (00:27–00:51) and resume at
07:59.

- **SF-1** `[emulated]` enters the format and checker ([notebook/SF-1.md](../notebook/SF-1.md)).
- **AF-1** a second independent reading of revision 4's changes: no missed accuracy error
  ([notebook/AF-1.md](../notebook/AF-1.md)).
- **QF-1** ([notebook/QF-1.md](../notebook/QF-1.md)): three more claims qualified, Q18 stays
  `unobservable`; discovery — ping payloads are zeros past a 4-byte timestamp, so small-frame
  corruption is invisible.
- **CF-1** candidate updated to revision 6: of 16 spec hunks only two change the driver; one new
  gap (which duplex a TNCRS reading belongs to after a link change) ([notebook/CF-1.md](../notebook/CF-1.md)).
- **SR-7** revision 7: six verification rounds; four FAILs were sentences a fix pass had written
  ([notebook/SR-7.md](../notebook/SR-7.md)).
- **FC-1** ([notebook/FC-1.md](../notebook/FC-1.md)): a planted defect fails every 60/61-byte ping
  while ping reports no loss, because ping reads a raw socket; only the kernel's ICMP
  checksum-error counter sees it.
- **SR-8** revision 8 states the TNCRS attribution rule — the first requirement change since
  revision 6; interrupted by a spend limit and resumed from disk ([notebook/SR-8.md](../notebook/SR-8.md)).
- **CS-1** ([notebook/CS-1.md](../notebook/CS-1.md)): 1 MiB each way in 214-byte frames, checked by
  MD5. Dead end: an MTU of 200 does not make a Linux peer advertise an MSS of 160 (floor 256).
  Round c1 "not as declared" and kept.
- **CF-2** candidate on revision 8: 40/40 twice; of 21 hunks only four matter, all one rule
  ([notebook/CF-2.md](../notebook/CF-2.md)). The model cannot test the crediting itself — hardware.

### Phase 8 — Real hardware: L01 on the Pi 4 fixture (09-26 14:01 → 17:47)

Sources: [evidence/L01-hw.md](../evidence/L01-hw.md), [notebook/L01-hw.md](../notebook/L01-hw.md).

- Both drivers build unchanged against the fixture's 6.18 kernel (`933904f`).
- Development runs, all on the **reference**: every received frame 4 bytes too long (FCS
  included, a predicted defect R-03); peer-to-DUT pings average 158 ms vs 1.2 ms for the
  candidate; `rmmod` under flood hung in `free_irq`, and the fixture took six minutes to come
  back from `reboot`. The candidate's `rmmod`: 0.1 s.
- Round p1: candidate 10/10 then 9/10 (a too-strict rule), reference 8/10 twice.
- The SSH agent refused to sign twice; the runner had read "no answer" as "driver bound" and
  rebooted the fixture; the unit reported blocked (`37bebe7`).
- **Reversal:** the reference's reopen failure was first blamed on an erratum and interrupt
  stall; the reviewer contradicted that, and the captures finally showed the switch's spanning
  tree advertising a non-forwarding port — no ARP reached the DUT. Earlier explanations withdrawn.
- A debug "mask" passed to a bit-count parameter silently logged nothing; a capture writer
  outlived its failed check. Scoped acceptance complete; reviewed by read-only Codex (`b02b687`).

### Phase 9 — From campaign to method: continuous review (09-26 17:08 → 19:04)

- **User's direction** ([evidence/DESIGN-2026-09-26.md](../evidence/DESIGN-2026-09-26.md)): "to
  generate a system to create reliable specs and test them, and over time ensure that we
  continuously review and correct them as the evidence changes and models get better … there are
  diminishing returns to getting every possible last thing corrected." Three sources of change:
  field bugs, updated sources, better models. Seven decisions, including a three-round cap on
  verification (fixes after round two may only delete or narrow).
- Plan CR1–CR8 ([evidence/PLAN-CR-2026-09-26.md](../evidence/PLAN-CR-2026-09-26.md), `c12a8fd`).
- **CR1** claim map and status index: 28 claims, 27 qualified ([evidence/CR1.md](../evidence/CR1.md)).
- **CR2** verification history backfilled for revisions 3–8, 95 section entries, the worked
  chain CF-1 finding → rev 8 → SR-8 → CF-2 ([evidence/CR2.md](../evidence/CR2.md)). The last commit
  in the record (`63ecca9`, 09-26 19:04).

## Proposed outline

**Through-line:** *What does it take before you can believe an agent-written driver spec?* The
answer the record gives is not "a better model" but an accumulating apparatus for catching your
own mistakes — blind answer keys, second readers, checks proven able to fail, and records that
say what they do not show — and then, once it works, the discipline to stop.

1. **"The values were right; the prose was wrong."** Opening on the Pixel 10 verification loop.
   Arc: a spec format meets an adversarial agent; verification becomes a separate agent; the
   addressing model survives only once it is arithmetic. Feeds: Phase 1.
2. **Writing the answer key first.** Arc: to measure a spec you need requirements it could not
   have influenced; errata renumbering, two blind readers, a reviewer refusing the freeze four
   times, a practice run whose perfect precision was meaningless. Feeds: Phase 2.
3. **The pivot.** Arc: the apparatus was growing faster than the product; an outside assessment
   and a user decision to write the driver now, deferring (not waiving) the experiment. Feeds:
   Phase 3, L01 first unit (Phase 4).
4. **A harder device, no bench.** Arc: e1000 in QEMU; independence of harness from spec; a spec
   error that two readings passed and an implementer found. Feeds: Phases 4–5.
5. **Tests that cannot fail, and a model that lies politely.** Arc: C9 — most checks never shown
   able to fail; planted defects, equivalent mutations, A6 amended; QEMU's EE_GNT, receive hold,
   runt delivery; ping's zero payloads and raw socket. Feeds: Phases 5–7 (L02d2, L02d3, L02f1–f2b,
   QF-1, FC-1, CS-1).
6. **The agents' own mistakes.** Arc: fix passes that introduce the next round's FAILs (SR-7,
   Pixel round 6), timestamps written from expectation, reasons written from memory, crashes,
   quota and credit limits; the process log as a first-class output. Feeds: PROCESS-NOTES,
   Phases 1, 6, 7, 8.
7. **Night shift.** Arc: an orchestrator running nine follow-on units overnight, each with a
   declaration frozen before the run and an independent review after. Feeds: Phase 7.
8. **Real silicon, and a switch.** Arc: the reference driver misbehaves in ways the spec
   predicted; a wrong explanation withdrawn when the capture shows spanning tree. Feeds: Phase 8.
9. **Knowing when to stop.** Arc: shortfalls recorded instead of worked; "sufficient for scope";
   continuous review as the answer to evidence and models that keep changing. Feeds: Phases 6, 9.

### Striking moments and numbers

- 21, 15, 18 format defects across three Pixel 10 runs; run 4 died out of credits.
- 2,774 device-tree nodes, 645 with registers, reproduced by three verifiers' own parsers; 410/0
  vs 409/1.
- Gold ledger: 205 rows, two blind readers, freeze refused four times.
- Practice run precision "equal to one" — and explicitly not reported.
- L01: 64/64 critical rows; eight defects found in the upstream reference driver.
- L02c recall 95.5%, yet PSCON bit 11 slipped past both readings.
- Candidate failed every scenario at probe because it obeyed the manual and QEMU didn't.
- 40 acceptance runs, 928 checks, 0 failed, in 81 seconds.
- A corrupted ping reply that ping itself never notices.
- Pi 4: 158 ms vs 1.2 ms pings; `rmmod` hang; six-minute reboot; the switch did it.
- Plan cut from 938 to 533 lines on the user's call.

## Open questions for the author

1. What prompted the project — a specific porting job (Fuchsia is mentioned as a consumer), a
   licensing concern, or curiosity about agent reliability?
2. Why the ENC28J60 and the e1000? The records justify them, but was there a personal reason?
3. The 09-20 pivot: what made you ask for the outside assessment that evening? Did the
   apparatus feel like it was running away?
4. How did it feel to see a Claude and a Codex agent review each other (the freeze refused four
   times; "consensus" plans) — and did you trust their consensus more than either alone?
5. Which of the agents' recurring failures (timestamps from expectation, fix passes adding
   defects) surprised you, and which did you expect?
6. The move to a separate public repository on 09-24: was it about scope, audience, or risk?
7. How much of the overnight run did you watch? What did you do when the SSH agent or spend limit
   stopped work?
8. Cost: the records log a few CLI dollar figures and per-reading minutes, but no total effort.
   Do you have an estimate of human time and spend?
9. Is the deferred experiment (paired with/without-skill runs) still wanted, or has continuous
   review replaced it?
10. What is the private deployment in the continuous-review design for, as much as can be said?
