# The "package" test: can FR + AC + tests + iterate specs explain WHAT and WHY?

> **Note 2026-10-31:** evidence for `2026-10-31-baseline-package-BRIEF.md` (section 1); every judgement in it is AI-made (Opus readers or the measuring agent), not human-verified. Paths such as `work/`, `runs/` and `replay2/` refer to the local measurement archive, not to this repository.

**Date:** 2026-10-31 · read-only measurement, nothing in the repo changed · inputs: `runs/BL0b/labels/FR_CATALOG.md` (21 FRs, 289 ACs), `replay2/` labels, repo `shipwright_events.jsonl`, `.shipwright/planning/iterate/`, `.shipwright/planning/adr/`, `.shipwright/agent_docs/decision_log.md` + `decision-drops/`, `.shipwright/compliance/`, `git log origin/main`.

## Summary (plain language)

1. **The acceptance criteria are mostly written the right way.** In a sample of 60 of 289, about 3 in 4 state a pure outcome ("a failed phase is never counted as done; a person decides"). About 1 in 5 also name a tool, vendor, number or file that could change without the promise changing. Only 2 of 60 are mainly "how".
2. Two independent AI readers agreed on 55 of 60 (92%). So the wording quality is not the main problem.
3. **The bigger problem is what is missing.** Of the 17 recent PRs that added behaviour no AC describes, about 11 added something a user or operator would notice or demand (e.g. "the build now sends your code to an outside AI reviewer by default"; "a run with no hosting target finishes without a hosting step"). A rebuild from the catalog would silently lose these.
4. Rough rate: **somewhere between 11 and 30 such holes per 100 PRs, best guess 15 to 20** (the sample was not random, so this is a rough range, not a measurement).
5. All of these holes came from changes recorded as "no requirement affected".
6. **The "why" trail mostly exists.** For 14 of 20 random finished iterates you can go from the requirement to the change record to a written plan and the PR. For 6, a link is missing (old entries from before the naming scheme, or small runs that never wrote a plan). None was a dead end.
7. **But the trail stops at the requirement, never at the acceptance criterion.** Only 1 of 20 iterates can be tied to a specific AC. The other way round, "show me every change that shaped AC X", works for only about 13% of ACs (those carrying a run id in their text), and then only for the latest change.
8. The single field that would fix most: record **which ACs a change touched or checked** (AC ids) on every finished change, next to the plan file path and PR number.
9. Requirement names are mostly tool names: 13 of 21 are a command such as "/shipwright-iterate" (42 ACs). A rebuild that splits or merges tools would have nothing stable to hang them on.
10. Every judgement here comes from AI readers (Opus) or my own reading. Nobody has checked it against a human, and the hole count rests on the replay2 labels.

---

## 1. AC level: WHAT/WHY vs MIXED vs HOW

**Method.** Seed `20261031`, proportional stratified sample of 60 ACs across all 21 FRs (each FR at least 1; FR-01.11 got 9, FR-01.14 got 6). Two independent Opus agents saw only the 60 AC texts. The order was shuffled, and agent B worked in reverse order. They had no catalog context, no repo and no access to each other's output. Prompt: `work/PROMPT_classify.md`; sample: `work/sample.json`; outputs: `work/classify_A.json`, `work/classify_B.json`.

| | A | B | Both agree |
|---|---|---|---|
| WHAT/WHY | 46 | 45 | 43 |
| MIXED | 12 | 13 | 10 |
| HOW | 2 | 2 | 2 |
| **Agreement** | | | **55 / 60 (92%), Cohen's kappa ≈ 0.78** |

Splits (all WHAT/WHY vs MIXED): FR-01.01 AC05, FR-01.11 AC22, FR-01.11 AC27, FR-01.14 AC02, FR-01.19 AC04.

**Extrapolated to 289 ACs (the sample is self-weighting):** about 215 WHAT/WHY, about 60 MIXED, about 10 HOW. A 60-item sample gives roughly ±11 points of uncertainty on the 75% figure.

### Examples (both readers agreed unless marked)

