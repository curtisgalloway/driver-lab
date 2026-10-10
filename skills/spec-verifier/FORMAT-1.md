<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Spec verifier — format 1 only (retained until SF2-12)

Use this procedure only for roots without `format: 2` and for the remaining
format 1 peripheral specs and reviews. The format 2 procedure is in
[SKILL.md](SKILL.md). Do not mix the two formats in a composition.

The roles, record names and commands below describe format 1 only. Until its
retirement, links to “Board specs” and “Peripheral specs and reviews” select
these sections after checking the root format.

A spec is written once by an author who read the sources as they went. Verification is the separate
pass that re-derives every claim from the authority it cites, in a context that never saw the
author's reasoning, and records the result **outside the spec**, so the record costs no context when
the spec is used. Every spec-creating skill here runs this phase as its last step and points back
here for the re-run: `board-spec-scaffold` for board specs, `peripheral-spec` and
`reference-driver-review` for peripheral specs and reviews. A skill from another repository that
defines its own spec kind may wrap this procedure: it loads this file, adds its kind's section and
rules, and its rules win where the two differ.

## Terms

These are format 1 terms; see the shared [glossary](../../GLOSSARY.md).

- **Claim** — the unit that gets a verdict. For a board spec, one fact bullet. For an anchored
  spec or review, one anchor (`[src:]`, `[tgt:]`, `[impl:]`, `[ref:]`) and the claim it is attached
  to.
- **Source** — what a claim cites: a repository at a commit, a patch series, a document at a URL, a
  device tree file, a databook section.
- **Verdict** — `PASS`, `FAIL`, `UNVERIFIABLE`, `GAP`, or `ADJUDICATE`, per claim.
- **Adjudication** — a decision only a person can make, because two independent readers of the same
  authority reached different answers. An `ADJUDICATE` claim is excluded from the pass/fail counts
  and carried in its own `summary.adjudicate` bucket; it is neither credit nor blame until settled.
- **Verification record** — the file that holds the verdicts, in a `resources/` directory beside
  the spec's root or the spec itself. Not a spec; never loaded by a reader.
- **Verifier** — the subagent that produces the verdicts. A fresh context: the spec, its declared
  sources, and this file. Nothing else.
- **Named pin / license gate** — a spec line naming one of several source trees with its commit
  and SPDX license (`Source pin: linux@<rev> GPL-2.0-only`) / the `anchor_check.py --root` check
  that fails an anchor whose pin's license the spec root's `accepts:` list does not include.
- **Orchestrator** — you. You spawn the verifier, write the record, run the mechanical checks, and
  report. You never read sources and never edit the spec.

## The record

Same frontmatter for every kind; the body's keys differ per kind (below).

```markdown
---
spec: rpi5                          # the spec id, or the spec's basename for kinds without ids
spec_file: rpi5.spec.md             # path relative to the record's parent's parent
spec_sha256: <64 hex digits>        # sha256 of the spec file as verified
verified: 2026-09-18                # ISO date
verifier: <which agent and harness produced this record>
sources:                            # every repo, series, and doc actually consulted
  - name: linux-rpi
    commit: <40 hex digits>
    fetch: ok
  - name: RP1 peripherals datasheet
    url: https://datasheets.raspberrypi.com/rp1/rp1-peripherals.pdf
    fetch: ok
  - name: TF-A Raspberry Pi 5 platform page
    url: https://trustedfirmware-a.readthedocs.io/en/latest/plat/rpi5.html
    fetch: blocked
summary: {pass: 9, fail: 0, unverifiable: 1, gap: 1, adjudicate: 0}
---

# Verification of `rpi5`

- Quick-facts/1 "Boot media and chain": PASS — chain and config.txt role match the Raspberry Pi
  documentation config.txt page; BL31 role matches the TF-A rpi5 platform page.
- Quick-facts/5 "Power": GAP — a TODO-only bullet; nothing to verify.
- Gotchas/2: UNVERIFIABLE — the RP1 datasheet section is cited by number; the PDF fetch was
  blocked, so the section was not read this pass.
- Gotchas/3: FAIL — the spec says the psci node's method is "smc"; bcm2712.dtsi at <commit> says
  "hvc". Proposed correction: change the parenthetical and the claim to hvc, and check the BL31
  page for which conduit it installs.
```

