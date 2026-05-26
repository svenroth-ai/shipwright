# Code Review (Two-Tier + Optional External Cascade)

Detail for Kern Step 6.

## 6a: Self-Review (always)

See [self-review-checklist.md](self-review-checklist.md).

**Goal:** Quick inline quality check (~30 seconds).

1. Run through the 5-point checklist (Spec Compliance, Error Handling, Security, Test Quality, Naming)
2. For each: ok or fail with 1-sentence explanation
3. **Fix all failures** before proceeding
4. Re-run tests after fixes

## 6b: Full Code Review (conditional)

See [code-review-protocol.md](code-review-protocol.md) for the review process.

**Trigger full review when ANY of:**

- Diff exceeds **100 lines** of changed code
- Section is marked `risk: high` in the plan
- Changes touch **security-sensitive files** (auth, middleware, RLS policies, migrations)

**Otherwise:** Self-review is sufficient — skip to Step 7.

**Full review flow:**

1. Generate diff of all changes:

```bash
git diff HEAD > /tmp/shipwright-review-diff.txt
```

2. Spawn code-reviewer subagent with:
   - Section spec file path
   - Diff file path

3. Receive structured review JSON

**If findings exist:**

**Autonomous mode** (check `autonomy` in `shipwright_run_config.json`):
Fix all findings immediately — no AskUserQuestion. For each finding:

1. Apply the suggested fix
2. Run tests to verify no regressions
3. Log fix in decision log with context "auto-fixed (autonomous mode)"

Skip to Step 8 (Commit).

**Guided mode** (default):
See [code-review-interview.md](code-review-interview.md) for user interaction.
Present findings to user via AskUserQuestion:

- Accept -> fix the issue
- Decline -> log reason in decision log
- Defer -> create TODO comment in code

**Dashboard update:**

```bash
uv run "{shared_root}/scripts/tools/update_build_dashboard.py" \
  --project-root "$(pwd)" --section "{section_name}" --step 6 --detail "Code review" --session-id "{SHIPWRIGHT_SESSION_ID}"
```

## 6c: External Code Review Cascade (opt-in, default off)

After the internal `code-reviewer` subagent finishes, optionally cascade an
external LLM review of the same diff against the section spec. This is a
second-opinion gate, not a replacement for Step 6b.

**Trigger:** `external_code_review.enabled: true` in
`shipwright_build_config.json` (per-project or per-section override).
Default value when absent: `false`. The nested form keeps the door open for
future settings (`external_code_review.providers`,
`external_code_review.max_diff_lines`, etc.) without breaking the read
contract; iterate uses the same shape.

```jsonc
// shipwright_build_config.json — example opt-in
{
  "external_code_review": {
    "enabled": true
  },
  "sections": [...]
}
```

**Operator warning — diff exposure:** Enabling this option transmits the
contents of the staged diff (including any code, comments, or strings
present in the changed files) to a third-party LLM provider (OpenRouter,
Gemini, or OpenAI direct, depending on which keys are configured). Do NOT
enable it for projects where the diff may contain secrets, customer data,
or code under restrictive license/NDA terms. The diff is already written
to `/tmp/shipwright-review-diff.txt` for Step 6b — that file is what gets
sent.

**Skip rules (no opt-in needed):**

- Missing API keys -> cascade silently skipped, marker records `skipped_config_disabled`.
- Empty diff (`/tmp/shipwright-review-diff.txt` 0 bytes / whitespace only) -> CLI short-circuits, no provider call, marker records `skipped_user_opt_out` with reason "empty_diff".

**Cascade flow (when enabled):**

1. The diff file from Step 6b is reused — no new git diff invocation:

```bash
# /tmp/shipwright-review-diff.txt was written in Step 6b
```

2. Run the external review:

```bash
uv run "{shared_root}/scripts/tools/external_review.py" \
  --mode code \
  --diff-file /tmp/shipwright-review-diff.txt \
  --spec-file "{section_spec_path}" \
  --plugin-root "{plan_plugin_root}"
```

(`--plugin-root` is unused in code-mode prompt loading but the argument
remains required for CLI shape parity with plan/iterate modes.)

3. Parse JSON output (`reviews.gemini.feedback` + `reviews.openai.feedback`).
   Merge any high/medium severity findings into the in-flight findings list
   from Step 6b. Treat them with the same autonomous/guided handling rule
   as the internal subagent findings.

4. Write the review marker:

```bash
uv run "{shared_root}/scripts/checks/mark-review-state.py" \
  --planning-dir "{planning_dir}" \
  --review-type code \
  --status "{completed | skipped_user_opt_out | skipped_config_disabled}" \
  --provider "{openrouter | null}" \
  --findings-count {N}
```

This writes `external_code_review_state.json` (distinct from the
plan-step `external_review_state.json`). Compliance evidence collection
reads either marker independently — the new file does not collide with
the existing plan/iterate gate.

5. Log accepted findings to the build dashboard and decision log via the
   same write_decision_log.py path used by Step 6b — section
   `External Code Review — {section_name}`.

If cascade is disabled or skipped, proceed to Step 7 with only the
internal subagent's findings. The cascade adds findings; it does NOT
gate progression.
