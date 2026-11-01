# ac-at-start Q1 measure: replay, question sheet, post-merge report

> Date 2026-11-01. Evidence for `2026-11-01-ac-at-start-BRIEF.md` unit Q1. Classifier output is AI-made (Opus), ground-truth labels are the brief's.

## (a) Replay of the 25 baseline PRs: RESULT, BAR FAILED (stopped, not tuned)

The brief's class lists name 25 PRs (12 demand, 6 only-how, 2 restore, 5 no-change), not 16, and 13 "other" PRs, not 11. The bar "flags at most 1 of the other cases" was applied as written.

**Method.** Earliest request text per PR (brief unit text, triage card, iterate spec or spec note; PR body only where nothing earlier exists, marked LEAKY): `Source` column below. Each case was an opaque id (C01 to C25, shuffled), with the request text and the catalog as it stood before the PR merged. The NEW rule is the outcome test with four classes (frozen text, sha256 prefix `a7bd2964041ea0a3`); the CONTROL is the current Step 2 text of the FEATURE and CHANGE paths plus the closed NONE reason codes (prefix `724471c5315a4119`). Classifier: Opus, read-only reviewer agent, blind to labels. No prompt was changed after the first result.

**Run state.** Only 3 of 10 classifier batches ran (NEW rule, C01 to C15). The runner's spawn guard allows a reviewer type three spawns per runner, and the other reviewer-type spawns are needed for the review cascade; the remaining batches (NEW C16 to C25, and all 25 CONTROL cases) were NOT run. They would not change the verdict below, because the "flags at most 1 of the other cases" bar is already lost on the 15 cases run. The comparison with the control ("beats the control by at least 3") is therefore NOT MEASURED.

| Case | PR | Source | Truth | NEW rule | Right |
|---|---|---|---|---|---|
| C01 | #884 | PR body LEAKY | demand_ac | demand_ac | yes |
| C02 | #919 | brief B4 | demand_ac | demand_ac | yes |
| C03 | #883 | triage card | demand_ac | demand_ac | yes |
| C04 | #869 | triage cards | demand_ac | demand_ac | yes |
| C05 | #900 | brief A2 | no_change | no_change | yes |
| C06 | #918 | brief B1 | only_how | only_how | yes |
| C07 | #924 | brief B3b | demand_ac | demand_ac | yes |
| C08 | #837 | brief U0 | demand_ac | demand_ac | yes |
| C09 | #866 | iterate spec | only_how | demand_ac | NO |
| C10 | #910 | PR body LEAKY | restore | demand_ac | NO |
| C11 | #855 | PR body LEAKY | no_change | no_change | yes |
| C12 | #921 | PR body LEAKY | only_how | demand_ac | NO |
| C13 | #936 | triage cards | only_how | demand_ac | NO |
| C14 | #886 | triage card | only_how | demand_ac | NO |
| C15 | #911 | triage card | no_change | no_change | yes |

