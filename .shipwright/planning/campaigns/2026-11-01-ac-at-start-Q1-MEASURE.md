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

## (b) Question sheet for the operator: operator verdicts recorded, new wording PENDING

Ten cases, each question exactly as the tool prints it now. Cases 1 and 2 are changed ACs, case 3 a removed AC; cases 4 to 10 are a new promise with no single owning area.

**The operator's verdicts on the previous sheet (recorded, not re-asked):** cases 1 and 2 clear; case 3 almost clear (the term "Claude review" was not explained); cases 4 and 9 not clear (a horizontal promise: it applies across parts of the product); case 5 not clear (touches the build phase and iterate, should become its own Review requirement); cases 6 and 7 not clear (should become a new stack-profile requirement); case 8 not clear ("the command is typed" was not understood); case 10 clear (the operator would pick B). The mix: the not-clear cases lacked CONTEXT and offered wrong area lists more than they lacked wording.

**What changed in the question (all computed by code; the model only words):**

1. An `Affects:` line from the changed paths (`plugins/<name>/` becomes a plain name such as "Build phase, Iterate"; omitted when no path maps or one plugin has no plain name). The paths on this sheet are the full file lists of the recorded cases' commits (`git show --name-only`); before a build the diff is empty, so a real run passes the paths it will change in the add item's `files`.
2. Cross-cutting: when the change touches 2 or more plugins, or no existing area fits, the FIRST choice is "Applies to several areas: make it its own requirement" (recorded as a new requirement with `cross_cutting: true`). The area list is no longer the only choice.
3. The question is "Which requirement would this promise belong to?".
4. Every question has "I do not understand this, please explain." The agent then rewords the promise in plainer words and asks again (tool exit 11; the new wording is a new question; a resume reuses the stored question and calls no model).
5. "In plain words:" is shown only when the model's wording shares fewer than 3 in 4 words with the original (otherwise the glossary explains the jargon in a bracket). The prompt now forbids copying jargon (reviewer, stack profile, command, merged, deployment, coordinator) and demands everyday explanations.
6. An `Already in the catalog:` line lists requirements that contain the same two-word phrase as the promise (omitted when none; a phrase found in more than 4 areas is ignored).
7. The glossary explains "Claude review", "outside reviewers" and "command", and changed or removed promises now get the same bracket explanations as new ones (this is what case 3 needed).

