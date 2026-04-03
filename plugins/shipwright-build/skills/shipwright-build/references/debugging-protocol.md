# Debugging Protocol

Structured 4-phase approach when tests fail or implementation breaks.
Replaces blind retries with systematic root-cause analysis.

## Phase 1: Root Cause Investigation

Before changing ANY code, investigate:

1. **Read the full error output** — stack trace, assertion message, line numbers
2. **Identify the failing component** — which file, function, or module?
3. **Check inputs** — is the test calling with correct data? Is the API returning what's expected?
4. **Write a 1-sentence root cause** — e.g., "getUser() returns null because RLS policy blocks anon access"

**Output:** Root cause statement (1 sentence)

## Phase 2: Pattern Analysis

Compare with previous attempts (if any):

1. **Same root cause as last attempt?** → Go to Architectural Reevaluation (below)
2. **New root cause?** → Continue to Phase 3
3. **Transient error (timeout, network)?** → Retry once without code changes

**Key rule:** Two failed fixes with the same root cause = the approach is wrong, not the fix.

## Phase 3: Hypothesis

Before writing the fix:

1. **State your hypothesis** — "If I change X in file Y, the test will pass because Z"
2. **Predict the outcome** — what specific test output do you expect?
3. **Identify blast radius** — will this change break other tests?

**Output:** Hypothesis statement (1-2 sentences)

## Phase 4: Fix & Verify

1. Make the targeted fix based on hypothesis
2. Run tests
3. If tests pass → done
4. If tests fail → back to Phase 1 with new error output

## Architectural Reevaluation

Triggered when:
- **2 failed fixes with the same root cause**
- OR **3 failed fixes total** (regardless of root cause)

Steps:
1. Re-read the section spec — is the approach fundamentally wrong?
2. Check prerequisites — is a dependency from another section missing?
3. Consider alternative approaches — different data flow, different API, different pattern
4. **Escalate to user** via AskUserQuestion with:
   - Summary of what was tried (each attempt + root cause)
   - What the underlying issue appears to be
   - 2-3 alternative approaches (if you see them)

**Never retry a 4th time without user input or a fundamentally different approach.**

## Tracking Format

When debugging, maintain a mental log:

```
Attempt 1: Root cause: {X}. Hypothesis: {Y}. Result: {pass|fail}
Attempt 2: Root cause: {X or Z}. Hypothesis: {Y}. Result: {pass|fail}
[If same root cause twice → Architectural Reevaluation]
[If 3 total attempts → Escalate]
```
