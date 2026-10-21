<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Atlas connection views: implementation plan

## Terms

- **Topology**: documented hardware resources and the connections between them.
- **Configuration**: named documented board choices, not detected live state.
- **Checkpoint**: a tested, reviewed local commit ending one unit of work.

See the [glossary](../../docs/GLOSSARY.md) and the [design](../../docs/ATLAS-CONNECTIONS-DESIGN.md),
revision 2026-10-16. Design sections A-L are the requirement labels below.

## Delivery conventions

The user delegated design-choice approval to Gemini 4 Argon, which confirmed the
complete design, then selected GPT-6.1 Sol to implement it. Argon remains the consultant
for material design changes. Fresh implementers run only through
`utilities/codex-implement.py`; the orchestrator applies their patch and runs the main
checkout's patch gate before executing patched code. GPT-6.1 Sol's actual launch model
must be checked in the wrapper's output, since the wrapper does not pin a model.

One unit per session, one topic branch per unit, fetched from `origin/main`.
AT1 branch: `feat/atlas-at1-topology`. Later branches use `feat/atlas-atN-<topic>`.
Checkpoint prefix: `driver-porting: ATN —`. No push, PR, or merge is authorized by this
plan; each follows the repository's explicit user instructions.

An independent reviewer reads each unit's diff and actual check artifacts before its
checkpoint, saves a report in the private run store, and verifies fixes. Use broader
`review-swarm` review if shared execution machinery or access policies change, or the
reviewer requests it. Existing license/trust rules are reused, not relaxed. Review of
any newly authored real hardware claims additionally uses `spec-verifier`.

These are tooling units: the private ledger records commands, artifacts, failed
attempts, decisions, and reviewer references. The prepared PR body holds results and
review resolutions. Per repository instructions, no notebook chapter or evidence file
is added. This supersedes the planning skill's generic notebook convention. No driver
campaign is being run; the frozen evaluation archive is not part of this work.

## Status and coverage

| Unit | Outcome | Design | Dependencies | Status |
| --- | --- | --- | --- | --- |
| AT1 | Topology fact contract, references and semantic validation | B-G, I-J, validation parts of H/L | Approved design | complete |
| AT2 | Deterministic atlas graph data and complete text readback | C-J, data parts of L | AT1 | pending |
| AT3 | Connections tab and accessible graph interaction | A, K, interaction parts of L | AT2 | pending |
| AT4 | Sourced partial example and end-to-end acceptance | A-L | AT3 | pending |

## AT1 — Topology facts that can be checked

**Outcome:** `validate` and `check` understand typed hardware nodes, connections,
configurations and selections, with evidence, trust, license and freshness preserved.
The atlas graph UI is not delivered by this unit.

**Scope:** schema, focused topology checker, reference enumeration, context-safe
conflict checking, tests and format contract documentation. Existing render commands
continue to work and show fact claims; complete typed readback arrives in AT2.

**Steps:**

1. Add only the four approved payloads and their fields to board/SoC/chip topology
   facts and compatible overlays, preserving existing kind restrictions.
2. Add explicit endpoint/reference checks and reuse existing dependency hashing.
3. Validate consumer slots and selections within admitted board contexts, avoiding
   a global collision between independent boards that share a chip.
4. Document the actual field contract and add synthetic fixtures and regression tests.

**Acceptance:**

- All four resource kinds and all four fact payloads validate in their intended kinds;
  other payload/kind combinations remain rejected.
- Wrong reference types, ports, roles, resource kinds, cell counts/ranges, configuration
  ownership, fixed/selectable mixing, and competing choices fail with useful diagnostics.
- Shared IRQ/clock/reset providers work. Separate boards sharing a SoC do not conflict.
  An unrelated chip's reverse reference does not make it part of a board's topology.
- Existing root layer, license, trust and record freshness checks apply transitively.
  Editing a node changes dependent connection/selection bases; old untouched bases
  stay identical, and editing a connection does not change its endpoint node's basis.
- Existing specs and render commands remain usable, with legacy strings untouched.

