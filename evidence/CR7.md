<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# CR7: a stand-in private deployment

**Terms:** a stand-in is an invented deployment created outside the public repository;
a registry records source identities without their contents; a sweep compares those
identities and queues work; a stub emits canned metadata without operating a device.
See the [glossary](../GLOSSARY.md) and
[index format](../skills/campaign-review/INDEX-FORMAT.md).

The driver reconstruction result remains CF-2's candidate and reference passing the
differential acceptance runs. CR7 exercises the review method, with no driver or
hardware execution. **Automated and live validation pass; stopped before independent
review.** The queued `gpt-6-astra` reading returned four PASS verdicts. Integrating
it into the stand-in index clears the queue while preserving stale history.
The resumed sandbox made the original run store read-only, so the verified private
updates were staged outside the repository; the user installed them on 2026-09-27
(the orchestrator's harness blocked it from running the installer or the stand-in
sweep) and reran the original stand-in's sweep: sufficient, empty queue. Independent
review follows.

## Acceptance

| Criterion | Evidence and result |
| --- | --- |
| Separate deployment with no method changes | The [generator](../skills/campaign-review/tests/standin.py) creates a root, run store, campaign, configuration, two invented documents and a local-layer chip spec outside the repository. Existing sweep, index and contract commands run unchanged. |
| Manifest through the deployment key | An isolated user configuration selects a relative manifest beside the configuration file; the run store resolves through the existing utility. Removing that manifest produces exit 3, proving there is no silent reference-manifest fallback. |
| Stub plugins only | All declarations point to a generated local stub skill. The [self-contained stub](../skills/campaign-review/tests/fixtures/standin_plugin.py) emits captured source identities and neutral fixture metadata; no reference plugin is executed: the QEMU backend is neither imported nor run, and the pinned-file adapter never reads a source. The sweep does import one helper, `module_at`, from `pinned_file_adapter.py` (through `deployment.py`); that is a shared utility, not plugin execution. Both outputs satisfy the contract checker. |
| C2 invalidation | Exact stale sets for document changes, mapped and unmapped sections, unreviewed maps, spec changes, declared dependencies and unknown dependencies. Unrelated source readings stay eligible. Existing nine-row C2 matrix also passes. |
| Unreadable sources | A child-process audit hook denies every open under the invented source directory. A control open proves denial is active; separate version-only and hash-only changes each stale exactly the citing reading. Any attempted source open during the sweep fails the test, even if caught by the sweep. |
| Role changes | Editing only the configured reader role changes every queued reading's model and adds a comparison reading. Freshness and the recorded index remain unchanged. |
| No invented IDs in public files | Runtime IDs are checked for collisions before generation and scanned after tests across tracked and publishable untracked filenames and file bytes, including binary files. A separate final scan also includes the live stand-in inventory. |
| Live tier-1 re-verification | The orchestrator ran the ready unit using Codex CLI `gpt-6-astra`, high reasoning effort: 4 PASS, 0 FAIL, 0 UNVERIFIABLE, 0 GAP, 0 ADJUDICATE; 52 seconds and 53,756 tokens. All four stable claim keys and summary counts validate. |
| Post-reading sweep | On the staged updated index, and again by the user on the original stand-in after installation (`post-install-sweep.txt` in the private run): sufficient for the declared synthetic scope, S1–S5 met, no blockers, empty queue and batch. One old reading stays stale, discharged from the queue by the new reading's complete coverage. |
| Private update installation | Installed by the user: the installer's read-only check reported 24 pending files and the install wrote 24, each guarded by its expected hash. |
| Independent review | Read-only Codex (`gpt-6-astra`): the live record, installed index and post-install sweep are consistent; three findings, all fixed (see Review). |

## Verification

Private run `cr7-20260926-01` retains the original commands, outputs, hashes,
ID inventories, queued unit, handoff and live record. The integration handoff
supplies the resumed checks and private index updates for that run. Neither the
stand-in's location nor its IDs are recorded here. The eight new tests run in the
existing discovery suite.

| Check | Result |
| --- | --- |
| `uv run --with pyyaml python3 -m unittest discover -s skills/campaign-review/tests` | 114 tests, OK; exit 0 |
| Stand-in index checker after integration | 1 claim, 3 verification entries (2 canned, 1 actual), 1 unqualified optional claim; exit 0 |
| Stand-in spec checker with `--require-verified` | 1 spec, 0 warnings; exit 0 on the original live workspace |
| Live stand-in sweep | Baseline exit 0; editorial edition queues one re-verification, exit 1; staged live result clears it, exit 0, `ok: true`, `fresh: false`, 3 current entries and 1 historical stale entry |
| `index_check.py evals/e1000` | 28 claims, 28 qualifications, 28 results, 8 observations, 48 items, 99 verifications, 3 candidate rounds; exit 0 |
| `test_sweep.py --matrix` | All nine exact expected sets pass; exit 0 |
| `sweep.py evals/e1000 --json` | Exit 1: existing campaign blockers remain; no index or source identity was edited |
| Leak scan before the live reading | Raw spec-versus-stub scan flags only the standard SPDX banner. With exactly those banners removed from derived scan inputs, no shared runs or identifiers remain; original inputs and raw finding retained. |
| Live record leak scan | Unmodified record against the invented stub: 0 shared runs, 0 high-signal identifiers, 0 all-caps identifiers; exit 0, no normalization or whitelist needed |
| Stand-in ID scan | 402 distinct generated IDs from the original and resumed test runs, live stand-in and appended reading; zero hits in public filenames or bytes |
| Privacy check and requested diff scan | 279 tracked files plus all five new public files clean; no requested-pattern hits in added lines or new files |
| Pyink, Pylint and whitespace check | All three new Python files pass formatting and lint; `git diff --check` clean |
| Reader input and record integrity | All seven input hashes and the brief hash still match; record's spec and both source hashes match; 1,864-byte record preserved verbatim, including its original lack of a final newline |

