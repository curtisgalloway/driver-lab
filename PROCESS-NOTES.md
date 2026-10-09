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

### 2026-09-26T10:34-07:00 — record times written from expectation, three times in one unit
Chapter: [CS-1](notebook/CS-1.md)
What happened: the implementer wrote "10:35"/"10:40" into the notebook, the index and the
evidence while the clock read 10:17, then "10:45" while it read 10:33, and had earlier put a
notebook entry 25 s after its own commit. Each was caught by a `date` run or a commit
timestamp and corrected before the commit, but only because a check happened to follow. FC-1's
review R3 and SR-8's F7 were the same fault.
Cost: three correction passes and an amended commit; a reviewer finding if one had slipped.
Prevention: run `date` in the same command that writes a timestamped record (or read it back
from the file just written); never type a clock time from the sense of how long a step took.
Fix belongs in: the lab-notebook skill (an instruction that the entry time is read from the
clock in the writing command) and the project's AGENTS.md records rule.
Status: open

### 2026-09-26T15:07-07:00 — a record time from expectation, again, and a runner that read "no answer" as "driver bound"
Chapter: [L01-hw](notebook/L01-hw.md)
What happened: the ledger's r2 declaration and a runner fix were stamped "15:10" while the
`date` in the same command printed 15:07; caught by that output and corrected before the
commit. Same fault as CS-1's. Separately, the run driver treated a failed `ssh` as "a driver
is bound before the run" and rebooted the fixture, and its first launch ran one job of eleven
because `ssh` without `-n` consumed the job list on stdin.
Cost: one correction pass; one needless reboot; a relaunch.
Prevention: take the stamp from the `date` output in the same command, never from the sense
of elapsed time; in a job loop over `ssh`, use `ssh -n` and test reachability separately
from the condition (an unreachable host is a stop, not a state).
Fix belongs in: the lab-notebook skill (entry time read from the clock) and a note in the
harness-authoring guidance for remote fixtures (`ssh -n` in loops; reachability first).
Status: open

### 2026-09-26T17:09:11-07:00 — diagnostic verbosity and a capture that outlived its check
Chapter: [L01-hw](notebook/L01-hw.md)
What happened: the declared reference debug value was a mask, but its parameter expects a
bit count and silently selected default logging. Separately, a C3 timeout bypassed capture
cleanup; the orphaned writer caused a size/hash mismatch during artifact retrieval.
Cost: a separately declared diagnostic and a second artifact copy, both retained.
Prevention: read the module parameter conversion before declaring diagnostics; put capture
cleanup in an exception-safe path and verify file stability before accepting a transfer.
Fix belongs in: the private hardware harness and fixture-run guidance.
Status: diagnostic corrected in a declared additional run; the C3 cleanup gap remains a
recorded limitation of the frozen harness, with the orphan stopped explicitly.

