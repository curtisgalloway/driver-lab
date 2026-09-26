<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# CF-1: the candidate on spec revision 6

## Terms

- **Candidate** — `e1000_l02`, the driver written from spec revision 4 (L02e), repaired once
  (L02f2) and, in this unit, updated to revision 6. **Reference** — Linux v6.12's `e1000`.
- **Round** — one bounded implementer pass in the audited clean-room sandbox
  (`cleanroom-implementer`, "Tier 1 on Linux"), as in L02f2: a brief carrying only spec text,
  manual text and permitted observations; an strace log audited by `sandbox_audit.py`.
- **Acceptance set** — L02f3's run set: all ten suite scenarios, isolated (one scenario per
  fresh boot), reference ×2 and candidate ×2, 40 runs. **Isolated run**, **claim**,
  **qualified** — as in the [L02d3 evidence](L02d3.md#terms).
- **L01 review trio** — the three independent reviews L01 and L02e gave a candidate: a
  reference review (candidate against the reference driver, each difference decided from the
  manual), a requirements review (candidate against the blind list, without the reference) and
  `review-swarm` on the diff ([L01](L01.md), [L02e](L02e.md)).

See the [glossary](../GLOSSARY.md), the [design](../QEMU-DIFFERENTIAL.md), the
[plan](../IMPLEMENTATION-PLAN.md) (CF-1), the [L02f3 evidence](L02f3.md) (the definition
of this follow-on) and the [notebook chapter](../notebook/CF-1.md).

## Status

**Complete, 2026-09-26.** The candidate now implements spec revision 6: one audited clean-room
round changed the two behaviors the revision-4-to-6 diff requires of this driver (FWE written
01b on the EECD write; TNCRS reported only in full duplex) and nothing else, with the other
revision-6 changes confirmed already met. On the QF-1 harness the reference and the updated
candidate each passed all ten scenarios in isolated runs, twice (40 runs, 928 checks, 0
failed), declared before the first run; every register-level difference from L02f3's
candidate traces is the FWE value, the added STATUS read, or run-to-run variation. The L01
review trio found no bug: one low implementation weakness that is a spec gap (TNCRS across a
duplex change), one stale header comment, and three places where the reference departs from
the manual or the kernel's own definition. Both L02 decisions restate as met for the updated
candidate. Private run `e1000-cf1-20260925-01`.

## Frozen before execution (2026-09-26, 07:59 Pacific)

Private run `e1000-cf1-20260925-01`.

| Artifact | Identity |
| --- | --- |
| Spec | Revision 6, `f78ea07a…45b2` (L02f3's landed copy); the revision-4-to-6 diff given to the implementer `96743b65…` (16 hunks, 228 lines) |
| Candidate before | `e1000_l02.c` `dfb0aa0c…` (L02f2 round 1; module `366782e4…`, the one L02f3 and QF-1 ran) |
| Candidate after (round 1) | `e1000_l02.c` `a8afc8c4…`, module `e1000_l02.ko` `ce7e3e2c…`, built with gcc-14 against the pinned v6.12 tree, 0 warnings at default and W=1, module defaults |
| Harness | `l02harness.py` `7024864e…`, `guest-init.sh` `eccecebe…` (QF-1's final harness, the checkout at `77e754d`) |
| Reference module | `e1000.ko` `43242751…` (as every unit since L02d2) |
| Kernel, QEMU, busybox | `bzImage` `0d96151b…`; 10.2.1+ds-1ubuntu3.2, `qemu-system-x86_64` `0cd4112a…`, KVM, DUT memory 3 GiB; `df12634c…` |
| Run script and job list | `run1.sh` `3c90950a…`, `jobs-a1.txt` `a847819e…` (L02f3's list, 40 lines) |

**Run declaration (round `a1`).** All ten suite scenarios, isolated, for the reference and
for the round-1 candidate, two repetitions each: 40 runs, eight in parallel, reference and
candidate interleaved, on the QF-1 harness. Pass criteria: reference 20 of 20 PASS (A4);
candidate 20 of 20 PASS on every check, the `trace` and `capture` pseudo-scenarios and the
kernel-log check included. Every failure is kept, attributed and reported; no run is repeated
to replace a result; a reference failure the manual does not explain blocks judging the
affected candidate behavior. Past probe, the candidate's register traces are compared with
L02f3's candidate traces scenario by scenario: the EECD write value (FWE now written 01b) and
one STATUS read before each TNCRS read are the expected differences; any other difference is
attributed to the candidate, the spec, the model or the harness before the unit closes. The
declaration is in the run's ledger and here, committed before the first run.

## Round 1: the update and its checks

One round, no repair needed. The implementer (Codex, `gpt-6-astra`, in `cleanroom_sandbox.sh`,
launched by the user after the agent's own launch was refused twice by its safety check) read
the spec, the revision-4-to-6 diff, the manual, the candidate and one kernel header
(`iopoll.h`), and nothing else: the canary pilot's audit found the expected read, and the
round's audit lists those five workspace reads, no successful read outside the allowed roots
(12 failed probes, all the agent's own housekeeping paths), and endpoints of the model API's
CDN and the local resolver only. Both audits were re-run in this unit with the repository's
`sandbox_audit.py` (`a4876214…`, the same file as the run's copy) and gave byte-identical PASS
reports. Codex ran 07:49:51 to 07:52:30 (395,315 input tokens, 4,214 output).

**Scope.** The revision-4-to-6 diff has 16 hunks; the implementer's `UPDATE-NOTES.md` gives
each a disposition, checked here against the code:

| Hunks | Disposition | Checked |
| --- | --- | --- |
| §4.1 FWE row; §5.3 E1 (the FWE clause) | **changed**: the candidate's one EECD write (`l02_eeprom_read_mac`, E1's release write) now clears EE_REQ, forces bits 5:4 to 01b and keeps every other bit as read | The file has one `EECD` write; the mask arithmetic gives 01b for every value bits 5:4 can read back |
| §4.7 TNCRS row | **changed**: the statistics poll (`l02_update_hw_stats`, under `stats_lock`) reads STATUS then TNCRS, always clearing TNCRS, and adds it to the accumulator only when STATUS.FD is set; `tx_carrier_errors` and `tx_errors` take the accumulator | As described |
| §4.7 RLEC, RUC, ROC rows | already compliant: `rx_length_errors` = RUC + ROC, RLEC accumulated but not reported | Confirmed; the comment there still calls the overlap a spec gap (wording, left) |
| §5.2 R6 margin | already compliant: `usleep_range(10, 20)` after the RST write, before the CTRL poll | Confirmed |
| §5.3 E1 policy; E5 third choice | already compliant: 5 µs poll, 10 ms bound, `-EBUSY` when EE_REQ stays set, one warning then EERD when only EE_GNT stays set, no run-time direct access; E5 keeps the random-address choice (the third choice is optional) | Confirmed |
| §5.4 G4, ordering note, PHY extras; §9.2 | already compliant: PSCON read-modify-write sets bits 6:5 and 11 and clears bit 1 before the ANA, GCON and PCTRL writes | Confirmed |
| Header; §1 tag table; §4.1 EERD pointer; §12.1 G-12; §12.3; §12.5–12.6 | not driver behavior | The `[emulated]` entries were not used to change anything; GCON, TCTL.COLD, CT and TIPG unchanged |

The diff is those two changes plus two defines (46 lines); nothing else in the file changed.
One gap filed: how to attribute TNCRS counts that span a duplex change between two reads
(§4.7 and the manual's §13.4.2 and §13.7.12 do not say); the implementer samples STATUS.FD
immediately before the read. Recorded for the next spec revision, not repaired.

**Build.** gcc-14 against the pinned v6.12 tree: 0 warnings at default and at W=1; source
`a8afc8c4…`, module `ce7e3e2c…`.

**Leak scan.** The round-1 source and its diff, scanned against the seven reference driver
files at the pinned commit with the L02c whitelist: 0 shared token runs in either; the
identifiers listed are kernel API names, `rtnl_link_stats64` field names and names the
candidate already had (the diff's two hits are context lines present before the round).

## Run results (round `a1`)

All 40 runs in `e1000-cf1-20260925-01`, 08:00:15 to 08:01:35 Pacific, KVM, eight at a time;
every run's `identities.json` matches the frozen table (checked by `summary.py`). The
declaration commit ([`122b04a`](https://github.com/curtisgalloway/driver-lab/commit/122b04a),
07:59:04) precedes the first run. No run was repeated or discarded.

| Scenario | Reference (×2) | Candidate (×2) | Checks per run | Claims |
| --- | --- | --- | --- | --- |
| `smoke` | PASS, PASS | PASS, PASS | 21 (with `capture`) | Q01–Q03, Q17, Q24, Q26 |
| `frame-sizes` | PASS, PASS | PASS, PASS | 25 | Q04–Q06, Q25 |
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

928 checks, 0 failed; the kernel-log check passed in every run. Every candidate probe logs
`EEPROM grant still set after release (EECD=0x00000198); trying EERD` (L02f3: `0x00000188`)
and binds with the right MAC and a good checksum; the driver's other kernel-log lines are
unchanged. The candidate's smallest reset gap per run was 5 to 17 µs (180 resets, memory BAR);
the reference's 5.84 to 6.06 ms (I/O window). No reference failure needs explaining (A4).

**Claims.** Q01–Q17 and Q19–Q26 PASS for the updated candidate in both repetitions, on the
harness on which L02d3, L02f2b and QF-1 qualified them, so 25 of 26 claims are qualified
evidence about the updated candidate on the emulated device within their stated scopes; Q18
passes as an observation (`unobservable`, [QF-1](QF-1.md)).

## Attribution of the differences from L02f3

Each candidate run's decoded register trace was compared with L02f3's run of the same
scenario and repetition (the L02f2-round-1 module), register by register within each guest
command: written values, write counts and read counts (`analysis/compare-cf1.py` and
`aggregate.py` in the run store; the two L02f3 repetitions of each scenario served as the
control for run-to-run variation).

| Difference | Attribution |
| --- | --- |
| The EECD write is `0x198` in every CF-1 probe (24, three per `reload` run), `0x188` in L02f3's | The FWE change (§4.1): bits 5:4 written 01b; expected |
| STATUS is read more often: in every run by exactly the number of statistics polls (3 to 23 per run; the poll count is the TNCRS reads minus the init-time sweeps that clear the whole block without reading STATUS); TNCRS read counts identical in every pair | The TNCRS change (§4.7): one STATUS read before each poll's TNCRS read; expected. In 18 of 20 runs the STATUS read is immediately followed by the TNCRS read in every poll; in `itr-1` one poll has an ICR read and in `ring-wrap-1` one has an RDT write stamped between them, another CPU's interrupt handler or NAPI poll running during the statistics poll (whose lock is local); `benign`, candidate concurrency, not a missing read |
| Ring base addresses; ring index values and ICR, IMC, IMS, RDT, TDT counts; MTA and RCTL write counts; EECD read counts at probe; IMC and IMS writes recorded one phase earlier or later around `set_link down` | Allocation, traffic and open/close cadence, and phase boundaries: the same variation the control pairs show between two L02f3 runs of one module; `benign`, not the candidate change |

No written value differs other than EECD and the allocation- and traffic-dependent ones above;
no register is written or read by only one build.

## Review: the L01 review trio

Three independent, fresh-context, read-only reviewers (same model family as the operator;
reports in the run store under `review/`), as L01 and L02e applied to the candidate:

| Review | Method | Result |
| --- | --- | --- |
| A: reference review | The two changed behaviors and the six "already compliant" claims against the Linux v6.12 `e1000` at the pinned commit, each difference decided from the manual; the reviewer read the reference (evaluator side) and its report was leak-scanned (0 shared token runs; it names reference functions as locations, and stays private) | 7 findings, **no `[bug]`**: 3 `[ref-issue]`, 4 `[benign]`; all six compliance claims confirmed; no regression (the full before/after diff is the update diff) |
| B: requirements review | Every active row of the [blind list](../evals/e1000/requirements.yaml) against the updated source, without the reference; the change's rows re-read, the rest confirmed untouched by the diff | 66 active rows: critical 60 of 60 implemented; important 5 implemented, 1 not applicable (PHY-004, link state from STATUS.LU, the row's own alternative, unchanged since L02e); 0 partial, missing or contradicting; no row constrains FWE or TNCRS by duplex (list gaps noted) |
| C: `review-swarm` | Seven arms and a referee on the round-1 diff, in a review checkout holding the candidate before and after, the spec and an instruction file naming the spec as the rule set (the candidate is not in this repository) | All 7 arms delivered (security 0, correctness 1, compat 2, docs 1, history 0, conventions 0, perf 0); checker 4 verified, 0 dropped; referee kept 2 (both low), dropped 2 as restating the change's intent |

**Fallback recorded.** L01's reviewer A used `reference-driver-review`'s anchored form with
its checkers; here, as in L02e, the reference review is a scoped brief (the changed behaviors
and the compliance claims) with manual citations, because the change is 46 lines and the
candidate lives outside any git repository the anchor checker could pin. The swarm's `history`
and `conventions` arms had a two-commit checkout and one instruction file to read; both
returned empty lists, which is the evidence that they looked.

### Findings and resolutions

| ID | Sev | Finding | Resolution |
| --- | --- | --- | --- |
| A-F1 | low, `[ref-issue]` | The reference writes EECD's FWE field back as read on every EECD write, so a disallowed value read back (EM2: 00b) is written back; the candidate writes 01b | None: the candidate follows §4.1 (Table 13-6 allows 01b and 10b only); a reference observation, not a candidate defect |
| A-F3 | low, `[ref-issue]` | The reference accumulates and reports TNCRS at every duplex; the candidate only in full duplex | None: §4.7 and §13.7.12 ("only valid … at full duplex"); the manual contradicts itself (G-12) |
| A-F4 | low, `[ref-issue]` | The reference leaves TNCRS out of `tx_errors`, while the kernel's `include/uapi/linux/if_link.h` says `tx_errors` includes `tx_carrier_errors`; the candidate includes it | None for the candidate. A reference-driver observation, not reported upstream in this unit (open item for the user, as QF-1's F1) |
| A-F5 / C-F1 | low (`[benign]` in A; correctness, low, in C) | Counts drained from TNCRS are attributed to the duplex read at drain time, so up to one watchdog period (2 s) of counts per duplex change goes to the wrong duplex; nothing drains the counter when the link changes. The implementer filed the same question as a spec gap | **Spec gap, recorded for the next spec revision**, not repaired: §4.7 and the manual's §13.4.2 and §13.7.12 give no attribution rule, so a fix is a design choice the spec has to make. Both reviewers propose the same rule (drain TNCRS at every link-status change under the statistics lock, crediting the duplex in force since the previous drain, and not gating on link-up). Bounded to one interval per link event, and unobservable on the model, whose link is always 1000 Mb/s full duplex |
| A-F7 | info, `[benign]` | E5's third choice (use a valid EEPROM address on a checksum failure) is not taken | None: optional in E5; the candidate's random-address choice is one of the permitted two |
| A-F2, A-F6 | info, `[benign]` | The reference has no EERD path for this part (it bit-bangs; E1 has no reference analog) and never polls RST after its reset; the candidate follows E1 and R6 | None |
| C-F4 | low, docs, outside the diff | The file header still says the driver was written from spec revision 4 | **Open**: a comment-only change to the implementer's file, to go in the next implementer round's brief rather than an operator edit; not made here because the source identity the acceptance set ran (`a8afc8c4…`) would change |
| C-F2, C-F3 | dropped by the referee | `tx_carrier_errors` now excludes half-duplex counts; FWE forced to 01b even if 10b was read | Both are the change's intent (§4.7, §4.1) |
| B: PHY-004 | info | Not applicable: the driver reads link state from STATUS.LU, never PHY register 1's latched-low bit | Unchanged since L02e; the row offers that alternative |

No finding changed a verdict, an identity or a qualification, and no reviewer asked for broader
review. Reviewer A also recorded the agreements between the two drivers on the changed code
(EE_GNT written back as read in the release write, the MAC byte order, the checksum, STATUS.FD
as the duplex source, RUC + ROC, the PSCON bits and their order before AN, the reset sequence).

## The two decisions, restated for the updated candidate

**Evaluation complete: met.** Every scenario result for the updated candidate is recorded (20
runs, all PASS); the one implementer-filed gap and the reviewers' findings are recorded with
their causes (spec gap; reference observations; a stale comment) and none needed a repair;
the register-level differences from the accepted candidate are attributed. L02f3's shortfalls
stand where this unit did not touch them (Q18 unqualified; d16 and d11 under A6; the L02e
session audit met by judgment; hardware-only behaviors; one QEMU version, one host, KVM only).

**Candidate qualified for the declared scope: met for the 25 qualified claims, not beyond.**
The scope is the 25 claims qualified in L02d3 (with Q15 in L02f2b) and QF-1, each within its
stated scope, on the emulated 82540EM with the identities frozen above. The updated candidate
passes every one in isolated runs, twice, on the harness those qualifications ran on; no
blocking finding is open; no mandatory claim in the scope is unresolved. Q18 passes as an
observation only (`unobservable`); nothing about hardware behavior is claimed, and the two
behaviors this unit changed (FWE, TNCRS by duplex) are exercised by no scenario: the model
reads FWE = 00b and never runs half duplex, so they rest on the spec's rules and the reviews,
not on a differential result.

## Open items for the user

| Item | Recommendation |
| --- | --- |
| The copied Codex credential in the run's agent home | Delete it: no further round is needed (recorded in the ledger once done) |
| TNCRS attribution across a duplex change (A-F5 / C-F1, the implementer's gap) | Add a rule to §4.7 in the next spec revision (SR-7's successor): drain TNCRS at every link-status change and credit the duplex in force since the previous drain; then implement it in the next candidate round |
| The file header's "revision 4" (C-F4) | Fold into the next implementer round's brief; no round for a comment |
| The reference's `tx_errors` omitting TNCRS (A-F4) | A reference-driver observation, like QF-1's F1; report upstream or not, the user's call |

## Measures

- Operator time: about 07:55 to 08:25 on 2026-09-26 (Pacific), one session, after the user's
  round-1 launch at 07:49; see the notebook. Model cost not measured; the implementer's round
  was 395,315 input and 4,214 output tokens.
- Host time: round `a1` (40 runs, 8 at a time) 80 seconds; reviews about 7 minutes in parallel.
- Human review effort: none during the unit, beyond launching round 1.

## Limitations

- The two changed behaviors are not exercised by any scenario on the model (FWE reads 00b
  and the write's effect is invisible; the emulated link never runs half duplex), so their
  correctness rests on the spec's rules and the three reviews, not on a differential result.
- The reviewers, the referee and the operator share a model family; the implementer does not.
  No human read the candidate or the runs in this unit.
- The reference review is scoped to the change and the compliance claims, not the whole
  driver (L02e's covered the whole driver); the requirements review re-read the changed rows
  and carried the rest from the unchanged code.
- Two repetitions per scenario, one host, one QEMU version, KVM only, eight runs at a time,
  as L02f3 and QF-1.
- Subagent transcripts are recorded by path in the run's ledger; those paths are temporary.
