<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# QF-1 — the four unqualified claims

Follow-on of the [plan](../IMPLEMENTATION-PLAN.md) named in L02f3. Terms: a **claim** is a
check whose PASS L02f cites as evidence about the candidate; it is **qualified** when a
planted defect made it fail for the claim's reason while the reference passed; a **trace
stamp** is the whole-microsecond host time QEMU writes on a traced register access. See the
[glossary](../GLOSSARY.md) and the [evidence](../evidence/QF-1.md).

## 2026-09-26T00:10-07:00 — opening: three claims need defects, one needs an instrument reading
Goal: qualify Q24 (interface up, unload), Q25 (60/61-byte receive) and Q26 (first load and
bind) with planted defects, and find out what the trace can say about Q18 (1 µs after a
global reset). Start: branch `driver-porting/qf1` from `origin/main` at `9b8c3b7`, own
worktree, clean; harness `705694b9…` as L02f3 left it. L02d3's script and run pattern are on
this host; the defects go in a new private run with their own ledger.

## 2026-09-26T00:18-07:00 — the trace resolves less than a microsecond, so the 1 µs rule was lenient, not blind
L02d3 concluded that no defect could produce a sub-microsecond gap. Before planting one, I
measured what the trace can resolve at all: over the 40 L02f3 traces, consecutive memory-BAR
writes are stamped 0 µs apart hundreds of times per run (the MTA table loop), and a write
followed by a read is stamped 1 µs apart most often. So the instrument is not the problem;
the rule was. Stamps are whole microseconds, so a difference of 1 can be any interval under
2 µs, and the old rule (fail below 1) passed intervals it could not show to be 1 µs. QEMU
(`system/memory.c`, v10.2.0) stamps a write before the model executes it and a read after, so
a stamp difference is an upper bound on the guest's interval. The observable form of the
claim is "stamps at least 2 µs apart": that is the harness change, one constant, with tests.
L02d3's d11 was through the I/O window, whose IOADDR-then-IODATA pairs are never stamped
under 10 µs here, which is why it showed 13–34 µs; the candidate resets through the memory
BAR and reads CTRL 6–18 µs later.

## 2026-09-26T00:24-07:00 — a small-frame defect that leaves ARP alone
The trap L02d3's reviewer named: the model pads every short frame to 60 bytes before the
driver sees it, so a driver that drops 60-byte frames also drops ARP and fails everything.
The defect chosen (d21) trims the copybreak path's frames by one byte: a 60- or 61-byte
echo then arrives shorter than its IP total length and IP drops it, while ARP (28 bytes of
payload in a 60-byte frame) and the padded reply to the 42-byte ping keep their slack and
1513/1514-byte frames are above the copybreak size. Expected failures are exactly the four
60/61 ping checks and, as a consequence, the sent-sizes capture check.

## 2026-09-26T00:27-07:00 — declaration committed, 63 runs launched
Six defects built (d22's first build hit `-Werror=unused-function` for the I/O write helper
it no longer called; kept referenced behind `if (0)`). The declaration, with each defect's
expected failing checks and the consequences, is in the ledger and the evidence file,
committed at `9442e08` before the first run (00:27:30). The acceptance set (ten scenarios,
reference ×2 and candidate ×2) reruns on the changed harness in the same round, since the
trace pseudo-scenario runs in every scenario. Offline, the new rule over the 40 stored
L02f3 traces reproduces every stored trace verdict and gap list (candidate minimum 4 µs).

## 2026-09-26T00:30-07:00 — five of six defects fail as declared; the small-frame one kills ARP
Round q1 in 122 s. d17, d18, d19 and d20 each fail exactly the declared check three times,
and the acceptance set passes 40 of 40 on the changed harness. d21 fails every ping: the
model does not pad short frames (I had it from memory that it did; the L02d3 reviewer's
"ARP at 42 bytes" was the fact, and the DUT capture shows 21 of them), so the peer's 42-byte
ARP replies come through the copybreak path at 42 bytes, one byte short is 41, and ARP drops
them. A defect that must spare 42-byte frames has to key on length, not trim. d18 also
tripped the kernel-log check: the reference's own probe error path unmaps the CE4100 MDIO
base it never mapped and the kernel warns. The check caught a real error-path bug in the
reference, which is what it is for.

## 2026-09-26T00:33-07:00 — a reset write is never followed within 4 µs, and I do not know why
d22 resets through the memory BAR and reads MANC at once; the stamps say 6 to 17 µs, every
one of 24 resets. The candidate's 80 resets in the acceptance set: never under 4 µs. But
EECD-then-STATUS pairs in the same traces are stamped 1 µs apart, and QEMU's `set_ctrl` only
clears the bit. So the restated rule is right about the instrument and still cannot fail
here; Q18 stays unqualified, now labeled `unobservable`, with the numbers and the gap in the
explanation stated as such rather than guessed at.

## 2026-09-26T00:35-07:00 — d21b qualifies Q25; d21c is invisible because ping payloads are zeros
Round q2 in 24 s. d21b (drop small frames over 46 bytes) fails exactly the four 60/61-byte
pings and the sent-sizes check on the two missing replies, 3 of 3, with 42, 1513 and 1514
passing. d21c (tail shifted by one byte from byte 46) passes everything: the payload is a
4-byte timestamp at frame bytes 42–45 and zeros after, so shifting zeros is a no-op, and the
peer's capture shows every reply echoing its request byte for byte. An equivalent mutation
under this stimulus, and a gap in the suite: nothing checks the content of a small frame.