Rules that hold for every kind:

- **One line per claim, every claim.** Gaps get `GAP`; claims whose authority could not be reached
  get `UNVERIFIABLE` with the reason (fetch blocked, NDA, no public authority named); claims two
  independent verifiers read differently get `ADJUDICATE` with both readings.
- **A citation that cannot be located is a `FAIL`**, not `UNVERIFIABLE`: a file that does not exist
  at the recorded ref, a line range that no longer holds the symbol, a page that does not say what
  the claim says, a databook section that does not cover the register.
- **`FAIL` carries the discrepancy and the proposed correction.** The verifier never edits the
  spec. The user, or the creating skill on the user's say-so, applies the fix; then re-run.
- **The record cites; it does not quote.** Describe what was compared and how it differs, by
  anchor, section or file and line; do not paste driver or firmware code into it.
- **Keys survive edits.** Claims are keyed by something stable (section and ordinal, the anchor
  text), never by line number.
- `summary` counts equal the verdict lines, `adjudicate` included (omit the key only when it is
  zero); `spec_sha256` is the spec file's hash at write time, so any later edit makes the record
  visibly stale.

## The procedure

1. **Identify the kind** from the spec: YAML frontmatter with `kind:` or `overlays:` is a board
   spec; `Source pin:` / `Impl pin:` lines and `[src:]`-family anchors mean a peripheral spec or
   review. Resolve a board spec across roots the way `board-expert` § 1 does; a path names the
   others. "Re-verify everything under `<dir>`" means every spec file below it.
2. **Run the kind's mechanical checks first** (below). They are cheap, and a spec that fails them
   is not worth a verifier's time until fixed.
3. **Spawn the verifier**: a subagent with a fresh context, given the spec file, read-only access
   to whatever the spec composes or pins (a board spec's `parts`; a peripheral spec's source and
   target checkouts at their pins), this file, and, for a board spec, `board-expert`'s section 2
   for how sources are cached. Not the author's report, not the previous record, not this
   conversation. Verify several specs in parallel, one verifier
   per spec.
4. **The verifier materializes the sources** it needs: repositories cloned into the cache the spec
   names (or the checkout the pin names) at the recorded ref or commit, series pulled in the form
   their note says works, documents fetched. It records every one under `sources` with its commit
   or URL and the fetch result.
5. **For every claim, in order**: open the cited authority, compare each stated value (address,
   size, interrupt number, cell count, clock name, frequency, ordering, register bit, exception
   level, line range, symbol) with what the authority says, and write the verdict line.
6. **Independent second verifier** where the kind says so (bring-up-critical facts of a board spec;
   the register-map tables of a peripheral spec). Same brief, no shared context. **A disagreement is
   an `ADJUDICATE` item, not a `FAIL`**: the two readers could not settle the question between
   them, which says nothing yet about whether the spec is wrong. Record both readings, and leave
   the claim **out of the pass/fail counts** — it is reported separately and waits for a person.
   Two things follow. If adjudication finds the spec wrong, that is a `FAIL` on the merits, and the
   record is rewritten with the resolved verdict. If adjudication finds the spec stated something
   more definitely than its evidence supports — a claim true of one tree written as true of both,
   an `[inference]` written as though it were read — that is also a `FAIL`, on the definiteness
   rather than on the disagreement. What is never a `FAIL` is the disagreement itself.
7. **Write the record.** Compute `spec_sha256`, fill `verified` and `verifier`, check the summary
   against the body, write the file at the kind's location, replacing any earlier record, and run
   the kind's checker so it is accepted.
8. **Report** the summary and every `FAIL` with its proposed correction, quoted from the record.
   Do not apply corrections. After a fix, run again; the loop ends at zero `FAIL`.

## Board specs

The kind defined by `board-expert/FORMAT-1.md`; this section is the one statement of its
verification procedure, and `board-expert/FORMAT-1.md` § Verification points here.

- **Claims** are the fact bullets of the fact sections (`Quick-facts`, `Gotchas`, and for an IP spec
  `Standards and databook`, `Programming model`, `Known variants and quirks`), each keyed as
  `<Section>/<ordinal> "<bold lead-in>"` (1-based, top-level bullets only, lead-in omitted when
  absent). A gap bullet (`TODO (verify on hardware)` first) is `GAP`.
