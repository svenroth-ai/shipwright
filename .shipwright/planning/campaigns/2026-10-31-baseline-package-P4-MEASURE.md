# Baseline package P4 (independent AI gap check): measure

Date: 2026-10-31 · unit P4 of `2026-10-31-baseline-package-BRIEF.md` · run `iterate-2026-10-31-p4-ai-gap-check` · every number below was produced by `shared/scripts/tools/ai_gap_check_replay.py` on this branch with a non-Claude model (GPT, through the external-review OpenRouter route). The model never saw a label. The ground-truth labels are the Opus labels of `2026-10-31-baseline-package-REPLAY2.md`, so they are AI-made too; the operator has checked 10 of 10 of the older BL0b labels, not these.

## Verdict, plainly

| Bar (from the brief) | Final prompt (v2), run 1 | v2 repeated (run 2) | Earlier prompt (v1) |
|---|---|---|---|
| Flags at least 6 of the 7 known misses | 6 of 7 | 7 of 7 | 7 of 7 |
| Flags 0 of the 5 no-change PRs | 0 of 5 | 0 of 5 | 1 of 5 |
| Disagrees on at most 25% of the 35 PRs, read as **the check's verdict differs from the label truth** (see 'Disagreement, two readings') | 8 of 34 = 24% | 7 of 34 = 21% | 5 of 34 = 15% |
| Same bar, read as **the check disagrees with the author's declaration** (REPLAY2's own 34% figure was this) | 22 of 35 = 63% | 23 of 35 = 66% | 25 of 35 = 71% |
| The operator agrees on a fresh set of 10 | **pending** (sheet below) | | |

Reading, honestly:

- Known misses and no-change controls: met by v2 in both runs *except* that #843 flips between runs (missed in run 1, flagged in run 2), so "6 of 7" is the floor and "7 of 7" the ceiling for this check, not a stable number. The no-change controls came out 0 of 5 in both v2 runs.
- The 25% bar depends on the reading. Read as an error rate against the labels it is met (24% and 21%), narrowly and on a 34-PR sample with one labeler-split PR left out. Read as how often the check disagrees with the author it is far above 25% (63% to 66%), because the labels themselves say the author's declaration was wrong on about 19 of 35 PRs (16 NEW plus 3 CHANGE): no check that finds those can disagree on only a quarter of them. The brief's wording ("disagrees on at most 25%") and the REPLAY2 table (12 of 35 = 34%, check against author) point at the second reading; the unit's instruction here (check's verdict against the label ground truth) at the first. Both are reported; the operator decides which one the campaign bar means.
- The operator bar is **not met and not claimed**: it is open until the operator answers the sheet at the end.
- Where the error comes from (v2, label-truth reading): the check disagrees on PRs the labelers call "fix that restores a promise" (#910, #914, #933, #934, #935 in run 1) and sometimes agrees with a declared "none" that the labelers call new behaviour (#843, #866, #918). The two #910/#914 cases are known misses the brief *wants* flagged, so the label truth and the brief's own list pull in opposite directions there.

## Method

- **Input per PR** (blind): the PR's full diff against its merge-base (`git diff <merge>^1 <merge>`; for a squash merge that is the whole PR), with finalization records dropped (the event log, test ledger, changelog drops, decision drops and review scratch under the run directory: they describe the change, they are not the change; 6 to 18 files per PR) and files cut whole only past 400,000 characters; the catalog = every FR's acceptance criteria as they stood just before the merge; the declaration = the iterate `work_completed` event the PR itself added to the event log (description, summary, `spec_impact` and its reason, affected FRs, and `affected_acs` / `catalog_gap` where the PR had them). **No label, verdict or known-miss list was passed.**
- **Reconstructed declaration.** The 35 PRs predate P1, so none carried `affected_acs`. The declaration is the recorded event as it was; all 35 PRs added an event; of the 10 fresh PRs one (#814) added none, and its declaration was then empty (the check is told "no declaration was recorded").
- **Model:** `openai/gpt-6.1-sol` through OpenRouter (`external_review.review_with_openrouter`, the same function the plan and code reviews use: identity-pinned model, retry rule, key check). Single call per PR; no tools; reply is one JSON object.
- **Sample:** the 35 BL0b PRs: the 7 known misses, the 5 no-change controls and 23 others (#837 #839 #842 #859 #866 #871 #883 #886 #891 #892 #897 #913 #918 #919 #920 #923 #924 #925 #933 #934 #935 #936 #937). The list is reconstructed from the REPLAY2 table and its `scores.json`; the BL0b archive is outside this repository.

## Prompt revision history

1. **v1** (first run). The system prompt in `shared/scripts/lib/ai_gap_check_core.py` before the revision: the role, the two things to look for (wrong "none"; catalog gap), and these rules: judge by observable behaviour; a change that touches behaviour an existing AC covers (including a fix that restores it) belongs to that requirement and the declaration should name it; do not hunt for ACs that became untrue unless the diff plainly contradicts one; the diff is the only evidence; cite AC ids exactly. Result: 7 of 7 misses, **1 of 5 controls flagged (#848**, a change to the repository's dependency-update bot settings and a CI security-scan exclusion).
2. **v2** (the one allowed revision, made after v1 and **based on that false positive only**, not on the other labels): one rule added. "Upkeep of the product's own repository (its CI settings, dependency-update bots, its test suite, its internal records) is not behaviour of the product unless it changes what the product does for the people who use it." Nothing else changed. v2 was then run twice on all 35 (same prompt) to show run-to-run variation. The PR set, model, catalog reconstruction and declarations were identical across all three runs.

Caveat on 'not tuned to the labels': the revision is a general scoping rule, but it was chosen *because* #848 is one of the five named controls, so v2's 0 of 5 is partly by construction. The v1 row is kept so that is visible.

## Per-PR results

`label` = what both Opus labelers (X, Y) said in REPLAY2: NEW (new behaviour no AC describes), CHANGE (an existing AC made untrue), IMPL (implements or restores a promise), NONE. `decl` = what the author recorded. `S` = REPLAY2's Sonnet verdict (for reference). Miss = one of the 7 known misses, ctrl = one of the 5 controls.

| PR | set | label | decl spec_impact | v1 | v2 run 1 | v2 run 2 | S (Sonnet) | v2-run-1 reason, shortened |
|---|---|---|---|---|---|---|---|---|
| #837 |  | NEW | none | disagree | disagree | disagree | agree | This changes operator-visible behaviour: malformed exemption records can block finishing, and delivery summaries must show exemption counts. No existi... |
| #839 |  | NEW | none | disagree | disagree | disagree | agree | The change alters when commits are stopped, adds a configurable coverage baseline, and warns when coverage cannot be measured, so declaring no specifi... |
| #842 |  | NEW | none | disagree | disagree | disagree | agree | This changes when operators can finish a small change, so declaring no specification impact is incorrect. No existing criterion defines the risk-or-mo... |
| #843 | miss | NEW | none | disagree | agree | disagree | agree | The change switches the model used by the project's own automated pull-request review tooling. This is repository upkeep, with no demonstrated change ... |
| #848 | ctrl | NONE | none | disagree | agree | agree | agree | The change activates dependency-update proposals and tightens a security check only for the product's own repository, with related test and record u... |
| #855 | ctrl | NONE | none | agree | agree | agree | agree | The diff only relaxes version expectations in the repository's own tests and adds requirement labels to those tests. It does not change what the produ... |
| #859 |  | IMPLEMENT_RESTORE/NEW | none | disagree | disagree | disagree | disagree | The shipped safety hook changes which user commands are allowed, including keeping protection active when its interpreter is unavailable, so this is n... |
| #866 |  | NEW | none | disagree | agree | agree | agree | The added check governs commits to the product's own repository and is not installed for projects that use the product. This is repository upkeep rath... |
| #869 | miss | NEW | none | disagree | disagree | disagree | disagree | This changes the product's campaign review behavior, including honoring the chosen reviewer model and preserving review replies, so declaring no requi... |
| #871 |  | IMPLEMENT_RESTORE | modify | agree | agree | agree | agree | The declaration correctly identifies the autonomous stop protection and adds a criterion under the right requirement. The supplied catalog has no exis... |
| #883 |  | NEW | none | disagree | disagree | disagree | disagree | The profile-aware fixes fit the named requirements, but refusing previews for non-web projects narrows the existing preview promise and needs an expli... |
| #884 | miss | NEW | none | disagree | disagree | disagree | disagree | Build now requests an outside code review by default unless the operator switches it off, changing when project code is sent to an outside provider. T... |
| #886 |  | NEW | none | disagree | disagree | disagree | disagree | The change prevents automatic promotion of test obligations for adopted requirements and reports a named skip instead, which operators can observe. No... |
| #887 | miss | CHANGE | none | disagree | disagree | disagree | disagree | Onboarding now stops providing automatic review on the code host, which is an observable product change, not internal repository upkeep. FR-01.17.AC03... |
| #891 |  | IMPLEMENT_RESTORE | none | agree | agree | agree | agree | The change stops reporting superseded cancelled checks as failures. The declaration names the existing requirement covering actionable imports and cor... |
| #892 |  | IMPLEMENT_RESTORE | none | agree | agree | agree | disagree | The change restores the existing worktree protection for adopted projects and aligns their eligibility for the change workflow. The declaration names ... |
| #897 |  | NEW | none | disagree | disagree | disagree | agree | Operators can now list, resolve and validate stack profiles, with project-over-home-over-bundled priority and explicit errors for broken profiles. The... |
| #900 | ctrl | NONE | none | agree | agree | agree | agree | The diff reorganizes existing logic without changing user-visible decisions, results, or workflows. The added tests, documentation updates, and reposi... |
| #908 | ctrl | NONE | none | agree | agree | agree | agree | The change strengthens the product's own test guards, isolates test environments, and updates internal records and comments. It does not change behavi... |
| #910 | miss | IMPLEMENT_RESTORE | none | disagree | disagree | disagree | disagree | The change makes project setup save its settings where later commands and completion checks can find them, so it is an observable fix rather than an u... |
| #911 | ctrl | NONE | none | agree | agree | agree | agree | The diff only initializes a local variable before the existing retry loop; it does not change the loop or how its result is used. No observable behavi... |
| #913 |  | IMPLEMENT_RESTORE | none | agree | agree | agree | agree | The change restores completion of the pipeline under the requirement the author named, and keeps the displayed run status consistent. The declaration ... |
| #914 | miss | IMPLEMENT_RESTORE | none | disagree | disagree | disagree | disagree | The fix changes evidence readers see: parameterized tests with brackets in their values are now recognized as executed rather than not run. This resto... |
| #918 |  | NEW | none | disagree | agree | agree | agree | The diff declares optional settings and checks their types, but shows no change to how the product uses profiles. The documentation and tests do not e... |
| #919 |  | NEW | none | disagree | disagree | disagree | disagree | This adds a usable built-in stack and changes how its projects are created, tested and previewed, so declaring no behavioural impact is incorrect. Exi... |
| #920 |  | CHANGE | none | disagree | disagree | disagree | disagree | This adds a user-visible package intake mode and replaces the project interview, so declaring no specification impact is incorrect even though two req... |
| #921 | miss | NEW | none | disagree | disagree | disagree | disagree | The change repairs user-visible browser testing on Windows and changes which application address verification uses. Existing criteria cover these capa... |
| #923 |  | NEW | none | disagree | disagree | disagree | agree | The change lets a brief's named stack profile override the automatic choice and stops intake when that name cannot be used, so it is not behavior-pres... |
| #924 |  | NEW | none | disagree | disagree | disagree | agree | Naming the design requirement is appropriate, but claiming no impact is not: the change adds chat journey mockups and new reasons to refuse a design. ... |
| #925 |  | CHANGE | none | disagree | disagree | disagree | agree | Although the declaration names the right requirement, this is not behaviour-preserving: projects using an approved Brief package now face a blocking s... |
| #933 |  | IMPLEMENT_RESTORE | none | disagree | disagree | disagree | agree | The completion check now recognises archived finished sections, and the audit no longer counts unrelated sections toward a decision's size. These chan... |
| #934 |  | IMPLEMENT_RESTORE | none | agree | disagree | disagree | agree | The declaration names the restored capabilities, but misses a catalog gap: installed security scans can now refresh compliance reports automatically. ... |
| #935 |  | IMPLEMENT_RESTORE | none | disagree | disagree | disagree | agree | The change alters release behaviour by stopping after a recording failure and withholding the main-branch push until the version tag is pushed. FR-01.... |
| #936 |  | NEW | none | disagree | disagree | disagree | agree | The change alters the appearance and accessibility of generated mockups, so declaring no behavioural impact is inaccurate even though FR-01.04 is name... |
| #937 |  | IMPLEMENT_RESTORE | none | agree | agree | agree | agree | The change restores the existing version-number rule, and the declaration explicitly names the requirement it repairs. No new acceptance criterion is ... |

## Disagreement, two readings

- **Label-truth reading** (the unit text): expected verdict is `disagree` when both labelers said NEW or CHANGE (the author's account is incomplete), `agree` when both said IMPL or NONE; #859 (labelers split) is left out, leaving 34 PRs. Mismatches v2 run 1: #843, #866, #910, #914, #918, #933, #934, #935. Run 2: #866, #910, #914, #918, #933, #934, #935. v1: #848, #910, #914, #933, #935.
- **Declaration reading** (REPLAY2's number): the share of PRs on which the check's verdict is `disagree`. Sonnet in REPLAY2: 12 of 35 = 34%. GPT here is far stricter (63% to 71%) and also more right on the labels than Sonnet was: it flags the NEW PRs Sonnet let through (for example #837 #839 #842 #897 #923 #924 #925 #936).
- Mixed ground truth: the labels call #910 and #914 'IMPL', yet the brief lists them as known misses to be flagged. Under the label-truth reading flagging them counts as a mismatch, under the known-misses bar it counts as a hit. Both are shown.

## Other facts

- No call failed; 0 of 105 calls ended `not_run` in the 3 x 35 replay, 0 of 10 in the fresh set. One PR (#936, a design-kit PR) exceeded the 400,000-character cap and had 6 whole files (kit CSS, reference docs, a test) cut; the check still ran on the rest.
- The older Sonnet replay named an AC as untrue for only 1 of 3 real contradictions. This check is framed as a gap check and was not scored on 'AC untrue'; it did list `requirements_changed` ACs in some replies, which were not graded.
- Cost: each call sends the whole catalog (about 100,000 characters) plus the trimmed diff; 35 calls took about one minute with 4 in parallel.
- Limits: one model, single calls (no majority vote), AI-made labels, a 35-PR sample enriched for misses (so the 'disagree' share is not a rate over normal PRs), declarations rebuilt from the event log.

## Fresh set of 10 for the operator (pending)

Drawn with seed 20261031 from the recent merged iterate PRs (head branch `iterate/*`, last 150 merged PRs) that are not among the 35 (pool of 96); the check ran with the final prompt (v2). **Status: pending. The operator answers later; the bar "the operator agrees on a fresh set of 10" is not claimed.** For each: does the check's verdict look right to you?

**1. PR #814** - fix(main): use malformed TOML for the uv-project-isolation negative control
- What changed, as the author recorded it: (no completion record was found in the PR; read the title)
- The check says: **agree** with the author's account; sees no uncovered behaviour. Reason: The diff only updates an internal test to accommodate different versions of its supporting tool. It changes no behaviour for product users or operators, so no requirement impact needs to be named.
- Your answer (agree / disagree with the check): _pending_

**2. PR #818** - fix(compliance): make audit D5 advisory so FR-01.10/AC06 holds
- What changed, as the author recorded it: The compliance audit now flags a change with no requirement link and suggests a fix, but no longer marks the whole audit as failed.
- The check says: **disagree** with the author's account; sees no uncovered behaviour. Reason: The declaration correctly identifies the advisory audit fix, but misses its effect on triage. Making the finding advisory also removes it from the triage card, contrary to the promise that every audit finding is available in the Triage Inbox.
- Your answer (agree / disagree with the check): _pending_

**3. PR #836** - docs(planning): campaign brief to make finalization enforce its documented claims
- What changed, as the author recorded it: (no completion record was found in the PR; read the title)
- The check says: **agree** with the author's account; sees no uncovered behaviour. Reason: The change adds planning documents describing proposed hardening work, but does not implement new gates or alter product behaviour. Declaring no catalog impact is appropriate for this diff.
- Your answer (agree / disagree with the check): _pending_

**4. PR #844** - feat(finalization): an external review that could not run is proven, announced and queued for a re-run
- What changed, as the author recorded it: When an automatic run cannot get its outside code review, it may carry on, but only with proof the reviewer failed, a visible note in the pull request and the run summary, and one reminder card to re-run the review.
- The check says: **disagree** with the author's account; sees behaviour no criterion describes. Reason: Naming FR-01.11 is appropriate, but declaring no impact misses new operator-visible rules. Existing criteria require recording missed reviews and their reasons, but do not describe requiring captured failure evidence, announcing missed reviews in the delivery request and run summary, or creating a re-run reminder.
- Your answer (agree / disagree with the check): _pending_

**5. PR #845** - feat(finalization): the requirement record is enforced on every iterate path
- What changed, as the author recorded it: Finishing a change now checks its requirement record properly: fixes are no longer exempt, a 'no requirement touched' answer needs a reason from a fixed list, and a change that calls itself documentation or tooling is checked against the files it actually changed.
- The check says: **agree** with the author's account; sees no uncovered behaviour. Reason: The declaration correctly identifies the change-workflow requirement. The diff updates its criteria to cover fixes, fixed-list reasons, checks against the actual changes, and refusal when requirement references cannot be verified.
- Your answer (agree / disagree with the check): _pending_

**6. PR #863** - fix(compliance): collector and gate share one TS lexer; trees scanned without git archive
- What changed, as the author recorded it: (no completion record was found in the PR; read the title)
- The check says: **agree** with the author's account; sees no uncovered behaviour. Reason: The change closes ways that added or edited tests could escape the requirement-tag check, which belongs to the declared requirement. The existing criteria cover this behavior, and the clarification makes the newly handled cases explicit.
- Your answer (agree / disagree with the check): _pending_

**7. PR #879** - fix(triage): raise one card per critical/high security finding and re-raise returning ones
- What changed, as the author recorded it: Open high-severity security findings now show up in the Triage one by one, and show up again if they come back.
- The check says: **disagree** with the author's account; sees behaviour no criterion describes. Reason: This is not only a restoration: separate finding cards and their stored details change existing promises about grouping and permitted content. No criterion describes bypassing the import waiting period when a newer security scan becomes available.
- Your answer (agree / disagree with the check): _pending_

**8. PR #905** - feat(profiles): custom stack profiles in the interview, docs, python guard and end-to-end test (campaign S5)
- What changed, as the author recorded it: You can now pick your own stack description in the project interview, the docs explain how to write one, and tests prove every command uses it from a fresh checkout.
- The check says: **disagree** with the author's account; sees behaviour no criterion describes. Reason: The change adds an interview choice for custom stack descriptions and changes how setup finds and validates them, so it is not behavior-preserving or confined to testing. No existing acceptance criterion describes offering those choices or stopping when an explicit choice is unusable.
- Your answer (agree / disagree with the check): _pending_

**9. PR #915** - fix(layer-promotion): skip the advisory adopted spec before escalating on ambiguous evidence
- What changed, as the author recorded it: A requirement in the adopted spec, which is never promoted anyway, no longer raises a recurring 'operator decision needed' warning.
- The check says: **disagree** with the author's account; sees behaviour no criterion describes. Reason: Advisory requirements with ambiguous test evidence now skip promotion instead of asking for an operator decision, which is an observable change. No existing acceptance criterion describes this exception, so declaring no impact misses a catalog gap.
- Your answer (agree / disagree with the check): _pending_

**10. PR #960** - refactor(catalog): tidy mixed ACs and rename command-named FR titles (baseline-package P5)
- What changed, as the author recorded it: Requirements now state what the product promises without naming today's tools, and thirteen requirement titles name a capability instead of a command.
- The check says: **agree** with the author's account; sees no uncovered behaviour. Reason: The diff edits requirement wording and titles and adjusts internal ownership bookkeeping and tests. It does not change how the product behaves for users or operators, so declaring no behavioral impact is appropriate.
- Your answer (agree / disagree with the check): _pending_


## Review dispositions that changed the build, and the operator stop

- Both external plan reviewers and one external code review asked for: a stricter reply check (done: an incomplete reply is a not_run), the size cap on every file including the first (done), inert rendering of the not-run note (done), and the replay reader test (done).
- The internal plan review added: honour the project opt-outs for external review and code review and a gateway-only route (done: the check records not_run), use GLM, never a GPT-family model, when the change was written under Codex (done: --driver), keep secret-shaped untracked files off the wire (done), drop the check own earlier record from its input (done). Rejected with reason: a prompt-injection rule in the prompt (the measured prompt must equal the shipped prompt; the verdict is advisory and its text is rendered inert); sending only the owning FRs ACs (a wrong none names no owning FR, so the whole catalog is sent, recorded in the F5b text).
- **Operator stop.** The campaign rule (brief sections 2 and 5) stops for the operator when a bar is not met. Two items are open and the unit does not claim them: (1) the fresh-10 sheet above; (2) which reading of the 25 percent bar the campaign means (label-truth reading met at 21 to 24 percent, declaration reading 63 to 66 percent). The unit result is therefore reported as escalated, waiting for the operator, with all code delivered and the branch pushed.
- Re-measure trigger (architecture reviewers): re-run `ai_gap_check_replay.py` over the 7 + 5 sets whenever the pinned review model changes.
