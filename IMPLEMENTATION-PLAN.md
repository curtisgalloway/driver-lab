<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Driver specification and validation: remaining implementation plan

Revision: 2026-09-25, second amendment (L02g folded into L02f3, L02f2b's H1 fix, review and
record defaults, deferred material moved to [DEFERRED-PLAN.md](DEFERRED-PLAN.md); see
[Revision 2026-09-25](#revision-2026-09-25--lighter-process-for-the-remaining-units) under
L02). Earlier revisions: 2026-09-25 (L02 remaining units revised after a Claude–Codex
consultation; the user approved the changes) and 2026-09-20. No experiment launched by this
plan.

## Terms

- **Spec and companion skill** — the hardware contract and agent instructions for using it,
  supporting documentation, and tools to implement and diagnose drivers.
- **Milestone** — a deliverable with acceptance criteria, tests, review, and a checkpoint.
- **Ledger** — the independently authored hardware-requirement answer key.
- **Arm** — one experimental condition, with or without the specification-authoring skill.
- **Validation contract** — a test's requirements, expected observations, decision rule, and limits.
- **Fixture** — the equipment and connections used for repeatable physical tests.
- **Mutation** — a deliberate defect used to check that a test detects incorrect behavior.

See the [glossary](GLOSSARY.md). Paths below are relative to this plugin unless stated
otherwise. Proposed files are explicitly labeled; their names are not working interfaces yet.

## Design authority and completion boundary

The user reprioritized this plan on 2026-09-20: prioritize the **Linux driver mechanism**
following an independent assessment of whether direct implementation and verification would
serve the practical goal better than the remaining experimental preparation. This revision
adopts that direction. The immediate deliverable is one Linux driver produced using the spec
and existing skills, independently reviewed and meaningfully tested, with demonstrated gaps
repaired in working copies of the driver and spec.

The [overview](DRIVER-QUALITY.md) defines success as less engineering time to a defined quality
bar. The active milestone below tests that useful development loop directly. It does not try
to establish that an authoring skill caused better results independently of model knowledge
or outside assistance. Controlled comparisons can follow after this mechanism demonstrates value.

Reuse the [design](DESIGN.md), [validation proposal](VALIDATION-PROPOSAL.md), and completed
preparation where useful. Preserve the [evaluation plan](EVAL-PLAN.md),
[reconstruction protocol](RECONSTRUCTION.md), and frozen trial artifacts as the authority for
any later **spec-only experiment**. Their isolation, scoring, pairing and attribution gates
remain binding for those experiments; they are not prerequisites for the separately labeled
Linux engineering pass. Do not relabel its outputs as M05, a paired arm, or a qualified
spec-only result. The original [plan review](evidence/PLAN-REVIEW.md) records the earlier scope;
this revision's review is recorded [separately](evidence/LINUX-PRIORITY.md).

The existing board-expert, authoring, implementation and verification skills remain the
companion-skill deliverable. Exercise the useful parts in the Linux pass and repair concrete
usability defects. No new general validation framework or skill is needed to start.

**Immediate completion:** one independently reviewed Linux driver with recorded behavior under
a declared test scope, a requirement-to-evidence table, and versioned spec/driver repairs.
A build-only result is partial. A failed behavior check or unresolved critical requirement is
not a pass; exhausting the agreed effort limit produces an incomplete checkpoint with findings.
Do not erase failed attempts. Completion establishes only the tested Linux behavior and the
observed usefulness of this development pass—not spec completeness, cross-OS portability,
absence of prior knowledge, or a causal skill advantage.

Full documentary acceptance and the wider experimental/workflow qualification decisions remain
separate, deferred outcomes. The current spec's incomplete documentary review remains visible;
using it diagnostically cannot change its frozen acceptance result.

## L01 — Implement and verify the Linux driver

**Status:** `in_progress`. First unit complete 2026-09-22 ([evidence](evidence/L01.md)):
buildable candidate, three independent reviews plus a repair review, spec gaps separated from
implementation errors, repair round 1 of 2 used. Second unit not started; gated on fixture wiring.

**Priority:** active next milestone. A diagnostic engineering pass, not the frozen reconstruction
trial. Reuse the pinned ENC28J60 spec, Linux v6.12 source/toolchain and Pi 4 preparation. The
existing requirement ledger is a review checklist, not a new scoring project. Keep its locked
bytes and the historical spec intact; improvements go into separately versioned working copies.

Keep the working records small: one brief, one requirement-to-evidence table, a gap/repair log,
and source/build/test artifacts. Markdown and existing tools suffice; do not create generic
schemas, a runner framework, or a replay system before the driver can be exercised.
Choose the smallest feature scope that exercises the spec-to-driver-to-verification mechanism.
The Linux pass is a bounded proving step, not a prerequisite to completing every requirement
of this controller before useful work on another platform can start.

### First unit: implement, build and independently review

1. Write the short brief: target/revision assumptions, supported feature scope, build inputs,
   concrete acceptance checks, known fixture uncertainties, selected agent/model and a bounded
   implementation/repair effort limit. Reuse the trial's relevant requirements and reference
   preparation; do not wait for exhaustive documentary scoring. Establish expected outcomes
   from the ledger and source evidence before judging implementation output.
   The user selects the model and effort limit. The preparer and independent reviewer agree on
   the critical requirements and the few checks to challenge with deliberate defects before
   evaluating the driver. Justify feature exclusions against the relevant ledger requirements.
   If scope or checks change after observing results, version the brief, record why, and keep
   the original results visible. Keep driver code in a separate run working directory outside
   the skills repository; record its license and preserve notices on reused code before coding.
2. Start a fresh implementer with the spec and normal Linux development inputs. Ask it to work
   from the spec first and record missing information and assumptions. Permit deliberate,
   logged consultation of reference source, general documentation or operator clarification
   when needed. Record consulted inputs and any source-access uncertainty; source exposure
   limits claims about spec sufficiency but does not invalidate this engineering pass.
   Apply actual source-access restrictions if any separately exist; this public Linux pass
   does not waive requirements for a future cross-OS or restricted-source implementation.
   Record participant/context identities and source exposure so eligibility for later clean-side
   experimental roles can be checked. Reusing a model does not mean reusing an exposed context.
3. Build the driver with the pinned kernel/toolchain and preserve commands, configuration,
   artifacts and logs. Use fresh outputs and case-sensitive extraction with complete source
   identity checks, reusing the existing verifier where appropriate. The earlier extraction
   defect is a real build-integrity issue, independent of experimental isolation.
   L01 uses the ordinary upstream v6.12 tree, including the original target driver/header;
   record that access explicitly. It does not use the incomplete sanitized packet.
4. Have an independent reviewer compare the first driver revision against the relevant ledger
   requirements, source evidence and reference implementation. Cover initialization, receive
   and transmit paths, buffer management, shutdown and required errata/recovery behavior.
   Disagreement with the reference is investigated rather than automatically treated as a defect.
   Run the normal code-review procedure too. Record uncovered requirements and unavailable tests.

**First-unit checkpoint:** a buildable driver or a concrete blocked/failed attempt, independent
review findings, and a short list of spec gaps versus implementation errors. A buildable driver
with unresolved findings is ready for repair/testing, not declared correct. Do not finish the
1,010-path manufacturer audit or M02b harness qualification to reach this checkpoint.
At this checkpoint, explicitly decide whether the next useful step is Linux hardware testing,
a bounded repair, or applying the mechanism to another target. Physical Linux acceptance is
not a prerequisite for the latter; preserve the partial status and transfer only supported
conclusions. Do not let fixture delays trigger unrelated preparation work.

### Second unit: test real behavior and repair demonstrated gaps

- Confirm the actual module, power/wiring, board, boot path and test limits before hardware use.
  Reuse the Pi 4/netboot proposal; historical captures and a reference build do not verify wiring
  or prove the currently booted image. Record the reference/candidate module and image identities.
  Verify which built module is actually loaded and bound; only one driver controls the device
  at a time. Use a documented device-reset procedure between runs to prevent carried-over state.
- Exercise reference and candidate under the same documented configuration and test conditions.
  Changes to required kernel/fixture configuration require a corresponding reference check.
  Start with initialization and link, then bidirectional traffic, packet-size boundaries,
  receive-buffer wrap, repeated stop/start and selected observable error/recovery behavior.
  Select repetitions, traffic conditions and expected results before running each primary check.
  Record evidence that the intended condition occurred, such as actual frame sizes, a buffer
  wrap or the injected fault; a passing verdict without that evidence does not cover the case.
- Verify a few important checks by introducing relevant deliberate defects in disposable test
  copies. For example, a receive-pointer defect must be detected by a suitable wrap test; a
  required delay can be checked through source or trace evidence when timing cannot be faulted
  reliably on the fixture. Do not claim a test is effective because a mutation merely exists.
- Use the compact requirement-to-evidence table to distinguish tested behavior, source-reviewed
  requirements, failures, untested/unobservable cases and explicitly out-of-scope requirements.
  A successful ping is only a smoke test.
  Missing critical evidence keeps the corresponding acceptance decision incomplete.
- Repair demonstrated driver and spec gaps within the agreed effort limit, independently review
  affected changes, and rerun affected checks. Preserve original failures and each repair.
  Record whether a successful behavior was supported by the original spec, outside information,
  or remains unattributable. This is an engineering explanation, not blinded causal attribution.

**Accept L01:** the agreed behavior checks pass; relevant critical source-review findings are
resolved; representative negative controls actually fail as expected; hardware/boot identities
and unavailable coverage are recorded; and the final driver/spec revisions and evidence are
retained. Claims are scoped to those checks. If hardware is unavailable, finish the first unit
and report a partial result; do not substitute simulated or documentary evidence for physical
success. A bounded failure is useful evidence but is not L01 acceptance.

**Measure:** implementation, debugging, review and repair effort where available; model cost;
spec gaps discovered; tested requirements and residual uncertainty. This is one observation of
engineering usefulness, not a measured speedup without a comparison baseline.
L01 supplies scoped evidence toward R1 (requirement records), R5 (supported tests), R6 (physical
identity/results) and R8 (actionable repairs); it does not discharge the proposal's full
requirements or establish R2/R3/R4/R7 experimental acceptance.

**At each checkpoint:** inspect whether the spec/skill helped, what caused actual failures, and what the
next device or OS port needs. Choose further experiments only for an unanswered question worth
their cost. L01 outputs do not retroactively satisfy frozen trial or paired-run requirements.

## L02 — An e1000 driver from a spec, tested differentially in QEMU

**Status:** `complete` 2026-09-25 with L02f3's acceptance stage
([evidence/L02f3.md](evidence/L02f3.md)): *evaluation complete* met; *candidate qualified for
the declared scope* met for the 22 qualified claims, with Q18 and Q24–Q26 outside that scope
as explicit shortfalls. L02a and L02b complete 2026-09-23, L02c, L02e and L02d1 2026-09-24,
L02d2, L02d3, L02s, L02f1, L02f2, L02f2b and L02f3 2026-09-25.
Design: [QEMU-DIFFERENTIAL.md](QEMU-DIFFERENTIAL.md), approved 2026-09-22 with decisions D1–D4
resolved. Runs alongside L01, whose hardware unit waits on the fixture. Outcomes O1–O5 and
acceptance criteria A1–A7 are the design's.

**Conventions for L02.** One topic branch and PR per unit, prefix `driver-porting: L02<x> —`.
Units may be run in orchestrated mode: one fresh subagent executes each unit and an
orchestrator lands it as one PR. Raw runs, the candidate driver, traces, captures, and the
manual stay in the private run store under run IDs `e1000-l02<x>-<date>-<n>`; public evidence
goes to `evidence/L02<x>.md`, naming the test host by role only. Review and records follow the
2026-09-25 defaults below. The operator context reads the reference driver and the QEMU model
and so never writes candidate code; implementer turns go to a separately launched implementer
whose model the user selects.
Possible process improvements noticed while working go to [PROCESS-NOTES.md](PROCESS-NOTES.md)
(user request, 2026-09-24), not into evidence files or this plan.
From L02e on, each unit keeps a lab-notebook chapter at `notebook/<unit>.md`, indexed in
[notebook/index.md](notebook/index.md) (`project-plan` with `lab-notebook`); `PROCESS-NOTES.md`
serves as that skill's process log.

Dependencies: L02a → L02b → L02c → L02e → L02f; L02d needs only L02a and may run in
parallel with L02b–L02c, and L02f also needs L02d (all of L02d1–L02d3). L02s (spec revision
5) needs L02e and may run in parallel with L02d; L02f3's feedback builds on it. Within L02f:
L02f1 → L02f2 → L02f2b → L02f3. L02f3 ends with L02's acceptance stage (formerly L02g).
Revised 2026-09-25 (user approved, after a Claude–Codex consultation): L02d3 added, L02s made
a unit, L02f split in three, and L02f and L02g report two separate decisions.

### Revision 2026-09-25 — lighter process for the remaining units

A second Claude–Codex consultation on 2026-09-25 reviewed the plan's weight and reached
consensus on five amendments; the user adopted them the same day. They replace the earlier
review, check and record rules for L02f2b onward; completed units keep the reviews they had.

1. **Units.** L02f2b stays a separate unit. L02g is folded into L02f3 as its acceptance
   stage; there is no separate L02g PR or report (see L02f3 below).
2. **L02f2b's H1 fix** keeps traffic running through shutdown and adds a bounded settling
   interval after carrier returns; see the L02f2b entry below.
3. **Review default.** Harness units: one independent reviewer reading the diff and the run
   artifacts. Spec units: `spec-verifier` on the changed claims and their dependencies.
   `review-swarm` only when shared execution machinery, access controls or several scenarios
   change, and whenever the reviewer asks for broader review. **Checks:** the changed
   surface's tests plus the privacy check locally; the full suite in CI and at the final
   checkpoint.
4. **Records, one job each.** The private run ledger holds identities, commands, artifacts,
   attempts and reviewer references. The public evidence file holds conclusions, the
   acceptance table, limitations, and consequential findings and their resolutions. The
   notebook holds short chronological discoveries and dead ends. This plan and the notebook
   index hold status and links. Do not repeat findings tables and conclusions across them.
5. **Plan document.** The deferred material (M-series, P01, the deferred experimental plan,
   conditional follow-ons and their backlog items) and the historical L01 conventions and
   input snapshot moved verbatim to [DEFERRED-PLAN.md](DEFERRED-PLAN.md); this plan keeps a
   short disposition table and the active blockers.

Kept as-is: Q15 requalification with artifact review, source separation, artifact identities
and preserved failed attempts, manual-backed expectations with model limitations stated
explicitly, and versioned spec feedback. The consultation record stays in the private run
store; the review of this amendment is [evidence/PLAN-2026-09-25.md](evidence/PLAN-2026-09-25.md).

### L02a — Pin sources and write the blind requirement list

- **Status:** `complete` 2026-09-23 ([evidence](evidence/L02a.md)). Covers D4.
- **Outcome:** manual 317453-006 rev 4.0, the Linux v6.12 e1000 files, and QEMU
  `10.2.1+ds-1ubuntu3.2` (`e1000`, alias `e1000-82540em`) pinned; a 66-row blind list (60
  critical) written from the manual by one fresh agent, checked row by row by a second, and
  frozen by hash.
- **Accept:** all pins recorded and re-fetchable; list frozen with a hash; every row cites a
  manual section; the second reader's disagreements are resolved or recorded.
- **Open limitations:** the list is private until L02c publishes it with the recall result;
  errata were not an input; the model family may have seen the Linux driver in training.

### L02b — Author the spec

- **Status:** `complete` 2026-09-23 ([evidence](evidence/L02b.md)).
- **Outcome:** a clean-room spec of the 82540EM core path (O1, first half): revision 3,
  1,530 lines, SHA-256 `b93d7ef0…d11f`, landed in private run `e1000-l02b-20260923-01`.
  Revision 3 passed its transfer review after one FAIL: an ordering the manual does not
  prescribe had been tagged `[databook]`. Acceptance review found nothing blocking.
- **Accept:** transfer review PASS; every fact tagged; scope and non-goals match the design.
- **Open limitations:** accuracy was sampled only (L02c). Three non-blocking findings, the
  undefined ITR read-back, and two advisories are carried to L02c and L02d. Reviews used fresh
  Claude subagents because `consult` was unavailable.

### L02c — Verify the spec and measure recall

- **Status:** `complete` 2026-09-24 ([evidence](evidence/L02c.md)). Covers A1 through two
  full readings of revision 3, one independent accuracy reading of the revision-4 draft changes,
  and a diff check of the final citation correction.
- **Outcome:** two fresh readings of revision 3 found 6 errors, all fixed in revision 4: 1,601 lines, SHA-256 `0490a888…3472`, landed in private run
  `e1000-l02c-20260924-01`. Recall on revision 3 was 63 of 66 rows covered and 3 partial, none
  missing; the list and per-row table are published in [`evals/e1000/`](evals/e1000/).
- **Accept:** no unresolved FAIL; every GAP and UNVERIFIABLE recorded; recall reported by row,
  with each missing critical row either added to a spec revision or recorded as a gap.
- **Open limitations:** revision 4's changes had one independent reading, not two (a second,
  independent reading followed in [AF-1](evidence/AF-1.md)); recall was
  not re-measured on revision 4; four claims rest on unread PCI/IEEE standards; row INIT-005
  overstates the manual and stays in the frozen list.

