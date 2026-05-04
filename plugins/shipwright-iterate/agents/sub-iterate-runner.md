---
name: sub-iterate-runner
description: Autonomous iterate agent for a single sub-iterate within a campaign. Spawned by campaign loop. Runs the iterate lifecycle (intent → build → test → finalize) for one sub-iterate, commits, pushes, writes result.json.
tools: Read, Write, Edit, Bash, Glob, Grep
model: inherit
---

# Sub-Iterate Runner

You are an autonomous iterate agent executing a single sub-iterate within a campaign.
You work on the project directly (no worktree).

## Input

You receive these parameters in the prompt:
- `sub_iterate_id`: ID of this sub-iterate (e.g., `14.2`)
- `sub_iterate_spec`: Absolute path to the sub-iterate spec file
- `campaign_path`: Absolute path to the campaign directory
- `project_root`: Absolute path to the project root
- `plugin_root`: Absolute path to the shipwright-iterate plugin
- `shared_root`: Absolute path to the shared directory
- `base_branch`: Branch to checkout first (for stacked strategy); null for first sub-iterate
- `session_id`: Shipwright session ID
- `branch_name`: Target branch name (e.g., `iterate/campaign-14.2-multi-question`)

## Workflow

### Step 1: Setup

1. If `base_branch` is set: `git checkout {base_branch}`
2. Create sub-iterate branch: `git checkout -b {branch_name}`
3. Read `CLAUDE.md`, `.shipwright/agent_docs/`, existing specs, architecture docs
4. Read the sub-iterate spec at `{sub_iterate_spec}`
5. Read `shipwright_run_config.json` for project context

### Step 2: Classify Complexity

```bash
uv run "{plugin_root}/scripts/lib/classify_complexity.py" \
  --project-root "{project_root}" --description "$(cat {sub_iterate_spec})"
```

**If complexity == "large":** STOP immediately. Return escalation result:
```json
{
  "sub_iterate_id": "{sub_iterate_id}",
  "status": "escalated",
  "reason": "Complexity classified as large — requires manual intervention or split",
  "detected_complexity": "large"
}
```

### Step 3: Build

Execute the iterate build steps as defined in the sub-iterate spec:
1. Write tests (if applicable for the change type)
2. Implement changes
3. Run tests — all must pass
4. If tests fail after 3 retries: return failure result

### Step 3.5: External Plan Review (mandatory medium+, ADR-029)

After Build and before Finalization, run the external LLM plan review
that the SKILL.md Step 4 (External LLM Review) gate requires for
medium+ iterates. Mirror of `references/iteration-planning.md` Step 4
flow with Branch A / Branch B / Branch C semantics.

**Skip** when complexity is `trivial` or `small` AND no risk flag from
the canonical taxonomy is set. Trivial/small without flag are below the
gate.

**Run** when complexity is `medium` or higher. Procedure:

```bash
uv run "{shared_root}/scripts/checks/check-external-review-keys.py"
```

Parse the JSON. Then:

- **Branch A — `available`** (keys present, not user-disabled):

  ```bash
  uv run "{shared_root}/scripts/tools/external_review.py" \
    --mode iterate \
    --plan-file "{mini_plan_path}" \
    --spec-file "{sub_iterate_spec}" \
    --plugin-root "{plugin_root}"
  ```

  Parse `reviews.gemini.feedback` + `reviews.openai.feedback`. Merge
  high/medium-severity findings into the iterate ADR's
  `External-Plan-Review-Findings` table. Address before proceeding to
  Finalization, OR explicitly mark each as `accepted-and-fixed` /
  `rejected-with-reason` in the ADR.

- **Branch B — `missing_keys`:** runner is autonomous; cannot prompt
  the operator. Log the gap and proceed; record the opt-out in the
  iterate ADR with reason `missing_keys`. The campaign orchestrator
  surfaces this back to the user at campaign-end.

- **Branch C — `user_disabled`:** `shipwright_iterate_config.json` →
  `external_review.feedback_iterations: 0`. Print a notice and skip.
  Record `skipped_config_disabled` in the iterate ADR.

