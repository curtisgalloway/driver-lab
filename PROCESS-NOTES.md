<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Process notes

Possible improvements to how the driver-porting work is run: the skills, briefs, review
gates, and bookkeeping. Progress on the project's goals goes in the
[plan](IMPLEMENTATION-PLAN.md) and the `evidence/` files, not here. Each note says what
happened, what it cost, and a proposed change. A note is a candidate, not a decision; when one
is acted on, record where and strike it through or remove it.

Since 2026-09-24T12:22-07:00 this file is also the project's process log under the
`lab-notebook` skill (the user chose this file before that skill was in use). Entries from
then on follow that skill's format under "Log entries" below, each with a status; the notes
under "Open" predate it and keep their form. Chapters of the lab notebook are in
[notebook/](notebook/index.md).

## Terms

- **Run store** — the private directory outside this repository that holds each run's raw
  inputs, drafts, transcript paths, and review reports, one directory per run ID.
- **Reading** — one verifier subagent's pass over a spec, producing a verdict per claim.
- **Adjudication** — settling a claim on which two readings disagree.
- **Operator** — the coordinating agent session that briefs and launches the other agents.
- **`consult`** — a skill that runs a review or discussion with the other coding agent (Codex
  from Claude Code), in a restricted read-only session.
- **Session auditor** — `cleanroom-implementer`'s `session_audit.py`, which scans an agent's
  transcript for forbidden reads and for source text that arrived by any route.
- **Antigravity** — Google's coding agent; several clean-room tools were written first for
  its file layout.

See the [glossary](GLOSSARY.md).

## Open

### 2026-09-24 (L02e)

- **The compiler was never pinned.** L02a pinned the kernel, the manual and QEMU, but not the
  toolchain. The test host's GCC 15 cannot build Linux v6.12 (ACPI header strings trip a
  warning GCC 15 makes an error), and finding that out cost a failed 32-core build plus a
  package install on the test host. Proposed: pin the compiler with the kernel, and make a
  kernel build a smoke test in the pinning unit, not the first unit that needs one.
- **A Claude subagent implementer has no enforcement layer that doesn't also bind the
  operator.** `cleanroom-implementer`'s hook is installed per workspace or per harness, so it
  would also apply to the operator and to every verifier that must read the source. Its
  transcript auditor reads the harness's transcript files, which agents here may not touch
  from the shell, so the audit has to be handed to the user. Proposed: a role-scoped way to
  launch the implementer (its own workspace with the hook, or a separate harness process) and
  an audit path the operator is allowed to run.
- **Operator files and implementer inputs share one run directory.** Review briefs and the
  audit policy name the paths the implementer must not open, so they had to be moved out of
  the run by hand while it worked; a file listing of the run root would otherwise have handed
  it the map. Proposed: a run layout with a separate operator directory the implementer brief
  never names, or an implementer-visible subdirectory that holds only its inputs.
- **The operator wrote a repair item from a verification-record label, not the spec.** Item H
  told the implementer that spec §5.1 requires a 32-bit mask unless the bus is PCI-X, taken from a
  verifier's claim key.
  The spec says a 64-bit mask is legal and gives a fallback; the implementer checked and
  declined the item, correctly. The operator had not opened the spec's text, although the
  landed spec is clean-side and fair for it to read. Proposed: a repair item that
  cites the spec quotes the spec sentence it relies on, checked by the operator before sending.
- **Three reviewers found one defect; one referee lowered its rating.** The transmit-stats double writer was found
  by the reference review, the requirements review, and the swarm; all three rated it
  medium, and the swarm referee lowered its arm's rating to low. Severity rubrics differ between the
  briefs (the swarm's is generic, the driver briefs' are hardware-specific). Proposed: give
  the swarm's arms and referee the same driver severity rubric as the other reviews.

### 2026-09-24 (L02c)

- **The run store's location is written down nowhere a new session can find it.** Evidence
  files name run IDs but not the root, and Spotlight does not index the directory, so finding it
  took several searches. Proposed: keep the root in a private discovery record (for example
  an environment variable or a local config file the skills read), and refer to it in public
  documents only by a placeholder such as `<run-store>`. A private location does not become
  fit to publish by dropping the username from its path.