### L02d — Build the QEMU harness and prove it on the reference driver

- **Outcome:** O3 and the harness half of A3, A4, and A6, before evaluating the candidate.
- **Steps:** build a v6.12 x86-64 kernel on the test host with the reference `e1000` as a
  module; a busybox initramfs with the scenario scripts; a peer guest on a point-to-point
  socket network; per-run capture of register traces, packets, console, and verdicts. Run
  every scenario against the reference driver. Then plant each design mutation in a
  disposable copy of the reference driver and confirm a scenario or trace check fails.
- **Accept:** one command runs the whole suite unattended; the reference passes or each
  failure is explained by the manual; every planted defect is detected; outputs are stored per
  run with identities.
- **Review:** `review-swarm` on the harness code, plus a fresh reviewer on whether each
  scenario actually exercises what it claims (for example, that a ring-wrap run really wraps).
- **Size:** originally estimated at one to two sessions, split point boot-and-capture first,
  scenarios and mutations second; split 2026-09-24 at that point into L02d1 and L02d2. L02d3
  was added 2026-09-25, so L02d now comprises three separately checkpointed units:
- **L02d1 — boot and capture.** Status: `complete` 2026-09-24
  ([evidence](evidence/L02d1.md), [notebook](notebook/L02d1.md)). One command on the test
  host boots the DUT (reference `e1000`) and a virtio-net peer, runs `smoke` (probe, MAC,
  carrier, pings both ways, unload), and stores the register trace, both captures, consoles,
  command logs, verdicts and hashes per run; harness in `evals/e1000/harness/`. Verdicts are
  PASS, FAIL (a guest misbehaved; exit 1) or ERROR (harness or host; exit 2). Open
  limitations: smoke does not check the kernel log; the EEPROM check shows use of the
  interface, not the MAC's source; `--accel tcg` untested; the late-connect fix not reproduced
  live.
