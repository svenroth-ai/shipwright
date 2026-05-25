# Error Handling

## Test Failures

1. Root cause investigation — read error output, identify failing
   component.
2. Pattern analysis — same root cause as last attempt? Change approach.
3. Hypothesis — state what you'll fix and why before changing code.
4. Fix and verify — targeted fix, then re-run tests.
5. If stuck after 3 attempts: escalate to user.

## Pre-commit Hook Failures

- Linting failures: auto-fix and re-commit.
- Type errors: fix and re-commit.
- Never bypass hooks with `--no-verify`.

## Missing Sync Config

- Skip FR mapping (`affected_frs = TBD`).
- Skip drift check in finalization.
- Default to medium complexity (conservative).

## Session Handoff

If context pressure detected during medium+ changes, see
`references/iteration-reviews.md` for handoff protocol.
