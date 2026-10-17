<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Atlas connection views: design

## Terms

- Topology: devices/resources and their documented connections.
- Provider/consumer: the resource service roles; an interrupt controller provides interrupt handling to a device even though the signal travels toward the controller.
- Port: a named resource input or output on a hardware node.
- Configuration: an explicitly named set of documented board choices, not detected live state.
- Basis hash: the existing fingerprint of a fact, its evidence, and its referenced dependencies.
- Specifier cells: ordered 32-bit values selecting a provider resource according to its binding.

See the [glossary](../GLOSSARY.md). Design revision: 2026-10-16. The user delegated design-choice approval to Gemini 4 Argon, which confirmed sections A-L with no remaining objections; the user then selected GPT-6.1 Sol for implementation. The private review is retained under run ID `atlas-design-consult`. This document defines intended behavior, not a claim of implemented views or populated board data. Delivery status is in the [implementation plan](ATLAS-CONNECTIONS-PLAN.md).


## A. Views

Existing offline HTML atlas remains the deliverable. Keep Graph as spec relations; add Connections with Clocks, Interrupts, Power/reset, and Device dependencies modes. DMA/address translation and pins/wiring remain later work.

## B. Payload placement

Add section topology to board/soc/chip and compatible overlays, allowing only four new discriminated fact payloads there: topologyNode, connection, topologyConfiguration, selection. Do not generally admit register/peripheral payloads into these spec kinds. Each fact retains existing evidence, TODO, scope, verdict and license rules. Preserve old schemas' accepted documents and unchanged legacy facts' basis hashes.

## C. Nodes and ports

topologyNode has kind, optional instance factRef (must target a real instance), and named ports. It can be standalone for oscillators, rails and internal mux/gate/divider/PLL blocks. No fabricated reg/irq/ip. A connection endpoint always targets a topologyNode fact, with port as separate field. Two instances of the same IP remain distinct; no dedup by display name/IP. A node may describe one sub-block of an instance, so multiple nodes can share instance ownership. Ports use provider/consumer resource roles plus kind, unique name, and optional provider specifier-cell count. Known count k requires exactly k cells; for k=0 omission or [] is allowed. Unknown count permits omitted cells or an array of unsigned 32-bit integers, and is labeled unknown. Consumer endpoints never carry cells. Endpoint roles and both port kinds must match the connection. Cells are bounded unsigned 32-bit integers; arity is never guessed. A provider may offer multiple clock/reset/domain IDs identified by cells; retain ordered cells verbatim. Existing quantity payload vocabulary is reused by references for known rates/voltages; no new floating-point unit conventions.

## D. Connections

connection has kind clock/interrupt/power/reset, provider {node, port, cells?}, consumer {node, port}, and mode fixed/selectable. For interrupts provider means controller and consumer means interrupting device: consistent resource semantics, but Interrupts UI draws physical signal arrows from device to controller. Controller cascade represented by a controller node consuming an upstream interrupt service. Legend states this. Attributes are kind-discriminated, preserve raw specifiers; decoded interrupt type/number/trigger appear only when explicitly authored with evidence, using IRQ_TYPE vocabulary where applicable. No GIC-specific universal encoding. No automatic live rate calculation.

## E. Slots and fan-out

Consumer slot key is canonical (consumer node factRef, consumer port); port has one kind. First increment supports single-provider slots: either one fixed connection or one-or-more selectable candidates, never both. Shared provider fan-out is permitted, including devices sharing a controller line. More complex fan-in uses explicit intermediate nodes with distinct input ports; do not invent a hardware combiner without evidence, show a gap instead. A mux's selectable parent slot is distinct from its physical output. A selected route is not the same as an enabled clock or released reset.

## F. Configurations and selections

topologyConfiguration has board spec ID (must resolve to kind board) and a human-readable name. The configuration fact and its selection facts must belong to that board spec or overlays of that board. Rendering a standalone SoC/chip offers no board configurations; selectable slots remain unknown. Its full fact reference is the configuration identity. selection has configuration factRef and selects connection factRef. At most one selected candidate per slot per configuration; identical duplicate claims retain both provenance records, differing selected candidates are a conflict/error with no winner. Fixed connections cannot be selected. Configurations do not inherit from each other in v1. Existing scope remains explanatory, not machine-evaluated. Selecting a configuration means viewing its documented claims, not detecting actual board/live state. Claims about firmware settings carry evidence and conditions; no default claim is promoted to live observation. With no selection for a slot, it remains unknown; incomplete configs allowed. Conflicts cannot be bypassed by merely adding conflicts[]; existing resolution semantics must be satisfied, and the UI must never silently choose.

## G. References and freshness

