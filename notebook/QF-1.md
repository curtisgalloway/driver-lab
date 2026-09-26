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
