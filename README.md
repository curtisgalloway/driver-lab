# hardware-specs

Agent skills and a command-line tool, `hwspecs`, for building a checked, cited body of knowledge
about hardware: what each register does, how a board's devices are wired to clocks and
interrupts, which order to bring them up in, and where every one of those facts came from.

The goal is to give people and coding agents something better to write drivers from than a pile
of datasheets and source trees. Writing a driver for a particular OS, or bringing up a
particular board, happens in projects that install these skills (see
[DESIGN.md's scope section](DESIGN.md#scope-specs-and-their-quality)).

New here? Start with the one-page [How it works](docs/HOW-IT-WORKS.md). Every borrowed or coined
term is defined in the [glossary](GLOSSARY.md).

## Does it work?

The core test is to rebuild a driver from the spec alone and run it against the original.

- **e1000 (L02).** A Linux driver for Intel's e1000 network card was written from the spec,
  without the writer reading the Linux source, then run beside Linux v6.12's own `e1000` on QEMU's
  emulated card. On the final harness both drivers passed all ten scenarios, twice each, in
  isolated runs: 40 runs, 928 checks, 0 failed. Every difference found along the way went back
  into the spec as a fix or a recorded gap. See [evidence/L02f3.md](evidence/L02f3.md).
- **ENC28J60 (L01).** A driver for this SPI Ethernet chip was written from its spec and tested
  on real hardware (a Raspberry Pi 4 fixture) against the Linux driver. It passed all ten
  checks, and all five deliberately broken controls were caught; an independent review of that
  result is pending. See [evidence/L01.md](evidence/L01.md) and
  [evidence/L01-hw.md](evidence/L01-hw.md).

Both targets already had a working reference driver to compare against, which is the easy case.
Hardware with no existing driver is the open question
([DESIGN.md](DESIGN.md#when-there-is-no-existing-driver)). Why the design leans on automated
checks rather than human review of every spec: [DRIVER-QUALITY.md](DRIVER-QUALITY.md).

## A knowledge graph for hardware (sort of)

A spec is a YAML file of **facts**. Each fact is one statement about the hardware ("this
register resets to zero", "the UART's clock comes from this PLL") with a stable id and the exact
source it came from. The facts and the links between them form a graph:

```
 specs     board ──parts──> SoC ──instances──> IP / peripheral spec
             ▲               ▲                      │
             │               └──────describes───────┘
          overlay (adds facts from another repository; never edits)

 facts     each spec holds facts; facts link to other facts:
             relates   qualifies / refines / contradicts / same-as
             premises  an inference rests on other facts
             topology  clock, interrupt, power, reset connections

 sources   every fact's support ──> source lines at a pinned commit,
                                    or a document section and page
```

**Nodes**

- **Specs**, of a few kinds: `board`, `soc`, `chip`, `ip` (a reusable block such as a UART
  design), `protocol`, `peripheral` (one block's full programming model: registers, sequences,
  data formats) and `review` (a driver compared with a reference).
- **Facts** inside them. A fact's full name, `<spec>@<repository>#<fact>`, is unique across
  every repository read together, so an id never changes meaning when another repository adds a
  fact.
- **Sources**: a Linux source file at a pinned commit, a datasheet section, a device tree.
  These are the leaves; every non-gap fact ends at one or more of them.

**Edges**

- **Composition**: a board lists its `parts`; an SoC's `instances` place IP and peripheral
  specs at base addresses; a peripheral spec `describes` the SoCs it appears in; an `overlay`
  adds facts to a spec from another repository.
- **Fact links**: `relates` (`qualifies`, `refines`, `contradicts`, `same-as`) and inference
  premises. Premises must form a DAG, so a conclusion can never rest on itself.
- **Topology** (newest): typed nodes and ports for clock sources, muxes, PLLs, power domains,
  reset and interrupt controllers, and `connection` facts between them, plus named board
  `configuration`s that select among alternative routes. See the
  [atlas connections design](docs/ATLAS-CONNECTIONS-DESIGN.md).

**What the graph is used for**

- **Freshness travels along edges.** Each verdict records a hash of the fact, its sources and
  every fact it rests on. Change one source line and exactly the facts downstream of it go
  stale; nothing else needs re-checking.
- **Licenses travel along edges.** A fact that cites GPL code, directly or through any chain of
  references, can only live in a repository that accepts GPL. The checker follows the chain.
- **Composition gives the reader one view.** `board-expert` follows parts, instances and
  overlays to answer "what is at this address on this board, and how sure are we?"
- **The atlas** (`hwspecs render --format atlas`) is an offline HTML page per board: an outline,
  the spec graph, a memory map, a verification coverage grid and open items.

**Why "sort of"**

- **Every edge is authored and cited.** Nothing is inferred by a reasoner, and there is no
  query language. The CLI and the rendered views are how you read it.
- **It is partial on purpose.** A missing connection is a gap, not a claim that the hardware is
  unconnected. Where complete upstream data already exists (a full device tree), specs link to it
  rather than copy it, and the view shows where extraction stopped.
- **It is split across repositories by license**, and the identity scheme exists so the pieces
  still join.
- **Status of the topology layer.** The fact format and its checks are done (AT1). The
  Connections view in the atlas, and a sourced real-board example, are still to come (AT2 to AT4
  in the [plan](docs/ATLAS-CONNECTIONS-PLAN.md)).

The full contract is [docs/SPEC-FORMAT.md](docs/SPEC-FORMAT.md), with the agent-facing summary in
[skills/spec-format/SKILL.md](skills/spec-format/SKILL.md).

## How quality is checked

- **Every fact cites its source** at a pinned commit or document page, and says what kind of
  evidence it is, so "a driver does this" is never mistaken for "the hardware requires this". A
  fact with no source is a recorded gap, not a guess.
- **Independent verification.** `spec-verifier` has fresh agents, who never saw the author's
  reasoning, re-derive each fact from the cited source and write a separate verification record.
  Bring-up-critical facts need two independent readers.
- **Conflicts are recorded, never overwritten.** When two sources disagree, both readings stay,
  with the resolution and who decided it.
- **Automation first, people for exceptions.** CI checks structure, citations, licenses and
  verdict freshness on every change; people handle disagreements.

What this does not prove: that the cited source is right. Two readers can share a mistake, and
only running on hardware settles behavior.

## Where the specs live

This repository holds the tools and the method. Published specs live in repositories split by
the licenses of what they cite. A spec goes in the most restrictive repository among its
sources, and each repository's CI rejects a spec citing a source it does not accept
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

One Rust binary does every mechanical step. `hwspecs --help` lists them all; the main groups:

| Job | Subcommands |
| --- | --- |
| Check specs | `validate`, `check`, `license-gate`, `prose-facts` |
| Follow evidence | `resolve`, `show`, `drift`, `inventory`, `fetch`, `resource`, `index` |
| Track verification | `verify`, `status`, `todo`, `corpus` |
| Build and publish views | `render` (`md`, `html`, `atlas`), `publish`, `stubgen` |
| Author in parallel | `assemble` (merge `.facts.yaml` slices into a spec) |
| Evaluate | `eval`, `campaign` |

Every command takes `--json` and `--offline` and follows the exit-code contract: 0 passed, 1 a
check failed, 2 usage error, 3 missing precondition.

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