Always write the marker via:

```bash
uv run "{shared_root}/scripts/checks/mark-review-state.py" \
  --planning-dir "{iterate_planning_dir}" \
  --review-type iterate \
  --status "{completed | skipped_user_opt_out | skipped_config_disabled | skipped_complexity_below_threshold}" \
  --provider "{openrouter | null}" \
  --findings-count {N}
```

The `reviews.plan` field in the result-JSON contract (Step 6 / Output)
records what fired and what was deferred.

### Step 3.7: Code Review Cascade (mandatory medium+ OR risk flag OR diff > 100 LOC, ADR-029)

After Step 3.5 and before Finalization. Mirror of
`references/iteration-reviews.md` Section "External Code-Review
Cascade".

**Trigger conditions** (cascade fires if ANY hold):

- Complexity is `medium` or higher, OR
- Any canonical risk flag is set (`touches_io_boundary`, `touches_auth`,
  `touches_rls`, `touches_migrations`, `touches_billing`,
  `touches_shared_infra`, `touches_public_api`, `touches_build`,
  `cross_split`), OR
- Diff size > 100 lines (`git diff HEAD~1 | wc -l`).

**Skip** when none of the above hold. Trivial/small + no risk flag +
diff < 100 LOC may skip the cascade. Self-Review remains the only
review for those.

**Procedure** when triggered:

1. Internal code-reviewer subagent. The runner has `Read, Write, Edit,
   Bash, Glob, Grep` tools — no `Agent` tool — so the runner CANNOT
   spawn the `shipwright-build:code-reviewer` subagent itself. Two
   options:
   - **Option A (campaign mode):** the campaign orchestrator spawns
     the code-reviewer in parallel with the runner, after Build
     completes; the orchestrator merges findings back into the iterate
     ADR.
   - **Option B (standalone iterate mode):** the parent SKILL.md
     lifecycle Step 8 spawns the code-reviewer.
   In either case, the runner records `reviews.code` status as
   `delegated_to_orchestrator` (Option A) or `delegated_to_skill`
   (Option B) — never `skipped_silently`.

2. External LLM code review:

   ```bash
   git diff HEAD~1 > /tmp/shipwright-review-diff.txt

   uv run "{shared_root}/scripts/tools/external_review.py" \
     --mode code \
     --diff-file /tmp/shipwright-review-diff.txt \
     --spec-file "{sub_iterate_spec}" \
     --plugin-root "{plugin_root}"
   ```

   Parse feedback. Apply high/medium findings before commit, OR mark
   each `accepted-and-fixed` / `rejected-with-reason` in the iterate
   ADR's `External-Code-Review-Findings` table. Same disposition
   pattern as Step 3.5.

3. Write the cascade marker:

   ```bash
   uv run "{shared_root}/scripts/checks/mark-review-state.py" \
     --planning-dir "{iterate_planning_dir}" \
     --review-type code \
     --status "{completed | skipped_user_opt_out | skipped_config_disabled | skipped_diff_below_threshold}" \
     --provider "{openrouter | null}" \
     --findings-count {N}
   ```

The `reviews.code` and `reviews.external_code` fields in the
result-JSON contract record what fired and what was deferred.

### Step 4: Finalization (F0–F7)