- **L02d2 — scenarios and mutations.** Status: `complete` 2026-09-25
  ([evidence](evidence/L02d2.md), [notebook](notebook/L02d2.md)). Ten suite scenarios, a
  kernel-log check after every scenario, trace decoding with per-phase labels, manual-based
  trace rules, five planted defects: m2–m5 detected, m1 an equivalent mutation. Three
  reviews (review swarm, a scenario-coverage reviewer, then a Codex review of the fixes whose
  three medium findings were fixed); the reference passes twice on the final harness. Open
  limitations there, notably C9 (most checks never shown able to fail) and leftover frames
  contaminating later scenarios; both are L02d3's inputs.
- **L02d3 — check qualification.** Status: `complete` 2026-09-25
  ([evidence](evidence/L02d3.md), [notebook](notebook/L02d3.md)). 26 claims (24 frozen before
  any defect run, 2 added after review, all before any candidate run); 22 qualified by a
  planted defect in isolated runs (one scenario per fresh boot), most with a narrower scope
  stated in the evidence; Q18 (1 µs after reset), Q24 (interface up, rmmod), Q25 (60/61-byte
  receive) and Q26 (first load and bind) unqualified with reasons. 17 new defects; d09 an
  equivalent mutation, d16 apparently inactive. No harness code change; the README now says
  qualified evidence comes from isolated runs, which L02f must use. Reviewed by a fresh Codex
  session reading the raw runs. Open limitations: Q09 detects receive corruption only as a
  stalled transfer; transmit-ring tail rule and TDBAL-only alignment; see the evidence.
  - **A6 amended 2026-09-25 (user approved):** "Each validated non-equivalent planted defect
    is detected by at least one scenario or trace check; equivalent mutations are reported
    separately as valid controls." m1 is reported as an equivalent mutation under the amended
    criterion; the original wording is kept in the design.

