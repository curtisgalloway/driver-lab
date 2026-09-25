<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Evaluating the driver-spec skills

How the driver-specification evaluation lands in this repository: what gets built, in what order,
and which of its measurements this plugin's existing machinery can and cannot make. The evaluation
design is the [2026-09-18 consensus](evals/EVAL-CONSENSUS-2026-09-18.md) of two reviewers, kept
verbatim as a record; this document carries its decisions forward and records where the work has
since departed from it.

The evaluation itself asks one question — **does `cleanroom-spec` produce a hardware contract
precise and complete enough that a different implementer can write a working driver and meaningful
tests from it, without ever reading the original source?** Everything below is in service of
answering that with numbers rather than impressions. Four things are measured separately, because
a spec can do well on one and badly on another:

- **Source comprehension** — does the spec state what the driver and hardware actually do?
- **Documentation integration** — does it combine the manual, errata and driver into one
  consistent account, including facts only one of them holds?
- **Applicability reasoning** — does it say which device, revision and mode each fact applies to,
  and keep what is known apart from what is inferred?
- **Downstream usability** — can a different implementer build a working driver and meaningful
  tests from it?

## Terms

This document borrows vocabulary from three places. Definitions first, because a reader who has not
used these tools cannot follow the plan without them.

- **Gold ledger** — the answer key. A list of atomic hardware requirements for one device, each
  written down *before anyone looks at the specification being graded*, derived only from the
  adjudicated reference corpus. "Gold" means it is the standard the candidate is measured against,
  not that it is infallible.
- **Candidate spec** — the document under evaluation: what `cleanroom-spec` produced for that
  device on a given run.
- **Reference corpus** — the frozen set of sources the ledger is authored from: datasheets and
  errata at named editions, a driver at a pinned commit, standards documents. Frozen means every
  item is pinned by hash, commit or document edition so the same inputs can be reconstructed later.
- **Recall** — of the requirements in the gold ledger, what fraction does the candidate actually
  cover? This is the omission measure.
- **Precision** — of the claims the candidate makes, what fraction are correct and supported? This
  is the error measure. A document can score perfectly on one and badly on the other; they are
  reported separately, never averaged.
- **Ablation** — a comparison run with something removed, here the skill itself. The "without
  skill" arm is the baseline the "with skill" arm is measured against.
- **`claude plugin eval`** — the harness that runs a case against this plugin and against a
  no-plugin baseline and reports the difference. Cases live in `evals/<case>/`.
- **Held-out test** — a device kept out of all skill tuning and run only after the skill is
  frozen, to see whether improvements transfer or merely fit the devices they were tuned on.
- **Corroborating implementation** — another OS's driver for the same device (Zephyr, NuttX,
  FreeBSD and so on). Evidence of completeness only: it can reveal a requirement the reference
  driver misses, but it is not an authority on the hardware.
- **`cleanroom-spec`** — the skill that produces a clean-room driver spec. The thing being
  evaluated.
- **`spec-verifier`** — the skill that re-derives a spec's claims from the sources it cites and
  writes a verdict per claim into a record outside the spec. Not the thing being evaluated; a tool
  used by the evaluation.
- **Provenance tag** — the marker on each fact saying where it came from: `[databook]`,
  `[standard]`, `[DT]`, `[source-observed]`, and `[inference]` for a fact concluded rather than
  read. Defined in `skills/board-expert/SPEC-FORMAT.md` and used by both spec kinds.
- **Adjudication** — a human decision resolving a conflict two readers could not settle between
  themselves. An adjudication item is not a pass and not a failure; it is a question waiting for a
  person.

See the repository [glossary](GLOSSARY.md) for shared terms.

## Devices, in order

The consensus fixed a sequence of four devices, each chosen for what it can test. A fifth, the
Intel e1000 in QEMU, was added on 2026-09-22 and is the current work. It does not replace any of
the four.