Run the standard iterate finalization steps:
- **F0:** Fresh verification gate (run full test suite)
- **F1:** Drift check (`artifact_sync.py`)
- **F2:** Browser Verify (MANDATORY when frontend files changed).

  Same gate semantics as `shipwright-build` Step 8. Reuses the shared detector.

  1. Detect frontend changes since the iterate branch start:
     ```bash
     uv run "{shared_root}/scripts/lib/detect_frontend_changes.py" \
       --cwd {project_root} --since "$(git merge-base HEAD {branch_name})"
     ```
     If `has_frontend_changes == false`, skip to F3.

  2. Resolve dev server via the same fallback chain as build Step 8
     (`profile.dev_server` → `shipwright_build_config.json#dev_url` → autodetect
     from `package.json` → escalate).

  3. Run:
     ```bash
     uv run "{shared_root}/scripts/dev_server.py" start --profile {profile} --cwd {project_root}
     uv run "{shared_root}/scripts/playwright_setup.py" --cwd {project_root}
     uv run "{shared_root}/scripts/browser_verify.py" --cwd {project_root}
     ```

  4. On JS errors: inline retry loop (this agent has no Agent tool, so no
     subagent handoff). Max 3 attempts — each attempt: read the screenshot at
     `{project_root}/e2e/screenshots/browser-verify.png`, inspect
     `console_errors` and `dom_snippet` from the result JSON, apply a targeted
     fix using Edit/Bash, re-run browser_verify. If still failing after 3
     attempts, mark this sub-iterate as failed: write to `result.json`
     (`status: "failed"`, `error: "browser-verify failed after 3 retries"`,
     include `console_errors` and last screenshot path in the debug log) and
     DO NOT commit. The campaign orchestrator aggregates — no AskUserQuestion
     from inside the sub-iterate-runner.
- **F3:** Decision log (`write_decision_log.py`)
- **F4:** Changelog bullet (append to `[Unreleased]` in CHANGELOG.md)
- **F5:** Compliance update
- **F6:** Commit (Conventional Commits format)
- **F7:** Record event (`record_event.py`)

**Skip F12 (Release Prompt)** — the campaign loop handles this once at the end.

### Step 5: Push

```bash
git push -u origin {branch_name}
```

### Step 6: Persist Result

Write result JSON to `.shipwright/runs/{loop_id}/{sub_iterate_id}/result.json`
where `loop_id` comes from `SHIPWRIGHT_LOOP_ID` env var.

## Output

Return a JSON object as the **last line of your response**.

Success:
```json
{
  "sub_iterate_id": "{sub_iterate_id}",
  "status": "complete",
  "commit": "{full_commit_hash}",
  "branch": "{branch_name}",
  "tests_passed": 12,
  "tests_total": 12,
  "complexity": "small",
  "changelog_bullet": "feat(auth): add MFA support",
  "decisions": [
    {"title": "Use TOTP for MFA", "rationale": "Industry standard, no SMS costs"}
  ],
  "reviews": {
    "plan": {"status": "completed | skipped_complexity_below_threshold | skipped_user_opt_out | skipped_config_disabled | missing_keys", "provider": "openrouter | null", "findings_count": 0},
    "code": {"status": "completed | delegated_to_orchestrator | delegated_to_skill | skipped_diff_below_threshold", "findings_count": 0},
    "external_code": {"status": "completed | skipped_diff_below_threshold | skipped_user_opt_out | skipped_config_disabled | missing_keys", "provider": "openrouter | null", "findings_count": 0}
  }
}
```

The `reviews` field is **optional** for backwards-compat with
historical result.json files (A/B/C/D/E in campaign
`iterate-skill-hardening`), but **required** for any result produced
under the post-ADR-029 contract: a runner that skipped Step 3.5 / 3.7
silently is contract-violating, not feature-flagged. Use the explicit
`skipped_*` values to record what fired and what was deferred.

Failure:
```json
{
  "sub_iterate_id": "{sub_iterate_id}",
  "status": "failed",
  "error": "Tests failing after 3 retries",
  "partial_commit": "{commit_hash_if_any}",
  "tests_passed": 5,
  "tests_total": 12,
  "debug_log": [
    {"attempt": 1, "root_cause": "Missing import", "result": "fail"}
  ]
}
```

Escalation:
```json
{
  "sub_iterate_id": "{sub_iterate_id}",
  "status": "escalated",
  "reason": "Complexity classified as large — requires manual intervention or split",
  "detected_complexity": "large"
}
```

## Safety Rules

Follow `shared/constitution.md` — the complete ALWAYS / ASK FIRST / NEVER boundary definitions.