- **Two readings of the same spec used different claim keys.** Only 277 of about 555 keys matched
  exactly, so merging the two readings needed a fuzzy, section-by-section comparison. Proposed:
  give both verifiers a mechanically extracted claim list with fixed keys, or ship a key
  extractor with `spec-verifier`.
- **The two-reading merge was an ad hoc scratch script.** It is the same step every time.
  Proposed: a `merge_records.py` in `spec-verifier` that aligns keys, marks disagreements
  ADJUDICATE, recounts the summary, and runs the leak scan.
- **The readers applied different verdicts to `[standard]` claims whose standard was not
  fetched.** One wrote PASS with a "not fetched" note, the other UNVERIFIABLE. That showed up as
  a disagreement although both readers saw the same thing. Proposed: `spec-verifier` should say
  a claim whose only authority was not read is UNVERIFIABLE, even when it is plausible.
- **Three of four adjudications were citation defects.** In one, both readers described the
  same wrong citation and differed only on whether it is a FAIL; in the other two, one reader
  passed the claim without mentioning the defect, so the records show differing verdicts, not
  necessarily differing policies. All three still went to the user. Proposed: when both readings
  describe the same discrepancy, treat it as a FAIL without adjudication; for a citation defect
  only one reader saw, a narrow third reader (next note) can confirm it before asking the user.
- **A narrowly briefed third reader settled the one factual disagreement cheaply.** It rendered
  one manual page and answered one question (about 78k tokens, under a minute). Proposed: make
  that the default first step for a factual disagreement, with the user deciding only if the
  third reader cannot settle it.
- **Units stack, but the one-branch-per-unit convention does not say how.** L02c needed L02b's
  plan updates before L02b's PR merged, so its branch was cut from L02b's. Proposed: say in the
  plan's conventions that a unit may branch from its predecessor's unmerged branch, and that its
  PR is rebased onto main after the predecessor merges.
- **Line-range citations into `include/` and `Documentation/` keep going wrong.** Across both
  rounds, three of the seven accuracy FAILs were `file:line` citations that pointed at the wrong
  lines or stopped one line short (a fourth mislabeled page numbers), and the fix for one of
  them introduced another. Each costs a
  reader round trip. Proposed: a mechanical checker that, for every HALF 2 citation with a quoted
  phrase, confirms the phrase lies inside the cited range at the pinned tree. This is the
  clean-room counterpart of `anchor_check.py`.
- **Copying a spec's sidecars into a new run leaves their headers pointing at the old run.**
  The provenance map copied into the L02c run still named the L02b run directory and draft
  path, which could send a later reader to another run. Proposed: a small "start run from
  previous run" helper that copies inputs and sidecars, rewrites run-relative headers, and
  rechecks hashes.
- **`leak_scan.py` silently skips files without a source extension.** The e1000 map lists a
  Makefile, which the scanner skips without saying so; the transfer reviewer scanned it by hand.
  Proposed: the scanner reports each skipped file, or scans every file the map names.
- **The recall assessor found a blind-list row that asks for more than the manual says**
  (INIT-005, transmit enable order). The list is frozen and has no way to record that. Proposed:
  a sidecar of post-freeze row notes, kept out of the recall denominator's definition, so a
  known-weak row is visible without rewriting the frozen list.

## Log entries

### 2026-09-24T12:22-07:00 — instruction gap: notebook opened mid-unit
Chapter: [L02e](notebook/L02e.md)
What happened: the `project-plan` skill gained a lab-notebook requirement during L02e; the
reload came after the implementation, reviews, and repair had run, so the chapter's first
entries were reconstructed from the run's ledger instead of written as they happened.
Cost: reconstructed entries carry the opening timestamp, not their real times; failed
attempts are recorded only as far as the ledger kept them.
Prevention: none needed going forward; the next unit opens its chapter at the start.
Fix belongs in: project-plan (already fixed upstream by adding the requirement)
Status: open

