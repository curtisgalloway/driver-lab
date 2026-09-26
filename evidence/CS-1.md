<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# CS-1: checksum-preserving corruption of received small frames

## Terms

- **Claim**, **qualified**, **precondition**, **planted defect**, **isolated run** — as in
  the [L02d3 evidence](L02d3.md#terms). **Candidate** — `e1000_l02` as CF-1 left it (spec
  revision 6, module `ce7e3e2c…`); **reference** — Linux v6.12's `e1000`.
- **Checksum-preserving corruption** — a change to a frame's bytes that leaves every
  ones'-complement checksum over them unchanged: two 16-bit words at even offsets
  swapped, or a compensating two-byte change. IP, ICMP, TCP and UDP all use that sum, so
  the stack accepts such a frame.
- **Small-frame streams** — 1 MiB over HTTP each way, added to `frame-sizes` by this unit,
  in frames of at most 214 bytes: the peer's MTU is lowered to 200 while they run.
- **Copybreak path** — the reference's receive path for frames of at most 256 bytes
  (descriptor length, which counts the 4-byte FCS the model reports), which copies the
  frame into a small buffer; d21c (QF-1) and d25 (here) are planted in it.
- **Acceptance set** — L02f3's run set: all ten suite scenarios, isolated, reference ×2 and
  candidate ×2, 40 runs.

See the [glossary](../GLOSSARY.md), the [design](../QEMU-DIFFERENTIAL.md) (§7, A6), the
[plan](../IMPLEMENTATION-PLAN.md) (CS-1), the [FC-1 evidence](FC-1.md) (the open
limitation this unit answers) and the [notebook chapter](../notebook/CS-1.md).

## Status

**Results in, review pending, 2026-09-26.** `frame-sizes` now carries 1 MiB over HTTP
each way in frames of at most 214 bytes and compares the delivered bytes by MD5, so a
corruption that keeps the checksum is seen in either direction; a new claim, Q28, is
qualified by two planted defects that swap two 16-bit words, on receive (d25) and on
transmit (d26), 3 of 3 each, failing exactly the stream check for their direction while
the reference and the candidate pass `frame-sizes` 5 of 5 each and the nine other
scenarios 18 of 18 each. No guest-image change; every existing check name unchanged.
Round `c1` (52 runs) was **not as declared** for a reason in the harness's premise, not
in either driver: the kernel never advertises an MSS under 256 by default, so the DUT's
stream went in 310-byte frames and the stimulus check withheld every `frame-sizes` PASS
(F1), and d26 caught 1 of 3 as a consequence (F2). The fix is one more peer-side setting;
round `c2` (16 runs) on it is as declared. Private run `cs1-20260926-01`: 68 isolated
runs in two declared rounds, none repeated or discarded.

## The gap (FC-1, open limitation)

FC-1's checks see a corruption of a 60- or 61-byte frame through the ICMP checksum (the
kernel's checksum-error count, a dropped request) or through the echo (the DUT's reply
compared with the peer's request). A corruption that keeps the checksum in a **reply the
DUT receives** is seen by neither: the kernel accepts the reply, busybox `ping` reads it
from a raw socket and compares nothing past the id and type, and both captures sit on
the wire side of the driver. ping's payload is one repeated byte, so even a swap of two
words inside it changes nothing; busybox has no tool that sends a chosen payload over
ICMP or UDP (its `nc` has no UDP mode). Q09 (4 MiB over HTTP, `ring-wrap`) compares the
delivered bytes by MD5, but in 1514-byte frames, and was qualified only by a
checksum-breaking defect that stalled the transfer (L02d3).

## The check

