# Applying Interview Fixes

## Process

For each accepted review finding:

1. Make the code change
2. Run tests immediately
3. If tests break: revert and reconsider the fix approach
4. If tests pass: mark finding as resolved

## Batch Fixes

If multiple findings are in the same file:
- Apply all fixes to that file at once
- Run tests once after all fixes

## Regression Prevention

After all fixes applied:
1. Run full test suite (not just section tests)
2. If regressions found: fix them before proceeding
3. Each fix should be a separate logical change (helps with git blame)
