# Pre-commit Hook Handling

## Philosophy

Never bypass pre-commit hooks. They exist for a reason.
Fix the underlying issue instead of using `--no-verify`.

## Common Failures

### Linting (ESLint, Prettier)
```bash
npx eslint --fix .
npx prettier --write .
```
Re-stage and re-commit.

### Type Errors (TypeScript)
Fix the type error in the source code. Don't add `@ts-ignore`.
Re-run `npx tsc --noEmit` to verify.

### Test Failures
If pre-commit runs tests and they fail:
1. Check if the failure is from your changes
2. Fix the test or the implementation
3. Don't disable the test

## After Fix

Always create a NEW commit after fixing pre-commit issues.
Never amend the previous commit (it didn't happen — the hook prevented it).
