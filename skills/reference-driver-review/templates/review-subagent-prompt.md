<!--
SPDX-FileCopyrightText: 2026 Curtis Galloway
SPDX-License-Identifier: Apache-2.0
Fill-in prompt: substitute every angle-bracket placeholder before delegation.
-->

# Format 2 review drafting prompt

**Terms:** roles identify the two trees; an assessment judges a difference; a verifier verdict
judges the finding's evidence. See [the glossary](../../../GLOSSARY.md).

Review <peripheral> (<IP block>, <board/revision>) at <impl-checkout>, <impl-commit>, against
<ref-checkout>, <ref-commit>. Reference choice and applicability: <reference choice>.
Destination root: <root>; output: <scratch-review>. Load `reference-driver-review`,
`peripheral-spec` and `spec-format`. Confirm cited file licenses and the destination's accepts
list first. Quote sparingly, preserve notices, never paste reference code into the implementation.

Build correspondence first, then fan out paired constants, sequences, interrupt/DMA and
error/quirk slices. Run constants twice independently, resolving differences against both
headers. Preserve investigators' ids and structured support; no invented line citations.

Start from this minimal complete finding template. The fixture pins/paths and suspect
example are synthetic; substitute read evidence and its actual applicability for real work.

```yaml
# SPDX-FileCopyrightText: <copyright-year> <copyright-holder>
# SPDX-License-Identifier: <file-license>
format: 2
kind: review
id: <review-id>
name: <review-name>
resources:
  repos:
    - name: impl
      role: impl
      url: https://example.invalid/impl
      commit: "<impl-commit>"
      license: MIT
      files: [{path: drivers/widget/widget_uart.c, license_from: spdx-line}]
    - name: ref
      role: ref
      url: https://example.invalid/reference
      commit: "<ref-commit>"
      license: GPL-2.0-only
      files: [{path: drivers/tty/serial/widget.c, license_from: spdx-line}]
facts:
  - id: f-baud-latch
    section: findings
    claim: The implementation writes LCR before BAUD while the reference writes BAUD first.
    data:
      finding:
        category: differs
        assessment: suspect
        consequence: The previous divisor may be latched on the first frame.
        resolution: {status: open}
    todo: {check: hardware, text: Observe the first frame rate after changing BAUD.}
    support:
      - class: src
        anchors:
          - {repo: impl, path: drivers/widget/widget_uart.c, lines: [30, 31], symbol: widget_init}
          - {repo: ref, path: drivers/tty/serial/widget.c, lines: [13, 14], symbol: widget_uart_init}
```

Add identity/applicability records and notes about reference choice and revision risks,
correspondence `data.pair: {impl: [anchors], ref: [anchors]}`, coverage
`data.coverage: {area, compared, read, reason}`, findings, agreements and open questions.
Pair-only evidence is support and needs no artificial TODO. All unmapped routines need a
finding or scope reason. A zero-finding area states what was read to earn it. `areas` carries
confidence. Do not create a placeholder verification record.

Every finding needs category (`differs`, `missing`, `extra`), assessment (`bug`, `suspect`,
`benign`, `ref-issue`), consequence, resolution and both-side evidence. Use implementation
search evidence for `missing`, reference search evidence for `extra`; the verifier repeats it.
A bug needs document-class `settled_by` or `self_evident: true` with `reason`, never the
reference's difference alone. Benign needs a justification; suspect needs a hardware probe.
Separate `requirement` (why behavior is needed) from assessment. Attribute comments and
separate source observation from hardware inference. Findings remain stable ids when fixed;
record full fixing commit, then inspect/rewrite the impl pin through spec.py drift.

Use tight inclusive lines with symbols or scoped search anchors, all `class: src` regardless
of repo role. Documents are named resources with matching support class and string locators,
canonical citation versus retrieval URL, revision, hashes/page counts. Public roots exclude
confidential and NDA material; applicable public proxies state their limits.

Self-check with the hash-pinned interpreter `<python>` and sibling `<spec.py>`:

```bash
<python> <spec.py> check <root> --require-license
<python> <spec.py> resolve <review> --root <root> --repo impl=<impl-checkout> --repo ref=<ref-checkout>
<python> <spec.py> show <review> --root <root> --repo impl=<impl-checkout> --repo ref=<ref-checkout>
<python> <spec.py> inventory <register-spec> --root <register-root> --repo linux=<ref-checkout> --pin linux --headers <header> --strict
```

`<review>` is the assembled file; tests substitute SF2-7's review fixture. Inspect skipped
counts; supply document bytes through `--docs-dir DIR` with `DIR/NAME` files. Inventory cannot
check finding prose: `<register-spec>` is a companion peripheral/facts file with actual
register/field payloads (the test uses SF2-7's peripheral fixture). Use each side's own companion,
pin and header for real comparisons. Resolve or record limitations for omissions, mismatches
and unknown expressions, never claim they passed. Return file, summary, resource entries,
check results, coverage exclusions and unresolved questions; verification is independent via
`templates/verifier-prompt.md`. Existing format 1 reviews use [FORMAT-1.md](../FORMAT-1.md).
