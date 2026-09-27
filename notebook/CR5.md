<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# CR5: deployment manifest and contract check

**Terms:** a manifest declares plugins and model roles; provenance identifies
the tools and inputs behind a result. See the [glossary](../GLOSSARY.md).

## 2026-09-26T20:40:20-07:00 — implementation and local checks

- The existing adapter already supplied the contract's identity fields. Extracted
  that validation for reuse rather than introducing another source-output format.
- The real QEMU run uses boolean checks and scenario-level errors. Kept that format
  readable and added a neutral fixture representation for other deployments.
- The source-read regression also blocked newly introduced manifest loading;
  loaded roles before closing the test's read boundary, preserving its purpose.
- The legacy run-store command name needed its lint annotation before the module
  docstring. Final checks passed; review and checkpoint stay with the orchestrator.

Conclusions, outputs and decisions: [evidence](../evidence/CR5.md). Exact commands
and artifacts: private run `cr5-20260926-01`. No QEMU launch or independent review.

## 2026-09-26T20:58:45-07:00 — orchestrator-directed review fixes

- The harness has a between-scenarios collection error in addition to boot and
  per-scenario failure paths. Regressions now exercise actual harness control
  flow with guest/process entry points mocked, without starting QEMU.
- Invalid YAML dates raise a constructor ValueError; normalizing parser errors
  at the manifest boundary keeps both CLIs' findings responses intact.
- The pre-fix regressions reproduced the findings. The full post-fix suite has
  105 passing tests; exact outputs stay in temporary scratch storage because the
  supplied run directory is read-only in this sandbox. The review dispositions
  and final verification are in the evidence file; checkpoint remains pending.
