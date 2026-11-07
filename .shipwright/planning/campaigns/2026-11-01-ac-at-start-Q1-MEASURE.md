# ac-at-start Q1 measure: deterministic replay, question sheet, post-merge report

> Date 2026-11-01. Evidence for `2026-11-01-ac-at-start-BRIEF.md` unit Q1, rebuilt as fully deterministic code (operator decision: everything code can decide is decided by code; AI only where code cannot).

## OPERATOR DECISION REQUIRED: the brief's measure bar is not met, and cannot be measured in this design

Plainly: the brief asked Q1 to beat a control arm by 3 PRs, miss at most 1 of the 12 demand cases, flag at most 1 of the others, and have the operator find 10 of 10 questions clear. **None of that is met, and most of it is not measurable any more.** Whether to merge Q1 as built is the operator's decision, not a result of this measure.

Why the bar does not apply:

- **The "only how" class no longer exists.** The lexical HOW test that sorted PRs into "answer: only how" was dropped (operator decision: code decides what code can decide). The 6 only-how PRs are now just observable changes that need a recorded AC, so there is nothing to classify against.
- **The replay measured the post-build path, not the pre-build path.** It reads the merged diff, which is what F11 sees. Before the build the diff is empty, so at Step 2a an exemption is only a claim; the replay says nothing about what an agent would have declared then.
- **An always-observable baseline scores almost the same.** Calling every PR observable gets 20 of 20 on demand, only-how and restore and misses only the 2 non-observable no-change PRs (#855, #908); the computed surface gets those 2 and is wrong on #848, #900, #911. The code's whole advantage over "always require an AC" is 2 PRs out of 25.
- **0 of 25 PRs changed an existing AC**, so the ask rule was never exercised by real data; only by tests and the sheet below.
- **No control arm exists** (the label-based text replayed by a model was dropped with the model classifiers), so "beats the control by 3" is not measurable.

Replay, re-run with the final surface rules (25 PRs, real merged diffs, in-process, no model calls):

| Class | PRs | Computed observable (record required) | Computed not observable | Always-observable baseline |
|---|---|---|---|---|
| demand | 12 | 12 | 0 | 12 observable |
| only-how | 6 | 6 | 0 | 6 observable |
| restore | 2 | 2 | 0 | 2 observable |
| no-change | 5 | 3 | 2 (#855, #908) | 5 observable |

Question sheet (b) below is still PENDING the operator's read; the ask-rate report (c) comes only after a merge.

## SUPERSEDED: the first measure (lexical HOW design, model classifiers)

The first Q1 build measured a different design and its result no longer applies. What it measured, stated without gloss:

- 15 of the 25 baseline PRs only (3 of 10 classifier batches; the runner's spawn guard stopped the rest).
- The classifiers (Opus, blind, opaque case ids) read the rule TEXT, not the shipped code; their answer is a model's reading of a prompt.
- No control arm was run, so "beats the control by 3" was never measured.
- Result for the new-rule prompt: 6 of 6 demand cases caught, 5 of the 9 other cases wrongly flagged; the bar "flags at most 1 of the others" failed.

That design (lexical HOW test as an ask trigger, hash as the freeze, how-only and label exemptions) is dropped. Nothing below reuses its numbers.

## (a) Deterministic replay: real diffs, in-process, no model calls

**Method.** For each baseline PR, the merged squash commit and its parent are read with git; `lib/ac_surface.git_changes` parses the real diff and `observable_files` computes whether anything a user or operator can observe changed; `lib/ac_record.changed_catalog` reads the catalog ACs the diff added, changed or removed. The script is not committed (it needs `gh` and the repository history); the PR list and merge commits are in the table, and the three libraries it calls are the shipped code. No Opus or other model was called.

**PR count.** The brief previously said 16 unique PRs (corrected to 25 in the brief) and its class lists name 25 (12 demand, 6 only-how, 2 restore, 5 no-change). All 25 were replayed.

**What a deterministic rule can and cannot measure.** The classes (demand, only-how, restore, no-change) are an operator's judgement about promises; code cannot reproduce that judgement, and no longer tries to. What code decides is (1) is the diff observable, so is an exemption refused and a record required, and (2) does the catalog diff change or remove an existing AC (the operator is asked). Per class:

| Class (brief's label) | PRs | Diff observable: exemption refused, a record is required | Diff not observable: exemption allowed | Catalog diff changed or removed an existing AC (ask) |
|---|---|---|---|---|
| demand an AC (the holes plus #887) | 12 | 12 | 0 | 0 |
| answer "only how" | 6 | 6 | 0 | 0 |
| restore with a named AC | 2 | 2 | 0 | 0 |
| no change | 5 | 3 | 2 | 0 |

**Hits and misses against the brief's intent.**

- Demand, only-how and restore classes (20 PRs): the exemption was refused for **20 of 20** (hit). None of the 20 changed the catalog, so no ask could fire: these are the holes. Under the new flow each would have had to record an AC (or the AC it restores) before the build, and F11 would warn if it had not.
- No-change class (5 PRs): 2 of 5 computed as non-observable (hit: #855, #908). **3 of 5 are misses**: #848 (CI configuration), #900 and #911 (script edits that preserve behaviour) change files that define behaviour, so code cannot tell them from a real change. They are not auto-exempt; the author names the AC the unchanged behaviour keeps (a restore) or the catalog gap gets an AC. That is the cost of not trusting a label, recorded here rather than tuned away.
- Ask rule on real catalog diffs: 0 of 25 PRs changed or removed an AC, so the ask rule was exercised by the tests and the sheet below, not by this replay.

| PR | Brief class | Merge commit | Files | Observable | First observable files |
|---|---|---|---|---|---|
| #837 | demand | `b564270d5e` | 38 | yes | plugins/shipwright-iterate/skills/iterate/references/F11.md, plugins/shipwright-iterate/skills/iterate/references/F12.md |
| #839 | demand | `b7e09d3544` | 25 | yes | plugins/shipwright-compliance/scripts/hooks/check_rtm_coverage.py, plugins/shipwright-compliance/scripts/lib/git_commit_command.py |
| #842 | demand | `8f2700352e` | 32 | yes | plugins/shipwright-iterate/agents/sub-iterate-runner.md, plugins/shipwright-iterate/scripts/lib/diff_change_set.py |
| #843 | only_how | `b19939fd26` | 19 | yes | .github/workflows/pr-review-run.yml, plugins/shipwright-security/scripts/lib/pr_review_model_policy.py |
| #848 | no_change | `68bb8ce998` | 13 | yes | .github/dependabot.yml, .github/workflows/security.yml |
| #855 | no_change | `a15da2f952` | 8 | no | - |
| #859 | demand | `cb27a0e6ee` | 14 | yes | plugins/shipwright-build/scripts/hooks/force_push_guard.py, plugins/shipwright-build/scripts/hooks/validate_command.sh |
| #866 | only_how | `524588ba9c` | 29 | yes | CLAUDE.md, plugins/shipwright-compliance/scripts/hooks/check_rtm_coverage.py |
| #869 | demand | `c4287504cd` | 35 | yes | plugins/shipwright-build/scripts/hooks/review_unit_root.py, plugins/shipwright-build/scripts/hooks/write-review-payload-on-stop.py |
| #883 | demand | `14d5cee59d` | 30 | yes | plugins/shipwright-deploy/scripts/checks/validate-deploy.py, plugins/shipwright-deploy/skills/deploy/SKILL.md |
| #884 | demand | `2c201cf0e3` | 13 | yes | plugins/shipwright-build/skills/build/SKILL.md, plugins/shipwright-build/skills/build/references/code-review.md |
| #886 | only_how | `27a9e00fef` | 16 | yes | shared/scripts/lib/layer_promotion.py, shared/scripts/lib/layer_promotion_policy.py |
| #887 | demand | `4b4c85ef62` | 46 | yes | plugins/shipwright-adopt/scripts/lib/automerge_setup_scaffolder.py, plugins/shipwright-adopt/scripts/lib/claude_review_workflow_scaffolder.py |
| #897 | demand | `2e71e28f6f` | 54 | yes | plugins/shipwright-design/pyproject.toml, shared/schemas/stack_profile.schema.json |
| #900 | no_change | `cd5a854c16` | 35 | yes | plugins/shipwright-run/scripts/lib/phase_task_core.py, plugins/shipwright-run/scripts/lib/phase_task_lifecycle.py |
| #908 | no_change | `f77a4446f6` | 17 | no | - |
| #910 | restore | `98ce96c97c` | 15 | yes | plugins/shipwright-project/scripts/checks/write-project-config.py, plugins/shipwright-project/skills/project/references/step-7-scaffolding.md |
| #911 | no_change | `080c7c1c85` | 9 | yes | plugins/shipwright-run/scripts/lib/orchestrator_pkg/phase_gate.py |
| #914 | restore | `85c1eb1caf` | 13 | yes | plugins/shipwright-compliance/scripts/lib/collectors/_evidence_readers.py |
| #918 | only_how | `79ceee6410` | 18 | yes | shared/schemas/stack_profile.schema.json |
| #919 | demand | `fd42ae7717` | 34 | yes | plugins/shipwright-build/skills/build/references/browser-verify.md, plugins/shipwright-project/skills/project/references/step-7-scaffolding.md |
| #921 | only_how | `054d9992de` | 23 | yes | plugins/shipwright-build/skills/build/references/browser-verify.md, plugins/shipwright-project/skills/project/references/step-7-scaffolding.md |
| #923 | demand | `7fc60e2a32` | 25 | yes | plugins/shipwright-run/skills/run/SKILL.md, plugins/shipwright-run/skills/run/references/brief-intake.md |
| #924 | demand | `08ce885960` | 42 | yes | integration-tests/fixtures/social-engagement/brief.json, integration-tests/fixtures/social-engagement/chat-map.json |
| #936 | only_how | `31434cdb8a` | 36 | yes | plugins/shipwright-design/scripts/tools/build_kit_examples.py, plugins/shipwright-design/skills/design/SKILL.md |

**Wording rule against the live catalog.** All 303 catalog ACs were run through `wording_violations` with no diff: 3 would be refused (1.0 percent): FR-01.09.AC12 (a file name), FR-01.21.AC04 (two backticked code names) and FR-01.21.AC06 (backticked placeholders). `end-to-end`, `and/or` and `read/write` pass; a backticked slash command a user types is product wording and passes. This is a false-positive census, not a precision claim: the rule is a hard validation on NEW text only; existing ACs are not rewritten.

**Not measured.** There is no control arm: the deterministic design has nothing to beat except the label-based Step 2 text, and a model replay of that text is the measure the operator dropped. The ask rate on real runs is reported after the merge (section c).

## (b) Question sheet for the operator: approved design, regenerated

**Verdict history (short).** Round 1: the area pick list and the model rewording were unclear for cases 4-9. Round 2 added context lines, a gloss and extra options: too much. Round 3 (reduced): why it is asked, the exact acceptance-criterion wording, the requirement, and a help option that is always last. Round 4 (the operator's go, this sheet): the requirement is shown by its NAME instead of its long text; `Part:` shows bare names; the code's own top three are offered only where they differ from the model's pick; "No requirement fits, create a new one" has a fast path; and the question can be switched off or answered by Shipwright (ask / auto / off). A measurement of "code and AI agree, so skip the question" found it rarely fires (7 / 27 / 0 / 14 percent), and the AI alone beat the vote: that idea is dropped. There is no rule that a requirement is "too broad, so suggest a new one" (the operator's decision; broad requirements are re-sliced separately).

**The question** (one fixed shape, English): an intro, `Finding:` (four findings), `Part:`, the acceptance-criterion lines with the agent's wording unchanged, the requirement (`Requirement FR-xx.yy: "<name>"`, plus for a model pick one optional `In plain words:` line of at most 12 words that code checked and drops when it is long, quoted or code-like; a requirement that does not exist yet shows `New requirement:` and `Purpose:`), `Does this fit?` and numbered options, `Don't understand, need help.` always last. When the code's own best match differs from the model's pick, up to three of them follow as `Add it to FR-xx instead`. "No requirement fits, create a new one" asks one more question that shows the drafted requirement: one Yes. When the model says nothing fits, that drafted-requirement question is the first one.

**`Part:`** is never a hard-coded word and never a path prefix. It is the spec's own grouping of the requirement (the requirements table's `Area` column, else the name of the split; this repo's `Adopted` names nothing and is skipped), else the changed paths' top-level parts as bare names (`shipwright-build`, not `plugins/shipwright-build`; `shared`, docs, tests and tooling are no part), else no line. On this sheet the paths are the files of the recorded cases' commits; a real run passes the paths it will change in the add item's `files`.

**Modes.** `ask` (default for an interactive iterate), `auto` (nothing is asked: the model's pick, else the best match, else a requirement Shipwright drafts; every decision is recorded `auto-assigned, unconfirmed`; the end list "assignments made without you" puts changed or removed existing criteria first; the default in a hands-off run) and `off`. Set per project (`ac_decision.mode`), per campaign (`--ac-mode`) or per run (`SHIPWRIGHT_AC_MODE`).

**The model** picks ONE requirement id (or null = none fits), writes the optional plain line and drafts a name and sentence for a new requirement; code checks the id exists, checks every line and fetches the name. One live run, cases 4 to 10, `anthropic/claude-haiku-5.5` (pinned), 7 short calls: **7 of 7 replies were valid, 0 fell back**; 6 named an existing requirement and 1 (case 7) said none fits, so that question is the drafted-new-requirement one.

Reading it honestly:

- The model picks by meaning; whether each pick is right is for the operator to judge (the options "wrong requirement" and "need help" exist for that). Case 4 (FR-01.17 for a review-reuse rule in the build and iterate parts) is the pick most open to doubt.
- The code's "Add it to ... instead" list is weak: it ranks by shared words, so in cases 4, 8 and 10 two or three of the three entries are unrelated requirements (for example "Triage Inbox" in case 10). It is shown because the operator asked for it; a better ranking (the run history) is not built.
- The acceptance-criterion wording is shown as recorded, including its jargon ("coordinator", "outside reviewers", "however the command was typed"); the agent-side rule in Step 2a (real names, no role nouns) is the fix, not a code check.
- Real gap for non-Shipwright projects: the spec has no component per requirement. A requirements table gives the `Area` column and several splits give the split name; a single-split project without an `Area` column gets no grouping, so `Part:` falls back to directories or is omitted.
- The cases 1 to 3 "until now" texts are reconstructed from the recorded cases. The 10-of-10 bar is NOT claimed; the operator has not seen this sheet.

### Case 1 (#839)

```
Shipwright keeps a list of requirements (FRs). Before building, it checks how
this change fits that list: it changes a requirement, adds to one, or creates
a new one. Please check that Shipwright made the correct selection.

Finding: this change changes an existing acceptance criterion.
Part: shipwright-compliance
Acceptance criterion today: "A commit is held back when the build progress line shows less than the required share of work done"
Acceptance criterion after this change: "A commit is held back when too few requirements are covered by passing tests"
Requirement FR-01.17: "Independent re-check on the code host"

Does this fit?
1 Yes, change it.
2 No. (You tell the agent in the chat what you want instead.)
3 Don't understand, need help.
```

### Case 2 (#923)

```
Shipwright keeps a list of requirements (FRs). Before building, it checks how
this change fits that list: it changes a requirement, adds to one, or creates
a new one. Please check that Shipwright made the correct selection.

Finding: this change changes an existing acceptance criterion.
Part: shipwright-run
Acceptance criterion today: "The stack profile is guessed from the kind of storage the project uses"
Acceptance criterion after this change: "A stack profile named in the project brief is used as given, and an unusable name stops the run with a clear message"
Requirement FR-01.02: "Project decomposition into scoped units"

Does this fit?
1 Yes, change it.
2 No. (You tell the agent in the chat what you want instead.)
3 Don't understand, need help.
```

### Case 3 (#887)

```
Shipwright keeps a list of requirements (FRs). Before building, it checks how
this change fits that list: it changes a requirement, adds to one, or creates
a new one. Please check that Shipwright made the correct selection.

Finding: this change removes an acceptance criterion.
Part: shipwright-adopt
Acceptance criterion that no longer holds: "Adopting a project sets up the automatic Claude review on every pull request"
Requirement FR-01.17: "Independent re-check on the code host"

Does this fit?
1 Yes, that is intended.
2 No, keep it. (The change is then reworked.)
3 Don't understand, need help.
```

### Case 4 (#869)

```
Shipwright keeps a list of requirements (FRs). Before building, it checks how
this change fits that list: it changes a requirement, adds to one, or creates
a new one. Please check that Shipwright made the correct selection.

Finding: this change adds a new acceptance criterion to an existing requirement.
Part: shipwright-build, shipwright-iterate
New acceptance criterion: "A coordinator repeats a review unless the earlier one is shown to cover exactly the code that is merged"
Requirement FR-01.17: "Independent re-check on the code host"
In plain words: Independent re-check of proposed changes on the code host before merge

Does this fit?
1 Yes, add it there.
2 Add it to FR-01.11 instead: Ongoing change at the depth it deserves
3 Add it to FR-01.03 instead: Implementation planning with independent review
4 Add it to FR-01.05 instead: Test-driven build of planned sections
5 No, wrong requirement. (You tell the agent in the chat which one.)
6 No requirement fits, create a new one.
7 Don't understand, need help.
```

### Case 5 (#884)

```
Shipwright keeps a list of requirements (FRs). Before building, it checks how
this change fits that list: it changes a requirement, adds to one, or creates
a new one. Please check that Shipwright made the correct selection.

Finding: this change adds a new acceptance criterion to an existing requirement.
Part: shipwright-build, shipwright-iterate
New acceptance criterion: "The build phase asks outside reviewers to read the code of each section unless the owner turns this off"
Requirement FR-01.05: "Test-driven build of planned sections"

Does this fit?
1 Yes, add it there.
2 No, wrong requirement. (You tell the agent in the chat which one.)
3 No requirement fits, create a new one.
4 Don't understand, need help.
```

### Case 6 (#897)

```
Shipwright keeps a list of requirements (FRs). Before building, it checks how
this change fits that list: it changes a requirement, adds to one, or creates
a new one. Please check that Shipwright made the correct selection.

Finding: this change adds a new acceptance criterion to an existing requirement.
Part: shipwright-adopt, shipwright-design, shipwright-project, shipwright-run, shipwright-test
New acceptance criterion: "A team can keep its own stack profile in its project and it is used instead of the shipped one"
Requirement FR-01.02: "Project decomposition into scoped units"
In plain words: Breaks a project into deliverable requirements and writes assistant starting guidance.

Does this fit?
1 Yes, add it there.
2 No, wrong requirement. (You tell the agent in the chat which one.)
3 No requirement fits, create a new one.
4 Don't understand, need help.
```

### Case 7 (#919)

```
Shipwright keeps a list of requirements (FRs). Before building, it checks how
this change fits that list: it changes a requirement, adds to one, or creates
a new one. Please check that Shipwright made the correct selection.

Finding: this change needs a requirement that does not exist yet.
Part: shipwright-adopt, shipwright-build, shipwright-project, shipwright-test
New acceptance criterion: "An app that is a chat window starts from a ready-made setup that needs no deployment"
New requirement: Ready-made starter apps for chat windows
Purpose: Lets a person start a chat-window app from a prepared template that runs without any deployment step.

Does this fit?
1 Yes, create it.
2 No. (You tell the agent in the chat what you want instead.)
3 Don't understand, need help.
```

### Case 8 (#866)

```
Shipwright keeps a list of requirements (FRs). Before building, it checks how
this change fits that list: it changes a requirement, adds to one, or creates
a new one. Please check that Shipwright made the correct selection.

Finding: this change adds a new acceptance criterion to an existing requirement.
Part: shipwright-compliance
New acceptance criterion: "A commit is checked for enough tested requirements at the moment it is recorded, however the command was typed"
Requirement FR-01.10: "Audit-ready compliance evidence"
In plain words: Audit-ready evidence linking requirements to the tests covering them

Does this fit?
1 Yes, add it there.
2 Add it to FR-01.16 instead: Guided requirement elicitation
3 Add it to FR-01.04 instead: Mockups from requirements
4 Add it to FR-01.11 instead: Ongoing change at the depth it deserves
5 No, wrong requirement. (You tell the agent in the chat which one.)
6 No requirement fits, create a new one.
7 Don't understand, need help.
```

### Case 9 (#936)

```
Shipwright keeps a list of requirements (FRs). Before building, it checks how
this change fits that list: it changes a requirement, adds to one, or creates
a new one. Please check that Shipwright made the correct selection.

Finding: this change adds a new acceptance criterion to an existing requirement.
Part: shipwright-design
New acceptance criterion: "Every colour set keeps text easy to read, also when the page is enlarged"
Requirement FR-01.04: "Mockups from requirements"
In plain words: Turns requirements into clickable mockups and design tokens before coding

Does this fit?
1 Yes, add it there.
2 No, wrong requirement. (You tell the agent in the chat which one.)
3 No requirement fits, create a new one.
4 Don't understand, need help.
```

### Case 10 (#843)

```
Shipwright keeps a list of requirements (FRs). Before building, it checks how
this change fits that list: it changes a requirement, adds to one, or creates
a new one. Please check that Shipwright made the correct selection.

Finding: this change adds a new acceptance criterion to an existing requirement.
Part: shipwright-security
New acceptance criterion: "The pull request gate is run by a different reviewer model, and what it checks stays the same"
Requirement FR-01.17: "Independent re-check on the code host"
In plain words: Independent re-check of proposed changes on the code host before merge.

Does this fit?
1 Yes, add it there.
2 Add it to FR-01.11 instead: Ongoing change at the depth it deserves
3 Add it to FR-01.14 instead: Triage Inbox
4 Add it to FR-01.01 instead: End-to-end delivery pipeline
5 No, wrong requirement. (You tell the agent in the chat which one.)
6 No requirement fits, create a new one.
7 Don't understand, need help.
```

## (c) Ask rate: reported after the merge, never before

The ask rate on the first 20 iterates after the merge is a report only. Stop rule (the brief's): above 30 percent, or the operator rejects more than 3 of 10 sampled ACs. The counting producer is `lib/ac_decision.count_decisions` (buckets `auto`, `asked`, `exempt`, `restore`, `unchanged`, plus `exempt_share` and `restore_share`), recorded per run in `ac-record.jsonl`, so a rising exemption share is visible without a model. There is no automated aggregator across runs yet: the 20-run report will be made by a one-off script over the per-run records when the time comes (not built now).
