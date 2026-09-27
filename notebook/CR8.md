<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# CR8 — one live item through a revision (spec revision 9)

Milestone CR8 of the [plan](../IMPLEMENTATION-PLAN.md#cr8--one-live-item-through-a-revision-conditional),
run on the user's decision (2026-09-26/27) to make revision 9 for CR6b's twelve R findings, the
E and W items bound for this revision and the CR6a TNCRS correction. Terms: a **reading** is
one fresh verifier's pass over a set of spec claims with a verdict per claim; a **round** is
one such reading of the current working copy; **R/E/W** are the continuous-review item classes
(changes what a driver must do / evidence / wording). See the [glossary](../GLOSSARY.md) and
the [evidence](../evidence/CR8.md).

## 2026-09-27T07:22-07:00 — opening: one revision carries every queued spec item
Start: branch `driver-porting/cr8` from `origin/main` at `ae57034`, own worktree, clean. The
sweep before any change: not sufficient; twelve open R items (CR6b's), S4 revisions 3 to 6 at
1/2, S5 unmet. The user's scope names the R items, the two CR6b aggregates and the CR6a fix;
the design says W items wait for "the next revision made for another reason", which this is,
so SR-8-1, SR-8-3 and A-RR-1 ride too (each touches a passage this revision edits anyway).
CF-2-AR-10 does not: an `[emulated]` entry needs an extract item built from CF-2's traces and a
reading of its own, which is more than riding along.

## 2026-09-27T07:30-07:00 — five of the twelve R fixes needed a choice CR6b's table left open
CR6b's table gave two fixes for RLEC and MTU and a direction, not a text, for PIF, the probe
ownership model and `ndo_stop`. Taken: RLEC alone (the adjudicator's recommendation); the driver
filters PIF packets (Table 3-2 says software "must examine" them); one unmanaged ownership
model; `max_mtu` set explicitly. For `ndo_stop` the table's fix ("mask again after
`napi_disable()`") is not enough on the kernel's own documentation: napi.rst says
`napi_disable()` waits for a poll to give up the instance, not to return, and the documented
poll unmasks after `napi_complete_done()`, so a late unmask can still follow the second mask.
The draft uses a mask lock and a stopping flag the poll checks before it unmasks. These choices
go to the user with the round-1 handover.

## 2026-09-27T07:38-07:00 — the leak scan now finds four kernel names, and that is expected
Revision 8 scans clean. The draft shares four lowercase identifiers with the reference driver:
a delayed-work cancel, a multicast-address test, the maximum-MTU field and the irq-saving
spinlock call. Each is a Linux interface the draft cites from `include/` in HALF 2, the class
SR-8 and CR6a judged in their records; the L02c whitelist lacks them only because revision 3
never named them. Kept the L02c whitelist unchanged, as SR-8 did, and recorded the judgment;
the readers see the report.

## 2026-09-27T07:49-07:00 — an authoring pre-check before the first round, because rounds are capped
With three rounds at most and fixes after round two limited to deleting or narrowing, a 47-hunk
revision cannot afford a round spent on the author's own slips. A fresh Claude reviewer read
every hunk against the manual text and the kernel's `include/` and `Documentation/` first (not a
verification round; no reader sees it). It found one error (a delayed link work canceled with
the plain-work cancel) and two races the draft still left: the link task could turn the
carrier back on after `ndo_stop` turned it off, and a shared-line interrupt before the reset
could read ICR inside R6's 1 µs. Both came from placing new text next to revision 8's old
order without re-deriving the whole sequence; `ndo_open` now requests the IRQ after §5.7.

## 2026-09-27T08:01-07:00 — round 1: the reader judged all four reason clauses over the wall
Round 1 (Codex `gpt-6-astra`, 8.4 minutes): 365 verdicts, 17 FAIL, 1 GAP. It judged all four
`[source-observed]` reason clauses to carry the source driver's reasoning, so under the user's
decision each lost its reason and kept only what was observed. The substantive finds were in
the new `ndo_stop`: a poll stalled past `napi_complete_done()` could come back during the next
open's reset after the flag was cleared, and the transmit-timeout work, which needs RTNL, cannot
be canceled synchronously from `ndo_stop`, which holds it. Both fixed by where things happen,
not by new machinery: the flag is cleared just before I2, and remove() cancels the timeout work
after `unregister_netdev()`. One FAIL was half wrong: §14.4 states the RDTR sentence twice,
once for every part and once for two other families; X9 now says so.

## 2026-09-27T08:18-07:00 — round 2: two concurrency gaps a deletion can only expose
Round 2 (14.4 minutes): 306 verdicts, 2 FAIL, clean-room PASS with all four reason clauses
cleared. Both FAILs were in the recovery and shutdown protocol HALF 2 now spells out: a poll
tail that stalls across a close and reopen can still unmask during the new open's poll, and the
transmit-timeout recovery does not keep a transmit from running while it resets. Neither can be
fixed by deleting words, and after round two nothing else is allowed, so the claims that
overstated them were deleted and the mechanisms go to the user. The lesson is the pre-check's
again: once a spec starts naming a concurrency protocol, every interleaving it does not name
becomes a finding.

## 2026-09-27T08:45-07:00 — round 3 and landing: the cap leaves the landed bytes unread
Round 3 (13.9 minutes): 343 verdicts, 2 FAIL, both wording (a quotation that changed the
manual's capitalization; "§8 alone" in the attestation, no longer true once §4.7 cites the
kernel). Deleting the quotation marks and "alone" fixed them, and because the §12.3 change was
not in the header's list, the header's "every changed passage named" went too: a deletion is
the only honest fix left once the claim of completeness is false. The index had to say what
that means: all three rounds are draft readings, superseded, and revision 9 has no reading of
its landed bytes, so S4 counts it 0/2 and the sweep queues the second reading. The two round-2
mechanisms became R items for the user with options, and every revision-8 reading went stale,
which is also what stales 27 qualifications: revision 9 touched a section almost every claim
cites.