**Live run (the only live use of this round):** model `anthropic/claude-haiku-5.5` (pinned in the tool), 7 calls, one per case 4 to 10, on the real agent-recorded wording and the new prompt. Cost: 7 short calls on a small model, a few cents at most (not metered here). **Validation: 6 of 7 passed, 1 fell back** (the tightened validator may reject more: case 8 fell back because the model's wording added "each" and "no"; the deterministic wording with the glossary brackets is shown instead). The plain wording was shown in 5 of the 7 cases and left out in 2: it is left out when it only swaps a word or two (case 9) or when it fell back (case 8).

Reading the result honestly:

- The context lines do what the operator asked for in cases 4, 5, 6 and 7: each now opens with "Applies to several areas: make it its own requirement" and names the parts touched. Whether that makes them clear is the operator's call; the bar (10 of 10 clear) is NOT claimed.
- Case 9 stays a gap: the real change touches only the design plugin, so code sees one area and offers no cross-cutting choice, although the operator calls the promise horizontal. Code cannot know a promise is horizontal from paths alone; the operator can pick "Somewhere new" or "I do not understand this".
- Case 6 lists 5 parts under `Affects:` (the real change touched many); the line is long but true. "Already in the catalog" is a plain phrase match and can be noisy (case 5 lists "Mockups from requirements"; case 7 lists "End-to-end delivery pipeline"); it never blocks anything.
- The plain wording is more useful than before where it is shown: it replaces "coordinator" with "work manager", "stack profile" with "ready-made set of technology choices", "merged" with "added to the main version" (cases 4, 6, 7, 10). Some replacements are clumsy ("needs no putting live on a hosting service").
- The "until now" texts in cases 1 to 3 are reconstructed from the recorded cases, not copied from the catalog.

### Case 1: #839 an existing promise is changed

Operator's verdict on the previous sheet: clear.

What the operator sees now:

```
This change alters a promise the product makes. Until now: A commit is held back when the build progress line shows less than the required share of work done. After this change: A commit is held back when too few requirements are covered by passing tests (commit: a saved snapshot of the work, kept in the project history; build: the stage where the software is actually written). Should it hold like this?
Affects: Compliance evidence.
1 Yes, change it.
2 No, instead: <your wording>
3 I do not understand this, please explain.
```

Operator: clear / not clear (PENDING - on this new wording)

### Case 2: #923 an existing promise is changed

Operator's verdict on the previous sheet: clear.

What the operator sees now:

```
This change alters a promise the product makes. Until now: The stack profile is guessed from the kind of storage the project uses. After this change: A stack profile named in the project brief is used as given, and an unusable name stops the run with a clear message (stack profile: the ready-made set of technology choices a project starts from). Should it hold like this?
Affects: Orchestrator.
1 Yes, change it.
2 No, instead: <your wording>
3 I do not understand this, please explain.
```

Operator: clear / not clear (PENDING - on this new wording)

### Case 3: #887 an existing promise is removed

Operator's verdict on the previous sheet: almost clear: the term "Claude review" was not explained.

What the operator sees now:

```
This change removes a promise. Until now this held: Adopting a project sets up the automatic Claude review on every pull request (claude review: a check of the work by the Claude AI, done inside the working session before anything is shared; pull request: a proposal to add finished work to the main version, which others can review first). After this change it no longer holds.
Affects: Adopting an existing project.
1 Yes, that is intended.
2 No, keep the promise (the change is then reworked).
3 I do not understand this, please explain.
```

Operator: clear / not clear (PENDING - on this new wording)

### Case 4: #869 no owner named

Operator's verdict on the previous sheet: not clear: a horizontal promise (it applies across parts of the product).

Agent's original wording: "A coordinator repeats a review unless the earlier one is shown to cover exactly the code that is merged"

Model wording (model anthropic/claude-haiku-5.5): "The automated work manager runs a check again unless the earlier check is shown to have covered exactly the code being added to the main version." - SHOWN (meaningfully different).

What the operator sees now:

```
This change adds a new promise: A coordinator repeats a review unless the earlier one is shown to cover exactly the code that is merged.
In plain words: The automated work manager runs a check again unless the earlier check is shown to have covered exactly the code being added to the main version.
Affects: Build phase, Iterate.
Which requirement would this promise belong to?
A Applies to several areas: make it its own requirement.
B Independent re-check on the code host: Re-checks each proposed change on the code hosting site before it can be added to the main version.
C Recovery of a broken shared branch: Finds which recent change broke the shared main version when it stops working, and reports what failed.
D Somewhere new (tell us the name).
E It is not a promise, only how it is built.
F Not wanted: <your wording>
G I do not understand this, please explain.
```

Operator: clear / not clear (PENDING - on this new wording)

### Case 5: #884 no owner named

Operator's verdict on the previous sheet: not clear: touches the build phase and iterate; should become its own Review requirement.

Agent's original wording: "The build phase asks outside reviewers to read the code of each section unless the owner turns this off"

Model wording (model anthropic/claude-haiku-5.5): "When the product builds each section of a project, it asks outside reviewers to read that section's code, unless the owner turns this off." - SHOWN (meaningfully different).

What the operator sees now:

```
This change adds a new promise: The build phase asks outside reviewers to read the code of each section unless the owner turns this off.
In plain words: When the product builds each section of a project, it asks outside reviewers to read that section's code, unless the owner turns this off.
Affects: Build phase, Iterate.
Already in the catalog: Implementation planning with independent review; Mockups from requirements; Test-driven build of planned sections.
Which requirement would this promise belong to?
A Applies to several areas: make it its own requirement.
B Test-driven build of planned sections: Building each planned section of a project into working code, checked against what that section was meant to do.
C Implementation planning with independent review: Turning requirements into a step-by-step plan, which independent outside reviewers then check before work starts.
D Somewhere new (tell us the name).
E It is not a promise, only how it is built.
F Not wanted: <your wording>
G I do not understand this, please explain.
```

Operator: clear / not clear (PENDING - on this new wording)

### Case 6: #897 owner is not in the catalog

Operator's verdict on the previous sheet: not clear: should become a new stack-profile requirement.

Agent's original wording: "A team can keep its own stack profile in its project and it is used instead of the shipped one"

Model wording (model anthropic/claude-haiku-5.5): "A team can keep its own ready-made set of technology choices, the starting point a project is built on, inside its project, and that set is used instead of the built-in one." - SHOWN (meaningfully different).

What the operator sees now:

```
This change adds a new promise: A team can keep its own stack profile in its project and it is used instead of the shipped one.
In plain words: A team can keep its own ready-made set of technology choices, the starting point a project is built on, inside its project, and that set is used instead of the built-in one.
Affects: Adopting an existing project, Design mockups, Requirements breakdown, Orchestrator, Test phase.
Already in the catalog: Project decomposition into scoped units.
Which requirement would this promise belong to?
A Applies to several areas: make it its own requirement.
B Project decomposition into scoped units: Splitting a project into smaller pieces that can each be delivered, including how its starting technology choices are picked.
C Somewhere new (tell us the name).
D It is not a promise, only how it is built.
E Not wanted: <your wording>
F I do not understand this, please explain.
```

Operator: clear / not clear (PENDING - on this new wording)

### Case 7: #919 two areas could own it

Operator's verdict on the previous sheet: not clear: should become a new stack-profile requirement.

Agent's original wording: "An app that is a chat window starts from a ready-made setup that needs no deployment"

Model wording (model anthropic/claude-haiku-5.5): "An app that is a chat window starts from a ready-made set of technology choices and needs no putting live on a hosting service." - SHOWN (meaningfully different).

What the operator sees now:

```
This change adds a new promise: An app that is a chat window starts from a ready-made setup that needs no deployment.
In plain words: An app that is a chat window starts from a ready-made set of technology choices and needs no putting live on a hosting service.
Affects: Adopting an existing project, Build phase, Requirements breakdown, Test phase.
Already in the catalog: End-to-end delivery pipeline.
Which requirement would this promise belong to?
A Applies to several areas: make it its own requirement.
B Project decomposition into scoped units: Works out which ready-made set of technology choices a project starts from, based on how it stores its data.
C Deployment and rollback: Covers sending a project live to a hosting service and undoing a release if it goes wrong.
D Somewhere new (tell us the name).
E It is not a promise, only how it is built.
F Not wanted: <your wording>
G I do not understand this, please explain.
```

Operator: clear / not clear (PENDING - on this new wording)

### Case 8: #866 no owner named

Operator's verdict on the previous sheet: not clear: "the command is typed" was not understood.

Agent's original wording: "A commit is checked for enough tested requirements at the moment it is recorded, however the command was typed"

Model wording: none, used the deterministic wording (fallback: negations or limits differ: original [], plain ['each', 'no']).

What the operator sees now:

```
This change adds a new promise: A commit is checked for enough tested requirements at the moment it is recorded, however the command was typed (commit: a saved snapshot of the work, kept in the project history; command: a typed instruction, such as /shipwright-iterate, that tells the tool to do one specific job).
Affects: Compliance evidence.
Which requirement would this promise belong to?
A Guided requirement elicitation: What exists is a requirement its author has confirmed and whose context is completely covered.
B Ongoing change at the depth it deserves: That change exists in the product.
C Mockups from requirements: Every one of them has at least one screen.
D Somewhere new (tell us the name).
E It is not a promise, only how it is built.
F Not wanted: <your wording>
G I do not understand this, please explain.
```

Operator: clear / not clear (PENDING - on this new wording)

### Case 9: #936 no owner named

Operator's verdict on the previous sheet: not clear: a horizontal promise (it applies across the design).

Agent's original wording: "Every colour set keeps text easy to read, also when the page is enlarged"

Model wording (model anthropic/claude-haiku-5.5): "Every colour scheme keeps text easy to read, also when the page is enlarged." - NOT shown (too close to the original).

What the operator sees now:

```
This change adds a new promise: Every colour set keeps text easy to read, also when the page is enlarged.
Affects: Design mockups.
Which requirement would this promise belong to?
A Mockups from requirements: Turns the product's requirements into screen designs, including the colours and text styles a build needs.
B Somewhere new (tell us the name).
C It is not a promise, only how it is built.
D Not wanted: <your wording>
E I do not understand this, please explain.
```

Operator: clear / not clear (PENDING - on this new wording)

### Case 10: #843 no owner named

Operator's verdict on the previous sheet: clear: the operator would pick B.

Agent's original wording: "The pull request gate is run by a different reviewer model, and what it checks stays the same"

Model wording (model anthropic/claude-haiku-5.5): "The check that decides whether a proposed change is accepted is now carried out by a different AI reviewer, and what that check looks for stays the same." - SHOWN (meaningfully different).

What the operator sees now:

```
This change adds a new promise: The pull request gate is run by a different reviewer model, and what it checks stays the same.
In plain words: The check that decides whether a proposed change is accepted is now carried out by a different AI reviewer, and what that check looks for stays the same.
Affects: Security checks.
Already in the catalog: Ongoing change at the depth it deserves; Independent re-check on the code host.
Which requirement would this promise belong to?
A Independent re-check on the code host: Re-checks each proposed change on the code host with tests and safety checks before it is added to the main version.
B Implementation planning with independent review: Has independent outside reviewers check each implementation plan before planning is considered finished.
C Somewhere new (tell us the name).
D It is not a promise, only how it is built.
E Not wanted: <your wording>
F I do not understand this, please explain.
```

Operator: clear / not clear (PENDING - on this new wording)

## (c) Ask rate: reported after the merge, never before

The ask rate on the first 20 iterates after the merge is a report only. Stop rule (the brief's): above 30 percent, or the operator rejects more than 3 of 10 sampled ACs. The counting producer is `lib/ac_decision.count_decisions` (buckets `auto`, `asked`, `exempt`, `restore`, `unchanged`, plus `exempt_share` and `restore_share`), recorded per run in `ac-record.jsonl`, so a rising exemption share is visible without a model. There is no automated aggregator across runs yet: the 20-run report will be made by a one-off script over the per-run records when the time comes (not built now).