**WHAT/WHY**: the promise survives any rewrite
| AC | One-line reason |
|---|---|
| FR-01.01 AC02 | A phase that failed its own checks is never marked done; a person decides. |
| FR-01.03 AC17 | Planning produces only a plan: no code written, no tests run. |
| FR-01.07 AC08 | Leaked secrets are masked in reports and can't be unmasked in unattended runs. |
| FR-01.08 AC07 | Rolling back is refused, with an explanation, if stored data has already moved on. |
| FR-01.09 AC10 | A release can be previewed without changing anything. |
| FR-01.10 AC02 | Evidence that no longer matches its source stops counting as evidence. |
| FR-01.12 AC06 | A preview never shows some other application as if it were this project. |
| FR-01.18 AC04 | Things that can't be judged are left out of the grade, not scored zero or guessed. |

**MIXED**: a real promise plus a detail that could change
| AC | Promise / replaceable detail |
|---|---|
| FR-01.03 AC02 | A missing outside review is never skipped quietly / "two outside reviewers" and "access key" are specifics. |
| FR-01.03 AC03 | An independent review always happens, or the fallback is stated / ties in how the Claude model is configured. |
| FR-01.03 AC07 | Each plan section says purpose, steps and testing / "at least two steps" is a tuning number. |
| FR-01.04 AC13 | Mockups use the real brand / the brand source is a named vendor product (claude.ai Design System). |
| FR-01.11 AC11 | Review findings are kept and re-readable / lists today's set of review steps by name. |
| FR-01.11 AC30 | Outside reviewers are independent of the tool that wrote the change / framed as Claude vs Codex. |
| FR-01.14 AC18 | Scanner results must not leak finding text / fixes the storage format (counts, links, length cap). |
| FR-01.20 AC01 | Each model exchange is counted once / spells out the transcript format used to do it. |

(More: FR-01.11 AC35 vendor-specific setting precedence; FR-01.14 AC14 two named data sources and their fallback order.)

**HOW**: mainly mechanism (only 2 in the sample)
| AC | One-line reason |
|---|---|
| FR-01.11 AC32 | Only says one more model name (fable/opus/sonnet/haiku) is accepted in a setting. |
| FR-01.21 AC05 | Describes a specific script, config file, command and flag for one vendor tool. The promise left over is just "hooks run there too". |

There are no further HOW examples. Below these two, the borderline cases are the five split ACs listed above.

**Pattern:** MIXED and HOW cluster around **model and vendor choices** (FR-01.03, FR-01.11 AC30/32/35, FR-01.21) and **tuning numbers and formats**. These are exactly the parts the stated goal says "may change freely".

### Plugin-sized FR titles
13 of 21 FR titles are a slash command (FR-01.01 to FR-01.13, e.g. "/shipwright-iterate", 42 ACs; "/shipwright-plan", 22). The description sentences under them are capability statements and read fine. The titles, though, name a tool, not a capability. FR-01.14 "Triage Inbox" (29 ACs) is a component name too. FR-01.15 to FR-01.20 are capability-named, which is the better shape. A rebuild that reshapes the tools would keep the ACs but lose the anchor. Renaming the titles is cheap and needs no re-mint.

**Caveat:** both readers are Opus and saw text only. The catalog was deliberately written under a "no file names, plain language" rule (FR-01.02 AC08/AC09), so a high WHAT/WHY share is expected. It measures the wording, not completeness.

## 2. Baseline gaps: behaviour no AC describes

Source: replay2 step-1 labels X/Y (`replay2/raw/step1_*`). 16 PRs both labelers called NEW, plus #859 (split NEW/IMPLEMENT). The "behaviour" column below paraphrases their `new_uncovered_behaviour` entries. The verdict is mine: would a rebuild from the catalog alone lose it, and is what would be lost a WHAT/WHY promise or only HOW? A keyword grep of today's `spec.md` (e.g. "stack profile", "chat-first", "deploy target", "risk flag", "promot") found none of them added since. That is a grep, not a full read.

