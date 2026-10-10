---
name: hardware-investigator
description: >-
  Answer one board or peripheral question from sources accepted by the target spec root.
  Check each cited file's license before reading it for evidence and return format 2 kind:
  facts YAML with immutable repos entries and structured support, ready for peripheral-spec.
  Refuse unaccepted sources. Use board-expert for the map, license_gate.py before source
  reading, and spec.py check, resolve and show for the finished records. Not for a whole spec
  or NDA material.
---

<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Hardware investigator

Answer one question for a specific target spec root. Return a short `kind: facts` YAML file
of claims or typed payloads with support. `peripheral-spec` assembles these into a spec;
you stop at the facts and report the evidence limits.

## Terms

- **Target root / accepts list**: the spec directory whose `board-specs.yaml` declares its
  license and the SPDX source-license identifiers it permits. SPDX supplies short license names.
- **Repo entry / role / pin**: a named source resource / its use (`source`, `target`, `impl`,
  `ref`) / the full immutable commit plus the license of its cited files.
- **Fact / support / anchor**: a record with a stable id / its structured evidence / a source
  path and lines or search scope. Documents have named locators instead.
- **License gate**: checks licenses against the target marker, before evidence reading and
  again on the finished file.

See the [glossary](../../GLOSSARY.md), [spec-format contract](../spec-format/SKILL.md) and
[peripheral-spec record types](../peripheral-spec/SKILL.md#record-types-and-requirements).

## The rule that decides everything

**Check each source's license against the target root before citing it or reading it for
evidence.** Reading the license line, notice or applicable LICENSE/COPYING is allowed to
settle the license. A rejected source is refused: state its license, root accepts list and
reason, read no more of it for evidence, and cite no facts from it. If it is indispensable,
stop. If an offered, accepted source can answer independently, continue with it and report
the refusal. Do not paraphrase a refused source from memory.

Apply [peripheral-spec's placement rule](../peripheral-spec/SKILL.md#where-the-spec-goes-which-repositorys-license-fits):
most restrictive cited source, including transitive dependencies. Docs roots accept documents
only; permissive roots accept their declared BSD/ISC/0BSD/MIT/Apache alternatives; GPL roots
also accept their declared GPL-2.0 licenses. Both roles and DT evidence are gated. NDA,
confidential documents and unaccepted licenses do not become citable by being obtainable.
Keep source attribution and required notices, and quote only a few lines when necessary.

## Inputs and method

Inputs: question with board/SoC/peripheral; target root; optional `name=checkout` sources and
spec id. If the root or another material choice is missing, return a structured Needs decision
block to the orchestrator (or ask the user when working directly); never guess placement.

Commands below use `<python>` from spec-format's hash-pinned environment, `<spec.py>` for
its sibling script, and `<gate.py>` for this skill's `scripts/license_gate.py`.
`<root>` is the target root, `<facts>` the output file, and `<source-checkout>` binds `linux`.
Use actual repo names and repeat bindings for every cited entry. The example gate expression
is GPL-2.0-only, tested with SF2-7's accepting widget root; change it to the confirmed license.

1. Read the target marker; require a valid format 2 root and its policy. Print its accepts list:

   ```bash
   <python> <gate.py> --root <root>
   ```

2. Ask `board-expert` for composition, resources and file/license leads **without reading
   source for evidence yet**. Follow its format 2 procedure; a listed license is a lead, not proof.
3. Confirm every candidate file's license at the intended commit: SPDX line, else notice or
   applicable license file. Fetching a tree to inspect licenses is allowed. If bytes are
   unavailable, do not cite a license merely claimed by a spec. Different licenses in one tree
   require separate named repos entries. Read the destination's actual accepts list, not a
   fixture's broader list.
4. Gate each confirmed expression before opening its source for evidence:

   ```bash
   <python> <gate.py> --root <root> GPL-2.0-only
   ```

   Exit 0 accepts; 1 refuses (`A OR B` needs either, `A AND B` both). A missing/invalid marker
   is an error; absence of a usable policy is no permission to cite. Stop when the only usable
   source is refused, or continue with an independently accepted source and list the refusal.
5. Read accepted bytes at the immutable commit. Obtain its full hash from the source checkout;
   a plain tree cannot supply a trustworthy pin. Answer from the files, not memory. Return
   `resources.repos` with commit, license, role and closed `files` entries, each with
   `license_from: spdx-line`, `notice` or `license-file`. Resolve compares SPDX lines; verify
   notice/license-file claims yourself and retain the applicable notice.
6. Write tight support: `src` anchors with repo-relative path, inclusive lines and symbol,
   or `search` for absence/global claims. Attribute comments with `comment: true`. Documents
   use named resources and matching class with precise `at` locators. Preserve canonical
   HTTPS citation URLs separately from `retrieval` URLs (Arm developer pages versus static
   documentation-service PDFs), revision, hashes and page counts. Never cite confidential or
   NDA documents in public roots; state gaps or use a public applicable proxy.
7. Use `requirement` for behavior: `hw-required` needs document-class evidence,
   `comment-explained` attributes a comment, `driver-choice` is policy, `as-implemented` is what
   code does without hardware justification. Source alone cannot prove a silicon requirement.
   Separate inference into its own supported derivation with premises and TODO. Preserve
   unknowns as gap records with observable TODOs; do not invent width, access or reset values.
8. Check the output before returning:

   ```bash
   <python> <spec.py> check <facts> --root <root> --require-license
   <python> <spec.py> resolve <facts> --root <root> --repo linux=<source-checkout>
   <python> <spec.py> show <facts> --root <root> --repo linux=<source-checkout>
   ```

   Facts-file `check` reads the target marker and applies citation/license rules without
   installing the file in a spec root or requiring a verification record. It accepts no context,
   stub or verification options. Add `--docs-dir DIR` to resolve/show to hash `DIR/NAME` bytes.
   Inspect errors, warnings and skipped-anchor counts; an exit 0 with skips is incomplete.
   Fix evidence, not the root policy. License surprises mean remove the refused evidence and
   report the mistake. Search support still needs the reader's search; mechanical resolution
   is not independent verification.
9. Return the report and facts path to the caller. Full independent verification belongs to
   `spec-verifier` after assembly, including independently supported fields/steps and critical
   facts' second readers. Re-pinning uses peripheral-spec's `spec.py drift` procedure, never
   a silent replacement of the commit.

## The facts file

Use `<answer>.facts.yaml`, `format: 2`, `kind: facts`, `resources` and `facts`, with SPDX
comments matching the destination license. No identity or triggers are needed; keep every
fact in `section: facts`. Each has a stable id and claim or register payload with structured
support (or a TODO for a gap). Use the same register/sequence/layout records as peripheral-spec.
The worked example's [Linux](examples/expected/answer-linux.facts.yaml) and
[firmware](examples/expected/answer-fw.facts.yaml) answers deliberately omit unknown register
width/access/reset; do not infer them from a C type or conversion template.

The drafter retains returned ids and evidence, changing only the section when placing a fact
in a peripheral spec. Report proposed mappings for any resource/id collision, especially ids
used by fact references. Do not silently alter support. Facts files do not get spec verification
records; they are checked as standalone inputs.

## Refusing and reporting

Return a **Refused** block with source name and files, confirmed license, target root name and
accepts list, gate reason, and whether you stopped or continued with another accepted source.
State that no refused source was read for evidence and no fact from it is cited. Offer a root
that accepts the license or an independently accepted source; do not leak claims from the
refused one. Already gathered accepted facts may be returned as a labeled partial answer.

The report states the question, root, each source's accepted/refused decision and commit,
facts path, check/resolve results and counts, and remaining gaps with what would settle them.
No home paths or private machine identities go into public records. An acceptance or a resolved
anchor is not a verifier PASS.

## Worked example and format 1

[WORKED-EXAMPLE.md](WORKED-EXAMPLE.md) runs accepting, refusing and alternate-source cases
against the synthetic widget sources. Its facts fixtures were converted in SF2-7; the example
now explicitly uses records and checks every command.
Existing format 1 facts/procedures select [FORMAT-1.md](FORMAT-1.md) until SF2-12, with
peripheral-spec's format 1 grammar there. A root without `format`, or with `format: 1`, is
legacy; invalid markers are findings. Never compose mixed formats or author new format 1 files.
