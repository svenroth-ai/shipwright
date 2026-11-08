# ac-at-start Q2 phase 1: seeded measurement (complete)

Date: 2026-11-08. Reviewer: `shipwright-build:spec-reviewer`, model=opus, CURRENT prompt from this branch plus `ac-claims.json`. Cases were blind (shuffled, neutral names). Per case: the PR description as spec, the PR diff without `.shipwright/`, events, changelog and docs, and one claim. Altered wordings were written by the assistant (author bias). Spec text is the PR description, so the set is easier than a real run.

| Case | Arm | PR | Reviewer | Result |
|---|---|---|---|---|
| 01 | correct | #839 | matches | ok |
| 02 | correct | #859 | diverges | see adjudication A |
| 03 | altered | #887 | diverges | caught |
| 04 | correct | #925 | matches | ok |
| 05 | correct | #920 | diverges | see adjudication B |
| 06 | correct | #887 | matches | ok |
| 07 | altered | #859 | diverges | caught |
| 08 | altered | #925 | diverges | caught |
| 09 | altered | #920 | diverges | caught |
| 10 | altered | #839 | diverges | caught |

Altered caught: 5 of 5 (bar: at least 4). Correct flagged by the label: 2 of 5 (bar as written: 0).

## Adjudication against the real code (coordinator, 2026-11-08)
- **A (#859, backfill AC09):** the AC says "a failure of this protection never blocks work". `validate_command.sh` degrades to a deliberately over-blocking grep when the guard fails; its pattern `[[:space:]:+/](main|master)\b` also matches `origin feature/main-fix`. So a guard failure CAN block a non-main force push. The reviewer is right; the backfilled AC wording overstates the design.
- **B (#920):** the AC says a refused package stops the run "before any project configuration is written". The documented start path (`plugins/shipwright-run/skills/run/SKILL.md` Step 4) runs `write-config` and only then `brief_dir_intake.py record`; a refusal is cleaned up by deleting the just-written run_config (prose, line 332). The reviewer is right; the AC overstates the order.

Both "false" alarms are genuine divergences between the written promise and the code, found with a cited line. Unsupported alarms: 0 of 5. The label "correct" was an assumption about old backfilled ACs, not proof.

## Reading
Bar met on the evidence reading (5/5 altered; 0 unsupported alarms), NOT met on the literal label reading (2/5). Both readings are recorded. Follow-ups (not in this PR): correct or re-scope AC09 (#859) and the #920 AC wording, or fix the code to fail open / write config after verification.

## Honest limits
n = 10, assistant-written alterations, PR description as spec. The set cannot show the false-alarm rate on real runs; that is measured on the first 20 iterates. Q2 stays warning-only until then.

## Correction 2026-11-08
The sentence in adjudication B (#920, "before any project configuration is written") was one of the assistant-written seed ACs of this measurement, derived from the PR text. It is not a catalog AC, so adjudication B concerns the seed wording only and no catalog fix is needed. Only A (FR-01.05 AC09) was a real catalog AC; it is corrected in iterate-2026-11-08-fix-overstated-acs. The follow-up line above ("correct or re-scope AC09 (#859) and the #920 AC wording") therefore reduces to AC09 alone.
