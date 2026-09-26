<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# QF-1: the four unqualified claims (Q18, Q24, Q25, Q26)

## Terms

- **Claim**, **qualified**, **unqualified**, **unobservable**, **insensitive**, **planted
  defect**, **isolated run** — as in the [L02d3 evidence](L02d3.md#terms). **Candidate** —
  `e1000_l02` as built in L02f2's round 1 (the module L02f3 accepted); **reference** —
  Linux v6.12's `e1000`.
- **Equivalent mutation** — a planted defect the suite cannot tell from the reference
  under its stimulus (design A6); reported as a control, not a detection.
- **Trace stamp** — the host time QEMU writes on each traced register access, in whole
  microseconds. QEMU stamps a write before the device model executes it and a read after
  (`system/memory.c`, read in the v10.2.0 source; the binary is 10.2.1); the difference
  between two stamps therefore bounds the guest's interval between the accesses from above.
- **Reset gap** — the difference between the stamp of a `CTRL.RST` write and the stamp of
  the next register access, the quantity the harness's reset rule judges (Q18).
- **Copybreak path** — the reference's receive path for frames of at most 256 bytes,
  which copies the frame into a small buffer; d21, d21b and d21c are planted in it.

See the [glossary](../GLOSSARY.md), the [design](../QEMU-DIFFERENTIAL.md) (§7, A6), the
[plan](../IMPLEMENTATION-PLAN.md) (QF-1) and the [notebook chapter](../notebook/QF-1.md).

## Status

**Complete, 2026-09-26.** Q24, Q25 and Q26 are qualified by planted defects in isolated
runs, three of three each, for the intended reason, with the reference passing the same
scenarios on the same harness; the candidate passes all three, so they move from
observations to qualified evidence. Q18 stays unqualified: the harness's reset rule was
restated as what the trace can observe (stamps at least 2 µs apart), and a defect that
resets through the memory BAR with no wait at all was still stamped 6 µs or more before
its next access in all 24 resets, so the rule was not shown able to fail on this host and
model (`unobservable`, with the reason below). The harness change is one constant with
tests; the whole acceptance set (ten scenarios, reference ×2 and candidate ×2) passed on
it, 40 of 40, and the new rule reproduces every stored L02f3 trace verdict offline.
Private run `qf1-20260926-01`: 69 isolated runs in two declared rounds, none repeated or
discarded; one independent review of the diff and the run artifacts (below).

## Frozen before execution (2026-09-26, 00:26 Pacific)

Private run `qf1-20260926-01`. The candidate does not change in this unit.

| Artifact | Identity |
| --- | --- |
| Harness | `l02harness.py` `7024864e…` (this unit's change, below), `guest-init.sh` `eccecebe…` (unchanged); the previous harness was `705694b9…` |
| Reference module | `e1000.ko` `43242751…` |
| Candidate module | `e1000_l02.ko` `366782e4…` (L02f2 round 1) |
| Kernel, QEMU, busybox | `0d96151b…`; 10.2.1+ds-1ubuntu3.2, `0cd4112a…`, KVM, DUT memory 3 GiB; `df12634c…` |
| Defects (modules) | d17 `007a1903…`, d18 `8fe39520…`, d19 `feaf2687…`, d20 `c368b636…`, d21 `6d7ff491…`, d22 `f19fba29…`; built out of tree against the same kernel with no warnings |
| Run script and job list | `run1.sh` `2ac79a3d…`, `jobs-q1.txt` `7285a263…` (63 lines). The script was edited in place for round `q2` (two module cases added, `c1569765…`), so the `q1` text survives only as its hash (review R6) |

**The harness change.** The trace stamps each access to the microsecond, so two stamps
1 µs apart can be any interval under 2 µs; in the 40 L02f3 traces, consecutive memory-BAR
writes are stamped 0 µs apart in every run (hundreds of pairs per run), and a write
followed by a read is stamped 0 or 1 µs apart in 38 of the 40 runs (2,827 of 255,188
pairs; the typical difference is 5 to 8 µs; review R1). So the instrument resolves below
its stamp. The old reset rule failed only on a difference under 1 µs,
so it passed intervals it could not show to be 1 µs. The rule now fails on a difference
under 2 µs (`RESET_GAP_STAMPS_US`), the smallest difference that shows an interval of at
least 1 µs; the check's name is unchanged and its detail says so. Tests: 0 and 1 µs fail,
2 and 3 pass; the I/O-window path is judged the same way. Nothing else in the harness
changed.

**Run declaration (round `q1`, 63 isolated runs, eight in parallel).**

- The acceptance set on the changed harness: all ten suite scenarios, reference ×2 and
  candidate ×2 (40 runs, as L02f3's). Criterion: reference 20 of 20 PASS, candidate 20 of
  20 PASS on every check. The change touches the trace pseudo-scenario, which runs in
  every scenario, so every earlier qualification's scenario is rerun for both drivers.
- d17 (module init fails), `smoke` ×3: expected "insmod" FAIL in 3 of 3; the scenario
  stops; the capture pseudo-scenario also fails for lack of any access (a consequence).
- d18 (probe rejects the 82540EM), `smoke` ×3: expected "insmod" PASS, "bound to a PCI
  device" FAIL in 3 of 3; the MAC, interface-up and carrier checks fail as consequences;
  the cleanup unload passes; the kernel log's "probe … failed" line is not flagged.
- d19 (`ndo_open` returns `-EBUSY`), `smoke` ×3: expected insmod, bind and MAC PASS,
  "interface up" FAIL in 3 of 3, carrier FAIL as a consequence, no pings; cleanup unload
  passes; kernel log clean.
- d20 (probe takes a module reference it never drops), `smoke` ×3: expected every check
  through the pings PASS, "rmmod" FAIL in 3 of 3 (module in use), the cleanup unload FAIL
  as a consequence; kernel log clean.
- d21 (the small-frame receive path delivers each frame one byte short), `frame-sizes`
  ×3: expected bring-up and the 42-byte ping PASS (its reply arrives padded to 60 bytes
  and survives one byte short), the four 60- and 61-byte ping checks FAIL in 3 of 3 (the
  frame arrives one byte shorter than its IP total length and IP drops it), 1513 and 1514
  PASS (above the copybreak size), the sent-sizes capture check FAIL on the missing 60-
  and 61-byte replies (a consequence), runts PASS, rmmod PASS, kernel log clean.
- d22 (global reset through the memory BAR with no wait after it), `smoke` ×8: expected
  every smoke check PASS; the reset rule FAIL in at least 1 of 8 runs, most likely most,
  with gaps of 0 or 1 µs; the gaps recorded per run, and the old rule's verdict
  recomputed from them. If no run shows a gap under 2 µs, Q18 stays unqualified.
- Every failure is kept, attributed and reported; no run is repeated to replace a result.
  A reference or candidate failure blocks the corresponding conclusion.

The declaration is in the run's ledger and here; this section was committed
([`9442e08`](https://github.com/curtisgalloway/driver-lab/commit/9442e08), 00:27:30)
before the first run (00:27:35).

**Round `q2` (declared 00:34, after `q1`'s results, before any `q2` run;
[`ae1298e`](https://github.com/curtisgalloway/driver-lab/commit/ae1298e) at 00:34:30; the
round's launcher started in the same second and its first scenario at 00:34:33).** d21 was not specific: QEMU's model does not pad short frames, so the
peer's 42-byte ARP frames reach the driver at 42 bytes and one byte short kills ARP and
every ping (results below). Two replacement defects, `frame-sizes` ×3 each, modules
`de9ecabf…` (d21b) and `5ff074ae…` (d21c), `jobs-q2.txt` `0b0d2abf…`, `run1.sh`
`c1569765…`:

- d21b (the small-frame path drops frames longer than the 46 bytes, header plus 32, it
  was written for): expected the 42-byte ping PASS, the four 60/61-byte ping checks FAIL
  in 3 of 3, 1513/1514 PASS, the sent-sizes check FAIL on the missing 60/61-byte replies
  only, everything else PASS.
- d21c (the small-frame copy's second part starts one byte too far, so frames longer than
  46 bytes arrive with their tail shifted): expected "peer pings DUT with 60/61-byte
  frames" FAIL in 3 of 3 (the DUT's ICMP checksum rejects the request); "DUT pings peer
  with 60/61-byte frames" PASS if `ping` accepts a reply with a bad ICMP checksum (a
  finding about that half of the check: arrival, not integrity) and FAIL if it verifies;
  42, 1513 and 1514 PASS; the sent-sizes check FAIL on the 60/61-byte replies.

## Results

All 69 runs (`q1` 00:27:35 to 00:29:37, `q2` 00:34:30 to 00:34:54 Pacific), KVM, every
run's `identities.json` recording the frozen hashes (checked by `summary.py` in the run
store). "Run" names the run directory in `qf1-20260926-01`.

**Controls on the changed harness.** Reference 20 of 20 PASS and candidate 20 of 20 PASS
across the ten scenarios ×2, every check (`q1-ref-*`, `q1-cand-*`); the `smoke` and
`frame-sizes` runs among them are the controls for the defects below. The candidate's
reset gaps on the new rule: smallest 5 to 8 µs per run (180 resets, each through the
memory BAR and followed by a CTRL read); the reference's 5.84 to 6.08 ms (114 resets, each
through the I/O window and followed by a MANC read).
Offline, the changed `trace_rules` over the 40 stored L02f3 traces (`analysis/recompute.py`
in the run store) reproduces every stored trace verdict and every stored gap list: 40
unchanged, 0 changed. So the L02d3 qualifications of Q19–Q23, carried to `705694b9…` in
L02f3, carry to `7024864e…` too: the diff touches the reset rule's threshold and detail
only, and the other five rules' verdicts are byte-identical on the same traces.

| Defect | Runs | Declared failing checks | Result |
| --- | --- | --- | --- |
| d17 module init returns an error | `q1-d17-smoke-1..3` | "insmod"; the capture pseudo-scenario as a consequence | **as declared, 3 of 3**: `insmod: can't insert … Input/output error`; no e1000 register access at all (129 PCI configuration accesses, 79 reads and 50 writes), so the three capture checks fail; kernel log clean |
| d18 probe rejects the 82540EM | `q1-d18-smoke-1..3` | "bound to a PCI device"; MAC, interface up, carrier as consequences | **as declared, 3 of 3**, plus one undeclared failure: the kernel-log check, on a `WARNING … iounmap` with a call trace from `e1000_probe` (finding F1 below); the cleanup unload passed; no register write and no EEPROM access, so two capture checks fail. The declared "probe … failed with error -19" log line did not appear: the driver core logs `-ENODEV` at debug level only (review R5) |
| d19 `ndo_open` returns `-EBUSY` | `q1-d19-smoke-1..3` | "interface up"; carrier as a consequence | **as declared, 3 of 3**: `SIOCSIFFLAGS: Device or resource busy`; carrier unreadable (`Invalid argument`); insmod, bind and MAC passed; no pings ran; cleanup unload and kernel log passed; trace and capture passed (probe's reset and EEPROM accesses happen) |
| d20 probe leaks a module reference | `q1-d20-smoke-1..3` | "rmmod"; the cleanup unload as a consequence | **as declared, 3 of 3**: every check through both pings passed, then `rmmod: can't unload module 'e1000': Resource temporarily unavailable`, twice; kernel log clean |
| d21 small frames one byte short | `q1-d21-frame-sizes-1..3` | the four 60/61-byte pings; sent-sizes as a consequence | **not as declared**: every ping check failed (42, 60, 61, 1513, 1514, both ways) and the sent-sizes check on all eight; bring-up, runts, rmmod and the kernel log passed. The model does not pad short frames (F2), so ARP died with the one byte. Violates Q25 but not specifically; kept as an attempt, not used to qualify |
| d21b small frames over 46 bytes dropped | `q2-d21b-frame-sizes-1..3` | the four 60/61-byte pings; sent-sizes on the 60/61 replies | **as declared, 3 of 3**: exactly "DUT pings peer with 60-byte frames", "… 61-byte frames", "peer pings DUT with 60-byte frames", "… 61-byte frames" (100 % loss each) and the sent-sizes check missing `(0, 60), (0, 61)` only; the 42-, 1513- and 1514-byte pings, the runt check, bring-up, rmmod and the kernel log passed |
| d21c small-frame tail shifted by one byte | `q2-d21c-frame-sizes-1..3` | "peer pings DUT with 60/61-byte frames"; the DUT's own 60/61 pings either way | **PASS, 3 of 3, every check**: an equivalent mutation under this stimulus (F3). The peer's capture shows every 60/61-byte reply carrying its request's payload unchanged: the shift starts at frame byte 46, the payload is a 4-byte timestamp at bytes 42–45 followed by zeros, and the byte pulled in from beyond the frame (the first of the FCS bytes the model leaves unwritten) was zero in these buffers, so the equivalence is contingent on buffer contents, not structural |
| d22 memory-BAR reset, no wait | `q1-d22-smoke-1..8` | the reset rule, in at least 1 of 8 | **the declared alternative**: every check passed in 8 of 8; reset gaps 6 to 17 µs over all 24 resets (smallest per run 6, 6, 6, 6, 6, 6, 6, 6); the old rule, recomputed from the recorded gaps, passes too. The "most likely most" expectation rested on a misreading of the stored traces (that write-then-read pairs are typically 1 µs apart; they are typically 5 to 8, review R1), which is part of why the alternative applied |

## Qualification

For each qualified row, the reference passed the same scenario on the same harness twice
(`q1-ref-smoke-1..2`, `q1-ref-frame-sizes-1..2`), and the failing check is the claim's
own; the notes say what else failed alongside it and why that is a consequence.

| Claim | Result | Defect → runs | What failed, and why it is the claim's failure |
| --- | --- | --- | --- |
| Q18 1 µs after reset | **unqualified: `unobservable` on this host and model** | d22 → `q1-d22-smoke-1..8` | The rule was restated as what the trace can observe (stamps at least 2 µs apart, since a difference of 1 µs can be any interval under 2 µs) and the acceptance set passed on it. A driver that resets through the memory BAR and does nothing at all before its next access (a MANC read) was still stamped 6 µs or more after the reset in all 24 resets; the candidate's 180 resets in this unit's acceptance set (each followed by a CTRL read) were stamped 5 µs or more, and its 180 in L02f3's 4 µs or more; L02d3's d11 through the I/O window 13 to 34 µs. In the same traces, ordinary write-then-read pairs are stamped from 1 µs apart (EECD then STATUS: minimum 1 µs, median 6 to 8), so a write followed by a read is not always 6 µs; QEMU's `set_ctrl` (v10.2.0) only clears the bit, so the model's reset work is not the cause either. What makes a `CTRL.RST` write's next access come 4 µs or more later was not determined. Whatever a driver does, no trace here showed a reset followed within 2 µs, so neither form of the rule was shown able to fail; the observation (the gaps) still distinguishes a driver that waits for the auto-read (the reference, about 6 ms) from one that does not (d22, the candidate) |
| Q24 the interface comes up without error | **qualified** | d19 → `q1-d19-smoke-1..3` | "interface up" failed on `ndo_open`'s error while insmod, bind and MAC passed; carrier failed as a consequence of the interface staying down; the cleanup unload passed, so the module was otherwise sound |
| Q24 the module unloads without error | **qualified** | d20 → `q1-d20-smoke-1..3` | "rmmod" failed on the leaked reference after every other smoke check, both pings included, had passed; the cleanup unload's failure is the same defect seen again |
| Q25 60/61-byte receive | **qualified** | d21b → `q2-d21b-frame-sizes-1..3` | exactly the four 60/61-byte ping checks, each way, while the 42-, 1513- and 1514-byte pings passed (so ARP, the small-frame path below 47 bytes and the large-frame path all worked); the sent-sizes check missed only the 60/61-byte replies the DUT never received requests for. d21 (not specific) and d21c (equivalent under this stimulus, F3) are reported as attempts |
| Q26 the module loads | **qualified** | d17 → `q1-d17-smoke-1..3` | "insmod" failed on the init error; the scenario stopped before binding, and the capture checks failed because no register was ever touched, which is the same defect seen from the trace |
| Q26 the module binds to the device | **qualified** | d18 → `q1-d18-smoke-1..3` | "bound to a PCI device" failed (no device under the driver) while "insmod" passed; the MAC, interface-up and carrier checks failed because there was no `eth0`; the cleanup unload passed. The kernel-log failure is the reference's own error path (F1), a second symptom of the same probe failure, not a second cause |

**Candidate results.** On the changed harness the candidate passes `smoke` and
`frame-sizes` twice each (`q1-cand-smoke-1..2`, `q1-cand-frame-sizes-1..2`), so its first
load and bind (Q26), its interface-up and unload (Q24) and its 60/61-byte reception (Q25)
are now qualified evidence within the scopes above, in addition to L02f3's 20 of 20 on
the previous harness. Q18 remains an observation: the candidate's smallest reset gap was
4 µs (L02f3) and 5 µs (here), against the reference's 5.84 to 6.08 ms here.

**Coverage after this unit.** 25 of 26 claims qualified (L02d3: 22, with Q15 in L02f2b;
here: Q24, Q25, Q26), each with its stated scope; Q18 unqualified, `unobservable`.

## Acceptance (against the brief)

| Criterion | Result |
| --- | --- |
| Q24, Q25, Q26: a defect planted for each, repetitions and expected outcome declared before the run, isolated runs, failure for the intended reason | Met: d19 and d20 (Q24), d21b (Q25), d17 and d18 (Q26), 3 of 3 each, on the declared checks; declarations committed at `9442e08` and `ae1298e` before their rounds |
| Q18: a timing approach that can show the check able to fail, or a recorded reason | The check restated as what the trace can observe (stamps ≥ 2 µs) and shown still unable to fail on this host and model by a no-wait defect (d22, 24 resets, smallest 6 µs); recorded as `unobservable` with the measurements and the undetermined mechanism |
| A check unable to fail is strengthened with harness tests, requalified, and the reference and candidate confirmed on the declared repetitions | The reset rule strengthened (one constant; tests for 0/1 fail, 2/3 pass, I/O window); reference 20 of 20 and candidate 20 of 20 on the changed harness; requalification of Q18 not achieved (above) |
| Any harness change: tests for the changed surface, affected scenarios rerun for both drivers, earlier qualifications kept valid | 44 harness tests pass; all ten scenarios rerun ×2 for both drivers; the other five trace rules' verdicts reproduced byte-identically on the 40 stored L02f3 traces |
| Every failure kept and attributed; no run repeated to replace a result | 69 runs, all kept: d21 (not specific), d21c (equivalent) and d22 (the declared alternative) reported as such |

## Findings

| ID | Sev | Finding | Resolution |
| --- | --- | --- | --- |
| F1 | medium | **The reference's probe error path warns.** When `e1000_probe` fails after `e1000_init_hw_struct` (d18 makes it fail there, as a real `init_hw_struct` error would), the `err_sw_init` label falls through `err_mdio_ioremap`, which unmaps the CE4100 MDIO base this part never mapped, and the kernel logs `WARNING: … at arch/x86/mm/ioremap.c:461 iounmap` with a call trace (`q1-d18-smoke-1..3`, `dut-dmesg-01-smoke.txt`). A reference-driver defect in v6.12's error handling, not a harness or check defect; the kernel-log check did its job | Recorded; the d18 row counts the log failure as a second symptom. Not reported upstream in this unit (open item for the user) |
| F2 | medium | **QEMU's model delivers short frames at their wire length.** The peer's 42-byte ARP and echo frames reach the driver at 42 bytes (46 with the CRC field), where the 82540EM would have discarded a runt or, from a real link, received a 60-byte frame; `e1000_receive_iov` (v10.2.0) uses its minimum-size buffer only to complete a short header for filtering (v10.2.0 source; the binary is 10.2.1). This is why d21's one byte short killed ARP, and it means a driver that assumes the minimum frame size on receive can misbehave on the model and not on hardware | Recorded as a model departure for the next spec revision's `[emulated]` table (CF-1's revision, with the run IDs `q1-d21-frame-sizes-1..3` and the capture counts); d21 replaced by d21b |
| F3 | low | **Small-frame payload integrity is not checked.** d21c shifts every small frame's content from byte 46 on and passes `frame-sizes` 3 of 3: the ping payloads are a 4-byte timestamp followed by zeros, so the shift changes nothing the stack or `ping` looks at. Q09 (4 MiB over HTTP, MD5) covers large frames only; no check exercises small-frame content | Recorded under Limitations; a follow-on could add a small-frame content check (a pattern payload or a short HTTP transfer). Not done here: it is a new check, outside this unit's scope |
| F4 | low | **The reset write's extra time is unexplained.** A `CTRL.RST` write is never followed within 4 µs by the next access on this host and model, while other write-then-read pairs are stamped 1 µs apart; the model's `set_ctrl` does no reset work. The cause (in QEMU's dispatch, KVM or the guest) was not determined | Recorded in the Q18 row; the `unobservable` label rests on the measurements, not on a mechanism |
| F5 | low | **d21's declaration rested on a wrong premise** (that the model pads short frames to 60 bytes, as the 82540EM's link would). The premise came from memory of QEMU's source, not from the run store; L02d3's reviewer had already recorded that ARP frames reach the DUT at 42 bytes, and the notebook's 00:24 entry wrongly attributes the padding premise to that reviewer | The round was kept and reported; round `q2` declared from the captures and the model's source; the notebook is append-only, so this row closes the attribution |

## Review

One independent fresh-context reviewer (same model family) read the diff (`9b8c3b7..` this
branch), the run store (ledger, both rounds' verdicts, identities, kernel logs, traces,
captures, the defect diffs and build logs, the analysis scripts) and this file, with the
brief to recompute what it could and to ask for `review-swarm` if it judged the change
broader than one rule. Its report is in the run store under `review/`. It recomputed every
verdict and failed-check list (69 runs), every reset gap (the harness's observation agrees
in all 69), every identity against the frozen table (69 of 69), the declaration commits'
order against the runs' start times, the offline recompute over the 40 L02f3 traces, the
qualification rows' consequence attributions, F1 against the reference source, F2 and F3
against the captures, and the QEMU statements against the v10.2.0 source; it confirmed
the Q18 resolution argument and judged the harness change sound and minimal and the
unchanged check name right (the offline comparison is by name). Findings, all applied
to the records:

| ID | Sev | Finding | Resolution |
| --- | --- | --- | --- |
| R1 | medium | "A write followed by a read is stamped 1 µs apart most often" was false: over the 40 L02f3 traces the modal difference is 6 µs; 0 or 1 µs occurs in 2,827 of 255,188 pairs (38 of 40 runs). The ledger's per-run minimum line was also wrong. The resolution argument stands on the write-to-write minimum of 0 µs in every run and on those pairs | Both paragraphs corrected; the d22 row says the "most likely most" expectation rested on the misreading |
| R2 | low | The candidate's resets in the acceptance set number 180, not 80; the 4 µs minimum is L02f3's (this unit's is 5) | Corrected |
| R3 | low | The reference's gap range matched neither store | One range from this unit (5.84 to 6.08 ms) in both places |
| R4 | low | d17's 129 PCI configuration accesses are 79 reads and 50 writes, not all reads | Corrected |
| R5 | low | d18's declared "probe … failed with error -19" line cannot appear (the driver core logs `-ENODEV` at debug level), and its absence was not reported | Said in the d18 row |
| R6 | low | The `q1` run script was edited in place for `q2`; its text is not preserved, only its hash | Said in the frozen table and the ledger; per-round copies in future |
| R7 | info | `q2`'s declaration commit and launcher share a second | The first scenario start (00:34:33) cited |
| R8 | info | d21c's pulled-in byte is the first unwritten FCS byte; the equivalence is contingent on buffer contents | Said in the d21c row |
| R9 | info | The notebook's 00:24 entry attributes the padding premise to L02d3's reviewer, who recorded the opposite | Closed in F5 |
| R10 | info | QEMU statements are from the v10.2.0 source; the binary is 10.2.1 | Said where cited |
| R11 | info | Ledger numbers: one IMC→STATUS median, and check counts stated as totals | Ledger corrected |

No finding changed a verdict, a qualification or the `unobservable` label. The reviewer
judged broader review unnecessary: one constant in one trace rule, with tests, the
acceptance set rerun for both drivers and the other rules reproduced byte-identically.

## Measures

- Operator time: about 00:10 to the final checkpoint on 2026-09-26 (Pacific), one session;
  see the notebook. Model cost not measured.
- Host time: round `q1` (63 runs, 8 at a time) 2 minutes 2 seconds; round `q2` (6 runs)
  24 seconds. Defect builds about 20 s each.
- Human review effort: none during the unit.

## Open limitations

- Qualification is defect-specific, as in L02d3: each row shows one defect caught under
  these conditions. Q24's open-failure defect fails at the first line of `ndo_open`; a
  failure later in open (after resources are allocated) was not planted. Q25 is qualified
  by a defect that drops the frames; small-frame content corruption is not detected (F3).
  Q26's bind defect fails probe at one point; a bind failure from a wrong PCI id table
  (the module loads, nothing matches) was not planted, though the same check would see it.
- Q18 is `unobservable` here: neither the old nor the restated rule was shown able to fail
  on this host and model, for a reason not determined (F4). The restated rule is kept
  because it is the sound reading of the instrument; a host or model on which a reset
  write can be followed within 2 µs would make it qualifiable. Hardware is HF-1's.
- The model delivers runts (F2); a driver whose receive path assumes 60-byte frames would
  pass here for the wrong reason or fail here and not on hardware.
- One host, one QEMU version, KVM only, eight runs at a time; the acceptance-set rerun
  is two repetitions per scenario, as L02f3's.
- The reviewer, the implementer and L02f3's reviewers share a model family; no human read
  the runs in this unit.
- Subagent transcripts are recorded by path in the run's ledger; those paths are temporary.
