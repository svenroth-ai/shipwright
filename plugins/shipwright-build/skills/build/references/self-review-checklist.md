# Self-Review Checklist

Lightweight inline review (~30 seconds). Run BEFORE spawning the code-reviewer subagent.
For each item: ✅ pass or ❌ fail + 1-sentence explanation. Fix all ❌ before committing.

## Checklist

### 1. Spec Compliance
Does the code implement what the section spec requires?
- All features/endpoints/components mentioned in the spec exist
- No extra features added beyond the spec (YAGNI)

### 2. Error Handling
Are system boundaries properly guarded?
- API routes have try/catch with meaningful error responses
- External service calls (DB, APIs) handle failures
- No unhandled null/undefined at data boundaries

### 3. Security Basics
Is user input treated as untrusted?
- No raw user input in SQL queries (use parameterized queries)
- No raw user input in HTML output (use framework escaping)
- No hardcoded secrets, API keys, or tokens in source
- Auth/permission checks on protected routes

### 4. Test Quality
Do tests validate behavior, not implementation?
- Tests assert on outcomes, not internal state
- At least one happy-path and one error-path test per feature
- No tests that always pass regardless of implementation

### 5. Naming & Structure
Is the code consistent with the existing codebase?
- File and folder locations match profile conventions
- No single file exceeds 300 lines (split if needed)
- Variable/function names follow existing patterns

## Output Format

```
Self-Review:
  1. Spec Compliance:  ✅ All 3 FRs implemented (auth, profile, settings)
  2. Error Handling:   ✅ API routes wrapped, DB calls guarded
  3. Security Basics:  ❌ Missing auth check on /api/settings PUT
  4. Test Quality:     ✅ 8 tests covering happy + error paths
  5. Naming:           ✅ Consistent with existing patterns

Action: Fix item 3 before commit.
```

## When to Escalate to Full Code Review

After self-review passes, spawn the `code-reviewer` subagent ONLY if:
- Diff exceeds **100 lines** of changed code
- Section is marked `risk: high` in the plan
- Changes touch **security-sensitive files** (auth, middleware, RLS policies, migrations)

Otherwise, self-review is sufficient — proceed to commit.
