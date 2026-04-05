# Iteration Reviews Reference

Consolidated protocol for: Self-Review, Full Code Review trigger, Session Handoff.

---

## Self-Review Checklist

Run AFTER implementation, BEFORE commit. All change types, all complexity levels.
For each item: pass or fail + 1-sentence explanation. Fix all failures before committing.

### 1. Spec Compliance
Does the code implement what was specified?
- All features/endpoints/components from the spec exist
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

### 5. Performance Basics
Any obvious performance issues?
- No N+1 query patterns (loop of DB calls → use join/include)
- List endpoints paginated (no unbounded result sets)
- No large synchronous blocking in async handlers

### 6. Naming & Structure
Is the code consistent with the existing codebase?
- File and folder locations match project conventions
- No single file exceeds 300 lines (split if needed)
- Variable/function names follow existing patterns

### Output Format
```
Self-Review:
  1. Spec Compliance:    [pass/fail] {explanation}
  2. Error Handling:     [pass/fail] {explanation}
  3. Security Basics:    [pass/fail] {explanation}
  4. Test Quality:       [pass/fail] {explanation}
  5. Performance Basics: [pass/fail] {explanation}
  6. Naming & Structure: [pass/fail] {explanation}

Action: {Fix items X, Y before commit / All clear, proceed to commit}
```

---

## Full Code Review Trigger

### When to Spawn `code-reviewer` Subagent
- Diff exceeds **100 lines** of changed code
- Change touches **security-sensitive files** (auth, middleware, RLS policies, migrations)
- Complexity = **medium+** (always)

### When Self-Review is Sufficient
- Trivial/small complexity with no risk flags
- Diff under 100 lines
- No security-sensitive files touched

### Invocation
The code-reviewer subagent from `shipwright-build` is reused. Provide:
- The diff (`git diff HEAD~1`)
- The iterate spec or affected FR section
- The self-review results

---

## Session Handoff Protocol

### Trigger
Context pressure detected: conversation exceeds ~70% of available context window.
Heuristic signals:
- Tool result truncation increasing
- 15+ tool calls on a single iterate run
- Agent notices it's losing track of earlier context

### Required Payload
Write to `agent_docs/session_handoff.md`:

```markdown
# Session Handoff: {run_id}

## State
- **Run ID:** {run_id}
- **Branch:** {branch_name}
- **Complexity:** {original} → {current if escalated}
- **Phase:** {active phase when handoff triggered}

## Completed Phases
- [x] Intent classification: {type}
- [x] Complexity assessment: {level}
- [x] Iterate spec: {path or "skipped"}
- [x] Mini-plan: {path or "inline" or "skipped"}
- [ ] Build: {partial / not started}
- ...

## Files Modified
{list of files changed so far}

## Test Status
{last test run: pass/fail, counts}

## Remaining
{phases still to complete}

## Blocked/Parked
{any parked visual groups, unresolved items}

## Resume Command
/shipwright-iterate  (will detect branch and resume)
```

### Generation Rules
- Best-effort: write what's known, don't block on missing fields
- Commit to branch before handoff
- Include enough context for next session to resume without re-reading all files
