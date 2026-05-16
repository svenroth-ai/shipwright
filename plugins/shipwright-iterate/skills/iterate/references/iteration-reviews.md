# Iteration Reviews Reference

Consolidated protocol for: Self-Review, Full Code Review trigger, Session Handoff.

---

## Why Self-Review is Mandatory

Self-review is non-negotiable regardless of complexity or external-review
availability. Trivial changes hide trivial mistakes; small iterations
accumulate. This is the "2x denken" pass — re-read your own diff with a
critic's eye before committing.

- **Trivial / small complexity:** Self-Review Checklist is the only review.
- **Medium+ complexity:** Self-Review + External LLM Review (or interactive
  opt-out per [iteration-planning.md](iteration-planning.md) Branch B) +
  code-reviewer subagent for large diffs.

---

## Self-Review Checklist

Run AFTER implementation, BEFORE commit. All change types, all complexity levels.
This is the 8-point checklist; for each item: pass or fail + 1-sentence
explanation. Fix all failures before committing.

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

### 7. Affected Boundaries
Were producer and consumer of any changed serialized format identified,
AND was a real round-trip probe run? See `references/round-trip-tests.md`.
- For every changed serialized format: producer + consumer pair listed
- Round-trip test (producer→file-on-disk→consumer) exists and passes
- For user-edited formats: all 8 probe categories from
  `references/boundary-probes.md` checked
- If `touches_io_boundary` risk flag fired: round-trip test is mandatory
  (Safety-enforced in Override Classes — skippable only with explicit
  risk acknowledgment in the iterate ADR)
- If no boundaries touched: mark `n/a` with one-line justification

### 8. Test Hygiene Probe
Run the static probe against changed test files and resolve any findings.
The probe surfaces silent-skip patterns that mask CI tooling absence or
collection-time-only `@pytest.mark.skipif` decorators that can't carry a
CI gate structurally. See ADR-044 + ADR-045.

```bash
uv run shared/scripts/tools/scan_test_hygiene.py --diff
```

- **Mandatory at medium+**
- Advisory at trivial / small
- Skip rules: an explicit `# test-hygiene: allow-silent-skip — <rationale>`
  marker comment on the offending line (or in a contiguous comment block
  immediately above it) suppresses a finding. The rationale must
  describe a setup-condition or upstream-state gate (not a binary-on-PATH
  gate, which is exactly what the rule catches).
- Exit code: `0` = no findings (pass); `1` = findings present (fail —
  either fix or document with the marker); `2` = usage error.

### Output Format
```
Self-Review:
  1. Spec Compliance:    [pass/fail] {explanation}
  2. Error Handling:     [pass/fail] {explanation}
  3. Security Basics:    [pass/fail] {explanation}
  4. Test Quality:       [pass/fail] {explanation}
  5. Performance Basics: [pass/fail] {explanation}
  6. Naming & Structure: [pass/fail] {explanation}
  7. Affected Boundaries:[pass/fail/n/a] {explanation}
  8. Test Hygiene Probe: [pass/fail/n/a] {explanation}

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

## External Code-Review Cascade (medium+, default on)

After the in-process `code-reviewer` subagent finishes (when it fired —
see "When to Spawn" above), cascade an external LLM review of the same
diff against the iterate spec. This is a second-opinion gate that mirrors
the existing mini-plan-review Branch A/B/C interactive opt-out flow.

### Trigger Rule

Cascade fires **iff the internal `code-reviewer` subagent fired in this
run** — same gate as the trigger above. No new threshold:

- Diff > 100 lines, OR
- security-sensitive files touched, OR
- complexity = medium+

For trivial/small iterates the cascade does NOT run, even if API keys are
present. Self-review is the only review for those.

For build (per-section opt-in, default off) see
`{build_plugin_root}/skills/build/SKILL.md` Step 6c.

### Operator Warning — Diff Exposure

Enabling the external code-review cascade transmits the staged diff to
a third-party LLM provider (OpenRouter, Gemini direct, or OpenAI direct,
depending on which keys are configured). Diffs are higher-risk than
plans because they may contain secrets, customer data, or code under
restrictive license terms accidentally checked into the patch. If those
risks apply to your project, set
`shipwright_iterate_config.json` → `external_code_review.enabled: false`
to opt out at the project level (one-time switch — falls into Branch C
"user_disabled" below).

### Branch A — `available` (keys present, not user-disabled)

```bash
git diff HEAD > /tmp/shipwright-review-diff.txt

