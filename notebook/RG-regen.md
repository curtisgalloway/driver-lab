<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# RG-regen: spec regeneration

Chapter for the [spec-regeneration plan](../docs/SPEC-REGEN-PLAN.md). Each unit's entries record
every review finding as a row; proposed skill changes roll up in
[SPEC-REGEN-learnings](SPEC-REGEN-learnings.md).

Finding rows use these columns: reviewer (`spec-verifier` or Codex), claim, finding, accepted or
rejected (why), caught by the other reviewer (yes/no), and the skill or format rule that would
have prevented it.

### 2026-10-07 — opening

Plan approved by the user. Decisions: implementer Opus 5.5, one fresh subagent per unit; Codex
is the second reviewer after `spec-verifier`, read-only, with the verifier's record in hand;
learnings recorded per unit here and rolled up. Units renamed `RG` (not `SR`) because
`evidence/SR-7.md` and `SR-8.md` already exist from earlier work.

### 2026-10-07 — Codex needs network to find sources

Probe with `codex exec --sandbox read-only`: curl failed DNS, web fetch returned a cache miss,
and web search found `armstub8.S` only on `master`, not at `439b619`. Read-only mode has no
network switch. Staging the sources locally would have given Codex the same bytes as the
verifier, but the user wants Codex to find sources the spec did not cite, which needs network.
Decision (user): Codex runs with `--sandbox workspace-write` and network access, in a throwaway
scratch directory only; the local permission rules allow exactly that form. Re-probe: curl
fetched the file at `439b619` and read its BSD-3-Clause header.
