# Architecture Brief: track-decision-drops

## Problem

`.shipwright/agent_docs/decision-drops/` (per-run ADR staging, folded into
`decision_log.md` only at `/shipwright-changelog` release time) is
gitignored. At the current ~10-week release cadence, architectural
decisions exist only on one machine for that whole window: absent from CI,
absent from any second checkout, lost with the disk. 214 drops currently
back this up.

## Options considered

1. **Track the whole directory as-is, no other change.** Flip the
   `.gitignore` rule in the three onboarding locations. The write path stays
   unchanged (iterate F3 writes directly onto the main checkout's disk,
   bypassing the calling iterate's own worktree).
2. **Track the directory, but redirect the write into the iterate's own
   worktree**, so the drop is staged and committed as part of that iterate's
   own commit and ships in its own PR — the same model already used for
   `shipwright_events.jsonl`, `reviews.json`, and other per-run artifacts in
   this codebase.
3. **Fold immediately instead of staging.** Have iterate F3 append directly
   to `decision_log.md` (skip the staging/drop step and the release-time
   aggregation entirely), assigning the ADR number at write time.
4. **Do nothing / leave gitignored, shorten the release cadence instead.**
   Solve the 10-week gap by releasing more often rather than changing what's
   tracked.

## Reviewers: answer straight — approve as designed, or name the smallest
alternative and why.