After its pings, `frame-sizes` lowers the peer's MTU to 200, serves 1 MiB of random
bytes over HTTP from the peer to the DUT and then from the DUT to the peer (port 8081,
so a capture check can tell the streams from `ring-wrap`'s transfer on 8080), compares
`wget`'s MD5 of the bytes the receiving stack delivered with the sender's MD5 of the
file, and restores the peer's MTU. Every existing check name is unchanged; the pings
and their content checks are unchanged.

| Check (`frame-sizes`) | Reads | Shows |
| --- | --- | --- |
| "1 MiB over HTTP in small frames peer to DUT arrives intact" | the MD5 the DUT's `wget` computed against the peer's | What the driver delivered to the DUT's stack is what the peer sent, byte for byte, over about 7,100 frames of at most 214 bytes: the claim's receive half. A corruption that keeps TCP's checksum reaches `wget` and changes the MD5; one that breaks it stalls the transfer (Q09's failure shape) |
| "1 MiB over HTTP in small frames DUT to peer arrives intact" | the MD5 the peer's `wget` computed against the DUT's | What reached the peer is what the DUT's stack gave the driver: the claim's transmit half |
| "peer's MTU set to 200 for the small-frame streams", "peer's MTU restored to 1500 after the small-frame streams", "HTTP server with a 1 MiB file (peer to DUT)", "… (DUT to peer)" | the peer's and the DUT's command results | Preconditions: the stimulus was set up and taken down |
| "the small-frame streams' data frames were at most 214 bytes and carried 1 MiB each way" | both captures: the peer's data frames from the DUT's capture (what entered its device), the DUT's from the peer's | The stimulus: each stream ran in small frames and carried the whole 1 MiB. A precondition, not a claim; a stalled stream fails it too |

**Why the peer's MTU.** TCP's checksum is the same 16-bit ones'-complement sum as
ICMP's, so a word swap survives it and reaches the application; MD5 over the delivered
bytes is then the witness, in either direction. The frames have to be small for the
receive path under test to be the small-frame one (the reference's copybreak path takes
frames up to 256 bytes with the FCS), and lowering the **peer's** MTU bounds both
directions: the peer's own sends by its MTU, the DUT's by the MSS the peer advertises
from it. So nothing changes on the DUT, and no MTU change reaches the driver under test,
whose `ndo_change_mtu` the two drivers may implement differently (the reference takes a
running interface down and up on one). The payload is `/dev/urandom`, as `ring-wrap`'s, so every frame's
bytes are distinct and any swap that moves bytes changes the MD5.

**Why not a UDP sender in the guest image.** A static sender and receiver with a chosen,
position-dependent payload would do the same for UDP, at the cost of a new program in
the initramfs with its own source, build and pin. busybox `httpd`, `wget`, `md5sum`,
`dd` and `ip link set … mtu` are already in the pinned image (1.37.0, `df12634c…`) and
already used by `ring-wrap` (all but the MTU change); the whole addition is one scenario
step and one capture check, and the guest image is unchanged.

**The reference transmits with TSO.** The reference advertises TCP segmentation offload
on the 82540EM, so the DUT's stream may leave its stack as large skbs that the model
segments at the 148-byte MSS; the wire frames and the MD5 at the peer are the same
either way, and the transmit defect below is written for both skb shapes. The candidate's
features are not known to this unit and do not matter to the check.

**Claim.** A new claim rather than a change to Q27's or Q09's frozen text: Q27 names 60-
and 61-byte ICMP frames and its qualifying defects are checksum-visible; Q09 is
`ring-wrap`'s 4 MiB in 1514-byte frames, qualified as a stalled transfer; this is a
different check on different frames, and the claim list's precedent for a new check is a
new claim added before the candidate's first run of it (Q25–Q27). Declared here before
any run:

| ID | Claim | Checks (scenario) |
| --- | --- | --- |
| Q28 | A 1 MiB TCP stream in frames of at most 214 bytes is received and transmitted with its content intact, as the MD5 of the delivered bytes shows | "1 MiB over HTTP in small frames peer to DUT arrives intact" (receive); "… DUT to peer arrives intact" (transmit) (frame-sizes) |

