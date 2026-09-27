<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Driver specification and validation: remaining implementation plan

Revision: 2026-09-25, second amendment (L02g folded into L02f3, L02f2b's H1 fix, review and
record defaults, deferred material moved to [DEFERRED-PLAN.md](DEFERRED-PLAN.md); see
[Revision 2026-09-25](#revision-2026-09-25--lighter-process-for-the-remaining-units) under
L02). 2026-09-26: the [continuous-review milestones](#cr--continuous-review) CR1–CR8 and
CR-G added from the design's C1–C8. Earlier revisions: 2026-09-25 (L02 remaining units revised after a Claude–Codex
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

**Status:** `complete` for scoped implementation and hardware acceptance
([first-unit evidence](evidence/L01.md), [hardware evidence](evidence/L01-hw.md)). The
unchanged candidate passed all ten r3 checks; repaired harness terms were qualified with
negative controls, and all fixture artifacts were verified. No further candidate/spec
repair was needed; repair round 1 of 2 remains the only one used. L01c's independent
artifact/code review and import of its local checkpoint bundle remain before landing.

**Priority:** acceptance recorded; review and landing next. A diagnostic engineering pass,
not the frozen reconstruction trial. Reuse the pinned ENC28J60 spec, Linux v6.12 source/toolchain and Pi 4 preparation. The
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
- **CF-1 — candidate on revision 6.** Status: `complete` 2026-09-26
  ([evidence](evidence/CF-1.md), [notebook](notebook/CF-1.md)). One audited clean-room round
  (Codex, launched by the user) changed the two behaviors revision 6 requires of this driver
  (FWE = 01b on the EECD write; TNCRS reported in full duplex only), the rest already met;
  reference and updated candidate 20 of 20 each on the QF-1 harness, declared before the run;
  the L01 review trio (reference review, requirements review, `review-swarm`) found no bug.
  For the next spec revision: the TNCRS attribution rule across a duplex change; for the next
  implementer round: the file header's revision number.
- **SR-7 — spec revision 7.** Status: `complete` 2026-09-26
  ([evidence](evidence/SR-7.md), [notebook](notebook/SR-7.md)). A second independent reading
  of revisions 5 and 6's changes, then revision 7 on revision 6; approved by the user
  2026-09-26. Three items for the next revision are in the evidence.
- **FC-1 — a small-frame content check.** Status: `complete` 2026-09-26
  ([evidence](evidence/FC-1.md), [notebook](notebook/FC-1.md)). From QF-1's F3, approved by
  the user 2026-09-26. `frame-sizes` sends its 60/61-byte pings with a pattern payload and
  checks the content from both captures and from the DUT kernel's ICMP checksum-error count;
  a new claim Q27 (small-frame content, both directions) qualified by QF-1's d21c and a new
  transmit defect, 3 of 3 each; reference and candidate 20 of 20 on the changed harness and
  `frame-sizes` 5 of 5 each, declared before the run; every existing check name unchanged.
  The review's one code finding (a failed counter read could hide a rise) fixed and the
  scenario rerun on the final harness `884e771c…`, 8 of 8.
- **SR-8 — spec revision 8.** Status: `complete` 2026-09-26
  ([evidence](evidence/SR-8.md), [notebook](notebook/SR-8.md)). Approved by the user
  2026-09-26, who chose CF-1's reviewer-A rule ("drain at link change"). Revision 8 on
  revision 7: the TNCRS attribution rule in §4.7 and a new §5.9 step (a driver-requirement
  change, stated in the header; the current candidate does not yet follow it) and SR-7's
  three wording items. The next candidate round, which implements the rule, is CF-2, approved
  by the user 2026-09-26.
- **CS-1 — checksum-preserving corruption of received small frames.** Status:
  `complete` 2026-09-26 ([evidence](evidence/CS-1.md), [notebook](notebook/CS-1.md)).
  From FC-1's open limitation (a checksum-preserving corruption of a reply the DUT
  receives was detected by no check), approved by the user 2026-09-26. `frame-sizes` now
  carries 1 MiB over HTTP each way in frames of at most 214 bytes (the peer's MTU and
  advertised-MSS floor lowered for the streams, which bounds both directions and touches
  nothing on the DUT) with the delivered bytes checked by MD5; a new claim Q28 qualified
  by two planted defects that swap two 16-bit words, on receive (d25) and on transmit
  (d26), 3 of 3 each, failing exactly their stream check; reference and candidate 20 of
  20 on the acceptance set and `frame-sizes` 5 of 5 each on the final harness
  `a1735b9f…`; the guest image unchanged; every existing check name unchanged. Round `c1`
  was not as declared and is kept: the kernel's advertised-MSS floor of 256 kept the
  DUT's frames at 310 bytes (a check-design error, F1, fixed for round `c2`). 27 of 28
  claims qualified; the review's seven findings applied or recorded.
- **CF-2 — candidate on revision 8.** Status: `complete` 2026-09-26
  ([evidence](evidence/CF-2.md), [notebook](notebook/CF-2.md)). Approved by the user
  2026-09-26 ("Run the next round when able"). One audited clean-room round (Codex, launched
  by the user) implemented revision 8's TNCRS attribution rule (one sample under the
  statistics lock, seeded at the clearing read; every reading credited by the previous sample;
  the link check drains under the lock) and the header's revision number, the other 17 spec
  hunks already met or not driver behavior; reference and updated candidate 20 of 20 each on
  the FC-1 harness `884e771c…`, declared before the run, and 20 of 20 again on CS-1's harness
  `a1735b9f…` (round `a2`, declared first; 27 of 28 claims qualified for the updated
  candidate); every trace difference from CF-1's candidate attributed (the three the rule
  predicts, plus cadence); the L01 review trio found no bug. The rule is unobservable on the model (its link never changes duplex); its hardware
  check is on HF-1's list.