| Device | Role | Evidence available | Status (2026-09-25) |
|---|---|---|---|
| ENC28J60 B7 (EREVID 0x06) | **Pilot.** Calibrates the ledger, scoring and test quality. A method check, not evidence about complex SoC drivers | Frozen DS39662E and DS80349C; SPI traces; a physical fixture | Corpus and ledger frozen (2026-09-20); practice run done; L01 rebuilt the Linux driver from a spec ([L01](evidence/L01.md)). L01's hardware unit waits on wiring a module to a Raspberry Pi 4. The paired with/without-skill run is pending |
| Intel e1000 (82540EM) in QEMU | **Added.** Reconstruction on a device with DMA descriptor rings, compared against the reference without a bench ([design](QEMU-DIFFERENTIAL.md)) | Intel 8254x manual; Linux driver; QEMU device model. Results are `[emulated]` evidence only | L02: spec written and verified, candidate driver written, harness built; L02d2 in progress, then the differential run (L02f) |
| One NXP FEC/ENET target | **Main benchmark.** Host DMA descriptors, SoC dependencies, variant-specific behavior, a replacement driver that runs | Matching SoC reference manual and errata edition; Linux and corroborating drivers; QEMU for modeled behavior only | Not started; the target is chosen later (see *Deferred*) |
| OpenTitan UART at `earlgrey_1.0.0` | **Held-out transfer test.** Does improvement carry over once skill tuning stops? | Adjudicated docs and pinned RTL; an independently prepared Verilator harness | Not started. The skill is frozen before this run, and its scoring material stays out of every tuning input |
| Intel 82574L (`e1000e`) | **Optional extension.** Driver and feature complexity | Matching Intel docs and QEMU `e1000e`; separately scoped errata checks | Not started; L02's harness may be extended to it later |

OpenTitan is an executable reference: it can show a driver working against the RTL, but it is not a
substitute for testing workarounds on commercial silicon. The e1000 unit answers two questions L01
left open — whether the process holds on a harder device, and whether the reference comparison
can run without a bench — and nothing it shows is a claim about real silicon.

## The documentary measurement, in four steps

The order matters more than any individual step, because the independence of the answer key is what
makes the numbers mean anything.

1. **Author and freeze the gold ledger**, from the adjudicated reference corpus only, without
   seeing any generated specification. Each requirement gets a **stable ID that does not depend on
   any document's section structure** — neither the corpus's nor a candidate's. The ledger is
   frozen before step 2 begins.
2. **Generate the candidate specification.** This is the "with skill" arm; the baseline arm runs
   the same model, sources, tools and budget without the skill.
3. **Coverage, gold → candidate.** Walk the ledger. Every applicable, recoverable requirement must
   map to sufficient evidence in the candidate, or be scored missing or partial. **The weighted
   recall denominator is the frozen, in-scope ledger** — never the candidate's section list, and
   never its TODOs. A candidate that omits an entire section still incurs every omission in it.
4. **Claim verification, candidate → sources.** Check every factual claim the candidate makes,
   *including claims that have no ledger row*. An extra claim is not wrong for being extra, but it
   still needs support, and an unsupported one counts against precision.

Steps 3 and 4 run in opposite directions and measure different things. Collapsing them loses the
recall number entirely — see "Why the answer key cannot come from the verifier" below.

## Downstream measurement: reconstruct a driver

The [reconstruction protocol](RECONSTRUCTION.md) adds an implementation test using the exact
frozen specs from both generation arms. Fresh isolated implementers build replacement drivers
on the selected reference OS; evaluators then compare requirements and observable behavior with
the original. Linux is an initial coverage assumption to verify per device, not a guaranteed
best reference. BSD or another OS may be selected. Cross-OS porting is a separate experiment.

Freeze the scope, independent checks, and implementation conditions before inspecting paired
candidates. Keep the original source, hardware documents, answer key, and review feedback out
of implementer access. Report reconstruction outcomes and failure attribution separately from
recall and precision; neither a successful driver nor a coding failure overrides document scores.

The [ENC28J60 run guide](evals/enc28j60/RECONSTRUCTION-RUN.md) is preparation guidance only.
No reconstruction experiment has run and no execution runner is implemented. The frozen
corpus already selects Linux for this pilot; that choice does not constrain future devices.

## Protocol common to every device

- **Ledger rows.** Atomic requirements, authored independently of any generated spec, then
  reviewed and adjudicated. Each records applicability (device, revision, mode), preconditions,
  behavior, timing and order, side effects, an evidence citation, a confidence and a verification
  method, and carries one label: documented hardware requirement, observed software behavior,
  inference, implementation choice, or unresolved conflict. Unresolved rows are excluded from
  binary scoring. The ENC28J60 form is [LEDGER-FORMAT.md](evals/enc28j60/LEDGER-FORMAT.md).
- **The primary comparison** is with and without the skill, holding the model, sources, tools and
  budget fixed. Memory-only, driver-only and datasheet-only runs are diagnostics, not arms. A high
  baseline score means limited headroom, not proven memorization; 80% is a planning heuristic for
  "near the ceiling", and past it the informative measures are precision, applicability,
  traceability and test quality rather than recall.
