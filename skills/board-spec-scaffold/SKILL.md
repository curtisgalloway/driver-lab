---
name: board-spec-scaffold
description: >-
  Author format 2 YAML board, SoC, companion-chip, IP or overlay specs and root markers,
  optionally with a thin board-expert stub or vendor-tools skill. Use when asked to scaffold,
  create or generate a board spec or bring-up reference, or when board-expert finds no spec.
  Research returns fact records; templates include documents-only roots and overlays.
---

<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Board-spec scaffold

## Terms

- **Fact record**: one stable-id claim with structured support, or an explicit gap with a TODO.
- **Root**: a directory of specs whose marker declares layer and source-license policy.
- **Composition**: a board's shared SoC/chip parts and their IP-block instances.
- **Overlay**: added facts with their own origin, without rewriting a base fact.
- **Stub**: a short skill naming a spec and handing questions to board-expert.

See the [glossary](../../GLOSSARY.md). Read [spec-format](../spec-format/SKILL.md) before writing;
its schemas define shapes and its text is the shared contract. QUESTIONS in board-expert is
the interview checklist. Authoring and reading use format 2 only.

## Outputs and templates

| Artifact | Template / author |
| --- | --- |
| `<id>.spec.yaml`, board | [board.spec.yaml](templates/board.spec.yaml) |
| `<id>.spec.yaml`, SoC | [soc.spec.yaml](templates/soc.spec.yaml) |
| `<id>.spec.yaml`, chip | [chip.spec.yaml](templates/chip.spec.yaml) |
| `<id>.spec.yaml`, generic IP | [ip.spec.yaml](templates/ip.spec.yaml) |
| `<name>.spec.yaml`, overlay with source/DT evidence | [overlay.spec.yaml](templates/overlay.spec.yaml) |
| Overlay citing documents only | [docs-root/overlay.spec.yaml](templates/docs-root/overlay.spec.yaml) |
| Root marker | [board-specs.yaml](templates/board-specs.yaml) |
| Documents-only root marker (`accepts: []`) | [docs-root/board-specs.yaml](templates/docs-root/board-specs.yaml) |
| `<board>-expert/SKILL.md` | [stub-SKILL.md](templates/stub-SKILL.md) |
| `<vendor>-board-tools/SKILL.md` | [vendor-board-tools-SKILL.md](templates/vendor-board-tools-SKILL.md) |
| `<root>/resources/<name>.verify.yaml`, one per spec file, overlays included | spec-verifier writes it |

The four base templates use documents and gaps and contain no repos; use them unchanged in
shape for a documents-only root. Source-derived additions use the source overlay in a root
whose accepts list permits the actual files' licenses. The docs overlay also has no repos.
Do not add even map-only repos to documents-only templates: `check --require-license` gates
those too. An internal overlay uses the same YAML shapes in a vendor/local root, with
`access: internal` on documents and a tool's `via` naming its loaded vendor skill. Do not add
`access`/`via` to repo entries or invocation `via` to documents; those fields do not exist.

## Steps

1. **Interview** only for missing choices, in one structured batch following
   [QUESTIONS.md](../board-expert/QUESTIONS.md): identity/kinds, variants, trigger keywords,
   composition/instances, target roots/layers/licenses, public source commits, document
   authorities/proxies, cache convention, stub/vendor skill, research-filled or skeleton,
   verification now or later. Defaults: research-fill public sources and verify now. Reuse
   existing SoC/chip/IP specs rather than duplicating them. Explain Apache 2.0 as the default
   for a new code project; spec content must match its chosen repository's license.
2. **Research-fill** by spawning an expert that loads board-expert and applicable vendor skills.
   Ask for YAML fact records (`id`, `section`, `title`, `claim`, `support`, TODO as needed),
   resource entries with immutable commits/doc hashes, and supported instances/variants.
   The expert manages fetching and its cache. A skeleton request or unavailable source gets
   explicit gap records with observable TODO methods; do not fabricate a citation to fill a form.
3. **Write YAML**, replacing every template placeholder with a real value, removing irrelevant
   examples and researching or explicitly keeping gaps. Replace SPDX header placeholders with
   the copyright year/holder and the target root's declared license, including documents-only
   markers; never leave an Apache-2.0 header in a CC-BY root. Preserve stable fact ids; every
   composition id and stub id must resolve. Put evidence only in support fields. Source
   observations say what code does, hardware conclusions get their own inference. Split
   mixed read/concluded claims; quote references, locator page numbers, commits and hashes.
   A hardware-location claim using `src` needs a document class too; `DT` takes the tree's
   license and may require a more restrictive root. Cite DT source (`.dts`/`.dtsi`) at a pinned
   commit; a claim whose only source is a binary blob is a gap until decompiled text is
   published at a pin. Mark critical facts for two readers.
