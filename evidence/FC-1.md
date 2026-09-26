<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# FC-1: a small-frame content check

## Terms

- **Claim**, **qualified**, **precondition**, **planted defect**, **isolated run** — as in
  the [L02d3 evidence](L02d3.md#terms). **Candidate** — `e1000_l02` as CF-1 left it (spec
  revision 6); **reference** — Linux v6.12's `e1000`.
- **Pattern payload** — the payload busybox `ping -p` sends: its 4-byte timestamp, then one
  byte repeated. Without `-p` the timestamp is followed by zeros.
- **Copybreak path** — the reference's receive path for frames of at most 256 bytes, which
  copies the frame into a small buffer; d21c is planted in it (QF-1).
- **Checksum-error count** — `InCsumErrors` on the `Icmp:` line of `/proc/net/snmp`: ICMP
  messages the kernel dropped for a bad checksum. The kernel verifies every ICMP message,
  echo replies included, after a raw socket (busybox ping's) has received it.
- **Acceptance set** — L02f3's run set: all ten suite scenarios, isolated, reference ×2 and
  candidate ×2, 40 runs.

See the [glossary](../GLOSSARY.md), the [design](../QEMU-DIFFERENTIAL.md) (§7, A6), the
[plan](../IMPLEMENTATION-PLAN.md) (FC-1), the [QF-1 evidence](QF-1.md) (F3, the finding
this unit answers) and the [notebook chapter](../notebook/FC-1.md).

## Status

**Complete, 2026-09-26.** `frame-sizes` now checks what its 60- and 61-byte frames carry,
not only that they arrive: the pings carry a pattern payload, and four new checks read the
content from the captures and from the DUT kernel's checksum-error count. A new claim, Q27
(small-frame content, both directions), is qualified by two planted defects in isolated
runs, 3 of 3 each, for the intended reason: QF-1's d21c, invisible to the suite before this
unit, now fails the checksum-error check on all four 60/61-byte pings, and a new transmit
defect fails the two capture comparisons at the byte it corrupts. The reference and the
candidate pass the whole acceptance set on the changed harness (20 of 20 each) and
`frame-sizes` five times each, every check, declared before the first run; every existing
check name is unchanged and the shared decoder is byte-identical on every stored capture.
The review found one robustness gap in the new check (a failed counter read could hide a
rise); fixed with a test, and the affected scenario rerun on the final harness (`884e771c…`)
for both drivers and both defects, 8 of 8 as declared. Private run `fc1-20260926-01`: 60
isolated runs in two declared rounds, none repeated or discarded; one independent review of
the diff and the run artifacts (below).

## The gap (QF-1, F3)

`frame-sizes` checked that 60- and 61-byte frames *arrive* (Q25), not what they carry. A
ping's payload past its 4-byte timestamp is zeros, so QF-1's d21c, which shifts every
received small frame's tail by one byte, passed the scenario 3 of 3: shifted zeros are zeros,
and the peer's capture showed every reply equal to its request. Q09 (4 MiB over HTTP)
covers large frames only, and only as a stalled transfer.

## The check

`frame-sizes` now sends its 60- and 61-byte pings, both directions, with a one-byte pattern
(`ping -p`; `0xa5` for 60-byte frames, `0x5a` for 61), and judges the content three ways.
Every existing check name is unchanged; the 42-, 1513- and 1514-byte pings are unchanged.

| Check (`frame-sizes`) | Reads | Shows |
| --- | --- | --- |
| "the DUT's kernel counted no ICMP checksum errors while the pings ran" | `/proc/net/snmp` on the DUT before the pings and after each of the nine | Frames the driver delivered arrived intact, echo replies included. This is the only witness for a reply the driver delivered corrupted: ping's raw socket receives the reply before the kernel verifies it, so ping counts it as received (arrival) while the kernel counts the error (integrity). The detail names the pings during which the count rose |
| "the DUT echoed the peer's 60- and 61-byte echo requests byte for byte" | the peer's capture; each request matched to the reply with its ICMP id and sequence number | The request reached the DUT's stack intact and the reply left the DUT intact (a corrupted request that the kernel dropped shows as "no reply") |
| "the DUT's 60- and 61-byte echo requests reached the peer with the pattern payload intact" | the peer's capture | What the driver transmitted is what the stack gave it, past the timestamp |
| "the peer's 60- and 61-byte echo requests and replies reached the DUT's device with the expected payload" | the DUT's capture (the frames that entered its device) | The stimulus: the peer's requests carried the pattern and its replies repeated the DUT's requests. A precondition, not a claim |

Why captures alone cannot do it: both captures sit on the wire side of the driver, so a
frame the driver delivers corrupted to the stack is visible only through what the stack does
with it, an echo reply or a checksum error. Why one byte: busybox `ping -p` takes one byte,
so a shift that stays inside the pattern is still invisible; a shift into the byte beyond
the frame, a flipped byte, a stale tail or a wrong length is not (limitation below).

**Claim.** A new claim rather than a change to Q25's frozen text, for three reasons: Q25 is
arrival ("frames of 60 and 61 bytes are received"), qualified by d21b, and stays as it is;
content is a different behavior, which is what F3 says; and the claim list's precedent for
a new check is a new claim added before the candidate's first run of it (Q25 and Q26 in
L02d3). Declared here before any run:

