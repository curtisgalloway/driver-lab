# driver-porting

Skills for writing and reviewing device-driver specs from source you may cite:

- peripheral specs and reviews for source you may cite (GPL-2.0, BSD, MIT, Apache, or your
  own code), published where their license fits,
- board experts that supply the per-SoC facts those specs need.

**Scope:** this project's goal is generating hardware specs and measuring and maintaining their
quality. Writing a driver for a particular target OS is not, and neither is bringing up a
particular board: a separate bring-up project installs these skills and uses them there to
write specs for its boards and Fuchsia drivers from them. A driver written from a spec, such as
the Linux candidates in the e1000 and ENC28J60 campaigns, is used here as one quality signal for
the spec. See [DESIGN.md's scope section](DESIGN.md#scope-specs-and-their-quality).

## Why this exists and what it is not for

Agents write drivers better from a spec than from a pile of source: a spec states the register
map, the init order and the quirks once, with a citation for each. This project makes those
specs and checks them. Terms used below: a *spec* is that per-device or per-board description;
an *anchor* cites the exact source lines (at a pinned commit) or document page a fact came from.
Full definitions are in the [glossary](GLOSSARY.md).

- **Published specs say what they derive from.** A spec that cites GPL code is a derivative of
  that code and is published under the GPL, in its own repository. Specs built only from
  datasheets, and specs citing BSD, MIT or Apache code, go in two other repositories under
  licenses that fit. One rule decides: a spec lives in the most restrictive repository among the
  sources it anchors to, and each repository's CI runs a check (the license gate) that fails a
  spec citing a source the repository does not accept. The three repositories are
  `hardware-specs-gpl`, `hardware-specs-docs` and `hardware-specs-permissive`; see the
  [license-split design](docs/LICENSE-SPLIT.md).
- **Every claim is checkable.** AI-written documentation is only as good as its checks. Every
  fact in a published spec carries an anchor, a checker resolves every anchor at its pinned
  commit, and an independent verifier re-derives the claims from the cited lines. A reader can
  open the spec and the source side by side.
- **Datasheet-based specs paraphrase and cite.** They quote sparingly and point at the section or
  page, the usual practice for working from a vendor's documents.
- **The clean-room method is published separately, and its output never is:** [cleanroom-skills](https://github.com/curtisgalloway/cleanroom-skills) holds the skills for writing a spec and a driver without the writers reading the original source, and its README says why they are not a way to launder GPL code.

Not for: publishing specs derived from NDA or vendor-licensed material; legal advice about any
of the above (none of this has had legal review); or writing a driver for a particular OS or
bringing up a particular board, which happen in projects that use these skills.

## Which one do I want?

| Situation | Skill |
| --- | --- |
| You may cite the reference driver (GPL-2.0, BSD, MIT, Apache, or your own code), and you want a spec whose every fact points back at the code, published where its license fits | `peripheral-spec` |
| A driver exists and you want it checked against the upstream, vendor, or original implementation | `reference-driver-review` |
| You need memory maps, boot chains, clocks, or interrupt details for a specific board | `board-expert`, for any board with a spec (none ship today; see `board-spec-scaffold`) |
| You have a hardware question and the answer will be published in a spec repository, so each source you cite must be one that repository's license accepts | `hardware-investigator` |
| You need a board expert for a board that does not have one yet | `board-spec-scaffold` writes the spec and stub; `board-expert` does its best without one |
| You want a spec checked against every source it cites, or re-checked after the sources moved | `spec-verifier`, for board specs and peripheral specs and reviews alike |

## Installing

### Claude Code

```
/plugin marketplace add curtisgalloway/driver-lab
/plugin install driver-porting@driver-lab
```

Add the marketplace once per machine. `driver-lab` is its name, set in
`.claude-plugin/marketplace.json`. Outside a session, run the same commands as `claude plugin
marketplace add ...` and `claude plugin install ...`. For a local clone, pass its path to
`marketplace add`. Update later with `/plugin marketplace update driver-lab`.

If you already use the `curtisg-skills` marketplace from
[public-skills](https://github.com/curtisgalloway/public-skills),
`/plugin install driver-porting@curtisg-skills` installs the same plugin from this repository;
there is no need to add a second marketplace.

### Codex

```
codex plugin marketplace add curtisgalloway/driver-lab
codex plugin add driver-porting@driver-lab
```

Update later with `codex plugin marketplace upgrade driver-lab`.

### Other agents

For Antigravity and other harnesses that read skill directories, clone the repo and link each
skill you want from `skills/<name>` into your skills root. The
[public-skills README](https://github.com/curtisgalloway/public-skills#installing) has the
paths for each harness.

## Peripheral specs and reviews

- **`peripheral-spec`**: a per-peripheral spec for driver source you may cite. Its
  placement rule and "which repo does my spec go in?" table say which spec repository's license
  fits the sources a spec anchors to.
  - Every source-derived fact carries a `[src: path:L1-L2 (symbol)]` anchor at a pinned
    commit. A reviewer can check the spec against the code, and the checker can tell which
    claims need re-reading when the tree moves.
  - Ships `scripts/anchor_check.py` (stdlib plus markdown-it-py 4.2.0, through `mdtokens.py`): resolves anchors against one or several
    named, licensed pins, renders a claim-vs-source review sheet with `--show`, detects and
    rewrites drift with `--drift REV --rewrite`, gates pin licenses against a spec root's
    accepts list with `--root DIR`, and checks named document anchors against the spec's
    `docs:` registry (with file hashes under `--docs-dir`). Also ships `scripts/inventory_check.py`, which finds omissions
    and value mismatches against the register headers.
  - Not a way to write a driver under a license the source's terms do not permit, and not for
    NDA source: a peripheral spec is a derivative of its source by design.
- **`reference-driver-review`**: reviews a driver implementation against a reference
  implementation of the same hardware (the upstream kernel driver, the vendor BSP, or the
  original a port was made from). Produces an anchored findings report.
  - Findings cover missing init steps, wrong constants, absent errata workarounds, and
    ordering and timing divergences. Each is cited to the file:line on *both* sides at pinned
    commits (`[impl:]`/`[ref:]`).
  - Defaults to the driver in the current directory, and finds the reference through a
    matching board-expert skill or by asking.
  - The reference is evidence, not truth: the databook breaks ties.
  - Reuses `peripheral-spec`'s checkers, so implementation-side anchors get drift
    tracking as fixes land. Output is a review, never driver code.
- **`hardware-investigator`**: answers one board or peripheral question as anchored facts, ready
  for `peripheral-spec`.
  - Reads the target root's accepts list first, gets the map from `board-expert`, and checks each
    source's license against the list **before** reading it for evidence. A source the root does
    not accept is refused with the reason, and the investigator stops rather than cite it.
  - Ships `scripts/license_gate.py` (stdlib-only), which prints a root's accepts list and
    accepts or refuses SPDX expressions with the rule `anchor_check.py --root` applies later, and
    a worked example (`WORKED-EXAMPLE.md`) on `board-expert`'s fixture: one run on an accepting
    root, one that refuses and stops, one that refuses a source and goes on with another.
  - Facts only: generating a whole spec is `peripheral-spec`'s job.

## Board experts

Board experts supply the per-board map and the sources and datasheets to cite. `board-expert`
carries its own investigation method: pin every tree, device trees first, cite documents, record
where each fact came from.

The map lives in **board specs**: one Markdown-with-frontmatter file per board, SoC, or
companion chip.

- Specs are *composed*: a board names its SoC and chips as `parts`.
- Specs are *overlaid*: vendor and bench-local material sits in separate roots and merges in
  a fixed layer order.
- A spec carries cited facts, not source, so it may live in the target OS tree next to the
  board code it describes, or in a spec repository whose license fits the sources it cites. The reference source stays in the expert's out-of-tree cache.

`board-expert/SPEC-FORMAT.md` is the contract. `scripts/spec_check.py` (stdlib plus markdown-it-py 4.2.0, tests
under `tests/`) enforces it: required keys per kind, every reference resolving, instance
shapes, the tag clause at the end of every fact, nothing internal under a public root, and
every stub's id resolving (`--stubs-from` finds the stubs by their "stub over" sentence).

- **`board-expert`**: the reader.
  - Resolves a spec by id, or by the board/SoC names in the question, across every spec root
    it can see: its own `specs/`, roots declared by project or vendor skills, a root at the
    checkout, and the user's local root.
  - Composes and overlays the spec, clones the sources it names into the cache, and answers
    with its own method.
  - Best-effort when no spec exists, with a suggestion to scaffold one.
  - An IP block (`dwc3`, `pl011`) resolves *anchored* through a board's `instances:` table
    and kernel tree, or *generic* from mainline at head plus the public standards.
  - Ships `specs/`, the public root. It is empty for now: the earlier board, SoC, chip, and IP
    specs and their per-board stubs were removed, to be regenerated with the current skills.
  - Also ships `QUESTIONS.md`, the structured question catalog and the `Needs decision`
    protocol every skill here follows instead of guessing; and `VENDOR-GUIDE.md`, how a
    vendor adds overlay roots, wraps internal tools as skills, and keeps internal material
    out of public roots.
- **`board-spec-scaffold`**: writes a new board spec (board, SoC, chip, or IP block) in the
  format `board-expert` reads.
  - Optionally adds a thin `<board>-expert` stub, a vendor overlay, a `<vendor>-board-tools`
    skill for a vendor's internal resources, or a new spec root in a source tree.
  - Runs an interview for the hardware's identity, root, sources, citations, cache name, and
    quick-facts, then an optional research-fill by a subagent that loads `board-expert`. Every
    artifact has a template under `templates/`.
  - Its last step is the verification phase. Authoring only: it reads no source and answers
    no hardware questions itself.
- **`spec-verifier`**: re-derives a spec's claims from the sources it cites, in a fresh
  verifier context, and writes a verification record outside the spec
  (`<root>/resources/<name>.verify.md` for a board spec, named for its file; a `resources/` sibling or the
  project's `docs/provenance/` for the others). One procedure, with a section per kind:
  - *Board specs*: every tagged fact against its device tree, databook, or document; two
    independent verifiers for the addressing model, entry state, and debug UART.
  - *Peripheral specs and reviews*: `anchor_check.py` resolves every anchor at the pin, then the
    creating skill's own verifier judges whether the cited lines support each claim; one
    verdict per anchor.

  It never edits a spec. A `FAIL` carries the proposed correction, and re-running is the
  loop. The checker reads the record's frontmatter: unverified and stale are warnings, a
  recorded `FAIL` is an error, and `--require-verified` makes the warnings errors too.

- **`spec-format`** (reference, being built): spec format 2, facts as YAML records validated
  by JSON Schemas ([design](docs/SPEC-FORMAT-V2.md), [plan](docs/SPEC-FORMAT-V2-PLAN.md)). So far
  its strict loader, schemas, `spec.py validate` and `spec.py check` (composition, references
  and the license gate); the skills above still read format 1.

The Fuchsia-specific skills that consume these skills live in
[curtisgalloway/fuchsia-skills](https://github.com/curtisgalloway/fuchsia-skills) and hand
off to these by name.

## Evaluating spec quality

- [Faster driver development with evidence we can test](DRIVER-QUALITY.md): the problem, the
  proposed workflow, and how independent checks could reduce human review while improving
  driver quality and test coverage. Written for programmers new to driver development.
- [Evaluation plan](EVAL-PLAN.md): measures both document quality and downstream usability.
- [OS-neutral reconstruction protocol](RECONSTRUCTION.md): how isolated implementers build
  drivers from generated specs, and how evaluators compare them with the selected reference.
- [ENC28J60 pilot](evals/enc28j60/README.md): documentary scoring tools and a paired-run
  protocol. Paired generation and reconstruction remain pending; its
  [reconstruction run guide](evals/enc28j60/RECONSTRUCTION-RUN.md) lists the preparation
  still needed.
- [Implementation plan for L01, L02 and continuous review](IMPLEMENTATION-PLAN.md): the L01
  Linux driver pass, the L02 e1000 QEMU differential campaign and the CR milestones, as
  session-sized units with status, dependencies and review gates.
- [Deferred plan](DEFERRED-PLAN.md): trial preparation, paired evaluation, test quality,
  companion-skill validation, and final verification (milestones M01–M17 and P01).
- These plans, the evaluation plan, the reconstruction protocol and [`evals/`](evals/README.md)
  are a frozen archive since the [license split](docs/LICENSE-SPLIT.md): kept as history, still
  checked by CI.

Evaluation terms are defined in the repository [glossary](GLOSSARY.md).

## Tests

```bash
python3 -m unittest discover -s skills/board-expert/tests -v
uv run --with markdown-it-py==4.2.0 python3 skills/board-expert/scripts/spec_check.py \
  skills/board-expert/specs \
  --stubs-from skills
```

Add `--require-verified` to make a missing or stale verification record an error rather than
a warning (CI keeps the default). The checker's last line names the parser it ran.

CI has no PyYAML, so CI and the plain `python3` commands above exercise the checker's own
subset parser. To exercise the PyYAML path as well, run the tests and the checker once under
a Python that has it, for example
`uv run --with pyyaml python -m unittest discover -s skills/board-expert/tests`.
