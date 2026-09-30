<!--
SPDX-FileCopyrightText: 2026 Curtis Galloway
SPDX-License-Identifier: Apache-2.0
-->

# License split for published hardware specs (design note, draft)

Status: draft for review. Nothing described here has been done yet.

## Start here (15 minutes)

- [ ] Open `skills/board-expert/specs/rk3588s.spec.md` and find its one `[source-observed]` fact.
      Decide whether it gets a datasheet or device-tree citation, or moves to the GPL repo.
      That one decision sets the pattern for the other 11 facts.

## The policy

1. **Publish the method, not clean-room output.** The clean-room skills (`cleanroom-spec`,
   `os-investigator`, `cleanroom-implementer`) stay published. No clean-room spec is published.
   Anyone who wants a clean spec generates it themselves and attests to how they made it.
2. **Published specs use the anchored format**, and each one lives in a repo whose license fits the
   sources it anchors to.
3. **Placement rule:** a spec lives in the most restrictive repo among the sources it anchors to.
   Specs may reference repos with less restrictive licenses, never ones with more restrictive licenses.

## The repos

| Repo | License | Anchors allowed | Holds | When |
|---|---|---|---|---|
| `hwspecs-gpl` | GPL-2.0-only | `[src:]` into any GPL tree, plus `[doc:]` | Linux-derived specs: references for Linux work, or for anyone who doesn't care about license. Easiest to verify. | Now |
| `hwspecs-docs` | CC-BY-4.0 or Apache-2.0 (open decision) | `[doc:]` only | Specs built only from public datasheets, TRMs and standards | Now |
| `hwspecs-permissive` | Apache-2.0, plus a NOTICE file for the BSD/MIT sources | `[src:]` into BSD, MIT or Apache trees, plus `[doc:]` | TF-A, rpi-tools, Zephyr, FreeBSD, and `GPL-2.0 OR MIT` device-tree files | Only once there is material for it |

Notes:
- A GPL-2.0-only repo can take anchors to both GPL-2.0-only and GPL-2.0-or-later sources.
- Many Linux `.dts`/`.dtsi` files are dual-licensed `GPL-2.0 OR MIT`. Facts anchored only to
  those files may go in the permissive repo.

## What happens to the 11 existing specs

`skills/board-expert/specs/` publishes 11 clean-room board and IP specs. Seven are already
datasheet- and device-tree-only. Four contain `[source-observed]` facts, meaning facts learned
by reading GPL code behind the wall. That makes them clean-room output, which the policy says
not to publish.

| Spec | `[source-observed]` facts |
|---|---|
| `bcm2711.spec.md` | 5 |
| `pixel10.spec.md` | 4 |
| `tensor-g5.spec.md` | 2 |
| `rk3588s.spec.md` | 1 |
| The other 7 | 0 |

Options, not yet decided:

| Option | Effect | Estimate |
|---|---|---|
| A. Strip the 12 facts | All 11 specs stay and the 4 expert skills keep working. Each fact gets a datasheet or device-tree citation, or moves to `hwspecs-gpl` as an anchored fact. | About 1–2 hours |
| B. Delete the 4 specs | Breaks `pixel10-expert`, `indiedroid-nova-expert` (via rk3588s) and the `rpi4` composition (via bcm2711); those skills need deleting or rewiring. | About 2–3 hours |
| C. Delete all 11 | `board-expert` becomes method-only. The 4 stub skills go, the tests need their own fixture specs, and the READMEs in driver-lab and public-skills both need updating. | About half a day |

Either way, the 7 clean specs are candidates to move into `hwspecs-docs` later.

## Tooling changes (driver-lab)

| # | Change | Estimate |
|---|---|---|
| 1 | `anchored-peripheral-spec/SKILL.md`: replace the "is it yours?" test with "which repo's license fits?" and add the placement rule | 2 h |
| 2 | `anchor_check.py`: several named source pins per spec (`Source pin: linux@abc GPL-2.0-only`, `[src:linux: path:L]`) | 1 day |
| 3 | `anchor_check.py`: a license gate that fails if an anchor's repo license isn't one the root accepts | 3 h |
| 4 | Doc anchors that can be checked: page number and a pinned sha256 for the document, for `hwspecs-docs` | 4 h |
| 5 | `SPEC-FORMAT.md` and `spec_check.py`: root marker gains `license:` and `accepts: [...]` fields, and the checker enforces them | 4 h |
| 6 | Clean-room firewall: `board-expert`, `os-investigator` and `cleanroom-implementer` refuse a root whose license is GPL, except inside the research subagent; plus a test | 2 h |
| 7 | `PROVENANCE.md` template that `cleanroom-spec` fills in for the user's attestation: who ran it, what sources were behind the wall, which agent saw what, pins, verifier reports, spec hash | 4 h |
| 8 | `inventory_check.py` and `spec-verifier`: per-repo pins | 3 h |
| 9 | driver-lab README: a "Why this exists and what it is not for" section, placed early (see community reaction) | 1 h |

## New repos (each)

- LICENSE, `board-specs.yaml` root marker with `license:` and `accepts:`, CI running
  `spec_check.py` and `anchor_check.py`, and a README with the placement rule and a
  "which repo does my spec go in?" table. About 2 h each.

