<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Glossary

Shared terminology for this repository. This initial glossary covers driver-specification
evaluation; add other terms as the documents that use them are updated.

| Term | Meaning |
| --- | --- |
| Agent | An AI assistant with tools; here, an author, implementer, or reviewer in a recorded session. |
| Skill | Instructions and optional supporting tools that guide an agent through a task. |
| Plugin | A package of related skills and optional tools. |
| Specification (spec) | A document describing hardware behavior precisely enough to implement a driver. |
| Driver | Software through which an operating system controls a device. |
| OS / kernel | Operating system / its core that manages hardware and supplies driver interfaces. |
| API | An interface a program uses to call another software component. |
| SDK | Software development kit: headers, libraries, and tools for building against a platform. |
| Corpus | The pinned collection of source code and documents used as reference evidence. |
| Pin | An exact revision, edition, or file digest identifying an input. |
| QEMU / device model | An open-source machine emulator / its software imitation of a hardware device, which a guest OS drives as if it were real. A device model is a separate implementation, not the silicon. |
| Differential test | Running a reference driver and a candidate under identical scenarios and comparing their outcomes and register traces. |
| Emulated evidence | A result observed on a device model (QEMU or another emulator; class `[emulated]`, adopted 2026-09-25); weaker than a hardware measurement because models are often lenient. It cites the model version and the runs, states what was observed from outside the model, and is never the sole authority for a fact. |
| RTL | Register-transfer level: the hardware design written in a language such as Verilog or VHDL. As evidence (`[rtl]`), the strongest authority for digital register behavior on the revision it names. |
| Conflict entry | A recorded disagreement between evidence sources, kept beside the claim with both readings, the resolution, and the assumption that justified it. |
| Hash / digest | A fingerprint of file contents; identifies bytes, not their correctness. |
| Claim / verification record | A statement checked against evidence / the separate report recording that comparison and its limits. |
| Carry-forward | Retaining an earlier finding for unchanged text; it is not a fresh reading of its sources. |
| UART / baud | A serial communication controller / the signaling rate of its connection. |
| Mux | A selector that routes a connection; its selected mode can change which setup steps apply. |
| GIC | Arm's Generic Interrupt Controller, which routes interrupt requests to processor cores. |
| Requirement ledger | The independently authored answer key of hardware requirements used for evaluation scoring; called the ledger in evaluation documents. |
| Candidate | The generated specification or driver being evaluated. |
| Reference driver | The existing driver selected as comparison evidence; it can contain defects. |
| Corroborating implementation | Another OS's driver for the same device (Zephyr, NuttX, FreeBSD, …), used only as completeness evidence after its lineage and hardware version are checked; not an authority on the hardware. |
| Evaluator | The preparation and testing side allowed to inspect reference material; separate from an isolated implementer. |
| Guest | An operating system running inside a virtual machine or container environment, separate from the host. |
| OCI image | A container image stored in the standardized Open Container Initiative format, with content identified by digests. |
| Initramfs | An initial filesystem loaded into memory with the kernel, used for startup or as a small self-contained system. |
| Netboot | Fetching boot files over the network before starting the operating system. |
| NFS root | A root filesystem accessed over the Network File System protocol; it requires working networking during startup. |
| Arm / experimental arm | Arm is the processor architecture company in hardware references. An experimental arm is one study condition: specification generation with or without the skill, or downstream implementation from that condition's spec. Generation and implementation pairing are assessed separately. |
| Baseline / treatment | The without-skill / with-skill generation conditions. |
| Paired run | Runs with recorded conditions held constant except for the intended experimental difference. |
| Recall / precision | Coverage of required facts / correctness and support of the claims actually made. |
| Reconstruction | Implementing a driver from a spec on the same OS as the reference driver. |
| Differential testing | Running implementations through shared scenarios and comparing observable behavior. |
| Fixture | The prepared hardware and connections used to execute repeatable tests. |
| Fault injection | Deliberately provoking a failure condition to test recovery. |
| Mutation check | Deliberately introducing a defect to verify that a test detects it. |
| Planted defect | One deliberate defect used in a mutation check; in the QEMU harness, an edit to a disposable copy of the reference driver. An *equivalent mutation* breaks no rule the manual states, so no test should fail on it. |
| Phase | In the QEMU harness, the guest command or host action (a link toggle, a wait) during which a register access happened; "idle" when none was running. |
| Deferred check | In the QEMU harness, a check a scenario registers and the harness evaluates after QEMU exits, from the register trace or the packet captures. |
| Claim (L02) | A harness check whose PASS the differential run will cite as evidence about the candidate driver. Checks that only confirm a scenario's stimulus happened (a flood ran, a ring wrapped) are *preconditions*, not claims. |
| Qualified check | A claim whose check was made to fail by a planted defect that violates it, for that reason, while the unmodified reference passed the same scenario on the same harness. Qualification is specific to that defect and those conditions, not proof the check catches every violation. |
| Acceptance gate | A predefined condition that must be met before an artifact advances or is accepted. |
| Milestone | A bounded deliverable with dependencies, acceptance criteria, verification, review, and a recorded checkpoint. |
| Validation contract | A test's requirements, independently supported expected observations, decision rule, setup, and limits. |
| Run manifest | The record identifying an experiment's inputs, settings, versions, access rules, and output artifacts. |
| Preparation manifest | An input and decision record that lists unresolved launch prerequisites; it is not a frozen execution manifest or permission to run. |
| Sidecar | A separate record linked to existing artifacts by identity or digest, without modifying those artifacts. |
| Custody | Locating and recovering the exact archived bytes used in an earlier run. |
| Qualification | Demonstrating that a build, access control, fixture, or check works within its declared scope. |
| Device tree / DTB | A hardware description supplied to a kernel / its compiled binary form. |
| GPIO / IRQ | General-purpose input/output pin / an interrupt request that signals an event to a processor. |
| FCS | Ethernet frame check sequence: the error-detection bytes that a capture may include or strip. |
| STP / RSTP | Spanning Tree Protocol / Rapid Spanning Tree Protocol: Ethernet switches exchange control frames to prevent loops. A port can have physical carrier while still withholding ordinary traffic. |
| BPDU | Bridge Protocol Data Unit: a spanning-tree control frame advertising a switch port's role and state, including whether it is learning addresses or forwarding traffic. |
| ARP | Address Resolution Protocol: the exchange that discovers the Ethernet destination for an IPv4 neighbor before sending ordinary IPv4 traffic. |
| defconfig | A kernel's starting configuration; the resolved build configuration must still be recorded. |
| Evidence channel | A means of collecting observations, such as a traffic peer or instrument capture; its suitability must be established for the observation. |
| Test envelope | The approved equipment configuration, operations, rates, duration, and other limits of a test. |
| Held-out test | An evaluation case kept out of development and tuning, used afterward to assess transfer to unfamiliar cases. |
| Regression test | A repeatable check that detects the return of a previously prevented defect. |
| Test model | A simplified executable description of expected behavior; its assumptions also need validation. |
| Convergence | Progress toward predefined acceptance conditions as defects and uncertainty are resolved; repeated agreement alone does not establish correctness. |
| Adjudication | Resolving conflicting readings of evidence, with unresolved questions kept explicit. |
| SPI | Serial Peripheral Interface in bus discussions; Shared Peripheral Interrupt in Arm GIC descriptions. |
| Erratum | A documented hardware defect or deviation, often specific to a device revision. |
| Blind requirement list | Requirements written from a device manual before any spec exists, used afterward to measure what the spec left out; the e1000 list is `evals/e1000/requirements.yaml`. |
| SDM | The Intel 8254x Software Developer's Manual (document 317453-006, revision 4.0), the e1000 hardware reference. |
| Operator | In the driver-porting runs, the coordinating agent session that prepares inputs and briefs, launches the other agents, and writes the evidence; it writes no driver code. |
| Review swarm | The `review-swarm` skill: four reviewer agents with narrow mandates, a mechanical check that drops findings not quotable from the code, and a referee. |
| Lab notebook | Append-only, timestamped notes per unit of work (chapters) plus an index, kept as the work happens (`lab-notebook` skill); the driver-porting notebook is `notebook/`. |
| Process log | A per-project log of where the agent's process cost time, as input for improving instructions and skills; for driver-porting, `PROCESS-NOTES.md`. |
| Bubblewrap (`bwrap`) | A Linux tool that runs a program in a private view of the file system, showing it only the directories it is given; L02's implementer sandbox was built on it. |
| strace | A Linux tool that logs the system calls a program and its children make (files opened, programs run, network connections); L02's implementer audit read its log. |
| Canary | A file planted in the workspace and read in a pilot run, to prove the audit log records the agent's reads before the log is trusted. |
| Repair round | In L02f2, one repair of the candidate by the implementer, then the command-log audit, a build, and an isolated rerun of every scenario. |
| Receive hold | QEMU's e1000 model delivers no received frame for one second after any write to RCTL; not described in the manual (L02f2, V6). |
| Half / full duplex | Whether a link carries traffic one direction at a time, sharing the wire and detecting collisions (half), or both directions at once (full). |
| Carrier sense (CRS) | The PHY's signal to the MAC that the wire is busy. In half duplex the MAC defers to it; the e1000 manual expects the PHY to assert it during every transmission (SDM §13.7.12). |
| PSCON | The 82540EM PHY's register 16, PHY Specific Control (SDM Table 13-31); its bit 11 decides whether the PHY asserts carrier sense on transmit. |
| Spec gap / spec error | A question a spec leaves unanswered, filed by an implementer / a place where the spec is wrong. |
| Spec revision | A numbered, hashed version of a spec; each is verified before use, and a change produces a new revision rather than an edit in place (L02s made revision 5). |
| MAC / PHY | The two halves of an Ethernet controller: the MAC moves frames between memory and the link logic; the PHY drives the wire, negotiates speed and duplex, and reports link and carrier. On the 82540EM the PHY is internal and reached through the MDIC register. |
| Run ledger | The private per-run record in the run store: identities, commands, artifacts, attempts and reviewer references. Public evidence files cite it by run ID; distinct from the requirement ledger. |
| Settling interval | In the QEMU harness, a documented, bounded wait after carrier returns and before recovery pings, longer than the model's receive hold plus a margin and confirmed from traces (L02f2b). |
| Acceptance stage | The closing part of L02f3 (formerly the separate unit L02g): a final isolated run set, the A1–A7 acceptance table, and an independent review. |
| Basis | The identities a verdict rests on: spec revision and sections read, source pins, harness, emulator or fixture, candidate build and toolchain, the model that read or implemented, and run IDs (continuous review, proposed 2026-09-26). |
| Campaign | One device's spec, candidate, checks and evidence under one declared scope; L02's e1000 work is one. |
| Status index | One small file per campaign listing each tracked verdict with its basis and status (`current`, `stale`, `contested`, `superseded`), plus the open items; M16's "latest-status index". |
| Stale / contested / superseded | A verdict whose basis changed, not shown wrong but not citable as current / one that newer evidence contradicts, with a conflict entry / one replaced by a newer verdict and kept for history. |
| Sweep | The mechanical comparison of every basis in a status index against the current identities, producing the stale set and a queue of re-review units. |
| Cost tier | How re-review work starts: tier 0 on every change with no model; tier 1 queued and run by agents in batches a person authorizes; tier 2 only on a person's decision. |
| Item (R / E / W) | A finding for a later spec revision: R changes what a driver must do, E changes the evidence for a claim, W changes wording or form only. |
| Sufficient for scope | The stopping rule's state: the declared scope is met or its gaps are recorded shortfalls, and further work starts only from a trigger. |
| Reading lineage | One reader's sequential fix passes, counted once when checking independence; an independent reader adds another lineage. |
| Review batch | Up to three proposed units from a campaign's queue; each needs its own reviewed checkpoint, and the sweep runs again between units. |
| Stopping report | The sweep's evaluation of S1–S5, stating whether the campaign is sufficient for its declared scope and listing what blocks it. |
| Guarded queue | Proposed review units whose selection obeys the batch cap and the requirement for a recorded user decision on tier-2 work; listing a unit does not run it. |
| Comparison reading | An independent reading by a new reader model, compared with the previous record claim by claim; disagreements are resolved against the cited authority before changing verdicts. |
| Shortfall | A gap in the declared scope recorded with a reason (`unobservable`, `blocked`, `out of scope`, `not worth it`) and a condition that would reopen it, instead of being worked. |
| Deployment | One installation of the method with its own sources, run store, specs, models and fixtures; a private one keeps all of them inside it. |
| Source registry | A deployment's list of its sources by local ID, version and hash, so change detection works without reading the content. |
| Pinned-file adapter | A local command that hashes a named file, compares it with its expected hash, and returns identity metadata without returning content. |
| Change map | Reviewed metadata connecting an old and new file hash to changed sections, check names, or scenarios. Missing or uncertain mappings require wider invalidation. |
| Eligible record | A verdict still current after a sweep's identity checks. This is a freshness filter, not a campaign acceptance decision or an additional reading. |
| Deployment manifest | A YAML file declaring plugins and models by role. The user config can select a private manifest; otherwise the repository reference applies. |
| Contract check | A structural check of plugin outputs and required provenance; it does not establish source availability, driver correctness or test isolation. |
| Model role | Reader, implementer or reviewer: a named job mapped to an agent and a model in the deployment manifest. |
| Plugin (extension point) | A skill, packaged like this repository's own, implementing one extension point for a deployment: source adapter, evidence producer, implementer or reviewer, or fixture/harness backend. |
| Claim map | Per campaign, the data file linking each claim ID to the harness checks that support it and the planted defects and runs that qualified it; proposed for e1000 as `evals/e1000/claims.yaml`. |
| Acceptance set / isolated run | The ten e1000 harness scenarios run for the reference and the candidate / one scenario on freshly booted guests, so nothing left over from another scenario reaches it. |
| L01 review trio | The three reviews a candidate change gets: a reference-driver review, a requirements review against the blind list, and `review-swarm` on the diff. |
| Root / root marker | A directory of specs / its `board-specs.yaml`, naming the root's layer; the board-expert reader merges several roots in layer order. From the license split on, the marker also declares the root's license and accepts list. |
| Overlay | A spec in one root that adds to or corrects a spec of the same ID in another root, without copying it. |
| Pin | A spec line naming a source tree and its commit (`Source pin: linux@abc123`); anchors cite lines at that commit. In a board spec the pin is a `resources.repos` entry with a full commit `ref` and a `license:`, and no `Source pin:` line is needed. |
| Accepts list | The SPDX license identifiers a spec root allows its anchored sources to carry (`accepts:` in the root marker). |
| License gate | The check that fails a spec citing a source whose license the root's accepts list does not include: `anchor_check.py --root` for a peripheral spec's pins, `spec_check.py --require-license` for a board spec's `resources.repos` licenses, and `spec_check.py` always for a board spec's `[src:]` anchors. In format 2, `spec.py check`: every `src`, `DT` and `rtl` anchor and every notice names a repos entry the file's root accepts, and every fact reference reaches only such entries, followed transitively (D13). |
| `[src]` fact | A board-spec fact read from source code at a pinned commit, cited with `[src:<repo>: path:L]` anchors into a `resources.repos` entry whose license the root accepts; a fact about the code, not a hardware requirement, and needs no hardware TODO (`SPEC-FORMAT.md`, "Facts read from source"; added 2026-10-07, RG-T1). |
| Placement rule | A spec lives in the most restrictive repository among the sources it anchors to, and never cites a source more restrictive than that repository. |
| Spec repositories | `hardware-specs-gpl`, `hardware-specs-docs` and `hardware-specs-permissive`: the three public homes for specs, by license. |
| Open side | driver-lab outside its frozen archive since the license split: the method for specs that cite their sources and are published where their licenses fit. |
| Frozen archive | The parts of driver-lab kept as history after the split (evals, evidence, notebook and the documents describing them); still checked by CI, no new rounds. |
| SPDX | The standard short identifiers for licenses (`GPL-2.0-only`, `MIT`, `CC-BY-4.0`) and expressions combining them with `OR`, `AND` and `WITH`. |
| Named pin | One of several pins in a spec, each with its own name and SPDX license (`Source pin: linux@abc123 GPL-2.0-only`); an anchor names the pin it resolves against (`[src:linux: drivers/net/foo.c:120]`). |
| Docs registry / named doc anchor | A `docs:` list in a peripheral spec's front matter giving each cited document a name, title, URL and SHA-256 hash / a citation of a listed document by name and page or section (`[doc:trm p.12]`, no space after `doc:`), which `anchor_check.py` checks. Distinct from a board spec's `resources.docs`. |
| Target root / refusal | The spec root whose accepts list governs which sources `hardware-investigator` may cite for one question / its return when a needed source's license is not on that list: the source, license, list and reason, with no fact from the source. |
| Anchored facts | Short statements about hardware, each with a `[src:]` or `[doc:]` anchor and a pinned, licensed source; what `hardware-investigator` returns and `peripheral-spec` builds on. |
| YAML / JSON Schema / validator | A text format for structured data / a standard language (current version: draft 2020-12) stating what shape such data must have / the library that checks data against a schema. Spec format 2 stores specs as YAML checked against a JSON Schema ([design](docs/SPEC-FORMAT-V2.md), proposed 2026-10-08). |
| Spec format 2 | The proposed replacement for the Markdown spec formats: every spec kind as one YAML file of fact records, validated by a JSON Schema, with Markdown generated from it ([design](docs/SPEC-FORMAT-V2.md)). |
| Strict loader (`load_strict`) | The one function every spec format 2 tool reads YAML with (`skills/spec-format/scripts/specload.py`). It admits one spelling per value: only `true`, `false`, `null` and integers are not strings, and anchors, tags, duplicate keys and invisible characters are errors with a line and column. |
| Schema fragment | The partial JSON Schema an extension supplies for its own support class (`source-observed`, design D15), named in a root marker's `extensions`. It may only add fields; `spec.py` refuses one that would loosen the core schema. |
| Fact record / fact id | One claim in a format 2 spec, stored as a mapping with its claim text and structured support / the stable identifier it keeps through every edit (`addressing-model`), unique per spec per root; facts in different roots may share an id. |
| Fact reference | How a premise or relation names a fact: `#<fact id>` in the same file, `<spec id>#<fact id>` in the same root. |
| Root-qualified reference | A fact reference into another root, naming the root by its marker's `name`: `bcm2711@hardware-specs-docs#addressing-model`. Also a fact's full reference, used by the viewer and the basis hash. |
| Upstream-stale | A verdict made stale only by a change to a fact in another root that it references; a warning on the dependent repository's `main`, an error on its next pull request. |
| Support entry | One piece of evidence for a fact record: its provenance class and the fields that class requires (a document and locators, anchors into a pinned repository, a board and method, premises and a derivation). |
| Locator | The structured place in a document a citation points at: section, page, table, figure, clause or heading. |
| Named assumption | An assumption stated once in a spec's `assumptions` list and named by every fact that rests on it, so it is visible and invalidates those facts when it changes. |
| Gap fact | A fact record with no support and a TODO: something the spec records as unknown. |
| Basis hash | A fingerprint of everything one verdict depends on: the fact record, the identity fields of the resources it cites, its named assumptions, and the basis hashes of the facts it references. A verdict whose basis hash no longer matches is stale. |
| Canonical form | One fixed serialization of parsed data (sorted keys, no whitespace), so files holding the same data hash the same whatever their layout. |
| Rendered view | Markdown generated from a format 2 spec for people to read, built and published by CI; never committed, edited or parsed for meaning. It cannot stop prose from imitating a cited fact. |
| Viewer / badge | The published HTML view of format 2 specs / a label in it drawn from a fact's structured fields (class, verdict, TODO, origin), placed outside the author's text, which author text cannot produce. |
| Conversion-fidelity check | In the format 2 migration, a fresh agent's comparison of each Markdown bullet with its converted record (same claim text, same citations, nothing added), which decides whether the old verdict may carry forward. |