**Shared code.** `http_blob()`, `ring-wrap`'s transfer, gained size, port and wording
parameters whose defaults reproduce its commands and check names byte for byte (a test
holds the literal strings). A TCP segment decoder (`tcp_segments()`) is new and used by
the stimulus check only; the ICMP decoder is untouched. Offline, before any run, on
FC-1's four stored `ring-wrap` runs: every IPv4 TCP frame in every capture verifies its
TCP checksum (6,167 to 7,485 per capture); after swapping the 16-bit words at frame bytes
200 and 202 of every data frame of at least 204 bytes (5,797 to 5,844 per capture) every
one still verifies, the swap having changed every one; a flipped byte 200 fails every
one. On FC-1's stored `frame-sizes` captures, swapping two words inside the 60/61-byte
echoes' pattern changes no byte at all (the pattern is one repeated byte), which is the
FC-1 blind spot made concrete. The new decoder finds `ring-wrap`'s data frames on port
8080 (about 2,900 each way, at most 1514 bytes, 4,194,497 payload bytes each way, the
4 MiB plus the HTTP headers) and no stream on 8081 there. 70 harness tests pass (58
before; 12 for the changed surface: the decoder, the checksum-preservation premise for
TCP and ICMP, the stimulus check's pass and each failure, `ring-wrap`'s unchanged
strings, the scenario's order and the MTU restore when the DUT dies mid-stream).

## Frozen before execution (2026-09-26)

Private run `cs1-20260926-01`. The candidate does not change in this unit.

| Artifact | Identity |
| --- | --- |
| Harness | `l02harness.py` `da4c9407…` (this unit's change; round `c1`), `guest-init.sh` `eccecebe…` (unchanged); the previous harness was `884e771c…` (FC-1 final). Round `c2` (below): `a1735b9f…` |
| Reference module | `e1000.ko` `43242751…` |
| Candidate module | `e1000_l02.ko` `ce7e3e2c…` (CF-1 round 1) |
| Kernel, QEMU, busybox | `0d96151b…`; 10.2.1+ds-1ubuntu3.2, `0cd4112a…`, KVM, DUT memory 3 GiB; `df12634c…` (busybox 1.37.0) |
| Defects (modules) | d25 `9dbee0dd…`, d26 `72510962…`, built out of tree against the same kernel with `gcc-14`, 0 warnings each |
| Run script and job list | `run1.sh` `6618f966…`, `jobs-c1.txt` `84b47350…` (52 lines) |

- **d25** (receive): after the copybreak copy, when the descriptor length is at least 208
  (a wire frame of at least 204 bytes, the FCS counted), the 16-bit words at frame bytes
  200 and 202 are swapped. In `frame-sizes` that range holds the peer's stream data
  frames (214 bytes; bytes 200–203 are payload bytes 134–137 of the segment) and possibly
  the peer's HTTP response header frames, and no ICMP (60, 61, 98, 1513, 1514 and the
  42-byte frames), ARP (42) or IPv6 housekeeping frame (70 to 90).
- **d26** (transmit): after the software padding, the words at skb offsets 200 and 202
  are swapped in every skb of 204 to 256 bytes and in every GSO skb segmented for an MSS
  of at most 200, through `skb_copy_bits` and `skb_store_bits` so a payload in page
  fragments is reached; in a GSO skb the swap lands in the first segment's payload. The
  streams' skbs are affected whichever shape the stack gives them; the 60/61-byte echoes,
  the 1042-byte flood frames, the 1513/1514-byte pings and `ring-wrap`'s 1448-byte MSS
  are not.

**Run declaration (round `c1`, 52 isolated runs, eight in parallel).**

- The acceptance set on the changed harness: all ten suite scenarios, reference ×2 and
  candidate ×2 (40 runs). Criterion: reference 20 of 20 PASS, candidate 20 of 20 PASS on
  every check. The harness file changed and a shared function (`ring-wrap`'s transfer)
  was reparameterized (its strings shown identical by test), so every earlier
  qualification's scenario is rerun for both drivers.
- `frame-sizes` ×3 more for each driver (5 each in all): every check PASS, the seven new
  ones included (30 checks in the scenario, 36 with the trace rules); both stream checks
  with equal MD5s; the stimulus check reporting about 7,100 data frames of at most 214
  bytes each way carrying at least 1,048,576 bytes.
- d25, `frame-sizes` ×3 (Q28, receive), expected in 3 of 3: exactly one failed check,
  "1 MiB over HTTP in small frames peer to DUT arrives intact", with `sent` and `got`
  different MD5s and `wget` completing (the swap keeps TCP's checksum, so nothing is
  dropped or retransmitted and the transfer does not stall); every other check PASS,
  among them the DUT-to-peer stream, the stimulus check (the wire frames are the peer's,
  unchanged), every ping and ICMP content check, the checksum-error count, bring-up,
  runts, rmmod, the kernel log and the trace rules. Contingency: a swapped HTTP response
  header frame could make `wget` fail instead; the check still fails, with a `got` that
  is not the MD5 of a full body, and it is reported.
- d26, `frame-sizes` ×3 (Q28, transmit), expected in 3 of 3: exactly one failed check,
  "1 MiB over HTTP in small frames DUT to peer arrives intact", `sent` and `got`
  different, `wget` completing (the model computes the TCP checksum after the swap when
  the driver offloads it, and the swap keeps it when it does not); every other check
  PASS, the peer-to-DUT stream and the stimulus check included (the frames' lengths are
  unchanged). Contingency: the DUT's HTTP response header skb, if 204 to 256 bytes or a
  GSO skb, is swapped too and the peer's `wget` could fail on it; the check still fails
  and it is reported.
- Every failure is kept, attributed and reported; no run is repeated to replace a result.
  A reference or candidate failure blocks the corresponding conclusion. Every run's
  `identities.json` must record the hashes above.

The declaration is in the run's ledger and here, committed
([`067d33f`](https://github.com/curtisgalloway/driver-lab/commit/067d33f), authored
09:29:35 Pacific) before the launch (10:10:28).

**Round `c2` (declared 10:18 Pacific, after `c1`'s results, before any `c2` run;
committed before launch).** Finding F1's fix: the peer's advertised-MSS floor
(`/proc/sys/net/ipv4/route/min_adv_mss`) is lowered to 160 in the same command as the
MTU and restored to 256 with it, so the peer advertises 160 and the DUT's segments carry
148 bytes in 214-byte frames. Harness `l02harness.py` `a1735b9f…`; the diff from
`da4c9407…` is the two peer commands, the two checks' names ("peer's MTU set to 200 and
its minimum advertised MSS to 160 for the small-frame streams", "peer's MTU restored to
1500 and its minimum advertised MSS to 256 after the small-frame streams"; `c1`'s names
lacked the MSS clause), one docstring and the constants; nothing that touches the
captures, the pings, the stream checks, the stimulus check or any other scenario. Two
tests changed for the new strings; 70 pass. `jobs-c2.txt` (16 lines): `frame-sizes`
reference ×5, candidate ×5, d25 ×3, d26 ×3, isolated, eight in parallel.

- Reference and candidate, 5 of 5 each: every check PASS, the stimulus check now
  reporting about 7,100 data frames of at most 214 bytes **each way** carrying at least
  1,048,576 bytes; both MD5s equal.
- d25 ×3: as `c1`'s declaration (exactly one failed check, the peer-to-DUT stream), now
  with the stimulus check passing.
- d26 ×3: as `c1`'s declaration, expected in 3 of 3 (exactly one failed check, the
  DUT-to-peer stream): with an MSS of 148, every skb of the DUT's stream is either 214
  bytes or a GSO skb with `gso_size` 148, both inside the defect's conditions.
- The other nine scenarios are **not rerun** in `c2`; their `c1` results on `da4c9407…`
  stand as the acceptance set, on the diff argument above (as FC-1's round `f2`). This
  is a decision taken after seeing `c1`'s results, stated here as such; `frame-sizes`
  itself is rerun in full for both drivers.
- Every failure kept; no run repeated to replace a result; identities checked per run.

## Results

**Round `c1`** (52 runs, launched 10:10:28, launcher done 10:12:13 Pacific; 1 min 45 s),
KVM, every run's `identities.json` matching the frozen hashes; "run" names the run
directory in `cs1-20260926-01`. 36 PASS, 16 FAIL, 0 ERROR.

**The nine other scenarios.** Reference 18 of 18 PASS and candidate 18 of 18 PASS
(`smoke`, `ring-wrap`, `rx-overrun`, `link-flap`, `link-loss-tx`, `stop-start`,
`down-during-traffic`, `reload`, `itr`, ×2 each), every check, the trace and capture
pseudo-scenarios included: the acceptance set minus `frame-sizes`.

**`frame-sizes`, not as declared (F1).** All 16 runs (reference ×5, candidate ×5, d25
×3, d26 ×3) FAIL the stimulus check "the small-frame streams' data frames were at most
214 bytes and carried 1 MiB each way", and only its DUT-to-peer half: "peer to DUT:
7,087 to 7,089 data frames of 98 to 214 bytes carrying 1,048,769 bytes" (as declared:
the 1 MiB plus 193 bytes of HTTP headers) but "DUT to peer: 4,299 to 4,305 data frames
of 110 to **310** bytes carrying 1,048,769 bytes, 4,289 to 4,298 over 214". The peer's
SYN to the DUT's port 8081 carried an MSS option of **256** in all 16 runs (the DUT's
carried 1460), so the DUT's segments held 244 bytes: the kernel's `ipv4_default_advmss`
takes the larger of the route MTU less 40 and `ip_rt_min_advmss`, whose default
`DEFAULT_MIN_ADVMSS` is 256 (v6.12 `net/ipv4/route.c`). The premise that the peer's MTU
bounds the DUT's frames held only down to that floor. Every other check passed in the
reference's and the candidate's ten runs (35 of 36 each), both stream MD5s equal in
every one: **both drivers delivered 1 MiB intact in each direction**, peer to DUT in
214-byte frames and DUT to peer in 310-byte frames. That is an observation, not Q28
evidence: the claim's transmit half names frames of at most 214 bytes, and the stimulus
check, doing its job, withheld the scenario's PASS.