### 2026-10-05T16:21-07:00 — a plan request run before its open decisions were asked
Chapter: [LS-design](notebook/LS-design.md)
What happened: asked to plan the license split, the session began reading the design to plan
from it while the note still listed five open decisions; the user stopped it ("ask me the
questions first, then make the plan"). The first quiz then asked for "the clean-room repo"
name, which read as a repo of clean-room specs, and needed two clarifying turns.
Cost: one interrupted turn and two clarification round trips.
Prevention: when a design lists open decisions, ask them as a quiz before planning; in a
question about a repo, say what the repo holds ("the repo holding the clean-room skills").
Fix belongs in: the project-plan skill (open decisions before planning), user instructions
(quiz wording).

### 2026-10-06T07:48-07:00 — tests that asserted only an exit code could not fail
Chapter: [LS1](notebook/LS1.md)
What happened: four new usage-error tests checked only `rc == 2`; the old scripts also exited 2,
for an unrelated reason (the `NAME=PATH` value read as a missing repository). The independent
reviewer found it by running the new tests against the old scripts.
Cost: one review round and a re-run.
Prevention: assert the message as well as the exit code, and run new tests against the
pre-change code before the checkpoint, not only the characterization tests.
Fix belongs in: the project-plan skill's milestone verification (a "new tests fail on the old
code" step).

### 2026-10-06T07:48-07:00 — a pull request's CI never started until the PR was reopened
Chapter: [LS-design](notebook/LS-design.md)
What happened: PR #43 showed no checks for several minutes; `gh run list --branch` returned
nothing while the API's run list later showed a queued run. Closing and reopening started a
second run, and branch protection waited on that one too.
Cost: about ten minutes and a duplicate CI run.
Prevention: query `repos/<owner>/<repo>/actions/runs` before concluding no run exists, and
wait a few minutes before reopening.
Fix belongs in: the orchestrate-milestones skill (CI wait step).

### 2026-10-06T10:02-07:00 — an exit code read after a command substitution
Chapter: [LS2](notebook/LS2.md)
What happened: a shell loop printed `printf '%s %s %s\n' "$(basename "$s")" "$r" "$?"` after
each gate run; the substitution ran first, so every row showed 0 (the substitution's status),
and the gate looked like it passed everything. A direct run of one pair showed FAIL.
Cost: one rerun; it would have been a false "the gate works" claim had the matrix been trusted.
Prevention: capture `rc=$?` on the line after the command, before anything else expands.
Fix belongs in: user instructions (shell command style), beside the pipeline-status rule.

### 2026-10-06T10:40-07:00 — privacy check run against the main checkout, not the worktree
Chapter: [LS4](notebook/LS4.md)
What happened: `python3 <worktree>/utilities/check-no-private-paths.py` from the session's
default directory (the main checkout) reported "278 tracked files"; from the worktree it reports
302. The script checks the tracked files of the repository it runs in, not the one it lives in,
so the first run said nothing about the worktree.
Cost: none (caught by the file count before relying on it).
Prevention: run repository checks from the worktree (`cd` once, or a script with the worktree
as its working directory), and read the file count.
Fix belongs in: project instructions (AGENTS.md, Checks) or the script (resolve the repository
from its own path).

### 2026-10-06T17:17-07:00 — a self-test pattern that matched an informational line
Chapter: [LS5](notebook/LS5.md)
What happened: the spec repositories' self-test first accepted a misfit when its output
contained `license gate:` and the exit code was 1. `anchor_check.py --root` prints
`license gate: root … accepts: …` for every spec, so a misfit failing for any other reason
would have passed the self-test as a gate failure. Seen while reading the first local log.
Cost: none (caught before any commit); one rerun.
Prevention: when a check greps output for proof, match the error line's own prefix, and run
the check once against a passing case to see what the pattern also matches.
Fix belongs in: the project-plan skill (testing gate: "shown able to fail" covers the pattern,
not only the exit code).

### 2026-10-06T17:17-07:00 — an EXIT trap on a local variable
Chapter: [LS5](notebook/LS5.md)
What happened: `scripts/checks.sh` set `trap 'rm -rf "$tmp"' EXIT` inside a function where
`tmp` was `local`; under `set -u` the trap fired after the function returned and failed with
`tmp: unbound variable`, turning a passing run into exit 1.
Cost: one regeneration and rerun of the three repositories' checks.
Prevention: a variable an `EXIT` trap reads must be global.
Fix belongs in: user instructions (shell command style), if it recurs.

### 2026-10-06T18:03-07:00 — a brief whose wording the acceptance grep forbids
Chapter: [LS7](notebook/LS7.md)
What happened: the LS7 brief asked SPEC-FORMAT to call `[source-observed]` "defined by an
extension (cleanroom-skills)" and plan step 4 offered "pointing at `cleanroom-skills`" for
references in open skills, while the acceptance grep (`clean-?room`) matches the repository's
name. Followed the design's wording (LS-R15, no repository named) and removed the references
instead; recorded as a deviation.
Cost: a few minutes deciding; no rework.
Prevention: write an acceptance grep and the wording it is meant to allow together, and check
the allowed wording against the pattern.
Fix belongs in: the project-plan skill (acceptance criteria phrased as greps).

### 2026-10-06T18:21-07:00 — notebook opened after the work, again
Chapter: [LS8](notebook/LS8.md)
What happened: the LS8 chapter was first written after `DESIGN.md`'s move had been drafted and
the check script written, so its opening and decision entries carry the time of writing, not
of the decisions (the 2026-09-24 entry "notebook opened mid-unit" recorded the same pattern).
Cost: the decisions' times are lost; the content was recoverable from the scratch move list.
Prevention: write the opening entry before the first edit, as the first tool call of a unit.
Fix belongs in: the project-plan skill (session start: open the chapter before reading the
code to be changed).

### 2026-10-07T09:26-07:00 — a filtered file list that filtered nothing
Chapter: [LS9](notebook/LS9.md)
What happened: the rename's file list came from `grep -rIl … .` and was filtered with `^./`
patterns, but that grep prints paths without the `./`, so the filter excluded nothing and the
`sed` rewrote history files (`evidence/`, `notebook/`, `docs/`). `git status` showed it before
staging; the files were restored with `git checkout --`.
Cost: a few minutes; no history was committed.
Prevention: print the file list and read it before running a bulk replace, and anchor exclusion
patterns to what the command really prints.
Fix belongs in: AGENTS.md of driver-lab (a rename rule), if it recurs.

### 2026-10-07T12:20-07:00 — glob tests that could not fail
Chapter: [LS11](notebook/LS11.md)
What happened: two tests for glob handling used `wide/b*/x`, but a glob matches only paths that
exist and no `x` file did, so the glob matched nothing on the old code and the new. They looked
like coverage until the fail-first run on a reverted copy was read test by test.
Cost: one rewrite; no wrong claim was committed.
Prevention: for a glob test, assert the glob matches the entry first (or glob the directories
themselves), then assert the verdict.
Fix belongs in: the project-plan skill (fail-first: read why each test failed, not only that it did).

### 2026-10-08T12:09-07:00 — design chapter written after the session, a third time
Chapter: [SF2-design](notebook/SF2-design.md)
What happened: the spec format 2 design session ran as a subagent task without opening a
notebook chapter; the chapter was written when the plan was, so its entries carry the time of
writing and the decisions' times come from commits. Same pattern as the 2026-09-24 and
2026-10-06 entries.
Cost: no lost content (the decisions are in the design and its commits), but the chapter is a
reconstruction.
Prevention: a design brief from the orchestrator should name the notebook chapter to open, as
milestone briefs do.
Fix belongs in: the orchestrator's brief template (`orchestrate-milestones`) or the project-plan
skill's design phase.

### 2026-10-08T12:41-07:00 — `uv run --with-requirements` installed a file with wrong hashes
Chapter: [SF2-1](notebook/SF2-1.md)
What happened: the plan's check lines could have used `uv run --with-requirements` on the
hash-pinned requirements file, as the other checks use `uv run --with`. A tamper test (every
hash of one package replaced) showed uv installing and running anyway, while
`pip install --require-hashes` refused. The lines were switched to a pip venv before use.
Cost: one extra check; nothing shipped unverified.
Prevention: when a check line claims hash pinning, tamper one package's hashes and confirm the
installer refuses before relying on it.
Fix belongs in: the `dep-quality` skill (pinning step) or driver-lab AGENTS.md, if it recurs.

### 2026-10-08T17:38-07:00 — a mutation pass without a clean baseline counted every mutation as caught
Chapter: [SF2-2](notebook/SF2-2.md)
What happened: the pre-review mutation pass copied only `skills/` into a scratch tree. One test
reads the design document, so the copied suite failed before any mutation, and every mutation was
counted as caught (80 of 80). Codex found it in round 1. The rerun copies the whole tree, asserts
a clean baseline first, and separates an assertion failure from a crash: 91 assertion, 2 crash
only, 2 survived of 95.
Cost: a withdrawn claim and one extra round of tests; survivors reached review unnoticed.
Prevention: a mutation runner runs the unmodified copy first and refuses to continue unless it
passes, and judges by `failures=` rather than a nonzero exit.
Fix belongs in: the project-plan skill's "mutation pass" step (or a shared runner script).

### 2026-10-08T17:38-07:00 — a fixture named `*~` was ignored by git and left out of a commit
Chapter: [SF2-2](notebook/SF2-2.md)
What happened: the round-2 backup-name fixture `b.spec.yaml~` matched the repository's `*~` ignore
rule, so `git add <dir>` skipped it without a word. Tests passed locally; a fresh checkout would
have passed that case for the wrong reason. Caught by `git status` and fixed with `git add -f`; a
clean `git archive` export now runs the suite.
Cost: one follow-up commit.
Prevention: after adding fixtures, run the suite from `git archive HEAD`, not the working tree.
Fix belongs in: driver-lab AGENTS.md (checks before a checkpoint), if it recurs.

### 2026-10-09T14:27:42-07:00 — export environment setup and oversized reads

Chapter: [SF2-4](notebook/SF2-4.md). Status: open. The brief asked for a dot-directory
venv, but the export instruction forbids creating one; system Python also lacked ensurepip.
A seeded temporary venv plus pip hash verification worked. Initial document batches exceeded
the output budget and required targeted reads. Cost: extra setup and read calls. Prevention:
briefs should prefer temporary venvs in exports; tools should budget combined output before
batching. Fix belongs in the implementer brief and tool usage.

### 2026-10-09T14:34:50-07:00 — test fixture typing and new diagnostics

Chapter: [SF2-4](notebook/SF2-4.md). Status: open. A tag-shaped unquoted claim became a YAML
list, reused Python objects generated YAML aliases, and generic YAML loading changed a zero
hash to an integer. New safety findings also invalidated two first-error assumptions. Cost:
three focused test reruns. Prevention: quote fixture strings, avoid shared objects in YAML
dumps, use the strict loader for format 2 inputs, and match the relevant diagnostic rather
than its position. Fix belongs in test authoring guidance.

### 2026-10-09T14:42:46-07:00 — checkout-dependent checks in an export

Chapter: [SF2-4](notebook/SF2-4.md). Status: open. Utilities reported two failures and
campaign-review reported ten errors: directory markers made filesystem checks classify temporary
paths as git trees, while git could not read a valid repository. Cost: two checks cannot be
verified here. Prevention: identify checkout-dependent suites in export briefs and rerun them
in the orchestrator's actual worktree. Fix belongs in the implementer brief; no unrelated
utility or campaign code was changed.

### 2026-10-09T15:16:34-07:00 — round-1 export environment and diagnostic expectations

Chapter: [SF2-4](notebook/SF2-4.md). Status: open. The default Python again lacked
ensurepip; a seeded Python 3.12 temporary environment installed the hash-pinned dependencies.
Initial batched reads were truncated and a patch failed because its last context did not
exist. Cost: targeted reads and one corrected patch. New safety rules changed existing
reference-definition and HTML/placeholder expectations, requiring fixture updates. Prevention:
use the chapter’s documented interpreter setup, budget combined output, and remove stale patch
context. Fix belongs in implementer tooling and test authoring guidance.

### 2026-10-09T15:22:19-07:00 — mutation scoring and fixture assumptions

Chapter: [SF2-4](notebook/SF2-4.md). Status: open. A missing rendered substring raised
ValueError in a mutation test; assertions must establish its presence before indexing. A
fixture assumed every support class allowed notes; switching to its document citation made
the containment test valid. Self-review caught a status-variable collision in the fix. Cost:
focused reruns and a repeated mutation pass. Prevention: inspect schema branches before
editing fixtures, test optional modes, and distinguish assertion kills from crashes. Fix
belongs in implementation and test authoring guidance.
