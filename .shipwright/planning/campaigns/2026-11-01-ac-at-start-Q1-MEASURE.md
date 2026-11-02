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

## (b) Question sheet for the operator: PENDING

Ten cases, each question exactly as the tool prints it now. Cases 1 and 2 are changed ACs, case 3 a removed AC; these stay as they were. Cases 4 to 10 are a new promise with no single owning area: a short lettered pick list in everyday words (never "feature", "FR" or an id; the ids stay in the machine record). **For these seven, a small model now does the semantic part**: it picks up to three areas by meaning and writes a plain one-sentence wording and a one-line description per area. **Code checks every output** before it is shown (the area ids exist in the catalog, no duplicates, at most three, the wording reads as an outcome and is short, and every number, limit and "not / never / unless / only / at most / at least / no" of the agent's wording is still there); on any failure the deterministic wording and candidates are used instead.

**Live run (the only live use):** model `anthropic/claude-haiku-5.5` (the cheap model the PR review already uses, through the existing OpenRouter transport), 7 calls (one per case, each a short prompt of the promise plus the catalog's areas), the real agent-recorded wording of each case, not a hand-rewritten one. Cost: 7 short calls on a small model, a few cents at most (not metered here). **Validation: 7 of 7 passed, 0 fell back.** Each case below shows the agent's original wording, the plain wording the model produced, and exactly what the operator would see. The model's text is a display aid only: the agent's original wording is what is frozen as the AC and stays in the record and the PR body next to the plain version (with the model id and the prompt sha).

Reading the result honestly:

- The plain wordings keep every number and condition (the code checks this). How plain they get varies: case 10 is clearly better ("pull request gate" became "the check that reviews each proposed code change"), case 5 swaps "phase" for "building step", but cases 4 and 7 stay close to the original and still use words such as "coordinator", "code", "merged" and "deployment" (case 10 still says "AI reviewer model"). The model does not remove all jargon; the prompt asks for it and the code cannot enforce it beyond code-shaped wording.
- The suggested areas are from this repository's catalog at `origin/main` and are only as good as the model's reading of it. The area descriptions can sound generic (case 6 offers "Project decomposition" and "Onboarding an existing codebase" for a promise about a team's own technology setup; the area that really owns it was not in this replay's catalog, because the stack-profile area is reconstructed from the recorded cases rather than present with a title). The operator can always pick "Somewhere new".
- The "until now" texts in cases 1 to 3 are reconstructed from the recorded cases, not copied from the catalog. The operator marks each "clear" or "not clear"; the bar (10 of 10 clear) is NOT claimed.

### Case 1: #839 an existing promise is changed

What the operator sees:

```
This change alters a promise the product makes. Until now: A commit is held back when the build progress line shows less than the required share of work done. After this change: A commit is held back when too few requirements are covered by passing tests. Should it hold like this?
1 Yes, change it.
2 No, instead: <your wording>
```

Operator: clear / not clear (PENDING)

### Case 2: #923 an existing promise is changed

What the operator sees:

```
This change alters a promise the product makes. Until now: The stack profile is guessed from the kind of storage the project uses. After this change: A stack profile named in the project brief is used as given, and an unusable name stops the run with a clear message. Should it hold like this?
1 Yes, change it.
2 No, instead: <your wording>
```

Operator: clear / not clear (PENDING)

### Case 3: #887 an existing promise is removed

What the operator sees:

```
This change removes a promise. Until now this held: Adopting a project sets up the automatic Claude review on every pull request. After this change it no longer holds.
1 Yes, that is intended.
2 No, keep the promise (the change is then reworked).
```

Operator: clear / not clear (PENDING)

### Case 4: #869 no owner named

Agent's original wording: "A coordinator repeats a review unless the earlier one is shown to cover exactly the code that is merged"

Plain wording shown (model anthropic/claude-haiku-5.5): "The coordinator runs a review again unless the earlier review is shown to cover exactly the code that is merged."

What the operator sees:

```
This change adds a new promise: The coordinator runs a review again unless the earlier review is shown to cover exactly the code that is merged. Where does it belong?
A Independent re-check on the code host: Re-checks a proposed change on the code host before it can be merged, so nothing slips in unchecked.
B Recovery of a broken shared branch: Finds which earlier change broke the shared code line when several changes land close together.
C Somewhere new (tell us the name).
D It is not a promise, only how it is built.
E Not wanted: <your wording>
```

Operator: clear / not clear (PENDING)

### Case 5: #884 no owner named

Agent's original wording: "The build phase asks outside reviewers to read the code of each section unless the owner turns this off"

Plain wording shown (model anthropic/claude-haiku-5.5): "The building step asks outside reviewers to read the code of each section, unless the project owner switches this off."

What the operator sees:

```
This change adds a new promise: The building step asks outside reviewers to read the code of each section, unless the project owner switches this off. Where does it belong?
A Test-driven build of planned sections: Building the planned sections of a project so that each one does what its written plan requires.
B Implementation planning with independent review: Turning requirements into a step-by-step plan that outside reviewers check before work begins.
C End-to-end delivery pipeline: Running a change through its fixed sequence of steps from start to finish, pausing when a step fails its checks.
D Somewhere new (tell us the name).
E It is not a promise, only how it is built.
F Not wanted: <your wording>
```

Operator: clear / not clear (PENDING)

### Case 6: #897 owner is not in the catalog

Agent's original wording: "A team can keep its own stack profile in its project and it is used instead of the shipped one"

Plain wording shown (model anthropic/claude-haiku-5.5): "A team can keep its own technology setup inside its project, and the product uses that setup in place of the default one that comes with it."

What the operator sees:

```
This change adds a new promise: A team can keep its own technology setup inside its project, and the product uses that setup in place of the default one that comes with it. Where does it belong?
A Project decomposition into scoped units: Splitting a project into scoped pieces of work, including guessing its technology setup from how it stores data.
B Onboarding an existing codebase: Bringing an existing codebase under the product's change process, including reading the technology it already uses.
C Somewhere new (tell us the name).
D It is not a promise, only how it is built.
E Not wanted: <your wording>
```

Operator: clear / not clear (PENDING)

### Case 7: #919 two areas could own it

Agent's original wording: "An app that is a chat window starts from a ready-made setup that needs no deployment"

Plain wording shown (model anthropic/claude-haiku-5.5): "A chat-window app starts from a ready-made setup and needs no deployment."

What the operator sees:

```
This change adds a new promise: A chat-window app starts from a ready-made setup and needs no deployment. Where does it belong?
A Project decomposition into scoped units: Breaking a project into smaller parts and working out which technologies it needs before setup is finished.
B Deployment and rollback: Putting a finished project onto a hosting target, and reverting a release when something goes wrong.
C Local project preview: Running a project on this machine so the person can preview it before anything is deployed.
D Somewhere new (tell us the name).
E It is not a promise, only how it is built.
F Not wanted: <your wording>
```

Operator: clear / not clear (PENDING)

### Case 8: #866 no owner named

Agent's original wording: "A commit is checked for enough tested requirements at the moment it is recorded, however the command was typed"

Plain wording shown (model anthropic/claude-haiku-5.5): "Each time a saved change is recorded, the system checks that enough of its requirements have been tested, no matter how the recording was requested."

What the operator sees:

```
This change adds a new promise: Each time a saved change is recorded, the system checks that enough of its requirements have been tested, no matter how the recording was requested. Where does it belong?
A Independent re-check on the code host: Re-checks a proposed change on the code host, with tests, lint and security checks, before it can join the shared code.
B End-to-end delivery pipeline: Runs a described change through its fixed sequence of steps, with each step required to pass its own checks.
C Multi-level project testing: Runs the project's tests at every level it has and records what passed, failed or was not run.
D Somewhere new (tell us the name).
E It is not a promise, only how it is built.
F Not wanted: <your wording>
```

Operator: clear / not clear (PENDING)

### Case 9: #936 no owner named

Agent's original wording: "Every colour set keeps text easy to read, also when the page is enlarged"

Plain wording shown (model anthropic/claude-haiku-5.5): "Every set of colours keeps text easy to read, including when the page is enlarged."

What the operator sees:

```
This change adds a new promise: Every set of colours keeps text easy to read, including when the page is enlarged. Where does it belong?
A Mockups from requirements: Turns requirements into screen designs, including the colours and text styles the build needs.
B Somewhere new (tell us the name).
C It is not a promise, only how it is built.
D Not wanted: <your wording>
```

Operator: clear / not clear (PENDING)

### Case 10: #843 no owner named

Agent's original wording: "The pull request gate is run by a different reviewer model, and what it checks stays the same"

Plain wording shown (model anthropic/claude-haiku-5.5): "The check that reviews each proposed code change before it is accepted is run by a different AI reviewer model, and what that check looks for stays the same."

What the operator sees:

```
This change adds a new promise: The check that reviews each proposed code change before it is accepted is run by a different AI reviewer model, and what that check looks for stays the same. Where does it belong?
A Independent re-check on the code host: Re-checks each proposed code change on the code hosting site, and blocks the change until every check passes.
B Implementation planning with independent review: Has outside reviewers check implementation plans, and says so plainly when those reviewers cannot be reached.
C Somewhere new (tell us the name).
D It is not a promise, only how it is built.
E Not wanted: <your wording>
```

Operator: clear / not clear (PENDING)

## (c) Ask rate: reported after the merge, never before

The ask rate on the first 20 iterates after the merge is a report only. Stop rule (the brief's): above 30 percent, or the operator rejects more than 3 of 10 sampled ACs. The counting producer is `lib/ac_decision.count_decisions` (buckets `auto`, `asked`, `exempt`, `restore`, `unchanged`, plus `exempt_share` and `restore_share`), recorded per run in `ac-record.jsonl`, so a rising exemption share is visible without a model. There is no automated aggregator across runs yet: the 20-run report will be made by a one-off script over the per-run records when the time comes (not built now).
