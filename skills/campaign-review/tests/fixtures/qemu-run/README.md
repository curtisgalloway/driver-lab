<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Reduced QEMU run

**Terms:** identities are recorded hashes and conditions; verdicts are named check
outcomes. See the [glossary](../../../../../GLOSSARY.md).

Reduced from real run `e1000-cf2-20260926-01`, `runs/a2-ref-itr-2`, read-only
in CR5. Only identities and verdicts remain: the paths mapping, raw logs,
timestamps, observations and check details are omitted. All retained values are
copied, not invented. There are 19 PASS checks across itr and trace.

The source run predates CS-1 and records its own harness hash. This fixture checks
that the contract reads that format; it does not renew any qualification or claim
to exercise the current harness. The source run's files remain unchanged.