| PR | Title (short) | Behaviour, plain | Lost in rebuild? | Verdict |
|---|---|---|---|---|
| 837 | one F11 extension point + reason-code vocabulary | Every change report states how many gate exemptions were accepted, and why. | yes | **WHAT/WHY** hole (transparency) |
| 839 | commit-time coverage hook measures requirement coverage | Commits are warned/blocked when requirement test coverage falls below the agreed level. | yes | **WHAT/WHY** hole (80% and the file it reads are HOW) |
| 842 | small iterate with risk flag or >100 lines answers for its code review | Risky or larger "small" changes must have an independent code review or a stated reason. | yes | **WHAT/WHY** hole (100-line rule is HOW) |
| 843 | PR-review default model → Haiku 5.5 | The outside PR reviewer uses a different model by default. | yes | HOW only |
| 859 (split) | force-push guard only blocks a real force flag at main | Force-pushing over main is blocked, normal commands aren't. If the checker is missing, it errs on blocking. | yes | **WHAT/WHY** hole (safety promise + fail-safe direction) |
| 866 | git pre-commit runs the coverage gate | The same coverage check also applies at the real commit; one logged override covers both. | partly | HOW (extends the 839 hole) |
| 869 | campaign reviews use resolved tier; 3f-bis skip on git-verified attestation | A second-look review is skipped only when there is proof the merged code was already reviewed and passed. | yes | **WHAT/WHY** hole (assurance rule) |
| 883 | honor profile and deploy_target none | A project with no hosting target finishes without a hosting step; preview says "nothing to preview" for non-web projects. | yes | **WHAT/WHY** hole (and FR-01.01 AC01 still implies hosting always runs) |
| 884 | build external code review default-on | Build sends each code diff to an outside AI reviewer by default unless the project opts out. | yes | **WHAT/WHY** hole (data leaves the machine) |
| 886 | layer promotion skips advisory adopted spec | Advisory requirements of an onboarded repo are never auto-promoted to stricter test demands. | yes | HOW (internal bookkeeping; borderline) |
| 897 | stack-profile resolver, schema, CLI | A team's own stack profile wins over the bundled one; a broken one fails loudly; profiles can be committed. | yes | **WHAT/WHY** hole |
| 918 | optional ux_shape/ui_host in profile schema | Two optional fields are accepted; nothing reads them yet. | n/a | HOW only |
| 919 | bundled chat-first-json profile | Shipwright can set up a "chat-first" app out of the box. | yes | **WHAT/WHY** hole (a supported app type) |
| 921 | Windows npx spawn, Browser Verify URL, host spelling | Tests use the profile's declared address; the app binds to 127.0.0.1. | yes | HOW only |
| 923 | stack profile named in wizard brief is validated | A stack the user names is used or the user is asked, never silently swapped. An agent may never approve fixtures on the operator's behalf. | yes | **WHAT/WHY** hole (2 promises) |
| 924 | chat-first design from the Brief package | Design can produce a chat-plus-pane app shape, checked against the agreed key flows. | yes | **WHAT/WHY** hole (chip/nav rule is HOW) |
| 936 | Untitled UI kit with three token sets | Mockups are built from a component kit with three ready-made looks. | yes | HOW (mostly; "pick one of 3 looks" is minor WHAT) |

**Count:** 11 WHAT/WHY holes (837, 839, 842, 859, 869, 883, 884, 897, 919, 923, 924) and 6 HOW-only (843, 866, 886, 918, 921, 936) among 17 PRs.

**Per 100 PRs (rough).** These 35 PRs were chosen from a 100-PR window (about 4 weeks) on BP's own disagreements (BL0B §0/§89), not at random. So:
- Hard floor: **11 per 100** (only the ones found).
- If the 35 were representative: about 31 per 100.
- Best guess **15 to 20 per 100**, i.e. roughly 4 to 5 a week. The intervals are wide. Labels are LLM-made, packs were size-capped, and "WHAT/WHY vs HOW" here is one reader's call (mine), not double-blind.

All 11 holes sat in PRs whose author recorded `spec_impact: none`. 6 of them (837, 839, 842, 883, 923, 924) named the right FR. So the FR was known, and the AC was simply never written.

## 3. Spec chain: FR → (AC) → iterate spec/mini-plan → PR

