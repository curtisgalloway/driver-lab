<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Hardware specifications: from source investigation to measured quality

**Revisions:** 2026-09-26, the [continuous
review](#continuous-review-keeping-specs-right-as-evidence-changes) section (C1–C8) added and
the evidence-loop, lifecycle §6 (now step 3), shipped/proposed and Limits sections amended; approved by the
user the same day ([evidence](evidence/DESIGN-2026-09-26.md)). 2026-09-27, the
[scope](#scope-specs-and-their-quality) section added at the user's direction. 2026-10-06,
the license split moved the sections on writing specs and drivers from source the target may
not copy to a separate repository, and this document keeps the open method (requirement
LS-R20 of the [license-split design](docs/LICENSE-SPLIT.md); [evidence/LS8.md](evidence/LS8.md)
lists every moved or reworded passage).

## Scope: specs and their quality

This project's goal is **generating hardware specs and measuring and maintaining their
quality**: board specs, anchored specs and reviews, their verification,
and the [continuous review](#continuous-review-keeping-specs-right-as-evidence-changes) that
keeps them right as evidence and models change. The deliverable is a spec someone can trust,
with a record of why.

Writing a driver for a particular target OS is **not** this project's goal. Using these specs to
bring up Fuchsia on a board belongs to a separate project, bringup-kit, which consumes finished
specs. A
driver written from a spec is one **quality signal** for the spec: the Linux
candidates in L01 and L02, written without reading the reference driver and run against the
upstream reference driver on the same OS, test whether the spec was sufficient to implement
from. A driver for another OS, such as a Fuchsia
driver from bringup-kit, may later be added as a further signal; it is not a milestone here.

In practice: this repository holds the skills, the method, and the reference campaigns
(ENC28J60, e1000) that measure how good the specs they produce are. Work here improves those
skills and their quality signals (verification readings, blind requirement lists, qualified
checks, same-OS differential candidates, continuous review). Real bring-up work, including
writing and checking the specs for a particular board such as a Raspberry Pi 5, happens in the
consuming project, which installs these skills and runs them there; it is not planned here.
What that work teaches about the skills comes back here as changes to them.

## Terms

- **Skill:** instructions in a `SKILL.md` file that tell an agent when and how to perform a task.
- **Plugin:** a themed package of skills and supporting files that a harness can install together.
- **Harness:** the application that runs the agent and supplies its tools and access controls.
- **Agent:** a model-driven worker that reads instructions, calls tools, and produces artifacts.
- **Subagent:** a separately prompted agent context assigned part of another agent's work.
- **Context:** the instructions, conversation, and tool results available to one agent session.
- **Orchestrator:** the agent coordinating questions, delegated work, checks, and artifact handoffs.
- **Spec:** a written description of hardware facts or a peripheral's programming requirements.
- **Board spec:** a reusable hardware map; the format also covers SoCs, companion chips, and IP.
- **SoC spec:** a board-spec file describing one system on a chip and its peripheral placements.
- **IP spec:** a board-spec file describing a reusable silicon block independently of its placement.
- **Chip spec:** a board-spec file for a companion chip, its connection, and the blocks it contains.
- **Driver spec:** a per-peripheral implementation document covering hardware and target-OS work.
- **Instance:** one placement of an IP block, with its address, interrupt, clocks, and local quirks.
- **Stub:** a thin board-name skill that selects a spec and delegates to the shared board reader.
- **Overlay:** a separate spec file that adds material to another spec by its identifier.
- **Root:** a directory marked by `board-specs.yaml`, beneath which board-spec files are discovered.
- **Layer:** a root's position in the ordered merge, from public material through local additions.
- **Frontmatter:** the YAML metadata between `---` lines at the beginning of a Markdown file.
- **Composition:** resolving a board's component specs and the IP specs its instances name.
- **Provenance:** the recorded origin of a fact or artifact and the evidence behind it.
- **Provenance tag:** a marker identifying a fact's support, such as a datasheet or observed code.
- **Anchor:** a citation to a repository-relative file, line range, and usually symbol at a pin.
- **Pin:** an exact source revision or document edition and hash used to make a reading repeatable.
- **RTL:** the hardware design in a description language such as Verilog; the `[rtl]` class.
- **Conflict entry:** a recorded disagreement between sources, kept beside the claim with its resolution.
- **Cache:** an out-of-tree store of reference sources and documents managed by the investigator.
- **Investigator:** the source-reading worker that extracts facts, evidence, and mechanism prose.
- **Verifier:** a fresh reader that independently checks the artifact under a named procedure.
- **Verification record:** a separate file of claim verdicts, source identities, and the spec hash.
- **Source:** a document, device tree, code revision, or observation used to support a claim.
- **Authority:** the evidence cited as establishing a claim, rather than just suggesting where to
  look.
- **Sidecar:** a separate supporting file stored alongside an artifact or in its evidence directory.
- **Attestation:** a recorded declaration about procedure or review that a script cannot establish.
- **Claim:** a statement being checked; its unit varies between verification and evaluation.
- **Verdict:** a recorded decision such as `PASS`, `FAIL`, `UNVERIFIABLE`, `GAP`, or `ADJUDICATE`.
- **Candidate:** the generated driver spec being evaluated.
- **Ledger:** a structured list; here an evaluation answer key.
- **Gold ledger:** the evaluation answer key, authored from sources without seeing any candidate.
- **Corpus:** the fixed collection of source code and documents from which the answer key is made.
- **Requirement:** an independently judgeable obligation or proposition represented in the ledger.
- **Facet:** a stable ledger category, such as registers, receive behavior, or interrupts.
- **Recall:** how much of the eligible answer key the candidate states sufficiently to implement.
- **Precision:** how many candidate claims meet the scoring policy's correctness rule.
- **Denominator:** the eligible rows or claims over which a reported fraction is calculated.
- **Recoverable:** derivable at all from the sources the candidate was given, whatever it omitted.
- **Weight:** a ledger requirement's consequence category, used to report recall separately.
- **Adjudication:** a person's recorded resolution of conflicting readings or provisional decisions.
- **Freeze:** fixing reviewed inputs and scoring rules before generating candidates for comparison.
- **Lock:** the file recording a freeze's date, content hashes, policy identity, and attestation.
- **Hash:** a content fingerprint, used here to detect changes rather than preserve missing files.
- **Gap:** a missing fact; a spec-gap is an implementer's filed question for the authoring workflow.
- **Fork:** an unanswered choice that changes the work, such as which peripheral instance to use.
- **Drift:** a change in a spec or source that may invalidate an earlier verification result.
- **Ablation:** a comparison with a component removed, here a run without the skill.
- **Fixture:** the equipment and configuration used to exercise and observe real hardware.
- **Acceptance:** a decision that stated conditions for using a spec or implementation are met.
- **Mutation:** a deliberate fault or change used to see whether a test detects it.

## The problem

A vendor kernel can make a board work without explaining why. The address in a device-tree node may
require several bus translations before it is a CPU physical address. A reset sequence may mix
required ordering, a workaround for one silicon revision, and a delay chosen experimentally. A
shared driver may apply a workaround to an entire family even when an erratum names one part. An
engineer starting another OS needs to separate those facts before deciding what to implement.

An agent can turn this material into a convincing document while preserving the wrong meaning. It
may read a quirk table without following the control flow, mistake a driver's preference for a
hardware requirement, or attach a plausible citation to a statement the cited lines do not support.
It can also omit an entire recovery path. Checking only the claims it wrote cannot discover that
missing path. These are the concrete failure modes behind [the investigation
method](skills/board-expert/SKILL.md#3-investigate) and [the evaluation plan](EVAL-PLAN.md).

**The accuracy problem controls belief.** `spec-verifier` asks whether each statement follows from
its cited authority. The evaluation adds the opposite question: which independently identified
requirements did the document leave out?

Specs that cite their sources are published in the repository whose license fits those
sources ([license-split design](docs/LICENSE-SPLIT.md)). This document describes the
repository's rules, rather than deciding license compatibility.

## How the hardware map is organized

The [repository README](README.md) and [repository instructions](AGENTS.md) describe
skills as directories under `skills/<name>/`. A skill contains instructions and may
include scripts or templates. Installing this plugin makes those instructions available to the
harness; it does not automatically install enforcement into a consuming OS project. Much of this
system is a procedure agents follow, with deterministic scripts checking selected properties.

There are two different kinds of specification. Board specs are reusable maps of hardware and its
references. Driver specs are implementation documents for one peripheral. A board map helps the
investigator find the right tree, instance, and datasheet; it is not a complete replacement for a
peripheral programming specification. The distinction is explicit in
[`SPEC-FORMAT.md`](skills/board-expert/SPEC-FORMAT.md).

### Separate identity, placement, and wiring

A `kind: board` file describes what is fitted and connected on a board. Its `parts` entries name SoC
and companion-chip specs. An SoC or chip's `instances` rows place reusable IP blocks at concrete
addresses with interrupts, clocks, and quirks. The IP spec describes the block's programming model
without assuming any particular SoC address. Several boards can share one SoC description, and
several SoCs can place the same IP description.

For example, the test fixture [`widgetboard`](skills/board-expert/tests/fixtures/good_root/widgetboard.spec.md)
names `widgetsoc` in `parts`, and [`widgetsoc`](skills/board-expert/tests/fixtures/good_root/widgetsoc.spec.md)
places the `widgetuart` IP in its `instances`. A per-board stub such as the fixture
[`widget-expert`](skills/board-expert/tests/fixtures/stubs/widget-expert/SKILL.md) has one job: select
a spec id and hand the question to `board-expert`. Its description helps the
harness match a user's hardware name. Keeping facts out of stubs avoids maintaining another copy of
the hardware map and another copy of the investigation procedure. The published board specs and
stubs that used to illustrate this were removed, to be regenerated with the current skills.

### Discover roots, compose, then overlay

`board-expert` collects roots from its own `specs/`, root pointers in loaded skills, the checkout's
`board-specs.yaml`, and the user's `~/.config/board-specs/board-specs.yaml`. Markers can point to
further roots. It does not search the filesystem for markers. Within known roots, `*.spec.md` files
supply the identifiers that resolve `parts`, `instances[].ip`, and overlay targets.

Resolution prefers an explicit spec identifier, then matches names through triggers and aliases.
Exclusion triggers prevent accidental matches to similarly named hardware. An IP question tied to a
board resolves through the matching instance and that board's kernel tree. A generic IP question
uses the IP spec and its sources and explicitly carries no instance facts. The word "anchored" in
this board-resolution mode means attached to a board, not necessarily a driver spec with `[src:]`
anchors.

Composition happens before overlays. Every component receives its own applicable overlays in the
order `public`, `ip-vendor`, `soc-vendor`, `product`, `local`. Later scalar values win, resource
lists combine with replacement by matching identity, and body sections append under headings that
name the contributing layer and root. Identity, kind, and component membership cannot be overridden.
The exact rules belong in [the format
contract](skills/board-expert/SPEC-FORMAT.md#roots-and-layers).

This is configuration precedence, not a way to prove a later factual claim correct. Appending a
vendor statement beside a public statement preserves their origins; it does not resolve a factual
contradiction. Internal resources identify a `via:` skill that knows how to access them. An expert
without that skill reports the resource unavailable rather than inventing access commands.

A public root cannot contain internal resource entries or references to private skills. Vendor and
local facts do not flow back into public specs. A publicly supported fact can be added on the
strength of its public citation. The [vendor guide](skills/board-expert/VENDOR-GUIDE.md) also makes
clear that a private report, test, or log retains its source restrictions. A layer is not, by
itself, a confidentiality control or permission to publish.

### Make the kind of evidence visible

The investigation tags distinguish `[databook]`, `[standard]`, `[DT]`, `[source-observed]`, and
`[inference]`. Board specs add `[rtl]`, `[doc]`, `[hardware]`, and `[press]`. These mean,
respectively, hardware documentation, a standard, device-tree values, observed software, a
reasoned conclusion, the hardware design itself, project or vendor documentation, a measurement,
and third-party reporting. Testing against a device model adds `[emulated]`: a result observed on
an emulator rather than on silicon (proposed in the [QEMU differential
design](QEMU-DIFFERENTIAL.md), adopted 2026-09-25 after L02 showed how it is used; follow-on
SF-1). The format specifies where tags go and what accompanying citations and cautions they
require.

The important distinction is between seeing a driver do something and establishing that hardware
requires it. Source-only ordering carries "order not known to be required"; source-only tuning
constants carry "re-derive on hardware". An inference states its premises, derivation, confidence,
and how to test it. Board facts tagged as source-observed, press, or inference also retain an
explicit hardware-verification TODO. A tag makes limited support visible; it does not strengthen it.
What each class is trusted for, and what that trust assumes, is the next section.

## Evidence model: what we trust and why

A tag says what kind of evidence supports a fact. It does not say why that kind deserves belief
or how it goes wrong. Leaving that implicit makes two mistakes easy: treating a working driver's
behavior as a hardware requirement, and letting whichever source was read last win a
disagreement. This section states the assumptions so they can be checked and argued with.

### Every class rests on an assumption

| Evidence | Trusted for | Assumes | Known failure modes |
| --- | --- | --- | --- |
| `[rtl]` | Digital register behavior: field layout, reset values, side effects, access types | The design matches the silicon revision and configuration parameters in use | Analog, electrical, and PHY behavior, firmware, and board wiring are not in it; the wrong revision's RTL misleads with full confidence |
| `[hardware]` | What this board did under stated conditions | The measurement method observes what it claims to | One board, revision, temperature, and firmware image; absence of an effect is weak evidence |
| `[databook]`, `[standard]` | Documented programming model and required behavior | The edition applies to the silicon revision | Errata, stale editions, silicon that does not follow its own document |
| `[DT]` | Placement: addresses, interrupts, clocks, and wiring for the image it came from | It is the description the bootloader actually selects | Overlays and bootloader changes; binding examples that are not production values |
| `[source-observed]` | What a working driver does | The driver works on this revision | Workarounds for other revisions, delays nobody measured, bugs the driver happens to survive |
| Independent drivers agreeing (Linux and a BSD, for example) | Raises confidence in a `[source-observed]` fact | They were written independently | One copied from the other, or both from the same vendor code: agreement then adds nothing |
| `[doc]` | What a vendor or project says about its own work | The author knew and the text is current | Marketing pages, docs for a different part or revision |
| `[press]`, forums, other low-confidence reports | A lead worth checking | None | Allowed only with `TODO (verify on hardware)`, as today |
| `[inference]` | A conclusion from tagged premises | The derivation is sound | Carries its own confidence; never stronger than its weakest premise |
| `[emulated]` | How a driver behaves against a named device model under stated scenarios, and where that model departs from the manual | The model implements the behavior under test as the manual describes | Models are lenient (accept programming the silicon would not), omit errata and timing, and may share a misreading with the reference driver. A pass is weaker than `[hardware]`; a failure the manual explains is strong evidence. Never a hardware requirement and never the sole authority for a fact: it stands beside another class or is a premise of an `[inference]` |
| Model recall | Nothing | n/a | Not evidence and never tagged; a fact with no source is a gap |

Three rules follow from the table:

- **Confidence is scoped.** `[rtl]` for revision A says nothing certain about revision B0, and a
  `[hardware]` result on one board is a result for that board. The citation must carry the scope:
  the revision, board, image, or conditions.
- **Low-confidence evidence is allowed, labeled.** A forum post that names a register quirk is
  worth recording as a lead. The tag and its TODO keep it from reading as settled fact.
- **A model observation is a citation, not a mechanism.** An `[emulated]` fact cites the model,
  its version and the runs the way `[hardware]` cites the board, and states what was observed
  from outside the model (a value read back, a gap in a trace, frames in a capture), never how
  the model produces it.

### Conflicts are recorded, never overwritten

The table is not a strict ranking. `[rtl]` outranks a databook for digital behavior, and a
`[hardware]` observation outranks a databook when an erratum exists, but a databook outranks a
single board's measurement taken under unusual conditions. So a conflict between classes is not
settled by editing the losing claim. It becomes a conflict entry beside the claim: both readings,
their evidence and scope, the resolution, and which assumption from the table justified it. The
losing reading stays visible, the way an erratum stays visible beside the datasheet it corrects.
An unresolved conflict is a gap.

`reference-driver-review` already applies one instance of this ("the reference is evidence, not
truth: the databook breaks ties"). The ENC28J60 corpus already separates `vendor_confirmed` errata
from `implementation_observed` workarounds. The general conflict entry is proposed, not shipped.

### The spec learns from debugging and testing

A spec is not finished when it is accepted. Implementation, debugging, and testing produce
evidence, and that evidence belongs in the spec rather than in a test log nobody rereads:

1. A test or debugging result becomes a `[hardware]` fact, citing the test, board, revision,
   image, and conditions; a result from a device model becomes an `[emulated]` fact, citing the
   model, its version and the runs, and it narrows or confirms a claim without closing it.
2. It confirms, contradicts, or narrows an existing claim. A `[source-observed]` ordering marked
   "order not known to be required" can become required, or shown not to be. A source-only
   constant can be re-derived.
3. A contradiction produces a conflict entry, as above, not a silent edit.
4. Only claims that depend on the changed fact are re-verified; the rest of the verification record
   stands. A hash change today marks the whole record stale, which is correct but coarse; the
   L02 follow-ons scoped re-verification by hand, and the proposed [continuous
   review](#continuous-review-keeping-specs-right-as-evidence-changes) layer (C1, C2) records
   what each verdict rests on so the scoping can be computed.
5. An answered spec gap is folded in the same way, with the evidence that answered it.

The first place this loop runs is the ENC28J60 Linux rebuild (L01 in
[`IMPLEMENTATION-PLAN.md`](IMPLEMENTATION-PLAN.md)): its differential tests against the original
driver produce exactly these results. A settled `[hardware]` result closes a claim without a person
reviewing it, which is the scalable path. Humans are needed for conflicts the table's assumptions do
not resolve. The L02 differential campaign ran the same loop on an emulator: its `[emulated]`
results and spec gaps became spec revisions 6 to 8 (L02f3, SR-7, SR-8), and two of those revisions
reached the candidate (CF-1, CF-2). Dependency-scoped re-verification was the deferred M16 work;
the [continuous review](#continuous-review-keeping-specs-right-as-evidence-changes) section
proposes pulling its record and invalidation half forward. Until that is built, a changed spec is
re-verified by changed sections and their dependencies, chosen by the operator, or whole.

### When there is no existing driver

Everything above is easier while a working driver exists: it supplies the facts, it is the
reference for differential tests, and it breaks ties. For new hardware with no driver anywhere,
`[source-observed]` disappears and all three jobs move elsewhere:

- **Facts** come from `[rtl]`, the databook, and the hardware designers.
- **The reference** becomes a simulation or emulation of the design (RTL simulation, an FPGA
  build, a behavioral model) and published conformance suites where they exist.
- **Ties** are broken by independent implementations from the same spec, whose disagreements
  expose ambiguity but not a misreading they share, and by questions to the designers.

In that setting the spec's gap list is the main product: a precise list of questions for the
people who designed the hardware, each tied to the claim it blocks. This mode is not designed or
tested yet; it is recorded here so the evidence model does not assume a reference driver.

## The pieces, grouped by role

### Investigation

A person asks a hardware question or requests a driver spec. The orchestrator delegates source
reading.
[`QUESTIONS.md`](skills/board-expert/QUESTIONS.md) defines the shared intake protocol. Choices that
change the answer are asked together. A subagent returns a `Needs decision` block for the
orchestrator to ask, while continuing work independent of that choice. Missing facts become gaps.

[`board-expert`](skills/board-expert/SKILL.md) takes a question plus optional board and IP
identifiers. It composes specs, manages its reference cache, invokes resource skills, and answers
with its own investigation method. The report adds contributing roots, layers, overlays, source
commits, and verification status. It refuses to guess material identity choices or edit a spec
without being asked. With no spec, it reports best-effort findings and suggests scaffolding.

Board stub skills are user-discoverable names for that same delegated role (none ship today).
They produce no independent hardware database. Research-fill and reference selection can
invoke the shared expert through a stub or directly; source acquisition remains the expert's
job.

### Authoring

[`board-spec-scaffold`](skills/board-spec-scaffold/SKILL.md) is a person-invoked authoring workflow.
It takes identity, root, source, document, and coverage choices. It creates missing board, SoC,
chip, or IP files, and optionally a root marker, overlay, vendor-tool skill, or board stub. Its
[templates](skills/board-spec-scaffold/templates/) cover those artifacts. Public-source research
normally delegates to an investigator. The scaffold does not itself read driver bodies or answer
hardware questions; its final verification phase hands the files to `spec-verifier`.

The driver spec names the IP and canonical references, groups registers by hardware function, and
describes initialization, data or descriptor formats, interrupts, DMA/addressing, and sub-protocols.
Its target-OS half identifies existing drivers to reuse or model, interfaces, binding, packaging,
and implementation milestones. Confidence, unresolved details, and the usage notice tell the
implementer which statements are established and which still need investigation or hardware work.

[`anchored-peripheral-spec`](skills/anchored-peripheral-spec/SKILL.md) takes source the target may
derive from, source and target pins, and a peripheral scope. It produces a driver spec of the same
broad shape, but every source-derived claim points to performing statements or definitions. `[src:]`
addresses the reference tree, `[tgt:]` the target tree, and `[doc:]` a document section.
Implementers can read the code. The skill refuses fabricated anchors, and it is not a way to
write a driver under a license the source's terms do not permit.

Its hardware statements distinguish documented requirements, comment explanations, driver choices,
and behavior that is merely implemented. It normally delegates slices of larger drivers before
drafting and independently derives register tables twice. Anchor and inventory checkers precede a
fresh accuracy reader. `spec-verifier` can later rerun that process and preserve per-anchor verdicts
outside the document.

[`reference-driver-review`](skills/reference-driver-review/SKILL.md) is a person-invoked comparison
workflow for an existing implementation. It takes two pinned trees, locating the reference through a
board expert or the user, and produces `docs/<driver>-review.md`. Findings have `[impl:]` and
`[ref:]` anchors, a consequence, and a verdict: bug, suspect, benign, or reference issue. The
databook can settle a divergence in either implementation's favor. This skill produces neither a new
implementation spec nor driver code. Its checkers and later verification reuse the anchored
route.

### Verification

[`spec-verifier`](skills/spec-verifier/SKILL.md) is an orchestration skill a person can invoke on
demand. Authoring workflows also point to it for verification or re-verification. It takes a spec or
review and its declared sources, runs mechanical checks, and delegates fresh readings. The verifiers
do not receive the author's reasoning or a previous verdict record. They propose fixes but never
edit the spec. The output is the external verification record and associated reports.

The independent second reading depends on the artifact: bring-up-critical addressing, boot, and
console facts for board specs; register tables for anchored specs. Agreement is evidence of
repeatability, not proof of truth.
The lifecycle below explains how failures and disagreements remain visible.

### Evaluation

Evaluation is a collection of files and procedures, not another shipped spec-authoring skill.
[`EVAL-PLAN.md`](EVAL-PLAN.md) defines the comparison, and
[`evals/enc28j60/`](evals/enc28j60/README.md) holds the pilot inputs, answer key, rules, and
checkers. People authorize and review evaluation work. Candidate production uses a spec-authoring
skill; claim checking uses `spec-verifier`; coverage scoring runs in the opposite direction against
the ledger. A scored comparison is still to be run. No skill-quality percentage is supplied by this
document.

## A peripheral's lifecycle

Follow an ENC28J60 Ethernet peripheral attached to a board supported by a vendor kernel. The
board attachment is illustrative; the evaluation corpus is the existing pilot. Paths below are
consuming-project artifacts unless explicitly under this plugin. The spec itself is written by
an authoring skill (on the open side, `anchored-peripheral-spec`); the steps for writing and
implementing one from source the target may not copy moved out in the license split. This
walkthrough describes how to reach a measurement, not a completed ENC28J60 comparison.

### 1. Set the scope and establish the board map

The person identifies the board revision, SPI attachment, peripheral revision, vendor tree, and
target OS. The authoring skill resolves any material forks using the question catalog. If the board
lacks a map, `board-spec-scaffold` writes `<root>/<board>.spec.md`, references an existing SoC or
writes `<root>/<soc>.spec.md`, and adds any missing host-controller IP spec and instance row. A new
root receives `board-specs.yaml`. An optional `<board>-expert/SKILL.md` makes the entry point
discoverable.

`spec_check.py` checks the board files and cross-root references. The scaffold's verification phase
produces `<root>/resources/<id>.verify.md` for each file, including overlays under their own roots.
Board mapping and peripheral authoring are separate products: fixing a board-console fact belongs in
the board map; the Ethernet controller's programming sequence belongs in the driver spec.

If measurement is part of this task, establish the corpus and blind ledger before generating the
ENC28J60 candidate. An evaluator who has already read the candidate cannot retroactively construct a
blind answer key for it. The evaluation section gives the required ordering and the existing pilot
paths. For the ENC28J60 comparison, source inputs must match `corpus.yaml`; an arbitrary vendor
kernel revision cannot silently replace its pinned reference. Without that preparation, proceed with
ordinary spec work but do not call it a blind test.

### 2. Establish accuracy

Invoke `spec-verifier` for the landed spec. It checks tagged facts against their documents,
device trees, or pinned source. An inference is checked as an argument: true premises do not
excuse an unsupported conclusion.

The external record lands at `docs/resources/<spec-basename>.verify.md`, or in the project's
existing `docs/provenance/` location as the verifier documents. It includes the spec hash, date,
verifier identity, sources actually consulted, and verdict totals. The body keys individual facts by
section and ordinal, table row, or sequence step. A board record instead lives beside the root
marker in `resources/`; the test fixtures under `skills/board-expert/tests/fixtures/verify_root/`
show the shape.

A wrong value, an unsupported derivation, or a citation that cannot be located is `FAIL`, with a
proposed correction. A source that cannot be reached, for example a blocked document, is
`UNVERIFIABLE`. A cited section that can be opened but does not support the statement is a failure,
not an access limitation. A TODO-only item is `GAP`. The author corrects failures and re-verifies;
`spec-verifier` itself never edits the spec.

If the independent readers disagree, record both readings as `ADJUDICATE` and exclude the item from
pass/fail counts until a person decides. Disagreement alone does not establish an error.
Adjudication may find a false fact or excessive certainty, either of which earns a failure on its
merits. Zero failures can still leave important gaps, inaccessible evidence, or unsettled readings.
The current accuracy procedure has no common repair bound; adding one is proposed work.

### 3. Measure, preserve, and revisit

With an independently frozen ENC28J60 ledger in place, the evaluator maps ledger requirements into
the candidate for recall, then checks candidate claims against sources for precision. The result
must name its frozen inputs and policy and preserve separate counts. The pilot artifacts live under
`evals/enc28j60/`: `corpus.yaml`, `ledger.yaml`, `SCORING-POLICY.md`, and the prescribed
`ledger.lock`. The scored comparison is unfinished, and the opened procedures specify no universal
score-output filename. A verified spec alone cannot supply this measurement.

Later spec edits make record hashes stale. Later source revisions require a new reading at the new
pin. On the anchored route, `anchor_check.py --drift` identifies unchanged, moved, and changed
citations; `--rewrite` moves safe anchors and marks changed ones stale. Removing a stale marker
requires re-verifying the claim. None of those operations establishes behavior on the actual board.

Revisiting is not a one-time step at the end of this walkthrough. Field evidence, updated sources
and better models each change what a spec's verdicts rest on; the next section proposes how those
changes are recorded, which verdicts they make stale, what re-review they trigger at what cost,
and when a spec is good enough for its declared scope that further corrections become recorded
shortfalls rather than work.

## Continuous review: keeping specs right as evidence changes

**Status: approved by the user 2026-09-26. Nothing in this section is built yet.**
Requirements C1–C8 below; each has acceptance criteria. Four points were decided by the user
on 2026-09-26 before approval and are written below as decided: the A1 amendment (C5), the round cap
(C6), a comparison reading per new reading model (C4), and a standing tier-1 queue (C3); two
further choices were made by the orchestrator in the user's place and are marked as such.

### Terms

- **Basis** — the identities a verdict rests on: spec revision and the sections read, source
  pins, harness, emulator or fixture, candidate build, reading or implementing model, run IDs.
- **Status index** — one small file per campaign listing each tracked verdict, its basis and
  its status; the "small latest-status index" M16 proposed ([deferred plan](DEFERRED-PLAN.md)).
- **Campaign** — one device's spec, candidate, checks and evidence under one declared scope;
  L02's e1000 work is one.
- **Stale** — a verdict whose basis changed. It is not shown wrong; it cannot be cited as
  current until re-checked. **Contested** — a verdict newer evidence contradicts; it has a
  conflict entry. **Superseded** — replaced by a newer verdict, kept for history.
- **Sweep** — the mechanical comparison of every basis in the index against the current
  identities, producing the stale set and a queue of re-review units.
- **Cost tier** — how a unit is started: tier 0 runs on every change with no model, tier 1
  is queued and run by agents without a person starting each unit, tier 2 waits for a person.
- **Item** — a finding for a later spec revision, with a class: **R** (changes what a driver
  must do), **E** (changes the evidence for a claim, not the requirement), **W** (wording or
  form only).
- **Sufficient for scope** — the stopping rule's state (C6): the spec meets its declared scope
  and further work starts only from a trigger.
- **Shortfall** — a gap in the declared scope that is recorded with a reason and a reopening
  condition instead of being worked.
- **Deployment** — one installation of this method with its own sources, run store, specs,
  models and fixtures; the public repository is one, and a private one may exist elsewhere.
- **Plugin** — a skill, packaged the way this repository packages its own, that implements one
  extension point (C8) for a deployment; a **reference plugin** is one this repository ships,
  such as the QEMU harness. A **marketplace** is the catalog a harness installs plugins from.
- **Source registry** — a deployment's list of its sources by local ID, version and hash.
  **Deployment manifest** — the YAML file, outside the repository, that declares its plugins.
- **Acceptance set** — the ten harness scenarios run for the reference and the candidate, each
  in an **isolated run** (freshly booted guests, one scenario). **L01 review trio** — a
  reference-driver review, a requirements review and `review-swarm` on the candidate's diff.
- **Mandatory claim** — a claim in the declared scope that the scope does not mark optional;
  for L02, every one of Q01–Q28.

See the [glossary](GLOSSARY.md).

### Why, and what already works by hand

The goal is a system that produces reliable specs, tests them, and keeps reviewing and
correcting them as the evidence changes and the models improve, while accepting that good
fixtures and specs reach diminishing returns long before every last correction is made. The
L02 follow-ons ran every part of that loop by hand:

- **Independent re-reading and comparison:** [AF-1](evidence/AF-1.md) and [SR-7](evidence/SR-7.md)
  gave already-verified changes a second reading by a fresh reader that never saw the first,
  joined the two records key by key and adjudicated each disagreement against the cited text.
- **Checks proven before they are cited:** [L02d3](evidence/L02d3.md) qualified 22 claims with
  planted defects (Q15 again in L02f2b), [QF-1](evidence/QF-1.md) three more, and FC-1 and CS-1
  one each (Q27, Q28); the one that could not be qualified is recorded with its reason (Q18,
  `unobservable`).
- **Revision to candidate:** [CF-1](evidence/CF-1.md) and [CF-2](evidence/CF-2.md) gave the
  implementer the spec diff only, reran the acceptance set declared before the run,
  and attributed every trace difference.
- **Scoped invalidation by reasoning:** after L02f2b changed one scenario and requalified Q15,
  [L02f3](evidence/L02f3.md) carried the other 21 qualifications to the final harness because
  the diff touched only that scenario.
- **Field evidence into the format:** [SF-1](evidence/SF-1.md) turned `[emulated]` from a
  proposal into a class with checker rules after it had been used.

What is missing is the bookkeeping that would let this happen without an operator rereading
every evidence file: which verdicts rest on what, which went stale when something changed,
where the queued items are (today in tables across AF-1, SR-7, SR-8 and CF-2), and when to
stop. SR-7 needed six sequential readings, and the FAILs in rounds 3 to 5 were sentences its
own fix passes had written; SR-7 and SR-8 drew the lesson that a fix pass which adds words needs
its own reading, but no rule said when that loop should end.

### Three sources of change

Three kinds of change are expected to require re-review. New tools and new data sources belong
to the second.

| Source | Examples here | What it can make stale | What it triggers (tier) | What a person decides | How it reaches a spec revision |
| --- | --- | --- | --- | --- | --- |
| **1. Field evidence**: findings from writing drivers and testing them on hardware or an emulator | L01-hw's reference driver failing C6 and C7 in all three runs; CF-2's review findings (A-RR-1 to A-RR-7); QF-1's F2 (the model delivers runts), which became EM8; a hardware result that contradicts an `[emulated]` observation (HF-1's list) | The facts it contradicts become *contested*, with a conflict entry; the claims that use them as a premise become *stale*. A candidate or reference defect makes nothing in the spec stale unless attribution finds a spec gap or error | Attribution inside the unit that found it; re-verification of the contested fact's dependents (tier 1) | A conflict that the evidence model's assumptions do not settle; whether a requirement changes (SR-8: the user chose the attribution rule); any hardware run | An item of class R, E or W, recorded where it was found and listed in the index |
| **2. Updated sources**: new document editions and errata, new reference-driver or kernel releases, new tools and data sources (an emulator version, a trace tool, a register database) | A new edition of the 8254x manual; a Linux release changing `e1000`; a QEMU package upgrade on the test host; a tool that could time a reset below 1 µs (Q18) | Verdicts citing the changed sections; if the change cannot be mapped to sections, every verdict citing that document. Emulator or harness changes: see C2. A new tool invalidates nothing; it can reopen a shortfall | Detection at tier 0 (identity comparison); re-verification, requalification or the acceptance-set rerun at tier 1 | Whether to adopt the new edition or release as the pin; whether a new tool is worth qualifying (C6) | An E or R item; the new pin recorded in the revision header |
| **3. Better models and tools**: the same inputs re-read or re-implemented by a stronger model | A newer reading model re-reading revision 8; a newer implementer model writing a fresh candidate from revision 8 | Nothing. A new model is not evidence that old verdicts are wrong | A comparison reading (tier 1); a fresh independent implementation (tier 2) | Adjudications the cited authority does not settle; launching an implementer | Only disagreements that survive adjudication become items (C4) |

The stopping rule (C6) applies to all three: every item any source produces gets a class, and
C6 decides whether it becomes work or a recorded shortfall.

### C1 — Record what every verdict rests on

Reuse what exists before adding anything:

- **Verification records** already carry `spec_sha256`, `verified`, `verifier` and `sources`
  with pins ([`spec-verifier`](skills/spec-verifier/SKILL.md)), and their bodies are keyed by
  section and item. C1 requires `verifier` to name the model and its version, which the L02
  records already do in prose.
- **Evidence files** already freeze identities before a run ("Frozen before execution" in
  CF-1, CF-2 and QF-1): spec revision and hash, candidate source and module, harness files,
  reference module, kernel, emulator, run script, run IDs. **Per-run `identities.json`** and
  the **run ledgers** hold the full values privately.
- **The claim list** Q01–Q28 (L02d3, QF-1, FC-1, CS-1) says, in prose tables, which check
  supports each claim and which defect qualified it.

Two files are new. A **claim map** per campaign (`evals/e1000/claims.yaml`) turns those prose
tables into data: claim ID, the harness checks by name, and the qualifying defects and runs; the
harness itself stays unchanged. And a **status index** per campaign (for the public e1000 campaign,
`evals/e1000/status.yaml`), with one entry per tracked verdict: the spec revision's
verification by section, each claim's qualification, the candidate's result per claim, each
`[emulated]` observation, and each open item. An entry holds the verdict, its basis (the
identities above; for a reading, the sections it read and the dependencies its brief declared,
as the SR-7 and SR-8 operators chose them by hand; plus the toolchain, which today is recorded
only as a name such as `gcc-14`),
a link to the public evidence, the run IDs, and a status (`current`, `stale`, `contested` or
`superseded`) with the reason. Items carry their class, their source (1, 2 or 3 above) and a
disposition (`queued`, `applied` with the revision, `shortfall` with the reason, or
`rejected`).

Rules: a verdict is never edited; a new verdict is a new entry that supersedes the old one,
and every attempt stays in the run store. Legacy verification records stay legacy; converting
their format does not make them current (M16). The index holds only IDs, hashes, verdicts, run
IDs and links, the same kind of content public evidence files already carry; everything else
stays in the private ledgers. Under the 2026-09-25 rule of one job per record, the index becomes
the status record for a campaign's verdicts and items: the plan links to it instead of repeating
status, and evidence files keep their conclusions and findings, not a running list of open items.

**Accept:** the e1000 index and claim map built from the existing evidence cover every claim,
every landed spec revision's verification and every open item in AF-1, SR-7, SR-8 and CF-2; a
reviewer can trace each entry's basis to a public evidence file and a run ID without opening
private content.

### C2 — Invalidate conservatively, scoped by dependency

| Change | Becomes stale | Stays current |
| --- | --- | --- |
| New spec revision | Verification of the changed sections and of every entry whose recorded dependencies include them (the review default in [AGENTS.md](AGENTS.md): "the changed claims and their dependencies"); an entry with no recorded dependencies, the whole revision's verification; the candidate's conformance only if the revision header says a driver requirement changed (SR-8 did, SR-7 did not); the qualification of claims whose expected outcome cites a changed section | Verification of unchanged sections with recorded dependencies outside the change; other qualifications |
| New document edition or erratum | Verdicts citing the changed sections; every verdict citing that document when the change cannot be mapped | Verdicts citing other sources |
| Reference driver or kernel release | `[source-observed]` and `[kernel]` verdicts at the old pin; the reference control runs if its module changes | Verdicts on the manual |
| Harness change | Qualification of the claims whose check code changed, found from the diff and confirmed by the reviewer (L02f3's reasoning); all qualifications when that cannot be established | Qualifications of untouched checks |
| Emulator, guest kernel or guest image change | Every `[emulated]` observation, every qualification and every candidate result on that emulator | Spec verdicts that do not cite `[emulated]` observations |
| Candidate build change | The candidate's results | Qualifications, which rest on the reference and the defects |
| Hardware result contradicting an `[emulated]` observation | The observation becomes contested, with a conflict entry (the general conflict entry is still proposed; for e1000 it goes in the spec's §12 tables beside EM1–EM8); claims that use it as a premise become stale | The candidate's emulated results, which stay true of the emulator |
| New fixture | Nothing: a result on a new board is a new scope, not a replacement | Earlier fixture results, within their scope |
| New reading or implementing model | Nothing (see C4) | Everything |

When a mapping is uncertain, widen to the enclosing unit (item to section to document; check
to scenario to harness) rather than guess. A stale verdict stays readable and is reported as
"stale since" the change; it cannot count toward acceptance. Only recorded identities can
invalidate: an input that was never recorded, such as the compiler before
[PROCESS-NOTES](PROCESS-NOTES.md) flagged it, cannot trigger anything, which is why C1 adds
the toolchain.

**Accept:** a synthetic change matrix, one change per row above, run against a copy of the e1000
index, marks exactly the listed entries stale; a model change marks nothing stale; a harness
diff touching one check stales only that check's claims; an unmappable change widens as stated.

### C3 — Triggers and cost tiers

| Tier | Runs | Work | Cost |
| --- | --- | --- | --- |
| 0 | Existing checks on every change, in CI and at each checkpoint, plus a schema and link check of the index; the sweep locally, wherever the run store is configured, at the start of each orchestrator session and whenever a known input changes (a host package upgrade, a new manual edition). Public CI cannot run the sweep: the spec, the ledgers and the emulator identities are in the private run store and on the test host | Existing checks (`spec_check.py`, a deployment's source-overlap scans, harness tests, `corpus_check.py`, the privacy check), the index check, and the sweep | Seconds; no model |
| 1 | From the sweep's queue, as a standing queue (decided by the user, 2026-09-26), at most three units per batch | Re-verification of stale sections and their dependents (one `spec-verifier` reading: 8.7 minutes in AF-1, 7.7 in SR-7); requalification of claims whose checks changed; the acceptance set rerun after an emulator or candidate change (40 isolated runs); a comparison reading by a new reading model (C4) | Bounded agent time, recorded per unit |
| 2 | Only on a person's decision | Requirement changes; implementer rounds (launched by the user, as in CF-1 and CF-2); a fresh implementation by a new implementer model; hardware runs (HF-1); a new blind list or recall re-measurement; adopting a new source edition as the pin; accepting a shortfall on a mandatory claim | Model, equipment and review time |

Tier-1 units run the way the follow-ons ran: `orchestrate-milestones` gives each unit a fresh
subagent and one pull request, and `quota-strategy` routes the work (decision D9 in the
[plan](IMPLEMENTATION-PLAN.md)). The user approved a standing tier-1 queue with a batch cap on
2026-09-26; the orchestrator set the cap at three units per batch under the `quota-strategy`
rules (an orchestrator decision, made in the user's place). No person starts each unit; pushing and
merging still follow [AGENTS.md](AGENTS.md): a batch ends in checkpoint commits on topic branches,
and pull requests open only on the user's explicit "push". There is no
daemon and no database: the sweep is one command that reads the index and the current
identities, and a scheduled run is optional where the environment allows it.

**Accept:** given the e1000 index and one changed identity, the sweep lists the stale entries and
the tier-1 units that cover them; one batch of at least two tier-1 units runs from the queue to
reviewed checkpoint commits with no person starting each unit, and records its cost; a tier-2 unit
never starts from the queue without a recorded decision.

### C4 — Better models are compared, never trusted

When the deployment's reading model changes, one fresh reader using the new model re-reads the
current revision of each campaign in scope, under the same brief format and without sight of
any earlier record (the `spec-verifier` rule). The operator joins the new record to the last
one key by key, as AF-1 and SR-7 did (`review/comparison.md` in the run store). Agreements
count as an additional independent reading. Disagreements are adjudicated against the cited
authority; only those that survive adjudication become items, and a person decides the ones the
authority does not settle. A new model's FAIL is a disagreement, not a verdict, until then.

This is one tier-1 unit per spec per new reading model, including specs already sufficient for
their scope (decided by the user, 2026-09-26): it is the cheapest check on whether the spec is
still converged.
A fresh implementation by a new implementer model is tier 2: it is useful as a second
independent implementation from the same spec, whose behavioral differences on the acceptance
set expose ambiguity, but it is launched only when the spec is not yet sufficient or the user
asks. Agreement between models raises repeatability, not truth: they can share a misreading.

**Accept:** one comparison reading of the e1000 spec's current revision by a different model,
joined key by key, with every disagreement adjudicated or listed and no verdict changed before
adjudication.

### C5 — Findings reach a revision, and the candidate, through the existing loop

1. An item is recorded in the evidence file of the unit that found it, with its class and
   source, and listed in the index.
2. A spec revision unit (the SR-n pattern) takes the queued R and E items and any W items, edits
   a working copy of the last landed revision (never the landed file), and states in its header
   whether a driver requirement changes.
3. `spec-verifier` reads the changed sections and their dependencies. Text that changes a driver
   requirement needs two independent readings (A1's standard; the AF-1 and SR-7 procedure)
   before the revision is sufficient for scope; wording-only and evidence-only changes need one
   reading plus, where the campaign uses one, the source-overlap scan. **This amends A1** in the [QEMU differential
   design](QEMU-DIFFERENTIAL.md#acceptance-criteria), which asked for two readings with no such
   split (SR-7 recorded revision 7, which changed no requirement, as not meeting it); the user
   approved the amendment on 2026-09-26.
4. If a requirement changed, a candidate update unit (the CF-n pattern) gives the
   implementer the revision diff only, audits the session where the deployment has an access
   audit, reruns the acceptance set declared
   before the run, attributes every trace difference, and ends with the L01 review trio.
5. The index records the new verdicts; the old ones become superseded.

The independence rules stay as they are: readers never see earlier records or the author's
reasoning; the implementer never sees the reference driver, the emulator's source or the
evidence; checks are qualified before they are cited and requalified when their code changes.

**Accept:** the SR-8 → CF-2 path backfilled into the index as the worked R-item path, each step
linked; and one live W or E item carried through a revision with the index updated at each
step. No new candidate round or new model is needed to accept the layer.

### C6 — Stopping rule: sufficient for the declared scope

A campaign is **sufficient for its declared scope** when:

- **S1** The scope is declared: the claims, the evidence classes accepted for them, and the
  target (for L02: Q01–Q28 on the emulated 82540EM at the pinned identities).
- **S2** Every mandatory claim in scope is qualified and passes, or is a recorded shortfall.
- **S3** No FAIL is open that is about a claim's truth or support (an accuracy FAIL, as against
  one about form or wording), and no R item is open; form and wording FAILs may stay queued.
- **S4** Every text that states a driver requirement has had two independent readings.
- **S5** The most recent independent re-reading (C4 or a second reading) produced no R item.

After that, only a trigger creates work, and not every trigger does:

- An R item, a contested fact in scope, or a stale entry in scope reopens the campaign.
- An E item reopens it only if it changes a claim's status in scope.
- A W item never starts a revision. W items wait for the next revision made for another reason.
- When an item's class is in doubt, it is R until a person decides otherwise. Findings about the
  records rather than the spec (SR-8's item 4) are not spec items.
- A fix pass that adds words needs its own reading (SR-7, SR-8). At most three verification
  rounds per revision, whatever the FAILs' class; fixes after round two may only delete or
  narrow text; after round three, what remains goes to the user as a list (decided by the user,
  2026-09-26).
- A shortfall names one reason: `unobservable` (the instrument cannot show it, as for Q18),
  `blocked` (equipment, as for HF-1), `out of scope`, or `not worth it` (an E or W item whose
  cost exceeds its effect, such as adding L02d3's unlabeled model leniencies to §12.5). It also
  names what would reopen it: a hardware fixture, a timing-capable tool, a revision that
  touches the passage.
- A person approves a shortfall on a mandatory claim; the operator records the others.

**Worked example (e1000, as of 2026-09-26, to be confirmed by the first sweep).** S1 holds (28
claims, all mandatory). S2 holds, with Q18 a shortfall (`unobservable`; reopened by hardware or
a timing-capable tool) that L02f3's acceptance, closed under the user-approved plan revision,
already accepted; HF-1's hardware-only behaviors are `out of scope` for the emulated scope and
reopen when hardware arrives. S3 holds: SR-8's items 1–3 and CF-2's `[emulated]` note are W or
E, item 4 concerns the records; CF-2's A-RR-1 ("at least" at the poll) is W: it permits extra
readings without changing the minimum (an orchestrator decision, made in the user's place on
2026-09-26). S4 does not hold:
revision 8's TNCRS rule (§4.7, §5.5, §5.9 L6) was read by sequential readings only (SR-8). So
one tier-1 unit, a second independent reading of revision 8's changes, stands between the
campaign and sufficient; it is the first tier-1 unit once this design is approved (an
orchestrator decision, made in the user's place). The queued W items ride along with whatever revision comes next; the
candidate's A-RR-7 serialization item stays in the next implementer brief, not a round of its
own; recall measured on revision 3 stays a recorded limitation, since no revision since then
widened the scope.

**Accept:** the sweep reports each campaign as sufficient or lists exactly what blocks it; every
open item has a class and a disposition; no W item alone started a revision; the e1000 campaign
reaches sufficient, or its blockers are those in the worked example.

### C7 — Deployable in a private environment

The method must run unchanged in a separate private environment whose sources, run store,
specs and evidence stay inside it, with nothing flowing back to this repository.

- **The public repository contains** the method: the skills, the formats (`SPEC-FORMAT.md`,
  the index schema), the checkers and the sweep, the invalidation and trigger rules, the
  orchestration conventions, the reference plugins (C8), and public-device campaigns (e1000,
  ENC28J60) as worked examples.
- **A deployment supplies** its sources and a source registry, its spec roots (the existing
  layer mechanism: `product` or `local` roots found through pointers, never by search), its run
  store (already configured per user, `run_store` in `~/.config/driver-lab/config.toml`), a
  campaign directory for its index and evidence, its models and agent CLIs by role, its
  fixtures and emulators, its implementer sandbox settings, and its publication policy.
- **Sources are identified by a local ID, a version and a hash.** Change detection compares
  those; the sweep never parses a source. The hash may come from the deployment's own adapter
  (C8) when the method's code may not read the bytes.
- **Models are named by role** (reader, implementer, reviewer), so C4's trigger names whatever
  that deployment uses.
- **Nothing flows back.** The existing rules already point this way: a public root cannot
  reference internal resources or private skills, vendor and local facts do not flow into
  public specs ([vendor guide](skills/board-expert/VENDOR-GUIDE.md)), and the run store path is
  never written into this repository. The method needs no return channel; the public repository
  never names a deployment's sources, plugins or campaigns.

**Accept:** a stand-in private deployment (a temporary root, run store and registry of invented
documents, created by the tests) runs the sweep, C2's invalidation and one tier-1 re-verification;
with the stand-in sources unreadable to the sweep, a version or hash change in the registry is
still detected; changing the role configuration changes the model the queue names without a code
change; afterwards a scan of the public repository finds none of the stand-in IDs.

### C8 — Extension points for tools that cannot be public

Four extension points, each implemented by a plugin. A plugin is a skill, packaged as this
repository packages its own (`.claude-plugin/plugin.json`, installed through the deployment's
own marketplace), declared the way an overlay already declares a vendor tool: an entry with a
`kind` and `via: skill:<name>`, where the named skill owns invocation, authentication and safety
([vendor guide](skills/board-expert/VENDOR-GUIDE.md), "Wrap a tool"). What is new is that an
entry the sweep or a harness calls without a model also names a `command` that prints JSON.

| Extension point | Called by | Input | Output | Provenance it must record | Reference plugins |
| --- | --- | --- | --- | --- | --- |
| **Source adapter**: identifies a document or data source (a data-sheet store, a register database) | The sweep (tier 0); readers, through the skill | A local source ID | `id`, `version`, `sha256`, `status` (`ok`, `blocked` or `unknown`), date checked; never content | The adapter's name and version; how the version was determined | A pinned-file adapter over `corpus.yaml`-style entries (as `corpus_check.py` does for ENC28J60, and L02a's manual pin for e1000) |
| **Evidence producer**: emits tagged observations (a simulator, a trace tool, a register dumper) | Tier-1 units | Target identity, what to observe, run ID, run directory | Observations, each with one evidence class and its citation (tool, version, run ID), phrased as what was observed from outside the tool | Tool name, version and hash; target identity; conditions | The QEMU harness's register trace and captures, class `[emulated]` |
| **Implementer or reviewer**: a model or agent CLI in a role | Tier-1 and tier-2 units | A brief, the allowed inputs, a workspace | The artifact and a session record; for an isolated implementer, its access audit | Agent or CLI, model and version, date, sandbox profile, audit verdict, transcript path (in the private ledger) | Codex in a bubblewrap sandbox with an strace access audit (L02); Claude subagents as `spec-verifier` readers and reviewers |
| **Fixture or harness backend**: runs scenarios against a driver (an emulator, a board with SPI, a proprietary bench) | Tier-1 units | Modules (reference, candidate, planted defects), scenarios, repetition count, run ID | One run directory per isolated run: per-check verdicts (PASS, FAIL, ERROR) by check name, raw artifacts, and `identities.json`; the claim map (C1) links check names to claims | Fixture or emulator identity, harness hash, kernel and image hashes, conditions | `evals/e1000/harness/l02harness.py` (QEMU, tested in CI); L01's Pi fixture harness, which today lives only in its private run and would have to be published to serve as a public reference |

**Discovery and configuration.** A deployment manifest (YAML) lists the entries: `id`, `kind`
(`source`, `producer`, `role` or `fixture`), `via`, `command` where needed, and for a producer
its `class`. Its path is a `deployment` key in the same user config file that already holds
`run_store`, so it lives outside the repository. With no key set, the public reference
manifest for the public campaigns applies. A producer that declares a class not in
`SPEC-FORMAT.md` or in the target spec's own tag table (the e1000 spec defines `[kernel]` there) is
rejected; a new general class goes through the format, the evidence model and the checker as
`[emulated]` did in SF-1.

**Testing without the private plugins.** Only the two points called without a model, the source
adapter and the fixture backend, get a mechanical contract check now: the public repository runs
it against the reference plugins and against stubs in its test fixtures (an adapter returning
invented IDs, a backend returning canned run directories), and a deployment runs the same
command against its own plugins, locally. The evidence producer and the implementer or reviewer
points are documented conventions, checked by the unit's reviewer as today; their mechanical
checks are added when a first private plugin of that kind exists.

**Accept:** the contract check passes on the reference adapter, the QEMU backend and the stubs,
and fails on stubs missing each required provenance field; the stand-in deployment of C7 runs
with stub plugins only; the manifest schema and the contract check are the only new interfaces;
no plugin is named in any public file other than the reference plugins.

### Acceptance for the layer, and a guard against over-building

The layer is accepted when C1–C8's criteria are met on the e1000 campaign and the stand-in
deployment. It adds an index file and a claim map per campaign, a manifest schema, the sweep, the
contract check and their tests; anything more (a service, a database, a scheduler, automated spec edits,
automated merges) needs its own design change. Every spec change still goes through a revision
unit and a person still decides everything in tier 2.

### Relation to M16, D6, R1, R7 and R8

- **D6 is absorbed and resolved** by C1 and C2: versioned records are the existing records plus
  the status index; conservative dependency invalidation is C2's table; legacy records are not
  migrated into current status.
- **M16 is split.** Its record and invalidation half (M16a) is **pulled forward** as C1–C3 for
  campaigns with a claim list, without waiting for M03/M04: L02 showed that frozen-identity
  tables, per-run identities and the run ledgers are enough, so this supersedes M16's dependency
  on M03/M04 for that scope. Its acceptance rules carry over: changed or unavailable evidence
  cannot keep unqualified acceptance, incompatible policy versions cannot be compared (here: a
  verdict under one scoring or qualification rule is not compared with one under another without
  saying so), unrelated capabilities stay scoped, old attempts stay.
  Its feedback half (M16b) is partly absorbed: C5 is the feedback path and C7 covers private
  material. **Replay of old attempts with archived tools stays deferred** with M03/M04 and the
  spec-only experiment.
- **R1, R7, R8** ([validation proposal](VALIDATION-PROPOSAL.md#1-outcome-and-scope)) gain C1–C2
  (identities and staleness), C2–C3 (maintenance and preserved attempts) and C5 (recorded
  feedback disposition) as their coverage outside the deferred experiment.

The plan entries are updated when a plan is derived from this design, not in this revision: D6 and
M16 in the deferred plan, and in the implementation plan's deferred table the rows "Automated
maintenance/invalidation and full pilot qualification (M16–M17)" and "Generic execution contracts
and synthetic replay (M03–M04)" ("build shared machinery only after demonstrated need"): L02's
hand-run loop is offered as that demonstrated need, for the record and invalidation half only.

### What this revision does not cover

- The paired experiment M09–M13, P01 and the scored ENC28J60 comparison stay deferred.
- Replay of old attempts with archived tools (M16b, with M03/M04).
- Automated recall re-measurement: the blind list is a baseline, not amended after the fact
  (CF-2), and a new one is tier 2.
- Hardware automation, and any change to how fixtures are qualified (L01, HF-1).
- Board specs without a claim list: their verification records keep today's whole-file
  staleness; general board and SoC claim identities remain the proposal's open choice.
- Automatic spec edits, pushes or merges.
- The contents or configuration of any private deployment.

## Evaluation: measure omissions and errors separately

### Why verification is not a quality score

A verifier begins with what the candidate says. If the candidate contains no interrupt recovery
section, there may be no recovery claim to fail. `GAP` catches an explicit TODO, but it does not
create a requirement for an omission the author never acknowledged. Anchor inventories help find
unmentioned header names, yet those names are not an independently reviewed list of everything a
working driver needs. This is why the evaluation requires a separate answer key.

[The evaluation plan](EVAL-PLAN.md) asks whether another implementer could write a working driver
and meaningful tests without reading the original source. Documentary scoring measures necessary
parts of that question: coverage and correctness. Whether the implementation actually works still
needs execution evidence. The ENC28J60 pilot calibrates the method on a small public peripheral; it
is not evidence about performance on a complex SoC driver.

### Build the answer key before seeing the answer

[`corpus.yaml`](evals/enc28j60/corpus.yaml) identifies the permitted sources: driver and header
content at an exact commit, document editions and hashes, and an edition-specific errata map.
Documents are referenced rather than redistributed. The same URL can serve changed bytes, and the
same issue number can denote different problems in different errata editions. Edition identity and
located evidence are therefore part of the input, not bibliographic decoration.

Ledger authors read only that corpus and no candidate. Otherwise, the candidate can teach them which
requirements to remember, making its omissions disappear from the answer key. The rule also excludes
someone who has already seen a candidate from authoring rows for that device. Independent readers
derive critical requirements; merging preserves disagreements for adjudication rather than silently
taking the first writer's answer.

[`ledger.yaml`](evals/enc28j60/ledger.yaml) has a header recording the pilot, corpus date, authoring
rule, and reader/merge conventions, followed by `rows`. Each row has an immutable identifier,
statement, class, derivation, applicability, weight, scope, recoverability, and status. Reader and
review metadata record independent support. [The format](evals/enc28j60/LEDGER-FORMAT.md) is the
contract; current rows and unresolved decisions live in the ledger and its companion files.

Identifiers use `ENC28J60-<FACET>-<NNN>`, independent of both document and candidate headings. They
are never reused or renumbered. Withdrawn rows remain with reasons. A derivation names a corpus
source and a locator such as a section or mechanism, not just a page number. Separate applicability
fields preserve what the vendor confirms, what the implementation does, and what remains unresolved.
Silence in an erratum is not proof that a revision is unaffected.

Rows distinguish documented hardware requirements, observed software behavior, inference,
implementation choice, and unresolved conflict. That classification prevents a faithfully reported
software policy from becoming a falsely mandatory hardware rule. Rows should be atomic; the pilot
policy enumerates bounded exceptions for composite scoring units and their verdict rules. Do not
infer a general permission to bundle unrelated requirements from those exceptions.

### Freeze the inputs and decisions

Freezing is more than adding a date. Resolve provisional classifications and weights, dispose of
overlaps so one requirement is not credited twice, establish independent support for critical rows,
and preserve unresolved matters explicitly. Run corpus drift checks, the ledger schema/freeze
checks, and the source-overlap scan prescribed by the [pilot README](evals/enc28j60/README.md).
Source quotations do not become acceptable merely because they are in an evaluation file.

`ledger_check.py` checks schema, identifiers, derivations against corpus pins, and structured freeze
conditions. It cannot establish blind authorship, semantic uniqueness, or the adequacy of a reader's
work. Those require the adjudicator's recorded attestation. Its `--freeze` mode checks readiness; it
is not permission to generate a candidate regardless of unresolved human decisions.

The lock records the ledger and corpus hashes, the policy version and content hash, the freeze date,
and the attestation. A version label alone cannot bind mutable policy text. `--lock` compares these
identities with the files used for a run. Consult the current
[checker](evals/enc28j60/ledger_check.py) and pilot README for the operative interface and remaining
freeze work. This directory is actively maintained; this document deliberately fixes neither its row
totals, remaining gate totals, nor a scoring-policy version.

Only after that freeze are candidates generated for the comparison. The planned with-skill and
without-skill arms use the same model, sources, tools, and budget. The answer key is not extracted
from either candidate. Candidate-informed corrections belong in a separately identified benchmark
revision; preserved candidates can be rescored with both old and new rules made explicit. Quietly
changing the denominator would confound a changed answer key with a changed skill.

### Recall: walk from the ledger into the candidate

The frozen policy determines which active, in-scope, recoverable rows enter recall. Recoverability
asks whether the candidate's supplied material could establish the requirement at all. A candidate
cannot remove rows by declaring a narrower scope, changing headings, or writing TODOs. Rows excluded
at authoring time remain visible with reasons rather than disappearing from the corpus.

The pilot's [scoring policy](evals/enc28j60/SCORING-POLICY.md) includes documented requirements,
unresolved conflicts, and inference rows. It reports observed software behavior separately and
excludes implementation choices from recall. A conflict is covered by accurately stating both
readings, not by pretending one is settled. Inference coverage must preserve its conditions and its
status as reasoning rather than documentation.

Each eligible row receives `covered`, `partial`, `missing`, or `misstated`. Full credit requires
enough information to implement the requirement. Partial credit covers incomplete statements;
TODO-only or absent content is missing. A misstatement earns no recall credit and also affects
precision. The formula is `(covered + 0.5 * partial) / eligible rows`, reported overall and within
each weight category, with the component counts. An empty category is reported as not applicable.

Weights distinguish critical, important, and minor consequences. The current policy's consequence
rule also limits the weight of requirements that matter only when an optional feature is used. Read
the exact weight rules in the ledger format rather than treating "critical" as a synonym for any
serious-looking register. Reporting categories separately prevents minor detail from masking missing
essentials. Partial counts remain visible because identical percentages can hide different patterns
of incompleteness.

### Precision: walk from candidate claims back to evidence

Precision checks every factual proposition, including ones without a ledger row. The policy splits
compound sentences and table assertions into independently falsifiable claims, then deduplicates
repeated propositions at their strongest statement. A claim matching several ledger rows is still
one claim. That avoids multiplying one mistake because the answer key has overlapping evidence.

A contradicted statement is an error. An accurately attributed observation of driver behavior is
judged as software behavior; declaring the same policy a hardware necessity can be an error.
Conditions matter: a revision-specific fact stated universally can be wrong even if its numerical
value came directly from a source. An inference presented as documented fact also has an attribution
error, even when its underlying content earns recall credit.

There is a substantive source inconsistency here. `EVAL-PLAN.md` defines precision in terms of
correct, supported claims and says unsupported extras count against it. The current
`SCORING-POLICY.md` instead defines precision by non-error claims and explicitly reports unsupported
claims separately without counting them as errors. It likewise reports true but underspecified
claims separately. Consequently, this pilot's precision must be read with its unsupported and
partial counts; it does not by itself mean the fraction independently supported by the corpus.

A scored run must identify the exact frozen policy rather than silently blend these definitions.
`spec-verifier` is a source of claim-verification evidence, not an automatic conversion from its
verdict totals into the pilot's claim segmentation and scoring. An unlocatable claimed citation, a
blocked authority, and an unsupported proposition also have different meanings and must not be
collapsed just because none produced a simple pass.

Recall and precision are never averaged. A short document can avoid errors while omitting nearly
everything needed; a comprehensive document can include a fatal false requirement. A combined number
conceals the difference. Report both directions, recall by consequence, unsupported claims, partial
statements, unresolved readings, and the input identities needed to interpret them.

## What is shipped, what is unfinished, and what is proposed

The investigation, authoring, and verification skills are shipped, with checkers and
tests. Existing board specs and verification records show their use. The plugin README lists test
commands. These components provide practical procedures and mechanical checks now; they do not
constitute the entire proposed validation architecture.

The main mechanical tools each have a narrower purpose than "prove this spec":

- [`spec_check.py`](skills/board-expert/scripts/spec_check.py) checks format, references, tag
  placement, selected public-root restrictions, stub resolution, and verification metadata.
- [`anchor_check.py`](skills/anchored-peripheral-spec/scripts/anchor_check.py) resolves citations,
  flags suspect literals and missing support, renders source beside claims, and detects drift.
- [`inventory_check.py`](skills/anchored-peripheral-spec/scripts/inventory_check.py) uses C-oriented
  patterns and device-tree inventory to find omissions and value conflicts, not
  semantic completeness.
- [`ledger_check.py`](evals/enc28j60/ledger_check.py) checks answer-key structure and freeze inputs;
  it is not the scored with-skill/without-skill comparison.

The ENC28J60 evaluation is partly built: corpus, format, ledger, scoring policy, conflict and
adjudication material, and checker exist. The scored comparison has not been run. Current freeze
readiness belongs in the pilot README, ledger, adjudication files, and checker output. The presence
of an answer-key file is neither proof that it is frozen nor a measured result for the skill.

[`VALIDATION-PROPOSAL.md`](VALIDATION-PROPOSAL.md) is a reviewed proposal, not an implementation. It
proposes links from requirements to tests, preserved attempts, separate decisions for spec
readiness, implementation validation, and physical validation, and strict treatment of unresolved
critical evidence. It also proposes test expectations derived independently of generated code,
mutation checks, and hardware observations tied to the actual image and fixture. None should be
inferred from an ordinary verification record's zero-failure summary.

The proposed delivery sequence starts with the blind ledger, then minimal scoring and acceptance
tools, then test contracts and synthetic execution, then separately gated physical work. Full vendor
workflows, feedback automation, and broader evaluation infrastructure are deferred. Fuchsia
integration is a separately scoped follow-on in a companion package. The proposal explicitly does
not authorize implementation or a paid evaluation campaign.

The [continuous review](#continuous-review-keeping-specs-right-as-evidence-changes) layer
(C1–C8) was approved by the user on 2026-09-26; none of it is built yet. What exists is the
loop run by hand in the L02 follow-ons: second independent readings with key-by-key comparison
(AF-1, SR-7), qualified checks (L02d3, QF-1, FC-1, CS-1), versioned spec revisions reaching the
candidate (CF-1, CF-2), and `[emulated]` adopted into the format from use (SF-1). The status
index, the sweep, the deployment manifest, the plugin contract check and the stopping rule are
designed, not built. The layer absorbs decision D6 and pulls forward the record and invalidation half of
M16; replay with archived tools stays deferred.

### Reading sources that disagree

Some discrepancies are historical text lag; others affect interpretation today:

- `EVAL-PLAN.md` and parts of the proposal/review say no ledger exists. The pilot now has
  `ledger.yaml`; existence does not establish freeze completion or a score.
- `SPEC-FORMAT.md` says a stale record cannot merge under default CI, but its own warning rules,
  the plugin README, and `spec_check.py` allow staleness unless `--require-verified` is used.
  A nonzero failure count is an error even when the record is stale.
- `VALIDATION-REVIEW.md` describes the stale-hash check hiding recorded failures. The proposal
  marks that bug fixed, and the current checker checks failures despite a stale hash.
- The scaffold's "always verify" wording also differs from `QUESTIONS.md`, which offers verification later.
  Treat deferred verification as explicitly unverified, not as completion of its quality bar.
- The vendor guide calls same-layer overlay order undefined; the format specifies pointer order.
  Both warn about duplicate overlays for the same target in a layer. Consolidate them rather than
  relying on the disagreement about ordering.
- The evaluation plan and pilot scoring policy disagree about unsupported claims, as explained in
  the precision section. A result needs the locked rule, not an assumed shared definition.

The evaluation files may change during active ledger work, including whether policy-hash checking is
described as pending or implemented. Check the current script and rules together before a freeze.
This document does not resolve that moving work by inventing a completion status.

## Extending the system

For a new board, invoke [board-spec-scaffold](skills/board-spec-scaffold/SKILL.md). Choose the root
and hardware identity, reuse existing SoC/chip/IP specs, and put each new fact in the appropriate
file. Add a board stub only when a named skill entry point is useful. A new spec requires no skill
registration, but a new stub does: the scaffold lists the README and metadata updates, and the
repository registration checker catches missing README entries. Run structural and independent
verification over all roots needed to resolve the new references.

For a vendor overlay, follow [the vendor guide](skills/board-expert/VENDOR-GUIDE.md) and the
scaffold's overlay and vendor-tool templates. Put private resources in an appropriate nonpublic
root, declare it through supported pointers, and use `via:` for access instructions. Preserve the
public baseline and the origins of additions. Test discovery through a report's provenance block;
then verify the overlay under its own root. Do not treat a successful merge as factual adjudication.

For a new peripheral driver spec, use the anchored authoring skill and place the spec in the
repository whose license fits its sources. Resolve the IP and instance first, produce the
programming and OS-integration document, and follow that route's checks. A new generic IP map may
also be needed, but that is a separate reusable artifact. If quality measurement is wanted,
establish a corpus and blind ledger before candidate generation; copying the pilot's categories
without reviewing device-specific requirements does not create an answer key.

## Limits and unresolved boundaries

A spec that passes every check can still be wrong in the same way both readers were wrong.
Independent contexts reduce shared drafting history; they do not eliminate shared assumptions, model
errors, incorrect source documents, or mistakes in extracting a device tree. The review of the
validation proposal gives examples of false requirements surviving through specs and tests.

Verification establishes what claims were supported at a pin, not that they are right now or on
every revision. Spec hashes detect edits only when checked. Source hashes cannot retrieve a missing
document or establish access rights. A maintained branch name is not an immutable source identity,
and moved line numbers are not the only way a claim becomes obsolete.

The current board checker reads verification frontmatter rather than independently redoing the
body's reasoning. `--require-verified` rejects missing or stale records but is not the proposal's
strict acceptance policy for every critical unresolved claim. Some anchor findings are warnings;
inventory omission checking is pattern-based. Passing these programs does not prove completeness.

The files do not establish a scored skill comparison, a working driver produced by this pilot, or a
qualified physical fixture for all proposed validation. They also leave general board/SoC claim
identities, policy placement, record migration, and follow-on hardware setup as proposal choices.
Consult the proposal's open-design section rather than assuming those interfaces exist.

Continuous review, as proposed, narrows but does not close these limits. It can only invalidate
what was recorded: an input missing from a verdict's basis cannot make it stale. A newer model
that agrees with an older one adds repeatability, not truth, and a model-family blind spot
survives every re-reading by that family. The stopping rule deliberately leaves known shortfalls
open; "sufficient for the declared scope" is a statement about that scope and its recorded
evidence, not about the hardware beyond it. A private deployment's results say nothing about
this repository's campaigns, and the reverse.

Finally, no amount of this substitutes for running the driver on the hardware. A test that passes
under one revision, load, or timing condition does not prove a sequence universally unnecessary.
Even a captured target message saying `PASS` is still the target's assertion. The proposed hardware
work calls for observations such as externally received traffic or an instrument reading, tied to a
known device and image. Specifications and their evidence make that work better directed and more
reviewable; they do not perform it.
