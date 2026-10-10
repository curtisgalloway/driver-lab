<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# SF2-7b — Reviews and the HTML generated sections

**Terms:** a payload is a fact's structured finding, correspondence pair, or coverage record;
a pair maps implementation and reference source anchors; a sub-key is a supported register
field or sequence step's separate verdict key; a mutation deliberately breaks a guard to show
that an assertion can detect it. See the [glossary](../GLOSSARY.md).
Plan: [SF2-7](../docs/SPEC-FORMAT-V2-PLAN.md#sf2-7--peripheral-specs-reviews-and-facts-files-in-format-2).
Run: `sf2-7b-20261009-01`. Implementation report and command results belong in the private
run ledger; the orchestrator owns the independent reviews and evidence close-out.

## 2026-10-09T22:18:09-07:00 — Implementation and mutation qualification

- Review judgments live in `data.finding.assessment`, distinct from a verifier's verdict.
  The widget finding keeps the design's wording and citations; its implementation side is
  illustrative. Missing findings require implementation search evidence, and correspondence
  pairs check each repository's implementation or reference role.
- Settlement documents and pair anchors now use the ordinary citation, license and freshness
  traversal. Pair paths point at their actual YAML lists, which lets drift rewrite only the
  selected side. A local source fixture verifies both resolution and that rewrite.
- D16 introduces no new review sub-keys: finding, pair and coverage data stay in the fact's
  basis. Supported register fields and sequence steps retain SF2-7a's independent bases.
- Both views use the same field projections for generated sections. The HTML view also shows
  nested payload support, requirements, notes and verdicts when the parent has a claim.
  Generated tables and lists use fixed elements and escaped literal values; author text cannot
  contribute an attribute or a badge.
- The first mutation runs could not qualify: their scratch copies omitted the legacy Markdown
  parser that the newer CLI imports through migration. Both runners now copy that dependency.
  A later run exposed a test indexing a missing pair before asserting its length, a settlement
  assertion that matched another fact, and a redundant resolution type predicate. The tests
  now isolate the intended payload, and the resolution status branches enforce its shape.
- The source-resolution fixture initially shared nested Python objects, which YAML emitted as
  forbidden aliases. Independent deep copies preserve the strict loader's one-record spelling.

## 2026-10-09T22:22:04-07:00 — Final checks and patch handoff

- The source-resolution test now asserts the pair's YAML paths before calling drift. A broken
  path therefore fails an assertion before it can cause an internal CLI error during mutation.
- All requested suites and both mutation runners completed successfully. Mutation failures
  are assertions, with no unittest errors or internal CLI errors counted as qualification.
  Command results and scratch artifact locations are in the implementer's handoff report.
- Both safety scans used their existing scan functions over the regular exported files because
  this tree has no Git index. The authored changes are regular text files suitable for the patch
  collector; independent review and milestone close-out remain with the orchestrator.