**Verification:** new `skills/spec-format/tests/test_topology.py` plus the full
spec-format suite through the patch gate. The gate also runs the utilities suite,
privacy and open-side scans. Reviewer inspects fixture semantics and failure results,
not merely test counts. This is a bounded format/checker unit; if context resolution
requires a broader architecture change, stop and consult Argon before expanding it.

## AT2 — Graph data and text readback

**Outcome:** the atlas exports a deterministic hardware graph for a selected board,
and Markdown/HTML renderers expose the full typed payload so no authored value is hidden.

**Steps:** build a normalized graph layer over checked records; implement design H's
owner traversal separately from spec-link selection; export nodes, edges, configuration
choices, verdicts, incomplete kinds, unknown arity and legacy unlinked claims; render all
new fields using existing safe author-text handling; update CLI/format documentation.

**Acceptance:** multi-hop companion topology joins only through explicit admitted-owner
references; unrelated boards/chips stay out; standalone SoC views have no board configs;
`--merged` boundaries remain distinct from missing-reference check errors. Exact origin
facts and all duplicate selection provenance survive export. No source fetching or
live-state inference occurs. Unknown inputs do not become fabricated edges. Stable input
produces stable output, and every typed field has text readback.

**Verification:** focused graph/export and renderer tests, complete spec-format suite,
patch gate, independent diff/artifact review. Include cross-root overlays, excluded context
roots, malformed labels and reference cycles. Keep browser UI out of this unit.

## AT3 — Connections interaction

**Outcome:** the existing offline HTML atlas gains Clocks, Interrupts, Power/reset and
Device dependencies modes, with usable keyboard and pointer navigation.

**Steps:** add mode/configuration controls; deterministic layered SVG graph with cycle
handling; searchable node/edge list; fit/pan/zoom and per-device dependency highlighting;
connect selections to the existing fact inspector; provide text legends and empty states.

**Acceptance:** interrupt arrows show device-to-controller signal flow; other modes
label their resource direction. Fixed routes, selected routes, alternatives, unknown
selection, incomplete topology, stale and contested evidence remain distinguishable
without color alone. Keyboard users can choose modes/configurations and open every
node/edge's evidence. Switching mode/configuration updates graph, list and inspector
consistently. The file opens offline and performs no asset/network requests. No arbitrary
author string reaches an HTML parsing sink.

**Verification:** automated browser tests against generated fixtures, including keyboard
navigation, configuration changes, inspector provenance, cycle handling and adversarial
labels. Inspect generated pages at narrow and desktop sizes. Run spec-format suite and
patch gate. Discover an installed browser runner before choosing a new dependency;
any pinned dependency/CI change requires the repository's separate gate-input review.

## AT4 — Complete acceptance and sourced example

**Outcome:** one synthetic complete example and one curated sourced partial example
exercise the entire data-to-browser path, with their limitations visible.

**Steps:** choose an already available board/source set, author only a justified useful
summary under D31, mark omitted topology explicitly, verify real claims independently,
render and inspect all modes, update user guide and final status.

**Acceptance:** every A-L requirement has test or review evidence. The example makes no
claim to a complete board graph or live state. Native facts do not duplicate an entire
canonical Devicetree. DMA, pin routing, automatic rate propagation, boot-order synthesis,
and source adapters remain explicitly out of scope. No unresolved blocking review finding
or required skipped check is recorded as complete.

**Verification:** run the full checks list in [AGENTS.md](../../AGENTS.md), browser acceptance,
privacy/open-side checks, independent implementation review, and `spec-verifier` for
changed real hardware claims. Hardware measurements are not implied by static rendering.

## Next session

AT1 passed 1,011 spec-format tests (three existing skips), 88 utility tests, and the
trusted privacy/open-side gate. Independent review verified the fix that invalidates
every competing selection, including duplicate claims, regardless of fact order.
The complete suites ran on Linux; four baseline macOS filesystem-test failures were
reproduced on the unchanged base. The two new Python files passed formatting and lint.

Stop for inspection after the AT1 local checkpoint, per the one-unit rule. AT2 begins
from the integrated AT1 after explicit push and merge instructions; do not silently
start a branch missing the topology contract.
Private run ID for this unit: `atlas-at1`. Design review run ID: `atlas-design-consult`.
