# Code Review (Two-Tier + Optional External Cascade)

Detail for Kern Step 6.

## Reviewer Cascade — Spec → Code → Doubt (overview)

Step 6 runs a three-stage reviewer cascade, in this fixed order, after the
always-on 6a self-review:

```
spec-reviewer (Stage 1, HARD-GATE)  ->  code-reviewer (Stage 2, quality)  ->  doubt-reviewer (Stage 3, conditional)
```

Each stage is a distinct subagent prompt under `agents/`:
`agents/spec-reviewer.md`, `agents/code-reviewer.md`, `agents/doubt-reviewer.md`.

### Stage 1 — `spec-reviewer` (HARD-GATE)

Spawn the `spec-reviewer` subagent with the section/iterate spec path and the
diff. It answers one question — **does the code match the spec?** — and returns
`{"verdict": "PASS" | "REJECT", "spec_citations": [...]}`.

- A **REJECT** is a HARD-GATE: it **blocks Stage 2**. Every REJECT entry carries
  an explicit `spec_ref` citing the exact spec file:line/section the diff
  violates. The implementer fixes the divergence; you re-invoke `spec-reviewer`
  on the updated diff. **The `code-reviewer` (6b) is NOT invoked until the
  spec-reviewer returns PASS** — keep the re-review loop running until then.
- Trigger: **whenever the full code review (6b) runs** — diff > 100 lines,
  section `risk: high`, or security-sensitive files. Stage 1 and Stage 2 share
  one trigger so Stage 1 always precedes Stage 2; there is no path where the
  `code-reviewer` runs without a prior spec-reviewer PASS. A trivial diff that
  skips 6b relies on the 6a self-review's Spec-Compliance item (item 1) instead.
- This is a spec-**compliance** gate only — it does not judge code quality. That
  is Stage 2's job and is exactly why the two stages are separate (Superpowers
  two-stage pattern): a clean implementation of the wrong spec still fails Stage 1.

### Stage 2 — `code-reviewer` (quality)

Once Stage 1 PASSes, run the existing 5-axis `code-reviewer` (6b below). Nothing
about the existing flow changes; it simply now runs **behind** the spec gate.

### Stage 3 — `doubt-reviewer` (conditional, advisory)

**After** the `code-reviewer` passes, conditionally spawn the `doubt-reviewer` —
a fresh-context, disprove-biased adversary (Osmani doubt-driven). It fires
**only** when the diff touches a non-trivial surface:

| Trigger | Example paths / signals |
|---|---|
| **Migrations** | `supabase/migrations/*.sql`, any schema change |
| **Async / concurrency** | `await` in loops, parallel writes, shared mutable state, locks, ordering |
| **Cross-plugin imports** | `plugins/shipwright-X` importing from `plugins/shipwright-Y`; new module dependency edge |
| **Irreversible ops** | deletes, destructive writes, side-effecting external calls, payments |

A diff that touches **only** trivial surfaces — **docs-only** (`README.md`, `*.md`
prose), comments, test fixtures, a one-line copy change — does **NOT** trigger
Stage 3. The change is too trivial to justify an adversarial pass.

`doubt-reviewer` is **advisory-must-address**, NOT a hard gate: it raises doubts
the implementer must answer in writing before commit — fix it, or give a
**reasoned rebuttal** that disproves the doubt. A doubt met with a sound rebuttal
may proceed; an unanswered doubt may not. (Contrast Stage 1, which hard-blocks.)

### Internal-only boundary

All three cascade reviewers are **internal** Claude subagents. The optional 6c
external cascade stays a *generic code-quality* second opinion on the diff — the
`spec-reviewer` and `doubt-reviewer` roles are **not** cascaded to external LLM
providers (no external spec-compliance or doubt prompt templates). This keeps the
internal/external boundary clean and limits third-party diff exposure to 6c.

---

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
