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
| CommonMark | A defined set of Markdown rules for interpreting headings, lists, links and code. |
| GFM | GitHub Flavored Markdown: GitHub's Markdown rules, which add tables, footnotes and automatic links to CommonMark. |
| Code span / code fence | Literal inline text between backticks / a literal block between delimiter lines. The view sizes delimiters so content cannot close them. |
| Autolink | Text a Markdown renderer turns into a link automatically, such as a URL or email address. |
| Nesting depth | How many Markdown containers or inline constructs surround a piece of text. |
| Driver | Software through which an operating system controls a device. |
| OS / kernel | Operating system / its core that manages hardware and supplies driver interfaces. |
| API | An interface a program uses to call another software component. |
| SDK | Software development kit: headers, libraries, and tools for building against a platform. |
| Corpus | The pinned collection of source code and documents used as reference evidence. |
| Pin | An exact revision, edition, or digest identifying an input. A cited `resources.repos` entry uses full `commit` and `license`; a branch-only `ref` entry is a map. |
| Symbolic link / hard link | A path pointing to another path / another name for the same underlying file. Replacing a symbolic link replaces the pointer; replacing one hard link separates it from the other names. |
| Mode bits | Unix file flags recording read, write and execute permissions and special modes. |
| Setuid / setgid | Unix mode flags that can make an executable run with its owner's user identity / its group's identity. Spec files with either flag are refused for rewriting. |
| Data path | The sequence of mapping keys and list positions naming a parsed value, such as `$['facts'][0]['title']`. Rewrite refusals name the first differing path. |
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
| Accepts list | The SPDX license identifiers a spec root allows its anchored sources to carry (`accepts:` in the root marker). |
| License gate | The check that fails a spec citing a source whose license the root's accepts list does not include. `spec.py check` gates every `src`, `DT` and `rtl` anchor and notice and follows fact references transitively (D13). |
| Source fact (`src`) | A fact about what code defines or does, supported by anchors into a pinned, licensed repo. Uses `class: src` structured support. It does not alone prove a hardware requirement and needs no hardware TODO for a claim about that code. |
| Placement rule | A spec lives in the most restrictive repository among the sources it anchors to, and never cites a source more restrictive than that repository. |
| Spec repositories | `hardware-specs-gpl`, `hardware-specs-docs` and `hardware-specs-permissive`: the three public homes for specs, by license. |
| Open side | driver-lab outside its frozen archive since the license split: the method for specs that cite their sources and are published where their licenses fit. |
| Frozen archive | The parts of driver-lab kept as history after the split (evals, evidence, notebook and the documents describing them); still checked by CI, no new rounds. |
| SPDX | The standard short identifiers for licenses (`GPL-2.0-only`, `MIT`, `CC-BY-4.0`) and expressions combining them with `OR`, `AND` and `WITH`. |
| Target root / refusal | The spec root whose accepts list governs which sources `hardware-investigator` may cite for one question / its return when a needed source's license is not on that list: the source, license, list and reason, with no fact from the source. |
| Anchored facts | Evidence-supported statements with exact document or source citations, stored as structured support in YAML records. |
| YAML / JSON Schema / validator | A text format for structured data / a standard language (current version: draft 2020-12) stating what shape such data must have / the library that checks data against a schema. Spec format 2 stores specs as YAML checked against a JSON Schema; see the [contract](skills/spec-format/SKILL.md). |
| Spec format 2 | YAML fact records checked against JSON Schemas, with generated Markdown views; the [contract](skills/spec-format/SKILL.md). Board/SoC/chip/IP/overlay/facts/peripheral/review kinds are supported. Format 1 readers and migration tools are retired; historical campaigns keep their original formats. |
| Untrusted root | In spec format 2, a root whose own `spec.py check` found any error (a context root's included, though its findings print as warnings). No reference may rest on it: every reference into it, direct or through other facts, is an error on the citing file (user decision, 2026-10-08). |
| Strict loader (`load_strict`) | The one function every spec format 2 tool reads YAML with (`skills/spec-format/scripts/specload.py`). It admits one spelling per value: only `true`, `false`, `null` and integers are not strings, and anchors, tags, duplicate keys and invisible characters are errors with a line and column. |
| Schema fragment | The partial JSON Schema an extension supplies for its own support class (`source-observed`, design D15), named in a root marker's `extensions`. It may only add fields; `spec.py` refuses one that would loosen the core schema. |
| Fact record / fact id | One claim in a format 2 spec, stored as a mapping with its claim text and structured support / the stable identifier it keeps through every edit (`addressing-model`), unique per spec per root; facts in different roots may share an id. |
| Fact reference / full reference | A link to a fact: `#<fact id>` in the same file, `<spec id>#<fact id>` in the same root, or `<spec id>@<root name>#<fact id>` in a named root. The last is its full reference, required across roots and used in answers. |
| Root-qualified reference | A fact reference into another root, naming the root by its marker's `name`: `bcm2711@hardware-specs-docs#addressing-model`. Also a fact's full reference, used by the viewer and the basis hash. |
| Upstream-stale | A verdict made stale only by a change to a fact in another root that it references; a warning on the dependent repository's `main`, an error on its next pull request. |
| Upstream map | In spec format 2, a verdict's `upstream` field: the facts in other roots its fact rests on, each with its basis hash when the verdict was reached. It is how the checker tells an upstream-stale verdict from a stale one (SF2-3). |
| Support entry | One piece of evidence for a fact record: its provenance class and the fields that class requires (a document and locators, anchors into a pinned repository, a board and method, premises and a derivation). |
| Locator | The structured place in a document a citation points at: section, page, table, figure, clause or heading. |
| Named assumption | An assumption stated once in a spec's `assumptions` list and named by every fact that rests on it, so it is visible and invalidates those facts when it changes. |
| Gap fact | A fact record with no support and a TODO: something the spec records as unknown. |
| Basis hash | A fingerprint of everything one verdict depends on: the fact record, the resource entries it cites and its named assumptions (each whole, except a short named list of bookkeeping fields such as `verified` and `note`), and the basis hashes of the facts it references. A verdict whose basis hash no longer matches is stale. |
| Verification record (format 2) | `resources/<name>.verify.yaml` beside a format 2 spec: one verdict per fact, instance row or variant row, each carrying the basis hash it was reached at (SF2-3). |
| Freshness status | What `spec.py status` reports for a verdict: current (its basis hash matches), stale (its own inputs changed), upstream-stale, unverified (no verdict), or unknown (a basis that cannot be established, such as one resting on a rejected citation; never treated as current). |
| Bookkeeping field | A field of a cited resource entry that the basis hash leaves out because it records upkeep rather than what the source is: a document's or repos entry's `verified`, `fetch`, `note` (and a repos entry's `fetch_via`), a `files` item's `note`, an assumption's `todo`. Every other field counts. |
| Canonical form | One fixed serialization of parsed data (sorted keys, no whitespace), so files holding the same data hash the same whatever their layout. |
| Rendered view | Markdown generated from a format 2 spec for people to read, built and published by CI; never committed, edited or parsed for meaning. SF2-4 fences author text to keep it inert; provenance is generated only from structured fields. |
| Viewer / badge | The HTML view of format 2 specs / a provenance label drawn from structured fields, outside author text. Built by `spec.py render --format html`; publishing workflows build and deploy the views. |
| Conversion-fidelity check | In the format 2 migration, a fresh agent's comparison of each Markdown bullet with its converted record (same claim text, same citations, nothing added), which decides whether the old verdict may carry forward. |
| Format 1 | The retired Markdown spec format with YAML frontmatter, prose provenance clauses, `ref` pins and whole-file verification hashes. Kept only in historical records and the frozen archive; current tools read YAML format 2. |
| Board spec / SoC / chip / IP spec | Cited bring-up facts for a board / system-on-chip / companion chip / reusable silicon intellectual-property block. An IP spec has no board-specific placement. |
| Composition / instance | A board's recursively shared parts plus needed IP specs / one placement of an IP block with address, interrupt, clocks and evidence. |
| Anchored IP / generic IP | An IP spec resolved through a board and instance, with placement / the IP programming model alone, with no instance facts. Distinct from an evidence anchor. |
| Layer / origin | A root's position in merge order (`public`, `ip-vendor`, `soc-vendor`, `product`, `local`) / the root and layer a fact comes from. |
| Context root | A root supplied to resolve dependencies; its findings print as warnings, but its underlying errors still make references into it fail. Its own freshness policy is not enforced in that run. |
| Documents-only root | A format 2 root with `accepts: []`; source/DT/RTL anchors and, under `--require-license`, even map-only repos are refused. |
| Support class / provenance class / read class | The kind of evidence a support entry supplies / any class other than inference; read support states an observation rather than a conclusion. |
| Anchor (format 2) | A structured source citation naming repo, relative path and lines/symbol, a search scope, or a node in pinned UTF-8 device-tree source, depending on class. Not prose syntax. |
| Canonical URL / retrieval URL | The stable document address used for citation / the separate working address from which bytes can be fetched. |
| Resource registry / map-only resource | The spec's lists of named documents, repos, series and tools / an entry used to find evidence, never itself cited as authority. |
| Schema branch / closed record | Rules for a particular kind or class / a mapping refusing undeclared fields, so a misspelled or alternative citation cannot silently pass. |
| JSON / mapping / scalar | A structured data notation / named keys paired with values / a single value such as a string or integer. JSON Schema describes shapes, not hardware correctness. |
| UTF-8 / NFC / BOM | A text encoding / one normalized spelling of Unicode strings / a byte-order marker refused by the strict loader. |
| CommonMark / GFM / containment | A defined Markdown grammar / GitHub-flavored Markdown / requiring an author field to stand alone so it cannot split or swallow later rendered facts. |
| Critical fact / second reader | A bring-up fact whose error could stop boot, marked `critical: true` / an independent verifier recorded with its own agreeing verdict at the current basis, required for critical facts; disagreement needs adjudication. |
| Delta verification | Re-reading the noncurrent facts and current critical facts missing a second reader, selected by `spec.py status --stale`. |
| Contrary evidence / citation precision | A fresh verdict's record of a search for conflicting evidence / whether the locator identifies the exact supporting passage; recorded as `contrary_evidence` and `citation_precision`, omitted only for a format 1 carry, which is not a fresh reading. |
| Stub / Needs decision | A thin skill naming a spec and handing work to board-expert / the expert's report block returning unresolved choices to the orchestrator. |
| Cache / materialize | The user-chosen local copy of reference resources / fetch or reuse those resources at the identities the spec records. |
| MMIO / DMA | Memory-mapped input/output registers / direct memory access by a device without a processor moving each byte. |
| EL / MMU / MPIDR | Arm exception level, a privilege state / memory management unit translating addresses / multiprocessor identifier used to identify cores. |
| DT / DTB / DTBO | Device tree, a hardware configuration description / its compiled binary / a compiled overlay; format 2 `DT` support cites `.dts`/`.dtsi` source at a pinned commit. A binary-only claim is a gap until decompiled text is published at a pin. |
| PSCI / SCMI / PMIC | Arm interfaces for power-state control / system control and clocks / power-management integrated circuit. |
| GPIO / pinmux / earlycon | General-purpose input/output pins / selecting which hardware function drives a pin / a kernel's early serial console configuration. |
| TRM / databook / public proxy | Technical reference manual / an IP or device programming manual / a publicly obtainable manual for a matching block when the exact document is restricted. |
| PPI / INTID | Arm GIC Private Peripheral Interrupt, a per-core interrupt / the controller's interrupt identifier: SPI INTID = number + 32; PPI INTID = number + 16. |
| NDA / BSP / MCP | Nondisclosure agreement limiting who may read or disclose material / board support package, the software supplied for a hardware platform / Model Context Protocol, the interface exposing tools to an agent. |
| Enum | An enumeration: the closed list of values a schema allows for a field, such as a support class. |
| Orchestrator | The coordinating agent that selects verification work, launches independent readers, assembles their records and runs the checks. In spec verification it does not read sources or edit the spec. |
| Harness | The application running an agent and providing its tools; record it with the model and a distinct reader identity so two sessions cannot be confused. |
| Verdict (format 2) | A recorded comparison result: PASS (supported as stated), FAIL (wrong or misclassified, with a correction), UNVERIFIABLE (evidence unavailable), GAP (a fact with no support), or ADJUDICATE (independent readings awaiting the user's decision). Freshness is separate: a current verdict can still be UNVERIFIABLE. |
| Assessment | A review finding's judgment: `bug` (a justified defect), `suspect` (a difference needing a probe), `benign` (a justified harmless difference), or `ref-issue` (following the reference would be wrong). Separate from a verification verdict about whether the finding is supported. |
| Correspondence | A review's mapping of implementation routines or files to their reference counterparts, stored as `data.pair` anchors on both sides. Unmapped entry points need findings or stated scope limits. |
| Coverage | A review's record of which areas were compared, what was read and why, stored in `data.coverage`. A zero-finding area still needs this account; coverage is separate from register inventory. |
| Role | A repository entry's declared use: `source` or `target` for peripheral specs, `impl` (the reviewed driver) or `ref` (the reference) for reviews. Citations on all sides use `class: src`; the role selects the side, not a different evidence class. Peripheral role enforcement applies only to target-section facts. |
| Document class | A support entry of class `databook`, `standard` or `doc`, naming a document and structured locators. Source code alone does not establish where hardware is or what it requires. |
| TODO method | A proposed way to settle a fact's remaining question, stored in `todo.method` or described in `todo.text`; the verifier checks whether it can observe that question under the stated conditions. |
| D16 sub-key | A verdict key of the form `fact-id.sub-id` for a register field or sequence step with its own support. SF2-7a checks these records and their freshness; fields and steps without separate support share their parent's verdict. |
| Register payload | A fact's structured `data.register` (name, byte offset, width in bits, access and optional reset) and optional `data.fields`; each field's `bits` is an inclusive `[low, high]` pair. |
| Sequence payload | A fact's structured `data.sequence`: steps with stable ids and actions, plus ordering constraints naming the step that comes before and the step that comes after. A step or constraint may override the fact's requirement label. |
| Layout payload | A fact's structured `data.layout`: a name, total size in bytes and fields with byte offsets and byte sizes. |
| Inventory (format 2) | `spec.py inventory` compares register names and offsets, and field names and masks, with C constants in listed source files at an immutable commit. It reports omitted names, mismatched values, conflicting records and unsupported expressions; it reads no prose for coverage. |
| Premise / derivation | Evidence or an explicit assumption an inference rests on / the reasoning that connects those premises to its conclusion. |
| Unicode NFC / case folding | A standard way to represent equivalent characters identically / comparing letters without case differences. The verifier identity comparison also collapses whitespace; it is not proof that two named readers are independent. |
| SHA-256 / ISO date | The digest algorithm used for file identities and fact bases / a date written `YYYY-MM-DD`, such as `2026-10-09`. A file digest identifies bytes, while a basis also fingerprints declared dependencies. |