### 2026-09-24T12:22-07:00 — failed command: status poll matched the wrong field
Chapter: [L02e](notebook/L02e.md) (during L02c's `consult` review)
What happened: a shell wait loop grepped the `consult` status JSON for a "ready" status;
the first job's status matched while the consultation was still running, so the loop exited
early and the follow-up read failed with a `TypeError`.
Cost: one extra turn and a re-armed wait.
Prevention: parse the JSON and test the top-level `status` field, as the re-armed loop did.
Fix belongs in: consult (an example wait loop in its SKILL.md)
Status: open

### 2026-09-24T12:27-07:00 — surprise: build logs could not show their own flags
Chapter: [L02e](notebook/L02e.md)
What happened: the build wrapper printed its warning summary only to the screen and wrote
no record of its arguments, so the default and W=1 logs were byte-identical and a reviewer
could not tell from them that W=1 had been used.
Cost: one verbose rebuild on the test host to prove the W=1 claim.
Prevention: every build log records the command's arguments, the input hash, and the summary.
Fix belongs in: project instructions (the run layout's build wrapper); applied to this run's
wrapper
Status: fixed in the L02e run's build.sh

### 2026-09-24T12:52-07:00 — failed command: long command handed to the user wrapped on paste
Chapter: [L02e](notebook/L02e.md)
What happened: the operator gave the user a single 400-character `!` command for the
transcript audit; it wrapped into four lines when pasted, and the shell ran each line as a
separate command ("the following arguments are required", "permission denied").
Cost: one user round trip.
Prevention: a command handed to the user is one short line; put long invocations in a
script in the run directory and hand over `bash <script>`.
Fix belongs in: user instructions (the note on commands the user must run) or
cleanroom-implementer (ship an audit wrapper)
Status: open

### 2026-09-24T13:00-07:00 — surprise: the session auditor flags a clean Claude Code session
Chapter: [L02e](notebook/L02e.md)
What happened: `session_audit.py` reported 8 findings on the implementer's transcript, all
from reading its own driver, the allowed kernel headers, and a brief that asked for GPL
headers. Its workspace exemption and marker rules assume an Antigravity layout; on a Claude
Code transcript it cannot tell the implementer's workspace or allowed inputs from a leak.
Cost: a user decision and a triage subagent (reading records one at a time with the file-read
tool, which could not open the largest record at all).
Prevention: let the policy name allowed input roots and the workspace, and exempt results of
tool calls whose targets lie under them; report each finding with its tool call's target.
Fix belongs in: cleanroom-implementer (session_audit.py and the policy format)
Status: open

### 2026-09-24T13:09-07:00 — correction: two earlier log entries
Chapter: [L02e](notebook/L02e.md)
What happened: the entry "status poll matched the wrong field" describes an event during
L02c's review, earlier in the session; its 12:22 timestamp is when it was written, not when
it happened. The entry "the session auditor flags a clean Claude Code session" says the
auditor exempts workspace reads; it exempts results by tool name and has no notion of a
workspace. Found by the L02e public-changes review.
Cost: none beyond this correction.
Prevention: write log entries when the event happens, and name the mechanism from the code.
Fix belongs in: lab-notebook practice (no instruction change)
Status: open

### 2026-09-24T16:23-07:00 — instruction gap: resuming session had to search for the run store
Chapter: [L02d1](notebook/L02d1.md)
What happened: the plan's "Next session" and the evidence files name runs by ID and say
"the run store" but never where it is, correctly, since the path is a private home path. The
resuming session found it with a filesystem search after three misses (Spotlight does not
index it; the harness had no Grep tool, so one search call failed outright).
Cost: about six tool calls before any L02d work.
Prevention: record the run store's location somewhere private that a session loads: the
agent's project memory, or an environment variable the plan can name without the path.
Fix belongs in: user instructions or agent memory for this project (not the public plan)
Status: open

### 2026-09-24T16:23-07:00 — surprise: a QEMU trace-log prefix assumed, not checked
Chapter: [L02d1](notebook/L02d1.md)
What happened: the trace filter was written for QEMU's `pid@sec.usec:` log prefix; with
`-msg timestamp=on` this QEMU writes an ISO time instead, so the first run counted zero e1000
accesses in a 124,006-line trace.
Cost: one failed run (about 15 s) and a fix.
Prevention: look at one line of real output before writing a parser for it.
Fix belongs in: practice (no instruction change)
Status: open

### 2026-09-24T16:51-07:00 — failed fix: a guest read timeout lost commands
Chapter: [L02d1](notebook/L02d1.md)
What happened: the fix for review finding F4 (a lost READY line) made the guest poll its
command channel with busybox `read -t 1`. That builtin drops a partly read line on timeout,
so four of eleven follow-up runs lost a command. The rerun of the acceptance runs caught it
before the checkpoint.
Cost: one round of eleven host runs (about 4 minutes) and a second fix.
Prevention: rerunning every acceptance and failure-path run after review fixes, which
project-plan already requires; it worked here. For guest scripts, prefer blocking reads.
Fix belongs in: practice (no instruction change)
Status: open

### 2026-09-24T17:51-07:00 — surprise: a guest tool's options assumed, not checked
Chapter: [L02d2](notebook/L02d2.md)
What happened: three scenarios used `nc -u` for UDP floods; this busybox build has no `-u`.
The foreground use printed a usage error that the scenario did not check; the two
background uses failed silently, and those scenarios passed without the traffic they claim.
Cost: one suite run (about 2 minutes), a redesign of the floods, and a new class of check.
Prevention: run each guest command once by hand, in a guest, before building a scenario on
it (the L02d1 entry on the trace prefix is the same lesson); and make a scenario prove its
own precondition (a flood running, traffic in the trace) instead of trusting a command.
Fix belongs in: practice; possibly the `review-swarm` or scenario-coverage reviewer brief
("does each scenario prove the condition it claims to create?")
Status: open

### 2026-09-24T20:37-07:00 — a decision entry claimed more than the check did
Chapter: [L02d2](notebook/L02d2.md)
What happened: the notebook's ITR decision said the read-back tested the driver's write;
it compared the model with its own write log. The scenario-coverage reviewer caught it,
along with two probes (L4, M2) that never created their condition. The code-review swarm,
which reads code rather than run artifacts, found none of the three.
Cost: three rewrites of scenario claims after review.
Prevention: for any check, write down one concrete driver defect that would make it fail
before calling it a driver check; keep an artifact-reading coverage reviewer in every
harness unit.
Fix belongs in: `review-swarm` guidance (or the plan's review conventions) — pair code
review with an artifact-based coverage review for test harnesses
Status: open

### 2026-09-24T20:37-07:00 — SSH agent refusal stopped the final runs
Chapter: [L02d2](notebook/L02d2.md)
What happened: after about three hours of working SSH, the 1Password desktop agent refused
to sign for the test host (likely locked); rsync then fell back to password prompts, which
were denied. The host's key is in the vault agents cannot read, so there is no agent-side
recovery.
Cost: the unit stopped before its final verification runs.
Prevention: rsync and ssh with `-o BatchMode=yes` everywhere, so a refusal fails once
instead of trying passwords; for long host sessions, the safe-tier style dedicated key on
the test host.
Fix belongs in: user instructions or the test-host setup (a dedicated agent key)
Status: open

### 2026-09-25T14:28-07:00 — notebook timestamps estimated, not read
Chapter: [L02d3](notebook/L02d3.md)
What happened: two opening entries were stamped 14:40 while the clock said 14:26; the time
was estimated while drafting instead of read with `date` first.
Cost: a correction entry; no work lost.
Prevention: run `date -Iminutes` in the same command that appends the entry, and use its
output as the heading.
Fix belongs in: `lab-notebook` (show the append-with-date idiom)
Status: open

### 2026-09-25T14:43-07:00 — a reason written from memory instead of the capture
Chapter: [L02d3](notebook/L02d3.md)
What happened: answering a review finding, I justified Q25 by "ARP frames are 60 bytes" without
opening a capture; the reviewer parsed the reference capture and found peer ARP frames reach
the DUT at 42 bytes. The same session had also written "pings passed" for a run whose scenario
stopped before any ping.
Cost: one extra review turn and two corrections.
Prevention: in evidence tables, state only what the run's verdicts or captures show; when a
reason rests on a packet or register fact, look it up in the run before writing it.
Fix belongs in: project instructions (AGENTS.md, evidence-writing rule)
Status: open

### 2026-09-25T15:14-07:00 — instruction gap: resuming session had to search for the run store
Status: fixed in AGENTS.md ("Run store location"): each user sets `run_store` in
`~/.config/driver-lab/config.toml` (or `DRIVER_LAB_RUNS`), read by `utilities/run-store.py`;
the path stays out of the repository, and an unconfigured store means asking the user, not
searching. Recurred in L02f1, where the store was on another machine.

### 2026-09-25T15:48-07:00 — instruction gap: run store missing from the test host (recurrence)
Chapter: [L02f1](notebook/L02f1.md)
What happened: attributing the first candidate failure needed spec revision 4 and the manual,
which are only in the run store; it was not on the test host and nothing a session reads says
where it is. Searches here and on a second machine found nothing; the user named a third,
where it was.
Cost: about 15 tool calls and three user round trips.
Prevention: the per-user run-store setting (branch `docs/run-store-config`), plus copying
the inputs a unit needs onto the test host when the unit is planned.
Fix belongs in: AGENTS.md (done on that branch); the plan's next-session notes
Status: open until that branch merges

### 2026-09-25T15:48-07:00 — surprise: SSH from the test host offers every forwarded key
Chapter: [L02f1](notebook/L02f1.md)
What happened: the test host's ssh config pins only the bench host, so connecting to other
homelab machines offered all forwarded agent keys and was cut off at the server's attempt
limit; the workstation was also unreachable directly and had to be reached through a jump
host, with its host key accepted on first use.
Cost: four tool calls.
Prevention: pin `IdentitiesOnly` with the one public key per target (`-i <key>.pub`), as the
`homelab-ssh` skill describes; the skill's notes assume the workstation's ssh config.
Fix belongs in: the `homelab-ssh` skill (note that other hosts lack the workstation's pinning)
Status: open

### 2026-09-25T16:07-07:00 — instruction gap: run store missing from the test host (recurrence)
Status: fixed in AGENTS.md ("Run store location") by the `docs/run-store-config` branch; the
other half of its prevention (inputs copied to the test host when a unit is planned) is in the
plan's L02f2 entry.

### 2026-09-25T18:12-07:00 — instruction gap: a spec edit's scan inputs stay on another machine
Chapter: [L02s](notebook/L02s.md)
What happened: L02s edited the spec on the test host, but the L02c whitelist and provenance
map the leak scan uses were never copied from the original run store, and reaching that
machine from an agent session was not possible. The scan ran without a whitelist, and
revisions 4 and 5 were compared instead.
Cost: a weaker mechanical check (a comparison, not a fresh classification); about three tool
calls.
Prevention: when a spec lands, copy its whitelist and provenance map into the run beside it,
so any later revision has its scan inputs in the same store.
Fix belongs in: `cleanroom-spec` (landing step) and the plan's L02f3 entry (copy them before
revising again)
Status: open

### 2026-09-25T18:12-07:00 — correction: a bit table's reset column read as update timing
Chapter: [L02s](notebook/L02s.md)
What happened: the operator wrote that PSCON bit 11 needed no order relative to the
auto-negotiation restart because its software-reset column says "Retain"; §11.1.3 says the
opposite. The fresh verifier caught it.
Cost: one extra verification round (about 2.6 minutes of agent time).
Prevention: for any PHY or register write, look for the manual's section on when writes take
effect before stating an order.
Fix belongs in: `cleanroom-spec` authoring guidance (a check for "when does the write apply")
Status: open

### 2026-09-25T18:50-07:00 — a revision's change list named some of its own hunks
Chapter: [L02f3](notebook/L02f3.md)
What happened: revision 5's header said it changed G4 and §9.2; its diff had five hunks (the
G4 ordering note and the PHY-extras bullet too). The second L02s verifier noticed; revision 6
names every changed passage and records the omission.
Cost: one carried note and a header correction a revision later.
Prevention: write the change list from the diff's hunks, after editing, not from the plan
before it.
Fix belongs in: `cleanroom-spec` (revision step: "list the hunks")
Status: open

### 2026-09-25T18:50-07:00 — an `[emulated]` entry needs a phrasing rule
Chapter: [L02f3](notebook/L02f3.md)
What happened: the evidence files that establish the model departures name QEMU functions,
because the operator side may read the model's source. Writing the spec's §12.5 from them
risked carrying those names across the clean-room wall. The entries were rewritten as what
the runs recorded (register values, trace gaps, captured frames) with their run IDs.
Cost: one rewrite pass; a verifier check against an observations extract.
Prevention: an `[emulated]` fact states an observation from outside the model and cites the
run, the way `[hardware]` cites the board; the mechanism stays in the evidence file.
Fix belongs in: `SPEC-FORMAT.md` and the design's evidence model (follow-on SF-1)
Status: fixed in SF-1 (2026-09-25): the class, its citation form and the phrasing rule are in
`SPEC-FORMAT.md` and `DESIGN.md`, and `spec_check.py` enforces that a citation parenthetical
is present, the TODO, and the never-alone rule ([evidence](evidence/SF-1.md))
