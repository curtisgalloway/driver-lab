<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# CR-G — acceptance of the continuous-review layer

Milestone CR-G of the [plan](../IMPLEMENTATION-PLAN.md#cr-g--layer-acceptance): one acceptance
table, C1–C8 against evidence. Terms: the **layer** is what CR1–CR8 built (index, claim map,
registry, manifest, sweep, contract check); the **sweep** is its one local command. See the
[glossary](../GLOSSARY.md) and the [evidence](../evidence/CR-G.md).

## 2026-09-27T10:05-07:00 — the sweep code has not changed since CR6
Branch `driver-porting/cr-g` from `origin/main` at `e401e4f`. CR7 and CR8 touched only tests,
fixtures and data, so "the same stale set and stopping state as after CR6" reduces to a data
question. Ran the sweep on CR6's merged tree in a scratch worktree: it reproduces CR6b's
recorded state exactly (96 stale, 15 tier-1 units). The entry-by-entry diff against today's
sweep has 48 newly stale entries and no entry that went back to current; every one traces to
revision 9's header or to CR8's index entries.

## 2026-09-27T10:20-07:00 — the no-key default had no end-to-end test
The loader's default is tested, and the CLI is tested with a config key, but nothing ran the
sweep command with no key and compared the queue's models with the reference manifest. The
operator's own config has no key, so the live sweep showed it; added one small test so it stays
shown. The rename check needed no test: two existing tests cover it, and a live probe on a
scratch copy (one check renamed in the real harness) fails the checker on Q01.

## 2026-09-27T10:30-07:00 — C6's last clause cannot be met literally yet
The design says e1000 "reaches sufficient, or its blockers are those in the worked example".
Neither holds: the worked example predicted one second reading; the sweep lists 28 claims under
S2, three S3 items and six revisions under S4. CR4's and CR6's criteria, in the approved plan,
accept explained differences and new blockers with class and disposition, and every difference
is explained. Recorded the clause as met in the plan's form and put the literal reading to the
user rather than deciding it here.

## 2026-09-27T10:40-07:00 — decision records make the tier-2 units ready
Recording the user's option (a) on CR8's two R items as replacement entries with `who: user`
turns their requirement-change units from `awaiting decision` to ready, as the guard intends.
They sort after all tier-1 work, so the sweep's first batch is three requalifications. Those
would be staled again by revision 10, which changes §10.3; the user's order (revision 10 first)
is the one to follow, and the evidence says so.

## 2026-09-27T11:05-07:00 — review: the acceptance claim outran the open C6 question
The reviewer's two main points were about wording, not numbers (every figure checked): the
records said "accepted" while leaving C6's literal clause to the user, and the plan criteria
cited for C6 each covered their own moment, not CR8's blockers. Now "met subject to the user's
reading". Its third point was new: `stopping.py` holds every reading unit while any revision
reports "limit reached", and revision 9 always will, so the second reading after revision 10
will not come out of the queue on its own. Recorded for the next unit; no code here.
