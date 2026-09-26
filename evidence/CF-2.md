<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# CF-2: the candidate on spec revision 8

## Terms

- **Candidate** — `e1000_l02`, the driver written from spec revision 4 (L02e), repaired once
  (L02f2), updated to revision 6 ([CF-1](CF-1.md)) and, in this unit, to revision 8.
  **Reference** — Linux v6.12's `e1000`.
- **The rule** — revision 8's TNCRS attribution rule ([SR-8](SR-8.md)): the clear-on-read
  TNCRS counter is read at the periodic statistics poll and at every link-status change, each
  reading's count is credited to the duplex sampled at the previous reading (reported if that
  was full duplex, discarded otherwise), and the record starts at the clearing read (§4.7,
  §5.5, §5.9 L6).
- **Reading** (of the counter) — one read of TNCRS, which clears it; the count covers the
  interval since the previous reading. **Sample** — the STATUS.FD value kept from a reading
  for crediting the next one.
- **Round**, **acceptance set**, **L01 review trio**, **isolated run**, **claim**,
  **qualified** — as in [CF-1](CF-1.md#terms).

See the [glossary](../GLOSSARY.md), the [design](../QEMU-DIFFERENTIAL.md), the
[plan](../IMPLEMENTATION-PLAN.md) (CF-2), the [SR-8 evidence](SR-8.md) (the rule), the
[CF-1 evidence](CF-1.md) (the pattern and the comparison baseline) and the
[notebook chapter](../notebook/CF-2.md).

## Status

**Complete, 2026-09-26.** The candidate now implements spec revision 8: one audited clean-room
round (Codex, launched by the user) added the TNCRS attribution rule in its four places (one
sample under the statistics lock, seeded at the clearing read; every reading credited by the
previous sample; the link check drains under the lock) and the header's revision number, and
nothing else; the other 17 spec hunks were already met or are not driver behavior. On the FC-1
harness the reference and the updated candidate each passed all ten scenarios in isolated runs,
twice (40 runs, 944 checks, 0 failed), declared before the first run; every register-level
difference from CF-1's candidate traces is one of the three the rule predicts, or cadence and
run-to-run variation. The L01 review trio found no bug: seven benign or reference-side
findings, all decided below, none needing a repair. The rule itself cannot be exercised on the
model, whose link never changes duplex; its hardware check is on HF-1's list. Both L02 decisions
restate as met for the updated candidate. Private run `e1000-cf2-20260926-01`.

## Frozen before execution (2026-09-26, 12:37 Pacific)

Private run `e1000-cf2-20260926-01`.

| Artifact | Identity |
| --- | --- |
| Spec | Revision 8, `e0f17ffa…6326d7` (SR-8's landed copy); the revision-6-to-8 diff given to the implementer `038d97e5…` (21 hunks, 270 lines) |
| Candidate before | `e1000_l02.c` `a8afc8c4…` (CF-1 round 1; module `ce7e3e2c…`, the one CF-1 and FC-1 ran) |
| Candidate after (round 1) | `e1000_l02.c` `2ac15713…`, module `e1000_l02.ko` `df37c7ad…`, built with gcc-14 against the pinned v6.12 tree, 0 warnings at default and W=1, module defaults |
| Harness | `l02harness.py` `884e771c…`, `guest-init.sh` `eccecebe…` (FC-1's final harness; the checkout at `ad247be`, origin/main) |
| Reference module | `e1000.ko` `43242751…` (as every unit since L02d2) |
| Kernel, QEMU, busybox | `bzImage` `0d96151b…`; 10.2.1+ds-1ubuntu3.2, `qemu-system-x86_64` `0cd4112a…`, KVM, DUT memory 3 GiB; `df12634c…` |
| Run script and job list | `run1.sh` `281dae8d…`, `jobs-a1.txt` `a847819e…` (CF-1's and L02f3's list, 40 lines) |

**Run declaration (round `a1`).** All ten suite scenarios, isolated, for the reference and
for the round-1 candidate, two repetitions each: 40 runs, eight in parallel, reference and
candidate interleaved, on the FC-1 harness. Pass criteria: reference 20 of 20 PASS (A4);
candidate 20 of 20 PASS on every check, the `trace` and `capture` pseudo-scenarios and the
kernel-log check included. Every failure is kept, attributed and reported; no run is repeated
to replace a result; a reference failure the manual does not explain blocks judging the
affected candidate behavior. Past probe, the candidate's register traces are compared with
CF-1's candidate traces scenario by scenario, CF-1's two repetitions serving as the control
for run-to-run variation. Three differences are expected from the change: TNCRS is read more
often, by the number of link checks per run (each link check now drains the counter); STATUS
is read once more per clearing sweep (the §5.5 sample); and within each statistics poll the
TNCRS read now precedes the STATUS read. Any other difference is attributed to the candidate,
the spec, the model or the harness before the unit closes. The kernel-log lines are expected
to be identical to CF-1's. The rule itself cannot be observed on the model, whose link is
1000 Mb/s full duplex and never changes duplex: every sample is full duplex and every reading
is credited, so the traces can show where the readings happen, not whether the crediting is
right. The declaration is in the run's ledger and here, committed before the first run.

## Round 1: the update and its checks

One round, no repair needed. The implementer (Codex, `gpt-6-astra`, in `cleanroom_sandbox.sh`,
launched by the user, as in CF-1) read the spec, the revision-6-to-8 diff and the candidate,
and nothing else (it did not open the manual, which the brief reserves for where the spec is
silent): the canary pilot's audit found the expected read, and the round's audit counts four
workspace reads (the workspace directory and the three files in `CONSULTED.md`, listed with
`--json`), no successful read outside the allowed roots (12 failed probes, the agent's own
housekeeping paths), and endpoints of the model API's CDN and the local resolver only. Both
audits were re-run in this unit with the repository's `sandbox_audit.py` (`a4876214…`, the
same file as the run's copy) and gave byte-identical PASS reports. Codex ran 10:32:11 to
10:34:11 (274,588 input tokens, 217,216 of them cached, 3,356 output).

**Scope.** The revision-6-to-8 diff has 21 hunks; the implementer's `UPDATE-NOTES.md` gives
each a disposition, checked here against the diff and the code:

| Hunks | Disposition | Checked |
| --- | --- | --- |
| §4.7 TNCRS row; §5.5; §5.9 L6 and its order paragraph; §10.3 link task and periodic accumulator | **changed**: one sample (`tncrs_full_duplex`, under `stats_lock`) seeded by a STATUS read right after the clearing sweep's TNCRS read; one helper `l02_update_tncrs()` (asserts the lock) that reads TNCRS, adds it to the accumulator only if the sample was full duplex, then reads STATUS, stores FD and returns it; the periodic poll calls it in place of its STATUS-then-TNCRS pair; `l02_link_check()` takes the lock, drains through it and uses the returned STATUS as L1's read, before the carrier reporting, whether the link is up or down | As described; the four hunks are one rule seen from four places |
| Header | **changed**: "revision 4" becomes "revision 8", nothing else in the comment | Confirmed (CF-1's C-F4) |
| §4.1 FWE punctuation; §4.7 clearing by reads; §4.8 PSCON row; §5.1 no wait before the clearing read; §5.2 R6 wording and R7's hardware test; §5.3 E1/E5 wording; §9.2; §10.3 BAR type | already compliant | Confirmed: one EECD write with FWE 01b; `l02_clear_hw_stats()` at open before RX/TX; PSCON bit 11 before the AN restart; the 10 µs margin and the 5 ms allowance; the bounded polls and their policies; the BAR type read from the configuration dword at probe |
| Header list; §1 tag table; §5.4 PHY extras (register 20); §12.1 G-12/G-16; §12.2; §12.3; §12.5 intro, EM7, EM8; §12.6 | not driver behavior | Nothing in them asks for code; the `[emulated]` entries were not used |

The diff is five hunks, 36 changed lines (+27, −9; 1590 to 1608 lines); nothing
else in the file changed, `tx_carrier_errors` and `tx_errors` included. `spec-gaps.md` is
empty. CF-1's stale "RLEC overlaps these (spec gap)" comment is still there (wording, outside
the brief's scope).

**The double drain.** `l02_link_check()` runs from the LSC work item and from every 2 s
watchdog tick, right after the periodic poll, so each tick takes two readings and the counter
is drained more often than §4.7 names. Judged permitted, not a deviation: the row names the
readings that must happen and does not say "only", and its rule is stated per reading (credit
by the sample kept at the previous reading, then re-sample), so an extra reading splits an
interval into two credited by the same sample unless a link change fell between them, in which
case the extra reading is the one L6 requires at that change; no count is credited to a
different duplex than the minimal set of readings would give it, and the residual the row
states (counts between the hardware's change and the driver's reading) can only shrink. The
implementer says the same in its notes; the cost is one TNCRS and one STATUS read per tick.
The reference review was asked to weigh it (below).

**Build.** gcc-14 against the pinned v6.12 tree: 0 warnings at default and at W=1; source
`2ac15713…`, module `df37c7ad…`.

**Leak scan.** The round-1 source and its diff, scanned against the seven reference driver
files at the pinned commit with the L02c whitelist: 0 shared token runs in either; the
identifiers listed are kernel API names (`spin_lock_irqsave`, `netif_carrier_ok`, `test_bit`,
`ARRAY_SIZE`, …) and names the candidate already had (`stats_lock`, since L02e).

## Run results (round `a1`)

All 40 runs in `e1000-cf2-20260926-01`, launched 12:38:07, first scenario 12:38:09, last
scenario end 12:39:26 Pacific, KVM, eight at a time; every run's `identities.json` matches the
frozen table (checked by `summary.py`). The declaration commit
([`a283279`](https://github.com/curtisgalloway/driver-lab/commit/a283279), 12:37:24) precedes
the launch. No run was repeated or discarded.

| Scenario | Reference (×2) | Candidate (×2) | Checks per run | Claims |
| --- | --- | --- | --- | --- |
| `smoke` | PASS, PASS | PASS, PASS | 21 (with `capture`) | Q01–Q03, Q17, Q24, Q26 |
| `frame-sizes` | PASS, PASS | PASS, PASS | 29 | Q04–Q06, Q25, Q27 |
| `ring-wrap` | PASS, PASS | PASS, PASS | 22 | Q07–Q09 |
| `rx-overrun` | PASS, PASS | PASS, PASS | 24 | Q10 |
| `link-flap` | PASS, PASS | PASS, PASS | 21 | Q11–Q13 |
| `link-loss-tx` | PASS, PASS | PASS, PASS | 23 | Q11–Q13 |
| `stop-start` | PASS, PASS | PASS, PASS | 18 | Q14, Q02 |
| `down-during-traffic` | PASS, PASS | PASS, PASS | 25 | Q15 |
| `reload` | PASS, PASS | PASS, PASS | 34 | Q16 |
| `itr` | PASS, PASS | PASS, PASS | 19 | Q23 |
| `trace` (pseudo-scenario) | PASS in all 20 | PASS in all 20 | | Q18 (unqualified), Q19–Q23 |
| `capture` (pseudo-scenario) | PASS, PASS | PASS, PASS | | not a claim |

944 checks (CF-1's 928 plus FC-1's four `frame-sizes` checks in each of its four runs), 0
failed; the kernel-log check passed in every run. Every candidate probe logs
`EEPROM grant still set after release (EECD=0x00000198); trying EERD` and binds with the right
MAC and a good checksum; the driver's kernel-log lines are identical to CF-1's in the eight runs
compared (`smoke`, `reload`, `link-flap`, `stop-start`, both repetitions). The candidate's
smallest reset gap per run was 4 to 8 µs (180 resets through the memory BAR, all 4 to 21 µs);
the reference's about 5.9 ms (I/O window). No reference failure needs explaining (A4).

**Claims.** Q01–Q17 and Q19–Q27 PASS for the updated candidate in both repetitions, on the
harness on which FC-1 qualified Q27 and reran every earlier qualification's scenario, so 26 of
27 claims are qualified evidence about the updated candidate on the emulated device within
their stated scopes; Q18 passes as an observation (`unobservable`, [QF-1](QF-1.md)).

## Attribution of the differences from CF-1

Each candidate run's decoded register trace was compared with CF-1's run of the same scenario
and repetition (the CF-1 round-1 module), register by register within each guest command
(`analysis/compare-cf2.py`, CF-1's script, and `aggregate-cf2.py` in the run store; CF-1's two
repetitions of each scenario served as the control for run-to-run variation, on file as
`analysis/control-pairs-cf1.txt`). `aggregate-cf2.py` also classifies every TNCRS read in a
CF-2 trace by the register read just before it (DC: the clearing sweep; COLC: the periodic
poll; anything else: a link check) and tests the three declared expectations. The comparison
crosses a harness revision (CF-1's runs on `7024864e…`, these on `884e771c…`, FC-1's
`frame-sizes` content checks); per run the set of registers touched is identical between the
builds.

| Difference | Attribution |
| --- | --- |
| TNCRS is read more often: in every run each read is a sweep's, a poll's (the watchdog's, or `l02_stop`'s final reading, one per close) or a link check's, and the link checks number the polls less the closes (the watchdog ticks) plus the ICR reads with the LSC bit set (the forced LSC of each open plus the scenario's link changes): `smoke` 3 − 1 + 2 = 4; `link-flap` 6 − 1 + 4 = 9; `link-loss-tx` 10 − 1 + 4 = 13; `reload` 6 − 3 + 6 = 9; `stop-start` 23 − 21 + 23 = 25; `frame-sizes-1` 6 − 1 + 2 = 7. In 19 of 20 runs the sweep and poll counts equal the CF-1 twin's exactly, so the surplus is exactly the link checks | The rule's L6 (each link check drains); expected |
| STATUS is read once more per clearing sweep in the same 19 runs (`smoke` 14 vs 13; `reload` 36 vs 33; `stop-start` 135 vs 114, 21 sweeps) | The §5.5 sample; expected |
| Within every sweep and every poll, in all 20 runs, the TNCRS read is immediately followed by the STATUS read, except one poll in `link-loss-tx-1` with a TDT write from another CPU between them (11 µs); so is every link check's but 26 in 12 runs, one per affected open: the first link check of an open (the forced LSC's link work) has its STATUS read 3 to 16 accesses later with MTA writes, and once the RCTL write, stamped between, the stack's own `set_rx_mode` (under `netif_addr_lock`) running on another CPU while the link work holds `stats_lock` | Expected order; the interleaving is candidate concurrency, the class CF-1 recorded for ICR and RDT; `benign`, the read is present |
| `frame-sizes-1` has one more watchdog tick than its CF-1 twin (6 polls and 7 link checks against 5 and 6; CF-2's own `frame-sizes-2` has 5 and 6), so every statistics register's run total is one read higher there | Poll cadence: the scenario now runs 10.40 to 10.43 s on the FC-1 harness (10.27 s in CF-1), on the 2 s tick boundary, so the sixth poll lands or not by run; `benign`, the harness revision, not the candidate |
| Ring base addresses; ring index values and ICR, IMC, IMS, RDT, TDT counts; MTA and RCTL write counts; EECD read counts at probe; statistics reads landing in a different guest command; IMS and IMC writes recorded in a neighboring phase (52 phase-level entries, 32 of them `frame-sizes` phases whose names changed with FC-1's pattern pings, so the same writes sit under a different phase key; whole-run IMS/IMC totals lie in or beside the spread of CF-1's two repetitions, with the same two values `0xd5` and `0xffffffff` in every run of both builds) | Allocation, traffic and open/close cadence, phase boundaries and the harness revision's phase names: the variation the control pairs show between two CF-1 runs of one module; `benign`, not the candidate change |

No written value differs other than the allocation- and traffic-dependent ones above; no
register is written or read by only one build; the EECD write is `0x198` in every probe of
both builds. What the traces cannot show is whether the crediting is right: the model's link
is always 1000 Mb/s full duplex (STATUS.FD = 1 and SPEED = 1000 Mb/s at every link check:
`0x80080783` with the link up, `0x80080781` with it down), so every sample is full duplex and
every reading is credited, and TNCRS read 0 at every reading in every run. One thing they do
show, an `[emulated]` observation for the next spec revision and not a requirement: on the
model STATUS.FD reads 1 while LU = 0 (the 80 link checks taken before the link is up or after
it went down), so the first interval's sample (A-RR-5) is full duplex here. The
traces show that the readings happen where the spec puts them (the sweep with its sample, the
poll, every link change) and that they are taken under the statistics lock's serialization
(no statistics read is ever interleaved with another statistics read); the rule's crediting
rests on the reviews and on the hardware check listed for HF-1.

## Review: the L01 review trio

Three independent, fresh-context, read-only reviewers (same model family as the operator;
reports in the run store under `review/`), as L01, L02e and CF-1 applied to the candidate:

| Review | Method | Result |
| --- | --- | --- |
| A: reference review | The rule, reading by reading (the clearing read's sample, the helper's credit-then-sample order, the link check's one STATUS read serving L1 and L6, the lock discipline, the lifecycle across open, stop and reload), the watchdog's double drain, and the "already compliant" claims, each difference from the Linux v6.12 `e1000` decided from the manual; the reviewer read the reference (evaluator side) and its report was leak-scanned and stays private | 7 findings, **no `[bug]`**: 5 `[benign]`, 2 `[ref-issue]`; every compliance claim confirmed; no regression (the full before/after diff is the update diff); the double drain judged permitted, neither a deviation nor a spec gap |
| B: requirements review | Every active row of the [blind list](../evals/e1000/requirements.yaml) against the updated source, without the reference; the statistics, link-handling and locking rows re-read, the rest confirmed untouched by the diff | 66 active rows: critical 60 of 60 implemented; important 5 implemented, 1 not applicable (PHY-004, link state from STATUS.LU, the row's own alternative, unchanged since L02e); 0 partial, missing or contradicting; no row constrains when TNCRS is read, its crediting, the kept sample or the lock (six list gaps noted) |
| C: `review-swarm` | Seven arms and a referee on the round-1 diff, in a review checkout holding the candidate before and after, spec revision 8 with its diff from revision 6, and an instruction file naming the spec and the rule as the rule set | All 7 arms delivered with **0 findings each** (security, correctness, compat, docs, history, conventions, perf); checker 0 verified, 0 dropped; referee 0 examined, 0 kept |

**Fallback recorded.** As in CF-1, the reference review is a scoped brief with manual citations
rather than `reference-driver-review`'s anchored form: the change is 36 lines and the candidate
lives outside any git repository the anchor checker could pin. The swarm's `history` and
`conventions` arms had a two-commit checkout and one instruction file to read; both returned
empty lists, which is the evidence that they looked.

### Findings and decisions

Per the orchestrator's process update of 2026-09-26 (12:44), each finding carries a decision
made by the unit implementer in the user's place, for the user to confirm or change; nothing
here is left as an open question, except that A-RR-4's upstream report is reserved for the
user as an outward action, by the process's own rule.

| ID | Sev | Finding | Decision |
| --- | --- | --- | --- |
| A-RR-1 | info, `[benign]` | The watchdog takes two readings per tick (the poll's, then the link check's) where §4.7 names one. An extra reading splits an interval into two, each credited by the sample at its start: identical credit when the duplex is unchanged, a smaller misattributed span when a change fell in the latency window. The rule forbids skipping a reading, not adding one | **Permitted; defer the wording**: no driver change. §4.7 could say the counter is read "at least" at the poll and at every change; recorded for the next spec revision below |
| A-RR-2 | low, `[benign]` | The reference takes no statistics reading while its link is down, so a lost link's counts land in the next link's first reading; the candidate reads at every link check and credits by the previous sample. The manual is silent (§13.7.12 ties incrementing to transmits being enabled, not to the link) | **Reject as a candidate change**: the spec's rule governs where the manual is silent, and the candidate follows it. The reviewer's hardware probe (transmit at full duplex, drop the link, return at half duplex, compare the totals per interval) is a variant of §4.7's own method, on HF-1's list in the plan |
| A-RR-3, A-RR-4 | info, `[ref-issue]` | The reference reports TNCRS at every duplex, and leaves it out of `tx_errors` where the kernel's `if_link.h` says `tx_errors` includes `tx_carrier_errors`; the candidate follows §13.7.12 and the kernel's definition | **None** for the candidate (CF-1's A-F3 and A-F4 again). Whether to report A-RR-4 upstream is an outward action and stays with the user, as CF-1 recorded |
| A-RR-5 | info, `[benign]` | The first sample is taken at the clearing read with the link normally down, and Table 13-5 gives FD an initial value of X with no rule for no link, so the first interval is credited by an unspecified duplex. Nothing can be counted in it: TCTL.EN is set after the clearing read, the carrier is off until the first link check, and the forced LSC at open ends it within one work-item latency | **Defer**: already SR-8's next-revision item 2 (a sentence in §5.5). The reviewer's hardware note (read STATUS.FD right after G7 with no link and record it) is on HF-1's list in the plan |
| A-RR-6 | info, `[benign]` | Between stop's D2 and its final reading the link check takes no reading; D3 disables transmits before the final reading and the reset comes after it, so no count is lost or double-counted, and the misattribution is within the residual §4.7 accepts. Re-seeding at every open restarts the record where §5.5 says it starts | **None** |
| A-RR-7 | low, `[benign]`, pre-existing | `l02_link_work` and `l02_watchdog` both call `l02_link_check()` and are not serialized against each other beyond the statistics lock. The drain and the sample are atomic under the lock, so no count is lost or credited to the wrong sample whichever order the readings take; only the carrier decision outside the lock can interleave, and two checks that see different LU values around a transition can leave the carrier opposite to the link, or log "link up" twice, until the next 2 s tick. Not introduced by this round; the reference handles link state from one work item. Reviewer B lists the same as a list gap | **Defer to the next implementer round's brief**: a driver change (one serialization for the carrier decision, or one work item for both callers) outside this round's scope; no statistic is affected and the carrier self-heals at the next tick. No round for it alone; recorded in the plan's deferred-work table so the next brief inherits it |
| B: PHY-004 | info | Not applicable: the driver reads link state from STATUS.LU, never PHY register 1's latched-low bit | **None**: unchanged since L02e; the row offers that alternative |
| B: list gaps | info | The blind list has no row for TNCRS's full-duplex-only validity, for counting only with TCTL.EN, for what STATUS.FD reads with LU = 0, for the duplex changing only with a link change, for the read-in-one-place lock rule, or for the two link-check callers' serialization | **Recorded, not added**: the list is the recall baseline measured on revision 3 (L02c) and is not amended after the fact; the rule's requirements live in the spec, which the reviews judged the code against |

No finding changed a verdict, an identity or a qualification, and no reviewer asked for
broader review. Reviewer A also recorded the agreements between the two drivers on the changed
code (duplex from STATUS bit 0 and speed from bits 7:6; the counters cleared by reading before
RX/TX are enabled; a 2 s accumulator under a spinlock with interrupts off; TNCRS reported as
`tx_carrier_errors`; duplex re-evaluated only at link events; no TNCRS read from the interrupt
handler or the NAPI poll).

**For the next spec revision (none applied here):** §4.7's TNCRS row could say "at least" at
the poll and at every change (A-RR-1); an `[emulated]` entry that the model's STATUS.FD reads 1
with LU = 0 (AR-10, below); beside SR-8's four listed items.

## The two decisions, restated for the updated candidate

**Evaluation complete: met.** Every scenario result for the updated candidate is recorded (20
runs, all PASS); every review finding is recorded with its cause (a permitted extra reading;
reference observations; a spec-wording item; a pre-existing carrier-reporting race) and a
decision, and none needed a repair; the register-level differences from CF-1's candidate are
attributed. L02f3's shortfalls stand where this unit did not touch them (Q18 unqualified; d16
and d11 under A6; the L02e session audit met by judgment; hardware-only behaviors; one QEMU
version, one host, KVM only).

**Candidate qualified for the declared scope: met for the 26 qualified claims, not beyond.**
The scope is the 26 claims qualified in L02d3 (with Q15 in L02f2b), QF-1 and FC-1, each within
its stated scope, on the emulated 82540EM with the identities frozen above. The updated
candidate passes every one in isolated runs, twice, on the harness those qualifications ran on
or were rerun on (FC-1); no blocking finding is open; no mandatory claim in the scope is
unresolved. Q18 passes as an observation only (`unobservable`); nothing about hardware behavior
is claimed, and the behavior this unit changed (which duplex a TNCRS reading is credited to)
is exercised by no scenario: the model's link never changes duplex, so it rests on the spec's
rule and the reviews, not on a differential result.

## Measures

- Operator time: about 12:32 to the final checkpoint on 2026-09-26 (Pacific), one session
  after a pause for a quota reset; the user's round-1 launch was at 10:32; see the notebook.
  Model cost not measured; the implementer's round was 274,588 input (217,216 cached) and
  3,356 output tokens.
- Host time: round `a1` (40 runs, 8 at a time) 79 seconds; the reviews about 7 minutes in
  parallel.
- Human review effort: none during the unit, beyond launching round 1.

## Limitations

- The changed behavior is not exercised by any scenario on the model (the emulated link is
  always 1000 Mb/s full duplex and never changes duplex, and TNCRS read 0 at every reading),
  so the crediting rests on the spec's argument and the three reviews; the traces show only
  that the readings happen where the spec puts them and under the lock.
- The reviewers, the referee and the operator share a model family; the implementer does not.
  No human read the candidate or the runs in this unit.
- The reference review is scoped to the change and the compliance claims, not the whole
  driver; the requirements review re-read the changed rows and carried the rest from the
  unchanged code.
- The comparison baseline crosses a harness revision (CF-1's `7024864e…` to FC-1's
  `884e771c…`), which changed one scenario's phase names and duration; one cadence difference
  is attributed to it.
- Two repetitions per scenario, one host, one QEMU version, KVM only, eight runs at a time,
  as CF-1.
- Subagent transcripts are recorded by path in the run's ledger; those paths are temporary.

### Review of this file

One fresh, read-only artifact reviewer (same model family; report in the run store under
`review/`) read this file, the ledger, the round-1 outputs, all 40 runs' verdicts, identities,
kernel logs and traces, CF-1's 20 candidate traces, the three review reports and the scans, and
recomputed every verdict, check count and identity hash, the declaration's timing, the reset
gaps, the EECD writes, the three expected trace differences and their exceptions (with its own
trace script, written before it read `aggregate-cf2.py`), the review counts, every decision
against its report and the scope table's dispositions. Nothing recomputed disagreed with a
verdict, an identity, an attribution or either decision; its ten findings are two records the
decisions pointed at but the plan did not yet hold, and figure and wording corrections, all
applied:

| ID | Sev | Finding | Resolution |
| --- | --- | --- | --- |
| R1 | medium | Two decisions said items were "added to HF-1's list" (A-RR-5's note, A-RR-2's probe) but the plan's HF-1 entry did not hold them | Both added to HF-1's entry in the plan; the cells now point at it |
| R2 | low | "STATUS `0x80080781` at every link check" is the link-down value (103 of 183 link checks read `0x80080783`); the notebook glossed it as "link up" | Restated as FD = 1 and SPEED = 1000 at every link check, both values given; the notebook corrected |
| R3 | low | The late STATUS read after an open's first link check is 26 reads in 12 runs (one per affected open; 5 and 11 in the two `stop-start` runs), 3 to 16 accesses later, not "one per run" and "1 to 6"; `aggregate-cf2.py` looked only two accesses ahead | Corrected; the script now looks 40 accesses ahead, reads and writes, and its rerun gives the reviewer's figures |
| R4 | low | One poll (`link-loss-tx-1`) has a TDT write between its TNCRS and STATUS reads, invisible to a reads-only check | Said; same benign class |
| R5 | low | The link-check identity as printed did not add up: a "poll" includes stop's final reading (one per close) and the forced LSC is one per open | Restated as polls − closes + LSC-flagged ICR reads, with the figures per scenario |
| R6 | low | 32 of the 52 phase-level IMS/IMC entries are `frame-sizes` phases, not 36 | Corrected here and in the ledger |
| R7 | low | A-RR-7's deferral to "the next implementer round's brief" had no durable home; no unit is queued | A row in the plan's deferred-work table |
| R8 | info | "34 lines" survived in the Fallback paragraph after the diff count was corrected to 36 | Corrected |
| R9 | info | "nothing here is left as an open question" while A-RR-4's upstream report is reserved for the user | Said in the sentence |
| R10 | info | The traces do show STATUS.FD = 1 while LU = 0 on the model (80 link checks), which answers A-RR-5 and B's list gap 3 for the model | Recorded as an `[emulated]` observation for the next spec revision |

The reviewer confirmed both decisions as stated and judged broader review unnecessary.
