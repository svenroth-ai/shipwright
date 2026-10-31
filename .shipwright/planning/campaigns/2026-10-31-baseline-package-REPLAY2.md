# Replay 2: sharper labels, AC-check (O5) and AC candidates (O2) on the 35 BL0b PRs

> **Note 2026-10-31:** evidence for `2026-10-31-baseline-package-BRIEF.md` (section 1); every label and judgement in it is AI-made (Opus labelers, Sonnet check), not human-verified beyond the operator's 10-card sample. Paths such as `runs/`, `raw/`, `inputs/` and `OPERATOR_10.md` refer to the local measurement archive, not to this repository.

**Date:** 2026-10-29 · read-only measurement, nothing in the repo changed · inputs: `runs/BL0b/labels/` packs + FR_CATALOG, `shipwright_events.jsonl` (declarations), and the iterate planning docs at each PR's merge commit (for O2 goals)

## Summary (plain language)

1. **O5 bar "flags at least 6 of the 7 known misses": met (6 of 7).** Only #843, the PR-review model swap, was not flagged. The new labelers also say no promise mentions a model, so that miss is arguably correct.
2. **O5 bar "flags 0 of the 5 no-change PRs": met (0 of 5).** The operator's check (8 of 10 agree) is still open: see `OPERATOR_10.md`.
3. **O2 bar "the labeled AC is in the top 3 for at least 9 of 12": met (11 of 12).** But 10 of those 12 "labeled ACs" turn out to be promises the PR *implemented*, not changed (point 5), so this shows that O2 finds the right area, not that it predicts changes.
4. **Noise:** the AI check disagreed with the author on 12 of 35 PRs (34%). That is at the top of the 7-to-12 range OPTIONS expected for this enriched sample. 9 of the 12 cite "you forgot to name this FR", and only 2 say "this AC is now untrue".
5. **The sharper question changes the picture.** Both new Opus labelers found an existing AC made untrue in only **3 of 35 PRs** (#887, #920, #925). 16 PRs added behaviour no AC describes, 10 implemented or restored an AC, 5 changed nothing, and they split on 1. They agreed on 34 of 35.
6. **Of the 7 "missed" PRs, only #887 really breaks a promise.** Four are new behaviour with no AC (#843, #869, #884, #921) and two are genuine fixes (#910, #914). The real gap is unnamed FRs and catalog gaps, not stale ACs. That argues for O3's `catalog_gap` and FR naming more than for an "AC untrue" detector.
7. **Restorations are never called changes at the AC level** (0 cases). But the check does *flag* 4 PRs the labelers call fixes (#892, #910, #914, and #859, where they split), for a missing FR name or for a "restore" claim it doubts.
8. **At the AC level the check is weak.** Of the 3 real AC changes, it named the AC for #920 only. It flagged #887 for a missing FR (its question cites AC03, but no AC is listed as untrue) and agreed on #925. It also called FR-01.01 AC01 untrue on #883, which both labelers explicitly rejected.
9. **Ground truth is still LLM-made.** Both labeler pairs (BL0b and this one) are Opus reading the same packs, and Sonnet is the "different model". High agreement shows consistency, not truth, so the operator's 10 labels decide.
10. **Main risks:** "missing FR" flags on a third of PRs could become a reflex, like the old "none". AC-level detection is the weak spot. Several packs were cut for size (marked T below), mostly test files.

**Reading this:** O5 passes its bars, but what it catches is "you didn't name the FR / this is uncatalogued". It does not reliably catch "this AC is now untrue". If the operator confirms the labels, build O3 (forcing a named nearest AC or `catalog_gap`) plus O5 framed as an FR and catalog-gap check, and do not sell O5 as an AC-change detector yet.

## Method

| Step | What ran | Model | Blindness |
|---|---|---|---|
| 1 | 2 independent labelers (X, Y), each in 5 batches of 7 PRs (10 fresh agents), on the question "existing AC made untrue/incomplete (CHANGE) / implement-restore / new behaviour no AC describes (NEW) / no change (NONE)" | Opus | Saw only the packs and the catalog (copied to `replay2/inputs/`). No labels, no declarations. Y processed its PRs in reverse order. |
| 2 | AC-check: 5 fresh agents, 7 PRs each, pack + catalog + recorded declaration. Disagree if `ac_untrue`, `missing_fr`, `unacknowledged_gap` or `wrong_restore_claim` | Sonnet | Did not see any labels. |
| 3 | O2: 1 fresh agent, title (FR/AC ids redacted) + goal text where found + catalog, top 3 ACs | Sonnet | Saw no packs, labels or declarations. |

Declarations were matched PR to `work_completed` event through the iterate id in the pack's file list (35 of 35 matched). O2 "goal" text was found for 19 of 35, taken from the iterate spec / architecture brief / spec note at the merge commit (the "Problem" paragraph or opening text). The other 16 had title only. Prompts: `inputs/PROMPT_step*.md`. Raw outputs: `raw/`. Joined data: `scores.json`.

**Pack truncation:** every pack is capped (~750 lines). Later diffs, mostly tests, are cut. At least one agent set `truncation_matters` on 883, 897, 900, 920 and 936 (T below). Nothing was re-run.

## Pass bars

| Bar (from OPTIONS O2/O5) | Result | Met? |
|---|---|---|
| O5: flags ≥ 6 of 7 known misses (#843 #869 #884 #887 #910 #914 #921) | 6 of 7 (not #843) | yes |
| O5: flags 0 of 5 no-change PRs (#848 #855 #900 #908 #911) | 0 of 5 | yes |
| O5: operator agrees on ≥ 8 of 10 | pending (`OPERATOR_10.md`) | open |
| O2: labeled AC in top 3 for ≥ 9 of 12 | 11 of 12 (miss: #934; O2 put FR-01.18 AC03 there, which the new labelers also name) | yes |

Extra numbers:
- O2 vs the step-1 CHANGE ACs: the changed AC was in the top 3 for 3 of 3 (#887, #920, #925).
- O2 at FR level: a labeled FR was among the top-3 ACs' FRs for 26 of 28 FR-labeled PRs (misses #886, #919).
- O2 always proposes 3 ACs, including for the 5 no-change PRs, so its precision is not measured.

## Step 1: sharper labels

| | Count |
|---|---|
| Primary category agreement X vs Y | 34 / 35 (split: #859 IMPLEMENT_RESTORE vs NEW) |
| Behaviour yes/no agreement | 35 / 35 |
| CHANGE (both) | 3: #887, #920, #925. Same AC set on 887 and 925; 920 overlaps (both name FR-01.02 AC01 and FR-01.16 AC05) |
| NEW (both) | 16 |
| IMPLEMENT_RESTORE (both) | 10 |
| NONE (both) | 5 (exactly the BL0b no-change five; #918 moved from no/unclear to NEW) |

What became of the 12 BL0b AC-labeled PRs: **CHANGE 2** (#887, #925) · **IMPLEMENT_RESTORE 4** (#871, #892, #934, #937) · **NEW 6** (#837, #842, #869, #883, #924, #936). In those six, the named AC was implemented and new uncovered behaviour came with it. #920 is a new CHANGE that BL0b gave no AC.

## Step 2: AC-check (Sonnet) vs declaration and step-1 labels

Disagree on 12 / 35. Reasons (a PR can have several): `missing_fr` on 9, `ac_untrue` on 2 (#883, #920), `wrong_restore_claim` on 3 (#883, #892, #921), `unacknowledged_gap` on 2.

| PR | Declaration (intent / type / reason / FRs) | Step 1 (X/Y) | AC-check | Note |
|---|---|---|---|---|
| 843 ★ | change / infra / – / none | NEW / NEW | agree | not flagged; no AC names the model |
| 869 ★ | change / tooling / tooling-only / none | NEW / NEW | **disagree** missing_fr | |
| 884 ★ | change / tooling / tooling-only / none | NEW / NEW | **disagree** missing_fr | |
| 887 ★ | change / tooling / tooling-only / none | CHANGE (FR-01.17 AC03, AC04) | **disagree** missing_fr | question cites AC03, but no AC listed as untrue |
| 910 ★ | bug / tooling / restores / none | IMPL / IMPL | **disagree** missing_fr | flags a restore for the unnamed FR |
| 914 ★ | bug / tooling / restores / none | IMPL / IMPL | **disagree** missing_fr | same |
| 921 ★ | bug / tooling / restores / none | NEW / NEW | **disagree** missing_fr, wrong_restore | |
| 859 | bug / tooling / tooling-only / none | IMPL / NEW | **disagree** missing_fr | |
| 883 T | change / – / restores / 01,06,08,12 | NEW / NEW | **disagree** ac_untrue FR-01.01 AC01 | both labelers explicitly rejected AC01 |
| 886 | bug / tooling / restores / none | NEW / NEW | **disagree** missing_fr, gap | |
| 892 | bug / – / restores / FR-01.11 | IMPL / IMPL | **disagree** wrong_restore | low confidence |
| 919 | change / tooling / behaviour-preserving / none | NEW / NEW | **disagree** missing_fr | |
| 920 T | feature / – / behaviour-preserving / 01,02 | CHANGE / CHANGE | **disagree** ac_untrue FR-01.02 AC01, AC06, AC12 | only correct AC-level hit |
| 925 | feature / – / behaviour-preserving / FR-01.06 | CHANGE (FR-01.06 AC12) | agree | missed AC change |
| 848 855 900T 908 911 | no-change controls | NONE | agree | 0 false alarms |
| other 18 | | | agree | |

★ = one of the 7 known misses.

**Restorations or implementations flagged as AC changes:** 0. No AC the check called untrue was one a labeler called implemented. But 4 of its 12 disagreements fall on PRs the labelers call fixes (#892, #910, #914, and #859 where they split).

## Ground truth: what is LLM-made

- Every label here, BL0b A/B and this replay's X/Y, is an Opus reading of the same size-capped packs. X/Y agreement (34/35) and BL0b A/B agreement are consistency, not correctness.
- The "known misses" and "no-change" sets come from BL0b's LLM labels. The step-1 labels show that 6 of the 7 misses are not AC changes, so "flag the miss" really measures "flag the unnamed FR".
- The "different model" in step 2 is still Claude (Sonnet). A GPT/GLM run through the external-review path would be a more independent test.
- O2 inputs leak a little: titles are written after the work (e.g. #937 "…per FR-xx"), and architecture briefs are written during the run. Real start-of-run text would be vaguer.

## Files

- `OPERATOR_10.md`: 10 cards for the operator
- `scores.json`: per-PR joined data and summary numbers
- `declarations.json`: per-PR author declarations pulled from the event log
- `o2_inputs.json`: O2 inputs (redacted titles and goals)
- `raw/step1_{X,Y}_batch{1-5}.json`, `raw/step2_batch{1-5}.json`, `raw/step3_o2.json`: agent outputs
- `inputs/`: blind copies of the packs and catalog, per-batch declarations and the three prompts