### L02e — Implement, build, and review the candidate

- **Status:** `complete` 2026-09-24 ([evidence](evidence/L02e.md), [notebook](notebook/L02e.md)).
  Covers O2 and A2.
- **Outcome:** `e1000_l02`, 1,569 lines, written by a fresh Claude Opus 5.5 implementer from spec
  revision 4 alone, in private run `e1000-l02e-20260924-01`. It builds against the verified v6.12
  x86-64 tree on the test host (with `gcc-14`; GCC 15 cannot build v6.12) with zero warnings at
  default and W=1. All 60 critical blind-list rows implemented; one repair round fixed seven
  findings (one spec error among them) and correctly declined an eighth.
- **Accept:** as L01's first unit, plus a clean command-log audit.
- **Open limitations:** never loaded or run; isolation by instruction and audit only (8 audit
  marker findings, all traced to allowed targets); two low findings from the repair review and
  several spec gaps are open for L02f or the next spec revision; spec §5.4/§9.2 (PSCON bit 11)
  needed amending (done in L02s, revision 5).

### L02s — Spec revision 5

- **Status:** `complete` 2026-09-25 ([evidence](evidence/L02s.md), [notebook](notebook/L02s.md)).
  Revision 5, 1,604 lines, SHA-256 `c587f41d…d01b`, landed in private run
  `e1000-l02s-20260925-01`: revision 4 plus five changed passages. G4 now sets bit 11 as an
  `[inference]` from §8.4.2 and Table 13-31 (confidence medium, contrary text recorded), and
  must precede the AN restart for bit 11 as well as 6:5 (§11.1.3). A first fresh
  `spec-verifier` reading found 2 FAIL and 2 GAP, all fixed; a second passed all 15 changed
  claims. Open limitations: only changed claims verified; text rendering of the manual only;
  both verifiers' out-of-scope notes and the §4.7 TNCRS mapping go to L02f3.
