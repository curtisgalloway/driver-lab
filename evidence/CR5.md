<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# CR5: deployment manifest and output contracts

**Terms:** a deployment manifest declares plugins and model roles; a contract
check validates output structure and provenance; an isolated run uses fresh
guests for one requested scenario. See the [glossary](../GLOSSARY.md) and
[format](../skills/campaign-review/INDEX-FORMAT.md#deployment-manifest-version-1-cr5).

The differential result remains CF-2's rebuilt driver and reference passing ten
scenarios twice. CR5 starts no QEMU guests and changes no driver or qualification.
Its contract check passes on CF-2's existing reference ITR run, the reduced CI
copy and both valid stubs. The live run has 19 PASS checks across itr and trace;
its identities and verdicts were read only and their hashes are unchanged.

Independent review is complete; its four findings are fixed as decided by the
orchestrator. The checkpoint remains with the orchestrator. No second independent
review, commit, push, pull request or user
config edit was performed. Private artifacts are in run `cr5-20260926-01`:
`VERIFY.txt` holds commands and output; `verification.json` indexes individual
stdout/stderr artifacts; `live-read-only.json` records before/after hashes.
That directory is read-only in the review-fix sandbox. New verification artifacts
are in temporary scratch storage for the orchestrator to retain, with the same
VERIFY.txt/verification.json names. Original run artifacts remain unchanged.

## Acceptance

| Criterion | Result |
| --- | --- |
| Manifest schema and reference plugins | `deployment.py` validates version 1; `evals/deployment.yaml` names the pinned-file adapter, QEMU fixture/producer and reader/implementer/reviewer roles |
| User config with reference default | Reuses `run-store.py` config discovery; explicit `--deployment` wins, then the deployment key, then the reference; temporary-config tests cover selection and override |
| Models by role | Queue units carry role/model; reader changes queue one comparison even for a sufficient campaign, without changing recorded verdicts; implementation remains tier 2 |
| Producer-class rule | Classes read from SPEC-FORMAT definitions and an explicitly supplied target tag table; unknown classes rejected; kernel passes with the actual e1000 table and fails without it |
| Source contract | Shared registry identity validator; reference adapter and generated-ID stub pass; nine missing-field variants fail |
| Backend contract | Native QEMU and neutral metadata checked by the same command; nine neutral and 14 native missing-field variants fail |
| Canned/live reference | `tests/fixtures/qemu-run/` reduces `e1000-cf2-20260926-01/runs/a2-ref-itr-2`; the same checker passes both, without starting guests |
| Boundaries | No plugin execution, source-content parsing, scheduler or role/producer-output checker; public files name only reference plugins; invented IDs are generated during tests |

The manifest schema and output contract are the new interfaces. The harness and
registry wire formats remain unchanged; the source validator is shared rather
than copied. Raw artifact review, model-session provenance and producer observation
quality remain C8 conventions. CR7 owns the full stand-in deployment exercise.

## Contract outputs

All successful checks emit `ok: true`, `findings: []`, exit 0. Fixture checks
add `overall: PASS`, `scenarios: 2`, `verdicts: {PASS: 19}`; the two result groups
are the requested itr scenario and its trace postprocessing, not two guest runs.

| Input | Contract output |
| --- | --- |
| Reference adapter, current harness registry entry | source status ok; exit 0 |
| Live CF-2 reference ITR run | 19 PASS; exit 0 |
| Reduced QEMU CI fixture | 19 PASS; exit 0 |
| Source stub with runtime-invented ID | source status ok; exit 0 |
| Neutral backend stub | 19 PASS; exit 0 |

Every negative stub below emits `ok: false` and one missing-field finding,
exit 1. Each field is removed independently; all other metadata stays intact.

| Stub family | Individually omitted fields | Outputs |
| --- | --- | --- |
| Source identity (6) | id; version; sha256; status; checked; provenance | All six rejected, exit 1 |
| Source provenance (3) | provenance.adapter; provenance.version; provenance.version_method | All three rejected, exit 1 |
| Neutral fixture identity (4) | fixture; fixture.name; fixture.version; fixture.sha256 | All four rejected, exit 1 |
| Neutral run provenance (5) | harness_sha256; kernel_sha256; image_sha256; conditions; conditions.scenarios | All five rejected, exit 1 |
| Native QEMU identity/conditions (8) | qemu_version; sha256; driver; accel; scenarios; dut_mem; host_kernel; python | All eight rejected, exit 1 |
| Native QEMU hashes (6) | sha256.qemu; sha256.harness:l02harness.py; sha256.harness:guest-init.sh; sha256.kernel; sha256.initramfs; sha256.busybox | All six rejected, exit 1 |

`source-missing-*`, `backend-missing-*` and `native-missing-*` artifacts hold each
full JSON output; later `-final2` artifacts supersede earlier outputs where present.
Tests additionally reject short/null hashes, empty conditions, multiple requested
scenarios, duplicate scenario/check names, malformed JSON, duplicate JSON fields
and contradictory PASS summaries. Well-formed FAIL and ERROR results satisfy the
contract while retaining those outcomes. Missing files exit 3.

## Verification

Required uv invocations used the existing offline cache, without changing machine
configuration or installing project dependencies.

| Command/check | Output |
| --- | --- |
| `uv run --with pyyaml python3 -m unittest discover -s skills/campaign-review/tests` | 105 tests, OK after review fixes; exit 0 |
| `uv run --with pyyaml python3 skills/campaign-review/scripts/index_check.py evals/e1000` | OK: 28 claims, 28 qualification, 28 result, 8 observation, 31 item, 95 verification, 3 candidate_round; exit 0 |
| `uv run --with pyyaml python3 skills/campaign-review/tests/test_sweep.py --matrix` | Nine rows, all ok; exit 0 |
| `uv run --with pyyaml python3 skills/campaign-review/scripts/sweep.py evals/e1000 --deployment evals/deployment.yaml --json` | 96 stale, 84 current, 13 superseded; 19 units; not sufficient; exit 1 expected |
| Contract checker on reference adapter, live/canned runs and all stubs | Outputs above; expected exits throughout |
| Actual e1000 tag-table class check | kernel accepted with the supplied spec, exit 0; unknown producer class without it, exit 1 |
| Review regressions | Actual boot ERROR, early FAIL and collection ERROR satisfy the contract; undeclared smoke is rejected; malformed YAML exits 1 as JSON; argument errors exit 2 as JSON |
| Pylint and Pyink on changed Python files | Clean after filename lint annotation; exit 0 |
| Portability scanner on campaign-review scripts | 0 findings; exit 0 |
| Privacy checker, tracked and new files; requested diff grep | Clean; no requested-pattern hits |
| `git diff --check` | Clean |

The real sweep preserves CR4's blockers and first batch: second reading, then
re-verification of AF-1-reading-coverage and SR-8-independent-reading. No queued
unit was executed. Its source identities remain CR3/CR4 snapshots; CR5 refreshes
only the local harness adapter as a contract example, without writing the registry.
The original implementation suite had 99 tests. The post-review 105-test suite
includes six new regression tests with multiple cases. The final lint pass also
shortened one test-helper docstring to the 88-character limit.

## Review

A read-only Codex reviewer, `gpt-6-astra`, reviewed the diff, contracts and run
artifacts. Its report is `codex-review-cr5.md` in run `cr5-20260926-01`. It
requested changes for four findings; all four fixes below were **decided by the
orchestrator**. No second independent review was performed.

| Finding | Disposition |
| --- | --- |
| R1, medium: valid native QEMU failure records rejected | Fixed, decided by the orchestrator. Accept boot ERROR without a requested-scenario result and FAIL before the first completed check. Also recognize the harness's between-scenarios collection ERROR. Regressions call the actual harness run/scenario code with process and guest entry points mocked, preserving ERROR/FAIL outcomes while the contract passes. |
| R2, medium: undeclared scenarios accepted | Fixed, decided by the orchestrator. Result names must be declared or reserved auxiliary/error groups. Adding passing smoke to the itr fixture fails for native and neutral identities. Boot and between-scenarios groups require ERROR with no checks; boot cannot accompany scenario execution. Native capture requires smoke; neutral capture requires the declared scenario. The equivalent neutral naming rules are documented in INDEX-FORMAT.md. |
| R3, medium: malformed manifest produces traceback | Fixed, decided by the orchestrator. Deployment loading normalizes YAML constructor errors, including an invalid date's ValueError; the sweep also catches malformed-input ValueErrors. Both CLIs return JSON findings and exit 1 for invalid timestamps and malformed YAML syntax. |
| R4, low: argument errors break strict JSON | Fixed, decided by the orchestrator. A shared internal argument parser preserves each CLI's findings shape when --json is requested. Missing flag values, unknown flags and the sweep's missing campaign return one JSON document, empty stderr and exit 2. |

The reviewer confirmed the reference/live/canned/stub contract passes, all 32
missing-field rejections, role routing, class validation and privacy. Its full
suite attempt had 57 temporary-directory errors among 99 tests because that
read-only review sandbox could not create temporary files; that was an environment
limitation, not a reported implementation failure. The implementer's new
regressions produced 15 failing subcases before the fixes and passed afterward.
The full post-fix verification is recorded above and in the temporary artifacts.

Review-fix decisions: use the same reserved result-group vocabulary for neutral
backends so arbitrary extra scenarios cannot masquerade as postprocessing; permit
capture on any declared neutral scenario because the smoke restriction belongs
to the native harness. Share argument-error formatting between the two affected
CLIs to keep their JSON behavior consistent. The orchestrator selected all four
fixes; no source adoption, spec change or QEMU execution was added.

## Decisions and limits

- Retain Claude Fable 5.1 for reader/reviewer and CF-2's `gpt-6-astra` for
  implementer: preserve the recorded reader and avoid an invented model-change trigger.
- Route readings to reader, implementation to implementer, and other work to
  reviewer: use the three specified roles without adding another role interface.
- Require all three roles and reject unknown manifest fields: incomplete or
  misspelled deployment configuration must not silently choose an agent.
- Resolve relative config values beside the config file; keep CLI paths relative
  to the working directory: configuration remains stable across campaign directories.
- Store commands as argument lists and check captured output only: invocation,
  authorization and safety stay with the named skill; CR5 starts no execution flow.
- Reuse registry validation, accepting the existing adapter envelope: one definition
  of required source provenance serves both registry and contract checks.
- Support neutral fixture identities alongside native QEMU metadata: deployments
  need no QEMU-specific names, and existing harness records require no migration.
- Preserve native boolean checks as PASS/FAIL and scenario ERRORs separately:
  earlier completed checks must not disguise later infrastructure failure.
- Separate contract success from source availability and test success: valid
  blocked/unknown, drift, FAIL and ERROR outputs remain usable evidence records.
- Require one declared scenario plus its postprocessing records, and check only
  the two metadata files: the CI fixture stays small; actual isolation and raw
  artifact completeness still need review.
- Read producer classes from definitions and explicit tag-table rows: e1000's
  kernel class stays local, and no private-source search or global promotion occurs.
- Generate invented stub IDs at runtime and provide missing-field variants from
  one generator: public files need no private plugin names or duplicated fixtures.

Open items: orchestrator checkpoint; CR6's actual comparison
reading; CR7's stand-in deployment. No new spec or driver finding is claimed.
