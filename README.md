# hardware-specs

A kind of knowledge graph for hardware. Facts about devices and boards ("this register resets to
zero", "this block sits at this address") are small cited records. Each one points to the
exact source lines or document page it came from, and to the other facts it rests on. Agent
skills write the facts and check them. A command-line tool, `hwspecs`, validates the links,
reports which facts have gone stale, and renders the result as readable views.

The aim is something better to write drivers from than a pile of datasheets and source trees.
Writing a driver for a particular OS, or bringing up a particular board, happens in projects
that install these skills (see [DESIGN.md's scope section](DESIGN.md#scope-specs-and-their-quality)).

New here? Start with the one-page [How it works](docs/HOW-IT-WORKS.md). Every borrowed or coined
term is defined in the [glossary](GLOSSARY.md).

## How the graph fits together

A **spec** is a YAML file of **facts** about one board, SoC, chip, IP block, protocol or
peripheral. Each fact has a stable id, a claim, and the sources that support it.

```
 specs     board ──parts──> SoC ──instances──> IP / peripheral spec
             ▲               ▲                      │
             │               └──────describes───────┘
          overlay (adds facts from another repository; never edits)

 facts     each spec holds facts; facts link to other facts:
             relates   qualifies / refines / contradicts / same-as
             premises  an inference rests on other facts
             topology  clock, interrupt, power, reset connections

 sources   a fact's support ──> source lines at a pinned commit,
                               or a document section and page
```

**Nodes**

- **Specs** of these kinds: `board`, `soc`, `chip`, `ip` (a reusable block such as a UART
  design), `protocol`, `peripheral` (one block's programming model: registers, sequences, data
  formats) and `review` (a driver compared with a reference).
- **Facts** inside them. A fact's full name, `<spec>@<repository>#<fact>`, is unique across the
  repositories read together, so adding a fact in one repository never changes what a reference
  in another resolves to.
- **Sources**: a source file at a pinned commit, a datasheet section, a device tree. A fact with
  no source is a gap and must say what would settle it.

**Edges**

- **Composition** links specs: a board lists its `parts`; an SoC's `instances` place IP and
  peripheral specs at base addresses; a peripheral spec `describes` the SoCs it appears in; an
  `overlay` adds facts to a spec from another repository.
- **Fact links** connect facts: `relates` (`qualifies`, `refines`, `contradicts`, `same-as`) and
  the premises of an inference. Premises may not form a cycle.
- **Topology** facts (the newest part) describe clock sources, muxes, PLLs, power domains,
  reset and interrupt controllers and the connections between them, plus named board
  configurations that choose among alternative routes
  ([design](docs/ATLAS-CONNECTIONS-DESIGN.md)).

**What the links are used for**

- **Freshness.** Each verification verdict records a hash of the fact, its sources and the facts
  it rests on. When one of those changes, the verdicts that depend on it become stale and the
  rest stay current. Composition links are not part of this hash.
- **Licenses.** A fact that rests on GPL code, directly or through other facts, can only live in
  a repository that accepts GPL. The checker follows those chains.
- **Reading a board.** `board-expert` follows composition and overlays to answer questions like
  "what is at this address on this board, and how well checked is it?"
- **Views.** `hwspecs render` produces Markdown and HTML views of a spec, and an offline HTML
  atlas that shows a spec with the specs around it.

**Why only "a kind of" knowledge graph**

- Every link is written by an author; fact links and topology facts are cited like any other
  fact. Nothing is inferred by a reasoner, and there is no query language: the CLI and the
  rendered views are how it is read.
- It is incomplete by design. A missing link is a gap, not a statement that the hardware is
  unconnected, and where a complete upstream description exists (a full device tree) a spec
  points to it rather than copying it.
- It is split across repositories by license, so seeing all of it means reading those
  repositories together.
- Topology is new. The format and its checks are in place; the atlas does not yet draw
  connections, and no real board's topology has been written up
  ([plan](docs/ATLAS-CONNECTIONS-PLAN.md)).

The full contract is [docs/SPEC-FORMAT.md](docs/SPEC-FORMAT.md), with the agent-facing summary in
[skills/spec-format/SKILL.md](skills/spec-format/SKILL.md).

## Does it work?

The main test is to write a driver from the spec alone and run it beside the existing one.

- **e1000 (L02).** A Linux driver for Intel's e1000 network card was written from the spec,
  without the writer reading the Linux source, and run beside Linux v6.12's `e1000` on QEMU's
  emulation of the card. On the final harness both drivers passed all ten scenarios in isolated
  runs (40 runs, 928 checks, 0 failed). The candidate is qualified for the 22 claims in scope;
  four were left outside it as recorded shortfalls. This was an emulator, not real hardware.
  See [evidence/L02f3.md](evidence/L02f3.md).
- **ENC28J60 (L01).** A driver for this SPI Ethernet chip was written from its spec and tested
  on a Raspberry Pi 4 fixture against the Linux driver. It passed all ten checks of its scoped
  acceptance, and all five deliberately broken controls were caught; an independent review of
  that result is pending. See [evidence/L01.md](evidence/L01.md) and
  [evidence/L01-hw.md](evidence/L01-hw.md).

Both devices already had a working driver to compare against, which is the easy case. Hardware
with no existing driver has not been tried
([DESIGN.md](DESIGN.md#when-there-is-no-existing-driver)). Why the design leans on automated
checks rather than human review of every spec: [DRIVER-QUALITY.md](DRIVER-QUALITY.md).

## How quality is checked

- **Each fact cites its source** at a pinned commit or document page, and says what kind of
  evidence it is, so "a driver does this" stays distinct from "the hardware requires this". A
  fact with no source is a recorded gap, not a guess.
- **Independent verification.** `spec-verifier` has fresh agents, who never saw the author's
  reasoning, re-derive each fact from the cited source and write a separate verification record.
  Bring-up-critical facts need two independent readers.
- **Conflicts are recorded, not overwritten.** When two sources disagree, the format keeps both
  readings, with the resolution and who decided it.
- **Automation first, people for exceptions.** CI checks structure, citations, licenses and
  verdict freshness on each pull request; people handle disagreements.

What this does not show: that the cited source is right. A verifier checks that a fact matches
its source; two readers can share a mistake, and only running on hardware settles behavior.

## Where the specs live

This repository holds the tools and the method. Published specs live in repositories split by
the licenses of what they cite. A spec goes in the most restrictive repository among its
sources, and each repository's CI runs a license check that fails a spec citing a source it
does not accept
([license-split design](docs/LICENSE-SPLIT.md)):

| Repository | Accepts |
| --- | --- |
| `hardware-specs-docs` | datasheets and documents only |
| `hardware-specs-permissive` | plus BSD, MIT and Apache source |
| `hardware-specs-gpl` | plus GPL source |
| [`hardware-specs-usb`](https://github.com/curtisgalloway/hardware-specs-usb) | generic facts of public standards (USB, xHCI, Type-C, PD, TCPCI) that board and SoC specs compose |

Not for: specs derived from NDA or vendor-licensed material, or legal advice (none of this has
had legal review). The method for writing a spec and driver without the writers reading the
original source is published separately in
[cleanroom-skills](https://github.com/curtisgalloway/cleanroom-skills).

## Which skill do I want?

| Situation | Skill |
| --- | --- |
| Write a spec for one peripheral, every fact pointing back at code or documents you may cite | `peripheral-spec` |
| Check an existing driver against an upstream, vendor or original implementation | `reference-driver-review` |
| Ask about a board: memory map, boot chain, clocks, interrupts | `board-expert` |
| Start a board, SoC, chip or IP spec that does not exist yet | `board-spec-scaffold` |
| Answer one hardware question as cited facts, from sources the target repository accepts | `hardware-investigator` |
| Check a spec against every source it cites, or re-check after sources moved | `spec-verifier` |
| Fetch, pin and cache web documentation, vendor wikis or PDFs for citing | `site-cache` |
| Measure whether readers of a spec can write correct code from it | `spec-eval` |
| Check a driver campaign's claims and status index against its evidence | `campaign-review` |
| Learn the format and the `hwspecs` CLI | `spec-format` |

In Claude Code the plugin also installs a `driver-porting:board-expert` agent that runs
`board-expert` in its own context with file-editing tools removed
([agents/board-expert.md](agents/board-expert.md)). The Fuchsia-specific skills that build on
these live in [fuchsia-skills](https://github.com/curtisgalloway/fuchsia-skills) and call them by
name.

## The `hwspecs` CLI

The skills run their mechanical steps through one Rust binary. `hwspecs --help` lists every
subcommand; grouped by job:

| Job | Subcommands |
| --- | --- |
| Check specs | `validate`, `check`, `license-gate`, `prose-facts` |
| Follow evidence | `resolve`, `show`, `drift`, `inventory`, `fetch`, `resource`, `index` |
| Track verification | `verify`, `status`, `todo`, `corpus` |
| Build and publish views | `render` (`md`, `html`, `atlas`), `publish`, `stubgen` |
| Author in parallel | `assemble` (merge `.facts.yaml` slices into a spec) |
| Evaluate | `eval`, `campaign` |

`--json` and `--offline` are global flags. Exit codes: 0 passed, 1 a check failed, 2 usage
error, 3 missing precondition.

## Installing

### The skills

Claude Code:

```
/plugin marketplace add curtisgalloway/hardware-specs
/plugin install driver-porting@hardware-specs
```

Update later with `/plugin marketplace update hardware-specs`. If you already use the
`curtisg-skills` marketplace from [public-skills](https://github.com/curtisgalloway/public-skills),
`/plugin install driver-porting@curtisg-skills` installs the same plugin.

Codex:

```
codex plugin marketplace add curtisgalloway/hardware-specs
codex plugin add driver-porting@hardware-specs
```

Other harnesses that read skill directories: clone the repository and link each
`skills/<name>` into your skills root. The
[public-skills README](https://github.com/curtisgalloway/public-skills#installing) has the paths.

The plugin keeps the name `driver-porting` because other skills hand off to these by name.

### The CLI

Build from a clone (the toolchain is pinned in `rust-toolchain.toml`):

```bash
cargo build --release --locked
target/release/hwspecs --version
```

[install.sh](install.sh) installs a pinned release binary, or builds a pinned revision with
`--from-source --rev <sha>`, and checks that the binary reports the commit you asked for.

## Tests

```bash
cargo test --locked --offline
cargo build --release --locked
target/release/hwspecs check skills/board-expert/specs --stubs-from skills --require-license
```

The full list CI runs is in [AGENTS.md](AGENTS.md#checks).

## Other documents

- [DESIGN.md](DESIGN.md): the overall design, evidence model and scope.
- [docs/SPEC-FORMAT.md](docs/SPEC-FORMAT.md): the spec format, references, roots and freshness.
- [docs/RUST-TOOLING-DESIGN.md](docs/RUST-TOOLING-DESIGN.md): the `hwspecs` tool.
- [docs/LICENSE-SPLIT.md](docs/LICENSE-SPLIT.md): why specs are split by license, and how.
- [docs/STANDARDS-SURVEY.md](docs/STANDARDS-SURVEY.md): existing hardware-description standards
  (IP-XACT, SystemRDL and others) and what the format borrows from them.
- `evidence/` and `notebook/`: a record of each milestone and experiment.

**Frozen archive.** The evaluation plans ([IMPLEMENTATION-PLAN.md](IMPLEMENTATION-PLAN.md),
[DEFERRED-PLAN.md](DEFERRED-PLAN.md), [EVAL-PLAN.md](EVAL-PLAN.md)), the
[reconstruction protocol](RECONSTRUCTION.md) and [`evals/`](evals/README.md) are kept as history
since the license split and are still checked by CI. New evaluation rounds happen elsewhere.

This repository was split out of
[public-skills](https://github.com/curtisgalloway/public-skills) on 2026-09-25 and renamed from
driver-lab on 2026-10-21; [TRANSITION.md](TRANSITION.md) records the move.

## License

Apache 2.0; see [LICENSE](LICENSE).
