<!--
SPDX-FileCopyrightText: 2026 Curtis Galloway
SPDX-License-Identifier: Apache-2.0
Fill-in prompt: substitute every angle-bracket placeholder before delegation.
-->

# Format 2 peripheral drafting prompt

**Terms:** a fact is an identified evidence record; a payload holds typed register/sequence/layout
values; a root declares license policy. See [the glossary](../../../GLOSSARY.md).

Produce a spec for <peripheral> (<IP block>, <board and instance>) from <source-checkout> at
<source-commit>, with integration for <target OS> at <target-checkout>. Destination: <root>;
output: <scratch-spec>. Load `peripheral-spec` and `spec-format`. Confirm every cited file's
license before reading for evidence; enforce the placement rule and preserve source notices.
Never cite confidential or NDA material in a public root. Return the file, summary, immutable
resource entries and scope limits. Do not write driver code or a placeholder verification record.

Fan out register, sequence, tuning and target slices to `hardware-investigator`; obtain
`kind: facts` YAML, not prose citations. Run registers twice independently and resolve all
value/coverage disagreements against the headers. Preserve ids and support, changing only
`section: facts` to the receiving section; explicitly settle id/resource collisions and reference
mappings. Invent no anchor for a line you did not read and no investigator returned.

Start from this minimal complete record template (its supported subset is not a finished spec).
Use the target's license in the SPDX header. Unknown register width/access/reset are absent.

```yaml
# SPDX-FileCopyrightText: <copyright-year> <copyright-holder>
# SPDX-License-Identifier: <file-license>
format: 2
kind: peripheral
id: <device-id>
name: <device-name>
resources:
  repos:
    - name: linux
      role: source
      url: https://example.invalid/source
      commit: "<source-commit>"
      license: <source-license>
      files: [{path: <header>, license_from: spdx-line}]
facts:
  - id: reg-ctrl
    section: registers
    data:
      register: {name: WIDGET_CTRL, offset: "0x0"}
      fields:
        - id: en
          name: WIDGET_CTRL_EN
          bits: [0, 0]
          meaning: block enable
          support:
            - class: src
              anchors: [{repo: linux, path: <header>, lines: [5, 5], symbol: WIDGET_CTRL_EN}]
    support:
      - class: src
        anchors: [{repo: linux, path: <header>, lines: [4, 4], symbol: WIDGET_CTRL}]
  - id: seq-init
    section: sequences
    claim: The driver clears CTRL before programming the UART.
    requirement: as-implemented
    data:
      sequence:
        steps:
          - id: s1
            action: write 0 to CTRL
            support:
              - class: src
                anchors: [{repo: linux, path: <header>, lines: [12, 12], symbol: widget_uart_init}]
    support:
      - class: src
        anchors: [{repo: linux, path: <header>, lines: [12, 12], symbol: widget_uart_init}]
```

Add complete register fields in databook order, performing steps and separate ordering
constraints, layouts, interrupts/DMA/addressing, identity, target protocols/binding/packaging,
gotchas and questions. Every actionable item is a supported record or a gap TODO; orientation
is not evidence. Target facts use a repo with `role: target` and `class: src` anchors. Source
and target in one tree still need a target-role entry for the target section.

`requirement` is `hw-required` (document-class support required), `comment-explained` (attribute
comments), `driver-choice` or `as-implemented`; children inherit or override it. Fields/steps
with their own support receive separate verifier sub-keys. Do not guess hardware requirements
from driver habits. Return inference as a separate record with premises/derivation and TODO.
Use `areas` for confidence. Hardware TODOs cover code-only width/reset/bit assumptions and
observable checks; the generated lists collect these records.

Document support names `resources.documents` with matching class and precise string locators.
Keep canonical citation URLs separate from workable retrieval URLs, with hashes and page counts.
For Arm manuals, retain the developer page and static documentation-service PDF retrieval.
Quote only a few lines when their expression matters. Use inclusive performing lines and
symbols, or a scoped `search` anchor for negative/global claims. Repeat counts yourself.

Before returning, use the pinned interpreter `<python>` and sibling `<spec.py>`:

```bash
<python> <spec.py> check <root> --require-license
<python> <spec.py> resolve <spec> --root <root> --repo linux=<source-checkout>
<python> <spec.py> inventory <spec> --root <root> --repo linux=<source-checkout> --pin linux --headers <header> --strict
<python> <spec.py> show <spec> --root <root> --repo linux=<source-checkout>
```

Here `<spec>` is the assembled, complete map in `<root>`, not the minimal template alone;
SF2-7's widget fixture is the executable test substitution. Repeat repo bindings for additional
sources and target entries. Supply document bytes as `--docs-dir DIR` with `DIR/NAME` files.
Inspect skipped counts. Inventory unknowns, mismatches and strict omissions are failures;
resolve or report them, never claim a pass. Return check results, omissions/scope limits and
open questions. Independent verification uses `templates/verifier-prompt.md` and `spec-verifier`.