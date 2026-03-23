# Validation Loop Protocol

Claude Architect Best Practice (Domain 4.4): "Retry with specific errors. Stop when the data isn't in the source."

## Pattern: Extract → Validate → Retry with Specific Feedback

After each test failure or implementation attempt, follow this protocol:

### 1. Specific Error Feedback

**Bad:** "Tests failed. Try again."

**Good:** "Test `login.test.ts:42` failed: `getUser()` returned `null` but expected `{id: '1', name: 'Alice'}`. The spec (section 01-auth, line 15) requires user lookup to return full user object. Check that the Supabase query includes all columns."

### 2. Retriable vs Terminal Errors

| Error Type | Example | Action |
|-----------|---------|--------|
| **Retriable** | Test assertion mismatch, type error, missing import | Fix and retry |
| **Retriable** | API timeout during test | Retry (transient) |
| **Terminal** | Spec references API from section 02-data (not yet built) | Log as dependency, move on |
| **Terminal** | Required env var not configured | Ask user, don't retry |

### 3. Stop Conditions

Stop retrying when:
- The failure is due to a **missing dependency from another section** → log as dependency in decision_log.md
- The data/API **doesn't exist yet** and can't be mocked → skip with `// TODO(shipwright): requires section XX`
- **3 attempts** have been made with the same root cause → escalate to user via AskUserQuestion

### 4. Decision Log Entry

When stopping early, log:
```markdown
## [Section] — Validation Stop
- **Error:** {specific error}
- **Attempts:** {N}
- **Root cause:** {dependency | missing data | requires user input}
- **Action taken:** {skipped with TODO | asked user | deferred}
```