**Method.** Pool: 216 `work_completed` events with `affected_frs` (amended events removed). Seed `20261031`, 20 drawn. For each, I tried event → `adr_id` → file in `.shipwright/planning/iterate/` (name match, run-id dir, content grep) → `planning/adr/` file / `decision_log.md` / `decision-drops/` → commit/PR (`git log origin/main --grep=<run id>`) → AC (event fields; run-id suffix on AC text in `spec.md`) → RTM. Raw data: `work/chain_raw.json`, script `work/chain.py`.

| # | Date | Run id (adr_id) | FRs | Plan/spec doc | Why-record | PR | AC link | Result |
|---|---|---|---|---|---|---|---|---|
| 1 | 05-03 | ADR-027 | 01.06 | none found | decision_log ADR-027 | none (commit in event) | no | **partial** |
| 2 | 05-04 | ADR-029 | 01.11 | none found | decision_log ADR-029 | none (commit in event) | no | **partial** |
| 3 | 05-06 | ADR-037 | 01.11 | `2026-05-06-e2e-verification-gate.md`, found only by matching the title | decision_log ADR-037 | none (commit in event) | no | **partial** |
| 4 | 05-16 | spec-impact-gate | 01.11/10/02 | `2026-05-16-spec-impact-gate.md` | decision_log ADR-053 | commit, no PR no. | no | full (pre-PR era) |
| 5 | 07-02 | gh-prompt-ghost-fix | 01.14 | `2026-07-02-gh-prompt-ghost-fix.md` | decision_log | #306 | no | full |
| 6 | 07-23 | tests-skipped-tracking | 01.10 | `iterate-…md` | drop | #430 | no | full |
| 7 | 07-27 | triage-defer-ci-cap | 01.14 | spec + miniplan | drop | #444 | no | full |
| 8 | 07-27 | changelog-writer-preserve-history | 01.09 | `iterate-…md` | drop | #452 | no | full |
| 9 | 07-27 | checks-that-gate-nothing | 01.17 | `2026-07-27-…md` | drop | #475 | no | full |
| 10 | 07-27 | triage-defer-review-followup | 01.14 | `2026-07-27-…md` | drop | #479 | no | full |
| 11 | 08-01 | verify-local-surface-gates | 01.17 | **none** (dir has only `reviews.json`) | drop | #525 | no | **partial** |
| 12 | 09-07 | p3-4-tagging-backfill | 01.01/07/11/13 | **none in iterate/**; plan is the campaign brief (`2026-08-23-req3-04-…-BRIEF.md`, which is untracked in the local checkout) | `planning/adr/` file | #689 | no | **partial** |
| 13 | 09-10 | p34c-promotion-anchor-guard | 01.11 | spec + miniplan | adr file | #717 | no | full |
| 14 | 09-16 | e6-judgement-drift-tests | six FRs | `…-MINIPLAN.md` | adr file | #763 | no | full |
| 15 | 09-18 | codex-review-tier-config | 01.11 | spec + miniplan | adr file | #771 | **yes**: run id in the text of 3 FR-01.11 ACs | full **incl. AC** |
| 16 | 10-07 | u9-rtm-80-hook | 01.10 | `<run>/mini_plan.md` + architecture brief | decision_log | #839 | no | full |
| 17 | 10-24 | s3-adopt-scaffolding | 01.06 | `<run>/mini-plan.md` | adr file | #903 | no | full |
| 18 | 10-25 | run-completion-after-skips | 01.01 | **none** (review replies only) | adr file | #913 | no | **partial** |
| 19 | 10-25 | gate-hardening-leftovers | 01.01 | spec + `<run>/miniplan.md` | adr file | #917 | no | full |
| 20 | 10-26 | b3c-screenshot-check-in-test | 01.06 | `<run>/mini-plan.md` + brief | adr file | #925 | no | full |

**Totals (FR → plan → PR):** **14 full, 6 partial, 0 not at all.** **FR → AC → plan: 1 of 20.**

### Where it breaks
- **No AC on the event.** `fr_impact` (AC-level) appears in 3 of 219 FR-tagged events and in none of the 20. Events name the FR, never the AC. This is the dominant break.
- **No plan document** for small runs (#11, #18) and campaign units whose plan lives in a campaign brief (#12). Population-wide, of 192 events with an `iterate-…` id, 114 have a spec file by name, 33 a plan inside the run directory, and **45 have no plan document at all**. A further 24 events carry a legacy `ADR-0xx` id with no spec file.
- **The path is found by convention, not by a field.** Plan files come in at least 5 shapes: `iterate-<date>-<slug>.md`, `<date>-<slug>.md` (prefix dropped), `-miniplan.md`, `-MINIPLAN.md`, `<run>/mini-plan.md|miniplan.md|mini_plan.md`. A rebuild reader needs fuzzy matching.
- **`commit` field empty** on 182 of 219 events. The PR is found only because squash commits happen to contain the run id (`git log --grep`). That held for 17 of 17 recent runs, but it is not guaranteed.
- **RTM stale.** `traceability-matrix.md` was generated 2026-10-09. The 4 newest sampled events are not in it. It links FR → event id (with description), not to the plan file or PR.

### The other way: AC → specs/PRs that changed it
- **Only partly possible.** About 39 of 289 AC lines (≈13%) carry a run-id suffix, covering 20 distinct runs. That gives the *last* run that shaped the AC, not its history.
- **Via `git log -L` on `spec.md`:** technically possible (spec.md changed in 76 of 1,959 main commits). It only shows runs that edited the AC text. The 80% of iterates recorded `spec_impact: none` are invisible, even when they changed the behaviour (section 2).
- **Via tests:** `test-traceability.json` binds ACs to tests (1,139 AC-level `covers` marks). AC → bound test → `git log` of the test file → PR works mechanically, but it is noisy (refactors, unrelated edits).
- **Conclusion:** there is no first-class AC → change index today.

### The single missing field that would fix most
**`affected_acs` on every `work_completed` event**: the AC ids changed, implemented, or checked-and-unchanged, plus `catalog_gap: true` when no AC fits. It fixes the AC break in 19 of 20 forward chains. It makes AC → changes a simple event-log query (no git mining). It is the same field OPTIONS O3 proposes (`checked_acs`), so one change serves both goals. A close second is `plan_path` + `pr` on the event, which removes the filename guessing and the empty `commit`.

## Fixes, ranked by value for the goal (WHAT/WHY controlled, HOW free)

1. **Make "no requirement affected" name the AC or declare a catalog gap** (O3 `checked_acs` / `catalog_gap`, stored as `affected_acs` on the event). This targets the ~11 holes per sample (all came through `none`) *and* the missing AC link in the chain. Highest value, small effort.
2. **When a gap is declared, mint or fold a WHAT/WHY AC in the same PR.** Write the promise only ("build sends code to an outside reviewer by default; projects can opt out"), not the mechanism. Backfill the 11 holes above as a first batch.
3. **Put `plan_path` and `pr` on the event, and require a plan stub for every non-trivial run.** That stub can be 3 lines: problem, intended outcome, why. Today 45 of 192 runs have no plan doc, and the event `summary` is filled in only 118 of 219.
4. **Strip replaceable detail from the ~20% MIXED ACs.** Move model and vendor names, thresholds and formats into config, ADRs or a "current realisation" note under the AC, so the AC text stays stable when the HOW changes. Start with the model/vendor cluster (FR-01.03 AC03, FR-01.11 AC30/32/35, FR-01.21 AC05).
5. **Rename the 13 tool-named FR titles to capability names** (e.g. "/shipwright-iterate" → "Ongoing change at the depth it deserves"). This is cosmetic, but it gives a rebuild a stable anchor. No re-mint needed.
6. **Regenerate the RTM regularly** (currently 3 weeks stale) and link plan files and PRs from it, not just event ids.

## Files
- `work/sample.json`: seed, per-FR allocation, the 60 sampled ACs
- `work/blind_acs.md`, `work/PROMPT_classify.md`: what the two readers saw
- `work/classify_A.json`, `work/classify_B.json`: per-AC class, mechanism, reason
- `work/agree.txt`: side-by-side comparison
- `work/chain.py`, `work/chain_raw.json`: spec-chain trace (seed 20261031, pool 216)
- `work/sample_acs.py`: sampling script