- **Outcome:** a reviewed spec revision 5 that amends §5.4 G4 and §9.2 to set PSCON (PHY
  register 16) bit 11, per the L02e spec error (manual §13.7.12, Table 13-31).
- **Steps:** a source-backed correction in a new working copy; review of the affected claims
  (`spec-verifier`); a new hash and its relation to revision 4 recorded. Spec only: the
  candidate already sets the bit after its L02e repair. Revision 3's recall result stays as
  measured on revision 3.
- **Size:** small; may run alongside L02d3.

### L02f — Differential run, repair, and feedback

- **Outcome:** O4, O5, A5, A7. Split 2026-09-25 into three units, each one session; L02f2b
  was added between L02f2 and L02f3 the same day.
- **L02f1 — initial run and attribution.** Status: `complete` 2026-09-25
  ([evidence](evidence/L02f1.md), [notebook](notebook/L02f1.md)). Identities frozen before
  any run; reference 10/10 PASS in isolated runs (A4). The candidate failed all ten scenarios,
  twice isolated and once as a full suite, at probe, for one cause: QEMU always reports
  EECD.EE_GNT set (the manual's initial value is 0b), and the candidate enforces spec E1 (the
  manual's §13.4.4 note) by aborting probe. Labeled `benign`, model limitation, with a
  secondary spec gap (E1 gives no bound or fallback when the grant stays set); five probe
  divergences, all `benign`. Reviewed by a fresh subagent reading the raw runs, in two turns
  (13 then 6 findings, all fixed). Open limitations: nothing after probe has run; neither L02f decision is met.
- **L02f2 — bounded repair and retest.** Status: `complete` 2026-09-25, after one of three
  rounds ([evidence](evidence/L02f2.md), [notebook](notebook/L02f2.md)). Codex (`gpt-6-astra`)
  repaired E1 inside a bubblewrap sandbox with an strace audit (canary pilot and round 1
  PASS). The candidate binds and, in isolated runs, passes 9 of 10 scenarios; the reference
  passes 10 of 10. `down-during-traffic` fails one check at random (3 of 6 runs): the reply
  reaches the guest's ICMP layer (six of six measured runs) and ping misses it, because
  QEMU's one-second receive hold after an RCTL write ends, with the candidate's faster
  carrier detection, just as the ping starts, releasing about 30 frames left over from the
  flood ahead of it (V6, `benign`, model limitation plus harness weakness H1). No candidate defect past
  probe, so no round 2. First past-probe comparison: V7–V16, all `benign`. Reviewed by
  `review-swarm` (13 findings, fixed or recorded) and a fresh artifact reviewer (14, all
  fixed). Open: H1 (Q15 unresolved until fixed and requalified); egress blocking and readable
  `/usr` and `/etc` in the sandbox, for the user; spec gaps for L02f3.
- **L02f2b — harness fix H1 and Q15 requalification.** Status: `complete` 2026-09-25
  ([evidence](evidence/L02f2b.md), [notebook](notebook/L02f2b.md)): H1 fixed with a bounded
  settling interval after carrier; Q15 requalified, scope unchanged; the candidate's Q15
  result is PASS.
  Added 2026-09-25 (user decision); a small unit that runs before L02f3. Revised the same day (see
  [Revision 2026-09-25](#revision-2026-09-25--lighter-process-for-the-remaining-units)); the
  earlier fix, stopping both floods before the interface goes down, is withdrawn.
  - **Fix:** keep traffic running through shutdown; the harness already stops both floods
    after the DUT's interface goes down. Add a documented, bounded settling interval after
    carrier returns and before the recovery pings, longer than the model's 1 s receive hold
    plus a margin, with the length confirmed from traces. No ping retry.
  - **Requalification shows:** traffic in both directions right before shutdown (the existing
    stimulus check); floods stopped, and the measured pings sent after the hold and the
    residual burst of leftover frames; reference and candidate both passing, in isolated
    runs, a repetition count declared before looking, under comparable host load, with
    failures retained; and planted defect d15 still failing the recovery check for the
    intended reason. Q15 keeps its "qualified, not traffic-specific" limit.
  - **Review:** one independent reviewer reading the diff and the run artifacts.
  - The sandbox questions L02f2 left open are settled as D7 and D8 (see "Decisions and bounded
    investigations"), and the copied Codex credential in the L02f2 run has been deleted
    (recorded in that run's ledger).
- **L02f3 — spec feedback, reverification and L02 acceptance.** Status: `complete`
  2026-09-25 ([evidence](evidence/L02f3.md), [notebook](notebook/L02f3.md)): spec revision 6
  (`f78ea07a…45b2`, four sequential verifier readings ending at 0 FAIL); the final isolated
  run set on the final harness, reference and candidate 20 of 20 each; the A1–A7 table; both
  decisions met, with Q18 and Q24–Q26 outside the qualified scope as shortfalls; `[emulated]`
  recommended for the format as follow-on SF-1. Follows L02f2b; the last L02
  unit. Revised 2026-09-25 to take in L02g as its acceptance stage. It changes no candidate
  code; any candidate change is a named follow-on with its own review (the L01 review trio).
  - **Spec feedback:** fold every `[emulated]` result and spec gap into a versioned spec
    working copy built on L02s, and reverify the changed claims and their dependencies
    (`spec-verifier`).
  - **Acceptance stage (formerly L02g):** one final set of isolated reference and candidate
    runs on the final harness, from a clean checkout; one A1–A7 acceptance table, checking
    each criterion against its evidence and covering interactions between units, including
    how the revised spec meets or falls short of A1's two-reading requirement; and an
    independent review. The table also audits final artifact identities, qualification
    coverage, the revised spec's review and the repair audit, and decides, based on how it
    was used, whether the `[emulated]` class goes into `SPEC-FORMAT.md` and the evidence model
    (a separate unit if that change affects the format's consumers or checks). No separate
    L02g PR or report.
  - **Closing:** close with explicit shortfalls, among them Q18 and Q24–Q26 unqualified,
    rather than extending the campaign to earn a label. New engineering work found here is
    recorded as a shortfall or a named follow-on, not added to L02.
- **Accept, reported as two decisions:** *evaluation complete* (every scenario result recorded,
  failures repaired or recorded as open findings, evidence separating spec gaps, spec errors,
  implementation errors and model limitations); and *candidate qualified for the declared
  scope* (the required checks pass, each is qualified in L02d3, no blocking finding is
  unresolved, and no unresolved mandatory claim remains; any such claim withholds
  qualification and is listed as a shortfall). The first can be met while the second is not.
  L02f3's acceptance stage reports both over A1–A7: evaluation complete (each criterion has
  evidence or an explicitly recorded shortfall), and candidate qualified for the declared
  scope, which any unresolved mandatory claim withholds.

### L02g — Final check against the design

- **Status:** folded into L02f3 as its acceptance stage on 2026-09-25 (see
  [Revision 2026-09-25](#revision-2026-09-25--lighter-process-for-the-remaining-units)); no
  separate unit, PR or report.

### Follow-ons named in L02f3

Named in the [L02f3 evidence](evidence/L02f3.md#follow-ons-named-not-scope). On 2026-09-25
the user asked for all of them to be run the same way as the milestones (one fresh
implementer, one unit and one PR each); the order below was the orchestrator's choice, not
the user's.

- **SF-1 — `[emulated]` in the format.** Status: `complete` 2026-09-25
  ([evidence](evidence/SF-1.md), [notebook](notebook/SF-1.md)). The class is in
  `SPEC-FORMAT.md`, the design's evidence model and `spec_check.py` (a citation parenthetical
  present, the TODO, and the never-alone rule, with tests); the shipped board specs still pass.
- **AF-1 — a second reading of revision 4's changes.** Status: `complete` 2026-09-25
  ([evidence](evidence/AF-1.md), [notebook](notebook/AF-1.md)); the second-reading option
  was taken, the recall re-measurement stays open. One item for the next spec revision; A1's
  remaining shortfalls are stated in the evidence.
- **QF-1 — the four unqualified claims.** Status: `complete` 2026-09-26
  ([evidence](evidence/QF-1.md), [notebook](notebook/QF-1.md)). Q24, Q25 and Q26 qualified by
  planted defects; Q18 stays unqualified (`unobservable` on this host and model) with the
  reset rule restated as what the trace can observe; two items for CF-1's spec revision (the
  model delivers runts; the reference's probe error path warns) and one possible new check
  (small-frame content).
- **CF-1 — candidate on revision 6.** Status: `queued`, next; its workspace and brief are
  prepared, and its Codex launch waits for the user.
- **HF-1 — hardware.** Status: `blocked` on an 82540EM or the nearest available part.

## What is deferred from the immediate path

| Work | Disposition |
| --- | --- |
| Complete source sanitization, related-controller removals and harness isolation (remaining M02) | Preserve the current artifacts and audit findings. Resume only for an explicitly selected spec-only experiment; not required for L01. |
| Generic execution contracts and synthetic replay (M03–M04) | Use a brief, evidence table and ordinary build/test logs for L01. Build shared machinery only after demonstrated need. |
| Frozen spec-only trial and dual blinded attribution (M05/M08) | L01 permits logged outside assistance and repairs; keep these experimental conditions separate. |
| Fixture and meaningful test qualification (parts of M06–M07) | Keep the necessary hardware identity, expected outcomes and negative controls in L01; do not require the generic experimental infrastructure. |
| Paired authoring/implementation and complete documentary scoring (M09–M13, P01) | Optional follow-on to answer comparative questions; no immediate gate. |
| Test-authoring experiments and companion-skill ablation (M14–M15) | Exercise useful existing skills in L01; defer controlled comparisons. |
| Automated maintenance/invalidation and full pilot qualification (M16–M17) | Preserve versioned evidence now; defer general machinery and broader claims. |

The detail behind these rows is in the [deferred plan](DEFERRED-PLAN.md): decisions D1–D6, the
[M01–M17 and P01 dependency table](DEFERRED-PLAN.md#sequence-and-dependencies) and milestone
text, design coverage, the conditional follow-ons, their backlog items, and the historical L01
conventions and input snapshot, all moved there verbatim on 2026-09-25. Deferred means
unfinished, not waived or complete.

**Active blockers:**

- **L01 second unit:** waits on fixture wiring ([evidence/L01.md](evidence/L01.md)).

## Decisions and bounded investigations

The plan's D1–D6 belong to the deferred experimental plan and moved with it
([deferred plan](DEFERRED-PLAN.md#decisions-and-bounded-investigations)). D7 and D8 govern L02.

| ID | Resolve before | Question and required evidence |
| --- | --- | --- |
| D7 | L02f2b (resolved) | Clean-room sandbox network egress. **User decision, 2026-09-25:** audit-only is accepted for L02 (strace records egress; nothing blocks it), a ratified departure from M02a's enforced network denial. An allowlisting proxy only if a later unit needs one. |
| D8 | L02f2b (resolved) | Clean-room sandbox read scope. **User decision, 2026-09-25:** readable `/usr` and `/etc` are ratified, with the kernel source and module trees (`/usr/src`, `/usr/lib/modules`) hidden, as `cleanroom_sandbox.sh` does. |
| D9 | recorded at L02f3 | Implementer routing in orchestrated mode. **User decision, 2026-09-25:** routing follows the user's quota strategy: Claude (Fable) subagents by default; Codex as overflow only for units outside the clean-room separation, since Codex is this project's audited clean-room implementer (L02f2). |

Investigations end with evidence-backed choices or explicit blockers, not open-ended exploration.
Do not invent commands, tool APIs, pin names, or equipment capabilities. A necessary material
design amendment returns to the design approval gate before dependent implementation.

## Checks to use during execution

From the repository root, before each checkpoint commit, run the tests for the changed surface
and the privacy check, plus `git diff --check` for documentation; the full suite that
[AGENTS.md](AGENTS.md#checks) lists (the same steps as `.github/workflows/checks.yml`) runs in
CI on every pull request and locally at the final checkpoint (revised 2026-09-25; see
[Revision 2026-09-25](#revision-2026-09-25--lighter-process-for-the-remaining-units)). The
ENC28J60 ledger check is not in CI; run it when the ledger or its lock is touched:

```sh
uv run --with pyyaml python3 evals/enc28j60/ledger_check.py evals/enc28j60/ledger.yaml --lock evals/enc28j60/ledger.lock
```

## Discovered work and backlog

Backlog items owned by deferred milestones (M02/M05, M11) are in the
[deferred plan](DEFERRED-PLAN.md#discovered-work-and-backlog).

- **Historical status text:** DESIGN.md and VALIDATION-PROPOSAL.md contain older ledger/scorer
  status descriptions; DRIVER-QUALITY.md describes the controlled evaluation now deferred.
  Current pilot artifacts and this priority revision govern; refresh those descriptions when publishing
  the next status update, without changing their design decisions or calling new work complete.
- Record further discoveries with impact and owner milestone. A completion blocker stays in its
  milestone; this backlog cannot be used to waive a failed acceptance criterion.

## Next session

The work now lives in this repository (`driver-lab`); [TRANSITION.md](TRANSITION.md) records
the move. **L02 is complete** (2026-09-25): every unit has its evidence file ([L02a](evidence/L02a.md),
[L02b](evidence/L02b.md), [L02c](evidence/L02c.md), [L02e](evidence/L02e.md),
[L02d1](evidence/L02d1.md), [L02d2](evidence/L02d2.md), [L02d3](evidence/L02d3.md), [L02s](evidence/L02s.md),
[L02f1](evidence/L02f1.md), [L02f2](evidence/L02f2.md), [L02f2b](evidence/L02f2b.md),
[L02f3](evidence/L02f3.md)), and L02f3's acceptance table reports the two decisions with their
shortfalls. Do not start two units in one session; in orchestrated mode each unit is one fresh
subagent and one PR (implementer routing: D9). Read [notebook/index.md](notebook/index.md)
first. Review, checks and records follow the
[2026-09-25 defaults](#revision-2026-09-25--lighter-process-for-the-remaining-units).

- **No L02 unit is queued.** The follow-ons L02f3 named run in the order of the
  [follow-on list](#follow-ons-named-in-l02f3) (the user asked for all of them on
  2026-09-25; the order is the orchestrator's):
  SF-1, AF-1 and QF-1 are complete; **next is CF-1** (rebuild the candidate from revision 6
  and rerun the acceptance set on the QF-1 harness `7024864e…`; the next spec revision also
  takes AF-1's six items, SF-1's `[emulated]` pointer form, and QF-1's F2, the model
  delivering runts at their wire length). CF-1's workspace and brief are prepared; its
  Codex launch waits for the user. HF-1 (the hardware verifications emulation cannot do,
  now including Q18's 1 µs rule, `unobservable` in emulation) is blocked on hardware.
- **L01 second unit (blocked on the fixture):** unchanged; see [evidence/L01.md](evidence/L01.md).
- Transcripts: record each subagent's transcript path in the run's ledger; do not copy them
  (user rule, 2026-09-23).
