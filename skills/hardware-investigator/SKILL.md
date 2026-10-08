---
name: hardware-investigator
description: >-
  Answer a board or peripheral question from source trees the target spec repository's license
  accepts, and return anchored facts (each citing file and line at a pinned, licensed commit)
  ready for peripheral-spec. Use when asked what a register, bit, init order, interrupt or
  address is for a named board, SoC or peripheral and the answer will be published in a spec
  repository (hardware-specs-gpl, -docs or -permissive) or any root with an accepts list. It
  reads through board-expert for the map, checks each source's license against the target root's
  accepts list before reading it for evidence or citing it, and refuses a source the root does not accept, saying why and
  stopping. Not for generating a whole spec (use peripheral-spec) and not for NDA material.
---

<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Hardware investigator (a question in, anchored facts out)

You answer one question about hardware, for a spec that will live in a specific **target root**,
and you cite only sources that root accepts. What you return is a short file of **anchored
facts**: statements about the hardware, each pointing at the file and lines it came from, at a
pinned commit whose license is stated. `peripheral-spec` turns facts like these into a whole
spec; you stop at the facts.

## Terms

- **Target root**: the directory whose `board-specs.yaml` marker says where the answer will be
  published. Its `accepts:` list names the SPDX license identifiers a cited source may carry.
  (SPDX is the standard short names for licenses, such as `GPL-2.0-only` or `MIT`.)
- **Accepts list**: that `accepts:` list. A source whose license is not on it may not be cited.
- **Pin**: a line `Source pin: <name>@<full commit> <SPDX license>` naming a source tree, the
  exact commit read, and the license of the files cited through it. An **anchor** is a citation
  `[src:<name>: path:L1-L2 (symbol)]` that resolves against the pin of that name.
- **License gate**: the rule that every cited pin's license is on the target root's accepts list;
  `anchor_check.py --root` enforces it on the finished facts.
- Longer definitions: `GLOSSARY.md` in driver-lab; the anchor grammar: `peripheral-spec`.

## The rule that decides everything

**Check a source's license against the target root's accepts list before you cite it; and before
you read it for evidence.** Not after, and not by the final checker alone. A source the root does
not accept is **refused**: you say which source, its license, the root's accepts list and the
reason, you read no more of it, you cite nothing from it, and you stop (see *Refusing*). Reading
the source's license line and its `LICENSE` or `COPYING` file is not reading it for evidence.

## Inputs

- **question**: what the caller wants to know, with the board, SoC or peripheral named.
- **target root**: a directory with a `board-specs.yaml`. If the caller names none, ask; do not
  guess a root, because the answer is only as citable as the root says.
- **sources** (optional): `name=path` local checkouts the caller offers. A caller's source may be
  one no board spec names.
- **spec id** (optional): a `board-expert` spec id (`spec: widgetuart`) when the caller has one.

## Method

1. **Read the target root's accepts list.** Run
   `python3 <skill>/scripts/license_gate.py --root <target root>` (`<skill>` is this skill's
   directory). It prints the root's name, license and accepts list, and exits 2 if the directory
   is not a spec root and 1 if the root has no `accepts:` at all (then nothing can be cited;
   stop and say so).
2. **Get the map from `board-expert`.** Load `board-expert` and run it as a subagent when you
   can spawn one (otherwise follow its *Resolve the spec* section yourself). Ask for the spec
   composition, the repositories and documents the specs name with the licenses they state, and
   the files each lists; ask it **not** to read source trees yet. Its answer tells you where to
   look and what each source claims to be licensed under. A claim in a spec is a lead, not
   proof.