4. **Write the marker/stub/vendor skill** if requested. All format 2 marker policy fields are
   required, even outside a published repository. Expand any root pointers explicitly for
   commands: skill pointers are relative to the checkout or absolute; marker `roots` entries
   are relative to that marker file or absolute. YAML files start with SPDX comments;
   SKILL.md headers go after frontmatter.
   Keep private document/bench details in private overlays. Source-license notices belong
   in `notices`, not code excerpts. A stub keeps “Board expert for” and “A stub over the
   `<id>` board spec” in its description, a `spec: <id>` line in its body, and no facts.
5. **Register** a new stub where the target repository requires; inspect its current README
   and plugin metadata rather than assuming an obsolete registration script exists. Spec
   files need no separate registry: they are discovered under the chosen roots. Follow the
   target tree's review process; do not change installed agent configuration unasked.
6. **Check** with the contract's pinned environment:
   `spec.py validate <file>... --root <root>` for shape, then
   `spec.py check <new root>... --context-root <dependency root>... --require-license
   --stubs-from <skills dir>`. Include every dependency, and check any other changed roots
   as checked roots. Run `spec.py resolve <file>... --root <root> --repo NAME=CHECKOUT
   --docs-dir <documents dir>` when bytes are available. Confirm anchors ran, not merely
   exit 0; skips and unrepeatable searches remain limits. Render every relevant id using
   `spec.py render <root>... --context-root <dependency root>... --spec <id> --merged
   --with-status --format md` and inspect it. SF2-4/SF2-6 are on main; HTML rendering
   (`render --format html`) arrives later in SF2-5, not part of this milestone's commands.
7. **Verify** by following [spec-verifier's format 2 procedure](../spec-verifier/SKILL.md).
   If verification was explicitly deferred, report the spec
   as unverified and leave completion pending.
8. **Report** files produced, resolved composition, record status from `spec.py status`, gaps
   and review needs. If new stubs require an installation sync, remind the user to run it;
   do not reconfigure the harness. Follow the repo's commit/push rules.

## Filling guidance

Quick-facts are the value, not just a link collection. Cover these dimensions in separate
records with support or explicit gaps:

- **Board**: boot media/configuration, debug connector/UART routing, headers/chip ownership,
  PMIC/power and hand-off links. Closed devices also need boot-image/partition layout,
  unlock/boot policy, physical console access, revision/DTBO selection and public kernel family.
- **SoC**: addressing and worked UART translation; boot/entry EL, MMU/cache, DTB register and
  resident-memory reservations; secondary-core release/MPIDR; interrupt controller and full
  interrupt table; debug UART width/shift/baud/ready flag/pinmux; timers; clocks/power;
  GPIO/pinmux; live DTB patches. Closed firmware is named as closed; do not invent its contract.
- **Chip**: prerequisite bus/link, address-window translation, contained blocks, firmware state.
- **IP**: which standard/databook governs each interface, register organization, reset/init/
  teardown, DMA/interrupt model, public versions/configurations and errata. Instance values
  belong in SoC/chip rows. A code-only ordering is an observation or explicit inference.

Use public proxies only when they document the relevant block/revision; name that scope.
Public roots never cite documents marked confidential or NDA, whatever their availability.
Use a public proxy, a GPL overlay citing public DT or source, or a gap instead. Record
canonical and retrieval URLs separately for Arm static PDFs. Do not infer hardware state from a
shipped build whose identity is only assumed; declare the assumption and a hardware TODO.
Keep gotchas precise and attributed. A plain gap is useful; a confident wrong address stops boot.

## Quality bar

The schemas validate, composition/references/license policy check clean, source anchors resolve
or their limits are recorded, every placeholder is gone, and public files contain only public
facts. Every supported record has precise support; gaps have observable TODOs. Every file has a
record, every required verdict is current, critical facts have independent agreeing readers,
and no FAIL or unsettled ADJUDICATE remains. `spec_sha256` matching alone establishes none of
this. Suggested next work names fact ids/full references. Independent review precedes the
checkpoint; a skeleton with deferred verification is delivered as a skeleton, not a verified spec.
