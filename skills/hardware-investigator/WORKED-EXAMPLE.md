<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Worked example: format 2 Widget UART facts

**Terms:** facts files contain identified records and structured support, without a spec identity;
a pin identifies immutable source bytes; a root declares acceptable licenses. See the
[glossary](../../GLOSSARY.md).

Everything here is synthetic. This example uses the sources and facts converted in SF2-7,
and the same target roots. It tests license placement and evidence resolution, not hardware.
The source statements do not establish register width, access or reset; the records omit them.
Write your own records after reading the accepted source, then compare with the expected files.

**Question:** what is the Widget UART's control register, and in what order does software bring
it up? The Linux-like source has GPL-2.0-only SPDX lines; offered firmware has MIT SPDX lines.
The board map is a source lead, never confirmation of a file's license or hardware behavior.

## Setup and substitutions

Use a scratch directory under the system temporary directory. Copy each tree from
`examples/sources/widget-linux` and `examples/sources/widget-fw` into it, initialize each as a
git checkout and commit its files with a fictional fixture author. Read its full HEAD hash.
Copy `examples/expected/answer-linux.facts.yaml` and `answer-fw.facts.yaml` to scratch, replacing
only the all-ones resource commit in each with its corresponding checkout hash. Do not change
claims or support to make them pass. The example tests make these same temporary checkouts.

Use a virtual environment installed with spec-format's hash-pinned requirements.
`<python>` is its interpreter; `<spec.py>` is `spec-format/scripts/spec.py`; `<gate.py>` is
`hardware-investigator/scripts/license_gate.py`. `<root>` is `examples/roots/gpl`,
`<permissive-root>` is `examples/roots/permissive`; `<facts>` and `<facts-fw>` are the two copied
answers. `<source-checkout>` and `<fw-checkout>` are the temporary source trees. Their names
and bindings match `resources.repos`, which have `role: source`, full commits, file licenses
and `license_from: spdx-line` confirmations.

## A: accepted Linux source

Read the GPL target policy:

```bash
<python> <gate.py> --root <root>
```

Read only the intended file's license line first. It states GPL-2.0-only. Gate before opening
the file for evidence:

```bash
<python> <gate.py> --root <root> GPL-2.0-only
```

Expected: exit 0 and `accepted: GPL-2.0-only`. Now read the accepted source at its pin and
write facts. Every record uses `section: facts`; the control, BAUD and LCR records carry
`data.register` with canonical quoted offsets and source support. The init record states
what the driver does with `requirement: as-implemented`. It is not a claim that silicon
requires the driver's order. The LCR explanation is attributed to source, not measured hardware.

```bash
<python> <spec.py> check <facts> --root <root> --require-license
<python> <spec.py> resolve <facts> --root <root> --repo linux=<source-checkout>
<python> <spec.py> show <facts> --root <root> --repo linux=<source-checkout>
```

Expected: exit 0 for each, zero check errors/warnings, four resolved anchors and zero skips.
Show puts claims beside source bytes. That makes them reviewable; it is not independent
verification. Return facts and resources unchanged to the drafter, which retains ids and
support and assigns destination sections explicitly.

## B: only refused source available

Read the permissive policy:

```bash
<python> <gate.py> --root <permissive-root>
```

After the GPL license line, gate it. **Expected exit: 1.**

```bash
<python> <gate.py> --root <permissive-root> GPL-2.0-only
```

The gate reports refusal. Stop without reading that source for evidence, pinning it for an
answer or returning hardware facts from it. Return the skill's Refused block, with confirmed
license, accepts list, reason and options. This refusal is the expected successful method result.

The following is a deliberately invalid backstop test, not a step in the refusing workflow.
If GPL facts were supplied anyway, both paths reject them. **Expected exit: 1.**

```bash
<python> <spec.py> check <facts> --root <permissive-root> --require-license
<python> <gate.py> --facts <facts> --root <permissive-root>
```

## C: independently accepted firmware offered

Record the Linux refusal from B. Read the offered firmware file's license line: MIT. Gate it
before reading further:

```bash
<python> <gate.py> --root <permissive-root> MIT
```

Expected: exit 0 and `accepted: MIT`. Now read firmware at its pin and produce the second
answer; use `fw` support only. Its initialization claim is `comment-explained`, because the
firmware comment explains disabling before programming. This is still a code comment, not
an independently established hardware requirement.

```bash
<python> <spec.py> check <facts-fw> --root <permissive-root> --require-license
<python> <spec.py> resolve <facts-fw> --root <permissive-root> --repo fw=<fw-checkout>
<python> <spec.py> show <facts-fw> --root <permissive-root> --repo fw=<fw-checkout>
```

Expected: all exit 0, zero check errors/warnings, four resolved anchors and zero skips.
Report Linux refused and firmware accepted, facts path, counts and hardware unknowns.
Do not turn a mechanical success into a verification PASS. Later spec assembly and independent
verification use the same records and per-fact bases; unknown width/access/reset stays unknown.

## Repeatability

The existing investigator worked-example suite checks the three license outcomes and exact
preserved claims/support. `skills/spec-format/tests/test_sf2_9_docs.py` also extracts and
executes every shell block above after these substitutions, as it does for the skills and
prompts. Stand-in sources for the review fixture are explicitly synthetic; no command result
here claims a differential driver or physical hardware test.