The required uv invocation used an existing offline cache. Initial empty-cache
attempts could not resolve PyYAML; an online attempt failed DNS. No dependency,
user setting or installed package was changed.

## Live reading and integration

The orchestrator reports start at 2026-09-27T06:45:55-07:00 and end at
06:46:47-07:00, CLI exit 0, with cost taken from its command log. The reader used
Codex's read-only sandbox with approval never; the CLI's output option saved the
verbatim final response. The record hash is
`86e383decf6be42244baf3a7d7efebfee5198f32b25e2530554348bbc4b06fcd`.
No transcript was opened, copied or hashed during integration; its locator and
the orchestrator-supplied provenance are in the private integration ledger.

The new basis pins both current source identities and the unchanged spec. The
new independent accuracy entry covers sections 1 and 2, revision 1, with sequence
3, the actual cost and an assessment of zero accuracy failures and zero R items.
Both canned entries and their original bases remain unchanged. The actual record
and a provenance summary are copied under the stand-in root for relative evidence
links; the original record remains untouched. No comparison adjudication against
the canned history is claimed. The second document does not state an edition;
the registry's version is an operator label, consistent with the reader recording
the edition as unstated.

## Limits and pending work

The test's optional claim and canned prior readings establish a controlled metadata
baseline, not device sufficiency or genuine previous independent readings. The live
reader is the first actual model reading of this stand-in. The invented edition
adds editorial text only; source drift does not adopt a new real source edition or
change a driver requirement. Metadata status `ok` means an identity is available,
not that the sweep can read the source bytes.

The leak control is the invented plugin source, not a reference driver. It tests
the scan workflow only. Read access was constrained by the brief, not by a read
boundary; the read-only sandbox enforced no reader writes. The brief forbade
network use, but the invocation had no network flags and no network isolation or
access audit is claimed.

The stopping report's round cap counts two canned entries and one actual reading,
reporting three rounds and "limit reached." There are no remaining findings or
queued readings; the report still returns sufficient. That result applies only
to the declared optional-claim synthetic scope and establishes no device coverage
or second actual reading. The report was validated on a relocated stand-in copy;
only its private run-store configuration was relocated, and that configuration is
excluded from the installation payload. The user installed the payload into the
original run on 2026-09-27; a fresh reviewer then reads the final diff, test
artifacts and live result (see Review). Nothing about a real private deployment was used.

## Review

One independent read-only reviewer (Codex `gpt-6-astra`, through the consult helper) read the
diff, the private run's artifacts, the live record and the post-installation sweep. It
reproduced all seven input hashes, the brief and record hashes, the four verdicts, the nine
matrix rows and the post-reading report (sufficient, empty queue, one historical stale entry)
in memory. Its sandbox had no writable temporary directory, so 71 of the 114 tests errored
there at setup; the orchestrator's run passes all 115 after the fixes. Each finding was
decided by the orchestrator. The orchestrator also made the fixes itself, because its harness
blocked resuming the implementer on this unit.

| ID | Severity | Finding | Disposition |
| --- | --- | --- | --- |
| R1 | medium | The source-denial test's audit hook sees only its own process: a child process could read the denied sources unobserved (reproduced by the reviewer with a 420-byte child read) | Fixed: the launcher in `test_standin.py` now also denies and records every child-process start (`subprocess.Popen`, `os.system`, `os.exec*`, `os.posix_spawn`, `os.spawn*`, `os.fork*`, `pty.spawn`), with a negative control proving the denial engages, and fails if the sweep starts any child |
| R2 | medium | "neither reference adapter nor QEMU backend is imported or invoked" was inaccurate: the sweep imports `module_at` from `pinned_file_adapter.py` through `deployment.py` | Fixed: the Acceptance row now says no reference plugin is executed and discloses the helper import |
| R3 | low | The ID scanner skipped directory and dangling symlinks and read file symlinks' targets instead of the link text Git publishes (no current leak: no symlinks among the scanned paths) | Fixed: `id_hits()` in `standin.py` checks names independently and reads symlink texts; `test_id_scan_finds_names_symlink_texts_and_bytes` covers names, bytes, dangling, directory and file symlinks |