| ID | Claim | Checks (scenario) |
| --- | --- | --- |
| Q27 | Frames of 60 and 61 bytes are received and transmitted with their content intact | the checksum-error count; the DUT echoed the peer's requests byte for byte; the DUT's requests reached the peer with the pattern intact (frame-sizes) |

**Shared code.** `icmp_echoes()`, which the `capture` pseudo-scenario and the sent-sizes
check use, is now a projection of the new decoder. Offline, before any run, the old and new
functions gave identical output on all 484 captures stored from every earlier run (1,270,293
frames). On QF-1's stored `frame-sizes` captures the new echo check passes for the reference,
the candidate and d21c (F3 reproduced offline) and fails for d21 and d21b (no replies); the
two pattern checks fail on every stored capture, as they must for a stimulus that carried
no pattern. 57 harness tests pass (44 before, 13 for the changed surface).

## Frozen before execution (2026-09-26, 08:41 Pacific)

Private run `fc1-20260926-01`. The candidate does not change in this unit.

| Artifact | Identity |
| --- | --- |
| Harness | `l02harness.py` `9c33f54d…` (this unit's change; round `f1`), `guest-init.sh` `eccecebe…` (unchanged); the previous harness was `7024864e…` (QF-1, CF-1). Final harness after the review: `884e771c…` (round `f2`, below) |
| Reference module | `e1000.ko` `43242751…` |
| Candidate module | `e1000_l02.ko` `ce7e3e2c…` (CF-1 round 1) |
| Kernel, QEMU, busybox | `0d96151b…`; 10.2.1+ds-1ubuntu3.2, `0cd4112a…`, KVM, DUT memory 3 GiB; `df12634c…` (busybox 1.37.0, whose `ping` has `-p`) |
| Defects (modules) | d21c `5ff074ae…` (QF-1's module, unchanged); d24 `9d48bc1d…` (new, built out of tree against the same kernel, 0 warnings) |
| Run script and job list | `run1.sh` `42733562…`, `jobs-f1.txt` `79e0028b…` (52 lines) |

- **d21c** (QF-1): the copybreak copy's second part starts one byte too far, so received
  frames longer than 46 bytes arrive with their tail shifted by one byte; the byte pulled in
  is the one beyond the frame in the receive buffer (0 in QF-1's runs).
- **d24** (new, transmit): after the software padding, bit 0 of frame byte 50 is flipped in
  every frame of 51 to 100 bytes. Byte 50 is payload byte 8 of a 60- or 61-byte echo, inside
  the pattern; for ARP and the padded 42-byte echo it is padding; 1513- and 1514-byte frames
  are untouched. It also lands in the DUT's IPv6 housekeeping frames (70 to 90 bytes), which
  no check reads (review R4).

**Run declaration (round `f1`, 52 isolated runs, eight in parallel).**

- The acceptance set on the changed harness: all ten suite scenarios, reference ×2 and
  candidate ×2 (40 runs). Criterion: reference 20 of 20 PASS, candidate 20 of 20 PASS on
  every check. The harness file changed and a shared decoder was reimplemented (shown
  byte-identical offline), so every earlier qualification's scenario is rerun for both.
- `frame-sizes` ×3 more for each driver (5 each in all): every check PASS, the four new ones
  included; the checksum-error count unchanged; the content details report two requests of
  each size per direction.
- d21c, `frame-sizes` ×3 (Q27, receive), expected in 3 of 3: bring-up and the 42-, 1513- and
  1514-byte pings PASS; "DUT pings peer with 60-byte frames" and "… 61-byte frames" **PASS**
  (the reply's shifted tail ends in the byte beyond the frame, its checksum fails, and the
  kernel drops it after ping's raw socket already has it: arrival, not integrity); "peer
  pings DUT with 60/61-byte frames" FAIL (the request's checksum fails; no reply); the
  checksum-error check **FAIL** with +2 during each of the four 60/61-byte pings (8 in all),
  the claim's own failure and, on the DUT's own pings, the only failing check; "the DUT
  echoed … byte for byte" FAIL with "no reply" for the peer's four requests (the claim's
  failure as the kernel's checksum saw it); the pattern check and the stimulus check PASS;
  sent-sizes FAIL on the missing 60/61-byte replies (a consequence); runts, rmmod, the
  kernel log and the trace rules PASS. Contingency: a frame whose byte beyond the frame
  equals its pattern byte would pass unchanged; any such frame is reported.
- d24, `frame-sizes` ×3 (Q27, transmit), expected in 3 of 3: bring-up and the 42-byte ping
  PASS (byte 50 is padding there); "DUT pings peer with 60/61-byte frames" FAIL (the peer
  drops the corrupted request); 1513/1514 PASS; "peer pings DUT with 60/61-byte frames" FAIL
  (the DUT's reply is corrupted on transmit); the checksum-error check PASS (nothing corrupted
  reaches the DUT); the pattern check **FAIL**, each of the DUT's four requests "differs at
  frame byte 50"; the echo check **FAIL**, each reply "differs at frame byte 50" (both the
  claim's own failure); the stimulus check FAIL with "no reply" for the DUT's four requests
  (a consequence: the peer never replied); sent-sizes, runts, rmmod, the kernel log and the
  trace rules PASS.
- Every failure is kept, attributed and reported; no run is repeated to replace a result.
  A reference or candidate failure blocks the corresponding conclusion.

The declaration is in the run's ledger and here; this section was committed
([`612ec59`](https://github.com/curtisgalloway/driver-lab/commit/612ec59), 08:41:24) before
the launcher started (08:41:35) and the first scenario (08:41:38). (The section as committed
said "08:42"; the time above is the commit's, finding F1.)

**Round `f2` (declared after the review, 09:03 Pacific, before any `f2` run; committed
before launch).** Review finding R2: the checksum-error check compared each counter read
with the previous one and let a failed read reset the comparison, so a rise across the gap
would have been lost. Fixed (a failed read fails the check; comparisons are against the
last successful read; one test), final harness `l02harness.py` `884e771c…`; the diff from
`9c33f54d…` is that check's bookkeeping and its detail text, nothing that touches the
captures, the pings or any other check, and the shared decoder is unchanged (identical on
all 588 stored captures). No read failed in any `f1` run (all 160 succeeded), so `f1`'s
verdicts stand as computed; `f2` shows the final harness on the affected scenario: reference
×2, candidate ×2, d21c ×2 and d24 ×2 of `frame-sizes`, eight isolated runs, with the same
expected outcome per check as `f1`'s declaration, except that under d24 "peer pings DUT
with 60/61-byte frames" is expected to PASS (F2).

## Results

All 52 runs of `f1` (launched 08:41:35, first scenario 08:41:38, last scenario end
08:43:23, launcher done 08:43:24 Pacific), KVM, every
run's `identities.json` recording the frozen hashes (checked by `summary.py` in the run
store). "Run" names the run directory in `fc1-20260926-01`.

**Reference and candidate on the changed harness.** 20 of 20 PASS each across the ten
scenarios ×2, and `frame-sizes` 5 of 5 PASS each: 46 runs, 1,118 checks, 0 failed, the
trace and capture pseudo-scenarios and the kernel-log check included. In every `frame-sizes`
run the checksum-error count read 0 before the pings and 0 after; the pattern check saw the
DUT's four requests (two of 60 bytes, two of 61) with the pattern intact; the echo check saw
the peer's four requests echoed byte for byte; the stimulus check saw the peer's eight
frames (four requests, four replies) with the expected payload, which also confirms the
`-p` layout the check assumes (timestamp, then the pattern). Every other scenario's check
count is as in CF-1's run set; `frame-sizes` has 23 checks in the scenario (19 before, plus
the four), 29 with the trace rules.

**Round `f2` on the final harness** (`884e771c…`; 8 runs, 09:01:05 to 09:01:25): reference
2 of 2 PASS, candidate 2 of 2 PASS, every check, with the same content details as in `f1`;
d21c 2 of 2 and d24 2 of 2 fail exactly the five checks each that `f1` shows below, with the
same details (`f2-*-frame-sizes-1..2`; `analysis/f2-content.txt`). Every identity as
frozen, with the final harness hash.

| Defect | Runs | Declared failing checks | Result |
| --- | --- | --- | --- |
| d21c small-frame tail shifted by one byte (receive) | `f1-d21c-frame-sizes-1..3` | the checksum-error check (+2 on each 60/61-byte ping); the echo check ("no reply"); "peer pings DUT with 60/61-byte frames"; sent-sizes as a consequence | **as declared, 3 of 3**, five failed checks each: the checksum-error check with `+2 during 'DUT pings peer with 60-byte frames'; +2 during '… 61-byte frames'; +2 during 'peer pings DUT with 60-byte frames'; +2 during '… 61-byte frames'`; the echo check with "no reply" for the peer's four requests; the two "peer pings DUT" checks at 100 % loss; sent-sizes missing `(0, 60), (0, 61)`. "DUT pings peer with 60-byte frames" and "… 61" **PASS** in 3 of 3 (`2 packets received, 0% packet loss`) while the count rose by 2 during each: the corrupted replies were counted received by ping and counted bad by the kernel. The pattern check, the stimulus check, the 42-, 1513- and 1514-byte pings, bring-up, runts, rmmod, the kernel log and the trace rules passed. The contingency did not arise: the 8 ICMP frames per run the defect touched (24 over the three runs) all failed their checksum, `InCsumErrors 8` at the end of every run |
| d24 small-frame transmit flips frame byte 50 | `f1-d24-frame-sizes-1..3` | the pattern check and the echo check ("differs at frame byte 50"); "DUT pings peer with 60/61-byte frames"; "peer pings DUT with 60/61-byte frames"; the stimulus check as a consequence | **as declared but for one check, 3 of 3**, five failed checks each: the pattern check with every DUT request `differs at frame byte 50 (0xa4 for 0xa5)` or `(0x5b for 0x5a)`; the echo check with every reply `differs at frame byte 50`; the two "DUT pings peer" checks at 100 % loss (the peer's kernel dropped the requests); the stimulus check with "no reply" for the DUT's four requests. **Not as declared:** "peer pings DUT with 60/61-byte frames" **passed** in 3 of 3: the DUT's corrupted replies reached the peer's ping on its raw socket before the peer's kernel verified them, exactly as on the DUT (F2). The checksum-error check passed (`0 before, 0 after`: nothing corrupted reached the DUT), sent-sizes passed (the frames exist at their sizes), and the 42-, 1513- and 1514-byte pings, bring-up, runts, rmmod, the kernel log and the trace rules passed |

## Qualification

For each row the reference passed `frame-sizes` on the same harness five times
(`f1-ref-frame-sizes-1..5`), and the failing check is the claim's own; the notes say what
else failed alongside it and why that is a consequence.

| Claim | Result | Defect → runs | What failed, and why it is the claim's failure |
| --- | --- | --- | --- |
| Q27 receive content | **qualified**, as the kernel's checksum sees it | d21c → `f1-d21c-frame-sizes-1..3` | The checksum-error check failed with +2 during each of the four 60/61-byte pings: eight ICMP messages per run that the driver delivered with a bad checksum. On the DUT's own 60/61-byte pings this was the only failing check, ping having reported 0 % loss: the case no check could see before this unit. The peer's 60/61-byte requests got no reply (the echo check and the two arrival checks), the same corrupted delivery seen where the kernel dropped the request; the missing replies fail sent-sizes as a consequence. The transmit checks passed, so the transmit path was intact |
| Q27 transmit content | **qualified** | d24 → `f1-d24-frame-sizes-1..3` | The pattern check failed on every DUT request and the echo check on every DUT reply, each at frame byte 50, the byte the defect flips; both name the byte and the values. The DUT's own 60/61-byte pings failed as the peer's kernel dropped the requests; the peer's pings passed for the same reason the DUT's did under d21c (F2); the checksum count stayed 0, so nothing corrupted reached the DUT; the stimulus check failed only because the peer never replied to a corrupted request (a consequence) |

**Candidate results.** On the changed harness the candidate passes `frame-sizes` 5 of 5
with every content check, so Q27 is qualified evidence about the candidate within the scope
above: its small-frame receive and transmit paths deliver 60- and 61-byte frames with their
content intact, as far as the ICMP checksum and a one-byte pattern can tell.

**Coverage after this unit.** 26 of 27 claims qualified (L02d3: 22, with Q15 in L02f2b;
QF-1: Q24, Q25, Q26; here: Q27), each with its stated scope; Q18 unqualified,
`unobservable` ([QF-1](QF-1.md)).

## Acceptance (against the brief)

| Criterion | Result |
| --- | --- |
| The harness checks the contents of small frames, not only their arrival, from the capture, both directions | Met: a pattern payload on the 60/61-byte pings; three capture checks (the DUT's requests against the pattern, the DUT's replies against the peer's requests, the peer's frames as the DUT's device received them) and the kernel's checksum-error count for the one path no capture can see |
| Existing check names stable; a new check and a claim, with the convention said | Met: every existing name unchanged (1,118 checks in the reference and candidate runs, every scenario's count as before plus `frame-sizes`' four); Q27 a new claim, with the reasons above |
| Harness tests for the changed surface | 14 new tests, 58 pass (one added for the review's R2) |
| Counts declared before running; d21c fails the new check for the intended reason, 3 of 3 isolated | Met: declaration committed at `612ec59` 14 s before the first scenario; d21c 3 of 3 on the checksum-error check, +8 per run; d24 3 of 3 on the two capture comparisons |
| Reference and candidate pass the declared repetitions of the affected scenario | `frame-sizes` 5 of 5 each on `9c33f54d…`, every check; 2 of 2 each on the final harness `884e771c…` |
| Whatever else the change touches rerun; earlier qualifications carry | The acceptance set rerun on the changed harness, 20 of 20 each; the shared decoder byte-identical on all 484 stored captures; every other scenario's checks unchanged by name and count |
| Every failure kept and attributed; no run repeated | 60 runs in two declared rounds, all kept; d24's one undeclared pass reported (F2) |

## Findings

| ID | Sev | Finding | Resolution |
| --- | --- | --- | --- |
| F1 | info | The frozen section as committed said "08:42 Pacific"; the commit is 08:41:24 | Corrected to the commit's time, with the note in that section |
| F2 | low | **The declaration applied two rules to one program.** It expected the DUT's ping to count a corrupted reply as received (raw socket before the kernel's checksum) and the peer's ping to lose one (kernel drop). Both guests run the same busybox ping on a raw socket, so under d24 the peer counted the DUT's corrupted replies as received, 3 of 3, and "peer pings DUT with 60/61-byte frames" passed where a failure was declared. The content checks caught the corruption either way | Recorded; the d24 row reports the pass. It is a second instance of arrival-not-integrity, on the peer's side: the four arrival checks at 60/61 bytes never see a corrupted reply, only a corrupted request. The peer's own checksum-error count is not read (limitation); the capture comparison sees the DUT's transmit corruption directly |
| F3 | info | The arrival-not-integrity prediction QF-1 made about the DUT's own pings held: under d21c, ping reported 0 % loss on both sizes in 3 of 3 while the kernel counted every reply bad | Recorded; this is why the checksum-error check exists |
| F4 | low | **A failed counter read could hide a rise** (review R2): the check compared each read with the previous one and a failed read reset the comparison. Not exercised: all 160 reads in `f1`'s 16 `frame-sizes` runs succeeded | Fixed: a failed read fails the check ("could not be read at every point") and later comparisons are against the last successful read; one test; the affected scenario rerun on the final harness (round `f2`, 8 of 8 as declared) |

## Review

One independent fresh-context reviewer (same model family) read the diff at `6d92d77`
(`9f8e43e..`), the run store (ledger, the 52 `f1` runs' verdicts, identities, command logs,
captures, the defect diffs and build logs, the analysis scripts) and this file, with the
brief to recompute what it could and to ask for `review-swarm` if it judged the change
broader than one scenario. Its report is in the run store under `review/`. It recomputed
every verdict and failed-check list (52 runs), the check counts (1,118, 0 failed; 23 and 29
for `frame-sizes`; every other scenario equal to CF-1's), every identity against the frozen
table, the declaration commit's time against the launcher and the first scenario, the
counter reads in the command logs (0, 0, 2, 4, 4, 4, 6, 8, 8, 8 under d21c), and parsed the
captures of a reference, a candidate, a d21c and a d24 run itself: the pattern bytes at
frame bytes 46 onward past a varying 4-byte timestamp, d24's flipped byte 50 in the DUT's
eight frames (its own ICMP checksum found exactly those eight bad per capture), d21c's four
missing replies, the padded 42-byte frames excluded. It confirmed the byte-beyond-the-frame
reasoning from the reference's copybreak path and the d21c diff, the raw-socket-before-
checksum claim from the kernel's `ip_input.c`, `raw.c` and `icmp.c` and the reference's
IXSM handling, F2 from the peer's command log and capture, the qualification rows' scopes
and consequence attributions, the offline identity claim (rerun: 588 of 588 captures with
this round's included), the four check names against what they compute, the unchanged
stimulus of the other checks, the records and privacy rules, and the claim count. Findings,
all applied:

| ID | Sev | Finding | Resolution |
| --- | --- | --- | --- |
| R1 | low | "All 24 frames the defect touched per run" is 8 per run (24 over three runs); the capture also holds IPv6 multicast frames in the copybreak range that no counter sees | The d21c row says 8 ICMP frames per run |
| R2 | low | The checksum-error check let a failed counter read hide a rise (reproduced with the test fake; not exercised in the runs) | Fixed with a test; round `f2` on the final harness (F4) |
| R3 | low | Notebook and index timestamps (08:50) ran ahead of the commit holding them (08:47:46); the ledger's step range too | A closing notebook entry at its real time; the ledger's steps corrected; the index's times are the entries' |
| R4 | info | d24 also flips byte 50 of the DUT's IPv6 housekeeping frames, which no check reads | Said in the d24 description |
| R5 | info | Two intervals in one sentence for round `f1` | The launcher's and the scenarios' endpoints both given |
| R6 | info | The Review section was written in the past tense before the review | This section, written from the report |
| R7 | info | The offline identity claim holds and covers this round too (588 of 588) | None |
| R8 | info | The busybox source read was the mirror's `master`, not the 1.37.0 tag; the captures confirm the binary's layout | Said in the ledger |

No finding changed a verdict, a check count, an identity or a qualification. The reviewer
judged broader review unnecessary: one scenario changed, no shared execution machinery or
access control, and the one reimplemented shared function is a projection shown identical
on every stored capture and exercised again by its two consumers in this round.

## Measures

- Operator time: about 08:22 to 09:05 on 2026-09-26 (Pacific), one session; see the
  notebook. Model cost not measured.
- Host time: round `f1` (52 runs, 8 at a time) 1 minute 49 seconds from launcher start to
  end (105 s from the first scenario's start to the last main scenario's end); round `f2`
  (8 runs) 20 seconds; the d24 build about 20 s; the review about 11 minutes.
- Human review effort: none during the unit.

## Open limitations

- The pattern is one byte, so a shift that stays inside the pattern is invisible; d21c is
  caught at its boundary byte (the byte beyond the frame), and both qualifying defects are
  ones the ICMP checksum sees. A corruption that preserves the checksum is seen by the
  capture comparisons only where the DUT echoes or sends the frame; a checksum-preserving
  corruption of a reply the DUT receives is not detected by any check.
- The checksum-error count relies on the kernel verifying the checksum in software, which
  it does here because the model marks every received frame "ignore checksum" (IXSM) and
  both drivers honor it. A driver that wrongly marked a corrupted ICMP frame's checksum as
  verified would escape the count; the echo comparison would still see a corrupted request.
- The peer's checksum-error count is not read; corruption of what the DUT transmits is seen
  from the peer's capture and as a lost ping, not as a counted error at the peer (F2).
- The 1513- and 1514-byte pings still carry zeros; large-frame content rests on Q09, which
  sees receive corruption only as a stalled transfer (L02d3).
- Qualification is defect-specific, as in L02d3: d21c and d24 each show one corruption
  shape caught; a stale-buffer defect (delivering an earlier frame's bytes with a valid
  checksum) was not planted.
- One host, one QEMU version, KVM only, eight runs at a time; the acceptance-set rerun is two
  repetitions per scenario, as L02f3's, with `frame-sizes` at five.
- The reviewer and the implementer share a model family; no human read the runs in this unit.
- Subagent transcripts are recorded by path in the run's ledger; those paths are temporary.