- **HF-1 — hardware.** Status: `blocked` on an 82540EM or the nearest available part. Its
  list: Q18's 1 µs reset rule (`unobservable` in emulation, QF-1); CF-1's FWE write and
  half-duplex TNCRS behaviors (no scenario exercises them); revision 8's TNCRS attribution rule
  (§4.7's method: a 10/100 link whose partner switches duplex, SR-8 and CF-2; CF-2's reference
  review adds two more: transmit at full duplex, drop the link, return at half duplex and
  compare the carrier-error totals per interval; and read STATUS.FD right after G7 with no
  link and record it, so the first interval's duplex is known).

## CR — Continuous review

**Status:** CR1 complete (PR #29); CR2 complete (PR #30); CR3 complete (PR #31); CR4 complete (PR #32); CR5 complete (PR #33); CR6 complete (PR #34; CR6a, CR6b); CR7 complete (PR #35); CR8 complete (PR #36; revision 9); CR-G complete (the layer's [acceptance table](evidence/CR-G.md); acceptance waits on the user's reading of C6's last clause, and the orchestrator's `review-swarm`); next, revision 10 for CR8's two remainder items, decided by the user. Derived 2026-09-26 from the design's
[Continuous review](DESIGN.md#continuous-review-keeping-specs-right-as-evidence-changes)
section, requirements C1–C8, as approved by the user on 2026-09-26 at commit `d9a3d66` (merged
as pull request #26, `80eb11b`); the decisions taken before approval are in
[evidence/DESIGN-2026-09-26.md](evidence/DESIGN-2026-09-26.md). The plan's review is
[evidence/PLAN-CR-2026-09-26.md](evidence/PLAN-CR-2026-09-26.md).

**Terms** (full definitions in the design's Terms block and the [glossary](GLOSSARY.md)):

- **Status index** — `evals/e1000/status.yaml`: one entry per tracked verdict or item, with its
  basis and status. **Claim map** — `evals/e1000/claims.yaml`: claim ID to harness checks and
  qualifying defects and runs.
- **Sweep** — one local command comparing every basis in the index with the current
  identities; it prints the stale set, the stopping-rule state and the tier-1 queue.
- **Source registry** — the list of sources by local ID, version and hash that the sweep reads
  as "current". **Deployment manifest** — the YAML file declaring a deployment's plugins and
  its models by role.
- **Tier 0 / 1 / 2** — no model, every change / queued agent units in batches of at most three
  / only on a person's decision. **Sufficient for scope** — C6's state (S1–S5).

### Conventions for CR

- One topic branch and one pull request per milestone, prefix `driver-porting: CR<n> —`;
  evidence in `evidence/CR<n>.md`, a notebook chapter in `notebook/CR<n>.md` indexed in
  [notebook/index.md](notebook/index.md); private material in the run store under run IDs
  `e1000-cr<n>-<date>-<n>`. Push, pull requests and merges follow [AGENTS.md](AGENTS.md).
- **Orchestrated execution and quota routing (D9) still apply:** each milestone, and each
  tier-1 unit inside CR6, is one fresh subagent; routing follows the user's quota strategy,
  Claude subagents by default and Codex as overflow only for work outside the clean-room
  separation. No CR milestone launches a clean-room implementer.
- Review and records follow the [2026-09-25 defaults](#revision-2026-09-25--lighter-process-for-the-remaining-units).
  Code milestones: one independent reviewer reading the diff **and** the sweep's or check's
  output on the real e1000 index (the artifact); `review-swarm` where named below because the
  code decides what runs unattended. Data milestones: a reviewer tracing a declared sample of
  entries to public evidence. Spec readings: `spec-verifier`, as today.
- **Once CR1 lands, the index is the status record** for e1000's verdicts and open items (C1's
  one-job rule): this plan and the evidence files link to it rather than restating which items
  are open. Completed evidence files are not edited to remove their tables.
- **Proposed locations** (decided here so no milestone re-litigates them; still proposed until
  built): the method's code as a new skill, `skills/campaign-review/` (a `SKILL.md` for the
  orchestrator, `scripts/`, `tests/`), so that a private deployment gets it by installing this
  plugin (C7); the index format in `skills/campaign-review/INDEX-FORMAT.md`; the public reference
  manifest and registry for the public campaigns as `evals/deployment.yaml` and
  `evals/e1000/sources.yaml`. YAML is read with PyYAML under `uv run --with pyyaml`, as the
  ENC28J60 tools do; CI reuses that job's venv. Scripts follow the cli-conventions exit
  contract `spec_check.py` documents (0 clean, 1 findings, 2 usage error, 3 missing
  precondition). The skill's `SKILL.md` stays a short orchestrator section.
- **Guard against over-building (the design's):** the layer adds the index and claim map, the
  registry, the manifest schema, the sweep, the contract check and their tests. No service,
  database, scheduler, automated spec edit or automated merge; anything more needs a design
  change first. A milestone that finds it needs more stops and says so.

### Milestones

| ID | Outcome | Covers | Depends on | Size | Status |
| --- | --- | --- | --- | --- | --- |
| CR1 | e1000 claim map and status index: claims, qualifications, candidate results, `[emulated]` observations, open items; index check in CI | C1 (most), C6 S1–S3 data, C3 tier-0 index check | — | one session | complete (PR #29) |
| CR2 | Spec verification history in the index by section (revisions 3–8), and the SR-8 → CF-2 path backfilled | C1 (rest), C5 (backfill) | CR1 | one session | complete (PR #30; [evidence](evidence/CR2.md)) |
| CR3 | The sweep, tier 0: source registry, the pinned-file adapter, C2 invalidation with widening | C2, C3 (detection), C7 (registry detection), C8 (reference adapter) | CR2 | one session | complete (PR #31; [evidence](evidence/CR3.md)) |
| CR4 | Stopping rule and tier-1 queue: S1–S5, item rules, the batch cap, the tier-2 guard, the rule (policy) comparison guard | C6, C3 (queue), C4 (trigger) | CR3 | one session | complete (PR #32; [evidence](evidence/CR4.md)) |
| CR5 | Deployment manifest and contract check: the manifest schema and models by role, the `deployment` config key, contract checks for the source adapter and fixture backend, stubs, the producer-class rule | C8, C4 (role change), C7 (roles) | CR4 | one session | complete (PR #33; [evidence](evidence/CR5.md)) |
| CR6 | First tier-1 batch from the queue: the second reading of revision 8's requirement change, and a comparison reading by a new reading model | C3 (batch), C4, C6 (e1000 verdict) | CR5; the user names the new reading model | two unit sessions plus the orchestrator's batch close | complete (PR #34; [CR6a](evidence/CR6a.md), [CR6b](evidence/CR6b.md)) |
| CR7 | A stand-in private deployment, created by the tests, runs the method end to end with stub plugins only | C7, C8 (stub-only clause) | CR5 | one session | complete; reviewed ([evidence](evidence/CR7.md)) |
| CR8 | One live W or E item carried through a spec revision, the index updated at each step | C5 (live item) | CR2, CR4; **a revision made for another reason**, or the user's decision (see below) | one session | complete (PR #36; [evidence](evidence/CR8.md)); revision 9; the two remainder R items decided by the user for revision 10 |
| CR-G | Layer acceptance against C1–C8 together | all | CR1–CR7; CR8 or the user's decision on C5 | one session | complete ([evidence](evidence/CR-G.md)); C1–C5, C7, C8 met (five with stated limits); C6's last clause for the user |

CR6 and CR7 may run in parallel after CR5. CR8 waits on an outside condition and holds up
nothing before CR-G. Publishing L01's Pi fixture harness as a second reference backend is not a
milestone: C8's criterion names the QEMU backend only; it is recorded in the deferred table
below.

Requirement coverage:

| Req | Where met | Accept criterion checked in |
| --- | --- | --- |
| C1 basis and index | CR1, CR2 | CR2 (reviewer traces every entry), CR-G |
| C2 invalidation | CR3 | CR3 (synthetic change matrix), CR7 (stand-in) |
| C3 tiers and queue | CR1 (index check), CR3 (detection), CR4 (queue, cap, guard, changed identity → units), CR6 (batch) | CR4, CR6, CR-G |
| C4 comparison readings | CR4 (trigger), CR5 (roles), CR6 (the reading) | CR6 |
| C5 findings to a revision | CR2 (SR-8 → CF-2 backfill), CR8 (live item) | CR8, or deferred on a condition (below) |
| C6 stopping rule | CR4 (evaluation), CR6 (e1000 verdict) | CR6, CR-G |
| C7 private deployment | CR3 (registry), CR5 (roles), CR7 | CR7 |
| C8 extension points | CR3 (reference adapter), CR5 (manifest, contract check), CR7 (stubs only) | CR5, CR7 |

**One criterion is deferred on a condition: C5's live item.** It needs a spec revision, and C6
says a W item never starts one ("W items wait for the next revision made for another reason").
CR8 therefore runs only when a revision is made for another reason: an R item (CR6's readings
may produce one), an E item that changes a claim's status in scope, or a stale entry whose text
must change; or when the user decides to run a revision for the queued items anyway, recorded
as that decision. The design accepts the layer only when all of C1–C8 are met, so if neither
has happened by CR-G, CR-G does not accept the layer with C5 partly met on its own authority:
it asks the user either to accept the layer with C5's live item open under that reopening
condition (a change to the design's acceptance that only the user can make), or to authorize
the revision for the queued items (CR8).

### CR1 — e1000 claim map and status index

- **Outcome:** one checked file shows, for the e1000 campaign, each of the 28 claims'
  qualification and the candidate's result, each `[emulated]` observation EM1–EM8, and every
  open item from AF-1, SR-7, SR-8 and CF-2 with its class, source and disposition. Before: the
  same facts sit in prose tables across about a dozen evidence files. After: `status.yaml` and
  `claims.yaml`, and a checker that CI runs.
- **Covers:** C1 (claims, qualifications, results, observations, items; basis fields; statuses;
  rules), C6's S1–S3 data, C3's tier-0 index check. **Depends on:** nothing.
- **Scope:** the claim map from L02d3, QF-1, FC-1 and CS-1 (claim ID, check names exactly as
  the harness emits them, qualifying defects and run IDs, scope notes, Q18's shortfall); index
  entries of kinds `qualification`, `result` (the candidate `df37c7ad…` on CS-1's harness
  `a1735b9f…`, round `a2`), `observation` and `item`; the index format; the checker.
  **Excluded:** spec verification entries (CR2); the sweep (CR3); any change to the harness or
  to completed evidence files.
- **Steps:**
  1. Write `skills/campaign-review/INDEX-FORMAT.md` (proposed): entry kinds, the basis fields
     C1 lists (spec revision and hash, sections read and declared dependencies, source pins,
     harness hash, emulator and guest identities, candidate module, toolchain, model and
     version, run IDs), `status` with reason and "stale since", `supersedes`, item `class`
     (R/E/W), `source` (1/2/3), `disposition` (`queued`, `applied`, `shortfall` with one of the
     four reasons and a reopening condition, `rejected`), an optional `decision` record (who,
     date, link), an optional `cost`, and a `rule` field naming the scoring or qualification
     rule the verdict was reached under (for readings: A1 as written, or A1 as amended
     2026-09-26), so that M16's rule carries over: verdicts under different rules are not
     compared without saying so. Content limited to IDs, hashes, verdicts, run IDs and links
     (C1's rule).
  2. Write `evals/e1000/claims.yaml` and `evals/e1000/status.yaml` (proposed) from the public
     evidence. Each claim also lists the spec sections its expected outcome cites (`cites`),
     which C2's new-revision row needs. Values that exist only in private ledgers (a full hash where the evidence
     truncates) are filled from the run store and must already be public-safe identities;
     nothing else from the store is copied.
  3. Write `skills/campaign-review/scripts/index_check.py` (proposed): schema, allowed values,
     unique IDs, `supersedes` targets exist and are not themselves current, every claim in the
     map has a qualification entry, every check name in the map exists in `l02harness.py`, every
     evidence link resolves to a file in the repository (home paths stay the job of
     `check-no-private-paths.py`).
  4. Tests in `skills/campaign-review/tests/` (proposed) with good and bad fixtures; add the
     test and check steps to `.github/workflows/checks.yml` and the list in AGENTS.md.
  5. Point the plan's e1000 follow-on status at the index in one line.
- **Accept:** every claim Q01–Q28 is in the map, with its cited sections, and has a
  qualification entry (Q18 a shortfall, `unobservable`, with its reopening condition and a
  `decision` record linking L02f3's user-approved acceptance, which S2 requires for a
  mandatory claim); every open item in AF-1, SR-7, SR-8 and CF-2
  appears once with class, source and disposition (A-RR-1 W, per the orchestrator's decision;
  A-RR-7 carried as the next implementer brief's item; SR-8's item 4 recorded as a records
  finding, not a spec item); the checker passes on the real files and fails on each bad
  fixture; CI runs it.
- **Verify:** `uv run --with pyyaml python3 -m unittest discover -s skills/campaign-review/tests`
  and `uv run --with pyyaml python3 skills/campaign-review/scripts/index_check.py evals/e1000`
  (both proposed interfaces); `python3 utilities/check-no-private-paths.py`; `git diff --check`.
- **Review:** a fresh reviewer traces a declared sample (all items, every fifth claim, every
  shortfall) to the public evidence, and reads the checker's diff. Regressions: the harness's
  check names are the claim map's keys, so a later rename breaks the map; the checker must catch
  that.
- **Sizing:** data entry from bounded, public tables plus one small checker; the unknown is how
  much of the basis is recoverable per entry from public files. **Split point:** the claim map,
  qualifications and results first; observations and items second.
- **Status:** complete, merged as PR #29; [evidence](evidence/CR1.md).

### CR2 — Spec verification history and the SR-8 → CF-2 backfill

- **Outcome:** the index says, for revision 8, which sections' verification is current and on
  which reading it rests, and records the R-item path from CF-1's finding through SR-8 and CF-2
  as linked entries. It confirms or corrects the design's worked example (S4 fails on revision
  8's TNCRS rule).
- **Covers:** C1 (verification entries; the accept criterion as a whole), C5 (the backfilled R
  path). **Depends on:** CR1.
- **Scope:** `verification` entries for every landed revision (3 to 8) from L02b, L02c, L02s,
  AF-1, L02f3, SR-7 and SR-8: by default one entry per reading unit, split per section only
  where a later revision touched part of that unit, so C2 can stale a section without staling a
  whole reading and the entry count stays small enough to trace; each with the sections read,
  the evidence classes its verdicts rest on (C2's `[kernel]` and `[source-observed]` rows need
  them), the dependencies its brief declared (widened to the whole
  revision when none were recorded, as C2 says), the verifier and model, the round, and the
  record's `spec_sha256`. Superseded entries stay. The SR-8 → CF-2 chain: CF-1's finding as an
  R item, SR-8's revision with its requirement-change header, its readings, CF-2's candidate
  round and results, with `applied` and `supersedes` links. **Excluded:** converting legacy
  verification records (they stay legacy, M16's rule); re-reading anything.
- **Steps:** extend the index; extend the checker (a verification entry's `spec_sha256` matches
  its revision's hash; every revision from 3 to 8 is present; a revision header marked
  requirement-changing has a matching item chain); tests.
- **Accept:** C1's criterion: the index and claim map cover every claim, every landed
  revision's verification and every open item, and a reviewer can trace each entry's basis to a
  public evidence file and a run ID without opening private content. The SR-8 → CF-2 path is
  one linked chain. The worked example's S4 statement is confirmed from the entries or
  corrected in the evidence (not in the design) with the reason.
- **Verify:** as CR1, plus the checker on the real files.
- **Review:** a fresh reviewer traces **every** entry (C1 requires each), reading public
  evidence only; the reviewer records any entry it could not trace.
- **Sizing:** six revisions' readings from public evidence; the unknown is how the older
  readings (L02b, L02c) recorded sections. **Split point:** revisions 6–8 first (they decide
  today's status), 3–5 second.
- **Status:** complete, merged as PR #30; [evidence](evidence/CR2.md).

### CR3 — The sweep, tier 0

- **Outcome:** `sweep.py` (proposed, `skills/campaign-review/scripts/`) reads a campaign's index
  and the source registry and prints the stale set with reasons and "stale since". Before: an
  operator rereads evidence to decide what a QEMU upgrade invalidates. After: one command.
- **Covers:** C2 (the whole table and the widening rule), C3 (tier-0 detection), C7 (sources
  identified by ID, version and hash; the sweep never parses a source), C8 (the reference
  source adapter). **Depends on:** CR2.
- **Scope:** the registry format and `evals/e1000/sources.yaml` (proposed): the manual pin, the
  Linux v6.12 files, the QEMU package and binary, the guest kernel and image, the harness files,
  the candidate and reference modules, the landed spec revision, the toolchain; a **pinned-file
  adapter** (proposed `scripts/pinned_file_adapter.py`, reusing or wrapping `corpus_check.py`'s
  pin logic rather than rewriting it) that prints `id`, `version`, `sha256`, `status` and date
  checked for a file named relative to the repository or the run store (C8's output shape,
  content never), and can write those values into the registry; the sweep itself only reads
  the registry; the C2 rules for every row; widening (item → section → document,
  check → scenario → harness); new-revision staleness of qualifications through the claim
  map's `cites`; harness diffs mapped to checks by the claim map's check names,
  widened to all qualifications when a diff cannot be mapped; stale entries excluded from
  acceptance counts. **Excluded:** the stopping rule and the queue (CR4); the manifest and
  the contract check (CR5).
- **Steps:** registry format; adapter; invalidation engine as data-driven rules, one per C2
  row; the sweep's report (text, and `--json`); tests, including a **synthetic change matrix**
  (one change per C2 row against a copy of the e1000 index); a short `SKILL.md` section for the
  orchestrator: run the sweep at the start of each orchestrator session and whenever a known
  input changes (a host package upgrade, a new manual edition).
- **Accept:** C2's criterion: each matrix row marks exactly the listed entries stale; a model
  change marks nothing; a harness diff touching one check stales only that check's claims; an
  unmappable change widens as stated; an input not in the registry (such as an unrecorded
  compiler) cannot trigger anything. Run on the real index with the current registry, the sweep
  reports no stale entry, or each one it reports is explained.
- **Verify:** the unit tests (under `uv run --with pyyaml`); the sweep locally on the real index (needs the run store,
  `python3 utilities/run-store.py`; if unconfigured, ask the user); the privacy check.
- **Review:** one independent reviewer reading the diff, the matrix and the real run's output,
  checking each rule against C2's table cell by cell.
- **Sizing:** one engine with table-driven rules and one adapter; the unknown is mapping harness
  diffs to check names. **Split point:** spec, source and candidate rows first; harness and
  emulator rows second.
- **Status:** complete (PR #31); [evidence](evidence/CR3.md).

### CR4 — Stopping rule and the tier-1 queue

- **Outcome:** the sweep also reports each campaign as **sufficient for scope** or lists
  exactly what blocks it, and emits the tier-1 queue. On e1000 it should report S4 unmet and
  queue one unit: the second independent reading of revision 8's requirement change.
- **Covers:** C6 (S1–S5; the item rules; the three-round cap check; shortfall reasons; a
  person's approval for a shortfall on a mandatory claim), C3 (the queue, the batch cap of
  three, the tier-2 guard), C4 (a change of the reader role queues one comparison reading per
  campaign in scope, sufficient ones included; the role itself comes from CR5's manifest, and
  until then from a constant equal to the reference manifest's value). **Depends on:** CR3.
- **Scope:** the scope declaration per campaign (S1: claims, accepted classes, target) in the
  index; S1–S5 evaluation; item rules (W never queues a revision; E only when it changes a
  claim's status in scope; unknown class treated as R; records findings are not spec items); a
  report of any revision started after 2026-09-26 with more than three rounds (revision 7's six
  readings predate the cap and are recorded as historical); the `rule` guard (entries under
  different rules are reported, not silently compared); the queue: tier-1 units from stale
  entries (re-verification, requalification, acceptance-set rerun) and from unmet S4/S5 (a
  second reading), tier-2 entries listed as `awaiting decision` and never batched unless the
  index holds a `decision` record; a batch of at most three. **Excluded:** running any unit
  (CR6); the manifest, roles and contract check (CR5).
- **Steps:** scope block and evaluation; item rules; queue and batch selection; a one-line
  annotation in [QEMU-DIFFERENTIAL.md](QEMU-DIFFERENTIAL.md)'s A1 row pointing to the design's
  C5 amendment (approved 2026-09-26), as A6's amendment is recorded there; AGENTS.md: the sweep
  at the start of each orchestrator session, and a batch as at most three tier-1 units ending
  in checkpoint commits, pull requests only on "push"; tests.
- **Accept:** C6's first three criterion parts on e1000 — the sweep reports sufficient or lists
  exactly what blocks it; every open item has a class and a disposition; no W item alone queues
  a revision. C3's first criterion part: for each row of CR3's change matrix, one changed
  identity yields the stale entries **and the tier-1 units that cover them** (the expected unit
  kind per row, tested). Tests also show: a tier-2 unit never enters a batch without a recorded
  decision; a fourth queued unit waits for the next batch; a change of reader model queues one
  comparison reading per campaign; an unknown item class is treated as R; entries under
  different rules are flagged, not compared. The e1000 report matches the design's
  worked example, or each difference is explained in the evidence.
- **Verify:** unit tests; the sweep on the real index; the privacy check.
- **Review:** `review-swarm` on the diff (the queue decides what runs unattended, and the tier-2
  guard is an access control), plus the e1000 report as the artifact.
- **Sizing:** rules over data already in the index; the manifest moved to CR5 to keep this
  one session. **Split point:** the stopping rule first; the queue and its guards second.
- **Status:** complete (PR #32). See [evidence](evidence/CR4.md).

### CR5 — Deployment manifest and contract check

- **Outcome:** the deployment manifest names a deployment's plugins and its models by role, and
  `contract_check.py` (proposed) checks a source adapter's JSON and a fixture backend's run
  directory against C8's table. A deployment runs the same command against its own plugins.
- **Covers:** C8, C4 (the role change that queues a comparison reading), C7 (models by role).
  **Depends on:** CR4.
- **Scope:** the manifest schema (`id`, `kind` of `source`, `producer`, `role` or `fixture`,
  `via`, `command` where needed, a producer's `class`) and the public reference manifest
  `evals/deployment.yaml` (proposed) naming only the reference plugins: the pinned-file adapter,
  the QEMU harness as fixture backend and as `[emulated]` producer, and roles `reader`
  (`spec-verifier` in a Claude subagent), `implementer` (`cleanroom-implementer` under Codex)
  and `reviewer`; the queue (CR4) reads each unit's model from the role; the `deployment` key in
  the user config file, beside `run_store`, defaulting to the reference manifest; the
  producer-class rule (in `SPEC-FORMAT.md` or the target spec's own tag table, so `[kernel]`
  passes for e1000); the adapter contract (`id`, `version`, `sha256`, `status`, date,
  provenance: the adapter's name and version, how the version was determined); the backend
  contract (one run directory per isolated run, per-check verdicts PASS, FAIL or ERROR by check
  name, `identities.json` with fixture or emulator identity, harness hash, kernel and image
  hashes); stubs in test fixtures (an adapter returning invented IDs; a backend returning a
  canned run directory; one stub per missing provenance field); a canned QEMU run directory
  reduced from a real `l02harness.py` run (verdicts and identities only) for CI, and the check
  run locally on a live run directory. **Excluded:** mechanical checks for the producer and
  role points (conventions until a first private plugin exists, per C8).
- **Accept:** C8's criterion: the check passes on the reference adapter, the QEMU backend and
  the stubs, and fails on stubs missing each required provenance field; the manifest schema and
  the contract check are the only new interfaces; no plugin other than the reference plugins is
  named in any public file. Changing the reader role's model in a manifest changes the model
  the queue names, with no code change; a producer with an unknown class is rejected.
- **Verify:** unit tests under `uv run --with pyyaml`; the check locally on a live QEMU run
  directory; the privacy check.
- **Review:** one independent reviewer reading the diff and the check's output on the live
  run.
- **Sizing:** one schema and two contracts with fixtures. **Split point:** the manifest and
  roles first; the contract check second.
- **Status:** complete (PR #33). See [evidence](evidence/CR5.md).

### CR6 — The first tier-1 batch

- **Outcome:** a batch of two tier-1 units, taken from the queue and run with no person starting
  each: **CR6a**, the second independent reading of revision 8's requirement change, the first
  tier-1 unit by the orchestrator's decision; and **CR6b**, a comparison reading of the whole
  of revision 8 by a new reading model (C4), queued by changing the reader role in the
  manifest. Afterwards the sweep reports e1000 sufficient for its declared scope, or lists
  what blocks it.
- **Covers:** C3 (the batch), C4, C6 (the e1000 verdict). **Depends on:** CR5. **Needs the
  user:** which model is the new reading model for CR6b (the design names models by role and
  the user selects models). CR6 does not close until two units have run from the queue: without
  the user's choice, the second unit must be one the queue produced legitimately (for example
  after a registry refresh stales an entry); otherwise CR6a checkpoints and CR6 waits for the
  choice.
- **Scope:** CR6a's brief covers every requirement-changing r7 → r8 hunk SR-8 names: §4.7's
  row, §5.5's sample, §5.9 L6 and §10.3's placement, with their dependencies. Each unit follows
  the AF-1 / SR-7 procedure: a fresh `spec-verifier` reader with no sight of earlier records, a
  brief declaring sections and dependencies, the key-by-key join (`review/comparison.md` in the
  run store), adjudication against the cited authority, and no verdict changed before
  adjudication. Each unit's evidence file `evidence/CR6a.md` and `evidence/CR6b.md`; new index
  entries that supersede, never edit, each with its `rule`; cost per unit (minutes, and tokens
  where the harness shows them) in the index. **Excluded:** any spec edit (an R item goes to
  the user as a revision decision, and is CR8's trigger); a candidate round; recall
  re-measurement.
- **Accept:** C3's batch criterion: at least two units ran from the queue to reviewed
  checkpoint commits with no person starting each, cost recorded. C4's criterion: one
  comparison reading by a different model, joined key by key, every disagreement adjudicated
  or listed. C6's: the e1000 campaign reaches sufficient, or its blockers are those in the
  worked example (or new ones this batch found, each with class and disposition).
- **Verify:** the index checker and the sweep after each unit; the leak scan and privacy check
  as for any spec reading.
- **Review:** each unit's adjudication by a fresh reviewer that sees both records and the cited
  passages; `spec-verifier` is the reading itself.
- **Sizing:** CR6a is about one AF-1-sized reading (8.7 minutes in AF-1 for changed sections)
  plus a join; CR6b reads the whole revision and is several times larger; one unit per
  subagent. **Split point:** the batch is already two units.
- **Status:** complete (merged as PR #34). [CR6a](evidence/CR6a.md): revision 8 has two independent lineages;
  its one R item was decided by the user (option b, no driver change) and is CR8's trigger.
  [CR6b](evidence/CR6b.md): the Codex `gpt-6-astra` comparison reading, adjudicated; twelve R
  findings go to the user as one revision decision. C4 met with one deviation: the PASS lines
  were joined at section level, the non-PASS lines key by key (CR6b, Limitations). e1000 is not
  sufficient; its blockers, each
  with class and disposition, are in the evidence and the [status index](evals/e1000/status.yaml).

### CR7 — A stand-in private deployment

- **Outcome:** tests create a temporary deployment (root, run store, registry of invented
  documents, stub plugins only, a manifest reached through the `deployment` key) and run the
  method in it, showing the public repository needs no change to serve a private one.
- **Covers:** C7, C8's stub-only clause. **Depends on:** CR5.
- **Scope:** a generator for the stand-in (in the tests); automated checks of the sweep, C2's
  invalidation, detection of a registry version or hash change with the stand-in sources
  unreadable, and a role change changing the queued model; a scan of the public repository for
  every stand-in ID afterwards; one **live** tier-1 re-verification in a stand-in generated to
  a scratch directory outside the repository: a `spec-verifier` reading of the stand-in's small
  invented spec against its invented sources, queued by the sweep. **Excluded:** anything about
  a real private deployment (the design's non-goal).
- **Accept:** C7's criterion in full: the stand-in runs the sweep, C2's invalidation and one
  tier-1 re-verification; with its sources unreadable to the sweep a registry change is still
  detected; changing the role configuration changes the model the queue names without a code
  change; the public repository contains none of the stand-in IDs. C8's: the stand-in runs
  with stub plugins only.
- **Verify:** unit tests under `uv run --with pyyaml`; the live reading's record in the scratch
  stand-in (its location is not recorded in the repository); the leak scan; the privacy check.
- **Review:** one independent reviewer reading the diff, the test output and the live
  reading's result.
- **Sizing:** test scaffolding over existing commands plus one short reading. **Split point:**
  the automated stand-in first; the live reading second.
- **Status:** complete: automated and live validation pass; independently reviewed, three
  findings fixed.
  The actual reading passed all four facts and the staged post-reading sweep clears
  the queue. The user installed the private update (the orchestrator's harness blocked
  it) and reran the stand-in's sweep: sufficient, empty queue. See
  [evidence](evidence/CR7.md).

### CR8 — One live item through a revision (conditional)

- **Outcome:** one queued W or E item (for example SR-8's item 2, a sentence in §5.5, or
  CF-2's `[emulated]` note on STATUS.FD) goes through the C5 loop: a revision unit on a working
  copy of revision 8, the verification C5 requires for its class, and the index updated at each
  step, old entries superseded.
- **Covers:** C5 (the live item). **Depends on:** CR2, CR4; and **a revision made for another
  reason**, or the user's recorded decision to run one for the queued items (see the coverage
  note above). Until then its status is `pending` with that condition.
- **Scope:** the SR-n pattern: the queued items that ride along, the header's
  requirement-change statement, at most three rounds with fixes after round two only deleting
  or narrowing, then what remains to the user. If the revision changes a requirement, the CF-n
  candidate round is a tier-2 step launched by the user and is not part of CR8.
- **Accept:** C5's second criterion: one live W or E item carried through a revision with the
  index updated at each step; C6's "no W item alone started a revision" still holds, or the
  user's decision that overrode it is recorded.
- **Verify / review:** as SR-7 and SR-8 (`spec-verifier`, the leak scan, the index checker and
  the sweep after landing).
- **Sizing:** an SR-sized unit. **Split point:** the revision and its readings; nothing smaller.
- **Status:** complete, 2026-09-27, merged as PR #36 ([evidence](evidence/CR8.md)). Run on the user's decision
  to make revision 9 for CR6b's R findings; spec revision 9 landed after the three-round cap
  (Codex `gpt-6-astra`), changing requirements on a driver. C5's live-item criterion met. Two R
  items go to the user (the remainder list in the evidence); the second independent reading of
  revision 9 (tier 1) and the CF-n candidate round (tier 2) are next.

### CR-G — Layer acceptance

- **Outcome:** one acceptance table, C1–C8 criteria against evidence, on the e1000 campaign and
  the stand-in deployment, as the design's "Acceptance for the layer" section asks.
- **Checks:** every criterion from its milestone's evidence, rerun where cheap (the index
  checker, the sweep on the real index, the change matrix, the contract check, the stand-in
  tests); cross-milestone interactions: the sweep after CR6's entries still reports the same
  stale set and stopping state; a harness check rename would break the claim map and be
  caught; the queue still names the reference manifest's models when no `deployment` key is
  set. The over-building guard: list every file the layer added and confirm it is the index,
  claim map, registry, manifest schema, sweep, contract check, their tests and docs. C5's live
  item met by CR8, or the user's decision on it (see the coverage note) recorded. The full CI
  list locally (AGENTS.md's final-checkpoint rule).
- **Plan updates:** the deferred table's rows for M03–M04 and M16–M17 and DEFERRED-PLAN's M16
  and D6 already point here (this revision); CR-G records the final state there.
- **Review:** `review-swarm` over the layer's combined diff, plus a fresh reviewer checking the
  acceptance table against the evidence files.
- **Sizing:** verification and one table, no new code. **Status:** complete, 2026-09-27
  ([evidence](evidence/CR-G.md)), subject to the orchestrator's `review-swarm`. C1–C5, C7 and
  C8 are met on their milestones' evidence, five with stated limits. C6's last clause is met
  only in the form CR4's and CR6's criteria give it, extended by CR-G to CR8's blockers (every
  difference from the worked example explained), not literally (e1000 is not yet sufficient);
  the layer's acceptance waits on the user's reading of it. A fresh reviewer checked the table
  (15 findings, all applied). Open: the sweep holds reading units whenever a revision reached
  its round cap, and no decision releases the hold. The cheap checks, the three
  cross-milestone checks and the full CI list pass; one test was added (no deployment key → the
  reference manifest's models). The user's decisions on CR8's two R items (option a each) are
  in the index, for revision 10.

## What is deferred from the immediate path

| Work | Disposition |
| --- | --- |
| Complete source sanitization, related-controller removals and harness isolation (remaining M02) | Preserve the current artifacts and audit findings. Resume only for an explicitly selected spec-only experiment; not required for L01. |
| Generic execution contracts and synthetic replay (M03–M04) | Use a brief, evidence table and ordinary build/test logs for L01. Build shared machinery only after demonstrated need. L02's hand-run loop is that need for the record and invalidation half only, which the [CR milestones](#cr--continuous-review) built without M03/M04 (2026-09-26) and [CR-G](evidence/CR-G.md) found met, subject to the user's reading of C6's last clause (2026-09-27); replay stays here. |
| Frozen spec-only trial and dual blinded attribution (M05/M08) | L01 permits logged outside assistance and repairs; keep these experimental conditions separate. |
| Fixture and meaningful test qualification (parts of M06–M07) | Keep the necessary hardware identity, expected outcomes and negative controls in L01; do not require the generic experimental infrastructure. |
| Paired authoring/implementation and complete documentary scoring (M09–M13, P01) | Optional follow-on to answer comparative questions; no immediate gate. |
| Test-authoring experiments and companion-skill ablation (M14–M15) | Exercise useful existing skills in L01; defer controlled comparisons. |
| Automated maintenance/invalidation and full pilot qualification (M16–M17) | M16a (record and invalidation) and D6 are absorbed into the [CR milestones](#cr--continuous-review) for campaigns with a claim list, and M16b (feedback) partly, through C5 and C7 (2026-09-26); built, and found met on e1000 and the stand-in deployment at [CR-G](evidence/CR-G.md) subject to the user's reading of C6's last clause (2026-09-27). Replay of old attempts with archived tools and M17 stay deferred. |
| L01's Pi fixture harness (`l01hw.py`, only in its private run) as a second public reference fixture backend for C8 | Not needed for C8's criterion, which names the QEMU backend. Publish only after L01 completes, with a privacy pass, the harness defects its review found fixed or recorded, and the CR5 contract check passing on it (2026-09-26). |
| The candidate's two link-check callers (`link_work` and the watchdog) are not serialized against each other beyond the statistics lock; the carrier decision can interleave and leave the carrier stale for up to one 2 s tick after a link flap (CF-2, A-RR-7; pre-existing since L02e; no statistic affected) | Deferred to the next implementer round's brief, whenever one is launched: one serialization for the carrier decision, or one work item for both callers. Not a round on its own. |

The detail behind these rows is in the [deferred plan](DEFERRED-PLAN.md): decisions D1–D6, the
[M01–M17 and P01 dependency table](DEFERRED-PLAN.md#sequence-and-dependencies) and milestone
text, design coverage, the conditional follow-ons, their backlog items, and the historical L01
conventions and input snapshot, all moved there verbatim on 2026-09-25. Deferred means
unfinished, not waived or complete.

**Active blockers:**

- **L01c landing:** independent review remains; the supplied worktree's Git metadata was
  read-only, so its local commits must be imported from the retained checkpoint bundle.
  Fixture work is finished. Two unchanged cleanroom tests fail under this session's
  environment; their diagnoses are recorded in [the evidence](evidence/L01-hw.md).

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
- **Possible upstream report (user decides later; not filed):** the reference driver's probe
  error path warns, [evidence/QF-1.md](evidence/QF-1.md) F1. Recorded on 2026-09-26 at the
  user's request as a pointer for a later decision on reporting it to the Linux maintainers;
  nothing has been filed. Owner: the user; no milestone.
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

- **Continuous review:** [CR1](evidence/CR1.md) is complete (PR #29, the e1000 claim map
  and status index); [CR2](evidence/CR2.md) is complete (PR #30, verification history).
  [CR3](evidence/CR3.md) is complete (PR #31). [CR4](evidence/CR4.md) is complete (PR #32).
  [CR5](evidence/CR5.md) is complete (PR #33). [CR6](evidence/CR6b.md) is complete (PR #34); its R items
  wait for the user's revision decision (CR8). [CR7](evidence/CR7.md) has passed automated
  and live validation, its private update is installed, and it was independently reviewed.
  [CR8](evidence/CR8.md) is complete (PR #36): spec revision 9 applied CR6b's findings.
  [CR-G](evidence/CR-G.md) is complete: the layer's acceptance table; C1–C5, C7 and C8 met,
  and the layer's acceptance waits on the user's reading of C6's last clause. **Next:** revision 10 for CR8's two R items, as the user decided (option (a)
  each: the poll's `napi_complete_done()` and unmask decision under the mask lock; recovery
  through the stack's own close and open under RTNL), with `CR8-W-attestation-kernel` riding
  along; then a second independent reading of the new text (the queue holds it under
  revision 9's round cap, so a person launches it or the hold rule is fixed first); then the
  candidate round (CF-n), which the user launches.
- **e1000 follow-on verdicts and item dispositions:** see the [status index](evals/e1000/status.yaml) and [claim map](evals/e1000/claims.yaml).
- **L01 complete for its declared hardware scope** (L01c, 2026-09-26): see
  [evidence/L01-hw.md](evidence/L01-hw.md). The candidate passes the ten revised checks on the
  Pi 4 fixture with no repair; the reference's C6 failure is attributed to the switch's
  forwarding delay. Further hardware runs need a named question and a fresh declaration.
- Transcripts: record each subagent's transcript path in the run's ledger; do not copy them
  (user rule, 2026-09-23).