- **Sources** are the bullet's tag clause: `[DT] (file)` names a device tree in a `repos` or
  `series` entry at its `ref`; `[databook]`, `[standard]`, `[doc]` name a `docs` entry or a document
  id; `[hardware]` names a board and a method; `[press]` names a page and is compared against it like
  any other claim, TODO or not; `[src]` names anchors (`[src:<repo>: path:L1-L2 (symbol)]`)
  into a `repos` entry pinned to a commit, and is verified as the next bullet says; a class an
  extension defines is verified as that extension says; `[inference]` names its
  premises and derivation in its parenthetical, and is verified on whether those premises hold and
  whether the conclusion follows from them; `[emulated]` names a device model, its version and
  run IDs, and is compared against an extract of what those runs recorded (traces, captures,
  logs, verdicts), prepared by the operator, never against the model's source, and fails when it claims more than the runs show or states
  the model's mechanism rather than an observation. `instances:` rows are claims
  too: each `reg`, `irq`, and `clocks` value against the device tree it came from, keyed
  `instances/<name>`.
- **`[src]` facts**, and `[src:]` anchors that are an `[inference]`'s premises, are verified in
  three steps. (1) **The anchors resolve at the pin**: run `peripheral-spec/scripts/anchor_check.py
  <spec> --root <root> --require-license --repo <name>=<checkout>` with one `--repo` per `repos`
  entry the anchors name, each checkout able to reach the entry's `ref` (the checker reads each
  entry with a `ref` as a Source pin; no `Source pin:` line is needed;
  `board-expert/scripts/fetch_src_pins.py <spec> <dir>` makes such checkouts and prints the
  `--repo` values; it fetches `https://` URLs only, and fails on a commit or repository that
  does not exist). An unresolved path, line
  range or symbol is a `FAIL` for that claim, and so is a warning that an anchor's repository was
  not given, until it is given. (2) **The claim matches the anchored lines**: render them with
  `anchor_check.py --show` and judge, as for a peripheral spec, whether the lines support the
  claim; a claim that says what the hardware requires, or that a product runs this code, is not
  supported by `[src]` alone and is a `FAIL` on its class (it should be an `[inference]`). (3)
  **The pin's license is in the root's accepts list**: the entry's `license:` must describe the
  cited files (check the file's notice or SPDX line at the pin) and be accepted by the root's
  `accepts:`; a mismatch with the files, or a `license gate:` error from either checker, is a
  `FAIL`. Record each entry under `sources` with its `commit`.
- **Composition.** The verifier may read the specs a board composes through `parts`, so "see
  `bcm2712`" resolves, but each spec file gets its own record. Overlays are verified under their own
  root, one record each.
- **Two verifiers** for the bring-up-critical facts: the addressing model, the boot chain and entry
  state, and the debug UART bullets of every `soc` spec in the composition, and the debug console
  bullet of the board.
- **Mechanical check**: `board-expert/scripts/spec_check.py <root>... --stubs-from <skills dir>`
  before and after (with the roots an overlay's target lives in, so it resolves). The checker
  accepts a record only when its `summary.fail` is zero: a current record with any `FAIL` is an
  error, the expected result until the spec is fixed and verified again. Once the spec is edited
  the record is stale and reports only that, so a fix can be checked before the next pass.
  Once `FAIL` is zero, the checker must accept the record with no error and no `verification
  stale` warning (`--require-verified` makes a missing or stale record an error).
- **Record location**: `<root>/resources/<name>.verify.md`, where `<root>` is the directory
  holding the root marker `board-specs.yaml` (`specs/` in the spec repositories) and `<name>` is
  the spec file's name without `.spec.md` (one record per spec file, so an overlay and its base,
  or two overlays of one id, in one root never share one). `spec` is the id (an overlay's: the id
  it overlays); `spec_file` is the file's path relative to `<root>`, and the checker rejects a
  record whose `spec_file` names another file.

## Peripheral specs and reviews

The kinds produced by `peripheral-spec` (`[src:]`/`[tgt:]` anchors, `Source pin:` /
`Target pin:`) and `reference-driver-review` (`[impl:]`/`[ref:]`, `Impl pin:` / `Ref pin:`). **Every
anchor is verified back to source**, in two layers:

1. **Resolve every anchor, mechanically.** Run `peripheral-spec/scripts/anchor_check.py`
   in its default mode with the spec's repositories (`--repo` / `--target-repo`, or `--impl-repo` /
   `--ref-repo` for a review) at the pins: every path must exist, every line range be in bounds,
   every symbol be present in or near its range, every hex literal in a claim appear in the lines it
   cites, every `[hw-required]` be backed by a `[doc:]`. **Give every pin its checkout:** a spec
   with several named pins (`Source pin: <name>@<rev> <license>`) needs one
   `--repo <name>=<checkout>` per Source pin (and `--target-repo <name>=<checkout>` per Target
   pin); a pin left without one leaves its anchors unresolved, which the checker reports only
   as a warning, so check the warnings. When the spec lives in a spec root (a
   directory whose `board-specs.yaml` declares `license:` and `accepts:`), run the same command
   with `--root <root> --require-license`, so the record is made under the license gate the
   repository's CI applies: a `license gate:` error is a `FAIL` for that anchor. When the spec
   lists documents in its `docs:` front matter and the files are at hand, add
   `--docs-dir <dir>`: a hash mismatch is a `FAIL` for every claim citing that document. Where
   register headers exist, run `inventory_check.py` too, once per pin whose tree holds them
   (`--repo <name>=<checkout>`; it compares one tree per run): omissions and value mismatches
   against the headers are findings. Any `[stale: was <pin>]` marker is a `FAIL` until a person
   re-verifies the claim and clears it.
