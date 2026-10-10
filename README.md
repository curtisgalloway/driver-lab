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

- **`peripheral-spec`** writes a format 2 YAML spec for one peripheral from sources the
  target may cite. Facts have stable ids, structured support and requirements; register,
  sequence and layout payloads hold the programming data. Repository resources declare each
  pin's full commit, license and per-file license evidence. The placement rule chooses a
  spec repository that accepts every cited source's license.
  `spec.py check/resolve/show/drift/inventory` check structure and licenses, resolve citations,
  show claims beside evidence, compare pins and compare register payloads with headers.
- **`reference-driver-review`** compares an implementation with a pinned reference for the
  same hardware. It produces a `kind: review` YAML spec: repositories have `role: impl` or
  `ref`, findings carry both sides' structured anchors and an `assessment` (bug, suspect,
  benign or reference issue). The databook can settle disagreements. A verifier checks the
  findings; a finding's assessment is separate from its verification verdict. Output is a
  review, never driver code.
- **`hardware-investigator`** answers one board or peripheral question as `kind: facts` YAML
  ready for peripheral authoring. It gets the map from `board-expert` and checks source
  licenses against the target root before reading source evidence. Its `license_gate.py`
  uses format 2's strict marker validation and shared SPDX acceptance rules; `--facts` runs
  the complete citation gate. It needs spec-format's hash-pinned dependencies. The
  [worked example](skills/hardware-investigator/WORKED-EXAMPLE.md) exercises accepting,
  refusing and alternate-source cases with synthetic sources.

Peripheral specs are derivatives of the sources they cite. These skills do not permit a
license the source's terms refuse and are not for NDA source.

## Board experts

Board experts supply the per-board map and sources to cite. The map lives in format 2 YAML:
board, SoC, chip and IP specs compose through `parts` and `instances`; overlays add material
from other roots in a fixed layer order. Reference source stays in an out-of-tree cache.

The shared contract is [spec-format](skills/spec-format/SKILL.md), with a pointer at
[board-expert/SPEC-FORMAT.md](skills/board-expert/SPEC-FORMAT.md). `spec.py check` enforces
schemas, references, composition, license policy, public-root restrictions, stub resolution
and verification records. Generated Markdown and HTML views present the YAML with provenance
and per-fact status; edit the YAML, then regenerate the views.

- **`board-expert`** reads format 2 only. It resolves ids or board/SoC names across declared
  roots, composes and overlays the specs, consults pinned sources and reports full fact
  references with freshness and limitations. An IP question can be tied to a board instance
  or answered generically. Without a spec it investigates and suggests scaffolding.
  Its shipped `specs/` root is empty, marked format 2; published specs live in the separate
  spec repositories. It also ships the structured question catalog and vendor guide.
- **`board-spec-scaffold`** creates board, SoC, chip or IP YAML from templates, with optional
  expert stubs, overlays, vendor tool skills and root markers. Its interview settles identity,
  placement and sources; optional research-fill returns fact records. Its verification phase
  hands the files to `spec-verifier`.
- **`spec-verifier`** re-derives each fact from its evidence in fresh reader contexts and writes
  `<root>/resources/<name>.verify.yaml`, one record per spec file, including overlays.
  Verdicts use fact ids, or sub-keys for independently supported register fields and sequence
  steps. Critical facts need a second independent reader. `spec.py status` computes per-fact
  freshness from basis and dependency hashes; whole-file `spec_sha256` is informational.
  `--require-verified pr|main` selects the checking policy. The verifier proposes corrections
  and never edits the spec.
- **`spec-format`** supplies the contract, strict YAML loader, JSON Schemas and CLI:
  `validate`, `check`, `status`, `render`, `resolve`, `show`, `drift` and `inventory`.
  Format 1 authoring, reading and migration tools are retired. Frozen campaigns and historical
  records keep their original formats; carried verdict provenance remains readable in format 2.

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

Install the hash-pinned dependencies and run the format 2 suites and shipped-root check:

```bash
uv venv /tmp/driver-lab-sf2
uv pip install --python /tmp/driver-lab-sf2/bin/python --require-hashes -r skills/spec-format/requirements.txt
python3 -m unittest discover -s skills/board-expert/tests -v
/tmp/driver-lab-sf2/bin/python -m unittest discover -s skills/spec-format/tests -v
/tmp/driver-lab-sf2/bin/python -m unittest discover -s skills/hardware-investigator/tests -v
/tmp/driver-lab-sf2/bin/python skills/spec-format/scripts/spec.py check skills/board-expert/specs --stubs-from skills --require-license
```

Add `--require-verified pr` to reject missing or stale verdicts; `main` allows upstream-stale
warnings while enforcing the other verdict requirements. These checks do not re-read evidence.
The full checks list, including the frozen archive, is in `AGENTS.md`.
