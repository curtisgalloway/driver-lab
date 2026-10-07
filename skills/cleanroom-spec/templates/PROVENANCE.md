<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
Fill-in provenance attestation for one clean-room spec; substitute every <angle-bracket>
placeholder. PRIVATE: this file and the spec it describes are the user's own record. Never
commit either to a public repository, attach them to an issue, or publish them in any form.
-->

# Provenance attestation: <device> spec

**Private record. Not for publication.** Clean-room output is never published (license-split
design, policy 1): this attestation and the spec stay with the person who ran the method. It
records how the spec was made so that they can show it later, for example to counsel.

## Spec

| Field | Value |
|---|---|
| Spec file | <path to the landed spec, e.g. docs/<device>-spec.md> |
| Spec sha256 | <full sha256 of the spec file as landed; the ledger's PASS line records its first 12 hex digits> |
| Landed | <ISO date> |
| Ledger line | <the provenance-ledger line for this revision, copied verbatim> |

## Who ran it

| Field | Value |
|---|---|
| Person responsible | <name of the person who ran the method and attests to this record> |
| Orchestrator | <agent, model and harness that ran cleanroom-spec> |
| Where | <the role of the machine or environment, e.g. "the test host"; not a host name> |
| Dates | <first investigator run> to <landing date> |

## Sources behind the wall

Every source the dirty side read. None of these was open to the spec's writer or to an
implementer.

| Source | Pin (repo@commit, or document and edition) | License | Read by |
|---|---|---|---|
| <reference driver tree> | <repo>@<commit> | <SPDX expression> | <investigator session(s)> |
| <firmware or device-tree tree> | <repo>@<commit> | <SPDX expression> | <investigator session(s)> |

## Which agent saw what

One row per session. "Saw" means what was in that session's context, not what it was allowed.

| Session | Role | Agent, model | Saw | Did not see | Transcript (path; never copied) |
|---|---|---|---|---|---|
| <id> | investigator | <agent, model> | <sources behind the wall> | <the spec draft, the target tree> | <path> |
| <id> | spec writer | <agent, model> | <investigator facts, the target tree, public documents> | <sources behind the wall> | <path> |
| <id> | verifier | <agent, model> | <the spec, the sidecar map, the sources at the pin> | <the writer's reasoning> | <path> |
| <id> | implementer | <agent, model> | <the PASSed spec, public documents> | <sources behind the wall, docs/provenance/> | <path> |

## Pins

| Side | Pin |
|---|---|
| Source (behind the wall) | <repo>@<commit> |
| Target tree | <repo>@<commit> |
| Documents | <document title, edition or sha256> |

## Verifier reports

| Check | Verdict | Report |
|---|---|---|
| Five-check verifier (`templates/verifier-prompt.md`) | <PASS or FAIL> | <report path> |
| Leak scan of the spec | <clean or findings> | <docs/provenance/<device>-scan-<date>.txt> |
| Accuracy pass (`spec-verifier`, clean-room driver specs) | <PASS, FAIL or not run> | <record path> |
| Output scan of the driver (pre-merge) | <clean, findings or not yet> | <report path> |
| Session audit (`cleanroom-implementer`) | <clean, findings or not yet> | <report path> |

## Attestation

I ran the method recorded above. To my knowledge no one who wrote the spec or the driver read
the sources behind the wall, and every exception is listed here: <none, or each exception and
how it was handled>.

<name>, <ISO date>
