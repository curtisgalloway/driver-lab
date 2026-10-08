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
