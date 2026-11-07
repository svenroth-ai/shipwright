# ac-at-start Q2 phase 1: seeded measurement (INCOMPLETE, bar not met so far)

Date: 2026-11-07. Reviewer: `shipwright-build:spec-reviewer` with model=opus, given the CURRENT prompt from this branch plus
`ac-claims.json`. Cases were blind (shuffled, neutral names). Per case: the PR's own description as spec, the PR diff without
`.shipwright/`, events, changelog and docs, and one claim.

Set: 5 correct ACs (#887, #920, #925, backfill AC09 force-push from #859, backfill AC15 commit-time coverage from #839)
and 5 altered copies. Altered wording was written by the assistant (author bias).

| Case | Arm | PR | Reviewer verdict | Counts as |
|---|---|---|---|---|
| case-02 | correct | #859 (force-push guard) | diverges (fallback grep over-blocks when the guard fails, e.g. `git push -f origin feature/main-fix`) | FALSE diverges |
| case-03 | altered | #887 (drop Claude review workflows) | diverges (earlier-adopted projects are deliberately left untouched) | true diverges |
| case-01, 04-10 | mixed | | NOT RUN | |

Why not complete: the runner's spawn guard allows only 3 spec-reviewer spawns per runner; they were used on cases 01-03.
Case 01 was still running when this was written. The kit for all 10 cases is in the scratchpad (`seed/case-NN`); key in
`seed_key_private.json`.

Reading: the bar is "0 false diverges on the correct five". Case-02 already breaks it. The reviewer's reason is arguably a
real finding (the fallback does block when the guard errors, and the AC says a failure never blocks), so the AC wording of
the backfill may itself be inaccurate; that is exactly the "evidence for a person, not proof" case. Per the plan: do NOT merge.
