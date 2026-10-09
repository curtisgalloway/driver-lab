<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Vendor guide: overlay roots, internal tools, and what may leave

For an engineer inside an organization that holds material the public specs cannot: NDA databooks,
internal BSP trees, lab rigs, errata trackers. Nothing here assumes you have read the rest of this
repository; [spec-format](../spec-format/SKILL.md) is the format 2 contract, and the
[glossary](../../GLOSSARY.md) defines shared terms.

## Terms

- **Public spec** — a board, SoC, chip, or IP spec under a root whose layer is `public`. Everything
  in it is citable from the public internet.
- **Overlay** — a `kind: overlay` YAML file adding to a public spec (`overlays: <id>`) without copying it. Your
  internal facts, documents, and tools live in overlays.
- **Root** — a directory with a `board-specs.yaml` marker declaring its `layer`. Overlays live under
  your roots; the reader finds roots only through pointers, never by searching.
- **Layer** — the merge position of a root: `public` < `ip-vendor` < `soc-vendor` < `product` <
  `local`. Later layers win on conflicting scalars; resource lists concatenate; added fact records keep their full references
  and appear under headings naming the layer and root.
- **Vendor skill** — `<vendor>-board-tools`: the one skill that knows how to reach your internal
  resources and declares your roots. The expert loads it beside `board-expert`.
- **`via:`** — the key on a `resources.tools` entry naming its driving skill. Documents and
  repos have no invocation `via`; retrieval `via` is only a fetch-method description.

## 1. Pick your layers

| You are | Layer | Typical overlay targets |
| --- | --- | --- |
| The maker of an IP block (a USB controller, a UART core) | `ip-vendor` | `ip` specs: `dwc3`, `dw-apb-uart` |
| The maker of an SoC | `soc-vendor` | `soc` specs, and `ip` specs for blocks you configured |
| The maker of a product built on someone's SoC, or on your own | `product` | `board` specs, plus `soc` specs if the SoC is yours |
| One engineer's bench | `local` | `board` specs: rig target names, serial adapter, power switch |

One organization can be more than one of these. A phone maker with its own SoC has a `soc-vendor`
root for the SoC and a `product` root for the phones, two markers, two directories, and one vendor
skill that declares both. Do not put everything in one root at the highest layer: the layer is what
lets an IP-vendor overlay and yours compose without either editing the other.

## 2. Lay out a root

```
vendor/<vendor>/board-specs/            any directory you control
  board-specs.yaml                      format: 2, layer: product, name: <vendor>-product
                                        license and accepts required
  pixel-10.spec.yaml                    kind: overlay, overlays: pixel-10
  tensor-g5.spec.yaml                   kind: overlay, overlays: tensor-g5 (use soc-vendor root)
```

- Prefer one overlay file per target per root. It declares `format: 2`, `kind: overlay`,
  `overlays: <id>`, and added fact records/resources. Never copy the public spec. Use the
  scaffold's YAML overlay templates and match the root's license header.
- In a source tree, the root can be the vendor directory itself so the overlay sits next to the
  vendor's board code and lands in the same review.
- Overlay facts have distinct ids within the target spec id and root. Across roots, cite the
  full `spec@root#fact` reference. Consolidate competing overlays within one root rather than
  relying on an undefined replacement order. Check the root with `spec.py check`.

## 3. Write the vendor skill

Copy `board-spec-scaffold/templates/vendor-board-tools-SKILL.md` to `<vendor>-board-tools/SKILL.md`
in your internal skills repository, and fill in:

- **Overlay roots.** One `board-spec root: <path>` line per root. Paths are relative to the checkout
  root of the tree that holds them, or absolute for a separate internal spec repository.
- **Document portal.** How to authenticate, how to search by part number, what a citation looks
  like (title, revision, section). The expert cites internal documents by title and section exactly
  as it cites public ones.
- **Code search and repositories.** How to check out the internal BSP or kernel, which branch is
  the product branch and full commit pins, and the user's cache convention. Internal trees
  use separate subdirectories in that cache; local paths never go into public artifacts.
- **Lab rig.** How to find the target for a board id and how to drive it. If the rig has its own
  skill, name it and say nothing else; the overlay's `tools:` entry points at it with `via:`.
- **Errata and bug tracker.** How to query errata for a part; how to cite an erratum.
- **Classification.** See section 5.

The skill's description must say it is internal and must name the vendor, so the harness's skill
matching offers it for your boards and never installs it elsewhere.

## 4. Wrap a tool

A tool is declared in the overlay and driven by a skill. The overlay says the tool exists:

```yaml
resources:
  tools:
    - kind: bench
      name: <bench-role>
      via: skill:<vendor>-board-tools
      note: serial, power, fastboot; no display capture
```

The skill named by `via:` owns invocation, authentication, and safety rules. `board-expert` never
invents a command line for a tool; it loads the skill and follows it. If that skill is not loaded in
the session, the reader reports the tool as unavailable and continues.

Kinds are free-form. The public conventions are `bench` (a target on a rig: serial console, power,
netboot, screen), `mcp` (an MCP server or tool), and `script` (a path in the tree). Add your own
kinds freely; the reader only cares about `via:`.

## 5. Classify what may leave

The expert runs in a subagent and returns a report. Decide, in the vendor skill, what may appear in
that report:

- **May leave:** hardware facts, addresses, sequences, and mechanism prose, each cited to the
  internal document by title and section. These are what the report is for.
- **May not leave:** document text beyond a phrase, internal hostnames and URLs in any artifact
  that could become public, tool credentials, and anything the document's own classification
  forbids.
- **Tagging:** every fact from your roots reaches the report tagged with its layer, so a downstream
  verifier can see that a citation is not publicly checkable. Facts from an NDA databook
  keep `class: databook` support; the full fact reference and layer say where they originate.
- **The one-way rule:** nothing from a vendor or local root is ever copied into a public-layer spec.
  If a fact turns out to be publicly documented, cite the public document and add it to the public
  spec on its own merits.

"May leave" means transfer into a report within the authorized private workflow, subject to the
source's restrictions. It does not authorize public disclosure. Reports, tests, logs, and other
derived artifacts retain those restrictions.

## 6. Install and test

1. Link or install `<vendor>-board-tools` wherever the expert subagent's skills come from.
2. Optionally add your roots to `~/.config/board-specs/board-specs.yaml` under `roots:` so they are
   found even in a session where the vendor skill is not loaded.
3. Ask a question that only an overlay can answer, through the orchestrator, and read the report's
   **Spec provenance** block: it must list your overlay file, its layer, and the internal documents
   it cited. If the overlay is missing from that block, the root pointer is wrong; if the facts are
   there but untagged by layer, the merge went wrong. File either as a bug against `board-expert`.

## 7. Coexisting with other vendors

An IP vendor's overlay on `dwc3` and your product overlay on `pixel-10` compose without contact: the
reader resolves the board, its SoC, its instances, and the IP each instance names, then applies every
overlay for every id in that composition in layer order. You never edit their files and they never
edit yours. When both overlay the same id, the higher layer wins on scalars, and both sets of facts
appear in the generated view under their own layer headings. An overlay never edits a base
fact; it adds a relationship or conflict. Each file has its own YAML verification record.

Existing format 1 vendor roots remain readable by board-expert until SF2-12; do not mix them
with a format 2 composition or use their Markdown rules for new authoring.