| Defect | Runs | Declared failing checks | Result |
| --- | --- | --- | --- |
| d25 small-frame receive words swapped | `c1-d25-frame-sizes-1..3` | "1 MiB over HTTP in small frames peer to DUT arrives intact" only | **the declared check, 3 of 3**: `sent` and `got` different MD5s in every run, `wget` completing (the transfer did not stall); the DUT-to-peer stream, every ping and ICMP content check, the checksum-error count, bring-up, runts, rmmod, the kernel log and the trace rules PASS. Plus the stimulus check, failed for F1's reason in every `frame-sizes` run of the round, on the DUT-to-peer half only; the peer-to-DUT half, the defect's side, read as declared (7,087 frames of 111 to 214 bytes) |
| d26 small-frame transmit words swapped | `c1-d26-frame-sizes-1..3` | "1 MiB over HTTP in small frames DUT to peer arrives intact" only | **1 of 3, a consequence of F1 (F2)**: run 1 failed the DUT-to-peer stream check (`sent` ≠ `got`), runs 2 and 3 passed it. The DUT's stream went in 310-byte frames (skbs over 256 bytes, or GSO skbs with `gso_size` 244), outside both of the defect's conditions; the only frames inside them were partial segments of 210 bytes, 16 in run 1 and none in runs 2 and 3 (`analysis/c1-mss.txt`), so the swap changed the delivered bytes in run 1 only. The stimulus check failed for F1's reason in all three; everything else PASS |