All topology-node instance refs, endpoints, quantity refs, configuration/selection refs enter existing reference resolution, transitive license/trust gates, and full-record freshness dependencies. Extend speccheck.references() for the new payloads and reuse records.Freshness.edges()/compute(), which ALREADY fold referenced basis digests into fact-v1 and handle cycles; do not add a second digest map or change the hash format. Verification files remain .verify.yaml, not .verify.md. References in old records are unchanged. Selection depends on selected connection and config; connection depends on node/port contracts. Circular hardware graphs do not automatically form circular evidence dependencies: node facts do not enumerate/ref their connections. Checker still handles reference cycles safely. No selective-hash optimization in v1.

## H. Traversal and isolation

Define a topology seed set separately from the existing spec graph selection: target spec plus downward parts closure, and instance IP/peripheral targets plus peripheral specs whose describes names that closure. Overlay facts belong to their overlays target; overlays do not use describes. Admit topology payloads only in permitted board/soc/chip specs and their overlays. For a board-focused atlas, admit board-authored connection/node facts only from that focus board; reject cross-board hardware endpoints as inapplicable to that view. For a non-board focus, admit no board-authored topology facts or configurations. Selectable configurations and their selection records must target the focus board. From seeded nodes, walk connections owned by already admitted specs in either direction; explicit endpoint references can admit a non-board SoC/chip spec and continue the walk through its connections. Never scan reverse edges from every loaded spec to grow the owner set: a loaded unrelated chip pointing at a shared SoC does not thereby join. This rule permits multi-hop companion topology when an admitted spec explicitly references the companion, while preventing unrelated-board or unrelated-chip claims leaking through shared endpoints. Retain disconnected nodes owned by admitted specs; maintain a deterministic visited set. Board-specific facts must be owned by their board, not scoped prose in a generic SoC overlay. Do not treat descriptive scope as an applicability filter. No implicit fetching. A missing root/reference fails check; a valid context reference excluded from rendering by existing --merged behavior becomes an explicit rendering boundary. Do not invent --max-license. Source topology selection does not promote unsafe/unrendered author fields into HTML; follow existing rendering safety gates.

## I. Legacy compatibility

Existing irq/clocks stay unchanged and visible. Display legacy data separately as unlinked information; do not infer provider, port names or matching identity. No hard legacy contradiction check unless a future explicit correspondence exists. Display both when typed topology coexists, labeled as separate claims; explain equivalence has not been checked. This avoids both silent overwrite and false claim of consistency.

## J. Source boundaries and incomplete topology

Native curated topology facts only where D31 justifies them (source cannot be pointed to, useful summaries, or information absent from canonical accessible source). Cite exact sources with current support shapes. Do not duplicate complete upstream DTS topology. Keep upstream-only areas as linked source references with a visible not-extracted boundary. The mechanical indicator is an optional topologyNode.incompleteKinds list of clock/interrupt/power/reset kinds, requiring an existing document TODO explaining the omission; that TODO uses normal evidence/source locators and is included in worklists. It does not claim all omitted items are enumerated. Legacy clocks/irq without an explicit correspondence remain separately labeled unlinked, never automatically classified as an identified missing port. Provider ports with unknown cell arity get an unknown-arity indicator. Do not parse TODO prose to determine topology kinds. A graph with no facts is not a statement of no hardware connections. The incompleteKinds field applies even when some connections of that kind are present. No DTS parser/compiler/adapter or build-script execution in v1. Therefore the views may be partial even for well-documented boards; this is a declared limitation, not completion. A normalized Python graph-building layer isolates future source adapters. Any future imported edges must carry provenance/license/freshness.

## K. Interaction and rendering

Deterministic layered SVG layout, true semantic directions, cycle-safe clustering/layout without changing hardware arrows, companion keyboard-accessible node/edge list, search, pan/zoom, fit and per-device upstream/downstream highlighting. Combined view labels resource relations and never claims initialization order. Edge styles distinguish fixed, selected, documented alternative, unknown selection and contested/stale evidence, with text labels beyond color. Inspector links each connection and selection to exact originating facts/evidence/verdict/TODO. All author labels inert; existing checked author renderer is the only source of trusted rendered prose. No remote assets.

## L. Acceptance

Acceptance: schema rejects wrong payload placement, bad target types/ports/cells, conflicting selections, fixed/selectable slot mixing, and license/trust failures; old specs/hash regression tests pass. Tests cover shared clock/reset, controller cascade and shared IRQ line, multiple instances of one IP, mux selection/unknown, distinct board configurations with identical display names, overlays and different roots, endpoint change staling connection and selection, unchanged reverse dependencies, cross-spec multi-hop reachability, unrelated-board and unrelated-chip exclusion, a deliberately missing non-board reverse join, explicit incompleteKinds markers even with some populated edges, cycle handling, quantity references, legacy coexistence without invented matching, unsafe labels, browser keyboard/mode/filter/inspector interaction, deterministic output. At least a synthetic complete fixture plus a curated sourced partial example demonstrates data-to-browser behavior. No claims of populated full real-board topology unless authoring and verification actually complete.