**NEW rule on the 15 cases run:** 10 of 15 right.
- Demand cases (C01 to C04, C07, C08: 6 in this subset): 6 of 6 caught, 0 missed. Bar "misses at most 1 of 12": holds so far (6 of the 12 run).
- Other cases (9 in this subset): 4 right (C05, C06, C11, C15), **5 wrongly flagged as "demand an AC"** (C09 #866, C10 #910, C12 #921, C13 #936, C14 #886). Bar "flags at most 1 of the other cases": **FAILED**.

**Why it fails (not tuned, recorded).**
- Four of the five false flags are labelled "only how" and one "restore with a named AC". The classifier called each a real change in what a user or operator can rely on (git now refuses a commit; Windows browser checks work; new design-kit components; a promotion PR no longer leaves CI red). For #910 the catalog holds no AC that states the promise, so under the brief's own rule ("if no AC names it, it is a catalog gap") the correct answer is "demand an AC", not "restore". The label "restore with a named AC" does not hold against the catalog as it stood.
- Only-how and demand are separated by the operator's judgement of what counts as a promise. A text-only outcome test cannot reproduce that judgement; this is also why the table asks the operator for a how-only exemption instead of letting the agent decide it.
- Leaky inputs (PR body, marked above) were used for #884, #910, #855, #921, #908, #848; a leaky body usually describes the built behaviour, which pushes toward "demand".
- Consequence for the campaign: per the brief a failed measure stops for the operator. Q2 depends on Q1 (a) and (b).

## (b) Question sheet for the operator: PENDING

Ten recorded cases, the question exactly as the tool prints it. The operator marks each "clear" or "not clear"; the bar (10 of 10 clear) is NOT claimed.

### Case 1 (#839, table row 1)

```
This change gives the product a new promise: A commit is held back when too few requirements are covered by passing tests. Until now: A commit is held back when the build progress line shows less than the required share of work done. Should it hold like this?
1 Yes, write it.
2 No, instead: <your wording>
3 This is only how it is built, not a promise.
```

Operator: clear / not clear (PENDING)

### Case 2 (#887, table row 1)

```
This change removes a promise. Until now this held: Adopting a project sets up the automatic Claude review on every pull request. After this change it no longer holds.
1 Yes, that is intended.
2 No, instead: <your wording>
3 This is only how it is built, not a promise.
```

Operator: clear / not clear (PENDING)

### Case 3 (#869, table row 2)

```
This change gives the product a new promise: A coordinator repeats a review unless the earlier one is shown to cover exactly the code that is merged. Until now: nothing. Should it hold like this?
1 Yes, write it.
2 No, instead: <your wording>
3 This is only how it is built, not a promise.
```

Operator: clear / not clear (PENDING)

### Case 4 (#884, table row 4)

```
This change gives the product a new promise: The build phase asks outside reviewers to read the code of each section unless the owner turns this off. Until now: nothing. Should it hold like this?
1 Yes, write it.
2 No, instead: <your wording>
3 This is only how it is built, not a promise.
```

Operator: clear / not clear (PENDING)

### Case 5 (#897, table row 3)

```
This change gives the product a new promise: A team can keep its own stack profile in its project and it is used instead of the shipped one. Until now: nothing. Should it hold like this?
1 Yes, write it.
2 No, instead: <your wording>
3 This is only how it is built, not a promise.
```

Operator: clear / not clear (PENDING)

### Case 6 (#919, table row 4)

```
This change gives the product a new promise: An app that is a chat window starts from a ready-made setup that needs no deployment. Until now: nothing. Should it hold like this?
1 Yes, write it.
2 No, instead: <your wording>
3 This is only how it is built, not a promise.
```

Operator: clear / not clear (PENDING)

### Case 7 (#923, table row 1)

```
This change gives the product a new promise: A stack profile named in the project brief is used as given, and an unusable name stops the run with a clear message. Until now: The stack profile is guessed from the kind of storage the project uses. Should it hold like this?
1 Yes, write it.
2 No, instead: <your wording>
3 This is only how it is built, not a promise.
```

Operator: clear / not clear (PENDING)

### Case 8 (#843, table row exempt)

```
This change does not add a promise. The agent says it is only how the product works: The pull request gate is run by a different reviewer model, and what it checks stays the same. Do you agree?
1 Yes, it is only how it is built.
2 No, instead: <your wording>
3 This is only how it is built, not a promise.
```

Operator: clear / not clear (PENDING)

### Case 9 (#936, table row 3)

```
This change gives the product a new promise: Every colour set keeps text easy to read, also when the page is enlarged. Until now: nothing. Should it hold like this?
1 Yes, write it.
2 No, instead: <your wording>
3 This is only how it is built, not a promise.
```

Operator: clear / not clear (PENDING)

### Case 10 (#866, table row 4)

```
This change gives the product a new promise: A commit is checked for enough tested requirements at the moment it is recorded, however the command was typed. Until now: nothing. Should it hold like this?
1 Yes, write it.
2 No, instead: <your wording>
3 This is only how it is built, not a promise.
```

Operator: clear / not clear (PENDING)


## (c) After the merge, report only

Ask rate on the first 20 iterates that run with this rule (stop rule: above 30 percent asked, or the operator rejects more than 3 of 10 sampled ACs), plus the counts of `ac_decisions` mode `asked` and of each exemption kind. Also reported then: how often the AC47 warning fires and how often "how, not what" is used, to decide whether AC47 and AC48 fold into the pre-build declaration. Not measured in this PR.