**Round `c2`** (16 isolated `frame-sizes` runs on `a1735b9f…`, launched 10:29:41, done
10:30:15 Pacific; 34 s), KVM, every identity as frozen with the `c2` harness hash. The
launch was the user's: the agent harness's safety check refused the implementer's launch
command, and the user ran the declared command instead (recorded in the ledger). 576
checks, 6 failed: exactly the six declared. The peer's SYN advertised an MSS of 160 in
all 16 runs, and the DUT's stream went in 214-byte frames (7,084 to 7,086 full segments
per run plus one to three partial ones of 90 to 210 bytes); the stimulus check passed in
every run: "peer to DUT: 7,087 to 7,089 data frames of 110 to 214 bytes carrying
1,048,769 bytes; DUT to peer: 7,087 to 7,090 data frames of 90 to 214 bytes carrying
1,048,769 bytes" (one run, `c2-d25-frame-sizes-1`, read 7,113 frames and 1,052,617 bytes
on the peer-to-DUT side: 26 segments retransmitted, an observation).

- **Reference 5 of 5 and candidate 5 of 5, every check** (36 each), both stream MD5s
  equal in all ten runs, every ping and ICMP content check passing, the checksum-error
  count 0 before and after. The candidate's stream leaves in a different mix of partial
  segments (16 of 186 bytes against the reference's one of 210), an observation about
  segmentation, the bytes intact.

| Defect | Runs | Declared failing checks | Result |
| --- | --- | --- | --- |
| d25 small-frame receive words swapped | `c2-d25-frame-sizes-1..3` | "1 MiB over HTTP in small frames peer to DUT arrives intact" only | **as declared, 3 of 3**: `sent` and `got` different MD5s, `wget` completing (no stall: the swap kept TCP's checksum and nothing was dropped); the DUT-to-peer stream, the stimulus check (the peer's 7,087 frames of 111 to 214 bytes, the DUT's 7,087), every ping and ICMP content check, the checksum-error count, bring-up, runts, rmmod, the kernel log and the trace rules PASS. The header contingency did not arise |
| d26 small-frame transmit words swapped | `c2-d26-frame-sizes-1..3` | "1 MiB over HTTP in small frames DUT to peer arrives intact" only | **as declared, 3 of 3**: `sent` and `got` different, `wget` completing; the peer-to-DUT stream, the stimulus check and everything else PASS. F2 resolved: with an MSS of 148 every skb of the stream is inside the defect's conditions |

## Qualification

For each row the reference passed `frame-sizes` on the same harness five times
(`c2-ref-frame-sizes-1..5`), and the failing check is the claim's own and the only
failure in the run.

| Claim | Result | Defect → runs | What failed, and why it is the claim's failure |
| --- | --- | --- | --- |
| Q28 receive content | **qualified** | d25 → `c2-d25-frame-sizes-1..3` | The peer-to-DUT stream check failed on the MD5 of the bytes the DUT's stack delivered, after 7,087 frames of at most 214 bytes had passed every checksum and `wget` had received the whole body: the corruption FC-1 could not see (a checksum-preserving change in what the DUT receives), caught by the only witness there is for it. Nothing else failed, so the transmit path, the ICMP paths and the stimulus were intact |
| Q28 transmit content | **qualified** | d26 → `c2-d26-frame-sizes-1..3` | The DUT-to-peer stream check failed on the peer's MD5 after the peer's stack had accepted every segment (the checksum was computed after the swap or preserved by it); nothing else failed, so the receive path and the stimulus were intact. Whether the reference segmented the stream itself or handed TSO skbs to the model is not observed; the defect is written for both shapes |

**Candidate results.** On the `c2` harness the candidate passes `frame-sizes` 5 of 5
with both stream checks and the stimulus check, so Q28 is qualified evidence about the
candidate within the scope above: its small-frame receive and transmit paths deliver a
1 MiB stream in 214-byte frames with its content intact, MD5-exact, which the ICMP checks
of FC-1 could not show for a checksum-preserving corruption. The nine other scenarios'
results for the candidate are `c1`'s, 18 of 18 on `da4c9407…`.

**Coverage after this unit.** 27 of 28 claims qualified (L02d3: 22, with Q15 in L02f2b;
QF-1: Q24, Q25, Q26; FC-1: Q27; here: Q28), each with its stated scope; Q18 unqualified,
`unobservable` ([QF-1](QF-1.md)).

## Acceptance (against the brief)

| Criterion | Result |
| --- | --- |
| A stimulus whose received payload the DUT verifies end to end, so a checksum-preserving corruption is detected | Met: d25 (a word swap in the copybreak copy, invisible to every checksum) fails the peer-to-DUT stream check 3 of 3 and nothing else; d26 the same on transmit |
| Smallest addition that works, justified | No guest-image change: busybox's `httpd`, `wget`, `md5sum`, `dd`, `ip link set … mtu` and one sysctl write on the peer, one scenario step and one capture check (above) |
| Check names stable; new checks and a claim, with the convention said | Every existing name unchanged (`ring-wrap`'s strings held by a test; `c1`'s 828 checks in the nine other scenarios, 0 failed); Q28 a new claim, with the reasons above. The two MTU checks were renamed between `c1` and `c2` to say what they now do (F1) |
| Harness tests for the changed surface | 12 new tests, 70 pass (2 changed for `c2`'s strings) |
| Planted defects for receive and transmit, built; counts and expected outcomes declared before any run | d25 and d26 built (0 warnings); `c1` declared at `067d33f` before its launch, `c2` at `ad48dfa` (rebased: `24e7c35`) before its launch; `c1` not as declared and kept (F1, F2), `c2` as declared |
| Reference and candidate on the declared repetitions; whatever else the change touches rerun | The acceptance set ×2 each on the `c1` harness (36 runs, 828 checks, 0 failed, the nine other scenarios) and `frame-sizes` ×5 each on the `c2` harness, every check; the `c2` diff confined to the streams' two peer commands and their check names |
| Every failure kept and attributed; no run repeated | 68 runs in two declared rounds, all kept; `c1`'s 16 stimulus failures and d26's 1 of 3 attributed to F1 |

## Findings

| ID | Sev | Finding | Resolution |
| --- | --- | --- | --- |
| F1 | medium | **The premise missed the kernel's advertised-MSS floor.** Lowering the peer's MTU to 200 bounded its own sends but the peer advertised an MSS of 256, not 160: `ipv4_default_advmss` never goes under `route.min_adv_mss` (default 256). The DUT sent its stream in 310-byte frames, the stimulus check failed in all 16 `frame-sizes` runs of `c1` (on the DUT-to-peer half only), and no `frame-sizes` run of `c1` is Q28 evidence. A check-design error in this unit, not a driver finding: both drivers delivered both streams intact | The peer's floor is lowered to 160 with the MTU and restored with it (harness `a1735b9f…`, round `c2`); the check names say so. `c1` is kept as recorded |
| F2 | low | **d26 caught in 1 of 3**, because F1 kept the DUT's stream outside the defect's conditions (skbs of 204 to 256 bytes, or GSO with `gso_size` at most 200): the only frames inside were 210-byte partial segments, present in run 1 only | No change to d26: with an MSS of 148 every skb of the stream is inside its conditions. Expected 3 of 3 in `c2` |

## Review

Pending (one independent reviewer reading the diff and the run artifacts, after the runs).

## Measures

- Operator time: about 09:10 to 10:34 on 2026-09-26 (Pacific) before the review, one
  session interrupted twice for the KVM slot; see the notebook. Model cost not measured.
- Host time: round `c1` (52 runs, 8 at a time) 1 minute 45 seconds; round `c2` (16 runs)
  34 seconds; the two defect builds about 20 s each; the offline premise checks about a
  minute.
- Human effort: one launch (round `c2`, after the safety check refused the implementer's).

## Open limitations

- One corruption shape per direction (two adjacent words swapped at one offset); a
  compensating two-byte change or a swap elsewhere in the frame is not planted.
  Qualification is defect-specific, as in L02d3.
- The streams' frames are at most 214 bytes; the copybreak boundary itself (252 bytes on
  the wire, 256 with the FCS) and frames between are not exercised, and a driver whose
  small-frame path starts elsewhere is exercised at 214 bytes only.
- The corruption must survive to the application to be seen: a checksum-preserving
  corruption of a TCP header field (a port, a sequence number) is seen as a lost or
  stalled transfer, not attributed.
- The transmit half rests on the wire frames and the peer's MD5; whether the reference's
  driver or the model segmented the DUT's stream is not observed, and under d26 a GSO skb
  has only its first segment's words swapped, so how many of the 7,087 frames the defect
  changed is not known (at least one per run, enough for the MD5).
- The stimulus is two settings on the peer's kernel (its MTU and its advertised-MSS
  floor); `c1` showed the check fails safe when a setting does not do what was assumed,
  and the stimulus check is what makes that visible. The candidate's stream leaves in a
  different mix of partial segments from the reference's, not examined further.
- The reference and the candidate were run once on the `c1` harness for the nine other
  scenarios and on the `c2` harness for `frame-sizes` only, on the diff argument stated
  in the `c2` declaration.
- `ring-wrap`'s Q09 stays qualified only as a stalled transfer; the same defect shape at
  frames over 1,000 bytes would qualify it for content too, a possible follow-on.
- Subagent transcripts are recorded by path in the run's ledger; those paths are temporary.
