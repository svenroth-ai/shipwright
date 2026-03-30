# Implementation Loop (TDD)

## Red-Green-Refactor Cycle

### Red: Write Failing Tests
1. Create test file in the location specified by the section
2. Write test cases that describe expected behavior
3. Run tests — they MUST fail
4. If tests pass immediately: you're testing the wrong thing or it's already implemented

### Green: Make Tests Pass
1. Write the minimum code to make tests pass
2. Don't optimize yet — just make it work
3. Run tests after each change
4. Stop when all tests pass

### Refactor: Clean Up
1. Remove duplication
2. Improve naming and structure
3. Run tests after each refactor step
4. Tests must still pass

## Per-Section Loop

For each section from /shipwright-plan:

```
1. Read section spec
2. Install dependencies
3. Write tests (RED)
4. Implement (GREEN)
5. Refactor (optional)
6. Code review
7. Fix review findings
8. Commit
```

## When Tests Won't Pass

Follow the [debugging-protocol.md](debugging-protocol.md):

1. **Investigate root cause** before changing code (Phase 1)
2. **Check if same root cause** as previous attempt (Phase 2) — if yes, the approach is wrong
3. **State hypothesis** before writing the fix (Phase 3)
4. **Fix and verify** (Phase 4)

**Escalation triggers:**
- 2 failed fixes with the same root cause → Architectural Reevaluation
- 3 failed fixes total → Escalate to user via AskUserQuestion

**Never** skip or weaken a test. **Never** retry blindly without root-cause analysis.