3. **List candidate sources and settle each license, one at a time.** For every tree you may
   cite, caller-supplied or named by the map: read the `SPDX-License-Identifier:` line of each
   file you expect to cite (else the tree's `LICENSE` or `COPYING`). The file's own license wins
   over what a spec says. For a tree you have no copy of, fetching it (a shallow clone is fine)
   in order to read those license lines is allowed; reading it for evidence is not, until step 4
   passes. If you cannot fetch it, its license is only the spec's claim: say so and do not cite
   it. If one tree carries files under two licenses, treat it as two pins
   with distinct names.
4. **Gate each license now.** Run
   `python3 <skill>/scripts/license_gate.py --root <target root> '<SPDX expression>'` (quote the
   expression; several may be given). Exit 0 means the expression is on the accepts list
   (`A OR B` passes when either side is, `A AND B` only when both are). Exit 1 means refused.
   Do this for every candidate before you open any of them for evidence.
5. **Read only accepted sources.** If a refused source is one the question cannot be answered
   without, stop (*Refusing*). If other accepted sources can answer it, go on with those and
   list the refusal in your report. A tree you fetched is read at the ref the spec records.
6. **Pin each accepted tree.** `git -C <tree> rev-parse HEAD` gives the full commit. A tree that
   is not a git checkout cannot be pinned: say so and use another source.
7. **Investigate.** Read the files; do not answer from memory. Anchor as tightly as the claim
   (one `#define`, one statement), always with the symbol, following the anchor grammar in
   `peripheral-spec`. Label each behavior claim `[hw-required]` (needs a `[doc:]` too),
   `[comment-explained]`, `[driver-choice]` or `[as-implemented]`; a source that only shows
   what code does never earns `[hw-required]`. Facts that rest on a document use `[doc: …]`,
   which the gate does not check. Never write an anchor for a line you did not read.
8. **Write the facts file** (format below), then run the gate on it:
   ```
   uv run --with markdown-it-py==4.2.0 python3 <skill>/../peripheral-spec/scripts/anchor_check.py <facts file> \
       --repo <name>=<tree> [--repo <name>=<tree> …] --root <target root> --require-license
   ```
   It must end `result: PASS`. Fix errors by finding the right lines or the right pin, not by
   loosening the root or widening a range. If it reports a license-gate error you did not
   expect, you cited a source you should have refused at step 4: remove the facts from it and
   say so.
9. **Report** (format below).

## The facts file

```
---
# SPDX-FileCopyrightText: <year> <holder>
# SPDX-License-Identifier: <the target root's license>
---

# <short title> (facts for peripheral-spec)

Source pin: <name>@<full commit> <SPDX>

## Facts

- <statement, one fact per bullet; label optional for a bare register offset> [src:<name>: <path>:<L1>-<L2> (<symbol>)]
- <statement> [as-implemented] [src:<name>: <path>:<L>-<L> (<symbol>)]
```

One `Source pin:` line per tree, each name distinct; the license on the pin is the one you
settled at step 3. Facts only: no register-map tables copied from the source, no sections of a
spec, no claims without an anchor or a document citation. The SPDX header goes in the front
matter as YAML comments: `anchor_check.py` holds the file to board-expert's spec Markdown
profile, which allows no HTML.

## Refusing

When a source the answer needs is not accepted, return this and nothing else about that source:

```
## Refused
Source: <name> (<files>), license <SPDX>
Target root: <root name> (<path>), accepts: <the list>
Reason: <what license_gate.py said>
Stopped: no line of this source was read for evidence and no fact from it is cited.
Options: place the answer in a root whose accepts list includes <SPDX>, or supply a source
under an accepted license.
```

Do not paraphrase the refused source from memory, hint at what it contains, or substitute a
source you picked yourself and did not gate. Facts you already gathered from accepted sources may
be returned as a partial answer, marked as such.

## Report

```
## Question
<restated, with the target root>

## Sources
<each source: license, gate verdict (accepted or refused), commit pinned>

## Facts
<path to the facts file, and the anchor_check.py result line>

## Gaps
<what the accepted sources do not settle; what would settle it>
```

## Worked example

`WORKED-EXAMPLE.md` (beside this file) runs the method on `board-expert`'s `widgetuart` fixture
against three target roots, one accepting, one refusing and stopping, one refusing a source and
carrying on with another. Its source trees, roots and expected facts are under `examples/`.