uv run "{shared_root}/scripts/tools/external_review.py" \
  --mode code \
  --diff-file /tmp/shipwright-review-diff.txt \
  --spec-file "{iterate_spec_path}" \
  --plugin-root "{plan_plugin_root}"
```

Parse `reviews.gemini.feedback` + `reviews.openai.feedback`. Merge any
high/medium-severity findings into the iterate ADR's
`External-Code-Review-Findings` table. Address before commit (apply fix,
rerun tests) — same disposition pattern as the mini-plan-review block:
each finding marked `accepted-and-fixed` or `rejected-with-reason`.

If the CLI returns `skipped: "empty_diff"` (which happens when the diff
file is empty or whitespace-only), the cascade is recorded as
`skipped_user_opt_out` with reason `empty_diff` and the run continues.

### Branch B — `missing_keys`

STOP and ask the user verbatim:

> External LLM code-review is the recommended cascade for this medium+
> shared-infra change, but no `OPENROUTER_API_KEY` (or
> `GEMINI_API_KEY` / `OPENAI_API_KEY`) was found in `.env.local`.
>
> **Option 1 (recommended):** Add a key to `.env.local` and say "ready" —
> I'll re-check and run the cascade.
> **Option 2:** Skip external code-review. The internal subagent already
> ran and its findings stand. Mark this run as opted-out in the iterate
> ADR.
>
> Which option?

- Option 1 → re-check via `check-external-review-keys.py`, then Branch A.
- Option 2 → log opt-out (with user's reason) in the iterate ADR. No
  further work — the internal subagent review remains the cascade gate.

### Branch C — `user_disabled`

`shipwright_iterate_config.json` → `external_code_review.enabled: false`.
Print a notice and skip the cascade. The internal subagent review remains.

The cascade has its own opt-out flag — it is intentionally NOT controlled by
the plan/iterate-mode `external_review.feedback_iterations: 0` knob. Users
can disable plan/iterate external review while keeping the code-review
cascade on, and vice versa.

### Write the cascade marker (all branches)

```bash
uv run "{shared_root}/scripts/checks/mark-review-state.py" \
  --planning-dir "{iterate_planning_dir}" \
  --review-type code \
  --status "{completed | skipped_user_opt_out | skipped_config_disabled}" \
  --provider "{openrouter | null}" \
  --findings-count {N} \
  --reason "{optional reason — e.g. 'empty_diff', 'user opted out: offline'}"
```

This writes `external_code_review_state.json` — distinct from the
plan/iterate-step `external_review_state.json`. The two markers
represent independent gates and never collide.

---

## Session Handoff Protocol

### Trigger
Context pressure detected: conversation exceeds ~70% of available context window.
Heuristic signals:
- Tool result truncation increasing
- 15+ tool calls on a single iterate run
- Agent notices it's losing track of earlier context

### Required Payload
Write to `.shipwright/agent_docs/session_handoff.md`:

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
/shipwright-iterate  (Step B1 detects the iterate/* branch and offers Resume/Abandon/Complete)
```

### Generation Rules
- Best-effort: write what's known, don't block on missing fields
- Commit to branch before handoff
- Include enough context for next session to resume without re-reading all files

### How Resume Works (Step B1 in SKILL.md)
When a new session starts, Step B1 checks for existing `iterate/*` worktrees and `session_handoff.md`. If found, it offers three options: Resume (`cd` into the worktree, skip to the remaining phase), Abandon (remove the worktree + branch, start fresh), or Complete (skip to finalization). The handoff file is the primary source of truth for what was done and what remains.