- **Two tracks stay distinct:** reconstruction (the driver plus selected document sections) and
  full-documentation integration. A withheld document can hold facts or mechanisms the supplied
  evidence cannot reveal, so observable behavior is scored separately from mechanism, and
  justified uncertainty scores above a confident guess.
- **Scoring.** Recall and precision are reported separately, by category and severity, after
  compound claims are split. The consensus set starting gates of at least 95% weighted recall, at
  least 98% precision, and no omitted required workaround in scope, to be recalibrated after the
  first reviewed run. The ENC28J60 pilot adopted a stricter rule instead: all 162 eligible rows
  are mandatory for documentary acceptance, and every critical claim must pass with two reviewers
  ([SCORING-RUN.md](evals/enc28j60/SCORING-RUN.md#strict-policy-and-limits)). Each later device
  fixes its own acceptance policy before its candidates are generated.
- **Checks** are built from adjudicated sources, never from the generated spec. A deliberate
  defect (a flipped dummy read cycle, a wrong wraparound, a reordered recovery step) must make
  each check fail before the check is trusted; L02's planted defects are this step.
- **Pinning.** Source commits, file hashes, document IDs and editions, generated headers and
  configuration are all recorded.
- **Corroborating implementations** — Zephyr, NuttX and EtherCard for the ENC28J60; FreeBSD,
  NetBSD, NuttX, U-Boot and QNEthernet for the FEC; Tock for OpenTitan — count only after their
  lineage and hardware-version compatibility are checked.

## What an executable result establishes

| Evidence | Establishes | Does not establish by itself |
|---|---|---|
| QEMU boot | The image boots | Network operation or replacement-driver correctness |
| QEMU traffic tests | Tested behavior works against that model | Silicon timing errata or unmodeled behavior |
| SPI or register trace assertions | The observed sequence satisfies the checked requirements | Complete hardware correctness |
| Ordinary physical traffic | Basic operation on the identified device | Recovery from faults never triggered |
| Fault injection, or reproduction on affected silicon | Behavior under the exercised conditions | Coverage of errata that were not triggered |
| Pinned RTL simulation | The digital implementation under test conditions | Analog or fabrication-dependent properties |

Known limits, recorded before they can mislead a result:

- QEMU's `imx_fec.c` transmits on a TDAR write and clears the register at once, so the TDAR race
  that ERR006358's recovery exists for cannot be observed there.
- QEMU's `test_imx8mm_evk.py` checks a console string, not DHCP; networking bring-up on that
  machine is separate work.
- Every e1000 result is consistent-with-the-model evidence; the model is a third implementation
  of the manual, not the silicon ([QEMU-DIFFERENTIAL.md](QEMU-DIFFERENTIAL.md)).
- Physical-fixture coverage is stated test by test, with the silicon revision confirmed.

## Why the answer key cannot come from the verifier

`spec-verifier` keys its claims to the candidate's own structure: for a clean-room spec,
`<Section>/<table>/<row name>` and `<Section>/<step number>`. A requirement the candidate never
states therefore never becomes a row, and never gets a verdict. Its `GAP` verdict does not close
the hole — `GAP` fires on a bullet whose author already wrote `TODO`, which is a disclosed gap, not
an undisclosed omission.

So `spec-verifier` answers "are the claims that are present correct?" It cannot answer "which
required claims are absent?" That makes it exactly right for step 4 and structurally unfit for
step 3.

This is a limitation of the mechanism, established by reading how it keys claims. The first
end-to-end run (2026-09-18, `pixel10` and `tensor-g5`, 87 claims, 10 FAIL) is consistent with it —
every failure was a wrong value, a wrong scope or an unlocatable citation, and none was an omission
— but a run finding no omissions does not by itself prove it cannot find them. The keying does.

**Sharing an independently authored ledger between the evaluator and the verifier is fine. Deriving
that ledger from the specification being evaluated is circular.** The two passes can eventually run
against one gold ledger without compromising independence; what must never happen is the answer key
being read off the answer.

## Build order

Step 3 as a separately reviewed evaluation and step 4 on the existing verifier is the initial
implementation. Extending `spec-verifier` to run both directions against one ledger is the intended
integration, and **ledger construction does not wait for it** — stable requirement IDs and an
explicit mapping are what make the later merge possible, and both are cheap to design now.

| Phase | What | Blocks on |
|---|---|---|
| 1 | Corpus manifest for the ENC28J60 pilot: driver and header hashes at v6.12, document editions and hashes, the edition-specific errata map | nothing |
| 2 | Gold ledger authored blind, with stable IDs; conflict log; second reviewer adjudicates | phase 1 |
| 3 | `claude plugin eval` case: with-skill and without-skill arms plus diagnostics | phase 1 |
| 4 | Coverage scoring (gold → candidate) as a reviewed manual pass | phases 2 and 3 |
| 5 | Claim verification (candidate → sources) via `spec-verifier` | phase 3 |
| R1a | Freeze reconstruction brief, scope, environment recipe, isolation, independent check definitions, and attribution rules | phases 1–2; before inspecting paired candidates; no hardware required |
| R1b | Implement and qualify executable checks, reference results, and mutation tests | R1a; hardware where needed; independent of candidates and before inspecting their execution results |
| R2 | Reconstruct a driver from each frozen spec under identical implementer conditions | phase 3 and R1a; build environment available; R1b is not required for partial build/source-review results; can overlap phases 4–5 without review feedback |
| R3 | Compare frozen implementations, execute independent checks, and attribute failures | R2 and R1b for executed comparisons; physical results require fixture |
| 6 | Extend `spec-verifier` to score both directions against the ledger | phases 4 and 5, and a decision that it earns its cost; lower priority than reconstruction, not hardware-gated |

Prioritize the reconstruction track ahead of optional phase 6 integration, but do not make
fixture delays a hard dependency for that tooling decision. R1a may be qualified
with a separately labeled procedure trial using the old practice candidate; that trial cannot
be one arm of the paired experiment. Generate the pair only after the protocol is frozen.
Generation, documentary review, reconstruction, execution, and optional repair need separate
budget estimates and run authorization. No paid benchmark is launched by adopting this plan.
The existing practice candidate's fresh documentary re-review remains independent work.
Evaluator-authored reconstruction checks test driver behavior; the broader objective of an
implementer authoring meaningful tests from the spec remains unmeasured by this stage.

The hardware purchase in the consensus's first action — two ENC28J60 modules, about $4 each — was
made on 2026-09-19; as of 2026-09-25 L01's hardware unit waits on wiring one to a Raspberry Pi 4.
Nothing above waits for it. Phases 1 through 5 are all reachable without the physical fixture;
what the fixture adds is execution evidence for the boundary and recovery checks, and its absence
is recorded test by test rather than papered over. Until the fixture works, a test that wants it is
recorded as awaiting it — not skipped, and not scored as though it had run.

## Three changes this requires in the existing skills

Each is a change to shipped text, listed with what it breaks if left alone. **Changes 1 and 2
landed with the verification phase** (PR #53); they are kept here because the reasoning is what
justifies them, and a reader asking why the tag set has an `[inference]` class or why a
disagreement is not a failure should find the answer in one place. Change 3 is implemented;
the paired run remains pending.

### 1. A verifier disagreement is an adjudication item, not a failure — *done*

`skills/spec-verifier/SKILL.md` used to say, of the two-verifier rule, that "a disagreement is a
`FAIL` with both readings recorded until a person resolves it."

That conflates two different things. A disagreement means the two readers could not settle the
question between them; it does not establish that the specification is wrong. Correct handling:
record both readings, mark the claim an **adjudication item**, and **exclude it from binary
scoring** while reporting it separately. If adjudication then shows the specification stated
something more definitely than its evidence supports, *that* counts against precision — but on the
merits, not on the disagreement.

Left alone, every unresolved reading disagreement inflates the failure count and depresses
precision for a reason that has nothing to do with the document's quality.

First case in the wild: `specs/resources/tensor-g5.verify.md`, Quick-facts/1, where two verifiers
read the production device tree's bus structure differently — one finding translating `simple-bus`
wrappers between the root and several peripherals, the other finding every peripheral a direct
child of the root. It was recorded `FAIL` under the old rule and is now recorded `ADJUDICATE`, with
both readings kept and the claim excluded from the pass/fail counts. Nobody has settled it yet;
that is the point of the bucket.

### 2. An explicit `[inference]` provenance tag — *done*

The evaluation labels every ledger row as one of: documented hardware requirement, observed
software behavior, inference, implementation choice, or unresolved conflict. Four of the five have
homes in the existing tag set — `[databook]` and `[standard]`, `[source-observed]`, the target-OS
mapping section, and an adjudication item.

**Inference has no home.** Nothing currently distinguishes "the hardware requires this" from "the
driver does this, and I concluded the hardware requires it." That distinction is the whole substance
of the consensus's first correction: `FEC_QUIRK_ERR006358` is set in one table and never tested,
while the recovery path runs unconditionally, so a reader who grades the flag table instead of the
control flow reaches a confident wrong answer. Without an inference tag there is nowhere to record
that a claim was reasoned rather than read.

An `[inference]` fact should carry: its **premises** (what was actually observed), the
**derivation** (why the conclusion follows), a **confidence**, and a **verification method** (what
would settle it — usually hardware). This is strictly more than the other tags carry, because an
inference is the one class whose support is an argument rather than a citation.

### 3. Recall needs a denominator the candidate cannot influence — *implemented*

The independently authored ENC28J60 ledger is frozen. `evals/enc28j60/score.py` computes recall
from reviewed fact dispositions against its fixed denominator, and precision from the candidate's
separate claim inventory. Its IDs come from the corpus rather than document headings. Stage A
adds strict documentary acceptance and preserved attempts; see `evals/enc28j60/SCORING-RUN.md`.
The semantic passes in phases 4 and 5 remain reviewer work. Synthetic tests establish the
scorer's arithmetic and gates. The [first practice run](evals/enc28j60/PRACTICE-RUN.md) exercised
generation, both review passes and replay, with blocked acceptance and an incomplete inventory
audit. Phase 3's paired evaluation and phase 6 integration remain pending.

## The consensus's five corrections, and where each lands

Both reviewers accepted all five into the shared answer key. The Linux line numbers are from
`master` when the consensus was written, not a pinned commit; recheck each against the corpus pin
before it is scored.

- **Correction 1 — grade the control flow, not the flag table.** `FEC_QUIRK_ERR006358` is set only
  in `fec_imx6q_info` (`fec_main.c:125`) and never tested, while `fec_enet_tx_queue()` performs the
  TDAR recovery (`:1714`) unconditionally. A reader who grades the flag table reaches a confident
  wrong answer. Already expressible: `cleanroom-spec`'s required structure marks
  `[source-observed]` orderings "order not known to be required" and `[source-observed]` constants
  "re-derive on hardware". The FEC erratum-to-code pairs become register-map and init-sequence
  content once the target SoC is frozen. This is the sharpest probe in the benchmark and is scored
  explicitly rather than folded into a general precision number.
- **Correction 2 — absence from a vendor document does not prove the device unaffected.** Linux
  applies the ERR007885 workaround to the i.MX6SX, 6UL, 8MQ, 8QM and S32V, but the vendor confirms
  it only in IMX6SXCE. The ledger keeps three separate applicability columns (vendor-confirmed,
  implementation-observed, unresolved), and an unresolved discrepancy never scores as a proven
  contradiction.
- **Correction 3 — related IP is not an interchangeable reference.** The RT1060 reference manual
  and the Teensy 4.1 may support an explicitly bounded portability experiment; they are not the
  authority for an i.MX6 or i.MX8M contract. This matches the rule that a spec may not silently
  compose another part's facts: anything borrowed across parts needs a reviewed equivalence
  argument per tested behavior.
- **Correction 4 — an erratum scoped to one part number.** Intel's erratum 19 applies to the
  82574IT only, but Linux sets `FLAG2_CHECK_PHY_HANG` for every 82574 (`82571.c:2014`) because the
  L and IT share a device ID. For an 82574L target that is observed software behavior, not a
  hardware requirement: an `[inference]` versus `[databook]` distinction, recordable since change 2
  landed.
- **Correction 5 — edition-specific errata identifiers.** DS80349C lists the ENC28J60 reset and
  CLKRDY issue as issue 2; the Linux comment's "#1" is recorded literally, not resolved against an
  assumed edition. In the corpus manifest, every errata reference carries its document edition.

## Deferred, and deliberately so

The FEC target SoC and revision are chosen only once the matching reference manual, errata edition
and a demonstrated QEMU network setup are in hand. Qualification order:

1. **i.MX6Q on QEMU's `sabrelite`** — IMX6DQRM Rev. 6 and IMX6DQCE Rev. 7, with documented
   erratum-to-code pairs; needs a cross-built `imx_v6_v7_defconfig` kernel.
2. **i.MX8M Mini on `imx8mm-evk`** — a stock Debian image boots; the errata content is not yet
   corroborated.

Commits and hashes are frozen at that point. Downloading the candidate reference manuals and
errata (a free NXP account) can happen any time, so phase 2 of the benchmark does not wait on it.
Nothing above depends on the choice; the ENC28J60 pilot exists to calibrate the ledger, the
scoring and the test quality before the harder target is touched.

The pilot is a method check, not evidence about complex SoC drivers. Any claim about how the skill
performs on those waits for the main benchmark.