2. **Judge every anchor, by reading.** Run the creating skill's own independent verifier as it
   defines it ([peripheral-spec format 1 verifier](../peripheral-spec/FORMAT-1.md#format-1-template-verifier-promptmd), or
   [review format 1 verifier](../reference-driver-review/FORMAT-1.md#format-1-template-verifier-promptmd) for a review): a fresh subagent that
   renders the review sheet with `anchor_check.py --show`, which places each claim beside the
   source lines it cites, reads the main source files in full once, and decides for every anchor
   whether the cited lines *support the claim*, not merely whether they resolve: a range that
   exists but describes a different register, a symbol that is present but whose value the claim
   misstates, an ordering the lines do not establish, all `FAIL`. It keeps that verifier's blind
   re-derivation sample, recomputed counts, and re-established negative claims. `[doc:]` tags are
   checked against the document section the same way a board spec's `[databook]` is. What this
   skill adds is the record: that verifier's `{section, line, anchor, reason}` list becomes
   per-anchor verdict lines, and every anchor it passed gets a `PASS` line too.

- **Claims** are keyed by the anchor text as written (`[src: path:L1-L2 (symbol)]`, or
  `[src:<pin>: path:L1-L2 (symbol)]` with a named pin), plus the `[doc:]` tags; a claim with
  several anchors gets one line per anchor. The record's `sources` lists every pin and every
  registry document.
- **Two verifiers** for the register-map tables (offsets, widths, bit positions), the densest values
  and the place `peripheral-spec` already runs two investigators.
- **Record location**: `resources/<spec-basename>.verify.md` in a `resources/` directory beside the
  spec, or, when the project already keeps `docs/provenance/` for the spec's sidecars, there as
  `<spec-basename>.verify.md`; say which in the report. `spec_file` is relative to the record's
  parent's parent. Save the `anchor_check.py` and `inventory_check.py` reports beside it.
- The record complements `anchor_check.py --drift`: drift detection says which anchors need
  re-review when the tree moves; this record says whether the claims were right at the pin.

## Rules

- **You never read sources.** The verifier subagent does, in its own context.
- **You never edit a spec.** A `FAIL` is a finding with a proposed fix, not a change.
- **The record is the only output.** Nothing from the verifier's work goes anywhere else, and no
  reader loads the record's body: `board-expert` reports a spec's `verified` date and `summary`
  from the record's frontmatter only.
- **Fresh context, every time.** A re-run gets a new verifier that has not seen the old record.
- Commit or stage the record if the project commits them; do not push unprompted.