## Other repos

- `bringup-kit`: its spec roots point at `hwspecs-docs` (and later `hwspecs-permissive`), never at
  `hwspecs-gpl`, because it writes Fuchsia drivers. About 30 min.
- `public-skills` README: pointer to the spec repos, plus any stub skills removed under option B or C. About 15 min.

## Community reaction (expected)

- **GPL repo:** likely welcomed by Linux people. Saying plainly that the specs are GPL
  derivatives, anchored to lines at a pinned commit, is the honest framing. The likely pushback
  is about the quality of AI-generated documentation. The answer is that every claim is anchored
  and the checker runs in CI; say that on the README's first screen.
- **Clean-room skills:** expect some people to call them a "GPL-laundering kit." In their favour:
  you don't publish their output, users must attest, verification is strict, and the same
  project offers the GPL route. Change 9 addresses this before anyone raises it.
- **Datasheet publishers:** docs-only specs paraphrase and cite, with rationed quotes, which is
  the usual accepted practice.

## Clean-room skills move to their own repo

Everything clean-room moves out of driver-lab into a separate repo and plugin (working name
`cleanroom-lab`). driver-lab becomes the open side and never mentions clean-room, apart from at
most one README line pointing to the other repo.

| Moves to `cleanroom-lab` | Stays in driver-lab |
|---|---|
| `cleanroom-spec`, `cleanroom-implementer` | `hardware-spec` (renamed from `anchored-peripheral-spec`) |
| `os-investigator`, renamed `cleanroom-investigator`, with `leak_scan.py` | `hardware-investigator` (new) |
| The clean-room section of `spec-verifier` | `board-expert`, `board-spec-scaffold` |
| The ENC28J60 and e1000 reconstruction evals (open decision) | `spec-verifier` (board and hardware specs), `reference-driver-review`, `campaign-review` |
| The clean-room design documents (`RECONSTRUCTION.md`, `QEMU-DIFFERENTIAL.md`, and the clean-room parts of `DESIGN.md` and `VALIDATION-*.md`) | |

**Dependency direction:** `cleanroom-lab` depends on driver-lab, and driver-lab never depends on
`cleanroom-lab`.

**`board-expert` goes neutral.** Today it always loads `os-investigator`, and `SPEC-FORMAT.md`
carries clean-room rules. After the split, it is a plain fact finder with no wall.
`cleanroom-investigator` wraps it and adds the wall on top.

**Firewall:** `cleanroom-implementer` never loads `board-expert`, `hardware-investigator` or
`cleanroom-investigator`, and its hook blocks all three. A neutral `board-expert` returns GPL
line references, so the block belongs in the repo that needs it.

### Naming

| Today | New name | Status |
|---|---|---|
| (new) anchored investigator | `hardware-investigator` | Decided |
| `anchored-peripheral-spec` | `hardware-spec` | Proposed |
| `os-investigator` | `cleanroom-investigator` | Proposed |
| "anchored spec" (the term in docs) | "hardware spec" | Proposed; see collision below |
| `anchor_check.py`, `[src:]` anchors, "anchor grammar" | Unchanged | These describe the citation mechanism, not the skill |

**Collision to settle:** "board spec" already means the frontmatter-and-facts specs `board-expert`
reads. "Hardware spec" and "board spec" read as near-synonyms. Either keep them distinct in the
glossary (a board spec is the map, a hardware spec is the per-peripheral implementation spec), or
pick a different noun such as "peripheral spec".

### Estimate

| Step | Estimate |
|---|---|
| Create `cleanroom-lab` and move skills with history (`git filter-repo` or subtree) | 3 h |
| Make `board-expert` and `SPEC-FORMAT.md` neutral | 4 h |
| Rename `os-investigator` to `cleanroom-investigator`; make it wrap `board-expert` | 3 h |
| Split `spec-verifier` | 2 h |
| Move evals and design documents; fix links | 4 h |
| Marketplace entries in both repos and the public-skills README | 1 h |
| Write `hardware-investigator`; rename `anchored-peripheral-spec` to `hardware-spec` | 1 day |

About 3 focused days in total.

## Open decisions

- [ ] Name for the clean-room repo: `cleanroom-lab`, or something else.
- [ ] Publish `cleanroom-lab` publicly from day one (skills only, which fits the policy)?
- [ ] ENC28J60 and e1000 evals: move them to `cleanroom-lab`, or keep them in driver-lab as history.
- [ ] Confirm `hardware-spec` as the new name for `anchored-peripheral-spec`, and settle the
      "hardware spec" and "board spec" collision.
- [ ] What to do with the 11 existing specs: option A, B or C.
- [ ] License for `hwspecs-docs`: CC-BY-4.0 (the usual choice for documents) or Apache-2.0
      (to match your other repos).
- [ ] Repo names: `hwspecs-gpl`, `hwspecs-docs`, `hwspecs-permissive`, or something else.

## Total

About 5–6 focused days of tooling work, plus about 2 hours per new repo, plus the spec
cleanup (1 hour to half a day depending on the option chosen).
